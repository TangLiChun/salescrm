"""Pure SSE / streaming-chunk parsing for the LLM clients."""

from __future__ import annotations

import json
from typing import Any


def merge_tool_call_delta(
    tool_calls: dict[int, dict[str, Any]],
    tool_delta: dict[str, Any],
) -> None:
    index = int(tool_delta.get("index") or 0)
    slot = tool_calls.setdefault(
        index,
        {
            "id": "",
            "type": "function",
            "function": {"name": "", "arguments": ""},
        },
    )
    if tool_delta.get("id"):
        slot["id"] = tool_delta["id"]
    fn = tool_delta.get("function")
    if isinstance(fn, str):
        try:
            fn = json.loads(fn)
        except json.JSONDecodeError:
            fn = {}
    if not isinstance(fn, dict):
        fn = {}
    if fn.get("name"):
        slot["function"]["name"] += str(fn["name"])
    elif tool_delta.get("name"):
        slot["function"]["name"] += str(tool_delta["name"])
    if fn.get("arguments"):
        slot["function"]["arguments"] += str(fn["arguments"])
    elif tool_delta.get("arguments"):
        piece = tool_delta["arguments"]
        slot["function"]["arguments"] += (
            piece if isinstance(piece, str) else json.dumps(piece, ensure_ascii=False)
        )


def apply_complete_message(
    *,
    content_parts: list[str],
    reasoning_parts: list[str],
    tool_calls: dict[int, dict[str, Any]],
    message: dict[str, Any],
) -> None:
    content = message.get("content")
    if content:
        full = str(content)
        joined = "".join(content_parts)
        if not joined:
            content_parts.append(full)
        elif len(full) > len(joined):
            content_parts[:] = [full]

    reasoning = message.get("reasoning_content") or message.get("reasoning")
    if reasoning:
        full_reasoning = str(reasoning)
        joined_reasoning = "".join(reasoning_parts)
        if not joined_reasoning:
            reasoning_parts.append(full_reasoning)
        elif len(full_reasoning) > len(joined_reasoning):
            reasoning_parts[:] = [full_reasoning]

    for index, raw in enumerate(message.get("tool_calls") or []):
        if not isinstance(raw, dict):
            continue
        slot = tool_calls.setdefault(
            index,
            {
                "id": "",
                "type": "function",
                "function": {"name": "", "arguments": ""},
            },
        )
        if raw.get("id"):
            slot["id"] = raw["id"]
        fn = raw.get("function")
        if isinstance(fn, dict):
            if fn.get("name"):
                slot["function"]["name"] = str(fn["name"])
            args = fn.get("arguments")
            if args is not None:
                slot["function"]["arguments"] = (
                    args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)
                )


def parse_sse_or_json_lines(raw_body: bytes) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    text = raw_body.decode("utf-8", errors="replace")
    for line in text.splitlines():
        line = line.strip()
        if not line or line == "data: [DONE]":
            continue
        payload = line[5:].strip() if line.startswith("data:") else line
        if not payload or payload == "[DONE]":
            continue
        try:
            chunks.append(json.loads(payload))
        except json.JSONDecodeError:
            continue
    if chunks:
        return chunks
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, dict):
        return [parsed]
    return []


def consume_stream_chunk(
    chunk: dict[str, Any],
    *,
    content_parts: list[str],
    reasoning_parts: list[str],
    tool_calls: dict[int, dict[str, Any]],
    emit_content_delta: bool,
    tool_status_emitted: list[bool],
    finish_reasons: list[str] | None = None,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for choice in chunk.get("choices") or [{}]:
        finish_reason = choice.get("finish_reason")
        if finish_reason is not None and finish_reasons is not None:
            finish_reasons.append(str(finish_reason))
        delta = choice.get("delta") or {}
        piece = delta.get("content")
        if piece:
            content_parts.append(str(piece))
            if emit_content_delta:
                events.append({"type": "content_delta", "text": str(piece)})

        reasoning_piece = delta.get("reasoning_content") or delta.get("reasoning")
        if reasoning_piece:
            reasoning_parts.append(str(reasoning_piece))
            if not tool_status_emitted[0] and not content_parts:
                tool_status_emitted[0] = True
                events.append({"type": "status", "message": "模型推理中…"})

        for tool_delta in delta.get("tool_calls") or []:
            if isinstance(tool_delta, dict):
                if not tool_status_emitted[0]:
                    tool_status_emitted[0] = True
                    events.append({"type": "status", "message": "正在准备工具调用…"})
                merge_tool_call_delta(tool_calls, tool_delta)

        message = choice.get("message")
        if isinstance(message, dict):
            apply_complete_message(
                content_parts=content_parts,
                reasoning_parts=reasoning_parts,
                tool_calls=tool_calls,
                message=message,
            )
    return events


def parse_sse_line(line: str) -> dict[str, Any] | None:
    """Parse one SSE/JSONL line into a chunk dict, or None to skip."""
    line = (line or "").strip()
    if not line or line == "data: [DONE]":
        return None
    payload = line[5:].strip() if line.startswith("data:") else line
    if not payload or payload == "[DONE]":
        return None
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def assemble_message(
    content_parts: list[str],
    reasoning_parts: list[str],
    tool_calls: dict[int, dict[str, Any]],
    finish_reasons: list[str] | None = None,
) -> dict[str, Any]:
    """Assemble the final assistant message from accumulated stream state."""
    import uuid

    message: dict[str, Any] = {"role": "assistant", "content": "".join(content_parts) or None}
    if finish_reasons:
        message["finish_reason"] = finish_reasons[-1]
    if reasoning_parts:
        message["reasoning_content"] = "".join(reasoning_parts)
    assembled: list[dict[str, Any]] = []
    for index in sorted(tool_calls):
        slot = tool_calls[index]
        fn = slot.get("function") or {}
        name = (fn.get("name") or "").strip()
        args = (fn.get("arguments") or "").strip()
        if not name and not args:
            continue
        if not slot.get("id"):
            slot["id"] = f"call_{uuid.uuid4().hex[:12]}"
        assembled.append(slot)
    if assembled:
        message["tool_calls"] = assembled
    return message
