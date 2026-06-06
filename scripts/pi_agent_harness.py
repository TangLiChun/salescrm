#!/usr/bin/env python3
"""Pi agent live harness.

Runs the real Pi agent loop against the configured LLM while replacing every
CRM/enrichment tool with deterministic canned results. This catches model
planning failures, tool-call stalls, bad arguments, and interrupted streams
without mutating production data.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape, quoteattr

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.pi_harness import (  # noqa: E402
    SCENARIOS,
    Scenario,
    ScenarioResult,
    load_scenarios_from_file,
    result_record,
    run_scenario_with_fake_tools,
    score_run,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Pi agent LLM/tool-call harness scenarios.")
    parser.add_argument("--live", action="store_true", help="Allow network LLM calls.")
    parser.add_argument("--list", action="store_true", help="List built-in scenarios and exit.")
    parser.add_argument(
        "--scenario-file",
        type=Path,
        action="append",
        default=[],
        help="Load additional JSON scenario file. May be repeated.",
    )
    parser.add_argument(
        "--scenario",
        action="append",
        default=[],
        help="Scenario name to run. May be repeated. Defaults to all scenarios.",
    )
    parser.add_argument(
        "--tag",
        action="append",
        default=[],
        help="Run only scenarios with any matching tag. May be repeated or comma-separated.",
    )
    parser.add_argument(
        "--jsonl",
        type=Path,
        help="Write one JSON object per scenario with score and compact event trace.",
    )
    parser.add_argument(
        "--show-events",
        choices=("none", "fail", "all"),
        default="fail",
        help="Print compact event traces.",
    )
    parser.add_argument("--max-events", type=int, default=80, help="Max events to keep per trace.")
    parser.add_argument("--min-pass-rate", type=float, default=0.75, help="Required pass rate.")
    parser.add_argument("--repeat", type=int, default=1, help="Repeat each scenario N times.")
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=240.0,
        help="Per-scenario timeout.",
    )
    parser.add_argument("--fail-fast", action="store_true", help="Stop after the first failed run.")
    parser.add_argument("--summary-json", type=Path, help="Write aggregate summary JSON.")
    parser.add_argument("--markdown", type=Path, help="Write a human-readable Markdown report.")
    parser.add_argument("--junit-xml", type=Path, help="Write a JUnit XML report for CI.")
    parser.add_argument(
        "--replay-jsonl",
        type=Path,
        help="Replay a prior harness JSONL artifact without live LLM calls.",
    )
    parser.add_argument("--api-key", default="", help="LLM API key override.")
    parser.add_argument("--base-url", default="", help="LLM base URL override.")
    parser.add_argument("--model", default="", help="LLM model override.")
    parser.add_argument(
        "--thinking-mode",
        choices=("auto", "enabled", "disabled"),
        default="",
        help="Override llm_thinking_mode for this harness run.",
    )
    return parser.parse_args()


def configure_settings_from_env(args: argparse.Namespace) -> None:
    """Patch settings readers so the harness can run without a populated DB."""
    import app.agent_chat as ac
    import app.llm as llm

    real_get_setting = llm.get_setting
    overrides = {
        "llm_api_key": args.api_key
        or os.getenv("LLM_API_KEY", "")
        or os.getenv("DEEPSEEK_API_KEY", ""),
        "llm_base_url": args.base_url
        or os.getenv("LLM_BASE_URL", "")
        or os.getenv("DEEPSEEK_BASE_URL", ""),
        "llm_model": args.model or os.getenv("LLM_MODEL", ""),
        "llm_thinking_mode": args.thinking_mode or os.getenv("LLM_THINKING_MODE", ""),
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


def load_all_scenarios(paths: list[Path]) -> list[Scenario]:
    scenarios = list(SCENARIOS)
    for path in paths:
        scenarios.extend(load_scenarios_from_file(path))
    seen: set[str] = set()
    duplicates: set[str] = set()
    for scenario in scenarios:
        if scenario.name in seen:
            duplicates.add(scenario.name)
        seen.add(scenario.name)
    if duplicates:
        raise SystemExit(f"Duplicate scenario name(s): {', '.join(sorted(duplicates))}")
    return scenarios


def select_scenarios(
    scenarios: list[Scenario],
    names: list[str],
    tags: list[str] | None = None,
) -> list[Scenario]:
    selected = list(scenarios)

    wanted_tags = _csv_set(tags or [])
    if wanted_tags:
        selected = [scenario for scenario in selected if scenario.tags & wanted_tags]
        if not selected:
            raise SystemExit(f"No scenarios matched tag(s): {', '.join(sorted(wanted_tags))}")

    wanted = _csv_set(names)
    if not wanted:
        return selected
    selected = [scenario for scenario in selected if scenario.name in wanted]
    missing = sorted(wanted - {scenario.name for scenario in selected})
    if missing:
        raise SystemExit(f"Unknown scenario(s): {', '.join(missing)}")
    return selected


def _csv_set(values: list[str]) -> set[str]:
    wanted: set[str] = set()
    for raw in values:
        wanted.update(name.strip() for name in raw.split(",") if name.strip())
    return wanted


async def run_harness(
    scenarios: list[Scenario],
    *,
    max_events: int,
    repeat: int,
    timeout_seconds: float,
    fail_fast: bool,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for scenario in scenarios:
        for run_index in range(1, repeat + 1):
            started = time.perf_counter()
            try:
                events = await asyncio.wait_for(
                    run_scenario_with_fake_tools(scenario),
                    timeout=timeout_seconds,
                )
                result = score_run(events, scenario)
            except TimeoutError:
                events = [{"type": "error", "message": f"timeout after {timeout_seconds:.1f}s"}]
                result = _failed_result(
                    scenario.name,
                    [f"timeout:{timeout_seconds:.1f}s"],
                )
            except Exception as exc:  # noqa: BLE001 - keep the scorecard complete
                events = [{"type": "error", "message": str(exc)}]
                result = _failed_result(scenario.name, [f"exception:{exc}"])
            duration_ms = round((time.perf_counter() - started) * 1000)
            records.append(
                result_record(
                    scenario,
                    result,
                    events,
                    max_events=max_events,
                    run={
                        "index": run_index,
                        "repeat": repeat,
                        "duration_ms": duration_ms,
                        "timestamp": datetime.now(UTC).isoformat(),
                    },
                )
            )
            if fail_fast and not result.passed:
                return records
    return records


def _failed_result(name: str, reasons: list[str]) -> ScenarioResult:
    return ScenarioResult(
        name=name,
        first_tool=None,
        all_tools=[],
        retries=0,
        acted_immediately=False,
        selected_expected=False,
        avoided_forbidden=False,
        args_ok=False,
        stopped_cleanly=False,
        had_error=True,
        lonely_intro=False,
        failure_reasons=reasons,
    )


def print_scenarios(scenarios: list[Scenario]) -> None:
    for scenario in scenarios:
        print(
            f"{scenario.name:<32} expect={','.join(sorted(scenario.expect_tools)) or '-'} "
            f"forbid={','.join(sorted(scenario.forbid_tools)) or '-'} "
            f"allowed={','.join(sorted(scenario.allowed_tools)) or '-'} "
            f"tags={','.join(sorted(scenario.tags)) or '-'} "
            f"message={scenario.message}"
        )


def print_scorecard(records: list[dict[str, Any]]) -> float:
    print(
        f"\n{'scenario':<32} run  {'first_tool':<18} retry ms     clean pass  blocked        reasons"
    )
    print("-" * 140)
    for record in records:
        result = record["result"]
        run = record.get("run") or {}
        reasons = "; ".join(result["failure_reasons"])
        blocked = ",".join(result.get("blocked_tools") or [])
        print(
            f"{result['name']:<32} {str(run.get('index', 1)):<4} "
            f"{str(result['first_tool']):<18} {result['retries']:<5} "
            f"{str(run.get('duration_ms', '-')):<6} {_mark(result['stopped_cleanly'])}    "
            f"{_mark(result['passed'])}   {blocked:<14} {reasons}"
        )
    passed = sum(1 for record in records if record["result"]["passed"])
    rate = passed / len(records) if records else 0.0
    print("-" * 140)
    print(f"PASS {passed}/{len(records)} ({rate:.0%})\n")
    return rate


def maybe_print_events(records: list[dict[str, Any]], *, mode: str, max_events: int) -> None:
    if mode == "none":
        return
    for record in records:
        passed = bool(record["result"]["passed"])
        if mode == "fail" and passed:
            continue
        print(f"[events] {record['scenario']['name']}")
        for event in record["events"][:max_events]:
            print("  " + json.dumps(event, ensure_ascii=False))


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if not path.exists():
        raise SystemExit(f"JSONL artifact does not exist: {path}")
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            text = line.strip()
            if not text:
                continue
            try:
                records.append(json.loads(text))
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path}:{lineno}: invalid JSONL: {exc}") from exc
    return records


def write_summary_json(path: Path, records: list[dict[str, Any]]) -> None:
    summary = build_summary(records)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_markdown_report(path: Path, records: list[dict[str, Any]]) -> None:
    summary = build_summary(records)
    lines = [
        "# Pi Agent Harness Report",
        "",
        f"- Generated: `{summary['generated_at']}`",
        f"- Result: `{summary['passed']}/{summary['total']}` passed",
        f"- Pass rate: `{summary['pass_rate']:.0%}`",
        f"- Failed: `{summary['failed']}`",
        "",
        "## Runs",
        "",
        "| Scenario | Run | First Tool | Pass | Duration | Blocked | Reasons |",
        "|---|---:|---|---|---:|---|---|",
    ]
    for record in records:
        result = record.get("result") or {}
        run = record.get("run") or {}
        lines.append(
            "| "
            + " | ".join(
                [
                    _md(result.get("name")),
                    _md(run.get("index", 1)),
                    _md(result.get("first_tool") or ""),
                    "yes" if result.get("passed") else "no",
                    _md(run.get("duration_ms", "")),
                    _md(", ".join(result.get("blocked_tools") or [])),
                    _md("; ".join(result.get("failure_reasons") or [])),
                ]
            )
            + " |"
        )

    lines.extend(["", "## Scenario Stability", ""])
    lines.append("| Scenario | Passed | Pass Rate | p95 ms | First Tools |")
    lines.append("|---|---:|---:|---:|---|")
    for row in summary["scenarios"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    _md(row["name"]),
                    f"{row['passed']}/{row['total']}",
                    f"{row['pass_rate']:.0%}",
                    _md(row.get("duration_p95_ms", "")),
                    _md(_counts_text(row.get("first_tool_counts") or {})),
                ]
            )
            + " |"
        )

    if summary["failures"]:
        lines.extend(["", "## Failures", ""])
        for failure in summary["failures"]:
            lines.append(
                f"- `{failure['name']}` run `{failure['run']}`: "
                f"{_md('; '.join(failure['failure_reasons']))}"
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_junit_xml(path: Path, records: list[dict[str, Any]]) -> None:
    failures = [record for record in records if not record.get("result", {}).get("passed")]
    duration_s = sum(_duration_seconds(record) for record in records)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<testsuite name="pi_agent_harness" tests="{len(records)}" '
            f'failures="{len(failures)}" errors="0" skipped="0" time="{duration_s:.3f}">'
        ),
    ]
    for record in records:
        result = record.get("result") or {}
        run = record.get("run") or {}
        name = f"{result.get('name') or 'scenario'}#{run.get('index', 1)}"
        case_time = _duration_seconds(record)
        lines.append(
            f'  <testcase classname="pi_agent_harness" '
            f'name={quoteattr(str(name))} time="{case_time:.3f}">'
        )
        if not result.get("passed"):
            reasons = "; ".join(result.get("failure_reasons") or ["failed"])
            lines.append(
                f"    <failure message={quoteattr(reasons[:240])}>{escape(reasons)}</failure>"
            )
        lines.append("  </testcase>")
    lines.append("</testsuite>")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    passed = sum(1 for record in records if record.get("result", {}).get("passed"))
    failure_reason_counts = Counter(
        reason
        for record in records
        if not record.get("result", {}).get("passed")
        for reason in (record.get("result", {}).get("failure_reasons") or [])
    )
    blocked_tool_counts = Counter(
        tool for record in records for tool in (record.get("result", {}).get("blocked_tools") or [])
    )
    failures = [
        {
            "name": record.get("result", {}).get("name"),
            "run": (record.get("run") or {}).get("index", 1),
            "failure_reasons": record.get("result", {}).get("failure_reasons") or [],
            "blocked_tools": record.get("result", {}).get("blocked_tools") or [],
        }
        for record in records
        if not record.get("result", {}).get("passed")
    ]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": passed / total if total else 0.0,
        "failure_reason_counts": dict(sorted(failure_reason_counts.items())),
        "blocked_tool_counts": dict(sorted(blocked_tool_counts.items())),
        "scenarios": scenario_summaries(records),
        "failures": failures,
    }


def scenario_summaries(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name in sorted({str((record.get("result") or {}).get("name") or "") for record in records}):
        group = [record for record in records if (record.get("result") or {}).get("name") == name]
        passed = sum(1 for record in group if (record.get("result") or {}).get("passed"))
        durations = [
            int((record.get("run") or {}).get("duration_ms"))
            for record in group
            if isinstance((record.get("run") or {}).get("duration_ms"), int)
        ]
        first_tools = Counter(
            str((record.get("result") or {}).get("first_tool") or "none") for record in group
        )
        failure_reasons = Counter(
            reason
            for record in group
            if not (record.get("result") or {}).get("passed")
            for reason in ((record.get("result") or {}).get("failure_reasons") or [])
        )
        blocked_tools = Counter(
            tool
            for record in group
            for tool in ((record.get("result") or {}).get("blocked_tools") or [])
        )
        rows.append(
            {
                "name": name,
                "total": len(group),
                "passed": passed,
                "failed": len(group) - passed,
                "pass_rate": passed / len(group) if group else 0.0,
                "duration_avg_ms": round(sum(durations) / len(durations)) if durations else None,
                "duration_p95_ms": percentile(durations, 95) if durations else None,
                "first_tool_counts": dict(sorted(first_tools.items())),
                "failure_reason_counts": dict(sorted(failure_reasons.items())),
                "blocked_tool_counts": dict(sorted(blocked_tools.items())),
            }
        )
    return rows


def percentile(values: list[int], pct: int) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((pct / 100) * (len(ordered) - 1))))
    return ordered[index]


def _duration_seconds(record: dict[str, Any]) -> float:
    duration_ms = (record.get("run") or {}).get("duration_ms")
    return (duration_ms / 1000) if isinstance(duration_ms, (int, float)) else 0.0


def _counts_text(counts: dict[str, int]) -> str:
    return ", ".join(f"{key}:{value}" for key, value in sorted(counts.items()))


def _md(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ")


def _mark(value: bool) -> str:
    return "ok" if value else "NO"


def main() -> int:
    args = parse_args()
    scenarios = select_scenarios(load_all_scenarios(args.scenario_file), args.scenario, args.tag)
    if args.list:
        print_scenarios(scenarios)
        return 0

    if args.replay_jsonl:
        records = read_jsonl(args.replay_jsonl)
        rate = print_scorecard(records)
        maybe_print_events(records, mode=args.show_events, max_events=args.max_events)
        if args.summary_json:
            write_summary_json(args.summary_json, records)
            print(f"Wrote {args.summary_json}")
        if args.markdown:
            write_markdown_report(args.markdown, records)
            print(f"Wrote {args.markdown}")
        if args.junit_xml:
            write_junit_xml(args.junit_xml, records)
            print(f"Wrote {args.junit_xml}")
        return 0 if rate >= args.min_pass_rate else 1

    if not args.live and os.getenv("PI_LIVE_LLM") != "1":
        print(
            "Harness is live-LLM opt-in. Example:\n"
            "  PI_LIVE_LLM=1 LLM_API_KEY=sk-... "
            "LLM_BASE_URL=https://api.deepseek.com LLM_MODEL=deepseek-v4-flash "
            ".venv/bin/python scripts/pi_agent_harness.py --jsonl artifacts/pi-harness.jsonl\n\n"
            "Use --list to inspect scenarios without network calls."
        )
        return 0

    configure_settings_from_env(args)
    records = asyncio.run(
        run_harness(
            scenarios,
            max_events=args.max_events,
            repeat=max(1, args.repeat),
            timeout_seconds=max(1.0, args.timeout_seconds),
            fail_fast=args.fail_fast,
        )
    )
    rate = print_scorecard(records)
    maybe_print_events(records, mode=args.show_events, max_events=args.max_events)
    if args.jsonl:
        write_jsonl(args.jsonl, records)
        print(f"Wrote {args.jsonl}")
    if args.summary_json:
        write_summary_json(args.summary_json, records)
        print(f"Wrote {args.summary_json}")
    if args.markdown:
        write_markdown_report(args.markdown, records)
        print(f"Wrote {args.markdown}")
    if args.junit_xml:
        write_junit_xml(args.junit_xml, records)
        print(f"Wrote {args.junit_xml}")
    return 0 if rate >= args.min_pass_rate else 1


if __name__ == "__main__":
    raise SystemExit(main())
