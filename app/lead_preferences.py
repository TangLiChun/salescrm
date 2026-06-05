from __future__ import annotations

import json
import re
from typing import Any

from app.db import get_conn

DEFAULT_PREFS: dict[str, Any] = {
    "min_score_hint": 60,
    "preferred_roles": [],
    "keyword_hints": [],
    "avoid_orgs": [],
    "avoid_domains": [],
    "liked_orgs": [],
    "role_weights": {},
    "stats": {
        "imports": 0,
        "invalid": 0,
        "interested": 0,
        "replied": 0,
        "contacted": 0,
        "deleted": 0,
    },
}

_ORG_STOPWORDS = frozenset(
    {
        "inc",
        "llc",
        "ltd",
        "corp",
        "corporation",
        "company",
        "co",
        "the",
        "and",
        "network",
        "networks",
        "communications",
        "telecom",
        "internet",
        "services",
        "service",
        "group",
        "global",
    }
)

_MAX_AVOID_DOMAINS = 50
_MAX_AVOID_ORGS = 30
_MAX_LIKED_ORGS = 25
_MAX_KEYWORD_HINTS = 12
_MAX_PREFERRED_ROLES = 5

_AI_SCORE_RE = re.compile(r"AI评分\s*(\d+)", re.IGNORECASE)
_ENRICH_SCORE_RE = re.compile(r"评分\s*(\d+)", re.IGNORECASE)


def _email_domain(email: str) -> str:
    email = (email or "").strip().lower()
    if "@" not in email:
        return ""
    return email.rsplit("@", 1)[-1]


def _normalize_roles(roles: object) -> list[str]:
    if isinstance(roles, list):
        parts = [str(item).strip() for item in roles if str(item).strip()]
    else:
        parts = [part.strip() for part in str(roles or "").split(",") if part.strip()]
    return parts


def _append_unique(items: list[str], value: str, *, limit: int) -> None:
    value = (value or "").strip()
    if not value:
        return
    lowered = value.lower()
    if any(existing.lower() == lowered for existing in items):
        return
    items.insert(0, value)
    del items[limit:]


def _merge_roles(preferred: list[str], weights: dict[str, int]) -> list[str]:
    ranked = sorted(
        weights.items(),
        key=lambda item: (-item[1], item[0]),
    )
    merged: list[str] = []
    for role, _count in ranked:
        if role not in merged:
            merged.append(role)
    for role in preferred:
        if role not in merged:
            merged.append(role)
    return merged[:_MAX_PREFERRED_ROLES]


def is_ai_lead_contact(contact: dict[str, Any]) -> bool:
    source = (contact.get("source") or "").strip().lower()
    notes = contact.get("notes") or ""
    if source in ("ai-lead", "contact-enrich", "contact-enrich-rdap"):
        return True
    if _AI_SCORE_RE.search(notes) or _ENRICH_SCORE_RE.search(notes):
        return True
    if "扩展自联系人" in notes:
        return True
    return False


def _extract_keyword_hints(row: dict[str, Any]) -> list[str]:
    hints: list[str] = []
    for key in ("matched_keyword", "network_name"):
        value = str(row.get(key) or "").strip().lower()
        if len(value) >= 3:
            hints.append(value)
    org = str(row.get("org") or "").strip()
    for token in re.split(r"[\s,/\-_.]+", org):
        token = token.lower().strip()
        if len(token) < 3 or token.isdigit() or token in _ORG_STOPWORDS:
            continue
        hints.append(token)
    return hints


def _merge_keyword_hints(prefs: dict[str, Any], hints: list[str]) -> bool:
    changed = False
    for hint in hints:
        before = len(prefs["keyword_hints"])
        _append_unique(prefs["keyword_hints"], hint, limit=_MAX_KEYWORD_HINTS)
        if len(prefs["keyword_hints"]) != before:
            changed = True
    return changed


def _parse_ai_score(notes: str) -> int | None:
    match = _AI_SCORE_RE.search(notes or "")
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def _coerce_prefs(raw: dict[str, Any] | None) -> dict[str, Any]:
    prefs = json.loads(json.dumps(DEFAULT_PREFS))
    if not raw:
        return prefs
    for key in DEFAULT_PREFS:
        if key in raw:
            prefs[key] = raw[key]
    stats = prefs.get("stats") or {}
    if not isinstance(stats, dict):
        stats = {}
    prefs["stats"] = {**DEFAULT_PREFS["stats"], **stats}
    for list_key in ("preferred_roles", "keyword_hints", "avoid_orgs", "avoid_domains", "liked_orgs"):
        value = prefs.get(list_key)
        if not isinstance(value, list):
            prefs[list_key] = []
        else:
            prefs[list_key] = [str(item).strip() for item in value if str(item).strip()]
    role_weights = prefs.get("role_weights")
    if not isinstance(role_weights, dict):
        prefs["role_weights"] = {}
    else:
        cleaned: dict[str, int] = {}
        for role, count in role_weights.items():
            role = str(role).strip()
            if not role:
                continue
            try:
                cleaned[role] = max(0, int(count))
            except (TypeError, ValueError):
                continue
        prefs["role_weights"] = cleaned
    try:
        prefs["min_score_hint"] = max(40, min(90, int(prefs.get("min_score_hint", 60))))
    except (TypeError, ValueError):
        prefs["min_score_hint"] = 60
    return prefs


def get_prefs(user_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT prefs_json FROM user_lead_preferences WHERE user_id = %s",
            (user_id,),
        ).fetchone()
    if not row:
        return _coerce_prefs(None)
    try:
        raw = json.loads(row["prefs_json"] or "{}")
    except json.JSONDecodeError:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    return _coerce_prefs(raw)


def reset_prefs(user_id: int) -> dict[str, Any]:
    with get_conn() as conn:
        conn.execute("DELETE FROM user_lead_preferences WHERE user_id = %s", (user_id,))
    return _coerce_prefs(None)


def save_prefs(user_id: int, prefs: dict[str, Any]) -> dict[str, Any]:
    normalized = _coerce_prefs(prefs)
    payload = json.dumps(normalized, ensure_ascii=False)
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO user_lead_preferences (user_id, prefs_json, updated_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (user_id) DO UPDATE
            SET prefs_json = EXCLUDED.prefs_json,
                updated_at = NOW()
            """,
            (user_id, payload),
        )
    return normalized


def _bump_role_weights(prefs: dict[str, Any], roles: list[str], *, amount: int = 1) -> None:
    weights = prefs.setdefault("role_weights", {})
    for role in roles:
        weights[role] = int(weights.get(role, 0)) + amount


def _adjust_min_score_hint(prefs: dict[str, Any], delta: int) -> None:
    prefs["min_score_hint"] = max(40, min(90, int(prefs.get("min_score_hint", 60)) + delta))


def record_import_feedback(user_id: int, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    prefs = get_prefs(user_id)
    stats = prefs["stats"]
    changed = False

    for row in rows:
        if not is_ai_lead_contact(row):
            continue
        changed = True
        stats["imports"] = int(stats.get("imports", 0)) + 1

        org = (row.get("org") or "").strip()
        if org:
            _append_unique(prefs["liked_orgs"], org, limit=_MAX_LIKED_ORGS)

        roles = _normalize_roles(row.get("roles"))
        if roles:
            _bump_role_weights(prefs, roles)
            prefs["preferred_roles"] = _merge_roles(prefs["preferred_roles"], prefs["role_weights"])

        score = _parse_ai_score(row.get("notes") or "")
        if score is not None and score >= 70:
            current = int(prefs.get("min_score_hint", 60))
            prefs["min_score_hint"] = max(current, min(score - 5, 85))

        if _merge_keyword_hints(prefs, _extract_keyword_hints(row)):
            changed = True

    if changed:
        save_prefs(user_id, prefs)


def record_search_feedback(user_id: int, user_query: str, plan: dict[str, Any]) -> None:
    prefs = get_prefs(user_id)
    changed = False

    for keyword in plan.get("keywords") or []:
        keyword = str(keyword).strip().lower()
        if len(keyword) >= 3 and _merge_keyword_hints(prefs, [keyword]):
            changed = True

    for token in re.split(r"[\s,;，；]+", user_query):
        token = token.strip().lower()
        if len(token) >= 4 and token not in _ORG_STOPWORDS and _merge_keyword_hints(prefs, [token]):
            changed = True

    if changed:
        save_prefs(user_id, prefs)


def record_status_feedback(user_id: int, contact: dict[str, Any], follow_up_status: str) -> None:
    if not is_ai_lead_contact(contact):
        return

    prefs = get_prefs(user_id)
    stats = prefs["stats"]
    email = (contact.get("email") or "").strip().lower()
    org = (contact.get("org") or "").strip()
    roles = _normalize_roles(contact.get("roles"))
    changed = True

    if follow_up_status == "invalid":
        stats["invalid"] = int(stats.get("invalid", 0)) + 1
        domain = _email_domain(email)
        if domain:
            _append_unique(prefs["avoid_domains"], domain, limit=_MAX_AVOID_DOMAINS)
        if org:
            _append_unique(prefs["avoid_orgs"], org, limit=_MAX_AVOID_ORGS)
        _adjust_min_score_hint(prefs, 2)
    elif follow_up_status == "interested":
        stats["interested"] = int(stats.get("interested", 0)) + 1
        if org:
            _append_unique(prefs["liked_orgs"], org, limit=_MAX_LIKED_ORGS)
        if roles:
            _bump_role_weights(prefs, roles, amount=2)
            prefs["preferred_roles"] = _merge_roles(prefs["preferred_roles"], prefs["role_weights"])
    elif follow_up_status == "replied":
        stats["replied"] = int(stats.get("replied", 0)) + 1
        if org:
            _append_unique(prefs["liked_orgs"], org, limit=_MAX_LIKED_ORGS)
        if roles:
            _bump_role_weights(prefs, roles, amount=3)
            prefs["preferred_roles"] = _merge_roles(prefs["preferred_roles"], prefs["role_weights"])
        _adjust_min_score_hint(prefs, -1)
    elif follow_up_status == "contacted":
        stats["contacted"] = int(stats.get("contacted", 0)) + 1
    else:
        changed = False

    if changed:
        save_prefs(user_id, prefs)


def record_delete_feedback(user_id: int, contact: dict[str, Any]) -> None:
    if not is_ai_lead_contact(contact):
        return

    prefs = get_prefs(user_id)
    stats = prefs["stats"]
    stats["deleted"] = int(stats.get("deleted", 0)) + 1

    email = (contact.get("email") or "").strip().lower()
    org = (contact.get("org") or "").strip()
    domain = _email_domain(email)
    if domain:
        _append_unique(prefs["avoid_domains"], domain, limit=_MAX_AVOID_DOMAINS)
    if org:
        _append_unique(prefs["avoid_orgs"], org, limit=_MAX_AVOID_ORGS)
    _adjust_min_score_hint(prefs, 1)
    save_prefs(user_id, prefs)


def preference_hints_for_llm(prefs: dict[str, Any]) -> str | None:
    lines: list[str] = []
    stats = prefs.get("stats") or {}

    preferred_roles = prefs.get("preferred_roles") or []
    if preferred_roles:
        lines.append(f"优先角色：{', '.join(preferred_roles)}")

    liked_orgs = prefs.get("liked_orgs") or []
    if liked_orgs:
        preview = "、".join(liked_orgs[:8])
        lines.append(f"用户曾导入或标记感兴趣的组织类型：{preview}")

    avoid_orgs = prefs.get("avoid_orgs") or []
    if avoid_orgs:
        preview = "、".join(avoid_orgs[:8])
        lines.append(f"用户标记无效或删除的组织，应降低优先级：{preview}")

    avoid_domains = prefs.get("avoid_domains") or []
    if avoid_domains:
        preview = "、".join(avoid_domains[:10])
        lines.append(f"避免这些邮箱域名：{preview}")

    keyword_hints = prefs.get("keyword_hints") or []
    if keyword_hints:
        lines.append(f"可复用的搜索关键词：{', '.join(keyword_hints[:8])}")

    min_hint = prefs.get("min_score_hint")
    if isinstance(min_hint, int) and min_hint > 60:
        lines.append(f"用户倾向更严格筛选，建议 min_score 不低于 {min_hint}")

    imports = int(stats.get("imports", 0))
    invalid = int(stats.get("invalid", 0))
    replied = int(stats.get("replied", 0))
    if imports >= 3 and invalid > 0:
        lines.append(f"历史反馈：导入 {imports} 条，标记无效 {invalid} 条，请更谨慎匹配目标画像")
    if replied > 0:
        lines.append(f"用户已有 {replied} 条回复记录，优先寻找类似组织与角色")

    if not lines:
        return None
    return "\n".join(lines)


def apply_prefs_to_plan(plan: dict[str, Any], prefs: dict[str, Any]) -> dict[str, Any]:
    merged = dict(plan)
    preferred = _merge_roles(prefs.get("preferred_roles") or [], prefs.get("role_weights") or {})
    if preferred:
        existing = [str(item).strip() for item in merged.get("preferred_roles") or [] if str(item).strip()]
        combined: list[str] = []
        for role in preferred + existing:
            if role not in combined:
                combined.append(role)
        merged["preferred_roles"] = combined[:_MAX_PREFERRED_ROLES]

    keyword_hints = prefs.get("keyword_hints") or []
    if keyword_hints:
        keywords = [str(item).strip() for item in merged.get("keywords") or [] if str(item).strip()]
        for hint in keyword_hints:
            if hint not in keywords:
                keywords.append(hint)
        merged["keywords"] = keywords[:8]

    min_hint = prefs.get("min_score_hint")
    if isinstance(min_hint, int):
        merged["min_score_hint"] = min_hint
    return merged


def effective_min_score(prefs: dict[str, Any], requested: int) -> int:
    hint = prefs.get("min_score_hint")
    if not isinstance(hint, int):
        return requested
    return max(requested, hint)


def filter_avoided_candidates(
    candidates: list[dict[str, Any]], prefs: dict[str, Any]
) -> list[dict[str, Any]]:
    avoid_domains = {item.lower() for item in prefs.get("avoid_domains") or [] if item}
    avoid_orgs = [item.lower() for item in prefs.get("avoid_orgs") or [] if item]
    if not avoid_domains and not avoid_orgs:
        return candidates

    filtered: list[dict[str, Any]] = []
    for candidate in candidates:
        email = (candidate.get("email") or "").strip().lower()
        domain = _email_domain(email)
        if domain and domain in avoid_domains:
            continue
        org = (candidate.get("org") or "").strip().lower()
        if org and any(token in org for token in avoid_orgs):
            continue
        filtered.append(candidate)
    return filtered
