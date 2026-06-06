from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from html import unescape
from typing import Any

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
ASN_RE = re.compile(r"\bAS[N]?[\s\-]?(\d{1,10})\b", re.IGNORECASE)
GOOGLE_H3_LINK_RE = re.compile(
    r'<a\s+[^>]*href="([^"]+)"[^>]*>\s*(?:<[^>]+>\s*)*<h3[^>]*>(.*?)</h3>',
    re.IGNORECASE | re.DOTALL,
)
GOOGLE_SNIPPET_RE = re.compile(
    r'class="[^"]*(?:VwiC3b|yXK7lf|MUxGbd|IsZvec)[^"]*"[^>]*>(.*?)</',
    re.IGNORECASE | re.DOTALL,
)
GOOGLE_HREF_RE = re.compile(r'href="(/url\?[^"]+|https?://[^"]+)"', re.IGNORECASE)
MARKDOWN_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")
BRIGHTDATA_DATA_FORMATS = frozenset({"auto", "raw", "parsed_light", "parsed", "json", "markdown"})

from app.settings_store import get_setting

ZHIPU_WEB_SEARCH_URL = "https://open.bigmodel.cn/api/paas/v4/web_search"
BRIGHTDATA_REQUEST_URL = "https://api.brightdata.com/request"
ZHIPU_SEARCH_ENGINES = frozenset(
    {"search_std", "search_pro", "search_pro_sogou", "search_pro_quark"}
)
GOOGLE_JUNK_URL_PARTS = (
    "google.com/search",
    "google.com/url?",
    "webcache.googleusercontent.com",
    "accounts.google.com",
    "support.google.com",
    "policies.google.com",
    "maps.google.com",
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


def brightdata_serp_configured() -> bool:
    return bool(get_setting("brightdata_api_key", "").strip()) and bool(
        get_setting("brightdata_serp_zone", "").strip()
    )


def _brightdata_data_format() -> str:
    fmt = (get_setting("brightdata_serp_data_format", "auto") or "auto").strip().lower()
    return fmt if fmt in BRIGHTDATA_DATA_FORMATS else "auto"


def available_backends() -> list[str]:
    backends: list[str] = []
    if brightdata_serp_configured():
        backends.append("brightdata")
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
        "brightdata_serp": {
            "configured": brightdata_serp_configured(),
            "endpoint": BRIGHTDATA_REQUEST_URL,
            "zone": get_setting("brightdata_serp_zone", "").strip(),
            "data_format": _brightdata_data_format(),
            "supported_response_types": ["json", "parsed_light", "markdown", "raw_html"],
        },
        "keys_configured": {
            "zhipu": zhipu_search_configured(),
            "brightdata": brightdata_serp_configured(),
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


def _normalize_result(
    title: str, url: str, snippet: str, *, backend: str, query: str
) -> dict[str, str]:
    return {
        "title": title.strip(),
        "url": url.strip(),
        "snippet": snippet.strip(),
        "backend": backend,
        "query": query,
    }


def _rows_useful(rows: list[dict[str, str]]) -> bool:
    if not rows:
        return False
    for item in rows:
        if (item.get("snippet") or "").strip():
            return True
        blob = f"{item.get('title') or ''} {item.get('url') or ''}"
        if EMAIL_RE.findall(blob) or ASN_RE.findall(blob):
            return True
    return False


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
        if results and _rows_useful(results):
            break

    return results[:max_results]


def search_web_many(
    queries: list[str],
    *,
    max_results_per_query: int = 6,
    max_queries: int = 4,
) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for query in queries[: max(1, max_queries)]:
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
    if backend == "brightdata":
        return _search_brightdata_serp(query, max_results=max_results)
    if backend == "tavily":
        return _search_tavily(query, max_results=max_results)
    if backend == "serpapi":
        return _search_serpapi(query, max_results=max_results)
    if backend == "brave":
        return _search_brave(query, max_results=max_results)
    if backend == "duckduckgo":
        return _search_duckduckgo(query, max_results=max_results)
    return []


def _strip_html(text: str) -> str:
    cleaned = unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", cleaned).strip()


def _unwrap_google_href(href: str) -> str:
    raw = unescape((href or "").strip())
    if raw.startswith("/url?"):
        parsed = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query)
        for key in ("q", "url"):
            values = parsed.get(key) or []
            if values and values[0].startswith("http"):
                return values[0]
        return ""
    return raw


def _is_junk_google_url(url: str) -> bool:
    lowered = (url or "").lower()
    if not lowered.startswith("http"):
        return True
    return any(part in lowered for part in GOOGLE_JUNK_URL_PARTS)


def _parse_brightdata_json(
    data: dict[str, Any], *, query: str, max_results: int
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in data.get("organic") or []:
        if not isinstance(item, dict):
            continue
        rows.append(
            _normalize_result(
                str(item.get("title") or ""),
                str(item.get("link") or item.get("url") or ""),
                str(item.get("description") or item.get("snippet") or ""),
                backend="brightdata",
                query=query,
            )
        )
        if len(rows) >= max_results:
            break
    return rows


def _parse_brightdata_json_payload(
    data: Any, *, query: str, max_results: int
) -> list[dict[str, str]]:
    if isinstance(data, dict):
        rows = _parse_brightdata_json(data, query=query, max_results=max_results)
        if rows:
            return rows
        for key in ("html", "markdown", "body", "content", "text"):
            inner = data.get(key)
            if isinstance(inner, str) and inner.strip():
                nested = _parse_brightdata_response(inner, query=query, max_results=max_results)
                if nested:
                    return nested
    if isinstance(data, list):
        rows: list[dict[str, str]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            link = str(item.get("link") or item.get("url") or "")
            title = str(item.get("title") or link)
            snippet = str(item.get("description") or item.get("snippet") or "")
            if not link.startswith("http") or _is_junk_google_url(link):
                continue
            rows.append(_normalize_result(title, link, snippet, backend="brightdata", query=query))
            if len(rows) >= max_results:
                break
        return rows
    return []


def _looks_like_markdown(text: str) -> bool:
    sample = text[:8000].lower()
    if "<html" in sample or "<!doctype" in sample:
        return False
    return "](http" in text or text.lstrip().startswith("#")


def _parse_brightdata_markdown(text: str, *, query: str, max_results: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    lines = text.splitlines()

    for index, line in enumerate(lines):
        for title, url in MARKDOWN_LINK_RE.findall(line):
            url = url.strip()
            title = title.strip()
            if not url or not title or _is_junk_google_url(url) or url in seen_urls:
                continue
            snippet = ""
            for offset in range(1, 4):
                if index + offset >= len(lines):
                    break
                candidate = lines[index + offset].strip()
                if not candidate or candidate.startswith("#") or MARKDOWN_LINK_RE.search(candidate):
                    break
                snippet = candidate.lstrip("-*> ").strip()
                if snippet:
                    break
            seen_urls.add(url)
            rows.append(_normalize_result(title, url, snippet, backend="brightdata", query=query))
            if len(rows) >= max_results:
                return rows
    return rows


def _parse_google_serp_html(html: str, *, query: str, max_results: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen_urls: set[str] = set()

    for match in GOOGLE_H3_LINK_RE.finditer(html):
        url = _unwrap_google_href(match.group(1))
        title = _strip_html(match.group(2))
        if not url or not title or _is_junk_google_url(url) or url in seen_urls:
            continue
        snippet = ""
        tail = html[match.end() : match.end() + 1200]
        snippet_match = GOOGLE_SNIPPET_RE.search(tail)
        if snippet_match:
            snippet = _strip_html(snippet_match.group(1))
        seen_urls.add(url)
        rows.append(_normalize_result(title, url, snippet, backend="brightdata", query=query))
        if len(rows) >= max_results:
            return rows

    for match in GOOGLE_HREF_RE.finditer(html):
        url = _unwrap_google_href(match.group(1))
        if not url or _is_junk_google_url(url) or url in seen_urls:
            continue
        seen_urls.add(url)
        rows.append(_normalize_result(url, url, "", backend="brightdata", query=query))
        if len(rows) >= max_results:
            break

    return rows


def _parse_brightdata_response(body: str, *, query: str, max_results: int) -> list[dict[str, str]]:
    text = (body or "").strip()
    if not text:
        return []

    if text.startswith("{") or text.startswith("["):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
        if data is not None:
            parsed = _parse_brightdata_json_payload(data, query=query, max_results=max_results)
            if parsed:
                return parsed

    if _looks_like_markdown(text):
        parsed = _parse_brightdata_markdown(text, query=query, max_results=max_results)
        if parsed:
            return parsed

    return _parse_google_serp_html(text, query=query, max_results=max_results)


def _build_brightdata_google_url(query: str, *, max_results: int, data_format: str) -> str:
    count = max(1, min(max_results, 20))
    params: dict[str, str] = {"q": query, "num": str(count), "hl": "en", "gl": "us"}
    if data_format == "json":
        params["brd_json"] = "1"
    return "https://www.google.com/search?" + urllib.parse.urlencode(params)


def _build_brightdata_payload(
    zone: str,
    google_url: str,
    *,
    data_format: str,
) -> dict[str, str]:
    payload: dict[str, str] = {"zone": zone, "url": google_url, "format": "raw"}
    if data_format == "parsed_light":
        payload["data_format"] = "parsed_light"
    elif data_format == "parsed":
        payload["data_format"] = "parsed"
    elif data_format == "markdown":
        payload["data_format"] = "markdown"
    return payload


def brightdata_request(payload: dict[str, str], *, timeout: float = 90) -> str:
    """POST Bright Data /request (SERP, Web Unlocker, etc.)."""
    api_key = get_setting("brightdata_api_key", "").strip()
    if not api_key:
        raise RuntimeError("未配置 Bright Data API Key")
    req = urllib.request.Request(
        BRIGHTDATA_REQUEST_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Bright Data HTTP {exc.code}: {detail[:300]}") from exc


def _brightdata_fetch(api_key: str, payload: dict[str, str]) -> str:
    _ = api_key  # kept for call-site compatibility; key always read from settings
    return brightdata_request(payload)


def _search_brightdata_serp(query: str, *, max_results: int) -> list[dict[str, str]]:
    api_key = get_setting("brightdata_api_key", "").strip()
    zone = get_setting("brightdata_serp_zone", "").strip()
    if not api_key or not zone:
        return []

    data_format = _brightdata_data_format()
    rows: list[dict[str, str]] = []

    if data_format == "auto":
        for attempt_fmt in ("json", "parsed_light"):
            google_url = _build_brightdata_google_url(
                query, max_results=max_results, data_format=attempt_fmt
            )
            payload = _build_brightdata_payload(zone, google_url, data_format=attempt_fmt)
            body = _brightdata_fetch(api_key, payload)
            rows = _parse_brightdata_response(body, query=query, max_results=max_results)
            if rows and _rows_useful(rows):
                return rows
        google_url = _build_brightdata_google_url(query, max_results=max_results, data_format="raw")
        payload = _build_brightdata_payload(zone, google_url, data_format="raw")
        body = _brightdata_fetch(api_key, payload)
        rows = _parse_brightdata_response(body, query=query, max_results=max_results)
    else:
        google_url = _build_brightdata_google_url(
            query, max_results=max_results, data_format=data_format
        )
        payload = _build_brightdata_payload(zone, google_url, data_format=data_format)
        body = _brightdata_fetch(api_key, payload)
        rows = _parse_brightdata_response(body, query=query, max_results=max_results)

        if not rows and data_format == "markdown":
            for fallback in ("parsed_light", "json"):
                google_url = _build_brightdata_google_url(
                    query, max_results=max_results, data_format=fallback
                )
                payload = _build_brightdata_payload(zone, google_url, data_format=fallback)
                body = _brightdata_fetch(api_key, payload)
                rows = _parse_brightdata_response(body, query=query, max_results=max_results)
                if rows and _rows_useful(rows):
                    break

    if rows and not _rows_useful(rows):
        return []

    if not rows:
        raise RuntimeError(
            "Bright Data SERP 响应未能解析为搜索结果（已尝试 JSON/parsed_light/Markdown/HTML）"
        )
    return rows


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
