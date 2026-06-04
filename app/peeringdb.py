from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

PEERINGDB_API = "https://www.peeringdb.com/api/net"


def search_networks(keyword: str, *, limit: int = 20) -> list[dict]:
    params = urllib.parse.urlencode({"name__icontains": keyword, "limit": limit})
    url = f"{PEERINGDB_API}?{params}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.load(resp)
    except urllib.error.URLError:
        return []

    rows = []
    for item in data.get("data") or []:
        asn = item.get("asn")
        name = item.get("name") or ""
        if not asn:
            continue
        rows.append(
            {
                "asn": int(asn),
                "name": name,
                "info_type": item.get("info_type") or "",
                "website": item.get("website") or "",
                "keyword": keyword,
            }
        )
    return rows


def discover_asns(keywords: list[str], *, max_asns: int) -> list[dict]:
    seen: set[int] = set()
    results: list[dict] = []
    per_keyword = max(5, max_asns // max(len(keywords), 1) + 3)

    for keyword in keywords:
        for net in search_networks(keyword, limit=per_keyword):
            asn = net["asn"]
            if asn in seen:
                continue
            seen.add(asn)
            results.append(net)
            if len(results) >= max_asns:
                return results
    return results
