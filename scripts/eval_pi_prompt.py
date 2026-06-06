#!/usr/bin/env python3
"""Live evaluation of Pi's tool-calling behavior against the real LLM.

This measures whether the system prompt + tool schemas make the model pick the
RIGHT tool, fill VALID args, and ACT immediately (instead of stalling on an
intro-only reply). It drives `agent_chat_stream` with the real LLM client but a
FAKE tool_runner, so the model's decisions are exercised without executing any
real tool (no RDAP/PeeringDB/web/DB side effects, no contact imports).

Usage (needs a DeepSeek-compatible key):

    PI_LIVE_LLM=1 \
    LLM_API_KEY=sk-... \
    LLM_BASE_URL=https://api.deepseek.com \
    LLM_MODEL=deepseek-chat \
    .venv/bin/python scripts/eval_pi_prompt.py

Without PI_LIVE_LLM=1 it prints how to run and exits 0 (so it never hits the
network by accident). Run it before and after a prompt change to compare.

The scoring logic (`score_run`) is pure and unit-tested in
tests/test_eval_harness.py — only the live run needs the network/key.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

VALID_FOLLOW_UP = {"new", "contacted", "replied", "invalid", "interested"}


@dataclass
class Scenario:
    name: str
    message: str
    expect_tools: set[str]
    forbid_tools: set[str] = field(default_factory=set)
    # (tool_name, args) -> bool; checked against the first call to an expected tool.
    arg_check: Callable[[str, dict[str, Any]], bool] | None = None


@dataclass
class ScenarioResult:
    name: str
    first_tool: str | None
    all_tools: list[str]
    retries: int
    acted_immediately: bool
    selected_expected: bool
    avoided_forbidden: bool
    args_ok: bool

    @property
    def passed(self) -> bool:
        return (
            self.selected_expected
            and self.avoided_forbidden
            and self.args_ok
            and self.acted_immediately
        )


def score_run(events: list[dict[str, Any]], scenario: Scenario) -> ScenarioResult:
    """Pure scoring of one agent event stream against a scenario's expectations."""
    tool_starts: list[tuple[str, dict[str, Any]]] = [
        (str(e.get("name")), e.get("args") or {}) for e in events if e.get("type") == "tool_start"
    ]
    all_tools = [name for name, _ in tool_starts]
    first_tool = all_tools[0] if all_tools else None

    # "Acted immediately" = the model did not need a retry nudge before its first
    # tool call (the loop emits a 正在重试 status whenever it re-prompts).
    acted_immediately = True
    retries = 0
    for event in events:
        if event.get("type") == "tool_start":
            break
        if event.get("type") == "status" and "重试" in str(event.get("message") or ""):
            acted_immediately = False
    retries = sum(
        1 for e in events if e.get("type") == "status" and "重试" in str(e.get("message") or "")
    )

    selected_expected = (first_tool in scenario.expect_tools) if scenario.expect_tools else True
    avoided_forbidden = not (set(all_tools) & scenario.forbid_tools)

    args_ok = True
    if scenario.arg_check is not None:
        candidates = [
            (n, a)
            for n, a in tool_starts
            if not scenario.expect_tools or n in scenario.expect_tools
        ]
        args_ok = any(scenario.arg_check(n, a) for n, a in candidates) if candidates else False

    return ScenarioResult(
        name=scenario.name,
        first_tool=first_tool,
        all_tools=all_tools,
        retries=retries,
        acted_immediately=acted_immediately,
        selected_expected=selected_expected,
        avoided_forbidden=avoided_forbidden,
        args_ok=args_ok,
    )


def _asn_text_ok(_name: str, args: dict[str, Any]) -> bool:
    text = str(args.get("text") or args.get("query") or "")
    return any(ch.isdigit() for ch in text)


def _list_contacts_ok(_name: str, args: dict[str, Any]) -> bool:
    return bool(str(args.get("q") or "").strip())


def _status_ok(_name: str, args: dict[str, Any]) -> bool:
    return str(args.get("follow_up_status") or "") in VALID_FOLLOW_UP


SCENARIOS: list[Scenario] = [
    Scenario(
        name="peering-leads-uses-discover",
        message="帮我找美国中型 ISP 的 peering 和 NOC 联系人",
        expect_tools={"discover_leads"},
        forbid_tools={"web_search"},
    ),
    Scenario(
        name="asn-roleemail-lookup",
        message="查这几个 ASN 的 role 邮箱：AS15169, 13335, AS3356",
        expect_tools={"lookup_asns", "discover_leads"},
        arg_check=_asn_text_ok,
    ),
    Scenario(
        name="search-crm-immediately",
        message="列出库里所有 Google 相关的联系人",
        expect_tools={"list_contacts"},
        arg_check=_list_contacts_ok,
    ),
    Scenario(
        name="update-status-valid-enum",
        message="把联系人 #5 标记为已联系",
        expect_tools={"update_contact"},
        arg_check=_status_ok,
    ),
]


def _configure_settings_from_env() -> None:
    """Patch get_setting in the modules that read it, sourcing from env vars.

    Lets the eval run without a populated DB — just export LLM_API_KEY etc.
    Falls back to the real (DB-backed) get_setting for any key not in env.
    """
    import app.agent_chat as ac
    import app.llm as llm

    real_get_setting = llm.get_setting
    overrides = {
        "llm_api_key": os.getenv("LLM_API_KEY", ""),
        "llm_base_url": os.getenv("LLM_BASE_URL", ""),
        "llm_model": os.getenv("LLM_MODEL", ""),
    }

    def _get_setting(key: str, default: str = "") -> str:
        val = overrides.get(key, "")
        if val:
            return val
        try:
            return real_get_setting(key, default)
        except Exception:
            return default

    llm.get_setting = _get_setting
    ac.get_setting = _get_setting


async def _run_scenario(scenario: Scenario) -> list[dict[str, Any]]:
    from app.agent_chat import agent_chat_stream

    calls: list[dict[str, Any]] = []

    async def recording_tools(user_id, name, args, emit):  # noqa: ANN001
        calls.append({"name": name, "args": args})
        # Canned, benign results so a turn can progress without real side effects.
        return {"ok": True, "contacts": [], "total": 0, "leads": [], "lead_count": 0}

    events: list[dict[str, Any]] = []
    async for event in agent_chat_stream(1, scenario.message, [], tool_runner=recording_tools):
        events.append(event)
    return events


def _print_scorecard(results: list[ScenarioResult]) -> float:
    print(f"\n{'scenario':<32} {'first_tool':<18} immed sel avoid args  PASS")
    print("-" * 86)
    for r in results:
        print(
            f"{r.name:<32} {str(r.first_tool):<18} "
            f"{_b(r.acted_immediately)}    {_b(r.selected_expected)}  "
            f"{_b(r.avoided_forbidden)}    {_b(r.args_ok)}   {_b(r.passed)}"
            + (f"  (retries={r.retries})" if r.retries else "")
        )
    passed = sum(1 for r in results if r.passed)
    rate = passed / len(results) if results else 0.0
    print("-" * 86)
    print(f"PASS {passed}/{len(results)}  ({rate:.0%})\n")
    return rate


def _b(value: bool) -> str:
    return " ✓ " if value else " ✗ "


async def _main_async() -> int:
    _configure_settings_from_env()
    results: list[ScenarioResult] = []
    for scenario in SCENARIOS:
        try:
            events = await _run_scenario(scenario)
        except Exception as exc:  # noqa: BLE001 — report, don't crash the whole run
            print(f"[{scenario.name}] ERROR: {exc}")
            results.append(ScenarioResult(scenario.name, None, [], 0, False, False, False, False))
            continue
        results.append(score_run(events, scenario))
    rate = _print_scorecard(results)
    # Exit non-zero if more than one scenario fails, so CI/comparison can gate.
    return 0 if rate >= 0.75 else 1


def main() -> int:
    if os.getenv("PI_LIVE_LLM") != "1":
        print(
            "Live eval is opt-in. Run with:\n"
            "  PI_LIVE_LLM=1 LLM_API_KEY=... LLM_BASE_URL=https://api.deepseek.com "
            "LLM_MODEL=deepseek-chat .venv/bin/python scripts/eval_pi_prompt.py"
        )
        return 0
    return asyncio.run(_main_async())


if __name__ == "__main__":
    raise SystemExit(main())
