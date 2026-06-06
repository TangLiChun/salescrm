"""Deterministic tests for the live-eval scoring logic (no network).

The live run in scripts/pi_agent_harness.py needs a real LLM, but its scoring
function must itself be correct — these tests pin that with synthetic event
streams shaped like real agent_chat_stream output.
"""

import json

from app.pi_harness import (
    SCENARIOS,
    Scenario,
    load_scenarios_from_file,
    result_record,
    scenario_from_dict,
    score_run,
)
from scripts.pi_agent_harness import build_summary


def _tool_start(name, args=None):
    return {"type": "tool_start", "name": name, "args": args or {}}


_RETRY = {"type": "status", "message": "模型未调用工具，正在重试…"}
_DONE = {"type": "done"}


def test_perfect_run_passes():
    scenario = Scenario(
        name="x",
        message="m",
        expect_tools={"discover_leads"},
        forbid_tools={"web_search"},
    )
    events = [_tool_start("discover_leads", {"query": "isp"}), _DONE]
    r = score_run(events, scenario)
    assert r.passed
    assert r.first_tool == "discover_leads"
    assert r.acted_immediately and r.selected_expected and r.avoided_forbidden


def test_wrong_tool_fails_selection():
    scenario = Scenario("x", "m", expect_tools={"discover_leads"}, forbid_tools={"web_search"})
    events = [_tool_start("web_search", {"query": "isp"}), _DONE]
    r = score_run(events, scenario)
    assert not r.selected_expected
    assert not r.avoided_forbidden
    assert not r.passed


def test_retry_before_first_tool_marks_not_immediate():
    scenario = Scenario("x", "m", expect_tools={"list_contacts"})
    events = [_RETRY, _tool_start("list_contacts", {"q": "google"}), _DONE]
    r = score_run(events, scenario)
    assert r.selected_expected
    assert not r.acted_immediately
    assert r.retries == 1
    assert not r.passed  # immediacy is part of passing


def test_no_tool_call_fails():
    scenario = Scenario("x", "m", expect_tools={"list_contacts"})
    events = [{"type": "assistant_done", "text": "让我查一下"}, _DONE]
    r = score_run(events, scenario)
    assert r.first_tool is None
    assert not r.selected_expected
    assert r.lonely_intro
    assert not r.passed


def test_arg_check_runs_against_expected_tool():
    def _status_ok(_name, args):
        return args.get("follow_up_status") in {"contacted", "replied"}

    scenario = Scenario("x", "m", expect_tools={"update_contact"}, arg_check=_status_ok)

    good = [
        _tool_start("update_contact", {"contact_id": 5, "follow_up_status": "contacted"}),
        _DONE,
    ]
    bad = [_tool_start("update_contact", {"contact_id": 5, "follow_up_status": "已联系"}), _DONE]

    assert score_run(good, scenario).args_ok
    assert not score_run(bad, scenario).args_ok


def test_arg_check_with_no_matching_tool_is_not_ok():
    scenario = Scenario("x", "m", expect_tools={"update_contact"}, arg_check=lambda n, a: True)
    events = [_tool_start("list_contacts", {"q": "x"}), _DONE]
    r = score_run(events, scenario)
    assert not r.args_ok  # no expected-tool call to validate


def test_either_expected_tool_accepted():
    scenario = Scenario("x", "m", expect_tools={"lookup_asns", "discover_leads"})
    events = [_tool_start("lookup_asns", {"text": "AS15169 13335"}), _DONE]
    assert score_run(events, scenario).selected_expected


def test_builtin_asn_scenario_requires_lookup_only():
    scenario = next(s for s in SCENARIOS if s.name == "asn-roleemail-lookup")
    assert scenario.expect_tools == {"lookup_asns"}
    assert {"discover_leads", "web_search"} <= scenario.forbid_tools
    assert score_run(
        [_tool_start("discover_leads", {"query": "AS15169 role"})], scenario
    ).failure_reasons


def test_error_without_done_fails_cleanliness():
    scenario = Scenario("x", "m", expect_tools={"list_contacts"})
    events = [{"type": "error", "message": "LLM 请求失败"}]
    r = score_run(events, scenario)
    assert r.had_error
    assert not r.stopped_cleanly
    assert "stream_did_not_end_with_done" in r.failure_reasons
    assert not r.passed


def test_blocked_tools_are_reported_without_counting_as_executed():
    scenario = Scenario("x", "m", expect_tools={"discover_leads"}, forbid_tools={"web_search"})
    events = [
        _tool_start("discover_leads", {"query": "isp"}),
        {"type": "tool_blocked", "name": "web_search", "reason": "discover_leads 已覆盖"},
        _DONE,
    ]
    r = score_run(events, scenario)
    assert not r.passed
    assert r.blocked_tools == ["web_search"]
    assert r.all_tools == ["discover_leads"]
    assert "blocked_tool_attempted=['web_search']" in r.failure_reasons


def test_blocked_tools_can_be_allowed_for_diagnostic_scenarios():
    scenario = Scenario(
        "x",
        "m",
        expect_tools={"discover_leads"},
        forbid_tools={"web_search"},
        fail_on_blocked_tools=False,
    )
    events = [
        _tool_start("discover_leads", {"query": "isp"}),
        {"type": "tool_blocked", "name": "web_search", "reason": "discover_leads 已覆盖"},
        _DONE,
    ]
    r = score_run(events, scenario)
    assert r.passed
    assert r.blocked_tools == ["web_search"]


def test_retry_budget_can_be_relaxed_per_scenario():
    scenario = Scenario(
        "x",
        "m",
        expect_tools={"list_contacts"},
        max_retries=1,
        require_immediate=False,
    )
    events = [_RETRY, _tool_start("list_contacts", {"q": "google"}), _DONE]
    r = score_run(events, scenario)
    assert "retry_budget_exceeded=1>0" not in r.failure_reasons
    assert "needed_retry_before_first_tool" not in r.failure_reasons
    assert r.passed


def test_result_record_is_json_serializable():
    scenario = Scenario("x", "m", expect_tools={"list_contacts"})
    events = [_tool_start("list_contacts", {"q": "google"}), _DONE]
    record = result_record(scenario, score_run(events, scenario), events, run={"index": 1})
    encoded = json.dumps(record, ensure_ascii=False)
    assert '"passed": true' in encoded
    assert record["run"]["index"] == 1


def test_scenario_from_dict_uses_named_arg_check():
    scenario = scenario_from_dict(
        {
            "name": "custom",
            "message": "查 ASN 15169",
            "expect_tools": ["lookup_asns"],
            "arg_check": "asn_text",
            "require_immediate": "false",
            "fail_on_blocked_tools": "false",
            "max_retries": 1,
        }
    )
    assert scenario.name == "custom"
    assert scenario.arg_check is not None
    assert not scenario.require_immediate
    assert not scenario.fail_on_blocked_tools
    assert scenario.max_retries == 1
    assert score_run([_tool_start("lookup_asns", {"text": "AS15169"}), _DONE], scenario).passed


def test_load_scenarios_from_file(tmp_path):
    path = tmp_path / "scenarios.json"
    path.write_text(
        json.dumps(
            {
                "scenarios": [
                    {
                        "name": "from-file",
                        "message": "列出 Google 联系人",
                        "expect_tools": ["list_contacts"],
                        "arg_check": "list_contacts_non_empty",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    scenarios = load_scenarios_from_file(path)
    assert len(scenarios) == 1
    assert scenarios[0].name == "from-file"


def test_build_summary_extracts_failures():
    good = result_record(
        Scenario("good", "m", expect_tools={"list_contacts"}),
        score_run(
            [_tool_start("list_contacts", {"q": "x"}), _DONE],
            Scenario("good", "m", expect_tools={"list_contacts"}),
        ),
        [_tool_start("list_contacts", {"q": "x"}), _DONE],
    )
    bad_scenario = Scenario("bad", "m", expect_tools={"discover_leads"})
    bad = result_record(
        bad_scenario,
        score_run([_tool_start("web_search", {"query": "x"}), _DONE], bad_scenario),
        [_tool_start("web_search", {"query": "x"}), _DONE],
    )
    summary = build_summary([good, bad])
    assert summary["total"] == 2
    assert summary["failed"] == 1
    assert summary["failures"][0]["name"] == "bad"
    assert summary["failures"][0]["blocked_tools"] == []
