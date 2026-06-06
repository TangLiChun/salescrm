"""A scriptable stand-in for the streaming LLM client used by agent_chat_stream.

Each element passed to FakeLLM is one *response* (a list of event dicts) returned
on successive calls, mirroring app.agent_chat._iter_llm_stream's event contract:
content_delta / status / message / error.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any


def tool_call(name: str, arguments: dict[str, Any], call_id: str | None = None) -> dict[str, Any]:
    return {
        "id": call_id or f"call_{name}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
    }


def content_message(
    text: str = "",
    *,
    tool_calls: list[dict[str, Any]] | None = None,
    reasoning: str | None = None,
    stream_text: bool = True,
) -> list[dict[str, Any]]:
    """Build one scripted response: optional streamed content + final message event."""
    events: list[dict[str, Any]] = []
    if text and stream_text:
        events.append({"type": "content_delta", "text": text})
    message: dict[str, Any] = {"role": "assistant", "content": text or None}
    if reasoning:
        message["reasoning_content"] = reasoning
    if tool_calls:
        message["tool_calls"] = tool_calls
    events.append({"type": "message", "message": message})
    return events


def error_response(message: str) -> list[dict[str, Any]]:
    return [{"type": "error", "message": message}]


class FakeLLM:
    """Callable matching agent_chat's injected llm_client signature."""

    def __init__(self, responses: list[list[dict[str, Any]]]) -> None:
        self._responses = list(responses)
        self._index = 0
        self.calls: list[dict[str, Any]] = []

    def __call__(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        *,
        tool_choice: Any = None,
    ) -> AsyncIterator[dict[str, Any]]:
        self.calls.append({"messages": messages, "tools": tools, "tool_choice": tool_choice})
        assert self._index < len(self._responses), "FakeLLM ran out of scripted responses"
        response = self._responses[self._index]
        self._index += 1

        async def _gen() -> AsyncIterator[dict[str, Any]]:
            for event in response:
                yield event

        return _gen()
