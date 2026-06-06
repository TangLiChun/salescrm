from __future__ import annotations

import asyncio
import json
import re
import threading
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

from arin_lookup import lookup_asn, parse_asns_from_text
from app.contact_enrichment import enrich_contact_stream
from app.database import (
    bulk_delete_contacts,
    count_contacts,
    create_contact_note,
    dedupe_contacts,
    create_scheduled_job,
    delete_contact,
    get_contact,
    get_contact_stats,
    import_contacts,
    list_contact_notes,
    list_contacts,
    list_scheduled_jobs,
    mark_contact_sent,
    normalize_import_row,
    update_contact,
    update_contact_follow_up_status,
    update_scheduled_job,
)
from app.lead_preferences import get_prefs, preference_hints_for_llm, reset_prefs
from app.import_filters import parse_patterns
from app.lead_discovery import discover_leads_stream
from app.llm import (
    LLMError,
    chat_completion_with_tools_stream,
    format_assistant_message_for_api,
)
from app.pi_chat_store import (
    MAX_LLM_HISTORY_MESSAGES,
    compress_thread_context_until_current,
    get_pi_thread,
    history_for_llm,
)
from app.pi_context import compress_tool_result_for_llm, context_stats, needs_summary_update
from app.settings_store import get_setting, update_settings
from app.sources import brightdata_social as bs
from app.sources import forums as forums_source
from app.sources import shodan as shodan_source
from app.sources import web_unlocker as web_unlocker_source
from app.sources import web_search
from app.sources.channel_registry import get_channel_config
from app.sources.social_registry import FACEBOOK, LINKEDIN, SOCIAL_CHANNELS, X

SOCIAL_PROFILE_TOOLS: dict[str, bs.SocialChannelSpec] = {
    "collect_linkedin_profiles": LINKEDIN,
    "collect_x_profiles": X,
    "collect_facebook_profiles": FACEBOOK,
}

MAX_TOOL_ROUNDS = 12
MAX_HISTORY = MAX_LLM_HISTORY_MESSAGES
MAX_WEB_SEARCH_QUERIES = 4
TOOL_HEARTBEAT_SECONDS = 12
KNOWN_TOOL_NAMES = {
    "list_contacts",
    "import_leads",
    "get_contact",
    "update_contact",
    "mark_contact_sent",
    "delete_contacts",
    "add_contact_note",
    "list_contact_notes",
    "get_lead_preferences",
    "reset_lead_preferences",
    "dedupe_contacts",
    "get_import_filters",
    "update_import_filters",
    "list_schedules",
    "create_schedule",
    "update_schedule",
    "get_search_config",
    "shodan_search",
    "web_search",
    "fetch_web_pages",
    "search_hosting_forums",
    "lookup_asns",
    "discover_leads",
    "enrich_contact",
    "collect_linkedin_profiles",
    "collect_x_profiles",
    "collect_facebook_profiles",
}

def _social_profile_tool(
    tool_name: str,
    spec: bs.SocialChannelSpec,
    *,
    example_url: str,
) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": (
                f"通过 Bright Data 按 URL 抓取 {spec.label} profile。"
                f"需配置 Bright Data API Key；一次最多 {bs.DEFAULT_MAX_URLS} 个 URL"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": f"{spec.label} profile URL 列表，如 {example_url}",
                    },
                    "max_urls": {
                        "type": "integer",
                        "description": "最多抓取条数，默认 10",
                    },
                },
                "required": ["urls"],
            },
        },
    }


AGENT_TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "list_contacts",
            "description": "在 Sales CRM 中搜索联系人，避免重复导入",
            "parameters": {
                "type": "object",
                "properties": {
                    "q": {"type": "string", "description": "搜索组织/姓名/邮箱/备注"},
                    "limit": {"type": "integer", "description": "最多返回条数，默认 20"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "import_leads",
            "description": "将线索行导入 CRM；每行需含 email，并尽量填写 org 和 name；asn 为纯数字（如 395092，勿写 AS 前缀）",
            "parameters": {
                "type": "object",
                "properties": {
                    "rows": {
                        "type": "array",
                        "items": {"type": "object"},
                    },
                    "source": {"type": "string", "description": "来源标记，默认 pi-agent"},
                },
                "required": ["rows"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_contact",
            "description": "按 ID 获取单个联系人详情",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {"type": "integer"},
                },
                "required": ["contact_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "enrich_contact",
            "description": "为已有联系人查找同一组织/ASN 的其他 role 邮箱（RDAP+搜索+PeeringDB），可选自动导入",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {"type": "integer", "description": "CRM 联系人 ID"},
                    "min_score": {"type": "integer", "description": "最低相关度，默认 60"},
                    "auto_import": {"type": "boolean", "description": "≥60 分线索自动导入，默认 true"},
                },
                "required": ["contact_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "discover_leads",
            "description": "首选线索工具：PeeringDB 直连 + 全球 RDAP + 联网搜索 + LLM 评分/入库。找 peering 联系人、挖 ASN 邮箱、批量线索请用这个，不要手动串联 web_search",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "min_score": {"type": "integer", "description": "最低相关度，默认 60"},
                    "auto_import": {"type": "boolean", "description": "≥60 分线索自动导入，默认 true"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_asns",
            "description": "批量 RDAP 查询 ASN role 邮箱（ARIN/RIPE/APNIC 等），支持混排文本自动去重",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_stats",
            "description": "获取 CRM 联系人统计概览",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_contact",
            "description": "更新联系人信息（组织、姓名、备注、roles、跟进状态）",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {"type": "integer"},
                    "org": {"type": "string"},
                    "name": {"type": "string"},
                    "notes": {"type": "string"},
                    "roles": {"type": "string", "description": "逗号分隔的 role"},
                    "follow_up_status": {
                        "type": "string",
                        "description": "new/contacted/replied/invalid/interested",
                    },
                },
                "required": ["contact_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mark_contact_sent",
            "description": "标记联系人是否已发邮件",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {"type": "integer"},
                    "sent": {"type": "boolean"},
                },
                "required": ["contact_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_contacts",
            "description": "删除一个或多个联系人",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                    },
                },
                "required": ["contact_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_contact_note",
            "description": "为联系人添加跟进备注",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {"type": "integer"},
                    "body": {"type": "string"},
                },
                "required": ["contact_id", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_contact_notes",
            "description": "读取联系人的跟进备注时间线（按时间倒序）；写 outreach 或继续跟进前应先查看历史备注",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_id": {"type": "integer"},
                    "limit": {"type": "integer", "description": "最多返回条数，默认 20"},
                },
                "required": ["contact_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_lead_preferences",
            "description": "查看当前用户从导入/跟进/删除等行为中学到的线索偏好（角色、关键词、避开域名/组织、min_score 倾向等）；discover_leads/enrich_contact 已自动应用",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reset_lead_preferences",
            "description": "清空当前用户的线索偏好记忆，恢复默认筛选行为",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "dedupe_contacts",
            "description": "按邮箱去重联系人，保留最早记录",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_import_filters",
            "description": "读取系统设置中的线索导入黑名单/白名单（与设置页「线索导入」相同）",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_import_filters",
            "description": "更新线索导入黑名单/白名单；可整段替换或追加域名/邮箱模式（如 @cox.com）",
            "parameters": {
                "type": "object",
                "properties": {
                    "blocklist": {
                        "type": "string",
                        "description": "完整黑名单文本（每行一条，替换现有黑名单）",
                    },
                    "allowlist": {
                        "type": "string",
                        "description": "完整白名单文本（每行一条，替换现有白名单）",
                    },
                    "append_blocklist": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "追加到黑名单的模式，如 @cox.com",
                    },
                    "append_allowlist": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "追加到白名单的模式",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_search_config",
            "description": "查看数据渠道配置：搜索引擎、Web Unlocker、Shodan、LinkedIn/X/Facebook、PeeringDB/RDAP 等是否启用",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shodan_search",
            "description": "Shodan host 搜索（需 API Key）。按 org/asn 等 filter 查互联网资产，补充 ASN/组织/域名",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": 'Shodan 查询，如 org:"Google" 或 asn:15169',
                    },
                    "page": {"type": "integer", "description": "页码，默认 1"},
                },
                "required": ["query"],
            },
        },
    },
    _social_profile_tool(
        "collect_linkedin_profiles",
        LINKEDIN,
        example_url="https://www.linkedin.com/in/username/",
    ),
    _social_profile_tool(
        "collect_x_profiles",
        X,
        example_url="https://x.com/username",
    ),
    _social_profile_tool(
        "collect_facebook_profiles",
        FACEBOOK,
        example_url="https://www.facebook.com/username",
    ),
    {
        "type": "function",
        "function": {
            "name": "search_hosting_forums",
            "description": (
                "在 LowEndTalk / WebHostingTalk 搜索主机/VPS/peering 相关帖子。"
                "LowEndTalk 可直连；WebHostingTalk 站内搜索需 Web Unlocker，"
                "两者均会尝试 site: 搜索引擎查询"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "搜索关键词，如公司名、ASN、VPS provider"},
                    "forums": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["lowendtalk", "webhostingtalk"]},
                        "description": "限定论坛，默认搜索所有已启用论坛",
                    },
                    "max_results": {"type": "integer", "description": "最多返回条数，默认 12"},
                },
                "required": ["keyword"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_web_pages",
            "description": (
                "Bright Data Web Unlocker 抓取网页正文（Markdown）。"
                "用于 peering/contact/NOC 等页面；SERP snippet 为空时尤其有用。"
                "需配置 Web Unlocker Zone；与 SERP 共用 Bright Data API Key"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "要抓取的 https URL 列表",
                    },
                    "max_urls": {
                        "type": "integer",
                        "description": f"最多抓取条数，默认 {web_unlocker_source.DEFAULT_MAX_URLS}",
                    },
                },
                "required": ["urls"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "仅用于快速查单个资料或验证 URL；找线索/Peering 联系人请用 discover_leads（含 PeeringDB+RDAP），不要用它替代 discover_leads",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "单个搜索词"},
                    "queries": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "多个搜索词（与 query 二选一，一次最多 4 条）",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "每个 query 最多返回条数，默认 8",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_schedules",
            "description": "列出定时 AI 线索发现任务",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_schedule",
            "description": "创建定时/持续线索发现任务。run_mode=continuous 表示一轮完成后自动继续；interval 表示按固定间隔运行",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "任务名称"},
                    "query": {"type": "string", "description": "与 discover_leads 相同的自然语言搜索描述"},
                    "run_mode": {
                        "type": "string",
                        "enum": ["continuous", "interval"],
                        "description": "continuous=持续运行；interval=固定间隔",
                    },
                    "interval_minutes": {
                        "type": "integer",
                        "description": "固定间隔模式下的分钟数（15-10080），默认 360",
                    },
                    "cooldown_minutes": {
                        "type": "integer",
                        "description": "持续模式下每轮间隔分钟数，默认 15",
                    },
                    "min_score": {"type": "integer", "description": "最低评分，默认 60"},
                    "auto_import": {"type": "boolean", "description": "是否自动导入，默认 true"},
                },
                "required": ["name", "query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_schedule",
            "description": "更新定时任务（启用/停用、改间隔、改描述等）",
            "parameters": {
                "type": "object",
                "properties": {
                    "schedule_id": {"type": "integer", "description": "任务 ID"},
                    "name": {"type": "string"},
                    "query": {"type": "string"},
                    "enabled": {"type": "boolean"},
                    "run_mode": {"type": "string", "enum": ["continuous", "interval"]},
                    "interval_minutes": {"type": "integer"},
                    "cooldown_minutes": {"type": "integer"},
                    "min_score": {"type": "integer"},
                    "auto_import": {"type": "boolean"},
                },
                "required": ["schedule_id"],
            },
        },
    },
]

SYSTEM_PROMPT = """你是 Sales CRM 的 Pi 助手，帮助销售/BD 人员操作网络运营商联系人库。

能力：
- lookup_asns：已知 ASN 列表时，批量 RDAP 查 role 邮箱
- discover_leads：首选线索工具 — PeeringDB + RDAP + 联网搜索 + 社交媒体（LinkedIn/X/Facebook，若启用）+ LLM 评分
- collect_linkedin_profiles / collect_x_profiles / collect_facebook_profiles：Bright Data 按 URL 抓社交 profile
- fetch_web_pages：Bright Data Web Unlocker 抓 peering/contact 等页面正文（需 Web Unlocker Zone）
- search_hosting_forums：LowEndTalk / WebHostingTalk 论坛搜索
- web_search：仅快速查资料，不要用它做线索挖掘主流程
- get_search_config：查看各数据渠道配置（搜索/社交/Shodan/PeeringDB 等）
- shodan_search：Shodan 资产搜索（org/asn filter），discover_leads 已自动接入
- enrich_contact：为已有联系人扩展更多联系方式，可 auto_import
- get_contact / list_contacts / import_leads：读取、搜索、导入联系人
- update_contact / mark_contact_sent / delete_contacts / add_contact_note / list_contact_notes：管理联系人与跟进备注
- get_lead_preferences / reset_lead_preferences：查看或重置 AI 学到的线索偏好（discover_leads/enrich 已自动应用）
- get_stats / dedupe_contacts：统计与去重
- get_import_filters / update_import_filters：导入黑名单/白名单（设置页同源）
- list_schedules / create_schedule / update_schedule：定时或持续自动找线索（≥60 分自动导入）

工具选用（重要）：
- 找 peering 联系人 / 挖 ASN 邮箱 / 批量线索 → discover_leads（auto_import=true, min_score=60），不要手动堆 web_search
- 已有明确 ASN 列表且只要 RDAP → lookup_asns
- 已有 CRM 联系人要扩展 → enrich_contact
- web_search 仅作补充；Bright Data markdown 模式 snippet 常为空，不可依赖；可配合 fetch_web_pages 抓正文
- 已有社交 profile URL → 用对应 collect_*_profiles；批量找线索仍用 discover_leads（会自动从搜索结果提取 URL）

联网搜索说明：系统设置 → AI 与搜索。搜索引擎优先级 brightdata > zhipu > tavily > serpapi > brave > duckduckgo。
社交媒体均走 Bright Data Scraper API（/datasets/v3/scrape），与 SERP 共用 API Key：
已配置渠道 Dataset ID 见系统设置；未配置时不会启用对应社交抓取。
用户问搜索引擎/数据渠道配置时，先 get_search_config 再回答。

跟进工作流：写 outreach、续跟、总结下一步前，先 get_contact + list_contact_notes 了解历史；必要时 add_contact_note 记录结论。
用户问「为什么搜得更严/避开某类域名」→ get_lead_preferences 解释；若要清空学习结果 → reset_lead_preferences（需用户明确同意）。

规则：简洁中文；屏蔽域名用 update_import_filters；导入前查重；不要编造数据。
入库：lead_score ≥ 60 直接 import_leads 或 discover_leads auto_import，无需再问用户。
import_leads 的 asn 必须是纯数字（如 395092），不要带 AS 前缀。
若线索含 linkedin/x/facebook/profile_url，导入时会自动写入联系人社交链接字段。
禁止只回复「让我查一下 / 我先搜一下」等开场白就结束；需要查 CRM 或联网时必须立刻调用对应工具。"""


async def _stream_lead_events(
    stream: AsyncIterator[dict[str, Any]],
    emit: ToolEmitter,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, str, str | None]:
    leads: list[dict[str, Any]] = []
    import_result = None
    message = ""
    error = None

    async for event in stream:
        event_type = event.get("type")
        if event_type == "status":
            msg = str(event.get("message") or "搜索中…")
            emit.progress(msg)
            emit.event({"kind": "status", "message": msg})
            if "评估" in msg:
                emit.event({"kind": "phase", "phase": "scoring"})
        elif event_type == "plan":
            plan = event.get("plan") or {}
            emit.event({"kind": "plan", "plan": plan})
            emit.progress(str(plan.get("summary") or "已生成搜索计划"))
        elif event_type == "source_result":
            emit.event(
                {
                    "kind": "source_result",
                    "source": event.get("source"),
                    "count": event.get("count", 0),
                    "preview": event.get("preview") or [],
                }
            )
            emit.progress(f"{event.get('source')}: {event.get('count', 0)} 条")
        elif event_type == "progress":
            emit.event(
                {
                    "kind": "progress",
                    "index": event.get("index"),
                    "total": event.get("total"),
                    "asn": event.get("asn"),
                    "network": event.get("network"),
                    "message": event.get("message"),
                }
            )
            emit.progress(
                str(
                    event.get("message")
                    or f"RDAP AS{event.get('asn')} ({event.get('index')}/{event.get('total')})"
                )
            )
        elif event_type == "asn_result":
            emit.event(
                {
                    "kind": "asn_result",
                    "asn": event.get("asn"),
                    "network": event.get("network"),
                    "candidate_count": event.get("candidate_count", 0),
                }
            )
            emit.progress(
                f"AS{event.get('asn')} · {event.get('candidate_count', 0)} 个邮箱候选"
            )
        elif event_type == "lead":
            leads.append(event["lead"])
            emit.event({"kind": "lead", "lead": event["lead"]})
        elif event_type == "error":
            error = str(event.get("message") or "搜索失败")
            break
        elif event_type == "done":
            leads = event.get("leads") or leads
            import_result = event.get("import")
            message = event.get("message") or ""
            emit.event(
                {
                    "kind": "done",
                    "message": message,
                    "lead_count": len(leads),
                    "import": import_result,
                }
            )

    return leads, import_result, message, error


def _leads_tool_result(
    leads: list[dict[str, Any]],
    *,
    message: str,
    import_result: dict[str, Any] | None,
    error: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if error:
        payload: dict[str, Any] = {"error": error, "leads": leads}
        if extra:
            payload.update(extra)
        return payload

    preview = [
        {
            "org": lead.get("org"),
            "email": lead.get("email"),
            "score": lead.get("lead_score"),
            "source": lead.get("source"),
        }
        for lead in leads[:15]
    ]
    payload = {
        "message": message,
        "lead_count": len(leads),
        "leads": leads,
        "leads_preview": preview,
        "import": import_result,
    }
    if extra:
        payload.update(extra)
    return payload


class ToolEmitter:
    def __init__(self, queue: asyncio.Queue[tuple[str, Any] | None]) -> None:
        self._queue = queue

    def progress(self, message: str) -> None:
        self._queue.put_nowait(("progress", message))

    def event(self, payload: dict[str, Any]) -> None:
        self._queue.put_nowait(("event", payload))


def _trim_history(
    history: list[dict[str, Any]],
    *,
    context_summary: str = "",
    summary_through: int = 0,
) -> list[dict[str, str]]:
    return history_for_llm(
        history,
        context_summary=context_summary,
        summary_through=summary_through,
    )


_TOOL_CONTENT_MARKERS = (
    "[{",
    "[工具",
    "[tool",
    "tool_calls",
    "tool_call",
    "dsml",
    "<|",
    "```json",
    '{"query',
    '{"queries',
    '"queries"',
    '{"name"',
    '{"function"',
    '"name":',
    '"arguments"',
    '"function":',
    '"type": "function"',
)


def _assistant_intro_before_tools(content: str) -> str:
    text = (content or "").strip()
    if not text:
        return ""
    lower = text.lower()
    cut_at = len(text)
    for marker in _TOOL_CONTENT_MARKERS:
        idx = lower.find(marker.lower())
        if idx >= 0:
            cut_at = min(cut_at, idx)
    for pattern in ("\n[", "\r[", "\n[{", "\r[{"):
        idx = text.find(pattern)
        if idx >= 0:
            cut_at = min(cut_at, idx)
    if cut_at == len(text) and text.startswith("["):
        cut_at = 0
    result = text[:cut_at].strip()
    if result.endswith("["):
        result = result[:-1].rstrip()
    return result


def _content_looks_like_tool_call(content: str) -> bool:
    lower = (content or "").lower()
    if any(marker in lower for marker in _TOOL_CONTENT_MARKERS):
        return True
    return bool(re.search(r'^\s*[\[{]', content or ""))


def _content_is_tool_json_fragment(content: str) -> bool:
    text = (content or "").strip()
    if not text:
        return False
    if text in ("[", "{", "(", "[{", "({"):
        return True
    if re.fullmatch(r"[\[\{\(,]+", text):
        return True
    if re.match(r"^[\[\{]", text) and len(text) < 24:
        return True
    return False


def _meaningful_assistant_content(content: str) -> str:
    visible = _assistant_intro_before_tools(content)
    if not visible or _content_is_tool_json_fragment(visible):
        return ""
    return visible


def _assistant_promises_tool_use(content: str) -> bool:
    text = (content or "").strip()
    if not text:
        return False
    if text.endswith(("：", ":", "…", "...")):
        return True
    lower = text.lower()
    markers = (
        "我先",
        "让我",
        "我来",
        "正在",
        "接下来",
        "马上",
        "帮你查",
        "帮你搜",
        "拉一下",
        "补查",
        "再扫",
        "再查",
        "搜索 crm",
        "查一下",
        "筛出",
    )
    return any(marker in lower for marker in markers)


def _extract_json_args(text: str) -> dict[str, Any]:
    start = text.find("{")
    if start < 0:
        return {}
    blob = text[start:]
    blob = re.sub(r"<\|[^|>]*\|>", "", blob, flags=re.I)
    blob = re.sub(r"<\s*/?\s*\|\s*\|[^>]*>", "", blob, flags=re.I)
    blob = blob.strip()
    for end in range(len(blob), 0, -1):
        if blob[end - 1] != "}":
            continue
        try:
            parsed = json.loads(blob[:end])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


def _import_result_summary(result: dict[str, Any]) -> str:
    imported = int(result.get("imported") or 0)
    skipped = int(result.get("skipped") or 0)
    parts = [f"导入 {imported} 条"]
    if skipped:
        parts.append(f"跳过 {skipped} 条")
    return " · ".join(parts)


def tool_result_summary(name: str, result: Any) -> str:
    if not isinstance(result, dict):
        return ""
    if result.get("error"):
        return str(result["error"])
    if name in ("discover_leads", "enrich_contact"):
        parts = [f"共 {result.get('lead_count', 0)} 条线索"]
        if result.get("contact_id"):
            parts.insert(0, f"联系人 #{result['contact_id']}")
        if result.get("import"):
            parts.append(_import_result_summary(result["import"]))
        elif result.get("message"):
            parts.append(str(result["message"]))
        return " · ".join(parts)
    if name == "lookup_asns":
        asns = result.get("asns") or []
        return f"识别 {len(asns)} 个 ASN · {result.get('email_count', 0)} 条邮箱"
    if name == "list_contacts":
        contacts = result.get("contacts") or []
        return f"返回 {len(contacts)} 条（总计 {result.get('total', 0)}）"
    if name == "get_contact":
        contact = result.get("contact") or {}
        return f"#{contact.get('id', '')} {contact.get('email') or ''}".strip()
    if name == "update_contact":
        contact = result.get("contact") or {}
        return f"已更新 #{contact.get('id', '')} {contact.get('email') or ''}".strip()
    if name == "mark_contact_sent":
        if result.get("ok"):
            status = "已标记发信" if result.get("sent") else "已取消发信标记"
            return f"联系人 #{result.get('contact_id', '')} {status}"
        return ""
    if name == "delete_contacts":
        return f"已删除 {result.get('deleted', 0)} / {result.get('requested', 0)} 条"
    if name == "add_contact_note":
        return "已添加备注" if result.get("ok") else ""
    if name == "list_contact_notes":
        return f"联系人 #{result.get('contact_id', '')} · {result.get('count', 0)} 条备注"
    if name == "get_lead_preferences":
        summary = result.get("summary") or ""
        if summary:
            return summary.split("\n", 1)[0][:200]
        stats = (result.get("preferences") or {}).get("stats") or {}
        return f"偏好已加载 · 导入 {stats.get('imports', 0)} · 无效 {stats.get('invalid', 0)}"
    if name == "reset_lead_preferences":
        return "已重置线索偏好" if result.get("ok") else ""
    if name == "dedupe_contacts":
        return (
            f"去重完成：删除 {result.get('removed', 0)} 条，"
            f"剩余 {result.get('total_contacts', result.get('total', 0))} 条"
        )
    if name == "import_leads":
        return _import_result_summary(result)
    if name == "get_stats":
        return f"联系人 {result.get('total', 0)} · 已发 {result.get('sent', 0)}"
    try:
        return json.dumps(result, ensure_ascii=False)[:8000]
    except (TypeError, ValueError):
        return str(result)[:8000]


_active_pi_streams: set[tuple[int, str]] = set()


def try_acquire_pi_thread(user_id: int, thread_id: str | None) -> bool:
    if not thread_id:
        return True
    key = (user_id, thread_id)
    if key in _active_pi_streams:
        return False
    _active_pi_streams.add(key)
    return True


def release_pi_thread(user_id: int, thread_id: str | None) -> None:
    if thread_id:
        _active_pi_streams.discard((user_id, thread_id))


def is_pi_thread_streaming(user_id: int, thread_id: str) -> bool:
    return (user_id, thread_id) in _active_pi_streams


def history_entry_from_agent_event(event: dict[str, Any]) -> dict[str, Any] | None:
    event_type = event.get("type")
    if event_type == "tool_result":
        name = str(event.get("name") or "tool")
        result = event.get("result") or {}
        summary = tool_result_summary(name, result)
        entry: dict[str, Any] = {
            "role": "tool",
            "name": name,
            "summary": summary[:8000],
        }
        if name == "lookup_asns":
            rows = result.get("rows") or result.get("preview") or []
            if isinstance(rows, list):
                entry["preview"] = rows[:25]
        if not entry["summary"] and isinstance(result, dict):
            try:
                entry["summary"] = json.dumps(result, ensure_ascii=False)[:8000]
            except (TypeError, ValueError):
                entry["summary"] = summary
        return entry
    if event_type == "assistant_done":
        text = str(event.get("text") or "").strip()
        if text:
            return {"role": "assistant", "content": text}
    return None


def append_user_turn_to_messages(
    messages: list[dict[str, Any]],
    history: list[dict[str, Any]],
    message: str,
) -> None:
    user_text = message.strip()
    if not user_text:
        return
    if (
        history
        and history[-1].get("role") == "user"
        and str(history[-1].get("content") or "").strip() == user_text
    ):
        return
    messages.append({"role": "user", "content": user_text})


_TOOL_NAME_ALIASES = {
    "search_contacts": "list_contacts",
    "list_contact": "list_contacts",
    "find_contacts": "list_contacts",
    "delete_contact": "delete_contacts",
    "remove_contacts": "delete_contacts",
    "bulk_delete_contacts": "delete_contacts",
}

_EMPTY_RESPONSE_NUDGE = (
    "（系统）请用中文回复用户，并调用合适的 CRM 工具完成任务，"
    "例如 list_contacts（搜索联系人）、delete_contacts（删除联系人）。"
)

_INTRO_ONLY_NUDGE = (
    "（系统）不要只回复开场白就停止。请立即调用 list_contacts、web_search、"
    "lookup_asns 等工具完成用户请求，然后再总结结果。"
)

_MAX_LLM_NUDGES = 2


def _fallback_prepared_calls(user_message: str) -> list[tuple[dict[str, Any], str, dict[str, Any]]]:
    """When the model keeps intro-only replies, run a sensible default CRM search."""
    text = (user_message or "").strip()
    lower = text.lower()
    if not text:
        return []

    queries: list[str] = []
    if any(token in text for token in ("运营商", "operator", " isp", "isp ", "电信", "联通", "移动")) or (
        "还有" in text and "其他" in text
    ):
        queries = [
            "运营商",
            "ISP",
            "Telecom",
            "Network",
            "Transit",
            "Cogent",
            "Verizon",
            "AT&T",
            "TDS",
            "RCN",
            "GTT",
        ]
    elif "abuse" in lower:
        queries = ["abuse@"]
    elif any(token in text for token in ("联系人", "crm", "搜索", "找出", "列出", "还有")):
        queries = ["", "Network", "ISP"]

    if not queries:
        return []

    raw_calls = [
        {
            "id": f"fallback-{uuid.uuid4().hex[:8]}",
            "type": "function",
            "function": {
                "name": "list_contacts",
                "arguments": json.dumps({"q": query, "limit": 100}, ensure_ascii=False),
            },
        }
        for query in queries[:8]
    ]
    return _prepare_tool_calls(raw_calls)


def _normalize_tool_name(name: str) -> str:
    cleaned = (name or "").strip().lower()
    for prefix in ("functions.", "function.", "tool.", "tools."):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
    if "." in cleaned and cleaned not in KNOWN_TOOL_NAMES:
        tail = cleaned.rsplit(".", 1)[-1]
        if tail in KNOWN_TOOL_NAMES or tail in _TOOL_NAME_ALIASES:
            cleaned = tail
    return cleaned


def _infer_tool_name(name: str, args: dict[str, Any]) -> str:
    cleaned = _normalize_tool_name(name)
    if cleaned in KNOWN_TOOL_NAMES:
        return cleaned
    if cleaned in _TOOL_NAME_ALIASES:
        return _TOOL_NAME_ALIASES[cleaned]
    if "contact_ids" in args or "ids" in args:
        return "delete_contacts"
    if "queries" in args or ("query" in args and "q" not in args and "max_results" in args):
        return "web_search"
    if "text" in args or "asns" in args:
        return "lookup_asns"
    if "contact_id" in args and ("auto_import" in args or "min_score" in args):
        return "enrich_contact"
    if "contact_id" in args and "note" in args:
        return "add_contact_note"
    if "contact_id" in args and "sent" in args:
        return "mark_contact_sent"
    if "contact_id" in args and not args.get("q"):
        return "get_contact"
    if "rows" in args:
        return "import_leads"
    if "keywords" in args or "keyword" in args:
        return "list_contacts"
    if "q" in args or ("limit" in args and "query" not in args and "queries" not in args):
        return "list_contacts"
    return cleaned or "unknown"


def _coerce_list_contacts_args(args: dict[str, Any]) -> dict[str, Any]:
    if "q" in args:
        return args
    for key in ("keywords", "keyword", "search", "query", "term", "filter"):
        if key not in args:
            continue
        val = args[key]
        if isinstance(val, list):
            args["q"] = " ".join(str(item) for item in val if item)
        else:
            args["q"] = str(val)
        break
    return args


def _normalize_raw_tool_entry(item: dict[str, Any]) -> dict[str, Any]:
    fn = item.get("function")
    if isinstance(fn, str):
        try:
            fn = json.loads(fn)
        except json.JSONDecodeError:
            fn = {}
    if isinstance(fn, dict) and fn.get("name"):
        args = fn.get("arguments")
        if isinstance(args, dict):
            args_str = json.dumps(args, ensure_ascii=False)
        else:
            args_str = str(args or "{}")
        return {
            "id": str(item.get("id") or f"inline-{uuid.uuid4().hex[:8]}"),
            "type": "function",
            "function": {"name": str(fn["name"]), "arguments": args_str},
        }
    name = str(item.get("name") or "").strip()
    raw_args = item.get("arguments")
    if isinstance(raw_args, dict):
        args_str = json.dumps(raw_args, ensure_ascii=False)
    elif raw_args is not None:
        args_str = str(raw_args)
    else:
        args_str = "{}"
    return {
        "id": str(item.get("id") or f"inline-{uuid.uuid4().hex[:8]}"),
        "type": "function",
        "function": {"name": name, "arguments": args_str},
    }


def _extract_tool_calls_from_content(text: str) -> list[dict[str, Any]]:
    text = (text or "").strip()
    if not text:
        return []

    start = text.find("[")
    if start >= 0:
        blob = text[start:]
        for end in range(len(blob), 0, -1):
            if blob[end - 1] not in "}]":
                continue
            try:
                parsed = json.loads(blob[:end])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, list):
                calls = [item for item in parsed if isinstance(item, dict)]
                if calls:
                    return [_normalize_raw_tool_entry(item) for item in calls]

    args = _extract_json_args(text)
    if args:
        name = _infer_tool_name("", args)
        if name != "unknown":
            return [_normalize_raw_tool_entry({"name": name, "arguments": args})]

    name_match = re.search(r'"name"\s*:\s*"([a-zA-Z0-9_]+)"', text)
    if name_match:
        return [
            _normalize_raw_tool_entry(
                {"name": name_match.group(1), "arguments": _extract_json_args(text)}
            )
        ]
    return []


def _parse_tool_call(tool_call: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """Normalize provider-specific tool_call payloads; skip empty/invalid calls."""
    fn = tool_call.get("function")
    if isinstance(fn, str):
        try:
            fn = json.loads(fn)
        except json.JSONDecodeError:
            fn = {}
    if not isinstance(fn, dict):
        fn = {}

    name = str(fn.get("name") or tool_call.get("name") or "").strip()
    raw_args = fn.get("arguments")
    if raw_args is None:
        raw_args = tool_call.get("arguments") or "{}"
    if isinstance(raw_args, dict):
        args = raw_args
    else:
        try:
            args = json.loads(raw_args) if raw_args else {}
        except json.JSONDecodeError:
            args = {}
    if not isinstance(args, dict):
        args = {}

    if (not name or name == "unknown") and isinstance(raw_args, str) and raw_args.strip():
        name_match = re.search(r'"name"\s*:\s*"([a-zA-Z0-9_]+)"', raw_args)
        if name_match:
            name = name_match.group(1)
        try:
            nested = json.loads(raw_args)
        except json.JSONDecodeError:
            nested = None
        if isinstance(nested, dict):
            if nested.get("name"):
                name = str(nested["name"])
            nested_args = nested.get("arguments")
            if isinstance(nested_args, dict):
                args = nested_args
            elif isinstance(nested_args, str):
                try:
                    parsed_args = json.loads(nested_args)
                    if isinstance(parsed_args, dict):
                        args = parsed_args
                except json.JSONDecodeError:
                    pass
            elif "name" not in nested:
                args = nested

    name = _infer_tool_name(name, args)
    if name == "list_contacts":
        args = _coerce_list_contacts_args(args)
    if name == "unknown":
        return None
    return name, args


def _ensure_tool_call_id(tool_call: dict[str, Any]) -> str:
    tool_id = str(tool_call.get("id") or "").strip()
    if not tool_id:
        tool_id = f"call_{uuid.uuid4().hex[:12]}"
        tool_call["id"] = tool_id
    return tool_id


def _prepare_tool_calls(
    tool_calls: list[Any],
) -> list[tuple[dict[str, Any], str, dict[str, Any]]]:
    """Resolve tool calls and drop invalid entries before OpenAI-style message assembly."""
    prepared: list[tuple[dict[str, Any], str, dict[str, Any]]] = []
    for raw in tool_calls:
        if not isinstance(raw, dict):
            continue
        parsed = _parse_tool_call(raw)
        if not parsed:
            continue
        name, args = parsed
        tool_call = dict(raw)
        _ensure_tool_call_id(tool_call)
        fn = tool_call.get("function")
        if not isinstance(fn, dict):
            fn = {}
        tool_call["function"] = {
            "name": name,
            "arguments": json.dumps(args, ensure_ascii=False),
        }
        tool_call["type"] = tool_call.get("type") or "function"
        prepared.append((tool_call, name, args))
    return prepared


def _assistant_response_empty(assistant: dict[str, Any] | None, content_buffer: str) -> bool:
    if not assistant:
        return True
    content = (assistant.get("content") or content_buffer or "").strip()
    tool_calls = assistant.get("tool_calls") or []
    if content or tool_calls:
        return False
    reasoning = str(assistant.get("reasoning_content") or "").strip()
    return not reasoning


def _parse_inline_tool_calls(content: str) -> tuple[str, list[dict[str, Any]]]:
    text = (content or "").strip()
    if not text or not _content_looks_like_tool_call(text):
        return text, []

    intro = _assistant_intro_before_tools(text)
    name = "unknown"
    name_match = re.search(r"\[(?:工具|tool)[:\s]*([a-zA-Z0-9_]+)\]", text, re.I)
    if name_match:
        name = name_match.group(1)
    args = _extract_json_args(text)
    name = _infer_tool_name(name, args)
    if name == "unknown" and not args:
        return text, []

    tool_call = {
        "id": f"inline-{uuid.uuid4().hex[:8]}",
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(args, ensure_ascii=False),
        },
    }
    return intro, [tool_call]


async def _discover_leads_tool(
    user_id: int,
    args: dict[str, Any],
    emit: ToolEmitter,
) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    min_score = int(args.get("min_score") or 60)
    auto_import = args.get("auto_import")
    if auto_import is None:
        auto_import = True
    else:
        auto_import = bool(auto_import)

    leads, import_result, message, error = await _stream_lead_events(
        discover_leads_stream(
            query,
            min_score=min_score,
            auto_import=auto_import,
            user_id=user_id,
        ),
        emit,
    )
    return _leads_tool_result(leads, message=message, import_result=import_result, error=error)


async def _enrich_contact_tool(
    user_id: int,
    args: dict[str, Any],
    emit: ToolEmitter,
) -> dict[str, Any]:
    contact_id = int(args.get("contact_id") or 0)
    if contact_id <= 0:
        return {"error": "contact_id 无效"}
    min_score = int(args.get("min_score") or 60)
    auto_import = args.get("auto_import")
    if auto_import is None:
        auto_import = True
    else:
        auto_import = bool(auto_import)

    leads, import_result, message, error = await _stream_lead_events(
        enrich_contact_stream(
            user_id,
            contact_id,
            min_score=min_score,
            auto_import=auto_import,
        ),
        emit,
    )
    return _leads_tool_result(
        leads,
        message=message,
        import_result=import_result,
        error=error,
        extra={"contact_id": contact_id},
    )


async def _lookup_asns_tool(args: dict[str, Any], emit: ToolEmitter) -> dict[str, Any]:
    text = str(args.get("text") or "")
    asns = parse_asns_from_text(text)[:50]
    if not asns:
        return {"error": "未识别到有效 ASN", "asns": []}
    emit.progress(f"已识别 {len(asns)} 个 ASN，开始 RDAP 查询…")
    rows: list[dict[str, Any]] = []
    for index, asn in enumerate(asns, start=1):
        batch = await asyncio.to_thread(lookup_asn, asn)
        rows.extend(row.to_dict() for row in batch)
        rir = next((row.rir for row in batch if row.rir), "")
        emails = sum(1 for row in batch if row.email and not row.error)
        emit.progress(f"AS{asn} · {rir or 'RDAP'} · {emails} 条邮箱（{index}/{len(asns)}）")
    emails = [r for r in rows if r.get("email") and not r.get("error")]
    return {
        "asns": asns,
        "row_count": len(rows),
        "email_count": len(emails),
        "rows": emails,
        "preview": emails[:20],
    }


def _merge_pattern_lines(existing: str, additions: list[str]) -> str:
    patterns = parse_patterns(existing)
    seen = set(patterns)
    for item in additions:
        line = str(item or "").strip().lower()
        if not line or line.startswith("#"):
            continue
        if line not in seen:
            patterns.append(line)
            seen.add(line)
    return "\n".join(patterns)


def _import_filters_payload() -> dict[str, Any]:
    blocklist = get_setting("import_blocklist", "")
    allowlist = get_setting("import_allowlist", "")
    return {
        "blocklist": blocklist,
        "allowlist": allowlist,
        "blocklist_patterns": parse_patterns(blocklist),
        "allowlist_patterns": parse_patterns(allowlist),
    }


async def _run_tool(
    user_id: int,
    name: str,
    args: dict[str, Any],
    emit: ToolEmitter,
) -> Any:
    if name == "list_contacts":
        q = args.get("q")
        limit = max(1, min(int(args.get("limit") or 20), 100))
        contacts = list_contacts(user_id, q=q, limit=limit)
        return {"contacts": contacts, "total": count_contacts(user_id, q=q), "limit": limit}

    if name == "get_contact":
        contact_id = int(args.get("contact_id") or 0)
        if contact_id <= 0:
            return {"error": "contact_id 无效"}
        contact = get_contact(user_id, contact_id)
        if not contact:
            return {"error": "联系人不存在"}
        return {"contact": contact}

    if name == "import_leads":
        rows = args.get("rows") or []
        source = str(args.get("source") or "pi-agent")
        payload = [normalize_import_row({**row, "source": row.get("source") or source}) for row in rows if isinstance(row, dict)]
        result = import_contacts(user_id, payload)
        result["total_contacts"] = count_contacts(user_id)
        return result

    if name == "discover_leads":
        return await _discover_leads_tool(user_id, args, emit)

    if name == "enrich_contact":
        return await _enrich_contact_tool(user_id, args, emit)

    if name == "lookup_asns":
        return await _lookup_asns_tool(args, emit)

    if name == "get_stats":
        return get_contact_stats(user_id)

    if name == "update_contact":
        contact_id = int(args.get("contact_id") or 0)
        if contact_id <= 0:
            return {"error": "contact_id 无效"}
        contact = update_contact(
            user_id,
            contact_id,
            org=args.get("org"),
            name=args.get("name"),
            notes=args.get("notes"),
            roles=args.get("roles"),
        )
        if not contact:
            return {"error": "联系人不存在"}
        status = args.get("follow_up_status")
        if status:
            if not update_contact_follow_up_status(user_id, contact_id, str(status).strip().lower()):
                return {"error": "跟进状态更新失败", "contact": contact}
            contact["follow_up_status"] = str(status).strip().lower()
        return {"ok": True, "contact": contact}

    if name == "mark_contact_sent":
        contact_id = int(args.get("contact_id") or 0)
        sent = bool(args.get("sent", True))
        if contact_id <= 0:
            return {"error": "contact_id 无效"}
        if not mark_contact_sent(user_id, contact_id, sent=sent):
            return {"error": "联系人不存在"}
        return {"ok": True, "contact_id": contact_id, "sent": sent}

    if name == "delete_contacts":
        ids = [int(item) for item in (args.get("contact_ids") or []) if int(item) > 0]
        if not ids:
            return {"error": "contact_ids 为空"}
        if len(ids) == 1:
            ok = delete_contact(user_id, ids[0])
            return {"deleted": 1 if ok else 0, "requested": 1}
        return bulk_delete_contacts(user_id, ids)

    if name == "add_contact_note":
        contact_id = int(args.get("contact_id") or 0)
        body = str(args.get("body") or "").strip()
        if contact_id <= 0 or not body:
            return {"error": "contact_id 或备注内容无效"}
        note = create_contact_note(user_id, contact_id, body)
        if not note:
            return {"error": "联系人不存在或备注为空"}
        return {"ok": True, "note": note}

    if name == "list_contact_notes":
        contact_id = int(args.get("contact_id") or 0)
        if contact_id <= 0:
            return {"error": "contact_id 无效"}
        limit = max(1, min(int(args.get("limit") or 20), 100))
        notes = list_contact_notes(user_id, contact_id)
        if notes is None:
            return {"error": "联系人不存在"}
        return {
            "contact_id": contact_id,
            "notes": notes[:limit],
            "count": len(notes),
            "limit": limit,
        }

    if name == "get_lead_preferences":
        prefs = get_prefs(user_id)
        summary = preference_hints_for_llm(prefs)
        return {
            "preferences": prefs,
            "summary": summary,
            "min_score_hint": prefs.get("min_score_hint"),
        }

    if name == "reset_lead_preferences":
        prefs = reset_prefs(user_id)
        return {"ok": True, "preferences": prefs, "message": "线索偏好已重置为默认"}

    if name == "dedupe_contacts":
        result = dedupe_contacts(user_id=user_id)
        result["total_contacts"] = count_contacts(user_id)
        return result

    if name == "get_import_filters":
        return _import_filters_payload()

    if name == "update_import_filters":
        updates: dict[str, str | None] = {}
        if "blocklist" in args:
            updates["import_blocklist"] = str(args.get("blocklist") or "")
        elif args.get("append_blocklist"):
            current = get_setting("import_blocklist", "")
            updates["import_blocklist"] = _merge_pattern_lines(
                current,
                list(args.get("append_blocklist") or []),
            )
        if "allowlist" in args:
            updates["import_allowlist"] = str(args.get("allowlist") or "")
        elif args.get("append_allowlist"):
            current = get_setting("import_allowlist", "")
            updates["import_allowlist"] = _merge_pattern_lines(
                current,
                list(args.get("append_allowlist") or []),
            )
        if not updates:
            return {"error": "请提供 blocklist/allowlist 或 append_blocklist/append_allowlist"}
        update_settings(updates)
        payload = _import_filters_payload()
        payload["ok"] = True
        payload["message"] = "导入过滤规则已更新"
        return payload

    if name == "list_schedules":
        schedules = list_scheduled_jobs(user_id)
        return {"schedules": schedules, "count": len(schedules)}

    if name == "create_schedule":
        job_name = str(args.get("name") or "").strip()
        query = str(args.get("query") or "").strip()
        if not job_name or not query:
            return {"error": "请提供 name 和 query"}
        job = create_scheduled_job(
            user_id,
            name=job_name,
            query=query,
            run_mode=str(args.get("run_mode") or "continuous"),
            interval_minutes=int(args.get("interval_minutes") or 360),
            cooldown_minutes=int(args.get("cooldown_minutes") or 15),
            min_score=int(args.get("min_score") or 60),
            auto_import=bool(args.get("auto_import", True)),
            enabled=True,
        )
        return {"ok": True, "schedule": job}

    if name == "update_schedule":
        schedule_id = int(args.get("schedule_id") or 0)
        if schedule_id <= 0:
            return {"error": "请提供 schedule_id"}
        fields = {
            key: args.get(key)
            for key in (
                "name",
                "query",
                "enabled",
                "run_mode",
                "interval_minutes",
                "cooldown_minutes",
                "min_score",
                "auto_import",
            )
            if key in args
        }
        job = update_scheduled_job(user_id, schedule_id, **fields)
        if not job:
            return {"error": "定时任务不存在"}
        return {"ok": True, "schedule": job}

    if name == "get_search_config":
        return get_channel_config()

    if name == "shodan_search":
        query = str(args.get("query") or "").strip()
        if not query:
            return {"error": "请提供 query（Shodan 搜索语法）"}
        if not shodan_source.is_configured():
            return {
                "error": "Shodan 未配置",
                "hint": "在系统设置填写 Shodan API Key 并启用渠道",
                "config": shodan_source.get_config(),
            }
        page = max(1, int(args.get("page") or 1))
        emit.progress(f"Shodan 搜索：{query}")
        try:
            payload = await asyncio.to_thread(shodan_source.host_search, query, page=page)
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc), "config": shodan_source.get_config()}
        matches = payload.get("matches") or []
        networks: list[dict[str, Any]] = []
        web_results: list[dict[str, str]] = []
        seen_asn: set[int] = set()
        for match in matches:
            if not isinstance(match, dict):
                continue
            web_results.append(shodan_source.match_to_web_result(match, query=query))
            network = shodan_source.match_to_network(match, keyword=query)
            if network and network["asn"] not in seen_asn:
                seen_asn.add(network["asn"])
                networks.append(network)
        return {
            "query": query,
            "total": payload.get("total", len(matches)),
            "match_count": len(matches),
            "networks": networks[:20],
            "web_results": web_results[:20],
            "config": shodan_source.get_config(),
            "note": "带 filter 的查询会消耗 Shodan query credits",
        }

    if name in SOCIAL_PROFILE_TOOLS:
        spec = SOCIAL_PROFILE_TOOLS[name]
        urls = [str(item).strip() for item in (args.get("urls") or []) if str(item).strip()]
        max_urls = max(1, min(int(args.get("max_urls") or bs.DEFAULT_MAX_URLS), bs.DEFAULT_MAX_URLS))
        if not urls:
            return {"error": f"请提供 urls（{spec.label} profile URL 列表）"}
        if not bs.is_channel_configured(spec):
            return {
                "error": f"Bright Data {spec.label} 未配置",
                "hint": f"在系统设置填写 Bright Data API Key 并启用 {spec.label} 渠道",
                "config": bs.channel_config(spec),
            }
        emit.progress(f"{spec.label} 抓取 {min(len(urls), max_urls)} 个 profile…")
        try:
            profiles = await asyncio.to_thread(
                bs.collect_profiles_by_url,
                spec,
                urls,
                max_urls=max_urls,
            )
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc), "config": bs.channel_config(spec)}
        previews = bs.profiles_to_lead_previews(spec, profiles)
        return {
            "profile_count": len(profiles),
            "profiles": profiles[:15],
            "lead_previews": previews[:15],
            "config": bs.channel_config(spec),
            "note": f"{spec.label} 通常无邮箱；请结合 discover_leads / lookup_asns 找可导入邮箱",
        }

    if name == "search_hosting_forums":
        keyword = str(args.get("keyword") or "").strip()
        forums = [str(item).strip() for item in (args.get("forums") or []) if str(item).strip()]
        max_results = max(1, min(int(args.get("max_results") or 12), 24))
        if not keyword:
            return {"error": "请提供 keyword"}
        emit.progress(f"论坛搜索：{keyword}")
        try:
            payload = await asyncio.to_thread(
                forums_source.search_forums,
                keyword,
                forums=forums or None,
                max_results=max_results,
            )
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}
        if payload.get("error"):
            return payload
        return payload

    if name == "fetch_web_pages":
        urls = [str(item).strip() for item in (args.get("urls") or []) if str(item).strip()]
        max_urls = max(
            1,
            min(int(args.get("max_urls") or web_unlocker_source.max_urls_limit()), 12),
        )
        if not urls:
            return {"error": "请提供 urls（https 页面 URL 列表）"}
        if not web_unlocker_source.is_configured():
            return {
                "error": "Bright Data Web Unlocker 未配置",
                "hint": "在系统设置填写 Bright Data API Key、Web Unlocker Zone 并启用渠道",
                "config": web_unlocker_source.get_config(),
            }
        emit.progress(f"Web Unlocker 抓取 {min(len(urls), max_urls)} 个页面…")
        try:
            rows = await asyncio.to_thread(
                web_unlocker_source.fetch_pages,
                urls,
                max_urls=max_urls,
            )
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc), "config": web_unlocker_source.get_config()}
        signals = web_search.extract_signals_from_results(
            [row for row in rows if not row.get("error")]
        )
        return {
            "page_count": len(rows),
            "pages": [
                {
                    "url": row.get("url"),
                    "snippet": (row.get("snippet") or "")[:400],
                    "error": row.get("error"),
                }
                for row in rows[:15]
            ],
            "emails_found": signals.get("emails") or [],
            "asns_found": signals.get("asns") or [],
            "config": web_unlocker_source.get_config(),
        }

    if name == "web_search":
        query = str(args.get("query") or "").strip()
        queries = [str(item).strip() for item in (args.get("queries") or []) if str(item).strip()]
        if query:
            queries = [query, *queries]
        if not queries:
            return {"error": "请提供 query 或 queries"}
        truncated = 0
        if len(queries) > MAX_WEB_SEARCH_QUERIES:
            truncated = len(queries) - MAX_WEB_SEARCH_QUERIES
            queries = queries[:MAX_WEB_SEARCH_QUERIES]
        max_results = max(1, min(int(args.get("max_results") or 8), 20))
        progress = f"联网搜索 {len(queries)} 条：{', '.join(queries[:2])}{'…' if len(queries) > 2 else ''}"
        if truncated:
            progress += f"（已截断 {truncated} 条，请分批搜索）"
        emit.progress(progress)
        try:
            results = await asyncio.to_thread(
                web_search.search_web_many,
                queries,
                max_results_per_query=max_results,
            )
        except Exception as exc:  # noqa: BLE001 — return tool error to LLM
            return {"error": str(exc), "query_count": len(queries)}
        backend = results[0].get("backend") if results else web_search.get_search_config()["active_web_backend"]
        signals = web_search.extract_signals_from_results(results)
        preview = [
            {
                "title": item.get("title"),
                "url": item.get("url"),
                "snippet": (item.get("snippet") or "")[:240],
                "backend": item.get("backend"),
                "query": item.get("query"),
            }
            for item in results[:15]
        ]
        return {
            "backend_used": backend,
            "config": web_search.get_search_config(),
            "query_count": len(queries),
            "result_count": len(results),
            "results": preview,
            "emails_found": signals.get("emails") or [],
            "asns_found": signals.get("asns") or [],
        }

    return {"error": f"未知工具: {name}"}


async def _iter_llm_stream(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    *,
    tool_choice: str | dict[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def worker() -> None:
        try:
            for event in chat_completion_with_tools_stream(
                messages,
                tools,
                tool_choice=tool_choice,
            ):
                loop.call_soon_threadsafe(queue.put_nowait, event)
        except LLMError as exc:
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "error", "message": str(exc)})
        except Exception as exc:  # noqa: BLE001 — surface unexpected LLM stream failures
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "error", "message": str(exc)})
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    threading.Thread(target=worker, daemon=True).start()
    while True:
        item = await queue.get()
        if item is None:
            break
        yield item


async def _stream_text_reply(
    messages: list[dict[str, Any]],
) -> tuple[str, bool]:
    """One text-only LLM turn (no tools). Returns (text, ok)."""
    assistant: dict[str, Any] | None = None
    content_buffer = ""
    async for event in _iter_llm_stream(messages, None):
        event_type = event.get("type")
        if event_type == "error":
            return "", False
        if event_type == "content_delta":
            piece = str(event.get("text") or "")
            if piece:
                content_buffer += piece
        elif event_type == "message":
            assistant = event.get("message")
    content = (assistant.get("content") if assistant else content_buffer or "").strip()
    return content, bool(content)


async def agent_chat_stream(
    user_id: int,
    message: str,
    history: list[dict[str, str]] | None = None,
    *,
    thread_id: str | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    if cancel_check and cancel_check():
        yield {"type": "error", "message": "任务已停止"}
        yield {"type": "done"}
        return
    yield {"type": "status", "message": "Pi 助手思考中…"}

    thread: dict[str, Any] | None = None
    if thread_id:
        loaded = get_pi_thread(user_id, thread_id)
        if loaded:
            history = loaded.get("history") or []
            had_summary = bool((loaded.get("context_summary") or "").strip())
            summary_through = int(loaded.get("context_summary_through") or 0)
            if needs_summary_update(len(history), summary_through):
                yield {"type": "status", "message": "整理对话上下文…"}
            thread = await asyncio.to_thread(
                compress_thread_context_until_current,
                user_id,
                thread_id,
            )
            thread = thread or get_pi_thread(user_id, thread_id)
            if thread and not had_summary and (thread.get("context_summary") or "").strip():
                yield {"type": "status", "message": "长对话已滚动压缩，继续处理…"}
    context_summary = str((thread or {}).get("context_summary") or "")
    summary_through = int((thread or {}).get("context_summary_through") or 0)
    history = _trim_history(
        history or [],
        context_summary=context_summary,
        summary_through=summary_through,
    )
    stats_history = (thread or {}).get("history") if thread else (history or [])
    yield {
        "type": "context",
        "stats": context_stats(
            stats_history,
            context_summary=context_summary,
            summary_through=summary_through,
            system_chars=len(SYSTEM_PROMPT),
            tools_chars=len(json.dumps(AGENT_TOOLS, ensure_ascii=False)),
            model=get_setting("llm_model", ""),
        ),
    }
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    append_user_turn_to_messages(messages, history or [], message)

    for round_index in range(MAX_TOOL_ROUNDS):
        if cancel_check and cancel_check():
            yield {"type": "error", "message": "任务已停止"}
            yield {"type": "done"}
            return
        if round_index > 0:
            yield {"type": "status", "message": "正在整理工具结果…"}

        assistant: dict[str, Any] | None = None
        content_buffer = ""
        streamed_reply = False
        nudged_empty_response = False
        llm_nudge_count = 0
        tool_calls: list[Any] = []
        content = ""
        prepared_calls: list[tuple[dict[str, Any], str, dict[str, Any]]] = []

        while True:
            if cancel_check and cancel_check():
                yield {"type": "error", "message": "任务已停止"}
                yield {"type": "done"}
                return
            assistant = None
            content_buffer = ""
            streamed_reply = False
            last_streamed_visible = ""

            tool_choice: str | dict[str, Any] | None = (
                "required" if llm_nudge_count > 0 and AGENT_TOOLS else None
            )

            async for event in _iter_llm_stream(messages, AGENT_TOOLS, tool_choice=tool_choice):
                event_type = event.get("type")
                if event_type == "error":
                    yield {"type": "error", "message": event.get("message") or "LLM 请求失败"}
                    yield {"type": "done"}
                    return
                if event_type == "content_delta":
                    piece = str(event.get("text") or "")
                    if piece:
                        content_buffer += piece
                        visible = _meaningful_assistant_content(content_buffer)
                        if visible and len(visible) > len(last_streamed_visible):
                            delta = visible[len(last_streamed_visible) :]
                            last_streamed_visible = visible
                            if delta:
                                if not streamed_reply:
                                    streamed_reply = True
                                    yield {"type": "assistant_start"}
                                yield {"type": "assistant_delta", "text": delta}
                elif event_type == "status":
                    yield {"type": "status", "message": event.get("message") or "Pi 助手处理中…"}
                elif event_type == "message":
                    assistant = event.get("message")

            if _assistant_response_empty(assistant, content_buffer):
                if not nudged_empty_response:
                    nudged_empty_response = True
                    messages.append({"role": "user", "content": _EMPTY_RESPONSE_NUDGE})
                    yield {"type": "status", "message": "模型未响应，正在重试…"}
                    continue
                yield {"type": "error", "message": "模型未返回有效回复，请换种说法或检查 LLM 配置"}
                yield {"type": "done"}
                return

            tool_calls = (assistant or {}).get("tool_calls") or []
            raw_content = ((assistant or {}).get("content") or content_buffer or "").strip()
            content = _meaningful_assistant_content(raw_content)

            if not tool_calls and raw_content:
                intro, inline_calls = _parse_inline_tool_calls(raw_content)
                if inline_calls:
                    tool_calls = inline_calls
                    content = _meaningful_assistant_content(intro)
                    assistant = {**(assistant or {}), "tool_calls": tool_calls, "content": intro or None}

            if content and not tool_calls:
                if _assistant_promises_tool_use(content) and llm_nudge_count < _MAX_LLM_NUDGES:
                    llm_nudge_count += 1
                    messages.append({"role": "user", "content": _INTRO_ONLY_NUDGE})
                    yield {"type": "status", "message": "模型未调用工具，正在重试…"}
                    continue
                fallback_calls = _fallback_prepared_calls(message)
                if fallback_calls and _assistant_promises_tool_use(content):
                    prepared_calls = fallback_calls
                    assistant = {**(assistant or {}), "role": "assistant", "content": content or None}
                    yield {"type": "status", "message": "模型未调用工具，正在直接搜索 CRM…"}
                    break
                if not streamed_reply:
                    yield {"type": "assistant_start"}
                    yield {"type": "assistant_delta", "text": content}
                yield {"type": "assistant_done", "text": content}
                yield {"type": "done"}
                return

            if not tool_calls:
                if llm_nudge_count < _MAX_LLM_NUDGES:
                    llm_nudge_count += 1
                    messages.append({"role": "user", "content": _EMPTY_RESPONSE_NUDGE})
                    yield {"type": "status", "message": "模型未调用工具，正在重试…"}
                    continue
                yield {"type": "error", "message": "模型未返回有效回复，请换种说法或检查 LLM 配置"}
                yield {"type": "done"}
                return

            prepared_calls = _prepare_tool_calls(tool_calls)
            if not prepared_calls and raw_content:
                extracted = _extract_tool_calls_from_content(raw_content)
                if extracted:
                    prepared_calls = _prepare_tool_calls(extracted)
                if not prepared_calls:
                    intro, inline_calls = _parse_inline_tool_calls(raw_content)
                    if inline_calls:
                        prepared_calls = _prepare_tool_calls(inline_calls)
                        content = _meaningful_assistant_content(intro)
            if not prepared_calls:
                attempted_tools = bool(tool_calls)
                if content and not attempted_tools:
                    if not streamed_reply:
                        yield {"type": "assistant_start"}
                        yield {"type": "assistant_delta", "text": content}
                    yield {"type": "assistant_done", "text": content}
                    yield {"type": "done"}
                    return
                if llm_nudge_count < _MAX_LLM_NUDGES:
                    llm_nudge_count += 1
                    messages.append({"role": "user", "content": _EMPTY_RESPONSE_NUDGE})
                    yield {
                        "type": "status",
                        "message": "工具调用无效，正在重试…" if attempted_tools else "模型未调用工具，正在重试…",
                    }
                    continue
                fallback_calls = _fallback_prepared_calls(message)
                if fallback_calls and (attempted_tools or _assistant_promises_tool_use(content)):
                    prepared_calls = fallback_calls
                    assistant = {**(assistant or {}), "role": "assistant", "content": content or None}
                    yield {"type": "status", "message": "工具调用无效，正在直接搜索 CRM…"}
                    break
                yield {"type": "error", "message": "模型未返回有效回复，请换种说法或检查 LLM 配置"}
                yield {"type": "done"}
                return
            break

        if not assistant:
            yield {"type": "error", "message": "模型未返回有效回复，请换种说法或检查 LLM 配置"}
            yield {"type": "done"}
            return

        intro = _meaningful_assistant_content(content or _assistant_intro_before_tools(content_buffer))
        if intro:
            if not streamed_reply:
                yield {"type": "assistant_start"}
            yield {"type": "assistant_done", "text": intro}
        elif streamed_reply:
            visible = _meaningful_assistant_content(content_buffer.strip())
            if visible:
                yield {"type": "assistant_done", "text": visible}

        executed_calls = [tool_call for tool_call, _, _ in prepared_calls]
        messages.append(
            format_assistant_message_for_api(
                assistant,
                content=intro or None,
                tool_calls=executed_calls,
            )
        )

        for tool_call, name, args in prepared_calls:
            yield {"type": "tool_start", "name": name, "args": args}

            event_queue: asyncio.Queue[tuple[str, Any] | None] = asyncio.Queue()
            emitter = ToolEmitter(event_queue)
            result_holder: dict[str, Any] = {}

            async def worker() -> None:
                try:
                    result_holder["value"] = await _run_tool(user_id, name, args, emitter)
                except Exception as exc:  # noqa: BLE001 — keep SSE stream alive
                    result_holder["value"] = {"error": str(exc)}
                finally:
                    await event_queue.put(None)

            task = asyncio.create_task(worker())
            while True:
                try:
                    item = await asyncio.wait_for(event_queue.get(), timeout=TOOL_HEARTBEAT_SECONDS)
                except asyncio.TimeoutError:
                    yield {"type": "status", "message": f"仍在执行 {name}…"}
                    continue
                if item is None:
                    break
                kind, payload = item
                if kind == "progress":
                    yield {"type": "tool_progress", "name": name, "message": payload}
                elif kind == "event":
                    yield {"type": "tool_event", "name": name, "event": payload}
            await task

            result = result_holder.get("value", {"error": "工具执行失败"})
            yield {"type": "tool_result", "name": name, "result": result}
            tool_content = compress_tool_result_for_llm(name, result)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": tool_content,
                }
            )

        if round_index == MAX_TOOL_ROUNDS - 1:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "（系统）本轮工具调用已达上限。请根据已有工具结果直接给出总结与下一步建议，"
                        "不要再调用任何工具。"
                    ),
                }
            )
            final_text, ok = await _stream_text_reply(messages)
            if not ok:
                final_text = "已达到最大工具调用轮次，请简化问题后重试。"
            yield {"type": "assistant_start"}
            yield {"type": "assistant_delta", "text": final_text}
            yield {"type": "assistant_done", "text": final_text}
            yield {"type": "done"}
            return

    yield {"type": "error", "message": "对话未完成，请重试"}
    yield {"type": "done"}
