"""Async, true-streaming LLM client with bounded retry/backoff.

Yields the same event contract agent_chat_stream consumes:
content_delta / status / message / error.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.llm import (
    AGENT_REQUEST_TIMEOUT,
    REQUEST_TIMEOUT,
    _chat_completions_url,
    _settings,
    is_deepseek_provider,
    resolve_deepseek_thinking,
    sanitize_messages_for_api,
)
from app.pi_stream_parser import assemble_message, consume_stream_chunk, parse_sse_line

RETRYABLE_STATUS = {429, 500, 502, 503, 504}
MAX_RETRIES = 3
_BACKOFF_BASE = 0.5
_BACKOFF_CAP = 20.0


def _next_backoff(attempt: int) -> float:
    raw = _BACKOFF_BASE * (2**attempt)
    return min(_BACKOFF_CAP, raw) + random.uniform(0, _BACKOFF_BASE)


def _retry_after(resp: Any) -> float | None:
    value = resp.headers.get("Retry-After")
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _build_payload(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    *,
    temperature: float,
    tool_choice: Any,
    model: str,
    base_url: str,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "temperature": temperature,
        "messages": sanitize_messages_for_api(messages),
        "stream": True,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = tool_choice if tool_choice is not None else "auto"
    if is_deepseek_provider(model=model, base_url=base_url):
        thinking = resolve_deepseek_thinking(tools=tools)
        if thinking:
            payload["thinking"] = {"type": thinking}
            if thinking == "enabled" and tools:
                payload["reasoning_effort"] = "high"
    return payload


async def stream_chat(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    *,
    temperature: float = 0.2,
    tool_choice: Any = None,
) -> AsyncIterator[dict[str, Any]]:
    api_key, base_url, model = _settings()
    url = _chat_completions_url(base_url)
    payload = _build_payload(
        messages,
        tools,
        temperature=temperature,
        tool_choice=tool_choice,
        model=model,
        base_url=base_url,
    )
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    timeout = httpx.Timeout(AGENT_REQUEST_TIMEOUT if tools else REQUEST_TIMEOUT, connect=15.0)

    last_error = "LLM 请求失败"
    for attempt in range(MAX_RETRIES + 1):
        emitted_any = False
        content_parts: list[str] = []
        reasoning_parts: list[str] = []
        tool_calls: dict[int, dict[str, Any]] = {}
        status_emitted = [False]
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as resp:
                    if resp.status_code in RETRYABLE_STATUS:
                        body = (await resp.aread()).decode("utf-8", "replace")
                        last_error = f"LLM 请求失败 ({resp.status_code}): {body[:200]}"
                        if attempt < MAX_RETRIES:
                            # Cap Retry-After so a hostile/misconfigured header
                            # (e.g. "Retry-After: 3600") cannot hang the turn.
                            delay = _retry_after(resp) or _next_backoff(attempt)
                            await asyncio.sleep(min(delay, _BACKOFF_CAP))
                            continue
                        yield {"type": "error", "message": last_error}
                        return
                    if resp.status_code >= 400:
                        body = (await resp.aread()).decode("utf-8", "replace")
                        yield {
                            "type": "error",
                            "message": f"LLM 请求失败 ({resp.status_code}): {body[:300]}",
                        }
                        return
                    async for line in resp.aiter_lines():
                        chunk = parse_sse_line(line)
                        if chunk is None:
                            continue
                        for event in consume_stream_chunk(
                            chunk,
                            content_parts=content_parts,
                            reasoning_parts=reasoning_parts,
                            tool_calls=tool_calls,
                            emit_content_delta=True,
                            tool_status_emitted=status_emitted,
                        ):
                            emitted_any = True
                            yield event
            yield {
                "type": "message",
                "message": assemble_message(content_parts, reasoning_parts, tool_calls),
            }
            return
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            last_error = f"无法连接 LLM 服务: {exc}"
            if emitted_any:
                yield {"type": "error", "message": last_error}
                return
            if attempt < MAX_RETRIES:
                await asyncio.sleep(_next_backoff(attempt))
                continue
            yield {"type": "error", "message": last_error}
            return

    yield {"type": "error", "message": last_error}
