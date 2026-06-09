from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from typing import Any

from app.contact_enrichment import enrich_contact_stream
from app.database import (
    bulk_delete_contacts,
    count_contacts,
    create_contact_note,
    create_scheduled_job,
    dedupe_contacts,
    delete_contact,
    get_contact,
    get_contact_stats,
    get_email_template,
    get_workbench_summary,
    import_contacts,
    import_lead_reviews,
    list_contact_notes,
    list_contacts,
    list_email_templates,
    list_lead_reviews,
    list_scheduled_jobs,
    mark_contact_sent,
    normalize_import_row,
    update_contact,
    update_contact_follow_up_status,
    update_scheduled_job,
)
from app.email_queue import queue_emails_for_contacts
from app.email_render import render_email
from app.import_filters import parse_patterns
from app.lead_discovery import discover_leads_stream
from app.lead_preferences import get_prefs, preference_hints_for_llm, reset_prefs
from app.llm import (
    LLMError,
    format_assistant_message_for_api,
)
from app.pi_chat_store import (
    MAX_LLM_HISTORY_MESSAGES,
    compress_thread_context_until_current,
    get_pi_thread,
    history_for_llm,
)
from app.pi_context import (
    compress_tool_result_for_llm,
    context_stats,
    is_context_overflow_error,
    should_compress_thread,
)
from app.pi_decisions import (
    Fail,
    FallbackToolCalls,
    FinalReply,
    Retry,
    decide_turn,
)
from app.pi_llm_client import stream_chat
from app.pi_parallel_tools import can_parallelize_tool_batch
from app.pi_reply_heuristics import (
    _MAX_LLM_NUDGES,
    _assistant_intro_before_tools,
    _meaningful_assistant_content,
)
from app.settings_store import get_setting, update_settings
from app.sources import brightdata_social as bs
from app.sources import forums as forums_source
from app.sources import shodan as shodan_source
from app.sources import web_search
from app.sources import web_unlocker as web_unlocker_source
from app.sources.channel_registry import get_channel_config
from app.sources.social_registry import FACEBOOK, LINKEDIN, X
from arin_lookup import lookup_asn, parse_asns_from_text

SOCIAL_PROFILE_TOOLS: dict[str, bs.SocialChannelSpec] = {
    "collect_linkedin_profiles": LINKEDIN,
    "collect_x_profiles": X,
    "collect_facebook_profiles": FACEBOOK,
}

MAX_TOOL_ROUNDS = 12
MAX_HISTORY = MAX_LLM_HISTORY_MESSAGES
MAX_WEB_SEARCH_QUERIES = 4
TOOL_HEARTBEAT_SECONDS = 12
MAX_LLM_CALLS_PER_TURN = 30
MAX_EXECUTED_TOOL_CALLS_PER_TURN = 8

_FORCE_SUMMARY_CONFIG_TOOLS = frozenset(
    {
        "get_import_filters",
        "update_import_filters",
        "get_search_config",
        "list_schedules",
        "create_schedule",
        "update_schedule",
    }
)


def _should_force_summary_after_tool(
    name: str,
    *,
    user_message: str,
    executed_count: int,
) -> bool:
    if name == "discover_leads":
        return True
    if name == "lookup_asns" and _is_asn_role_lookup_turn(user_message):
        return True
    if name in _FORCE_SUMMARY_CONFIG_TOOLS:
        return True
    return executed_count >= MAX_EXECUTED_TOOL_CALLS_PER_TURN


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
                        "description": (
                            "线索行数组。每行必须含 email；尽量含 org 和 name；"
                            "asn 为纯数字（如 395092，不要带 AS 前缀）。"
                            '例：[{"email":"noc@example.net","org":"Example Net","asn":"395092"}]'
                        ),
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
                    "auto_import": {
                        "type": "boolean",
                        "description": "≥60 分线索自动导入，默认 true",
                    },
                },
                "required": ["contact_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "discover_leads",
            "description": "首选线索工具：PeeringDB 直连 + 全球 RDAP + 联网搜索 + LLM 评分/入库。找 peering 联系人、批量挖潜在线索请用这个，不要手动串联 web_search。若用户已给明确 ASN 列表且只要 RDAP/role 邮箱，必须改用 lookup_asns",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "自然语言搜索描述，如「美国中型 ISP 的 peering/NOC 联系人」或「AS13335 的 abuse 邮箱」",
                    },
                    "min_score": {"type": "integer", "description": "最低相关度，默认 60"},
                    "auto_import": {
                        "type": "boolean",
                        "description": "≥60 分线索自动导入，默认 true",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_asns",
            "description": "批量 RDAP 查询已知 ASN 的 role 邮箱（ARIN/RIPE/APNIC 等），支持混排文本自动去重；查完直接总结，不要再扩展 discover_leads 或 web_search",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "含 ASN 的文本，自动提取并去重，如「AS15169, 13335 AS3356」",
                    }
                },
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
                        "enum": ["new", "contacted", "replied", "invalid", "interested"],
                        "description": "跟进状态，只能取这五个值之一",
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
                    "keyword": {
                        "type": "string",
                        "description": "搜索关键词，如公司名、ASN、VPS provider",
                    },
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
                    "query": {
                        "type": "string",
                        "description": "与 discover_leads 相同的自然语言搜索描述",
                    },
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
    {
        "type": "function",
        "function": {
            "name": "get_workbench",
            "description": "获取今日工作台摘要：待审线索数、今日新增、待发信新联系人、超期未跟进列表。回答「今天做什么/该跟进谁」时首选",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_email_templates",
            "description": "列出已保存的邮件模板（id、名称、主题），发邮件前先用它确认模板",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "preview_email",
            "description": "用指定模板对单个联系人渲染邮件（主题+正文），给用户预览后再决定是否排队发送",
            "parameters": {
                "type": "object",
                "properties": {
                    "template_id": {"type": "integer", "description": "邮件模板 ID"},
                    "contact_id": {"type": "integer", "description": "联系人 ID"},
                },
                "required": ["template_id", "contact_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "queue_emails",
            "description": "把邮件加入发送队列（按模板渲染、自动跳过重复/已发信）。属于对外发信操作，会先弹出用户确认",
            "parameters": {
                "type": "object",
                "properties": {
                    "contact_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "要发信的联系人 ID 列表",
                    },
                    "template_id": {"type": "integer", "description": "邮件模板 ID"},
                    "skip_sent": {
                        "type": "boolean",
                        "description": "跳过已标记发信的联系人，默认 true",
                    },
                },
                "required": ["contact_ids", "template_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_lead_reviews",
            "description": "查看待人工审核的线索（低分或需复核的发现结果）",
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["pending", "approved", "rejected", "all"],
                        "description": "默认 pending",
                    },
                    "limit": {"type": "integer", "description": "最多返回条数，默认 50"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "import_lead_reviews",
            "description": "把指定的待审线索标记通过并导入 CRM（需用户先看过 list_lead_reviews 结果并同意）",
            "parameters": {
                "type": "object",
                "properties": {
                    "review_ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "要通过并导入的审核条目 ID",
                    }
                },
                "required": ["review_ids"],
            },
        },
    },
]

SYSTEM_PROMPT = """你是 Sales CRM 的 Pi 助手，帮销售/BD 操作网络运营商联系人库。

核心行为（最重要，优先遵守）：
1. 需要查 CRM 或联网时立刻调用工具。禁止只回「让我查一下 / 我先搜一下」等开场白就停——结论与动作先行，说明放到工具结果之后。
2. 能并行的工具调用一次性发出（如一次查多个 ASN、多个搜索词）；拿到足够结果就总结收尾，不要反复重查同一目标。
3. 简洁中文；不编造数据；lead_score ≥ 60 直接入库（import_leads 或 discover_leads 的 auto_import），无需再问用户。
4. 商用护栏：discover_leads 是完整线索流水线（PeeringDB + RDAP + 联网搜索 + 评分 + 入库）。一旦本轮调用 discover_leads，立即根据结果总结，禁止继续调用 web_search、get_search_config、get_lead_preferences、list_contacts、get_stats、get_contact、enrich_contact 做二次补搜或查配置，除非用户明确要求这些工具本身。
5. 若用户已给出明确 ASN 列表且只要 role/RDAP/abuse/NOC 邮箱，本轮只调用 lookup_asns；禁止升级为 discover_leads 或 web_search。

选哪个工具（按场景对号入座）：
- 找 peering 联系人 / 批量找线索 / 挖潜在客户 → discover_leads（auto_import=true, min_score=60）。这是首选，别用 web_search 替代，也别手动串联多次 web_search。
- 已有明确 ASN 列表、只要 RDAP role 邮箱 → 只调用 lookup_asns；不要再调用 discover_leads/web_search，除非用户还要求找更多公司、找线索或导入。
- 给已有 CRM 联系人扩展更多联系方式 → enrich_contact
- 写 outreach / 续跟 / 总结下一步 → 先 get_contact + list_contact_notes 看历史，必要时 add_contact_note 记结论
- 已有社交 profile URL → 对应 collect_linkedin/x/facebook_profiles；批量找线索仍用 discover_leads（会自动从结果提取 URL）
- 抓 peering/contact/NOC 页面正文 → fetch_web_pages；查主机/VPS 论坛 → search_hosting_forums
- web_search 只用于快速查证单个资料，不用于线索挖掘主流程；如果同批或此前已调用 discover_leads，不要再调用 web_search。
- 用户问数据渠道/搜索引擎配置 → 先 get_search_config 再回答；找线索时不要顺手查配置。
- 用户问「为什么搜得更严 / 避开某类域名」→ get_lead_preferences 解释；找线索时不要顺手查偏好；要清空学习结果需用户明确同意后 reset_lead_preferences。
- 「今天做什么 / 该跟进谁 / 待办」→ get_workbench；用户说「标记已联系/已回复/不再跟进」→ update_contact 带 follow_up_status。
- 发邮件流程：list_email_templates 选模板 → preview_email 给用户看一封示例 → 用户同意后 queue_emails（系统会再弹确认，发送由后台按节流执行）。不要跳过预览直接排队，除非用户已明确指定模板并要求直接发。
- 「有哪些待审线索 / 帮我过一遍审核」→ list_lead_reviews 列出并给出建议；用户同意后 import_lead_reviews 导入指定条目。

入库与数据规则：
- import_leads 每行必须含 email，尽量带 org 和 name；asn 必须是纯数字（如 395092，不要带 AS 前缀）。
- 线索含 linkedin/x/facebook/profile_url 时，导入会自动写入联系人社交链接字段。
- 导入前用 list_contacts 查重；要屏蔽域名用 update_import_filters。

破坏性操作确认：调用 delete_contacts / dedupe_contacts / reset_lead_preferences / queue_emails 后若返回 confirm_required，表示系统在等用户确认。不要重试、不要自行再次调用该工具，用一句中文说明将发生什么（含数量），并提示用户点界面上的「确认执行」按钮。"""


def system_prompt_now() -> str:
    """System prompt plus the current date — the model cannot know "today"
    otherwise, and follow-up/workbench questions depend on it."""
    now = datetime.now(UTC)
    weekday = "一二三四五六日"[now.weekday()]
    return f"{SYSTEM_PROMPT}\n\n当前日期：{now.date().isoformat()}（周{weekday}，UTC）。"


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
            emit.progress(f"AS{event.get('asn')} · {event.get('candidate_count', 0)} 个邮箱候选")
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
    if name == "get_workbench":
        return (
            f"待审 {result.get('pending_reviews', 0)} · 今日新增 {result.get('imported_today', 0)}"
            f" · 待发信 {result.get('unsent_new', 0)}"
        )
    if name == "list_email_templates":
        return f"{result.get('total', 0)} 个邮件模板"
    if name == "preview_email":
        return f"预览「{result.get('template', '')}」→ {result.get('to', '')}".strip()
    if name == "queue_emails":
        return f"已排队 {result.get('queued', 0)} 封邮件"
    if name == "list_lead_reviews":
        return f"{result.get('status', 'pending')} 审核线索 {result.get('total', 0)} 条"
    if name == "import_lead_reviews":
        return f"审核通过并导入 {result.get('imported', result.get('approved', 0))} 条"
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


def _is_asn_role_lookup_turn(user_message: str) -> bool:
    text = (user_message or "").lower()
    if not text or not parse_asns_from_text(user_message):
        return False
    lookup_tokens = (
        "role",
        "rdap",
        "邮箱",
        "email",
        "mail",
        "abuse",
        "noc",
        "technical",
        "admin",
        "tech-c",
        "admin-c",
    )
    discovery_tokens = (
        "线索",
        "潜在客户",
        "客户",
        "公司",
        "导入",
        "import",
        "找更多",
        "挖掘",
    )
    return any(token in text for token in lookup_tokens) and not any(
        token in text for token in discovery_tokens
    )


def _is_lead_discovery_turn(user_message: str) -> bool:
    text = (user_message or "").lower()
    if not text:
        return False
    if _is_asn_role_lookup_turn(user_message):
        return False
    action_tokens = ("找", "搜", "挖", "discover", "search", "查找", "扩展")
    lead_tokens = (
        "peering",
        "noc",
        "isp",
        "运营商",
        "线索",
        "联系人",
        "客户",
        "公司",
        "asn 邮箱",
        "role 邮箱",
    )
    return any(token in text for token in action_tokens) and any(
        token in text for token in lead_tokens
    )


def _blocked_tool_result(name: str, reason: str) -> dict[str, Any]:
    return {
        "blocked": True,
        "tool": name,
        "reason": reason,
        "message": "该工具调用已被 Pi 商用护栏拦截，请根据已有结果直接总结。",
    }


def _tool_block_reason(
    name: str,
    *,
    user_message: str,
    current_batch_names: set[str],
    executed_names: list[str],
    executed_count: int,
) -> str | None:
    if executed_count >= MAX_EXECUTED_TOOL_CALLS_PER_TURN:
        return f"本轮工具调用预算已达 {MAX_EXECUTED_TOOL_CALLS_PER_TURN} 次"

    if _is_asn_role_lookup_turn(user_message):
        if name == "lookup_asns" and "lookup_asns" in executed_names:
            return "lookup_asns 本轮已完成明确 ASN role 邮箱查询，禁止重复查询"
        if name != "lookup_asns":
            return "明确 ASN role/RDAP 邮箱查询必须使用 lookup_asns，禁止扩展为线索搜索或网页搜索"

    discover_seen = "discover_leads" in executed_names or "discover_leads" in current_batch_names
    if not discover_seen:
        return None

    if name == "discover_leads" and "discover_leads" in executed_names:
        return "discover_leads 本轮已完成，禁止重复线索搜索"

    blocked_after_discover = {
        "web_search",
        "get_search_config",
        "get_lead_preferences",
        "list_contacts",
        "get_stats",
        "get_contact",
        "enrich_contact",
    }
    if name in blocked_after_discover and (
        "discover_leads" in executed_names or _is_lead_discovery_turn(user_message)
    ):
        return "discover_leads 已覆盖线索搜索/评分/入库，禁止继续调用辅助搜索或配置工具"
    return None


async def _finalize_with_summary(
    messages: list[dict[str, Any]],
    llm_client: Callable[..., AsyncIterator[dict[str, Any]]],
    instruction: str,
) -> AsyncIterator[dict[str, Any]]:
    messages.append({"role": "user", "content": instruction})
    final_text, ok = await _stream_text_reply(messages, llm_client)
    if not ok:
        final_text = "工具结果已整理完毕，请查看上方结果并按需继续缩小范围。"
    yield {"type": "assistant_start"}
    yield {"type": "assistant_delta", "text": final_text}
    yield {"type": "assistant_done", "text": final_text}
    yield {"type": "done"}


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


PI_DESTRUCTIVE_TOOLS = {
    "delete_contacts",
    "dedupe_contacts",
    "reset_lead_preferences",
    # 对外发信：不可撤回的外部副作用，与删除同级，必须用户确认。
    "queue_emails",
}


def _destructive_confirm_summary(name: str, args: dict[str, Any], user_id: int) -> str:
    if name == "delete_contacts":
        ids = [item for item in (args.get("contact_ids") or []) if item]
        return f"将删除 {len(ids)} 个联系人，此操作不可逆。"
    if name == "dedupe_contacts":
        return "将按邮箱合并并删除重复联系人，此操作不可逆。"
    if name == "reset_lead_preferences":
        return "将清空已学习的线索偏好并恢复默认，此操作不可逆。"
    if name == "queue_emails":
        ids = [item for item in (args.get("contact_ids") or []) if item]
        template = get_email_template(user_id, int(args.get("template_id") or 0))
        template_name = (template or {}).get("name") or f"#{args.get('template_id')}"
        return f"将用模板「{template_name}」给 {len(ids)} 个联系人排队发送邮件（发出后不可撤回）。"
    return "此操作不可逆，确认后才会执行。"


def _contact_to_undo_row(contact: dict[str, Any]) -> dict[str, Any]:
    """Shape a contact into an import-ready row so an accidental delete/dedupe
    can be re-imported via the normal contacts import path."""
    roles = contact.get("roles")
    if isinstance(roles, (list, tuple)):
        roles = ", ".join(str(role) for role in roles if role)
    return {
        "email": contact.get("email") or "",
        "org": contact.get("org") or "",
        "name": contact.get("name") or "",
        "roles": roles or "",
        "notes": contact.get("notes") or "",
        "source": "undo-restore",
    }


async def _run_tool(
    user_id: int,
    name: str,
    args: dict[str, Any],
    emit: ToolEmitter,
    *,
    allow_destructive: bool = False,
) -> Any:
    # Hard gate: destructive tools never run from the agent loop. They return a
    # confirm_required marker; only an explicit user confirmation (the
    # /api/pi/confirm-tool endpoint) sets allow_destructive=True. The model
    # cannot self-confirm because this flag is not a tool argument.
    if name in PI_DESTRUCTIVE_TOOLS and not allow_destructive:
        return {
            "confirm_required": True,
            "name": name,
            "summary": _destructive_confirm_summary(name, args, user_id),
            "pending_args": args,
        }
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
        payload = [
            normalize_import_row({**row, "source": row.get("source") or source})
            for row in rows
            if isinstance(row, dict)
        ]
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

    if name == "get_workbench":
        return get_workbench_summary(user_id)

    if name == "list_email_templates":
        templates = list_email_templates(user_id)
        return {
            "templates": [{k: t.get(k) for k in ("id", "name", "subject")} for t in templates],
            "total": len(templates),
        }

    if name == "preview_email":
        template_id = int(args.get("template_id") or 0)
        contact_id = int(args.get("contact_id") or 0)
        template = get_email_template(user_id, template_id)
        if not template:
            return {"error": "模板不存在"}
        contact = get_contact(user_id, contact_id)
        if not contact:
            return {"error": "联系人不存在"}
        subject, text, _html = render_email(template, contact)
        return {
            "template": template.get("name") or "",
            "to": contact.get("email") or "",
            "subject": subject,
            "body_text": text,
        }

    if name == "queue_emails":
        contact_ids = [int(item) for item in (args.get("contact_ids") or []) if int(item) > 0]
        template_id = int(args.get("template_id") or 0)
        if not contact_ids or template_id <= 0:
            return {"error": "contact_ids 或 template_id 无效"}
        return queue_emails_for_contacts(
            user_id,
            contact_ids,
            template_id,
            skip_sent=bool(args.get("skip_sent", True)),
        )

    if name == "list_lead_reviews":
        status = str(args.get("status") or "pending").strip().lower()
        if status not in {"pending", "approved", "rejected", "all"}:
            return {"error": "status 必须是 pending/approved/rejected/all"}
        limit = max(1, min(int(args.get("limit") or 50), 200))
        reviews = list_lead_reviews(user_id, status=status, limit=limit)
        return {"reviews": reviews, "total": len(reviews), "status": status}

    if name == "import_lead_reviews":
        review_ids = [int(item) for item in (args.get("review_ids") or []) if int(item) > 0]
        if not review_ids:
            return {"error": "review_ids 为空"}
        result = import_lead_reviews(user_id, review_ids)
        result["total_contacts"] = count_contacts(user_id)
        return result

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
            if not update_contact_follow_up_status(
                user_id, contact_id, str(status).strip().lower()
            ):
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
        undo_rows = [
            _contact_to_undo_row(contact) for cid in ids if (contact := get_contact(user_id, cid))
        ]
        if len(ids) == 1:
            ok = delete_contact(user_id, ids[0])
            result = {"deleted": 1 if ok else 0, "requested": 1}
        else:
            result = bulk_delete_contacts(user_id, ids)
        if undo_rows and result.get("deleted"):
            result["undo_payload"] = undo_rows
            result["undo_kind"] = "contacts"
        return result

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
        prior = get_prefs(user_id)
        prefs = reset_prefs(user_id)
        return {
            "ok": True,
            "preferences": prefs,
            "message": "线索偏好已重置为默认",
            "undo_payload": prior,
            "undo_kind": "prefs",
        }

    if name == "dedupe_contacts":
        result = dedupe_contacts(user_id=user_id)
        removed_rows = result.pop("removed_rows", [])
        result["total_contacts"] = count_contacts(user_id)
        if removed_rows:
            result["undo_payload"] = [_contact_to_undo_row(row) for row in removed_rows]
            result["undo_kind"] = "contacts"
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
        max_urls = max(
            1, min(int(args.get("max_urls") or bs.DEFAULT_MAX_URLS), bs.DEFAULT_MAX_URLS)
        )
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
        progress = (
            f"联网搜索 {len(queries)} 条：{', '.join(queries[:2])}{'…' if len(queries) > 2 else ''}"
        )
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
        backend = (
            results[0].get("backend")
            if results
            else web_search.get_search_config()["active_web_backend"]
        )
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
    try:
        async for event in stream_chat(messages, tools, tool_choice=tool_choice):
            yield event
    except LLMError as exc:
        yield {"type": "error", "message": str(exc)}


async def _stream_text_reply(
    messages: list[dict[str, Any]],
    llm_client: Callable[..., AsyncIterator[dict[str, Any]]] | None = None,
) -> tuple[str, bool]:
    """One text-only LLM turn (no tools). Returns (text, ok)."""
    client = llm_client or _iter_llm_stream
    assistant: dict[str, Any] | None = None
    content_buffer = ""
    async for event in client(messages, None):
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
    llm_client: Callable[..., AsyncIterator[dict[str, Any]]] | None = None,
    tool_runner: Callable[..., Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    if cancel_check and cancel_check():
        yield {"type": "error", "message": "任务已停止"}
        yield {"type": "done"}
        return
    yield {"type": "status", "message": "Pi 助手思考中…"}
    llm_client = llm_client or _iter_llm_stream
    tool_runner = tool_runner or _run_tool

    thread: dict[str, Any] | None = None
    if thread_id:
        loaded = get_pi_thread(user_id, thread_id)
        if loaded:
            history = loaded.get("history") or []
            had_summary = bool((loaded.get("context_summary") or "").strip())
            summary_through = int(loaded.get("context_summary_through") or 0)
            context_summary = str(loaded.get("context_summary") or "")
            usage_percent = int(
                context_stats(
                    history,
                    context_summary=context_summary,
                    summary_through=summary_through,
                    system_chars=len(SYSTEM_PROMPT),
                    tools_chars=len(json.dumps(AGENT_TOOLS, ensure_ascii=False)),
                    model=get_setting("llm_model", ""),
                ).get("usage_percent")
                or 0
            )
            if should_compress_thread(len(history), summary_through, usage_percent=usage_percent):
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
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt_now()}]
    messages.extend(history)
    append_user_turn_to_messages(messages, history or [], message)

    llm_call_count = 0
    executed_tool_names: list[str] = []
    executed_tool_count = 0
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
        llm_nudge_count = 0
        content = ""
        prepared_calls: list[tuple[dict[str, Any], str, dict[str, Any]]] = []

        while True:
            if cancel_check and cancel_check():
                yield {"type": "error", "message": "任务已停止"}
                yield {"type": "done"}
                return
            if llm_call_count >= MAX_LLM_CALLS_PER_TURN:
                msg = "本次对话已达调用上限，请简化问题后重试。"
                yield {"type": "assistant_start"}
                yield {"type": "assistant_delta", "text": msg}
                yield {"type": "assistant_done", "text": msg}
                yield {"type": "done"}
                return
            assistant = None
            content_buffer = ""
            streamed_reply = False
            last_streamed_visible = ""
            reasoning_open = False

            tool_choice: str | dict[str, Any] | None = (
                "required" if llm_nudge_count > 0 and AGENT_TOOLS else None
            )

            llm_call_count += 1
            overflow_retried = False
            llm_stream_done = False
            while not llm_stream_done:
                recover_overflow = False
                async for event in llm_client(messages, AGENT_TOOLS, tool_choice=tool_choice):
                    event_type = event.get("type")
                    if event_type == "error":
                        err_msg = str(event.get("message") or "LLM 请求失败")
                        if (
                            is_context_overflow_error(err_msg)
                            and thread_id
                            and not overflow_retried
                        ):
                            overflow_retried = True
                            recover_overflow = True
                            yield {
                                "type": "status",
                                "message": "上下文过长，正在压缩后重试…",
                            }
                            thread = await asyncio.to_thread(
                                compress_thread_context_until_current,
                                user_id,
                                thread_id,
                                max_rounds=48,
                            )
                            thread = thread or get_pi_thread(user_id, thread_id)
                            context_summary = str((thread or {}).get("context_summary") or "")
                            summary_through = int(
                                (thread or {}).get("context_summary_through") or 0
                            )
                            trimmed = _trim_history(
                                (thread or {}).get("history") or [],
                                context_summary=context_summary,
                                summary_through=summary_through,
                            )
                            messages.clear()
                            messages.append({"role": "system", "content": system_prompt_now()})
                            messages.extend(trimmed)
                            append_user_turn_to_messages(messages, trimmed, message)
                            stats_history = (thread or {}).get("history") if thread else trimmed
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
                            break
                        yield {"type": "error", "message": err_msg}
                        yield {"type": "done"}
                        return
                    elif event_type == "reasoning_start":
                        reasoning_open = True
                        yield {"type": "reasoning_start"}
                    elif event_type == "reasoning_delta":
                        yield event
                    elif event_type == "content_delta":
                        piece = str(event.get("text") or "")
                        if piece:
                            content_buffer += piece
                            visible = _meaningful_assistant_content(content_buffer)
                            if visible and len(visible) > len(last_streamed_visible):
                                delta = visible[len(last_streamed_visible) :]
                                last_streamed_visible = visible
                                if delta:
                                    if not streamed_reply:
                                        if reasoning_open:
                                            reasoning_open = False
                                            yield {"type": "reasoning_done"}
                                        streamed_reply = True
                                        yield {"type": "assistant_start"}
                                    yield {"type": "assistant_delta", "text": delta}
                    elif event_type == "status":
                        yield {
                            "type": "status",
                            "message": event.get("message") or "Pi 助手处理中…",
                        }
                    elif event_type == "message":
                        assistant = event.get("message")

                if recover_overflow:
                    continue
                llm_stream_done = True

            decision = decide_turn(
                assistant,
                content_buffer,
                user_message=message,
                history=history or [],
                nudge_count=llm_nudge_count,
                max_nudges=_MAX_LLM_NUDGES,
            )

            if isinstance(decision, Retry):
                llm_nudge_count += 1
                messages.append({"role": "user", "content": decision.nudge})
                yield {"type": "status", "message": "模型未调用工具，正在重试…"}
                continue

            if isinstance(decision, Fail):
                yield {"type": "error", "message": decision.error}
                yield {"type": "done"}
                return

            if isinstance(decision, FinalReply):
                if not streamed_reply:
                    yield {"type": "assistant_start"}
                    yield {"type": "assistant_delta", "text": decision.text}
                yield {"type": "assistant_done", "text": decision.text}
                yield {"type": "done"}
                return

            if isinstance(decision, FallbackToolCalls):
                prepared_calls = decision.prepared_calls
                content = _meaningful_assistant_content(
                    (assistant or {}).get("content") or content_buffer or ""
                )
                assistant = {**(assistant or {}), "role": "assistant", "content": content or None}
                yield {"type": "status", "message": decision.status_message}
                break

            # EmitToolCalls
            prepared_calls = decision.prepared_calls
            content = decision.intro_text
            assistant = {
                **(assistant or {}),
                "role": "assistant",
                "content": content or None,
                "tool_calls": [tc for tc, _, _ in prepared_calls],
            }
            break

        if not assistant:
            yield {"type": "error", "message": "模型未返回有效回复，请换种说法或检查 LLM 配置"}
            yield {"type": "done"}
            return

        intro = _meaningful_assistant_content(
            content or _assistant_intro_before_tools(content_buffer)
        )
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

        current_batch_names = {name for _, name, _ in prepared_calls}
        should_force_summary = False
        allowed_calls: list[tuple[dict[str, Any], str, dict[str, Any]]] = []

        for tool_call, name, args in prepared_calls:
            block_reason = _tool_block_reason(
                name,
                user_message=message,
                current_batch_names=current_batch_names,
                executed_names=executed_tool_names,
                executed_count=executed_tool_count,
            )
            if block_reason:
                blocked_result = _blocked_tool_result(name, block_reason)
                yield {
                    "type": "tool_blocked",
                    "name": name,
                    "args": args,
                    "reason": block_reason,
                }
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": compress_tool_result_for_llm(name, blocked_result),
                    }
                )
                allow_asn_lookup_correction = (
                    block_reason.startswith("明确 ASN")
                    and "lookup_asns" not in executed_tool_names
                    and "lookup_asns" not in current_batch_names
                )
                if not allow_asn_lookup_correction:
                    should_force_summary = True
                continue
            allowed_calls.append((tool_call, name, args))

        parallel_batch = len(allowed_calls) > 1 and can_parallelize_tool_batch(
            [name for _, name, _ in allowed_calls]
        )

        def _start_tool_worker(
            name: str, args: dict[str, Any]
        ) -> tuple[asyncio.Task[None], asyncio.Queue[tuple[str, Any] | None], dict[str, Any]]:
            event_queue: asyncio.Queue[tuple[str, Any] | None] = asyncio.Queue()
            result_holder: dict[str, Any] = {}

            async def worker() -> None:
                try:
                    emitter = ToolEmitter(event_queue)
                    result_holder["value"] = await tool_runner(user_id, name, args, emitter)
                except Exception as exc:  # noqa: BLE001 — keep SSE stream alive
                    result_holder["value"] = {"error": str(exc)}
                finally:
                    await event_queue.put(None)

            return asyncio.create_task(worker()), event_queue, result_holder

        async def _stream_tool_events(
            name: str, event_queue: asyncio.Queue[tuple[str, Any] | None]
        ) -> AsyncIterator[dict[str, Any]]:
            while True:
                try:
                    item = await asyncio.wait_for(event_queue.get(), timeout=TOOL_HEARTBEAT_SECONDS)
                except TimeoutError:
                    yield {"type": "status", "message": f"仍在执行 {name}…"}
                    continue
                if item is None:
                    break
                kind, payload = item
                if kind == "progress":
                    yield {"type": "tool_progress", "name": name, "message": payload}
                elif kind == "event":
                    yield {"type": "tool_event", "name": name, "event": payload}

        if parallel_batch:
            tracked: list[
                tuple[
                    dict[str, Any],
                    str,
                    dict[str, Any],
                    asyncio.Task[None],
                    asyncio.Queue[tuple[str, Any] | None],
                    dict[str, Any],
                ]
            ] = []
            for tool_call, name, args in allowed_calls:
                yield {"type": "tool_start", "name": name, "args": args}
                task, event_queue, result_holder = _start_tool_worker(name, args)
                tracked.append((tool_call, name, args, task, event_queue, result_holder))

            pending = [True] * len(tracked)
            while any(pending):
                for i, (_tool_call, name, _args, _task, event_queue, _result_holder) in enumerate(
                    tracked
                ):
                    if not pending[i]:
                        continue
                    while True:
                        try:
                            item = event_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                        if item is None:
                            pending[i] = False
                            break
                        kind, payload = item
                        if kind == "progress":
                            yield {
                                "type": "tool_progress",
                                "name": name,
                                "message": payload,
                            }
                        elif kind == "event":
                            yield {"type": "tool_event", "name": name, "event": payload}
                if any(pending):
                    await asyncio.sleep(0.05)
            for tool_call, name, _args, task, _event_queue, result_holder in tracked:
                await task
                executed_tool_count += 1
                executed_tool_names.append(name)
                result = result_holder.get("value", {"error": "工具执行失败"})
                yield {"type": "tool_result", "name": name, "result": result}
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": compress_tool_result_for_llm(name, result),
                    }
                )
                if _should_force_summary_after_tool(
                    name,
                    user_message=message,
                    executed_count=executed_tool_count,
                ):
                    should_force_summary = True
        else:
            for tool_call, name, args in allowed_calls:
                yield {"type": "tool_start", "name": name, "args": args}
                executed_tool_count += 1
                executed_tool_names.append(name)
                task, event_queue, result_holder = _start_tool_worker(name, args)
                async for event in _stream_tool_events(name, event_queue):
                    yield event
                await task
                result = result_holder.get("value", {"error": "工具执行失败"})
                yield {"type": "tool_result", "name": name, "result": result}
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": compress_tool_result_for_llm(name, result),
                    }
                )
                if _should_force_summary_after_tool(
                    name,
                    user_message=message,
                    executed_count=executed_tool_count,
                ):
                    should_force_summary = True

        if should_force_summary:
            reason = (
                "（系统）关键工具已完成，或本轮工具预算/商用护栏已触发。"
                "请立即根据已有工具结果给出简洁总结和下一步建议，不要再调用任何工具。"
            )
            async for event in _finalize_with_summary(messages, llm_client, reason):
                yield event
            return

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
            final_text, ok = await _stream_text_reply(messages, llm_client)
            if not ok:
                final_text = "已达到最大工具调用轮次，请简化问题后重试。"
            yield {"type": "assistant_start"}
            yield {"type": "assistant_delta", "text": final_text}
            yield {"type": "assistant_done", "text": final_text}
            yield {"type": "done"}
            return

    yield {"type": "error", "message": "对话未完成，请重试"}
    yield {"type": "done"}
