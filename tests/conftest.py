"""Shared test fixtures and async helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def stub_agent_settings(monkeypatch):
    """Stop agent_chat_stream from reading settings out of Postgres in tests.

    agent_chat_stream calls get_setting("llm_model", "") for its context-usage
    meter even when thread_id is None, which would hit the DB. Integration tests
    inject FakeLLM/fake tool_runner and must stay DB-free, so we return defaults.
    Harmless for unit tests that never call it.
    """
    try:
        import app.agent_chat  # noqa: F401
    except Exception:
        return
    monkeypatch.setattr("app.agent_chat.get_setting", lambda key, default="": default)


async def collect_events(stream: AsyncIterator[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drain an agent event stream into a list for assertions."""
    events: list[dict[str, Any]] = []
    async for event in stream:
        events.append(event)
    return events


def event_types(events: list[dict[str, Any]]) -> list[str]:
    return [str(e.get("type")) for e in events]


def assistant_text(events: list[dict[str, Any]]) -> str:
    """Concatenate all assistant_done texts (final visible reply)."""
    return "".join(str(e.get("text") or "") for e in events if e.get("type") == "assistant_done")
