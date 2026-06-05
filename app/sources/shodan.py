"""Shodan REST API — host search for ASN/org/domain signals."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from arin_lookup import parse_asn
from app.settings_store import get_setting

SHODAN_API_BASE = "https://api.shodan.io"
DEFAULT_TIMEOUT = 25.0
DEFAULT_MAX_MATCHES = 10


class ShodanError(RuntimeError):
    pass


def api_key() -> str:
    return get_setting("shodan_api_key", "").strip()


def is_enabled() -> bool:
    return get_setting("shodan_enabled", "1").strip() != "0"


def is_configured() -> bool:
    return bool(api_key()) and is_enabled()


def get_config() -> dict[str, Any]:
    configured = is_configured()
    info: dict[str, Any] = {
        "configured": configured,
        "enabled": is_enabled(),
        "endpoint": SHODAN_API_BASE,
        "docs": "https://developer.shodan.io/api",
    }
    if not configured:
        return info
    try:
        account = api_info()
        info["plan"] = account.get("plan")
        info["query_credits"] = account.get("query_credits")
        info["scan_credits"] = account.get("scan_credits")
    except ShodanError as exc:
        info["account_error"] = str(exc)
    return info


def _request(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    key = api_key()
    if not key:
        raise ShodanError("Shodan API Key 未配置")
    query = dict(params or {})
    query["key"] = key
    url = f"{SHODAN_API_BASE}{path}?{urllib.parse.urlencode(query)}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(body).get("error") or body
        except json.JSONDecodeError:
            detail = body or exc.reason
        if exc.code in {401, 403}:
            raise ShodanError(f"Shodan 认证失败：{detail}") from exc
        if exc.code == 402:
            raise ShodanError(f"Shodan 积分不足：{detail}") from exc
        raise ShodanError(f"Shodan HTTP {exc.code}：{detail}") from exc
    except urllib.error.URLError as exc:
        raise ShodanError(f"Shodan 请求失败：{exc.reason}") from exc
    if not isinstance(payload, dict):
        raise ShodanError("Shodan 返回非 JSON 对象")
    return payload


def api_info() -> dict[str, Any]:
    return _request("/api-info")


def host_search(
    query: str,
    *,
    page: int = 1,
    minify: bool = True,
) -> dict[str, Any]:
    clean = (query or "").strip()
    if not clean:
        raise ShodanError("请提供 Shodan 搜索 query")
    return _request(
        "/shodan/host/search",
        {"query": clean, "page": max(1, page), "minify": "true" if minify else "false"},
    )


def host_lookup(ip: str) -> dict[str, Any]:
    clean = (ip or "").strip()
    if not clean:
        raise ShodanError("请提供 IP 地址")
    return _request(f"/shodan/host/{urllib.parse.quote(clean)}")


def _parse_asn_value(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value if value > 0 else None
    text = str(value).strip()
    if not text:
        return None
    try:
        return parse_asn(text)
    except (ValueError, TypeError):
        return None


def _match_snippet(match: dict[str, Any]) -> str:
    parts = [
        str(match.get("org") or match.get("isp") or ""),
        str(match.get("asn") or ""),
        str(match.get("ip_str") or ""),
        ", ".join(str(item) for item in (match.get("hostnames") or [])[:3]),
        ", ".join(str(item) for item in (match.get("domains") or [])[:3]),
        str(match.get("port") or ""),
        str((match.get("location") or {}).get("country_name") or ""),
    ]
    return " | ".join(part for part in parts if part)[:1200]


def match_to_web_result(match: dict[str, Any], *, query: str) -> dict[str, str]:
    org = str(match.get("org") or match.get("isp") or "").strip()
    asn = str(match.get("asn") or "").strip()
    ip_str = str(match.get("ip_str") or "").strip()
    title = org or ip_str or "Shodan host"
    if asn:
        title = f"{title} ({asn})"
    url = f"https://www.shodan.io/host/{ip_str}" if ip_str else "https://www.shodan.io"
    return {
        "title": title,
        "url": url,
        "snippet": _match_snippet(match),
        "backend": "shodan",
        "query": query,
    }


def match_to_network(match: dict[str, Any], *, keyword: str) -> dict[str, Any] | None:
    asn = _parse_asn_value(match.get("asn"))
    if not asn:
        return None
    org = str(match.get("org") or match.get("isp") or "").strip()
    domains = [str(item).strip() for item in (match.get("domains") or []) if str(item).strip()]
    return {
        "asn": asn,
        "name": org,
        "source": "shodan",
        "keyword": keyword,
        "domains": domains[:5],
        "ip": str(match.get("ip_str") or ""),
    }


def _build_keyword_queries(keywords: list[str]) -> list[tuple[str, str]]:
    queries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for keyword in keywords:
        clean = (keyword or "").strip()
        if not clean or len(clean) < 2:
            continue
        query = f'org:"{clean}"'
        key = query.lower()
        if key in seen:
            continue
        seen.add(key)
        queries.append((clean, query))
    return queries[:4]


def discover_from_keywords(
    keywords: list[str],
    *,
    max_networks: int = 15,
    max_matches_per_query: int = DEFAULT_MAX_MATCHES,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    if not is_configured():
        return [], []

    networks: list[dict[str, Any]] = []
    web_results: list[dict[str, str]] = []
    seen_asn: set[int] = set()

    for keyword, query in _build_keyword_queries(keywords):
        try:
            payload = host_search(query, minify=True)
        except ShodanError:
            continue
        matches = payload.get("matches") or []
        for match in matches[: max(1, max_matches_per_query)]:
            if not isinstance(match, dict):
                continue
            web_results.append(match_to_web_result(match, query=query))
            network = match_to_network(match, keyword=keyword)
            if not network or network["asn"] in seen_asn:
                continue
            seen_asn.add(network["asn"])
            networks.append(network)
            if len(networks) >= max_networks:
                return networks, web_results
    return networks, web_results
