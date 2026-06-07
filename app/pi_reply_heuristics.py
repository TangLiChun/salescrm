"""Heuristics that classify LLM replies and build fallback tool calls for the Pi agent."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from app.pi_tool_calls import _extract_json_args, _infer_tool_name, _prepare_tool_calls

# Markers that unambiguously begin a machine tool-call payload leaking into the
# assistant's text content. Kept deliberately narrow: only patterns that start a
# JSON tool-call object/array or a known special-token block. Bare keys like
# '"name":' or '"arguments"' and the old '\n['/startswith('[') heuristics were
# removed because they silently truncate ordinary prose (markdown links, "[1]"
# references, bracketed labels, JSON examples), which made the agent appear to
# "reply a few words then stop".
_TOOL_CONTENT_MARKERS = (
    "[{",
    "[工具",
    "[tool",
    "tool_calls",
    "tool_call",
    "dsml",
    "<|",
    "<｜",
    "```json",
    '{"query',
    '{"queries',
    '{"name"',
    '{"function"',
)


def _assistant_intro_before_tools(content: str) -> str:
    text = (content or "").strip()
    if not text:
        return ""
    lower = text.lower()
    cut_at = len(text)
    for marker in _TOOL_CONTENT_MARKERS:
        idx = lower.find(marker.lower())
        if idx >= 0:
            cut_at = min(cut_at, idx)
    result = text[:cut_at].strip()
    if result.endswith("["):
        result = result[:-1].rstrip()
    return result


def _content_looks_like_tool_call(content: str) -> bool:
    lower = (content or "").lower()
    if any(marker in lower for marker in _TOOL_CONTENT_MARKERS):
        return True
    return bool(re.search(r"^\s*[\[{]", content or ""))


def _content_is_tool_json_fragment(content: str) -> bool:
    text = (content or "").strip()
    if not text:
        return False
    if text in ("[", "{", "(", "[{", "({"):
        return True
    if re.fullmatch(r"[\[\{\(,]+", text):
        return True
    # Short JSON-looking fragment, e.g. '[{' or '{"q' — but NOT bracketed prose
    # like "[已完成] 已导入 3 条线索。". Require a JSON opener right after the
    # leading bracket/brace.
    if re.match(r'^[\[\{]\s*["\[\{]', text) and len(text) < 24:
        return True
    return False


def _meaningful_assistant_content(content: str) -> str:
    visible = _assistant_intro_before_tools(content)
    if not visible or _content_is_tool_json_fragment(visible):
        return ""
    return visible


def _assistant_promises_tool_use(content: str) -> bool:
    text = (content or "").strip()
    if not text:
        return False
    if text.endswith(("：", ":", "…", "...")):
        return True
    lower = text.lower()
    markers = (
        "我先",
        "让我",
        "我来",
        "正在",
        "接下来",
        "马上",
        "这就",
        "帮你查",
        "帮你搜",
        "拉一下",
        "补查",
        "再扫",
        "再查",
        "再搜",
        "再找",
        "继续",
        "接着",
        "开始搜",
        "开始查",
        "去搜",
        "去查",
        "搜索 crm",
        "查一下",
        "筛出",
        "搜索更多",
        "继续搜索",
        "继续查找",
        "再看看",
        "找找",
    )
    if any(marker in lower for marker in markers):
        return True
    if len(text) <= 120 and any(
        verb in text for verb in ("搜索", "查找", "查询", "筛选", "挖掘", "扩展")
    ):
        if any(
            prefix in text for prefix in ("好的", "行", "嗯", "OK", "ok", "继续", "马上", "正在")
        ):
            return True
    return False


def _user_requests_continuation(message: str) -> bool:
    text = (message or "").strip()
    if not text or len(text) > 48:
        return False
    lower = text.lower()
    markers = (
        "继续",
        "再看看",
        "再看",
        "还有吗",
        "再来",
        "接着",
        "再搜",
        "再查",
        "再找",
        "更多",
        "continue",
        "more",
    )
    return any(marker in lower for marker in markers)


def _infer_continuation_query(history: list[dict[str, Any]], user_message: str) -> str:
    substantive: list[str] = []
    saw_discover = False
    for item in history:
        role = item.get("role")
        if role == "user":
            content = str(item.get("content") or "").strip()
            if content and not _user_requests_continuation(content):
                substantive.append(content)
        elif role == "tool" and item.get("name") == "discover_leads":
            saw_discover = True

    if not substantive and not saw_discover:
        return ""

    base = substantive[-1] if substantive else "扩展线索搜索，找更多符合条件的组织和联系人"
    if not _user_requests_continuation(user_message):
        return base

    lead_tokens = ("线索", "公司", "isp", "运营商", "peering", "asn", "大企业", "大公司", "知名")
    lower_base = base.lower()
    if saw_discover or any(token in lower_base for token in lead_tokens):
        return f"{base}（用户要求继续，请扩展搜索范围并找更多结果）"
    return f"{base}（继续）"


def _make_discover_fallback_call(query: str) -> dict[str, Any]:
    return {
        "id": f"fallback-{uuid.uuid4().hex[:8]}",
        "type": "function",
        "function": {
            "name": "discover_leads",
            "arguments": json.dumps(
                {"query": query, "min_score": 60, "auto_import": True},
                ensure_ascii=False,
            ),
        },
    }


def _parse_inline_tool_calls(content: str) -> tuple[str, list[dict[str, Any]]]:
    text = (content or "").strip()
    if not text or not _content_looks_like_tool_call(text):
        return text, []

    intro = _assistant_intro_before_tools(text)
    name = "unknown"
    name_match = re.search(r"\[(?:工具|tool)[:\s]*([a-zA-Z0-9_]+)\]", text, re.I)
    if name_match:
        name = name_match.group(1)
    args = _extract_json_args(text)
    name = _infer_tool_name(name, args)
    if name == "unknown" and not args:
        return text, []

    tool_call = {
        "id": f"inline-{uuid.uuid4().hex[:8]}",
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(args, ensure_ascii=False),
        },
    }
    return intro, [tool_call]


def _fallback_prepared_calls(
    user_message: str,
    history: list[dict[str, Any]] | None = None,
) -> list[tuple[dict[str, Any], str, dict[str, Any]]]:
    """When the model keeps intro-only replies, run a sensible default CRM search."""
    text = (user_message or "").strip()
    lower = text.lower()
    if not text:
        return []

    if _user_requests_continuation(text):
        query = _infer_continuation_query(history or [], text)
        if query:
            return _prepare_tool_calls([_make_discover_fallback_call(query)])

    if _user_requests_continuation(text):
        raw_calls = [
            {
                "id": f"fallback-{uuid.uuid4().hex[:8]}",
                "type": "function",
                "function": {
                    "name": "list_contacts",
                    "arguments": json.dumps({"q": "", "limit": 100}, ensure_ascii=False),
                },
            }
        ]
        return _prepare_tool_calls(raw_calls)

    queries: list[str] = []
    if any(
        token in text for token in ("运营商", "operator", " isp", "isp ", "电信", "联通", "移动")
    ) or ("还有" in text and "其他" in text):
        queries = [
            "运营商",
            "ISP",
            "Telecom",
            "Network",
            "Transit",
            "Cogent",
            "Verizon",
            "AT&T",
            "TDS",
            "RCN",
            "GTT",
        ]
    elif "abuse" in lower:
        queries = ["abuse@"]
    elif any(token in text for token in ("联系人", "crm", "搜索", "找出", "列出", "还有")):
        queries = ["", "Network", "ISP"]

    if not queries:
        return []

    raw_calls = [
        {
            "id": f"fallback-{uuid.uuid4().hex[:8]}",
            "type": "function",
            "function": {
                "name": "list_contacts",
                "arguments": json.dumps({"q": query, "limit": 100}, ensure_ascii=False),
            },
        }
        for query in queries[:8]
    ]
    return _prepare_tool_calls(raw_calls)


_EMPTY_RESPONSE_NUDGE = (
    "（系统）请用中文回复用户，并调用合适的 CRM 工具完成任务，"
    "例如 list_contacts（搜索联系人）、delete_contacts（删除联系人）。"
)

_INTRO_ONLY_NUDGE = (
    "（系统）不要只回复开场白就停止。请立即调用 list_contacts、discover_leads、web_search、"
    "lookup_asns 等工具完成用户请求，然后再总结结果。"
)

_CONTINUE_NUDGE = (
    "（系统）用户要求继续上一任务。不要只回复「好的、继续」就结束。"
    "请立即调用 discover_leads、list_contacts、lookup_asns 等工具继续执行，然后再总结。"
)

_MAX_LLM_NUDGES = 2
