from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import AsyncIterator
from typing import Any

from arin_lookup import lookup_asn, parse_asns_from_text
from app.contact_enrichment import enrich_contact_stream
from app.database import (
    bulk_delete_contacts,
    count_contacts,
    create_contact_note,
    dedupe_contacts,
    delete_contact,
    get_contact,
    get_contact_stats,
    import_contacts,
    list_contacts,
    list_scheduled_jobs,
    mark_contact_sent,
    normalize_import_row,
    update_contact,
    update_contact_follow_up_status,
)
from app.import_filters import parse_patterns
from app.lead_discovery import discover_leads_stream
from app.llm import LLMError, chat_completion_with_tools_stream
from app.pi_chat_store import (
    MAX_LLM_HISTORY_MESSAGES,
    get_pi_thread,
    history_for_llm,
)
from app.settings_store import get_setting, update_settings
from app.sources import web_search

MAX_TOOL_ROUNDS = 8
MAX_HISTORY = MAX_LLM_HISTORY_MESSAGES
MAX_WEB_SEARCH_QUERIES = 4
TOOL_HEARTBEAT_SECONDS = 12

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
            "description": "将线索行导入 CRM；每行需含 email，并尽量填写 org（公司/组织）和 name（联系人姓名）",
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
                    "min_score": {"type": "integer", "description": "最低相关度，默认 50"},
                    "auto_import": {"type": "boolean", "description": "找到后自动导入 CRM"},
                },
                "required": ["contact_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "discover_leads",
            "description": "使用 CRM 内置 AI 多渠道线索发现（LLM 规划 → 联网搜索[智谱/Bright Data/Tavily/SerpAPI/Brave/DuckDuckGo 按优先级] → PeeringDB → 全球 RDAP → LLM 评分）",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "min_score": {"type": "integer"},
                    "auto_import": {"type": "boolean"},
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
            "description": "查看当前联网搜索配置：启用的搜索引擎、优先级、智谱/Bright Data SERP 等 API Key 是否已配置",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "直接调用 CRM 联网搜索（与 discover_leads 内嵌的搜索引擎相同，按系统设置优先级自动选智谱/Tavily 等）",
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
]

SYSTEM_PROMPT = """你是 Sales CRM 的 Pi 助手，帮助销售/BD 人员操作网络运营商联系人库。

能力：
- lookup_asns：全球 RIR（ARIN/RIPE/APNIC/LACNIC/AFRINIC）RDAP 查 ASN role 邮箱
- discover_leads：AI 多渠道找线索（联网搜索 + PeeringDB + RDAP + LLM 评分）
- web_search：直接联网搜索（不跑完整线索流程）
- get_search_config：查看当前联网搜索用哪个引擎（智谱 zhipu / Bright Data Google SERP / Tavily / SerpAPI / Brave / DuckDuckGo）及优先级
- enrich_contact：为已有联系人扩展更多联系方式，可 auto_import
- get_contact / list_contacts / import_leads：读取、搜索、导入联系人
- update_contact / mark_contact_sent / delete_contacts / add_contact_note：管理联系人
- get_stats / dedupe_contacts：统计与去重
- get_import_filters / update_import_filters：导入黑名单/白名单（设置页同源）
- list_schedules：定时线索任务

联网搜索说明：系统设置 → AI 与搜索 中配置。默认优先级 brightdata(Bright Data Google SERP) > zhipu(智谱) > tavily > serpapi > brave > duckduckgo。
用户问「AI 搜索用的什么 / 怎么调用 / 有哪些渠道」时，先调用 get_search_config 再回答，不要猜测。

规则：简洁中文；屏蔽域名用 update_import_filters；导入前查重；不要编造数据。"""


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
            emit.progress(str(event.get("message") or "搜索中…"))
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


def _trim_history(history: list[dict[str, Any]]) -> list[dict[str, str]]:
    return history_for_llm(history)


def _assistant_intro_before_tools(content: str) -> str:
    text = (content or "").strip()
    if not text:
        return ""
    lower = text.lower()
    cut_at = len(text)
    for marker in (
        "[工具",
        "tool_calls",
        "<|",
        "```json",
        '{"query',
        '{"queries',
        '"queries"',
    ):
        idx = lower.find(marker.lower())
        if idx >= 0:
            cut_at = min(cut_at, idx)
    return text[:cut_at].strip()


async def _discover_leads_tool(
    user_id: int,
    args: dict[str, Any],
    emit: ToolEmitter,
) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    min_score = int(args.get("min_score") or 60)
    auto_import = bool(args.get("auto_import"))

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
    min_score = int(args.get("min_score") or 50)
    auto_import = bool(args.get("auto_import"))

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

    if name == "get_search_config":
        return web_search.get_search_config()

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
    tools: list[dict[str, Any]],
) -> AsyncIterator[dict[str, Any]]:
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def worker() -> None:
        try:
            for event in chat_completion_with_tools_stream(messages, tools):
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


async def agent_chat_stream(
    user_id: int,
    message: str,
    history: list[dict[str, str]] | None = None,
    *,
    thread_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    if thread_id:
        thread = get_pi_thread(user_id, thread_id)
        if thread:
            history = thread.get("history") or []
    history = _trim_history(history or [])
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": message.strip()})

    yield {"type": "status", "message": "Pi 助手思考中…"}

    for round_index in range(MAX_TOOL_ROUNDS):
        assistant: dict[str, Any] | None = None
        content_buffer = ""

        async for event in _iter_llm_stream(messages, AGENT_TOOLS):
            event_type = event.get("type")
            if event_type == "error":
                yield {"type": "error", "message": event.get("message") or "LLM 请求失败"}
                return
            if event_type == "content_delta":
                piece = str(event.get("text") or "")
                if piece:
                    content_buffer += piece
            elif event_type == "message":
                assistant = event.get("message")

        if not assistant:
            yield {"type": "error", "message": "模型未返回有效回复"}
            return

        tool_calls = assistant.get("tool_calls") or []
        content = (assistant.get("content") or content_buffer or "").strip()

        if content and not tool_calls:
            yield {"type": "assistant_start"}
            yield {"type": "assistant_delta", "text": content}
            yield {"type": "assistant_done", "text": content}
            yield {"type": "done"}
            return

        if not tool_calls:
            yield {"type": "error", "message": "模型未返回有效回复"}
            return

        intro = _assistant_intro_before_tools(content)
        if intro:
            yield {"type": "assistant_start"}
            yield {"type": "assistant_delta", "text": intro}
            yield {"type": "assistant_done", "text": intro}

        messages.append({**assistant, "content": intro or None})

        for tool_call in tool_calls:
            fn = tool_call.get("function") or {}
            name = fn.get("name") or "unknown"
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except json.JSONDecodeError:
                args = {}

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
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.get("id"),
                    "content": json.dumps(result, ensure_ascii=False)[:12000],
                }
            )

        if round_index == MAX_TOOL_ROUNDS - 1:
            final_text = "已达到最大工具调用轮次，请简化问题后重试。"
            yield {"type": "assistant_start"}
            yield {"type": "assistant_delta", "text": final_text}
            yield {"type": "assistant_done", "text": final_text}
            yield {"type": "done"}
            return

    yield {"type": "error", "message": "对话未完成，请重试"}
