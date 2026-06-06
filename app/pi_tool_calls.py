"""Pure tool-call parsing, normalization, and recovery for the Pi agent."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

KNOWN_TOOL_NAMES = {
    "list_contacts",
    "import_leads",
    "get_contact",
    "update_contact",
    "mark_contact_sent",
    "delete_contacts",
    "add_contact_note",
    "list_contact_notes",
    "get_lead_preferences",
    "reset_lead_preferences",
    "dedupe_contacts",
    "get_import_filters",
    "update_import_filters",
    "list_schedules",
    "create_schedule",
    "update_schedule",
    "get_search_config",
    "shodan_search",
    "web_search",
    "fetch_web_pages",
    "search_hosting_forums",
    "lookup_asns",
    "discover_leads",
    "enrich_contact",
    "collect_linkedin_profiles",
    "collect_x_profiles",
    "collect_facebook_profiles",
}

_TOOL_NAME_ALIASES = {
    "search_contacts": "list_contacts",
    "list_contact": "list_contacts",
    "find_contacts": "list_contacts",
    "delete_contact": "delete_contacts",
    "remove_contacts": "delete_contacts",
    "bulk_delete_contacts": "delete_contacts",
}


def _normalize_tool_name(name: str) -> str:
    cleaned = (name or "").strip().lower()
    for prefix in ("functions.", "function.", "tool.", "tools."):
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix) :]
    if "." in cleaned and cleaned not in KNOWN_TOOL_NAMES:
        tail = cleaned.rsplit(".", 1)[-1]
        if tail in KNOWN_TOOL_NAMES or tail in _TOOL_NAME_ALIASES:
            cleaned = tail
    return cleaned


def _infer_tool_name(name: str, args: dict[str, Any]) -> str:
    cleaned = _normalize_tool_name(name)
    if cleaned in KNOWN_TOOL_NAMES:
        return cleaned
    if cleaned in _TOOL_NAME_ALIASES:
        return _TOOL_NAME_ALIASES[cleaned]
    if "contact_ids" in args or "ids" in args:
        return "delete_contacts"
    if "queries" in args or ("query" in args and "q" not in args and "max_results" in args):
        return "web_search"
    if "text" in args or "asns" in args:
        return "lookup_asns"
    if "contact_id" in args and ("auto_import" in args or "min_score" in args):
        return "enrich_contact"
    if "contact_id" in args and "note" in args:
        return "add_contact_note"
    if "contact_id" in args and "sent" in args:
        return "mark_contact_sent"
    if "contact_id" in args and not args.get("q"):
        return "get_contact"
    if "rows" in args:
        return "import_leads"
    if "keywords" in args or "keyword" in args:
        return "list_contacts"
    if "q" in args or ("limit" in args and "query" not in args and "queries" not in args):
        return "list_contacts"
    return cleaned or "unknown"


def _coerce_list_contacts_args(args: dict[str, Any]) -> dict[str, Any]:
    if "q" in args:
        return args
    for key in ("keywords", "keyword", "search", "query", "term", "filter"):
        if key not in args:
            continue
        val = args[key]
        if isinstance(val, list):
            args["q"] = " ".join(str(item) for item in val if item)
        else:
            args["q"] = str(val)
        break
    return args


def _normalize_raw_tool_entry(item: dict[str, Any]) -> dict[str, Any]:
    fn = item.get("function")
    if isinstance(fn, str):
        try:
            fn = json.loads(fn)
        except json.JSONDecodeError:
            fn = {}
    if isinstance(fn, dict) and fn.get("name"):
        args = fn.get("arguments")
        if isinstance(args, dict):
            args_str = json.dumps(args, ensure_ascii=False)
        else:
            args_str = str(args or "{}")
        return {
            "id": str(item.get("id") or f"inline-{uuid.uuid4().hex[:8]}"),
            "type": "function",
            "function": {"name": str(fn["name"]), "arguments": args_str},
        }
    name = str(item.get("name") or "").strip()
    raw_args = item.get("arguments")
    if isinstance(raw_args, dict):
        args_str = json.dumps(raw_args, ensure_ascii=False)
    elif raw_args is not None:
        args_str = str(raw_args)
    else:
        args_str = "{}"
    return {
        "id": str(item.get("id") or f"inline-{uuid.uuid4().hex[:8]}"),
        "type": "function",
        "function": {"name": name, "arguments": args_str},
    }


def _extract_tool_calls_from_content(text: str) -> list[dict[str, Any]]:
    text = (text or "").strip()
    if not text:
        return []

    start = text.find("[")
    if start >= 0:
        blob = text[start:]
        for end in range(len(blob), 0, -1):
            if blob[end - 1] not in "}]":
                continue
            try:
                parsed = json.loads(blob[:end])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, list):
                calls = [item for item in parsed if isinstance(item, dict)]
                if calls:
                    return [_normalize_raw_tool_entry(item) for item in calls]

    args = _extract_json_args(text)
    if args:
        name = _infer_tool_name("", args)
        if name != "unknown":
            return [_normalize_raw_tool_entry({"name": name, "arguments": args})]

    name_match = re.search(r'"name"\s*:\s*"([a-zA-Z0-9_]+)"', text)
    if name_match:
        return [
            _normalize_raw_tool_entry(
                {"name": name_match.group(1), "arguments": _extract_json_args(text)}
            )
        ]
    return []


def _parse_tool_call(tool_call: dict[str, Any]) -> tuple[str, dict[str, Any]] | None:
    """Normalize provider-specific tool_call payloads; skip empty/invalid calls."""
    fn = tool_call.get("function")
    if isinstance(fn, str):
        try:
            fn = json.loads(fn)
        except json.JSONDecodeError:
            fn = {}
    if not isinstance(fn, dict):
        fn = {}

    name = str(fn.get("name") or tool_call.get("name") or "").strip()
    raw_args = fn.get("arguments")
    if raw_args is None:
        raw_args = tool_call.get("arguments") or "{}"
    if isinstance(raw_args, dict):
        args = raw_args
    else:
        try:
            args = json.loads(raw_args) if raw_args else {}
        except json.JSONDecodeError:
            args = {}
    if not isinstance(args, dict):
        args = {}

    if (not name or name == "unknown") and isinstance(raw_args, str) and raw_args.strip():
        name_match = re.search(r'"name"\s*:\s*"([a-zA-Z0-9_]+)"', raw_args)
        if name_match:
            name = name_match.group(1)
        try:
            nested = json.loads(raw_args)
        except json.JSONDecodeError:
            nested = None
        if isinstance(nested, dict):
            if nested.get("name"):
                name = str(nested["name"])
            nested_args = nested.get("arguments")
            if isinstance(nested_args, dict):
                args = nested_args
            elif isinstance(nested_args, str):
                try:
                    parsed_args = json.loads(nested_args)
                    if isinstance(parsed_args, dict):
                        args = parsed_args
                except json.JSONDecodeError:
                    pass
            elif "name" not in nested:
                args = nested

    name = _infer_tool_name(name, args)
    if name == "list_contacts":
        args = _coerce_list_contacts_args(args)
    if name == "unknown":
        return None
    return name, args


def _ensure_tool_call_id(tool_call: dict[str, Any]) -> str:
    tool_id = str(tool_call.get("id") or "").strip()
    if not tool_id:
        tool_id = f"call_{uuid.uuid4().hex[:12]}"
        tool_call["id"] = tool_id
    return tool_id


def _prepare_tool_calls(
    tool_calls: list[Any],
) -> list[tuple[dict[str, Any], str, dict[str, Any]]]:
    """Resolve tool calls and drop invalid entries before OpenAI-style message assembly."""
    prepared: list[tuple[dict[str, Any], str, dict[str, Any]]] = []
    for raw in tool_calls:
        if not isinstance(raw, dict):
            continue
        parsed = _parse_tool_call(raw)
        if not parsed:
            continue
        name, args = parsed
        tool_call = dict(raw)
        _ensure_tool_call_id(tool_call)
        fn = tool_call.get("function")
        if not isinstance(fn, dict):
            fn = {}
        tool_call["function"] = {
            "name": name,
            "arguments": json.dumps(args, ensure_ascii=False),
        }
        tool_call["type"] = tool_call.get("type") or "function"
        prepared.append((tool_call, name, args))
    return prepared


def _extract_json_args(text: str) -> dict[str, Any]:
    start = text.find("{")
    if start < 0:
        return {}
    blob = text[start:]
    blob = re.sub(r"<\|[^|>]*\|>", "", blob, flags=re.I)
    blob = re.sub(r"<\s*/?\s*\|\s*\|[^>]*>", "", blob, flags=re.I)
    blob = blob.strip()
    for end in range(len(blob), 0, -1):
        if blob[end - 1] != "}":
            continue
        try:
            parsed = json.loads(blob[:end])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}
