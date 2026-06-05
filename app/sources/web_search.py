from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
ASN_RE = re.compile(r"\bAS[N]?[\s\-]?(\d{1,10})\b", re.IGNORECASE)


from app.settings_store import get_setting


def available_backends() -> list[str]:
    backends: list[str] = []
    if get_setting("tavily_api_key", "").strip():
        backends.append("tavily")
    if get_setting("serpapi_key", "").strip():
        backends.append("serpapi")
    if get_setting("brave_search_key", "").strip():
        backends.append("brave")
    backends.append("duckduckgo")
    return backends


def _normalize_result(title: str, url: str, snippet: str, *, backend: str, query: str) -> dict[str, str]:
    return {
        "title": title.strip(),
        "url": url.strip(),
        "snippet": snippet.strip(),
        "backend": backend,
        "query": query,
    }


def search_web(query: str, *, max_results: int = 8) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for backend in available_backends():
        try:
            batch = _search_with_backend(backend, query, max_results=max_results)
        except Exception:
            batch = []
        for item in batch:
            url = item.get("url") or ""
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            results.append(item)
        if results:
            break

    return results[:max_results]


def search_web_many(queries: list[str], *, max_results_per_query: int = 6) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for query in queries:
        for item in search_web(query, max_results=max_results_per_query):
            url = item.get("url") or ""
            if url and url in seen_urls:
                continue
            if url:
                seen_urls.add(url)
            merged.append(item)
    return merged


def extract_signals_from_results(results: list[dict[str, str]]) -> dict[str, list]:
    emails: set[str] = set()
    asns: set[int] = set()
    for item in results:
        blob = " ".join([item.get("title") or "", item.get("snippet") or "", item.get("url") or ""])
        for email in EMAIL_RE.findall(blob):
            if not _is_noise_email(email):
                emails.add(email.lower())
        for match in ASN_RE.findall(blob):
            try:
                asn = int(match)
                if 1 <= asn <= 4294967295:
                    asns.add(asn)
            except ValueError:
                continue
    return {"emails": sorted(emails), "asns": sorted(asns)}


def _is_noise_email(email: str) -> bool:
    lowered = email.lower()
    noise = ("example.com", "email.com", "domain.com", "sentry.io", "wixpress.com")
    return any(part in lowered for part in noise)


def _search_with_backend(backend: str, query: str, *, max_results: int) -> list[dict[str, str]]:
    if backend == "tavily":
        return _search_tavily(query, max_results=max_results)
    if backend == "serpapi":
        return _search_serpapi(query, max_results=max_results)
    if backend == "brave":
        return _search_brave(query, max_results=max_results)
    if backend == "duckduckgo":
        return _search_duckduckgo(query, max_results=max_results)
    return []


def _search_tavily(query: str, *, max_results: int) -> list[dict[str, str]]:
    api_key = get_setting("tavily_api_key", "").strip()
    payload = {"api_key": api_key, "query": query, "max_results": max_results}
    req = urllib.request.Request(
        "https://api.tavily.com/search",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    rows = []
    for item in data.get("results") or []:
        rows.append(
            _normalize_result(
                item.get("title") or "",
                item.get("url") or "",
                item.get("content") or "",
                backend="tavily",
                query=query,
            )
        )
    return rows


def _search_serpapi(query: str, *, max_results: int) -> list[dict[str, str]]:
    api_key = get_setting("serpapi_key", "").strip()
    params = urllib.parse.urlencode({"q": query, "api_key": api_key, "num": max_results})
    url = f"https://serpapi.com/search.json?{params}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.load(resp)
    rows = []
    for item in data.get("organic_results") or []:
        rows.append(
            _normalize_result(
                item.get("title") or "",
                item.get("link") or "",
                item.get("snippet") or "",
                backend="serpapi",
                query=query,
            )
        )
    return rows


def _search_brave(query: str, *, max_results: int) -> list[dict[str, str]]:
    api_key = get_setting("brave_search_key", "").strip()
    count = max(1, min(max_results, 20))
    params = urllib.parse.urlencode({"q": query, "count": count})
    url = f"https://api.search.brave.com/res/v1/web/search?{params}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "gzip",
            "X-Subscription-Token": api_key,
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    rows = []
    for item in (data.get("web") or {}).get("results") or []:
        rows.append(
            _normalize_result(
                item.get("title") or "",
                item.get("url") or "",
                item.get("description") or item.get("snippet") or "",
                backend="brave",
                query=query,
            )
        )
    return rows


def _search_duckduckgo(query: str, *, max_results: int) -> list[dict[str, str]]:
    from ddgs import DDGS

    rows = []
    for item in DDGS().text(query, max_results=max_results):
        rows.append(
            _normalize_result(
                item.get("title") or "",
                item.get("href") or item.get("url") or "",
                item.get("body") or item.get("snippet") or "",
                backend="duckduckgo",
                query=query,
            )
        )
    return rows
