"""Deterministic tests for the live-eval scoring logic (no network).

The live run in scripts/eval_pi_prompt.py needs a real LLM, but its scoring
function must itself be correct — these tests pin that with synthetic event
streams shaped like real agent_chat_stream output.
"""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from scripts.eval_pi_prompt import Scenario, score_run  # noqa: E402


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
