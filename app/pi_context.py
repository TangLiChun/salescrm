"""Pi chat context: rolling summary + tiered history for large-context models."""

from __future__ import annotations

import json
from typing import Any

from app.import_filters import parse_patterns
from app.llm import LLMError, chat_completion_summary

# Stored in DB per thread (full UI history cap)
MAX_STORED_MESSAGES = 800

# Sent to LLM with full user/assistant/tool-summary text
MAX_RECENT_FULL_MESSAGES = 100

# Compact one-line fallback for middle tier (between summary and recent)
MAX_MIDDLE_COMPACT_LINES = 240

# When uncovered history exceeds recent window by this much, LLM-summarize a batch
SUMMARIZE_TRIGGER_GAP = 48
SUMMARIZE_BATCH_SIZE = 40
SUMMARY_MAX_CHARS = 6000
CONTEXT_USAGE_COMPRESS_PERCENT = 80

# Tool JSON fed back into the agent loop (per tool call)
MAX_TOOL_JSON_CHARS = 32000

# Stored tool summary in thread history (UI + future compression)
MAX_STORED_TOOL_SUMMARY_CHARS = 8000

_MAX_PATTERN_SAMPLE = 12
_MAX_QUERY_PREVIEW = 120
_MAX_SCHEDULE_PREVIEW = 30


def _truncate_preview_text(text: Any, limit: int) -> str:
    value = str(text or "")
    if len(value) <= limit:
        return value
    return value[:limit] + "…"


def _import_filters_compact(result: dict[str, Any]) -> dict[str, Any]:
    blocklist_patterns = result.get("blocklist_patterns")
    if blocklist_patterns is None:
        blocklist_patterns = parse_patterns(str(result.get("blocklist") or ""))
    allowlist_patterns = result.get("allowlist_patterns")
    if allowlist_patterns is None:
        allowlist_patterns = parse_patterns(str(result.get("allowlist") or ""))

    payload: dict[str, Any] = {
        "blocklist_count": len(blocklist_patterns),
        "allowlist_count": len(allowlist_patterns),
        "blocklist_sample": blocklist_patterns[:_MAX_PATTERN_SAMPLE],
        "allowlist_sample": allowlist_patterns[:_MAX_PATTERN_SAMPLE],
    }
    omitted_block = max(0, len(blocklist_patterns) - _MAX_PATTERN_SAMPLE)
    omitted_allow = max(0, len(allowlist_patterns) - _MAX_PATTERN_SAMPLE)
    if omitted_block:
        payload["blocklist_omitted"] = omitted_block
    if omitted_allow:
        payload["allowlist_omitted"] = omitted_allow
    if "ok" in result:
        payload["ok"] = result["ok"]
    if result.get("message"):
        payload["message"] = result["message"]
    return payload


def _schedule_item_preview(job: dict[str, Any]) -> dict[str, Any]:
    preview: dict[str, Any] = {}
    for key in ("id", "name", "enabled"):
        if job.get(key) is not None:
            preview[key] = job.get(key)
    if job.get("query") is not None:
        preview["query"] = _truncate_preview_text(job.get("query"), _MAX_QUERY_PREVIEW)
    return preview


def _search_config_slim(result: dict[str, Any]) -> dict[str, Any]:
    zhipu = result.get("zhipu_web_search") or {}
    bright = result.get("brightdata_serp") or {}
    shodan_cfg = result.get("shodan") or {}
    unlocker = result.get("web_unlocker") or {}
    raw_channels = result.get("data_channels") or result.get("channels") or {}
    data_channels = {
        key: value for key, value in raw_channels.items() if isinstance(value, bool)
    }
    return {
        "active_web_backend": result.get("active_web_backend"),
        "web_backend_priority": result.get("web_backend_priority") or [],
        "keys_configured": result.get("keys_configured") or {},
        "zhipu_web_search": {
            "configured": zhipu.get("configured"),
            "engine": zhipu.get("engine"),
        },
        "brightdata_serp": {
            "configured": bright.get("configured"),
            "zone": bright.get("zone"),
            "data_format": bright.get("data_format"),
        },
        "data_channels": data_channels,
        "social_configured": result.get("social_configured") or [],
        "shodan_configured": bool(
            shodan_cfg.get("configured") if isinstance(shodan_cfg, dict) else shodan_cfg
        ),
        "web_unlocker_configured": bool(
            unlocker.get("configured") if isinstance(unlocker, dict) else unlocker
        ),
    }


def compress_tool_result_for_llm(name: str, result: Any) -> str:
    if not isinstance(result, dict):
        text = json.dumps(result, ensure_ascii=False)
        return _truncate_json_text(text)

    if result.get("error"):
        return json.dumps({"error": result["error"]}, ensure_ascii=False)

    if name in ("discover_leads", "enrich_contact"):
        leads = result.get("leads") or []
        preview = []
        for lead in leads[:60]:
            if not isinstance(lead, dict):
                continue
            preview.append(
                {
                    k: lead.get(k)
                    for k in (
                        "org",
                        "name",
                        "email",
                        "asn",
                        "lead_score",
                        "source",
                        "linkedin",
                        "x",
                        "facebook",
                    )
                    if lead.get(k) not in (None, "")
                }
            )
        payload = {
            "message": result.get("message"),
            "lead_count": result.get("lead_count", len(leads)),
            "leads_preview": preview,
            "leads_omitted": max(0, len(leads) - len(preview)),
            "import": result.get("import"),
        }
        if result.get("contact_id"):
            payload["contact_id"] = result["contact_id"]
        return _truncate_json_text(json.dumps(payload, ensure_ascii=False))

    if name == "lookup_asns":
        rows = result.get("rows") or result.get("preview") or []
        preview = []
        for row in rows[:80]:
            if not isinstance(row, dict):
                continue
            preview.append(
                {
                    k: row.get(k)
                    for k in ("asn", "org", "name", "email", "roles", "rir")
                    if row.get(k) not in (None, "")
                }
            )
        payload = {
            "asn_count": result.get("asn_count") or len(result.get("asns") or []),
            "email_count": result.get("email_count"),
            "rows_preview": preview,
            "rows_omitted": max(0, len(rows) - len(preview)),
        }
        return _truncate_json_text(json.dumps(payload, ensure_ascii=False))

    if name == "list_contacts":
        contacts = result.get("contacts") or []
        preview = [
            {
                k: item.get(k)
                for k in ("id", "org", "name", "email", "asn", "follow_up_status")
                if item.get(k) not in (None, "")
            }
            for item in contacts[:40]
            if isinstance(item, dict)
        ]
        payload = {
            "total": result.get("total", len(contacts)),
            "contacts_preview": preview,
            "contacts_omitted": max(0, len(contacts) - len(preview)),
        }
        return _truncate_json_text(json.dumps(payload, ensure_ascii=False))

    if name == "import_leads":
        return _truncate_json_text(
            json.dumps(
                {
                    k: result.get(k)
                    for k in ("imported", "duplicates", "skipped", "filtered", "total")
                },
                ensure_ascii=False,
            )
        )

    if name == "list_contact_notes":
        notes = result.get("notes") or []
        preview = []
        for note in notes[:30]:
            if not isinstance(note, dict):
                continue
            body = str(note.get("body") or "")
            preview.append(
                {
                    "id": note.get("id"),
                    "created_at": note.get("created_at"),
                    "body": body[:600] + ("…" if len(body) > 600 else ""),
                }
            )
        payload = {
            "contact_id": result.get("contact_id"),
            "count": result.get("count", len(notes)),
            "notes_preview": preview,
            "notes_omitted": max(0, int(result.get("count") or len(notes)) - len(preview)),
        }
        return _truncate_json_text(json.dumps(payload, ensure_ascii=False))

    if name == "get_lead_preferences":
        prefs = result.get("preferences") or {}
        payload = {
            "min_score_hint": prefs.get("min_score_hint"),
            "preferred_roles": (prefs.get("preferred_roles") or [])[:8],
            "keyword_hints": (prefs.get("keyword_hints") or [])[:12],
            "avoid_orgs": (prefs.get("avoid_orgs") or [])[:12],
            "avoid_domains": (prefs.get("avoid_domains") or [])[:15],
            "liked_orgs": (prefs.get("liked_orgs") or [])[:12],
            "stats": prefs.get("stats") or {},
            "summary": result.get("summary"),
        }
        return _truncate_json_text(json.dumps(payload, ensure_ascii=False))

    if name == "reset_lead_preferences":
        return _truncate_json_text(
            json.dumps(
                {
                    "ok": result.get("ok"),
                    "message": result.get("message"),
                    "min_score_hint": (result.get("preferences") or {}).get("min_score_hint"),
                },
                ensure_ascii=False,
            )
        )

    if name in ("shodan_search", "web_search", "fetch_web_pages", "search_hosting_forums"):
        networks = result.get("networks") or []
        web_results = (
            result.get("web_results") or result.get("results") or result.get("pages") or []
        )
        payload = {
            "query": result.get("query"),
            "match_count": result.get("match_count") or result.get("result_count"),
            "networks": networks[:25],
            "web_results": web_results[:15],
            "note": result.get("note"),
        }
        return _truncate_json_text(json.dumps(payload, ensure_ascii=False))

    if name.startswith("collect_") and name.endswith("_profiles"):
        profiles = result.get("profiles") or result.get("lead_previews") or []
        payload = {
            "profile_count": result.get("profile_count", len(profiles)),
            "profiles": profiles[:20],
            "note": result.get("note"),
        }
        return _truncate_json_text(json.dumps(payload, ensure_ascii=False))

    if name in ("get_import_filters", "update_import_filters"):
        return _truncate_json_text(
            json.dumps(_import_filters_compact(result), ensure_ascii=False)
        )

    if name == "list_schedules":
        schedules = result.get("schedules") or []
        preview = [
            _schedule_item_preview(item)
            for item in schedules[:_MAX_SCHEDULE_PREVIEW]
            if isinstance(item, dict)
        ]
        payload = {
            "count": result.get("count", len(schedules)),
            "schedules_preview": preview,
            "schedules_omitted": max(0, len(schedules) - len(preview)),
        }
        return _truncate_json_text(json.dumps(payload, ensure_ascii=False))

    if name in ("create_schedule", "update_schedule"):
        schedule = result.get("schedule") or {}
        payload = {
            "ok": result.get("ok"),
            "schedule": _schedule_item_preview(schedule) if isinstance(schedule, dict) else {},
        }
        return _truncate_json_text(json.dumps(payload, ensure_ascii=False))

    if name == "get_search_config":
        return _truncate_json_text(json.dumps(_search_config_slim(result), ensure_ascii=False))

    slim = {k: v for k, v in result.items() if k not in ("leads", "rows", "contacts", "profiles")}
    if "leads_preview" in result:
        slim["leads_preview"] = result.get("leads_preview")
    return _truncate_json_text(json.dumps(slim, ensure_ascii=False))


def tool_summary_for_storage(name: str, result: Any, *, fallback: str = "") -> str:
    if isinstance(result, dict) and result.get("error"):
        return str(result["error"])[:MAX_STORED_TOOL_SUMMARY_CHARS]
    compressed = compress_tool_result_for_llm(
        name, result if isinstance(result, dict) else {"value": result}
    )
    if len(compressed) <= MAX_STORED_TOOL_SUMMARY_CHARS:
        return compressed
    if fallback.strip():
        return fallback.strip()[:MAX_STORED_TOOL_SUMMARY_CHARS]
    return compressed[:MAX_STORED_TOOL_SUMMARY_CHARS]


def _truncate_json_text(text: str) -> str:
    if len(text) <= MAX_TOOL_JSON_CHARS:
        return text
    return text[:MAX_TOOL_JSON_CHARS] + f"…[truncated, {len(text)} chars total]"


def compact_history_line(item: dict[str, Any], *, verbose: bool = False) -> str | None:
    role = item.get("role")
    if role == "user":
        text = str(item.get("content") or "").strip().replace("\n", " ")
        if not text:
            return None
        limit = 500 if verbose else 220
        return f"用户: {text[:limit]}{'…' if len(text) > limit else ''}"
    if role == "assistant":
        text = str(item.get("content") or "").strip().replace("\n", " ")
        if not text:
            return None
        limit = 500 if verbose else 220
        return f"助手: {text[:limit]}{'…' if len(text) > limit else ''}"
    if role == "tool":
        name = str(item.get("name") or "tool")
        summary = str(item.get("summary") or "").strip().replace("\n", " ")
        if not summary:
            return f"工具 {name}: (无摘要)"
        limit = 800 if verbose else 280
        return f"工具 {name}: {summary[:limit]}{'…' if len(summary) > limit else ''}"
    return None


def build_llm_messages(
    history: list[dict[str, Any]],
    *,
    context_summary: str = "",
    summary_through: int = 0,
) -> list[dict[str, str]]:
    """Tiered context: rolling summary + compact middle + recent full turns."""
    if not history:
        return []

    messages: list[dict[str, str]] = []
    summary = (context_summary or "").strip()
    covered = max(0, min(int(summary_through or 0), len(history)))
    n = len(history)
    recent_start = max(0, n - MAX_RECENT_FULL_MESSAGES)

    if summary:
        messages.append(
            {
                "role": "user",
                "content": (
                    "[Earlier conversation summary — merged from older turns]\n"
                    f"{summary[:SUMMARY_MAX_CHARS]}"
                ),
            }
        )
        messages.append(
            {
                "role": "assistant",
                "content": "已读取历史摘要，我会结合摘要与最近对话继续协助。",
            }
        )

    middle_start = max(covered, 0)
    middle_end = recent_start
    if middle_start < middle_end:
        lines: list[str] = []
        for item in history[middle_start:middle_end]:
            line = compact_history_line(item)
            if line:
                lines.append(line)
        if len(lines) > MAX_MIDDLE_COMPACT_LINES:
            omitted = len(lines) - MAX_MIDDLE_COMPACT_LINES
            lines = lines[-MAX_MIDDLE_COMPACT_LINES:]
            lines.insert(0, f"…（另有 {omitted} 条更早对话已省略）")
        if lines:
            messages.append(
                {
                    "role": "user",
                    "content": "[Intermediate turns — compact]\n" + "\n".join(lines),
                }
            )

    for item in history[recent_start:]:
        role = item.get("role")
        if role in ("user", "assistant"):
            content = str(item.get("content") or "").strip()
            if content:
                messages.append({"role": role, "content": content})
        elif role == "tool":
            name = str(item.get("name") or "tool")
            summary_text = str(item.get("summary") or "").strip()
            if summary_text:
                messages.append(
                    {
                        "role": "assistant",
                        "content": f"[工具 {name} 结果]\n{summary_text[:MAX_STORED_TOOL_SUMMARY_CHARS]}",
                    }
                )

    return messages


def needs_summary_update(history_len: int, summary_through: int) -> bool:
    if history_len <= MAX_RECENT_FULL_MESSAGES + SUMMARIZE_TRIGGER_GAP:
        return False
    uncovered = history_len - max(0, summary_through)
    return uncovered > MAX_RECENT_FULL_MESSAGES + SUMMARIZE_TRIGGER_GAP


def should_compress_thread(
    history_len: int, summary_through: int, *, usage_percent: int = 0
) -> bool:
    if needs_summary_update(history_len, summary_through):
        return True
    if usage_percent >= CONTEXT_USAGE_COMPRESS_PERCENT:
        uncovered = history_len - max(0, summary_through)
        if uncovered > SUMMARIZE_BATCH_SIZE:
            return True
    return False


_CONTEXT_OVERFLOW_MARKERS = (
    "context length",
    "maximum context",
    "context_length",
    "too many tokens",
    "token limit",
    "max_tokens",
    "reduce the length",
    "prompt is too long",
    "request too large",
    "上下文过长",
    "上下文长度",
    "超出最大",
    "超过最大",
    "token 超限",
)


def is_context_overflow_error(message: str | None) -> bool:
    text = str(message or "").strip().lower()
    if not text:
        return False
    return any(marker in text for marker in _CONTEXT_OVERFLOW_MARKERS)


def is_valid_compression_cut(history: list[dict[str, Any]], end: int) -> bool:
    """True when history[:end] ends on a turn boundary (not mid tool chain)."""
    if end <= 0 or end > len(history):
        return False
    role = str(history[end - 1].get("role") or "")
    if role == "user":
        return True
    if role == "assistant":
        return end >= len(history) or str(history[end].get("role") or "") != "tool"
    return False


def next_compression_batch_end(
    history: list[dict[str, Any]],
    through: int,
    batch_size: int,
    max_end: int,
) -> int:
    """Pick batch end respecting turn boundaries; never split assistant/tool chains."""
    if through >= max_end or through >= len(history):
        return through
    target = min(through + max(1, batch_size), max_end, len(history))
    end = target
    while end > through and not is_valid_compression_cut(history, end):
        end -= 1
    if end <= through:
        end = min(through + 1, max_end, len(history))
        while end <= max_end and end <= len(history) and not is_valid_compression_cut(history, end):
            end += 1
    return min(end, max_end, len(history))


def summarize_branch_suffix(batch: list[dict[str, Any]]) -> str:
    """Summarize discarded suffix when forking (Pi branch-summary lite)."""
    lines = [line for item in batch if (line := compact_history_line(item, verbose=True))]
    if not lines:
        return ""
    prompt = (
        "你是 Sales CRM Pi 助手的分支摘要器。以下是对话在分叉点之后、主线程上继续的内容。\n"
        "输出简短中文条目：已尝试操作、关键结论、失败原因、待办。不要寒暄，不超过 400 字。\n\n"
        + "\n".join(lines)
    )
    try:
        return chat_completion_summary(
            [
                {"role": "system", "content": "你只输出摘要正文，不要 markdown 代码块。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        ).strip()[:SUMMARY_MAX_CHARS]
    except LLMError:
        merged = "\n".join(lines)
        return merged[:SUMMARY_MAX_CHARS]


def summarize_history_batch(existing_summary: str, batch: list[dict[str, Any]]) -> str:
    lines = [line for item in batch if (line := compact_history_line(item, verbose=True))]
    if not lines:
        return existing_summary.strip()

    prior = (existing_summary or "").strip()
    prompt = (
        "你是 Sales CRM Pi 助手的对话压缩器。将「待压缩片段」合并进「已有摘要」，输出更新后的摘要。\n"
        "必须保留：用户目标、已查 ASN/组织、线索数量、导入结果、关键决策、待办、失败原因。\n"
        "用中文条目化，不要寒暄，不超过 800 字。\n\n"
        f"已有摘要：\n{prior or '（无）'}\n\n"
        f"待压缩片段：\n" + "\n".join(lines)
    )
    try:
        updated = chat_completion_summary(
            [
                {"role": "system", "content": "你只输出压缩后的摘要正文，不要 markdown 代码块。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        ).strip()
    except LLMError:
        merged = (prior + "\n" + "\n".join(lines)).strip()
        return merged[:SUMMARY_MAX_CHARS]
    return updated[:SUMMARY_MAX_CHARS]


def model_context_limit(model: str) -> int:
    name = (model or "").strip().lower()
    # DeepSeek V4: 1M context — https://api-docs.deepseek.com/zh-cn/quick_start/pricing
    if "deepseek" in name:
        return 1_000_000
    if any(token in name for token in ("gpt-4", "gpt-4o", "claude", "glm-4", "qwen", "moonshot")):
        return 128_000
    return 64_000


def context_stats(
    history: list[dict[str, Any]],
    *,
    context_summary: str = "",
    summary_through: int = 0,
    system_chars: int = 0,
    tools_chars: int = 0,
    model: str = "",
) -> dict[str, int | bool]:
    llm_messages = build_llm_messages(
        history,
        context_summary=context_summary,
        summary_through=summary_through,
    )
    message_chars = sum(len(str(m.get("content") or "")) for m in llm_messages)
    summary = (context_summary or "").strip()
    compressed = bool(summary) or int(summary_through or 0) > 0
    middle_count = max(
        0, len(history) - max(int(summary_through or 0), 0) - MAX_RECENT_FULL_MESSAGES
    )
    overhead = max(0, int(system_chars)) + max(0, int(tools_chars))
    if compressed and not overhead:
        overhead = 15_000
    char_estimate = message_chars + overhead
    token_estimate = max(1, char_estimate // 3)
    context_limit = model_context_limit(model)
    usage_percent = min(100, round(token_estimate * 100 / context_limit)) if context_limit else 0
    compress_threshold = MAX_RECENT_FULL_MESSAGES + SUMMARIZE_TRIGGER_GAP
    return {
        "stored_messages": len(history),
        "llm_message_count": len(llm_messages),
        "char_estimate": char_estimate,
        "token_estimate": token_estimate,
        "context_limit": context_limit,
        "usage_percent": usage_percent,
        "summary_through": max(0, int(summary_through or 0)),
        "recent_full_window": MAX_RECENT_FULL_MESSAGES,
        "compressed": compressed,
        "summary_chars": len(summary),
        "middle_tier_messages": middle_count,
        "compress_threshold": compress_threshold,
        "needs_compression": len(history) > compress_threshold,
    }
