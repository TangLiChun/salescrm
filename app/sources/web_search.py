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


ZHIPU_WEB_SEARCH_URL = "https://open.bigmodel.cn/api/paas/v4/web_search"
ZHIPU_SEARCH_ENGINES = frozenset(
    {"search_std", "search_pro", "search_pro_sogou", "search_pro_quark"}
)


def _zhipu_api_key() -> str:
    key = get_setting("zhipu_api_key", "").strip()
    if key:
        return key
    base_url = get_setting("llm_base_url", "").lower()
    if "bigmodel.cn" in base_url:
        return get_setting("llm_api_key", "").strip()
    return ""


def zhipu_search_configured() -> bool:
    return bool(_zhipu_api_key())


def available_backends() -> list[str]:
    backends: list[str] = []
    if zhipu_search_configured():
        backends.append("zhipu")
    if get_setting("tavily_api_key", "").strip():
        backends.append("tavily")
    if get_setting("serpapi_key", "").strip():
        backends.append("serpapi")
    if get_setting("brave_search_key", "").strip():
        backends.append("brave")
    backends.append("duckduckgo")
    return backends


def get_search_config() -> dict[str, Any]:
    backends = available_backends()
    zhipu_key = get_setting("zhipu_api_key", "").strip()
    llm_base = get_setting("llm_base_url", "").lower()
    zhipu_engine = get_setting("zhipu_search_engine", "search_pro") or "search_pro"
    if zhipu_engine not in ZHIPU_SEARCH_ENGINES:
        zhipu_engine = "search_pro"
    return {
        "active_web_backend": backends[0] if backends else "duckduckgo",
        "web_backend_priority": backends,
        "channels": {
            "web_search": backends,
            "peeringdb": True,
            "arin_rdap": True,
            "llm_extract": True,
            "llm_scoring": True,
        },
        "zhipu_web_search": {
            "configured": zhipu_search_configured(),
            "engine": zhipu_engine,
            "endpoint": ZHIPU_WEB_SEARCH_URL,
            "uses_dedicated_key": bool(zhipu_key),
            "reuses_llm_key": bool(not zhipu_key and "bigmodel.cn" in llm_base),
        },
        "keys_configured": {
            "zhipu": zhipu_search_configured(),
            "tavily": bool(get_setting("tavily_api_key", "").strip()),
            "serpapi": bool(get_setting("serpapi_key", "").strip()),
            "brave": bool(get_setting("brave_search_key", "").strip()),
            "duckduckgo": True,
        },
        "usage": (
            "discover_leads / enrich_contact 会自动按 web_backend_priority 选第一个可用引擎；"
            "也可直接调用 web_search 工具做联网检索"
        ),
    }


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
    if backend == "zhipu":
        return _search_zhipu(query, max_results=max_results)
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


def _search_zhipu(query: str, *, max_results: int) -> list[dict[str, str]]:
    api_key = _zhipu_api_key()
    if not api_key:
        return []

    engine = (get_setting("zhipu_search_engine", "search_pro") or "search_pro").strip()
    if engine not in ZHIPU_SEARCH_ENGINES:
        engine = "search_pro"

    count = max(1, min(max_results, 50))
    payload: dict[str, Any] = {
        "search_query": query,
        "search_engine": engine,
        "count": count,
        "content_size": "medium",
    }

    req = urllib.request.Request(
        ZHIPU_WEB_SEARCH_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Zhipu web search HTTP {exc.code}: {body[:300]}") from exc

    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(str(data.get("error")))

    rows: list[dict[str, str]] = []
    for item in data.get("search_result") or []:
        if not isinstance(item, dict):
            continue
        link = item.get("link") or item.get("url") or ""
        snippet = item.get("content") or item.get("snippet") or ""
        media = item.get("media") or ""
        title = item.get("title") or media or link
        if media and media not in title:
            snippet = f"[{media}] {snippet}".strip()
        rows.append(
            _normalize_result(
                str(title),
                str(link),
                str(snippet),
                backend="zhipu",
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
