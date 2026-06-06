"""Bright Data Web Scraper API — dataset-based collectors (LinkedIn, etc.)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from app.settings_store import get_setting

BRIGHTDATA_SCRAPE_URL = "https://api.brightdata.com/datasets/v3/scrape"
DEFAULT_SCRAPE_TIMEOUT = 120.0


def api_key_configured() -> bool:
    return bool(get_setting("brightdata_api_key", "").strip())


def scrape_dataset(
    dataset_id: str,
    inputs: list[dict[str, Any]],
    *,
    include_errors: bool = True,
    timeout: float = DEFAULT_SCRAPE_TIMEOUT,
) -> list[dict[str, Any]]:
    """POST /datasets/v3/scrape — sync batch scrape for a Bright Data dataset."""
    api_key = get_setting("brightdata_api_key", "").strip()
    if not api_key:
        raise RuntimeError("未配置 Bright Data API Key")
    if not dataset_id:
        raise RuntimeError("未配置 Bright Data dataset_id")
    if not inputs:
        return []

    params = urllib.parse.urlencode(
        {
            "dataset_id": dataset_id,
            "include_errors": "true" if include_errors else "false",
        }
    )
    req = urllib.request.Request(
        f"{BRIGHTDATA_SCRAPE_URL}?{params}",
        data=json.dumps({"input": inputs}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Bright Data Scraper HTTP {exc.code}: {detail[:400]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Bright Data Scraper 连接失败: {exc.reason}") from exc

    return parse_scrape_response(body)


def parse_scrape_response(body: str) -> list[dict[str, Any]]:
    text = (body or "").strip()
    if not text:
        return []

    if text.startswith("["):
        data = json.loads(text)
        if isinstance(data, list):
            return [row for row in data if isinstance(row, dict)]
        return []

    if text.startswith("{"):
        data = json.loads(text)
        if isinstance(data, dict):
            if data.get("snapshot_id"):
                raise RuntimeError("Bright Data 返回异步 snapshot，请减少批量 URL 或稍后重试")
            if data.get("error"):
                raise RuntimeError(str(data.get("error")))
            return [data]
        return []

    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows
