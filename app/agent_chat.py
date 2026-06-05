from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from typing import Any

from arin_lookup import lookup_asn, parse_asns_from_text
from app.database import count_contacts, get_contact_stats, import_contacts, list_contacts
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
            "description": "使用 CRM 内置 AI 多渠道线索发现（搜索+PeeringDB+ARIN）",
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
            "description": "批量 ARIN RDAP 查询 ASN role 邮箱，支持混排文本自动去重",
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
]

SYSTEM_PROMPT = """你是 Sales CRM 的 Pi 助手，帮助销售/BD 人员操作网络运营商联系人库。
你可以调用工具查询 ASN、AI 发现线索、搜索/导入联系人、查看统计。
规则：用简洁中文回复；导入前尽量 list_contacts 查重；不要编造数据。"""


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
    emit: Callable[[str], None],
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
            emit(str(event.get("message") or "搜索中…"))
        elif event_type == "plan":
            plan = event.get("plan") or {}
            emit(str(plan.get("summary") or "已生成搜索计划"))
        elif event_type == "source_result":
            emit(f"{event.get('source')}: {event.get('count', 0)} 条")
        elif event_type == "progress":
            emit(
                str(
                    event.get("message")
                    or f"ARIN AS{event.get('asn')} ({event.get('index')}/{event.get('total')})"
                )
            )
        elif event_type == "lead":
            leads.append(event["lead"])
        elif event_type == "error":
            return {"error": event.get("message"), "leads": leads}
        elif event_type == "done":
            leads = event.get("leads") or leads
            import_result = event.get("import")
            message = event.get("message") or ""

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
        "leads_preview": preview,
        "import": import_result,
    }


async def _lookup_asns_tool(args: dict[str, Any], emit: Callable[[str], None]) -> dict[str, Any]:
    text = str(args.get("text") or "")
    asns = parse_asns_from_text(text)[:50]
    if not asns:
        return {"error": "未识别到有效 ASN", "asns": []}
    emit(f"已识别 {len(asns)} 个 ASN，开始 RDAP 查询…")
    rows: list[dict[str, Any]] = []
    for index, asn in enumerate(asns, start=1):
        emit(f"查询 AS{asn}（{index}/{len(asns)}）")
        batch = await asyncio.to_thread(lookup_asn, asn)
        rows.extend(row.to_dict() for row in batch)
    emails = [r for r in rows if r.get("email") and not r.get("error")]
    return {
        "asns": asns,
        "row_count": len(rows),
        "email_count": len(emails),
        "preview": emails[:20],
    }


async def _run_tool(
    user_id: int,
    name: str,
    args: dict[str, Any],
    emit: Callable[[str], None],
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

            progress_queue: asyncio.Queue[str | None] = asyncio.Queue()
            result_holder: dict[str, Any] = {}

            def emit_progress(msg: str) -> None:
                progress_queue.put_nowait(msg)

            async def worker() -> None:
                try:
                    result_holder["value"] = await _run_tool(user_id, name, args, emit_progress)
                finally:
                    await progress_queue.put(None)

            task = asyncio.create_task(worker())
            while True:
                progress_msg = await progress_queue.get()
                if progress_msg is None:
                    break
                yield {"type": "tool_progress", "name": name, "message": progress_msg}
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
