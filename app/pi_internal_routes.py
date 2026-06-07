"""Internal HTTP API for the TypeScript Pi agent service.

Not exposed publicly — requires X-Internal-Secret and is only reachable on the Docker network.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent_chat import (
    AGENT_TOOLS,
    MAX_EXECUTED_TOOL_CALLS_PER_TURN,
    SYSTEM_PROMPT,
    ToolEmitter,
    _blocked_tool_result,
    _is_asn_role_lookup_turn,
    _run_tool,
    _tool_block_reason,
    append_user_turn_to_messages,
)
from app.llm import get_setting, llm_configured
from app.pi_chat_store import (
    append_pi_thread_history_entries,
    compress_thread_context_until_current,
    get_pi_thread,
)
from app.pi_context import compress_tool_result_for_llm, context_stats, needs_summary_update

router = APIRouter(prefix="/api/internal/pi", tags=["pi-internal"])


def _internal_secret() -> str:
    return os.environ.get("PI_INTERNAL_SECRET", "").strip()


def _verify_internal(request: Request) -> None:
    secret = _internal_secret()
    if not secret:
        raise HTTPException(
            status_code=503, detail="PI internal API disabled (no PI_INTERNAL_SECRET)"
        )
    if request.headers.get("X-Internal-Secret") != secret:
        raise HTTPException(status_code=403, detail="Forbidden")


class PrepareRequest(BaseModel):
    user_id: int
    message: str
    thread_id: str | None = None
    history: list[dict[str, Any]] | None = None


class PersistRequest(BaseModel):
    user_id: int
    thread_id: str
    entries: list[dict[str, Any]]
    compress: bool = True


class ToolRunRequest(BaseModel):
    user_id: int
    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class CompressToolRequest(BaseModel):
    name: str
    result: dict[str, Any] = Field(default_factory=dict)


class ToolBlockRequest(BaseModel):
    name: str
    user_message: str
    current_batch_names: list[str] = Field(default_factory=list)
    executed_names: list[str] = Field(default_factory=list)
    executed_count: int = 0


class ForceSummaryRequest(BaseModel):
    name: str
    user_message: str
    executed_count: int = 0


async def prepare_pi_turn(
    user_id: int,
    message: str,
    *,
    thread_id: str | None = None,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    thread: dict[str, Any] | None = None
    status_messages: list[str] = []

    if thread_id:
        loaded = get_pi_thread(user_id, thread_id)
        if loaded:
            history = loaded.get("history") or []
            had_summary = bool((loaded.get("context_summary") or "").strip())
            summary_through = int(loaded.get("context_summary_through") or 0)
            if needs_summary_update(len(history), summary_through):
                status_messages.append("整理对话上下文…")
            thread = await asyncio.to_thread(
                compress_thread_context_until_current,
                user_id,
                thread_id,
            )
            thread = thread or get_pi_thread(user_id, thread_id)
            if thread and not had_summary and (thread.get("context_summary") or "").strip():
                status_messages.append("长对话已滚动压缩，继续处理…")

    from app.agent_chat import _trim_history

    context_summary = str((thread or {}).get("context_summary") or "")
    summary_through = int((thread or {}).get("context_summary_through") or 0)
    trimmed_history = _trim_history(
        history or [],
        context_summary=context_summary,
        summary_through=summary_through,
    )
    stats_history = (thread or {}).get("history") if thread else (trimmed_history or [])

    context_event = {
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
    messages.extend(trimmed_history)
    append_user_turn_to_messages(messages, trimmed_history or [], message)

    return {
        "messages": messages,
        "context_event": context_event,
        "tools": AGENT_TOOLS,
        "history": trimmed_history,
        "status_messages": status_messages,
    }


@router.get("/llm-config")
def internal_llm_config(request: Request) -> dict:
    _verify_internal(request)
    if not llm_configured():
        raise HTTPException(status_code=503, detail="LLM not configured")
    from app.llm import _settings, resolve_deepseek_thinking

    api_key, base_url, model = _settings()
    return {
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "thinking": resolve_deepseek_thinking(tools=AGENT_TOOLS),
    }


@router.post("/prepare")
async def internal_prepare(body: PrepareRequest, request: Request) -> dict:
    _verify_internal(request)
    prepared = await prepare_pi_turn(
        body.user_id,
        body.message,
        thread_id=body.thread_id,
        history=body.history,
    )
    return prepared


@router.post("/persist")
async def internal_persist(body: PersistRequest, request: Request) -> dict:
    _verify_internal(request)
    if body.entries:
        append_pi_thread_history_entries(body.user_id, body.thread_id, body.entries)
        if body.compress:
            await asyncio.to_thread(
                compress_thread_context_until_current,
                body.user_id,
                body.thread_id,
            )
    return {"ok": True}


@router.post("/compress-tool")
def internal_compress_tool(body: CompressToolRequest, request: Request) -> dict:
    _verify_internal(request)
    return {"content": compress_tool_result_for_llm(body.name, body.result)}


@router.post("/tool-block")
def internal_tool_block(body: ToolBlockRequest, request: Request) -> dict:
    _verify_internal(request)
    reason = _tool_block_reason(
        body.name,
        user_message=body.user_message,
        current_batch_names=set(body.current_batch_names),
        executed_names=body.executed_names,
        executed_count=body.executed_count,
    )
    if reason:
        blocked = _blocked_tool_result(body.name, reason)
        return {
            "blocked": True,
            "reason": reason,
            "result": blocked,
            "llm_content": compress_tool_result_for_llm(body.name, blocked),
        }
    return {"blocked": False}


@router.post("/force-summary")
def internal_force_summary(body: ForceSummaryRequest, request: Request) -> dict:
    _verify_internal(request)
    force = (
        body.name == "discover_leads"
        or (body.name == "lookup_asns" and _is_asn_role_lookup_turn(body.user_message))
        or body.executed_count >= MAX_EXECUTED_TOOL_CALLS_PER_TURN
    )
    return {"force": force}


@router.post("/tools/run")
async def internal_tool_run(body: ToolRunRequest, request: Request) -> StreamingResponse:
    _verify_internal(request)

    async def event_generator():
        queue: asyncio.Queue[tuple[str, Any] | None] = asyncio.Queue()
        emitter = ToolEmitter(queue)
        result_holder: dict[str, Any] = {}

        async def worker() -> None:
            try:
                result_holder["value"] = await _run_tool(
                    body.user_id,
                    body.name,
                    body.args,
                    emitter,
                )
            except Exception as exc:  # noqa: BLE001
                result_holder["value"] = {"error": str(exc)}
            finally:
                await queue.put(None)

        task = asyncio.create_task(worker())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                kind, payload = item
                if kind == "progress":
                    yield f"data: {json.dumps({'type': 'tool_progress', 'message': payload}, ensure_ascii=False)}\n\n"
                elif kind == "event":
                    yield f"data: {json.dumps({'type': 'tool_event', 'event': payload}, ensure_ascii=False)}\n\n"
            await task
            result = result_holder.get("value", {"error": "工具执行失败"})
            llm_content = compress_tool_result_for_llm(body.name, result)
            payload = {
                "type": "done",
                "result": result,
                "llm_content": llm_content,
            }
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
        finally:
            if not task.done():
                task.cancel()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
