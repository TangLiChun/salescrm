"""Merge LinkedIn / X / Facebook profile URLs onto contact rows."""

from __future__ import annotations

import re
from typing import Any

from app.sources import brightdata_social as bs
from app.sources.social_registry import SOCIAL_CHANNELS

SOCIAL_FIELDS = ("linkedin", "x", "facebook")

_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "linkedin": ("linkedin", "linkedin_url", "linkedin_profile"),
    "x": ("x", "x_url", "twitter", "twitter_url"),
    "facebook": ("facebook", "facebook_url"),
}

_SOURCE_TO_FIELD = {spec.source: spec.key for spec in SOCIAL_CHANNELS}


def _norm_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _names_match(left: str, right: str) -> bool:
    a = _norm_text(left)
    b = _norm_text(right)
    if not a or not b:
        return False
    if a == b:
        return True
    return len(a) >= 3 and (a in b or b in a)


def _orgs_match(left: str, right: str) -> bool:
    a = _norm_text(left)
    b = _norm_text(right)
    if not a or not b:
        return False
    if a == b:
        return True
    return len(a) >= 4 and (a in b or b in a)


def _spec_for_field(field: str) -> bs.SocialChannelSpec | None:
    for spec in SOCIAL_CHANNELS:
        if spec.key == field:
            return spec
    return None


def normalize_social_url(field: str, url: object) -> str:
    spec = _spec_for_field(field)
    if not spec:
        return str(url or "").strip()
    return bs.normalize_url(spec, str(url or ""))


def extract_social_fields_from_row(row: dict[str, Any]) -> dict[str, str]:
    found: dict[str, str] = {}
    for field, aliases in _FIELD_ALIASES.items():
        for alias in aliases:
            clean = normalize_social_url(field, row.get(alias))
            if clean:
                found[field] = clean
                break

    source = str(row.get("source") or "").strip().lower()
    profile_url = str(row.get("profile_url") or "").strip()
    field = _SOURCE_TO_FIELD.get(source)
    if field and profile_url:
        clean = normalize_social_url(field, profile_url)
        if clean:
            found.setdefault(field, clean)
    return found


def merge_social_fields(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, str]:
    merged: dict[str, str] = {}
    for field in SOCIAL_FIELDS:
        current = normalize_social_url(field, existing.get(field))
        new_value = normalize_social_url(field, incoming.get(field))
        merged[field] = current or new_value
    return merged


def attach_profiles_to_candidates(
    candidates: list[dict[str, Any]],
    profiles_by_channel: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    if not profiles_by_channel:
        return candidates

    updated: list[dict[str, Any]] = []
    for candidate in candidates:
        row = dict(candidate)
        cand_name = row.get("name") or ""
        cand_org = row.get("org") or ""
        cand_email = str(row.get("email") or "").lower()

        for channel_key, profiles in profiles_by_channel.items():
            if channel_key not in SOCIAL_FIELDS:
                continue
            if row.get(channel_key):
                continue
            for profile in profiles:
                profile_name = profile.get("name") or profile.get("handle") or ""
                profile_org = profile.get("org") or ""
                url = normalize_social_url(channel_key, profile.get("url"))
                if not url:
                    continue
                external = str(profile.get("external_link") or "").lower()
                if cand_email and external and cand_email in external:
                    row[channel_key] = url
                    break
                if _names_match(cand_name, profile_name) and (
                    _orgs_match(cand_org, profile_org) or not cand_org or not profile_org
                ):
                    row[channel_key] = url
                    break
                if _names_match(cand_name, profile_name):
                    row[channel_key] = url
                    break
        updated.append(row)
    return updated


def attach_web_social_urls(
    candidates: list[dict[str, Any]],
    web_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not web_results:
        return candidates

    email_re = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
    updated: list[dict[str, Any]] = []
    for candidate in candidates:
        row = dict(candidate)
        cand_name = _norm_text(row.get("name"))
        cand_email = str(row.get("email") or "").lower()
        for item in web_results:
            blob = " ".join(
                str(item.get(key) or "")
                for key in ("title", "snippet", "url")
            )
            blob_lower = blob.lower()
            emails_in_blob = {email.lower() for email in email_re.findall(blob)}
            name_hit = cand_name and cand_name in blob_lower
            email_hit = cand_email and cand_email in emails_in_blob
            if not name_hit and not email_hit:
                continue
            for spec in SOCIAL_CHANNELS:
                if row.get(spec.key):
                    continue
                urls = bs.extract_urls(spec, blob)
                if urls:
                    row[spec.key] = urls[0]
        updated.append(row)
    return updated


def enrich_candidates_with_social(
    candidates: list[dict[str, Any]],
    *,
    web_results: list[dict[str, Any]] | None = None,
    profiles_by_channel: dict[str, list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    rows = candidates
    if web_results:
        rows = attach_web_social_urls(rows, web_results)
    if profiles_by_channel:
        rows = attach_profiles_to_candidates(rows, profiles_by_channel)
    return rows
