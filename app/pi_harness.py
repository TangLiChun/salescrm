"""Reusable Pi agent evaluation harness primitives.

The harness runs the real agent loop with a fake tool runner, so it evaluates
LLM planning/tool-calling behavior without touching production CRM data or
network enrichment tools.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

VALID_FOLLOW_UP = {"new", "contacted", "replied", "invalid", "interested"}


@dataclass
class Scenario:
    name: str
    message: str
    expect_tools: set[str]
    forbid_tools: set[str] = field(default_factory=set)
    arg_check: Callable[[str, dict[str, Any]], bool] | None = None
    arg_check_name: str | None = None
    max_retries: int = 0
    require_immediate: bool = True
    fail_on_blocked_tools: bool = True


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
    stopped_cleanly: bool = True
    had_error: bool = False
    lonely_intro: bool = False
    blocked_tools: list[str] = field(default_factory=list)
    failure_reasons: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failure_reasons


def _asn_text_ok(_name: str, args: dict[str, Any]) -> bool:
    text = str(args.get("text") or args.get("query") or "")
    return any(ch.isdigit() for ch in text)


def _list_contacts_ok(_name: str, args: dict[str, Any]) -> bool:
    return bool(str(args.get("q") or "").strip())


def _status_ok(_name: str, args: dict[str, Any]) -> bool:
    return str(args.get("follow_up_status") or "") in VALID_FOLLOW_UP


ARG_CHECKS: dict[str, Callable[[str, dict[str, Any]], bool]] = {
    "asn_text": _asn_text_ok,
    "list_contacts_non_empty": _list_contacts_ok,
    "follow_up_status": _status_ok,
}


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
        expect_tools={"lookup_asns"},
        forbid_tools={"discover_leads", "web_search"},
        arg_check=_asn_text_ok,
        arg_check_name="asn_text",
    ),
    Scenario(
        name="search-crm-immediately",
        message="列出库里所有 Google 相关的联系人",
        expect_tools={"list_contacts"},
        arg_check=_list_contacts_ok,
        arg_check_name="list_contacts_non_empty",
    ),
    Scenario(
        name="update-status-valid-enum",
        message="把联系人 #5 标记为已联系",
        expect_tools={"update_contact"},
        arg_check=_status_ok,
        arg_check_name="follow_up_status",
    ),
]


def scenario_from_dict(raw: dict[str, Any]) -> Scenario:
    """Parse a JSON scenario definition into a typed Scenario."""
    if not isinstance(raw, dict):
        raise ValueError("scenario must be an object")
    name = str(raw.get("name") or "").strip()
    message = str(raw.get("message") or "").strip()
    if not name:
        raise ValueError("scenario.name is required")
    if not message:
        raise ValueError(f"{name}: scenario.message is required")

    arg_check_name = str(raw.get("arg_check") or "").strip() or None
    arg_check = None
    if arg_check_name:
        arg_check = ARG_CHECKS.get(arg_check_name)
        if arg_check is None:
            raise ValueError(
                f"{name}: unknown arg_check {arg_check_name!r}; "
                f"known: {', '.join(sorted(ARG_CHECKS))}"
            )

    return Scenario(
        name=name,
        message=message,
        expect_tools=_string_set(raw.get("expect_tools")),
        forbid_tools=_string_set(raw.get("forbid_tools")),
        arg_check=arg_check,
        arg_check_name=arg_check_name,
        max_retries=max(0, int(raw.get("max_retries") or 0)),
        require_immediate=_bool(raw.get("require_immediate", True)),
        fail_on_blocked_tools=_bool(raw.get("fail_on_blocked_tools", True)),
    )


def load_scenarios_from_file(path: Path) -> list[Scenario]:
    """Load custom scenarios from a JSON file.

    The file may contain either a top-level list or {"scenarios": [...]}.
    """
    with path.open("r", encoding="utf-8") as fh:
        payload = json.load(fh)
    rows = payload.get("scenarios") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("scenario file must be a list or an object with a scenarios list")
    return [scenario_from_dict(row) for row in rows]


def score_run(events: list[dict[str, Any]], scenario: Scenario) -> ScenarioResult:
    """Score one agent event stream against a scenario."""
    tool_starts: list[tuple[str, dict[str, Any]]] = [
        (str(e.get("name")), e.get("args") or {}) for e in events if e.get("type") == "tool_start"
    ]
    all_tools = [name for name, _ in tool_starts]
    first_tool = all_tools[0] if all_tools else None
    event_types = [str(e.get("type") or "") for e in events]

    acted_immediately = True
    for event in events:
        if event.get("type") == "tool_start":
            break
        if event.get("type") == "status" and "重试" in str(event.get("message") or ""):
            acted_immediately = False
            break

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

    stopped_cleanly = bool(event_types and event_types[-1] == "done")
    errors = [str(e.get("message") or "error") for e in events if e.get("type") == "error"]
    blocked_tools = [
        str(e.get("name") or "tool") for e in events if e.get("type") == "tool_blocked"
    ]
    lonely_intro = bool(
        scenario.expect_tools
        and not tool_starts
        and any(e.get("type") == "assistant_done" for e in events)
    )

    failure_reasons: list[str] = []
    if not stopped_cleanly:
        failure_reasons.append("stream_did_not_end_with_done")
    if errors:
        failure_reasons.append("error:" + " | ".join(errors[:2]))
    if not selected_expected:
        failure_reasons.append(
            f"expected_first_tool={sorted(scenario.expect_tools)} got={first_tool}"
        )
    if not avoided_forbidden:
        failure_reasons.append(
            f"forbidden_tool_used={sorted(set(all_tools) & scenario.forbid_tools)}"
        )
    if not args_ok:
        failure_reasons.append("args_check_failed")
    if scenario.require_immediate and not acted_immediately:
        failure_reasons.append("needed_retry_before_first_tool")
    if retries > scenario.max_retries:
        failure_reasons.append(f"retry_budget_exceeded={retries}>{scenario.max_retries}")
    if lonely_intro:
        failure_reasons.append("assistant_intro_without_tool")
    if scenario.fail_on_blocked_tools and blocked_tools:
        failure_reasons.append(f"blocked_tool_attempted={blocked_tools[:5]}")

    return ScenarioResult(
        name=scenario.name,
        first_tool=first_tool,
        all_tools=all_tools,
        retries=retries,
        acted_immediately=acted_immediately,
        selected_expected=selected_expected,
        avoided_forbidden=avoided_forbidden,
        args_ok=args_ok,
        stopped_cleanly=stopped_cleanly,
        had_error=bool(errors),
        lonely_intro=lonely_intro,
        blocked_tools=blocked_tools,
        failure_reasons=failure_reasons,
    )


def canned_tool_result(name: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    """Plausible non-empty tool result for live LLM evaluation."""
    args = args or {}
    sample_lead = {
        "org": "Example Net",
        "email": "noc@example.net",
        "asn": "395092",
        "lead_score": 72,
    }
    if name in ("discover_leads", "enrich_contact"):
        return {"lead_count": 1, "leads": [sample_lead], "import": {"imported": 1}}
    if name == "lookup_asns":
        return {"asns": ["15169"], "email_count": 1, "rows": [sample_lead]}
    if name == "list_contacts":
        q = str(args.get("q") or "Google")
        return {"contacts": [{"id": 1, "org": q, "email": "peering@example.net"}], "total": 1}
    if name == "get_contact":
        return {"contact": {"id": args.get("contact_id", 5), "org": "Example Net"}}
    return {"ok": True}


async def run_scenario_with_fake_tools(
    scenario: Scenario,
    *,
    user_id: int = 1,
) -> list[dict[str, Any]]:
    from app.agent_chat import agent_chat_stream

    async def fake_tool_runner(user_id, name, args, emit):  # noqa: ANN001
        return canned_tool_result(str(name), args if isinstance(args, dict) else {})

    events: list[dict[str, Any]] = []
    async for event in agent_chat_stream(
        user_id,
        scenario.message,
        [],
        tool_runner=fake_tool_runner,
    ):
        events.append(event)
    return events


def compact_events(events: list[dict[str, Any]], *, limit: int = 80) -> list[dict[str, Any]]:
    """Shrink event streams enough for JSONL artifacts and failed-run logs."""
    compacted = [_compact_event(event) for event in events[:limit]]
    if len(events) > limit:
        compacted.append({"type": "omitted", "count": len(events) - limit})
    return compacted


def result_record(
    scenario: Scenario,
    result: ScenarioResult,
    events: list[dict[str, Any]],
    *,
    max_events: int = 80,
    run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = {
        "scenario": {
            "name": scenario.name,
            "message": scenario.message,
            "expect_tools": sorted(scenario.expect_tools),
            "forbid_tools": sorted(scenario.forbid_tools),
            "arg_check": scenario.arg_check_name,
            "max_retries": scenario.max_retries,
            "require_immediate": scenario.require_immediate,
            "fail_on_blocked_tools": scenario.fail_on_blocked_tools,
        },
        "result": asdict(result) | {"passed": result.passed},
        "events": compact_events(events, limit=max_events),
        "event_count": len(events),
    }
    if run:
        record["run"] = dict(run)
    return record


def _compact_event(event: dict[str, Any]) -> dict[str, Any]:
    event_type = str(event.get("type") or "")
    if event_type in {"status", "error"}:
        return {"type": event_type, "message": _clip(event.get("message"))}
    if event_type in {"assistant_delta", "assistant_done", "assistant"}:
        return {"type": event_type, "text": _clip(event.get("text"))}
    if event_type == "tool_start":
        return {
            "type": event_type,
            "name": event.get("name"),
            "args": _safe_json(event.get("args")),
        }
    if event_type == "tool_result":
        result = event.get("result")
        return {
            "type": event_type,
            "name": event.get("name"),
            "result": _summarize_result(result),
        }
    if event_type == "tool_blocked":
        return {
            "type": event_type,
            "name": event.get("name"),
            "reason": _clip(event.get("reason")),
            "args": _safe_json(event.get("args")),
        }
    if event_type == "tool_progress":
        return {
            "type": event_type,
            "name": event.get("name"),
            "message": _clip(event.get("message")),
        }
    return {"type": event_type}


def _summarize_result(result: Any) -> Any:
    if not isinstance(result, dict):
        return _clip(result)
    keys = ("ok", "error", "total", "lead_count", "email_count", "imported", "skipped")
    summary = {key: result.get(key) for key in keys if key in result}
    if not summary:
        summary["keys"] = sorted(str(k) for k in result.keys())[:12]
    return summary


def _safe_json(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except (TypeError, ValueError):
        return _clip(value)


def _clip(value: Any, limit: int = 500) -> str:
    text = str(value or "")
    return text[:limit] + ("..." if len(text) > limit else "")


def _string_set(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, str):
        return {value} if value.strip() else set()
    if isinstance(value, list):
        return {str(item).strip() for item in value if str(item).strip()}
    raise ValueError("tool fields must be strings or arrays of strings")


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)
