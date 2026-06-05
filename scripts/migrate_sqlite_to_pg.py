#!/usr/bin/env python3
"""One-time migration from legacy SQLite data/salescrm.db to PostgreSQL."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE = ROOT / "data" / "salescrm.db"

TABLES = (
    ("users", ["id", "username", "password_hash", "created_at"]),
    (
        "contacts",
        [
            "id",
            "user_id",
            "asn",
            "org",
            "name",
            "email",
            "roles",
            "handle",
            "rir",
            "source",
            "notes",
            "email_sent",
            "email_sent_at",
            "follow_up_status",
            "created_at",
            "updated_at",
        ],
    ),
    (
        "scheduled_jobs",
        [
            "id",
            "user_id",
            "name",
            "query",
            "interval_hours",
            "min_score",
            "auto_import",
            "enabled",
            "last_run_at",
            "last_run_status",
            "last_run_message",
            "next_run_at",
            "created_at",
            "updated_at",
        ],
    ),
    ("app_settings", ["key", "value", "updated_at"]),
    ("contact_notes", ["id", "contact_id", "user_id", "body", "created_at"]),
    ("job_runs", ["id", "job_id", "status", "message", "leads_found", "imported", "ran_at"]),
    (
        "email_templates",
        ["id", "user_id", "name", "subject", "body", "created_at", "updated_at"],
    ),
    (
        "background_jobs",
        [
            "id",
            "user_id",
            "job_type",
            "status",
            "params_json",
            "progress_json",
            "result_json",
            "message",
            "created_at",
            "updated_at",
            "finished_at",
        ],
    ),
)


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value in (1, "1", "true", "TRUE"):
        return True
    return False


def _sqlite_path() -> Path:
    configured = os.getenv("SQLITE_PATH", "").strip()
    return Path(configured) if configured else DEFAULT_SQLITE


def main() -> int:
    sqlite_path = _sqlite_path()
    if not sqlite_path.exists():
        print(f"SQLite file not found: {sqlite_path}", file=sys.stderr)
        return 1

    os.environ.setdefault("POSTGRES_HOST", "localhost")
    from app.database import get_conn, init_db

    init_db()

    src = sqlite3.connect(sqlite_path)
    src.row_factory = sqlite3.Row

    with get_conn() as conn:
        user_count = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"]
        if user_count:
            print("PostgreSQL already has users; skipping migration.")
            return 0

        for table, columns in TABLES:
            if table not in {
                row[0]
                for row in src.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }:
                continue
            rows = src.execute(f"SELECT * FROM {table}").fetchall()
            if not rows:
                continue
            placeholders = ", ".join(["%s"] * len(columns))
            col_sql = ", ".join(columns)
            for row in rows:
                values = []
                for col in columns:
                    value = row[col]
                    if col in {"email_sent", "auto_import", "enabled"}:
                        value = _bool(value)
                    values.append(value)
                conn.execute(
                    f"INSERT INTO {table} ({col_sql}) VALUES ({placeholders})",
                    values,
                )
            if table in {"users", "contacts", "scheduled_jobs", "contact_notes", "job_runs", "email_templates", "background_jobs"}:
                conn.execute(
                    f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), COALESCE(MAX(id), 1)) FROM {table}"
                )
            print(f"Migrated {len(rows)} rows from {table}")

        if "asn_lookup_cache" in {
            row[0] for row in src.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }:
            rows = src.execute("SELECT * FROM asn_lookup_cache").fetchall()
            for row in rows:
                conn.execute(
                    """
                    INSERT INTO asn_lookup_cache (cache_key, asn, rir, payload_json, created_at, expires_at)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (cache_key) DO NOTHING
                    """,
                    (
                        row["cache_key"],
                        row["asn"],
                        row["rir"],
                        row["payload_json"],
                        row["created_at"],
                        row["expires_at"],
                    ),
                )
            print(f"Migrated {len(rows)} rows from asn_lookup_cache")

    src.close()
    print("Migration complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
