from app.pi_tool_calls import (
    _extract_tool_calls_from_content,
    _infer_tool_name,
    _parse_tool_call,
    _prepare_tool_calls,
)


def test_infer_tool_name_from_aliases():
    assert _infer_tool_name("search_contacts", {}) == "list_contacts"
    assert _infer_tool_name("functions.list_contacts", {}) == "list_contacts"


def test_infer_tool_name_from_args_shape():
    assert _infer_tool_name("", {"rows": []}) == "import_leads"
    assert _infer_tool_name("", {"text": "AS123"}) == "lookup_asns"
    assert _infer_tool_name("", {"contact_id": 5, "auto_import": True}) == "enrich_contact"


def test_parse_tool_call_valid():
    parsed = _parse_tool_call({"function": {"name": "list_contacts", "arguments": '{"q": "isp"}'}})
    assert parsed == ("list_contacts", {"q": "isp"})


def test_parse_tool_call_empty_name_no_args_returns_none():
    # A truly unresolvable call: empty name and empty args → "unknown" → None
    assert _parse_tool_call({"function": {"name": "", "arguments": "{}"}}) is None


def test_parse_tool_call_nested_json_in_arguments():
    parsed = _parse_tool_call(
        {
            "function": {
                "name": "",
                "arguments": '{"name": "list_contacts", "arguments": {"q": "x"}}',
            }
        }
    )
    assert parsed == ("list_contacts", {"q": "x"})


def test_prepare_tool_calls_drops_invalid_keeps_valid():
    prepared = _prepare_tool_calls(
        [
            {"function": {"name": "list_contacts", "arguments": '{"q": "a"}'}},
            {"function": {"name": "", "arguments": "{}"}},  # empty name+args → dropped
            "not-a-dict",
        ]
    )
    names = [name for _, name, _ in prepared]
    assert names == ["list_contacts"]
    assert prepared[0][0]["id"]  # id ensured


def test_extract_tool_calls_from_content_json_array():
    text = 'sure: [{"name": "list_contacts", "arguments": {"q": "isp"}}]'
    calls = _extract_tool_calls_from_content(text)
    assert calls[0]["function"]["name"] == "list_contacts"
