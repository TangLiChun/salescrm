"""Structural guards for the Pi tool schemas and system prompt.

These lock in the prompt-tuning improvements. They do NOT validate that the
model behaves better (only the live model can) — they prevent regressions in
the schema/prompt structure the model relies on.
"""

from app.agent_chat import AGENT_TOOLS, SYSTEM_PROMPT
from app.pi_tool_calls import KNOWN_TOOL_NAMES, TOOL_NAME_ALIASES, tool_name_aliases


def _tool(name: str) -> dict:
    return next(t["function"] for t in AGENT_TOOLS if t["function"]["name"] == name)


def _tool_names() -> list[str]:
    return [t["function"]["name"] for t in AGENT_TOOLS]


def test_every_tool_is_well_formed():
    for tool in AGENT_TOOLS:
        assert tool.get("type") == "function"
        fn = tool["function"]
        assert fn.get("name"), "tool missing name"
        assert fn.get("description", "").strip(), f"{fn.get('name')} missing description"
        params = fn.get("parameters") or {}
        assert params.get("type") == "object", f"{fn['name']} parameters not an object"
        assert "properties" in params, f"{fn['name']} missing properties"


def test_no_duplicate_tool_names():
    names = _tool_names()
    assert len(names) == len(set(names))


def test_schema_names_match_known_tool_names():
    # Every advertised tool must be a first-class known name (so name
    # normalization/inference treats it correctly), and vice versa.
    assert set(_tool_names()) == set(KNOWN_TOOL_NAMES)


def test_tool_aliases_point_to_advertised_tools():
    assert tool_name_aliases() == TOOL_NAME_ALIASES
    assert TOOL_NAME_ALIASES
    assert set(TOOL_NAME_ALIASES.values()).issubset(set(_tool_names()))


def test_required_params_are_declared_properties():
    for tool in AGENT_TOOLS:
        params = tool["function"]["parameters"]
        props = params.get("properties") or {}
        for req in params.get("required", []):
            assert req in props, f"{tool['function']['name']}: required '{req}' not in properties"


def test_follow_up_status_is_constrained_enum():
    prop = _tool("update_contact")["parameters"]["properties"]["follow_up_status"]
    assert prop["enum"] == ["new", "contacted", "replied", "invalid", "interested"]


def test_import_leads_documents_email_and_asn_rules():
    rows = _tool("import_leads")["parameters"]["properties"]["rows"]
    desc = rows["description"]
    assert "email" in desc
    assert "AS" in desc  # the "no AS prefix" rule for asn
    assert "rows" in _tool("import_leads")["parameters"]["required"]


def test_discover_leads_is_preferred_over_web_search():
    assert "首选" in _tool("discover_leads")["description"]
    web = _tool("web_search")["description"]
    assert "discover_leads" in web  # tells the model not to use web_search instead


def test_key_search_tools_have_param_descriptions():
    assert _tool("discover_leads")["parameters"]["properties"]["query"].get("description")
    assert _tool("lookup_asns")["parameters"]["properties"]["text"].get("description")


def test_system_prompt_front_loads_act_immediately():
    assert "核心行为" in SYSTEM_PROMPT
    assert "立刻调用工具" in SYSTEM_PROMPT
    assert "禁止只回" in SYSTEM_PROMPT
    # The act-immediately rule must come before the capability/selection details.
    assert SYSTEM_PROMPT.index("核心行为") < SYSTEM_PROMPT.index("选哪个工具")


def test_system_prompt_keeps_critical_data_rules():
    assert "纯数字" in SYSTEM_PROMPT  # asn must be digits
    assert "并行" in SYSTEM_PROMPT  # batch tool calls
    assert "list_contacts" in SYSTEM_PROMPT  # dedupe-before-import guidance
