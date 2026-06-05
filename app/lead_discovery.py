from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from app.llm import LLMError, extract_leads_from_web, plan_lead_search, score_leads
from app.sources import list_channels
from app.sources import peeringdb as peeringdb_source
from app.sources import web_search
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


def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for row in candidates:
        email = (row.get("email") or "").lower()
        if email:
            key = f"email:{email}"
        else:
            key = f"asn:{row.get('asn')}:{row.get('org')}:{row.get('source')}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def _merge_asn_targets(
    networks: list[dict[str, Any]],
    web_asns: list[int],
    web_leads: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[int, dict[str, Any]] = {}
    for net in networks:
        merged[net["asn"]] = net
    for asn in web_asns:
        if asn not in merged:
            merged[asn] = {"asn": asn, "name": "", "source": "web-search", "keyword": "regex"}
    for lead in web_leads:
        asn = lead.get("asn")
        if asn and asn not in merged:
            merged[int(asn)] = {
                "asn": int(asn),
                "name": lead.get("org") or "",
                "source": "web-search",
                "keyword": "llm",
            }
    return list(merged.values())


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

    channels = list_channels()
    plan["channels"] = channels
    yield {"type": "plan", "plan": plan}

    keywords = plan.get("keywords") or []
    web_queries = plan.get("web_queries") or []
    max_asns = plan.get("max_asns", 15)
    preferred_roles = plan.get("preferred_roles") or []

    yield {
        "type": "status",
        "message": f"多渠道搜索中：搜索引擎({', '.join(channels['web_search'])}) · PeeringDB · 全球 RDAP",
    }

    peeringdb_task = asyncio.to_thread(peeringdb_source.discover_asns, keywords, max_asns=max_asns)
    web_task = asyncio.to_thread(
        web_search.search_web_many,
        web_queries,
        max_results_per_query=max(4, plan.get("max_web_results", 20) // max(len(web_queries), 1)),
    )
    networks, web_results = await asyncio.gather(peeringdb_task, web_task)

    yield {
        "type": "source_result",
        "source": "peeringdb",
        "count": len(networks),
        "preview": [f"AS{n['asn']} {n.get('name', '')}" for n in networks[:5]],
    }
    yield {
        "type": "source_result",
        "source": "web_search",
        "count": len(web_results),
        "preview": [r.get("title") or r.get("url") or "" for r in web_results[:5]],
    }

    signals = web_search.extract_signals_from_results(web_results)
    yield {
        "type": "source_result",
        "source": "web_regex",
        "count": len(signals["emails"]) + len(signals["asns"]),
        "preview": [f"emails={len(signals['emails'])}, asns={len(signals['asns'])}"],
    }

    web_leads: list[dict[str, Any]] = []
    try:
        web_leads = await asyncio.to_thread(
            extract_leads_from_web,
            user_query,
            plan,
            web_results,
            signals["emails"],
            signals["asns"],
        )
    except LLMError as exc:
        yield {"type": "status", "message": f"网页线索提取部分失败：{exc}"}

    for lead in web_leads:
        if lead.get("email"):
            lead.setdefault("source", "web-search")

    yield {"type": "source_result", "source": "llm_extract", "count": len(web_leads), "preview": []}

    asn_targets = _merge_asn_targets(networks, signals["asns"], web_leads)
    if not asn_targets and not web_leads:
        yield {"type": "error", "message": "所有渠道均未找到有效线索，请调整描述后重试"}
        return

    all_candidates: list[dict[str, Any]] = list(web_leads)
    total = len(asn_targets)

    for index, network in enumerate(asn_targets):
        asn = network["asn"]
        yield {
            "type": "progress",
            "index": index + 1,
            "total": total,
            "asn": asn,
            "network": network.get("name") or "",
            "message": f"RDAP 查询 AS{asn}",
        }

        rows = await asyncio.to_thread(lookup_asn, asn)
        row_dicts = [row.to_dict() for row in rows]
        candidates = _contact_candidates(row_dicts, preferred_roles)

        for candidate in candidates:
            candidate["source"] = "arin-rdap"
            candidate["source_detail"] = f"RDAP · {network.get('name') or ''}".strip(" ·")
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

    all_candidates = _dedupe_candidates(all_candidates)
    all_candidates = [row for row in all_candidates if row.get("email")]

    if not all_candidates:
        yield {"type": "done", "leads": [], "import": None, "message": "找到网络信息但未提取到可用邮箱联系人"}
        return

    yield {"type": "status", "message": f"AI 正在评估 {len(all_candidates)} 条跨渠道候选线索…"}

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
            source = lead.get("source") or "ai-lead"
            detail = lead.get("source_detail") or ""
            notes = f"AI评分 {lead.get('lead_score', 0)} · {lead.get('lead_reason', '')}"
            if detail:
                notes += f" · {detail}"
            payload.append({**lead, "source": source, "notes": notes.strip(" ·")})
        import_result = await asyncio.to_thread(import_contacts, user_id, payload)

    yield {
        "type": "done",
        "leads": leads,
        "import": import_result,
        "message": f"完成，跨渠道共找到 {len(leads)} 条高匹配线索",
    }


async def run_lead_discovery_batch(
    user_query: str,
    *,
    min_score: int = 60,
    delay: float = 0.5,
    auto_import: bool = False,
    user_id: int | None = None,
) -> dict:
    leads: list[dict[str, Any]] = []
    import_result = None
    error = None
    message = ""

    async for event in discover_leads_stream(
        user_query,
        min_score=min_score,
        delay=delay,
        auto_import=auto_import,
        user_id=user_id,
    ):
        event_type = event.get("type")
        if event_type == "error":
            error = event.get("message")
        elif event_type == "lead":
            leads.append(event["lead"])
        elif event_type == "done":
            leads = event.get("leads") or leads
            import_result = event.get("import")
            message = event.get("message") or ""

    return {
        "leads": leads,
        "import": import_result,
        "error": error,
        "message": message,
    }
