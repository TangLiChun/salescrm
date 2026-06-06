"""Pure turn-decision logic for the Pi agent loop.

Given one LLM turn's result, decide what the driver should do next. No I/O.
Mirrors the branching previously inlined in agent_chat_stream (lines 1501-1674).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.pi_reply_heuristics import (
    _CONTINUE_NUDGE,
    _EMPTY_RESPONSE_NUDGE,
    _INTRO_ONLY_NUDGE,
    _assistant_promises_tool_use,
    _fallback_prepared_calls,
    _meaningful_assistant_content,
    _parse_inline_tool_calls,
    _user_requests_continuation,
)
from app.pi_tool_calls import _extract_tool_calls_from_content, _prepare_tool_calls

PreparedCall = tuple[dict[str, Any], str, dict[str, Any]]


@dataclass
class EmitToolCalls:
    prepared_calls: list[PreparedCall]
    intro_text: str = ""


@dataclass
class FinalReply:
    text: str


@dataclass
class Retry:
    nudge: str
    reason: str


@dataclass
class FallbackToolCalls:
    prepared_calls: list[PreparedCall]
    status_message: str


@dataclass
class Fail:
    error: str = "模型未返回有效回复，请换种说法或检查 LLM 配置"


Decision = EmitToolCalls | FinalReply | Retry | FallbackToolCalls | Fail


def _assistant_response_empty(assistant: dict[str, Any] | None, content_buffer: str) -> bool:
    """Mirror agent_chat.py _assistant_response_empty (lines 863-871)."""
    if not assistant:
        return True
    content = (assistant.get("content") or content_buffer or "").strip()
    tool_calls = assistant.get("tool_calls") or []
    if content or tool_calls:
        return False
    reasoning = str(assistant.get("reasoning_content") or "").strip()
    return not reasoning


def decide_turn(
    assistant: dict[str, Any] | None,
    content_buffer: str,
    *,
    user_message: str,
    history: list[dict[str, Any]],
    nudge_count: int,
    max_nudges: int,
) -> Decision:
    """Encode the branching of the agent_chat_stream inner while True: (lines 1501-1674).

    Parameters
    ----------
    assistant:
        The assembled assistant message dict from the LLM (may be None if stream
        ended without a "message" event).
    content_buffer:
        Accumulated text from content_delta events (fallback when assistant.content
        is None).
    user_message:
        The original user turn text (used for continuation heuristics and fallback).
    history:
        Conversation history entries before the current turn (for fallback query
        inference).
    nudge_count:
        How many nudge retries have already been issued in this turn's while loop.
        Corresponds to llm_nudge_count in the real loop, plus nudged_empty_response
        for the empty-response path.
    max_nudges:
        Maximum retries before giving up / falling back (_MAX_LLM_NUDGES = 2).
    """
    # -----------------------------------------------------------------------
    # Path 1: Empty response (agent_chat.py lines 1539-1547)
    # In the real loop, nudged_empty_response (a bool) is a separate counter from
    # llm_nudge_count. For decide_turn, we unify them: the caller uses nudge_count=0
    # for the first attempt and nudge_count>=max_nudges to signal exhaustion.
    # -----------------------------------------------------------------------
    if _assistant_response_empty(assistant, content_buffer):
        if nudge_count < max_nudges:
            return Retry(_EMPTY_RESPONSE_NUDGE, "empty_response")
        return Fail()

    assistant = assistant or {}
    raw_tool_calls: list[Any] = assistant.get("tool_calls") or []
    raw_content = (assistant.get("content") or content_buffer or "").strip()
    content = _meaningful_assistant_content(raw_content)

    # -----------------------------------------------------------------------
    # Path 2: Inline tool calls found in content (lines 1553-1562)
    # If the LLM returned no structured tool_calls but embedded them in text,
    # parse and treat as real tool calls.
    # -----------------------------------------------------------------------
    if not raw_tool_calls and raw_content:
        intro, inline_calls = _parse_inline_tool_calls(raw_content)
        if inline_calls:
            # Fall through with the resolved inline calls (mirrors the loop
            # setting tool_calls = inline_calls and continuing to the tool
            # processing block below).
            raw_tool_calls = inline_calls
            content = _meaningful_assistant_content(intro)

    # -----------------------------------------------------------------------
    # Path 3: Content present, no tool calls (lines 1564-1599)
    # -----------------------------------------------------------------------
    if content and not raw_tool_calls:
        continue_request = _user_requests_continuation(user_message)
        promises = _assistant_promises_tool_use(content)
        should_act = promises or continue_request

        if should_act and nudge_count < max_nudges:
            nudge = _CONTINUE_NUDGE if continue_request else _INTRO_ONLY_NUDGE
            return Retry(nudge, "continuation" if continue_request else "intro_only")

        fallback_calls = _fallback_prepared_calls(user_message, history)
        if fallback_calls and should_act:
            status_msg = (
                "正在直接继续上一任务…" if continue_request else "模型未调用工具，正在直接搜索 CRM…"
            )
            return FallbackToolCalls(fallback_calls, status_msg)

        if continue_request:
            # Real loop: yield error "无法继续上一任务，请补充更具体的搜索描述" (line 1591)
            return Fail("无法继续上一任务，请补充更具体的搜索描述")

        return FinalReply(content)

    # -----------------------------------------------------------------------
    # Path 4: No tool calls AND no meaningful content (lines 1601-1609)
    # -----------------------------------------------------------------------
    if not raw_tool_calls:
        if nudge_count < max_nudges:
            return Retry(_EMPTY_RESPONSE_NUDGE, "no_visible_content")
        return Fail()

    # -----------------------------------------------------------------------
    # Path 5: Tool calls present — prepare and validate (lines 1611-1674)
    # -----------------------------------------------------------------------
    prepared = _prepare_tool_calls(raw_tool_calls)

    if not prepared and raw_content:
        # Try extracting from content (lines 1612-1620)
        extracted = _extract_tool_calls_from_content(raw_content)
        if extracted:
            prepared = _prepare_tool_calls(extracted)
        if not prepared:
            # Try inline parse as final fallback within this block
            intro2, inline2 = _parse_inline_tool_calls(raw_content)
            if inline2:
                prepared = _prepare_tool_calls(inline2)
                content = _meaningful_assistant_content(intro2)

    if prepared:
        return EmitToolCalls(prepared, content)

    # Not prepared (lines 1621-1673)
    # In this branch attempted_tools = True (we had raw_tool_calls).
    # "if content and not attempted_tools" block (lines 1623-1646) never fires here.
    # So we go straight to the nudge / fallback / fail logic (lines 1647-1673).
    if nudge_count < max_nudges:
        return Retry(_EMPTY_RESPONSE_NUDGE, "invalid_tool_calls")

    fallback_calls = _fallback_prepared_calls(user_message, history)
    # Condition at lines 1658-1661: fallback AND (attempted_tools OR promises OR continue_request)
    # attempted_tools is always True here, so the condition simplifies to bool(fallback_calls).
    if fallback_calls:
        return FallbackToolCalls(fallback_calls, "工具调用无效，正在直接搜索 CRM…")

    return Fail()
