"""Search LowEndTalk / WebHostingTalk via site-restricted web search and forum HTML search."""

from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request
from html import unescape
from typing import Any

from app.sources import web_search, web_unlocker
from app.sources.forum_registry import (
    ForumSpec,
    configured_channels,
    get_all_configs,
    is_channel_enabled,
)

USER_AGENT = "SalesCRM/1.0 (+forum-lead-discovery)"
DEFAULT_TIMEOUT = 25.0
MAX_KEYWORDS = 4
MAX_SITE_QUERIES_PER_KEYWORD = 2
MAX_DIRECT_QUERIES_PER_KEYWORD = 1
MAX_RESULTS_PER_FORUM = 24

THREAD_PATH_MARKERS = (
    "/discussion/",
    "/threads/",
    "/showthread.php",
    "/thread/",
    "/topic/",
)


def _site_queries(keyword: str, domain: str) -> list[str]:
    clean = (keyword or "").strip()
    if not clean:
        return []
    return [
        f"site:{domain} {clean} peering email contact",
        f"site:{domain} {clean} VPS hosting ASN",
    ][:MAX_SITE_QUERIES_PER_KEYWORD]


def _thread_url(url: str, domain: str) -> bool:
    lower = (url or "").lower()
    if domain not in lower:
        return False
    return any(marker in lower for marker in THREAD_PATH_MARKERS)


def _normalize_forum_result(
    title: str,
    url: str,
    snippet: str,
    *,
    spec: ForumSpec,
    keyword: str,
) -> dict[str, str]:
    return {
        "title": (title or url).strip(),
        "url": url.strip(),
        "snippet": (snippet or "").strip(),
        "backend": spec.key,
        "query": keyword,
    }


def _fetch_html(url: str, *, spec: ForumSpec) -> str | None:
    if spec.requires_unlocker:
        if not web_unlocker.is_configured():
            return None
        try:
            return web_unlocker.fetch_page(url, timeout=90)
        except Exception:
            return None
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"},
    )
    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return None


def _parse_search_html(html: str, *, spec: ForumSpec, keyword: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    domain = spec.domain

    heading_re = re.compile(
        rf'<h3>\s*<a\s+href="(https?://[^"]*{re.escape(domain)}[^"]*)"[^>]*>(.*?)</a>\s*</h3>',
        re.IGNORECASE | re.DOTALL,
    )
    for match in heading_re.finditer(html):
        url = unescape(match.group(1).strip())
        title = re.sub(r"<[^>]+>", " ", unescape(match.group(2))).strip()
        if not _thread_url(url, domain) or url in seen:
            continue
        seen.add(url)
        rows.append(_normalize_forum_result(title, url, title, spec=spec, keyword=keyword))

    if rows:
        return rows

    link_re = re.compile(
        rf'href="(https?://(?:www\.)?{re.escape(domain)}/[^"]+)"[^>]*>([^<{{}}]+)',
        re.IGNORECASE,
    )
    for match in link_re.finditer(html):
        url = unescape(match.group(1).strip())
        title = unescape(match.group(2)).strip()
        if not _thread_url(url, domain) or url in seen:
            continue
        if len(title) < 4:
            continue
        seen.add(url)
        rows.append(_normalize_forum_result(title, url, title, spec=spec, keyword=keyword))
    return rows


def search_forum(spec: ForumSpec, keyword: str, *, max_results: int = 8) -> list[dict[str, str]]:
    clean = (keyword or "").strip()
    if not clean or not is_channel_enabled(spec):
        return []

    merged: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for query in _site_queries(clean, spec.domain):
        try:
            batch = web_search.search_web(query, max_results=max(3, max_results // 2))
        except Exception:
            batch = []
        for item in batch:
            url = (item.get("url") or "").strip()
            if not url or url in seen_urls or spec.domain not in url.lower():
                continue
            seen_urls.add(url)
            merged.append(
                _normalize_forum_result(
                    item.get("title") or url,
                    url,
                    item.get("snippet") or "",
                    spec=spec,
                    keyword=clean,
                )
            )

    if len(merged) < max_results and (not spec.requires_unlocker or web_unlocker.is_configured()):
        search_url = spec.search_url.format(query=urllib.parse.quote(clean))
        html = _fetch_html(search_url, spec=spec)
        if html:
            for item in _parse_search_html(html, spec=spec, keyword=clean):
                url = item.get("url") or ""
                if url in seen_urls:
                    continue
                seen_urls.add(url)
                merged.append(item)

    return merged[:max_results]


def discover_from_keywords(
    keywords: list[str],
    *,
    max_results_per_forum: int = MAX_RESULTS_PER_FORUM,
) -> list[dict[str, str]]:
    specs = configured_channels()
    if not specs:
        return []

    merged: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    per_keyword = max(3, max_results_per_forum // max(len(keywords[:MAX_KEYWORDS]), 1))

    for spec in specs:
        forum_count = 0
        for keyword in keywords[:MAX_KEYWORDS]:
            if forum_count >= max_results_per_forum:
                break
            batch = search_forum(
                spec,
                keyword,
                max_results=min(per_keyword, max_results_per_forum - forum_count),
            )
            for item in batch:
                url = (item.get("url") or "").strip()
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                merged.append(item)
                forum_count += 1
                if forum_count >= max_results_per_forum:
                    break
    return merged


def search_forums(
    keyword: str,
    *,
    forums: list[str] | None = None,
    max_results: int = 12,
) -> dict[str, Any]:
    clean = (keyword or "").strip()
    if not clean:
        return {"error": "请提供 keyword"}

    wanted = {name.strip().lower() for name in (forums or []) if str(name).strip()}
    specs = configured_channels()
    if wanted:
        specs = [spec for spec in specs if spec.key in wanted]
    if not specs:
        return {
            "error": "没有可用的论坛渠道",
            "hint": "在系统设置启用 LowEndTalk / WebHostingTalk；WebHostingTalk 直连搜索还需 Web Unlocker",
            "forums": get_all_configs(),
        }

    per_forum = max(2, max_results // max(len(specs), 1))
    by_forum: dict[str, list[dict[str, str]]] = {}
    all_rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for spec in specs:
        rows = search_forum(spec, clean, max_results=per_forum)
        by_forum[spec.key] = rows
        for row in rows:
            url = row.get("url") or ""
            if url in seen:
                continue
            seen.add(url)
            all_rows.append(row)

    signals = web_search.extract_signals_from_results(all_rows)
    return {
        "keyword": clean,
        "forums_searched": [spec.key for spec in specs],
        "result_count": len(all_rows),
        "results": all_rows[:max_results],
        "by_forum": {key: vals[:8] for key, vals in by_forum.items()},
        "emails_found": signals.get("emails") or [],
        "asns_found": signals.get("asns") or [],
    }
