"""PostgreSQL TTL cache for ASN RDAP lookup results."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta

from app.database import get_conn, utc_now

DEFAULT_TTL_SECONDS = 86400


def cache_ttl_seconds() -> int:
    try:
        return max(60, int(os.getenv("ASN_CACHE_TTL_SECONDS", str(DEFAULT_TTL_SECONDS))))
    except ValueError:
        return DEFAULT_TTL_SECONDS


def _cache_key(asn: int, rir: str | None = None) -> str:
    if rir:
        return f"{asn}:{rir}"
    return str(asn)


def _purge_expired(conn) -> None:
    conn.execute("DELETE FROM asn_lookup_cache WHERE expires_at <= %s", (utc_now(),))


def get_cached_rows(asn: int, *, rir: str | None = None) -> list[dict] | None:
    key = _cache_key(asn, rir)
    now = utc_now()
    with get_conn() as conn:
        _purge_expired(conn)
        row = conn.execute(
            "SELECT payload_json FROM asn_lookup_cache WHERE cache_key = %s AND expires_at > %s",
            (key, now),
        ).fetchone()
        if not row:
            return None
        payload = row["payload_json"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        return payload if isinstance(payload, list) else None


def set_cached_rows(asn: int, rows: list[dict], *, rir: str | None = None) -> None:
    key = _cache_key(asn, rir)
    created = utc_now()
    expires = (
        datetime.now(UTC).replace(microsecond=0) + timedelta(seconds=cache_ttl_seconds())
    ).isoformat()
    primary_rir = rir
    if not primary_rir:
        for row in rows:
            candidate = (row.get("rir") or "").strip()
            if candidate:
                primary_rir = candidate
                break

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO asn_lookup_cache (cache_key, asn, rir, payload_json, created_at, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT(cache_key) DO UPDATE SET
                rir = EXCLUDED.rir,
                payload_json = EXCLUDED.payload_json,
                created_at = EXCLUDED.created_at,
                expires_at = EXCLUDED.expires_at
            """,
            (key, asn, primary_rir, json.dumps(rows, ensure_ascii=False), created, expires),
        )
