"""Find additional contacts related to an existing CRM contact."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from arin_lookup import lookup_asn
from app.database import get_contact, import_contacts, list_contact_emails, update_contact_social_fields
from app.lead_discovery import _contact_candidates, _dedupe_candidates
from app.llm import LLMError, extract_leads_from_web, score_leads
from app.lead_preferences import (
    effective_min_score,
    filter_avoided_candidates,
    get_prefs,
    preference_hints_for_llm,
)
from app.sources import peeringdb as peeringdb_source
from app.sources import web_search
from app.sources import brightdata_social as bs
from app.sources.social_registry import SOCIAL_CHANNELS, extract_all_social_urls_from_web_results
from app.social_contacts import enrich_candidates_with_social

GENERIC_EMAIL_DOMAINS = frozenset(
    {
        "gmail.com",
        "yahoo.com",
        "hotmail.com",
        "outlook.com",
        "icloud.com",
        "proton.me",
        "protonmail.com",
    }
)


def _email_domain(email: str) -> str:
    email = (email or "").strip().lower()
    if "@" not in email:
        return ""
    return email.split("@", 1)[1]


def _build_enrich_queries(contact: dict[str, Any]) -> list[str]:
    org = (contact.get("org") or "").strip()
    domain = _email_domain(contact.get("email") or "")
    asn = contact.get("asn")
    queries: list[str] = []

    if org:
        queries.append(f"{org} peering contact email")
        queries.append(f"{org} network operations noc abuse email")
    if domain and domain not in GENERIC_EMAIL_DOMAINS:
        queries.append(f"site:{domain} peering contact email")
    if asn:
        label = f"AS{asn}"
        if org:
            label = f"{label} {org}"
        queries.append(f"{label} peering desk email")

    seen: set[str] = set()
    unique: list[str] = []
    for query in queries:
        key = query.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(query)
    return unique[:5]


def _enrich_user_query(contact: dict[str, Any]) -> str:
    org = contact.get("org") or "该组织"
    email = contact.get("email") or ""
    asn = contact.get("asn")
    parts = [f"为 {org} 找更多网络/peering/运营相关联系人"]
    if email:
        parts.append(f"已有邮箱 {email}，需要同一组织或同一 ASN 的其他 role 邮箱")
    if asn:
        parts.append(f"ASN AS{asn}")
    parts.append("优先 abuse、peering、noc、technical、administrative")
    return "；".join(parts)


def _row_from_rdap(row: dict[str, Any], *, contact: dict[str, Any], network_name: str = "") -> dict[str, Any]:
    roles = row.get("roles") or []
    if isinstance(roles, str):
        roles = [part.strip() for part in roles.split(",") if part.strip()]
    return {
        "asn": row.get("asn") or contact.get("asn"),
        "org": row.get("org") or contact.get("org") or "",
        "name": row.get("name") or "",
        "email": (row.get("email") or "").lower(),
        "roles": roles,
        "handle": row.get("handle") or "",
        "rir": row.get("rir") or "",
        "source": "contact-enrich-rdap",
        "source_detail": f"RDAP 扩展 · {network_name or contact.get('org') or ''}".strip(" ·"),
    }


def _email_related_to_contact(email: str, contact: dict[str, Any]) -> bool:
    email = email.lower()
    anchor = (contact.get("email") or "").lower()
    if not email or email == anchor:
        return False
    domain = _email_domain(anchor)
    if domain and domain not in GENERIC_EMAIL_DOMAINS and email.endswith(f"@{domain}"):
        return True
    org = (contact.get("org") or "").lower()
    if org and len(org) >= 4 and org in email:
        return True
    return False


async def enrich_contact_stream(
    user_id: int,
    contact_id: int,
    *,
    min_score: int = 50,
    auto_import: bool = False,
) -> AsyncIterator[dict[str, Any]]:
    contact = get_contact(user_id, contact_id)
    if not contact:
        yield {"type": "error", "message": "联系人不存在"}
        return

    anchor_email = (contact.get("email") or "").lower()
    if not anchor_email:
        yield {"type": "error", "message": "该联系人没有邮箱，无法作为扩展锚点"}
        return

    prefs = get_prefs(user_id)
    preference_hints = preference_hints_for_llm(prefs)
    score_threshold = effective_min_score(prefs, min_score)

    known_emails = list_contact_emails(user_id)
    enrich_query = _enrich_user_query(contact)

    yield {
        "type": "status",
        "message": f"正在扩展联系人 #{contact_id}（{anchor_email}）…",
    }
    yield {
        "type": "anchor",
        "contact": contact,
    }
    yield {
        "type": "plan",
        "plan": {
            "summary": enrich_query,
            "target_profile": f"与 {contact.get('org') or anchor_email} 相关的其他联系方式",
            "keywords": [contact.get("org") or ""],
            "web_queries": _build_enrich_queries(contact),
            "preferred_roles": ["abuse", "peering", "noc", "technical", "administrative", "routing"],
        },
    }

    candidates: list[dict[str, Any]] = []
    asn_targets: list[dict[str, Any]] = []

    if contact.get("asn"):
        asn_targets.append(
            {
                "asn": int(contact["asn"]),
                "name": contact.get("org") or "",
                "source": "anchor",
                "keyword": "contact",
            }
        )

    org = (contact.get("org") or "").strip()
    if org:
        networks = await asyncio.to_thread(peeringdb_source.discover_asns, [org], max_asns=3)
        yield {
            "type": "source_result",
            "source": "peeringdb",
            "count": len(networks),
            "preview": [f"AS{n['asn']} {n.get('name', '')}" for n in networks[:5]],
        }
        for net in networks:
            if net["asn"] not in {item["asn"] for item in asn_targets}:
                asn_targets.append(net)

    queries = _build_enrich_queries(contact)
    web_results: list[dict[str, str]] = []
    if queries:
        web_results = await asyncio.to_thread(web_search.search_web_many, queries, max_results_per_query=5)
        yield {
            "type": "source_result",
            "source": "web_search",
            "count": len(web_results),
            "preview": [r.get("title") or r.get("url") or "" for r in web_results[:5]],
        }

    signals = web_search.extract_signals_from_results(web_results)
    social_profiles_by_channel: dict[str, list[dict[str, Any]]] = {}
    found_social_urls = extract_all_social_urls_from_web_results(web_results)
    for spec in SOCIAL_CHANNELS:
        urls = found_social_urls.get(spec.key) or []
        if not bs.is_channel_configured(spec) or not urls:
            continue
        yield {
            "type": "status",
            "message": f"{spec.label} 补充抓取 {min(len(urls), 5)} 个 profile…",
        }
        try:
            profiles = await asyncio.to_thread(
                bs.collect_profiles_by_url,
                spec,
                urls,
                max_urls=5,
            )
            social_profiles_by_channel[spec.key] = profiles
            for profile in profiles:
                web_results.append(spec.to_web_result(profile))
        except Exception as exc:
            yield {"type": "status", "message": f"{spec.label} 抓取跳过：{exc}"}

    enriched_anchor = enrich_candidates_with_social(
        [contact],
        web_results=web_results,
        profiles_by_channel=social_profiles_by_channel,
    )[0]
    social_patch = {
        key: enriched_anchor.get(key) or ""
        for key in ("linkedin", "x", "facebook")
        if enriched_anchor.get(key) and not (contact.get(key) or "")
    }
    if social_patch:
        update_contact_social_fields(user_id, contact_id, **social_patch)
        contact.update(social_patch)
        yield {"type": "status", "message": "已补充社交 profile 链接"}

    for signal_asn in signals["asns"]:
        if signal_asn not in {item["asn"] for item in asn_targets}:
            asn_targets.append(
                {
                    "asn": signal_asn,
                    "name": org,
                    "source": "web-search",
                    "keyword": "regex",
                }
            )

    yield {
        "type": "source_result",
        "source": "web_regex",
        "count": len(signals["emails"]) + len(signals["asns"]),
        "preview": [f"emails={len(signals['emails'])}, asns={len(signals['asns'])}"],
    }

    mini_plan = {
        "target_profile": enrich_query,
        "preferred_roles": ["abuse", "peering", "noc", "technical", "administrative", "routing"],
    }

    web_leads: list[dict[str, Any]] = []
    if web_results or signals["emails"]:
        try:
            web_leads = await asyncio.to_thread(
                extract_leads_from_web,
                enrich_query,
                mini_plan,
                web_results,
                signals["emails"],
                signals["asns"],
            )
        except LLMError as exc:
            yield {"type": "status", "message": f"网页线索提取部分失败：{exc}"}

    for lead in web_leads:
        email = (lead.get("email") or "").lower()
        if not email or email in known_emails:
            continue
        if not _email_related_to_contact(email, contact):
            continue
        lead.setdefault("org", contact.get("org") or "")
        lead.setdefault("asn", contact.get("asn"))
        lead["source"] = lead.get("source") or "contact-enrich-web"
        candidates.append(lead)

    yield {"type": "source_result", "source": "llm_extract", "count": len(web_leads), "preview": []}

    total = len(asn_targets)
    for index, network in enumerate(asn_targets):
        asn = int(network["asn"])
        yield {
            "type": "progress",
            "index": index + 1,
            "total": total,
            "asn": asn,
            "network": network.get("name") or "",
            "message": f"RDAP 扩展 AS{asn}",
        }

        rows = await asyncio.to_thread(lookup_asn, asn)
        row_dicts = [row.to_dict() for row in rows]
        rdap_rows = _contact_candidates(row_dicts, mini_plan["preferred_roles"])

        for row in rdap_rows:
            email = (row.get("email") or "").lower()
            if not email or email == anchor_email or email in known_emails:
                continue
            candidates.append(_row_from_rdap(row, contact=contact, network_name=network.get("name") or ""))

        yield {
            "type": "asn_result",
            "asn": asn,
            "network": network.get("name") or "",
            "rows": row_dicts,
            "candidate_count": len(rdap_rows),
        }

    candidates = _dedupe_candidates(candidates)
    candidates = [
        row
        for row in candidates
        if row.get("email") and row["email"].lower() not in known_emails and row["email"].lower() != anchor_email
    ]
    candidates = enrich_candidates_with_social(
        candidates,
        web_results=web_results,
        profiles_by_channel=social_profiles_by_channel,
    )
    candidates = filter_avoided_candidates(candidates, prefs)

    if not candidates:
        yield {
            "type": "done",
            "leads": [],
            "import": None,
            "message": "未找到该联系人的其他可用邮箱（可能已全部在 CRM 中）",
            "anchor_contact_id": contact_id,
        }
        return

    yield {"type": "status", "message": f"AI 正在评估 {len(candidates)} 条相关联系人…"}

    try:
        scored = await asyncio.to_thread(
            score_leads,
            enrich_query,
            mini_plan,
            candidates,
            preference_hints=preference_hints,
        )
    except LLMError as exc:
        yield {"type": "error", "message": str(exc)}
        return

    leads = [
        row for row in scored if row.get("lead_relevant") and row.get("lead_score", 0) >= score_threshold
    ]
    leads.sort(key=lambda item: item.get("lead_score", 0), reverse=True)

    for lead in leads:
        note_parts = [
            f"扩展自联系人 #{contact_id}",
            anchor_email,
            f"评分 {lead.get('lead_score', 0)}",
            lead.get("lead_reason") or "",
        ]
        lead["notes"] = " · ".join(part for part in note_parts if part).strip(" ·")
        lead["source"] = lead.get("source") or "contact-enrich"
        yield {"type": "lead", "lead": lead}

    import_result = None
    if auto_import and leads:
        payload = [{**lead, "source": lead.get("source") or "contact-enrich"} for lead in leads]
        import_result = await asyncio.to_thread(import_contacts, user_id, payload)

    yield {
        "type": "done",
        "leads": leads,
        "import": import_result,
        "message": f"完成，为 #{contact_id} 找到 {len(leads)} 条其他联系方式",
        "anchor_contact_id": contact_id,
    }
