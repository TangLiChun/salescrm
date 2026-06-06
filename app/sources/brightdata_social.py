"""Shared helpers for Bright Data social profile scrapers (LinkedIn, X, Facebook)."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.settings_store import get_setting
from app.sources.brightdata_scraper import scrape_dataset

NormalizeFn = Callable[[dict[str, Any]], dict[str, Any]]
WebResultFn = Callable[[dict[str, Any]], dict[str, str]]
PreviewFn = Callable[[dict[str, Any]], dict[str, Any]]

DEFAULT_MAX_URLS = 10


@dataclass(frozen=True)
class SocialChannelSpec:
    key: str
    label: str
    enabled_setting: str
    dataset_setting: str
    default_dataset_id: str
    url_pattern: re.Pattern
    docs_url: str
    backend: str
    source: str
    normalize: NormalizeFn
    to_web_result: WebResultFn
    to_lead_preview: PreviewFn


def api_key_present() -> bool:
    return bool(get_setting("brightdata_api_key", "").strip())


def is_channel_enabled(spec: SocialChannelSpec) -> bool:
    return get_setting(spec.enabled_setting, "1").strip() != "0"


def is_channel_configured(spec: SocialChannelSpec) -> bool:
    if not is_channel_enabled(spec):
        return False
    if not api_key_present():
        return False
    return bool(dataset_id(spec))


def dataset_id(spec: SocialChannelSpec) -> str:
    return get_setting(spec.dataset_setting, "").strip()


def channel_config(spec: SocialChannelSpec) -> dict[str, Any]:
    return {
        "key": spec.key,
        "label": spec.label,
        "configured": is_channel_configured(spec),
        "enabled": is_channel_enabled(spec),
        "dataset_id": dataset_id(spec),
        "endpoint": "https://api.brightdata.com/datasets/v3/scrape",
        "max_urls_per_request": DEFAULT_MAX_URLS,
        "docs": spec.docs_url,
    }


def normalize_url(spec: SocialChannelSpec, url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    if not raw.startswith("http"):
        raw = f"https://{raw.lstrip('/')}"
    match = spec.url_pattern.search(raw)
    if not match:
        return ""
    return match.group(0).rstrip("/") + "/"


def extract_urls(spec: SocialChannelSpec, *blobs: str) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for blob in blobs:
        for match in spec.url_pattern.findall(blob or ""):
            clean = normalize_url(spec, match)
            if clean and clean not in seen:
                seen.add(clean)
                ordered.append(clean)
    return ordered


def extract_urls_from_web_results(
    spec: SocialChannelSpec, results: list[dict[str, Any]]
) -> list[str]:
    blobs: list[str] = []
    for item in results:
        blobs.append(str(item.get("title") or ""))
        blobs.append(str(item.get("snippet") or ""))
        blobs.append(str(item.get("url") or ""))
    return extract_urls(spec, *blobs)


def collect_profiles_by_url(
    spec: SocialChannelSpec,
    urls: list[str],
    *,
    max_urls: int = DEFAULT_MAX_URLS,
) -> list[dict[str, Any]]:
    if not is_channel_configured(spec):
        raise RuntimeError(f"Bright Data {spec.label} 未配置（需 API Key 且启用渠道）")

    normalized: list[str] = []
    seen: set[str] = set()
    for url in urls:
        clean = normalize_url(spec, url)
        if clean and clean not in seen:
            seen.add(clean)
            normalized.append(clean)
        if len(normalized) >= max(1, max_urls):
            break

    if not normalized:
        return []

    rows = scrape_dataset(
        dataset_id(spec),
        [{"url": url} for url in normalized],
    )
    return [spec.normalize(row) for row in rows if isinstance(row, dict)]


def profiles_to_web_results(
    spec: SocialChannelSpec, profiles: list[dict[str, Any]]
) -> list[dict[str, str]]:
    return [spec.to_web_result(profile) for profile in profiles]


def profiles_to_lead_previews(
    spec: SocialChannelSpec, profiles: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    return [spec.to_lead_preview(profile) for profile in profiles]
