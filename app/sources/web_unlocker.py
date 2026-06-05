"""Bright Data Web Unlocker — fetch page bodies via /request API."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlparse

from app.settings_store import get_setting
from app.sources.web_search import brightdata_request

DEFAULT_MAX_URLS = 6
SNIPPET_MAX_LEN = 1200

PEERING_HINTS = (
    "peering",
    "contact",
    "noc",
    "abuse",
    "policy",
    "network",
    "about",
    "support",
)
SKIP_HOST_MARKERS = (
    "google.",
    "bing.com",
    "duckduckgo.com",
    "facebook.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "youtube.com",
    "wikipedia.org",
    "peeringdb.com",
)


def is_enabled() -> bool:
    return get_setting("brightdata_web_unlocker_enabled", "0").strip() != "0"


def zone_name() -> str:
    return get_setting("brightdata_web_unlocker_zone", "").strip()


def is_configured() -> bool:
    return (
        bool(get_setting("brightdata_api_key", "").strip())
        and bool(zone_name())
        and is_enabled()
    )


def max_urls_limit() -> int:
    raw = get_setting("brightdata_web_unlocker_max_urls", str(DEFAULT_MAX_URLS)).strip()
    try:
        return max(1, min(12, int(raw)))
    except ValueError:
        return DEFAULT_MAX_URLS


def get_config() -> dict[str, Any]:
    return {
        "configured": is_configured(),
        "enabled": is_enabled(),
        "zone": zone_name(),
        "max_urls": max_urls_limit(),
        "endpoint": "https://api.brightdata.com/request",
        "docs": "https://docs.brightdata.com/scraping-automation/web-unlocker/introduction",
    }


def fetch_page(url: str, *, data_format: str = "markdown", timeout: float = 90) -> str:
    zone = zone_name()
    if not zone:
        raise RuntimeError("未配置 Bright Data Web Unlocker Zone")
    clean_url = (url or "").strip()
    if not clean_url.startswith(("http://", "https://")):
        raise RuntimeError("URL 必须以 http:// 或 https:// 开头")
    payload: dict[str, str] = {"zone": zone, "url": clean_url, "format": "raw"}
    fmt = (data_format or "markdown").strip().lower()
    if fmt == "markdown":
        payload["data_format"] = "markdown"
    body = brightdata_request(payload, timeout=timeout)
    if not body.strip():
        raise RuntimeError("Web Unlocker 返回空内容")
    return body


def _snippet_from_body(body: str) -> str:
    text = re.sub(r"\s+", " ", (body or "").strip())
    if len(text) > SNIPPET_MAX_LEN:
        return text[:SNIPPET_MAX_LEN] + "…"
    return text


def _should_skip_url(url: str) -> bool:
    try:
        host = (urlparse(url).netloc or "").lower()
    except ValueError:
        return True
    if not host:
        return True
    return any(marker in host for marker in SKIP_HOST_MARKERS)


def _url_priority(url: str, snippet: str) -> int:
    score = 0
    stripped = (snippet or "").strip()
    if not stripped:
        score += 50
    elif len(stripped) < 80:
        score += 25
    lower = url.lower()
    for hint in PEERING_HINTS:
        if hint in lower:
            score += 12
    return score


def select_urls(web_results: list[dict[str, Any]], *, max_urls: int) -> list[str]:
    ranked: list[tuple[int, str]] = []
    seen: set[str] = set()
    for item in web_results:
        url = (item.get("url") or "").strip()
        if not url or url in seen or _should_skip_url(url):
            continue
        seen.add(url)
        ranked.append((_url_priority(url, item.get("snippet") or ""), url))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    return [url for _, url in ranked[: max(1, max_urls)]]


def enrich_web_results(
    web_results: list[dict[str, Any]],
    *,
    max_urls: int | None = None,
) -> dict[str, Any]:
    """Fetch selected pages and merge Markdown into matching result snippets."""
    limit = max_urls if max_urls is not None else max_urls_limit()
    urls = select_urls(web_results, max_urls=limit)
    if not urls:
        return {"fetched": 0, "urls": [], "errors": []}

    by_url = {(item.get("url") or "").strip(): item for item in web_results if item.get("url")}
    fetched = 0
    errors: list[dict[str, str]] = []
    for url in urls:
        try:
            body = fetch_page(url)
            snippet = _snippet_from_body(body)
        except Exception as exc:  # noqa: BLE001 — collect per-URL errors
            errors.append({"url": url, "error": str(exc)})
            continue
        item = by_url.get(url)
        if item:
            prior = (item.get("snippet") or "").strip()
            item["snippet"] = snippet if not prior else f"{prior}\n\n{snippet}"
            item["backend"] = "web_unlocker"
            item["unlocker_fetched"] = "1"
        else:
            web_results.append(
                {
                    "title": url,
                    "url": url,
                    "snippet": snippet,
                    "backend": "web_unlocker",
                    "query": "",
                    "unlocker_fetched": "1",
                }
            )
        fetched += 1
    return {"fetched": fetched, "urls": urls[:fetched], "errors": errors}


def fetch_pages(
    urls: list[str],
    *,
    max_urls: int | None = None,
) -> list[dict[str, Any]]:
    """Fetch explicit URLs and return normalized web-result rows."""
    limit = max_urls if max_urls is not None else max_urls_limit()
    rows: list[dict[str, Any]] = []
    for url in urls[:limit]:
        clean = (url or "").strip()
        if not clean:
            continue
        try:
            body = fetch_page(clean)
            rows.append(
                {
                    "title": clean,
                    "url": clean,
                    "snippet": _snippet_from_body(body),
                    "backend": "web_unlocker",
                    "query": "",
                }
            )
        except Exception as exc:  # noqa: BLE001
            rows.append(
                {
                    "title": clean,
                    "url": clean,
                    "snippet": "",
                    "backend": "web_unlocker",
                    "query": "",
                    "error": str(exc),
                }
            )
    return rows
