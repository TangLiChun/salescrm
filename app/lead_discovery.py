from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

from app.lead_checkpoint import (
    PHASE_PLANNED,
    PHASE_RDAP_PROGRESS,
    PHASE_SCORED,
    PHASE_SOURCES_DONE,
    PHASE_WEB_EXTRACTED,
    checkpoint_resume_message,
    phase_at_least,
)
from app.llm import LLMError, extract_leads_from_web, plan_lead_search, score_leads
from app.lead_preferences import (
    apply_prefs_to_plan,
    effective_min_score,
    filter_avoided_candidates,
    get_prefs,
    preference_hints_for_llm,
    record_search_feedback,
)
from app.sources import list_channels
from app.sources import peeringdb as peeringdb_source
from app.sources import shodan as shodan_source
from app.sources import web_search
from app.sources import brightdata_social as bs
from app.sources import forums as forums_source
from app.sources import web_unlocker as web_unlocker_source
from app.sources.forum_registry import FORUM_CHANNELS
from app.sources.social_registry import SOCIAL_CHANNELS, extract_all_social_urls_from_web_results
from app.social_contacts import enrich_candidates_with_social
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
    checkpoint: dict[str, Any] | None = None,
    on_checkpoint: Callable[[dict[str, Any]], None] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    cp: dict[str, Any] = dict(checkpoint or {})
    phase = str(cp.get("phase") or "")

    prefs: dict[str, Any] = get_prefs(user_id) if user_id else {}
    preference_hints = preference_hints_for_llm(prefs) if user_id else None
    score_threshold = effective_min_score(prefs, min_score) if user_id else min_score

    def persist(next_phase: str, **fields: Any) -> None:
        nonlocal cp, phase
        cp = {
            **cp,
            **fields,
            "phase": next_phase,
            "query": user_query,
            "min_score": score_threshold,
        }
        phase = next_phase
        if on_checkpoint:
            on_checkpoint(dict(cp))

    resume_msg = checkpoint_resume_message(cp if phase else None)
    if resume_msg:
        yield {"type": "status", "message": resume_msg, "phase": phase}

    plan: dict[str, Any]
    if not phase_at_least(phase, PHASE_PLANNED):
        yield {"type": "status", "message": "正在理解你的需求…"}

        try:
            plan = await asyncio.to_thread(
                plan_lead_search, user_query, preference_hints=preference_hints
            )
        except LLMError as exc:
            yield {"type": "error", "message": str(exc)}
            return

        if user_id:
            plan = apply_prefs_to_plan(plan, prefs)
            if preference_hints:
                plan["preference_applied"] = True

        channels = list_channels()
        plan["channels"] = channels
        yield {"type": "plan", "plan": plan}
        persist(PHASE_PLANNED, plan=plan)
    else:
        plan = cp["plan"]
        yield {"type": "plan", "plan": plan}

    keywords = plan.get("keywords") or []
    web_queries = plan.get("web_queries") or []
    max_asns = plan.get("max_asns", 15)
    preferred_roles = plan.get("preferred_roles") or []

    networks: list[dict[str, Any]]
    web_results: list[dict[str, Any]]
    social_profiles_by_channel: dict[str, list[dict[str, Any]]]
    shodan_networks: list[dict[str, Any]]

    if not phase_at_least(phase, PHASE_SOURCES_DONE):
        channel_bits = [
            f"搜索引擎({', '.join(plan['channels']['web_search'])})",
            "PeeringDB",
            "全球 RDAP",
        ]
        if plan["channels"].get("shodan"):
            channel_bits.append("Shodan")
        if plan["channels"].get("web_unlocker"):
            channel_bits.append("Web Unlocker")
        for spec in SOCIAL_CHANNELS:
            if plan["channels"].get(spec.key):
                channel_bits.append(spec.label)
        for spec in FORUM_CHANNELS:
            if plan["channels"].get(spec.key):
                channel_bits.append(spec.label)
        yield {
            "type": "status",
            "message": f"多渠道搜索中：{' · '.join(channel_bits)}",
            "phase": PHASE_SOURCES_DONE,
        }

        peeringdb_task = asyncio.to_thread(peeringdb_source.discover_asns, keywords, max_asns=max_asns)
        web_task = asyncio.to_thread(
            web_search.search_web_many,
            web_queries,
            max_results_per_query=max(4, plan.get("max_web_results", 20) // max(len(web_queries), 1)),
        )
        forum_task = asyncio.to_thread(forums_source.discover_from_keywords, keywords)
        shodan_task = None
        if shodan_source.is_configured() and keywords:
            shodan_task = asyncio.to_thread(
                shodan_source.discover_from_keywords,
                keywords,
                max_networks=max_asns,
            )

        if shodan_task:
            networks, web_results, forum_results, shodan_bundle = await asyncio.gather(
                peeringdb_task, web_task, forum_task, shodan_task
            )
            shodan_networks, shodan_web = shodan_bundle
        else:
            networks, web_results, forum_results = await asyncio.gather(
                peeringdb_task, web_task, forum_task
            )
            shodan_networks, shodan_web = [], []

        if forum_results:
            seen_web = {(item.get("url") or "").strip() for item in web_results if item.get("url")}
            for item in forum_results:
                url = (item.get("url") or "").strip()
                if url and url not in seen_web:
                    seen_web.add(url)
                    web_results.append(item)

        if shodan_networks or shodan_web:
            seen_asn = {int(net["asn"]) for net in networks}
            for net in shodan_networks:
                if int(net["asn"]) not in seen_asn:
                    seen_asn.add(int(net["asn"]))
                    networks.append(net)
            web_results.extend(shodan_web)

        unlocker_summary: dict[str, Any] = {"fetched": 0, "urls": [], "errors": []}
        if web_unlocker_source.is_configured() and web_results:
            yield {
                "type": "status",
                "message": f"Web Unlocker 补充抓取页面正文（最多 {web_unlocker_source.max_urls_limit()} 个 URL）…",
            }
            try:
                unlocker_summary = await asyncio.to_thread(
                    web_unlocker_source.enrich_web_results,
                    web_results,
                )
            except Exception as exc:
                yield {"type": "status", "message": f"Web Unlocker 跳过：{exc}"}

        social_profiles_by_channel = {}
        found_social_urls = extract_all_social_urls_from_web_results(web_results)
        for spec in SOCIAL_CHANNELS:
            urls = found_social_urls.get(spec.key) or []
            if not bs.is_channel_configured(spec) or not urls:
                continue
            yield {
                "type": "status",
                "message": f"{spec.label} 补充抓取 {min(len(urls), 8)} 个 profile…",
            }
            try:
                profiles = await asyncio.to_thread(
                    bs.collect_profiles_by_url,
                    spec,
                    urls,
                    max_urls=8,
                )
                social_profiles_by_channel[spec.key] = profiles
                for profile in profiles:
                    web_results.append(spec.to_web_result(profile))
            except Exception as exc:
                yield {"type": "status", "message": f"{spec.label} 抓取跳过：{exc}"}

        yield {
            "type": "source_result",
            "source": "peeringdb",
            "count": len(networks),
            "preview": [f"AS{n['asn']} {n.get('name', '')}" for n in networks[:5]],
        }
        if shodan_networks:
            yield {
                "type": "source_result",
                "source": "shodan",
                "count": len(shodan_networks),
                "preview": [f"AS{n['asn']} {n.get('name', '')}" for n in shodan_networks[:5]],
            }
        yield {
            "type": "source_result",
            "source": "web_search",
            "count": len(web_results),
            "preview": [r.get("title") or r.get("url") or "" for r in web_results[:5]],
        }
        if unlocker_summary.get("fetched"):
            yield {
                "type": "source_result",
                "source": "web_unlocker",
                "count": unlocker_summary["fetched"],
                "preview": unlocker_summary.get("urls") or [],
            }
        forum_counts: dict[str, int] = {}
        for item in web_results:
            backend = item.get("backend") or ""
            if backend in {"lowendtalk", "webhostingtalk"}:
                forum_counts[backend] = forum_counts.get(backend, 0) + 1
        for key, count in forum_counts.items():
            if count:
                yield {
                    "type": "source_result",
                    "source": key,
                    "count": count,
                    "preview": [
                        r.get("title") or r.get("url") or ""
                        for r in web_results
                        if r.get("backend") == key
                    ][:5],
                }
        for spec in SOCIAL_CHANNELS:
            profiles = social_profiles_by_channel.get(spec.key) or []
            if not profiles:
                continue
            yield {
                "type": "source_result",
                "source": spec.key,
                "count": len(profiles),
                "preview": [
                    f"{p.get('name') or '?'} @ {p.get('org') or '?'}" for p in profiles[:5]
                ],
            }

        persist(
            PHASE_SOURCES_DONE,
            plan=plan,
            networks=networks,
            web_results=web_results,
            social_profiles_by_channel=social_profiles_by_channel,
            shodan_networks=shodan_networks,
        )
    else:
        networks = cp["networks"]
        web_results = cp["web_results"]
        social_profiles_by_channel = cp.get("social_profiles_by_channel") or {}
        shodan_networks = cp.get("shodan_networks") or []

    signals: dict[str, Any]
    web_leads: list[dict[str, Any]]

    if not phase_at_least(phase, PHASE_WEB_EXTRACTED):
        yield {
            "type": "status",
            "message": "正在从网页/论坛结果提取线索…",
            "phase": PHASE_WEB_EXTRACTED,
        }

        signals = web_search.extract_signals_from_results(web_results)
        yield {
            "type": "source_result",
            "source": "web_regex",
            "count": len(signals["emails"]) + len(signals["asns"]),
            "preview": [f"emails={len(signals['emails'])}, asns={len(signals['asns'])}"],
        }

        web_leads = []
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

        yield {
            "type": "source_result",
            "source": "llm_extract",
            "count": len(web_leads),
            "preview": [],
        }

        persist(
            PHASE_WEB_EXTRACTED,
            signals=signals,
            web_leads=web_leads,
        )
    else:
        signals = cp["signals"]
        web_leads = list(cp.get("web_leads") or [])

    asn_targets: list[dict[str, Any]]
    all_candidates: list[dict[str, Any]]
    rdap_done_asns: set[int]

    if not phase_at_least(phase, PHASE_RDAP_PROGRESS):
        asn_targets = _merge_asn_targets(networks, signals["asns"], web_leads)
        if not asn_targets and not web_leads:
            yield {"type": "error", "message": "所有渠道均未找到有效线索，请调整描述后重试"}
            return
        all_candidates = list(web_leads)
        rdap_done_asns = set()
    else:
        asn_targets = cp.get("asn_targets") or []
        all_candidates = list(cp.get("all_candidates") or [])
        rdap_done_asns = {int(asn) for asn in (cp.get("rdap_done_asns") or [])}

    total = len(asn_targets)
    processed = len(rdap_done_asns)

    for index, network in enumerate(asn_targets):
        asn = int(network["asn"])
        if asn in rdap_done_asns:
            continue

        processed += 1
        yield {
            "type": "progress",
            "index": processed,
            "total": total,
            "asn": asn,
            "network": network.get("name") or "",
            "message": f"RDAP 查询 AS{asn}",
            "phase": PHASE_RDAP_PROGRESS,
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
        rdap_done_asns.add(asn)

        persist(
            PHASE_RDAP_PROGRESS,
            asn_targets=asn_targets,
            rdap_done_asns=sorted(rdap_done_asns),
            all_candidates=all_candidates,
        )

        yield {
            "type": "asn_result",
            "asn": asn,
            "network": network.get("name") or "",
            "rows": row_dicts,
            "candidate_count": len(candidates),
        }

        if processed < total and delay:
            await asyncio.sleep(delay)

    leads: list[dict[str, Any]]

    if not phase_at_least(phase, PHASE_SCORED):
        all_candidates = _dedupe_candidates(all_candidates)
        all_candidates = [row for row in all_candidates if row.get("email")]
        if user_id:
            all_candidates = filter_avoided_candidates(all_candidates, prefs)
        all_candidates = enrich_candidates_with_social(
            all_candidates,
            web_results=web_results,
            profiles_by_channel=social_profiles_by_channel,
        )

        if not all_candidates:
            yield {
                "type": "done",
                "leads": [],
                "import": None,
                "message": "找到网络信息但未提取到可用邮箱联系人",
            }
            return

        yield {
            "type": "status",
            "message": f"AI 正在评估 {len(all_candidates)} 条跨渠道候选线索…",
            "phase": PHASE_SCORED,
        }

        try:
            scored = await asyncio.to_thread(
                score_leads,
                user_query,
                plan,
                all_candidates,
                preference_hints=preference_hints,
            )
        except LLMError as exc:
            yield {"type": "error", "message": str(exc)}
            return

        leads = [
            row
            for row in scored
            if row.get("lead_relevant") and row.get("lead_score", 0) >= score_threshold
        ]
        leads.sort(key=lambda item: item.get("lead_score", 0), reverse=True)
        persist(PHASE_SCORED, leads=leads, all_candidates=all_candidates)
    else:
        leads = list(cp.get("leads") or [])

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

    if user_id and leads:
        try:
            await asyncio.to_thread(record_search_feedback, user_id, user_query, plan)
        except Exception:
            pass

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
