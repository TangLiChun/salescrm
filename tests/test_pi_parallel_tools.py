from app.pi_parallel_tools import PARALLEL_SAFE_TOOLS, can_parallelize_tool_batch


def test_can_parallelize_read_only_batch():
    assert can_parallelize_tool_batch(["get_import_filters", "get_search_config"])
    assert can_parallelize_tool_batch(["list_contacts", "get_stats"])


def test_cannot_parallelize_mixed_or_write_tools():
    assert not can_parallelize_tool_batch(["get_import_filters", "update_import_filters"])
    assert not can_parallelize_tool_batch(["list_contacts", "discover_leads"])
    assert not can_parallelize_tool_batch(["get_stats"])


def test_parallel_safe_tools_are_known_read_only():
    assert "discover_leads" not in PARALLEL_SAFE_TOOLS
    assert "update_import_filters" not in PARALLEL_SAFE_TOOLS
