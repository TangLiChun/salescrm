from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from arin_lookup import lookup_asn, parse_asns_from_text
from app.database import (
    bulk_delete_contacts,
    count_contacts,
    create_contact_note,
    dedupe_contacts,
    delete_contact,
    get_contact_stats,
    import_contacts,
    list_contacts,
    mark_contact_sent,
    update_contact,
    update_contact_follow_up_status,
)
from app.lead_discovery import discover_leads_stream
from app.llm import LLMError, chat_completion_with_tools

MAX_TOOL_ROUNDS = 8
MAX_HISTORY = 20

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
            "description": "将线索行导入 CRM，email 必填",
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
            "name": "discover_leads",
            "description": "使用 CRM 内置 AI 多渠道线索发现（搜索+PeeringDB+全球 RDAP）",
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
]

SYSTEM_PROMPT = """你是 Sales CRM 的 Pi 助手，帮助销售/BD 人员操作网络运营商联系人库。

能力：
- lookup_asns：全球 RIR（ARIN/RIPE/APNIC/LACNIC/AFRINIC）RDAP 查 ASN role 邮箱，非 ARIN 会自动查对应注册局
- discover_leads：AI 多渠道找线索（与「AI 线索发现」相同）
- list_contacts / import_leads：搜索、导入联系人
- update_contact / mark_contact_sent / delete_contacts / add_contact_note：管理已有联系人
- get_stats / dedupe_contacts：统计与去重

规则：用简洁中文回复；导入前尽量 list_contacts 查重；查完 ASN 可用 import_leads 导入；不要编造数据。"""


class ToolEmitter:
    def __init__(self, queue: asyncio.Queue[tuple[str, Any] | None]) -> None:
        self._queue = queue

    def progress(self, message: str) -> None:
        self._queue.put_nowait(("progress", message))

    def event(self, payload: dict[str, Any]) -> None:
        self._queue.put_nowait(("event", payload))


def _trim_history(history: list[dict[str, str]]) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for item in history[-MAX_HISTORY:]:
        role = item.get("role")
        content = (item.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            cleaned.append({"role": role, "content": content})
    return cleaned


async def _discover_leads_tool(
    user_id: int,
    args: dict[str, Any],
    emit: ToolEmitter,
) -> dict[str, Any]:
    query = str(args.get("query") or "").strip()
    min_score = int(args.get("min_score") or 60)
    auto_import = bool(args.get("auto_import"))
    leads: list[dict[str, Any]] = []
    import_result = None
    message = ""

    async for event in discover_leads_stream(
        query,
        min_score=min_score,
        auto_import=auto_import,
        user_id=user_id,
    ):
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
            return {"error": event.get("message"), "leads": leads}
        elif event_type == "done":
            leads = event.get("leads") or leads
            import_result = event.get("import")
            message = event.get("message") or ""
            emit.event({"kind": "done", "message": message, "lead_count": len(leads), "import": import_result})

    preview = [
        {
            "org": lead.get("org"),
            "email": lead.get("email"),
            "score": lead.get("lead_score"),
            "source": lead.get("source"),
        }
        for lead in leads[:15]
    ]
    return {
        "message": message,
        "lead_count": len(leads),
        "leads": leads,
        "leads_preview": preview,
        "import": import_result,
    }


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

    if name == "import_leads":
        rows = args.get("rows") or []
        source = str(args.get("source") or "pi-agent")
        payload = [
            {**row, "source": row.get("source") or source}
            for row in rows
            if isinstance(row, dict)
        ]
        result = import_contacts(user_id, payload)
        result["total_contacts"] = count_contacts(user_id)
        return result

    if name == "discover_leads":
        return await _discover_leads_tool(user_id, args, emit)

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

    return {"error": f"未知工具: {name}"}


async def agent_chat_stream(
    user_id: int,
    message: str,
    history: list[dict[str, str]] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    history = _trim_history(history or [])
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": message.strip()})

    yield {"type": "status", "message": "Pi 助手思考中…"}

    for round_index in range(MAX_TOOL_ROUNDS):
        try:
            assistant = await asyncio.to_thread(
                chat_completion_with_tools,
                messages,
                AGENT_TOOLS,
            )
        except LLMError as exc:
            yield {"type": "error", "message": str(exc)}
            return

        tool_calls = assistant.get("tool_calls") or []
        content = (assistant.get("content") or "").strip()

        if content and not tool_calls:
            yield {"type": "assistant", "text": content}
            yield {"type": "done"}
            return

        if not tool_calls:
            yield {"type": "error", "message": "模型未返回有效回复"}
            return

        messages.append(assistant)

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
                finally:
                    await event_queue.put(None)

            task = asyncio.create_task(worker())
            while True:
                item = await event_queue.get()
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
            yield {"type": "assistant", "text": "已达到最大工具调用轮次，请简化问题后重试。"}
            yield {"type": "done"}
