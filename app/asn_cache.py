"""SQLite TTL cache for ASN RDAP lookup results."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

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


def _ensure_table() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS asn_lookup_cache (
                cache_key TEXT PRIMARY KEY,
                asn INTEGER NOT NULL,
                rir TEXT,
                payload_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_asn_lookup_cache_expires ON asn_lookup_cache(expires_at)"
        )


def _purge_expired(conn) -> None:
    conn.execute("DELETE FROM asn_lookup_cache WHERE expires_at <= ?", (utc_now(),))


def get_cached_rows(asn: int, *, rir: str | None = None) -> list[dict] | None:
    _ensure_table()
    key = _cache_key(asn, rir)
    now = utc_now()
    with get_conn() as conn:
        _purge_expired(conn)
        row = conn.execute(
            "SELECT payload_json FROM asn_lookup_cache WHERE cache_key = ? AND expires_at > ?",
            (key, now),
        ).fetchone()
        if not row:
            return None
        payload = json.loads(row["payload_json"])
        return payload if isinstance(payload, list) else None


def set_cached_rows(asn: int, rows: list[dict], *, rir: str | None = None) -> None:
    _ensure_table()
    key = _cache_key(asn, rir)
    created = utc_now()
    expires = (
        datetime.now(timezone.utc).replace(microsecond=0) + timedelta(seconds=cache_ttl_seconds())
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
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                rir = excluded.rir,
                payload_json = excluded.payload_json,
                created_at = excluded.created_at,
                expires_at = excluded.expires_at
            """,
            (key, asn, primary_rir, json.dumps(rows, ensure_ascii=False), created, expires),
        )
