from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from app.llm import LLMError, plan_lead_search, score_leads
from app.peeringdb import discover_asns
from arin_lookup import lookup_asn


def _row_has_preferred_role(row: dict[str, Any], preferred_roles: list[str]) -> bool:
    roles = row.get("roles") or []
    if not preferred_roles:
        return bool(row.get("email"))
    return any(role in preferred_roles for role in roles)


def _contact_candidates(rows: list[dict[str, Any]], preferred_roles: list[str]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for row in rows:
        if row.get("error") or not row.get("email"):
            continue
        if preferred_roles and not _row_has_preferred_role(row, preferred_roles):
            continue
        candidates.append(row)
    if candidates:
        return candidates

    for row in rows:
        if row.get("error") or not row.get("email"):
            continue
        candidates.append(row)
    return candidates


async def discover_leads_stream(
    user_query: str,
    *,
    min_score: int = 60,
    delay: float = 0.5,
    auto_import: bool = False,
    user_id: int | None = None,
) -> AsyncIterator[dict[str, Any]]:
    yield {"type": "status", "message": "正在理解你的需求…"}

    try:
        plan = await asyncio.to_thread(plan_lead_search, user_query)
    except LLMError as exc:
        yield {"type": "error", "message": str(exc)}
        return

    yield {"type": "plan", "plan": plan}

    keywords = plan.get("keywords") or []
    max_asns = plan.get("max_asns", 15)
    preferred_roles = plan.get("preferred_roles") or []

    yield {"type": "status", "message": f"正在 PeeringDB 搜索：{', '.join(keywords)}"}

    networks = await asyncio.to_thread(discover_asns, keywords, max_asns=max_asns)
    if not networks:
        yield {"type": "error", "message": "未找到匹配的网络，请调整描述后重试"}
        return

    yield {"type": "networks", "networks": networks, "total": len(networks)}

    all_candidates: list[dict[str, Any]] = []
    total = len(networks)

    for index, network in enumerate(networks):
        asn = network["asn"]
        yield {
            "type": "progress",
            "index": index + 1,
            "total": total,
            "asn": asn,
            "network": network.get("name") or "",
            "message": f"正在查询 AS{asn}",
        }

        rows = await asyncio.to_thread(lookup_asn, asn)
        row_dicts = [row.to_dict() for row in rows]
        candidates = _contact_candidates(row_dicts, preferred_roles)

        for candidate in candidates:
            candidate["source"] = "ai-lead"
            candidate["network_name"] = network.get("name") or ""
            candidate["matched_keyword"] = network.get("keyword") or ""

        all_candidates.extend(candidates)

        yield {
            "type": "asn_result",
            "asn": asn,
            "network": network.get("name") or "",
            "rows": row_dicts,
            "candidate_count": len(candidates),
        }

        if index + 1 < total and delay:
            await asyncio.sleep(delay)

    if not all_candidates:
        yield {"type": "done", "leads": [], "import": None, "message": "未找到可评分的 ARIN 邮箱联系人"}
        return

    yield {"type": "status", "message": f"AI 正在评估 {len(all_candidates)} 条候选线索…"}

    try:
        scored = await asyncio.to_thread(score_leads, user_query, plan, all_candidates)
    except LLMError as exc:
        yield {"type": "error", "message": str(exc)}
        return

    leads = [row for row in scored if row.get("lead_relevant") and row.get("lead_score", 0) >= min_score]
    leads.sort(key=lambda item: item.get("lead_score", 0), reverse=True)

    for lead in leads:
        yield {"type": "lead", "lead": lead}

    import_result = None
    if auto_import and user_id and leads:
        from app.database import import_contacts

        payload = []
        for lead in leads:
            notes = f"AI评分 {lead.get('lead_score', 0)} · {lead.get('lead_reason', '')}".strip(" ·")
            payload.append(
                {
                    **lead,
                    "source": "ai-lead",
                    "notes": notes,
                }
            )
        import_result = await asyncio.to_thread(import_contacts, user_id, payload)

    yield {
        "type": "done",
        "leads": leads,
        "import": import_result,
        "message": f"完成，共找到 {len(leads)} 条高匹配线索",
    }
