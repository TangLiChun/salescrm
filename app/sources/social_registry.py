"""Bright Data social profile channels: LinkedIn, X, Facebook."""

from __future__ import annotations

import re
from typing import Any

from app.sources import brightdata_social as bs

DEFAULT_LINKEDIN_DATASET_ID = "gd_l1viktl72bvl7bjuj0"
DEFAULT_X_DATASET_ID = "gd_lwxmeb2u1cniijd7t4"
DEFAULT_FACEBOOK_DATASET_ID = "gd_mf0urb782734ik94dz"

LINKEDIN_URL_RE = re.compile(
    r"https?://(?:[\w-]+\.)?linkedin\.com/in/[\w\-_%]+/?",
    re.IGNORECASE,
)
X_URL_RE = re.compile(
    r"https?://(?:(?:www\.)?(?:twitter|x)\.com)/[\w]+/?",
    re.IGNORECASE,
)
FACEBOOK_PROFILE_URL_RE = re.compile(
    r"https?://(?:[\w-]+\.)?facebook\.com/(?!groups/|events/|marketplace/|watch/|share/|photo\.php|story\.php)[\w.\-]+/?",
    re.IGNORECASE,
)


def _normalize_linkedin(row: dict[str, Any]) -> dict[str, Any]:
    current = row.get("current_company") if isinstance(row.get("current_company"), dict) else {}
    org = str(row.get("current_company_name") or current.get("name") or "").strip()
    name = str(row.get("name") or "").strip()
    if not name:
        name = f"{row.get('first_name') or ''} {row.get('last_name') or ''}".strip()
    experience_lines: list[str] = []
    for item in row.get("experience") or []:
        if not isinstance(item, dict):
            continue
        line = " · ".join(
            part
            for part in (
                str(item.get("title") or item.get("subtitle") or "").strip(),
                str(item.get("company") or "").strip(),
            )
            if part
        )
        if line:
            experience_lines.append(line)
    url = bs.normalize_url(LINKEDIN, str(row.get("url") or row.get("input_url") or ""))
    return {
        "name": name,
        "org": org,
        "position": str(row.get("position") or "").strip(),
        "city": str(row.get("city") or row.get("location") or "").strip(),
        "url": url,
        "about": str(row.get("about") or "").strip(),
        "experience_preview": experience_lines[:5],
        "followers": row.get("followers"),
        "raw": row,
    }


def _linkedin_web_result(profile: dict[str, Any]) -> dict[str, str]:
    parts = [
        profile.get("name") or "",
        profile.get("position") or "",
        profile.get("org") or "",
        profile.get("city") or "",
        profile.get("about") or "",
        *(profile.get("experience_preview") or []),
    ]
    return {
        "title": profile.get("name") or profile.get("org") or "LinkedIn profile",
        "url": profile.get("url") or "",
        "snippet": " | ".join(part for part in parts if part)[:1200],
        "backend": "brightdata-linkedin",
        "query": "linkedin",
    }


def _linkedin_lead_preview(profile: dict[str, Any]) -> dict[str, Any]:
    notes = " · ".join(
        part
        for part in (
            profile.get("position") or "",
            profile.get("city") or "",
            profile.get("url") or "",
        )
        if part
    )
    url = profile.get("url") or ""
    return {
        "org": profile.get("org") or "",
        "name": profile.get("name") or "",
        "email": "",
        "roles": [],
        "source": "linkedin",
        "source_detail": "Bright Data LinkedIn",
        "notes": notes,
        "profile_url": url,
        "linkedin": url,
    }


def _normalize_x(row: dict[str, Any]) -> dict[str, Any]:
    url = bs.normalize_url(X, str(row.get("url") or row.get("input_url") or ""))
    name = str(row.get("profile_name") or row.get("name") or row.get("id") or "").strip()
    bio = str(row.get("biography") or row.get("bio") or "").strip()
    location = str(row.get("location") or "").strip()
    external = str(row.get("external_link") or "").strip()
    return {
        "name": name,
        "org": "",
        "handle": str(row.get("id") or "").strip(),
        "position": "",
        "city": location,
        "url": url,
        "about": bio,
        "external_link": external,
        "followers": row.get("followers"),
        "following": row.get("following"),
        "verified": row.get("is_verified"),
        "raw": row,
    }


def _x_web_result(profile: dict[str, Any]) -> dict[str, str]:
    parts = [
        profile.get("name") or "",
        profile.get("handle") or "",
        profile.get("about") or "",
        profile.get("city") or "",
        profile.get("external_link") or "",
    ]
    return {
        "title": profile.get("name") or profile.get("handle") or "X profile",
        "url": profile.get("url") or "",
        "snippet": " | ".join(part for part in parts if part)[:1200],
        "backend": "brightdata-x",
        "query": "x",
    }


def _x_lead_preview(profile: dict[str, Any]) -> dict[str, Any]:
    notes = " · ".join(
        part
        for part in (
            profile.get("handle") or "",
            profile.get("city") or "",
            profile.get("external_link") or "",
            profile.get("url") or "",
        )
        if part
    )
    url = profile.get("url") or ""
    return {
        "org": "",
        "name": profile.get("name") or profile.get("handle") or "",
        "email": "",
        "roles": [],
        "source": "x",
        "source_detail": "Bright Data X",
        "notes": notes,
        "profile_url": url,
        "x": url,
    }


def _normalize_facebook(row: dict[str, Any]) -> dict[str, Any]:
    url = bs.normalize_url(FACEBOOK, str(row.get("url") or row.get("input_url") or ""))
    name = str(row.get("name") or "").strip()
    bio = str(row.get("bio") or row.get("about") or "").strip()
    work = row.get("work")
    org = ""
    if isinstance(work, str):
        org = work.strip()
    elif isinstance(work, list) and work:
        first = work[0]
        if isinstance(first, dict):
            org = str(first.get("name") or first.get("employer") or "").strip()
        else:
            org = str(first).strip()
    return {
        "name": name,
        "org": org,
        "position": str(row.get("profile_type") or "").strip(),
        "city": "",
        "url": url,
        "about": bio,
        "followers": row.get("followers"),
        "verified": row.get("is_verified"),
        "raw": row,
    }


def _facebook_web_result(profile: dict[str, Any]) -> dict[str, str]:
    parts = [
        profile.get("name") or "",
        profile.get("org") or "",
        profile.get("position") or "",
        profile.get("about") or "",
    ]
    return {
        "title": profile.get("name") or "Facebook profile",
        "url": profile.get("url") or "",
        "snippet": " | ".join(part for part in parts if part)[:1200],
        "backend": "brightdata-facebook",
        "query": "facebook",
    }


def _facebook_lead_preview(profile: dict[str, Any]) -> dict[str, Any]:
    notes = " · ".join(
        part
        for part in (profile.get("org") or "", profile.get("about") or "", profile.get("url") or "")
        if part
    )
    url = profile.get("url") or ""
    return {
        "org": profile.get("org") or "",
        "name": profile.get("name") or "",
        "email": "",
        "roles": [],
        "source": "facebook",
        "source_detail": "Bright Data Facebook",
        "notes": notes,
        "profile_url": url,
        "facebook": url,
    }


LINKEDIN = bs.SocialChannelSpec(
    key="linkedin",
    label="LinkedIn",
    enabled_setting="brightdata_linkedin_enabled",
    dataset_setting="brightdata_linkedin_dataset_id",
    default_dataset_id=DEFAULT_LINKEDIN_DATASET_ID,
    url_pattern=LINKEDIN_URL_RE,
    docs_url="https://docs.brightdata.com/api-reference/scrapers/social-media-apis/linkedin-profiles-collect-by-url",
    backend="brightdata-linkedin",
    source="linkedin",
    normalize=_normalize_linkedin,
    to_web_result=_linkedin_web_result,
    to_lead_preview=_linkedin_lead_preview,
)

X = bs.SocialChannelSpec(
    key="x",
    label="X",
    enabled_setting="brightdata_x_enabled",
    dataset_setting="brightdata_x_dataset_id",
    default_dataset_id=DEFAULT_X_DATASET_ID,
    url_pattern=X_URL_RE,
    docs_url="https://docs.brightdata.com/api-reference/scrapers/social-media-apis/twitter-profiles-collect-by-url",
    backend="brightdata-x",
    source="x",
    normalize=_normalize_x,
    to_web_result=_x_web_result,
    to_lead_preview=_x_lead_preview,
)

FACEBOOK = bs.SocialChannelSpec(
    key="facebook",
    label="Facebook",
    enabled_setting="brightdata_facebook_enabled",
    dataset_setting="brightdata_facebook_dataset_id",
    default_dataset_id=DEFAULT_FACEBOOK_DATASET_ID,
    url_pattern=FACEBOOK_PROFILE_URL_RE,
    docs_url="https://docs.brightdata.com/api-reference/scrapers/social-media-apis/facebook-profiles-collect-by-url",
    backend="brightdata-facebook",
    source="facebook",
    normalize=_normalize_facebook,
    to_web_result=_facebook_web_result,
    to_lead_preview=_facebook_lead_preview,
)

SOCIAL_CHANNELS: tuple[bs.SocialChannelSpec, ...] = (LINKEDIN, X, FACEBOOK)


def configured_channels() -> list[bs.SocialChannelSpec]:
    return [spec for spec in SOCIAL_CHANNELS if bs.is_channel_configured(spec)]


def extract_all_social_urls_from_web_results(results: list[dict[str, Any]]) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for spec in SOCIAL_CHANNELS:
        urls = bs.extract_urls_from_web_results(spec, results)
        if urls:
            found[spec.key] = urls
    return found


def get_all_configs() -> dict[str, Any]:
    return {spec.key: bs.channel_config(spec) for spec in SOCIAL_CHANNELS}
