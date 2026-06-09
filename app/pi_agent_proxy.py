"""Proxy Pi agent chat stream to the TypeScript pi-agent sidecar."""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx


def pi_agent_service_url() -> str:
    return os.environ.get("PI_AGENT_SERVICE_URL", "").strip().rstrip("/")


def pi_internal_secret() -> str:
    return os.environ.get("PI_INTERNAL_SECRET", "").strip()


def sanitize_agent_history(history: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    for item in history or []:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        if role in ("user", "assistant"):
            content = str(item.get("content") or "").strip()
            if content:
                cleaned.append({"role": role, "content": content})
        elif role == "tool":
            name = str(item.get("name") or "").strip()
            summary = str(item.get("summary") or "").strip()
            if name and summary:
                cleaned.append({"role": "tool", "name": name, "summary": summary})
    return cleaned


async def stream_pi_agent_events(
    user_id: int,
    message: str,
    *,
    thread_id: str | None = None,
    history: list[dict[str, Any]] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    url = f"{pi_agent_service_url()}/stream"
    secret = pi_internal_secret()
    if not secret:
        yield {"type": "error", "message": "Pi agent 服务未配置 PI_INTERNAL_SECRET"}
        yield {"type": "done"}
        return

    payload = {
        "user_id": user_id,
        "message": message,
        "thread_id": thread_id,
        "history": sanitize_agent_history(history),
    }
    check = cancel_check or (lambda: False)
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "POST",
            url,
            json=payload,
            headers={"X-Internal-Secret": secret},
        ) as resp:
            if resp.status_code >= 400:
                detail = (await resp.aread()).decode("utf-8", "replace")[:300]
                yield {
                    "type": "error",
                    "message": f"Pi agent 服务错误 ({resp.status_code}): {detail}",
                }
                yield {"type": "done"}
                return
            async for line in resp.aiter_lines():
                if check():
                    yield {"type": "error", "message": "任务已停止"}
                    yield {"type": "done"}
                    return
                stripped = line.strip()
                if not stripped.startswith("data:"):
                    continue
                payload_line = stripped[5:].strip()
                if not payload_line:
                    continue
                try:
                    event = json.loads(payload_line)
                except json.JSONDecodeError:
                    continue
                yield event
                if event.get("type") == "done":
                    return
