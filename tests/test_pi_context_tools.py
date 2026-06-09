"""Compact LLM payloads for Pi tool results."""

from __future__ import annotations

import json

from app.pi_context import compress_tool_result_for_llm


def _parsed(text: str) -> dict:
    return json.loads(text)


def test_compress_update_import_filters_is_compact_not_full_blocklist() -> None:
    blocklist_patterns = [f"spam{i}.com" for i in range(50)]
    allowlist_patterns = [f"good{i}.org" for i in range(20)]
    result = {
        "blocklist": "\n".join(blocklist_patterns),
        "allowlist": "trusted.example",
        "blocklist_patterns": blocklist_patterns,
        "allowlist_patterns": allowlist_patterns,
        "ok": True,
        "message": "导入过滤规则已更新",
    }

    compressed = compress_tool_result_for_llm("update_import_filters", result)
    payload = _parsed(compressed)

    assert len(compressed) < 1200
    assert payload["ok"] is True
    assert payload["message"] == "导入过滤规则已更新"
    assert payload["blocklist_count"] == 50
    assert payload["allowlist_count"] == 20
    assert len(payload["blocklist_sample"]) == 12
    assert payload["blocklist_omitted"] == 38
    assert "spam49.com" not in compressed
    assert result["blocklist"] not in compressed


def test_compress_list_schedules_preview_truncates_query() -> None:
    long_query = "asn:64512 " + ("hosting " * 40)
    schedules = [
        {
            "id": 1,
            "name": "Nightly scan",
            "enabled": True,
            "query": long_query,
            "interval_minutes": 360,
        },
        {
            "id": 2,
            "name": "Weekend",
            "enabled": False,
            "query": "org:Example ISP",
        },
    ]
    result = {"schedules": schedules, "count": len(schedules)}

    compressed = compress_tool_result_for_llm("list_schedules", result)
    payload = _parsed(compressed)

    assert len(compressed) < 800
    assert payload["count"] == 2
    assert len(payload["schedules_preview"]) == 2
    first = payload["schedules_preview"][0]
    assert first["id"] == 1
    assert first["name"] == "Nightly scan"
    assert first["enabled"] is True
    assert len(first["query"]) <= 121
    assert first["query"].endswith("…")
    assert long_query not in compressed
    assert "interval_minutes" not in compressed
