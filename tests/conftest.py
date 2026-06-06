"""Shared test fixtures and async helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any


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
