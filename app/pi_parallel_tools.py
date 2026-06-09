"""Read-only Pi tools safe to execute in parallel within one LLM turn."""

from __future__ import annotations

PARALLEL_SAFE_TOOLS: frozenset[str] = frozenset(
    {
        "list_contacts",
        "get_contact",
        "get_stats",
        "list_contact_notes",
        "get_lead_preferences",
        "get_import_filters",
        "get_search_config",
        "list_schedules",
    }
)


def can_parallelize_tool_batch(names: list[str]) -> bool:
    if len(names) < 2:
        return False
    return all(name in PARALLEL_SAFE_TOOLS for name in names)
