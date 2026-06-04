from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.security import hash_password

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT_DIR / "data" / "salescrm.db"
DEFAULT_ADMIN_USER = os.getenv("DEFAULT_ADMIN_USER", "admin")
DEFAULT_ADMIN_PASSWORD = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin123")


def db_path() -> Path:
    configured = os.getenv("DATABASE_PATH")
    if configured:
        return Path(configured)
    return DEFAULT_DB_PATH


@contextmanager
def get_conn():
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {row["name"] for row in rows}


def _migrate_contacts(conn: sqlite3.Connection) -> None:
    columns = _table_columns(conn, "contacts")
    if "email_sent" not in columns:
        conn.execute("ALTER TABLE contacts ADD COLUMN email_sent INTEGER NOT NULL DEFAULT 0")
    if "email_sent_at" not in columns:
        conn.execute("ALTER TABLE contacts ADD COLUMN email_sent_at TEXT")

    dedupe_contacts(conn=conn)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_contacts_user_email ON contacts(user_id, email)")
    try:
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_contacts_user_email_unique ON contacts(user_id, email)"
        )
    except sqlite3.IntegrityError:
        dedupe_contacts(conn=conn)
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_contacts_user_email_unique ON contacts(user_id, email)"
        )


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                asn INTEGER,
                org TEXT,
                name TEXT,
                email TEXT NOT NULL,
                roles TEXT,
                handle TEXT,
                rir TEXT,
                source TEXT NOT NULL DEFAULT 'arin',
                notes TEXT,
                email_sent INTEGER NOT NULL DEFAULT 0,
                email_sent_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE TABLE IF NOT EXISTS scheduled_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                query TEXT NOT NULL,
                interval_hours INTEGER NOT NULL DEFAULT 24,
                min_score INTEGER NOT NULL DEFAULT 60,
                auto_import INTEGER NOT NULL DEFAULT 1,
                enabled INTEGER NOT NULL DEFAULT 1,
                last_run_at TEXT,
                last_run_status TEXT,
                last_run_message TEXT,
                next_run_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE INDEX IF NOT EXISTS idx_contacts_user_id ON contacts(user_id);
            CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email);
            CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_next_run ON scheduled_jobs(enabled, next_run_at);
            """
        )

        _migrate_contacts(conn)

        row = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()
        if row["count"] == 0:
            now = utc_now()
            conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (DEFAULT_ADMIN_USER, hash_password(DEFAULT_ADMIN_PASSWORD), now),
            )


def get_user_by_username(username: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT id, username, password_hash FROM users WHERE username = ?",
            (username.strip(),),
        ).fetchone()


def get_user_by_id(user_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT id, username FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()


def _contact_from_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["email_sent"] = bool(data.get("email_sent"))
    return data


def list_contacts(user_id: int, *, status: str = "all") -> list[dict]:
    clauses = ["user_id = ?"]
    params: list[object] = [user_id]
    if status == "sent":
        clauses.append("email_sent = 1")
    elif status == "unsent":
        clauses.append("email_sent = 0")

    where = " AND ".join(clauses)
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT id, asn, org, name, email, roles, handle, rir, source, notes,
                   email_sent, email_sent_at, created_at, updated_at
            FROM contacts
            WHERE {where}
            ORDER BY email_sent ASC, created_at DESC, id DESC
            """,
            params,
        ).fetchall()
    return [_contact_from_row(row) for row in rows]


def contact_exists(user_id: int, email: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM contacts WHERE user_id = ? AND lower(email) = lower(?) LIMIT 1",
            (user_id, email.strip()),
        ).fetchone()
    return row is not None


def import_contacts(user_id: int, rows: list[dict]) -> dict:
    imported = 0
    skipped = 0
    duplicates = 0
    now = utc_now()

    with get_conn() as conn:
        for row in rows:
            email = (row.get("email") or "").strip().lower()
            if not email or row.get("error"):
                skipped += 1
                continue

            existing = conn.execute(
                "SELECT id, org, name, roles, notes FROM contacts WHERE user_id = ? AND lower(email) = ?",
                (user_id, email),
            ).fetchone()
            if existing:
                duplicates += 1
                merged_notes = _merge_notes(existing["notes"], row.get("notes") or "")
                merged_roles = _merge_roles(existing["roles"], row.get("roles") or [])
                conn.execute(
                    """
                    UPDATE contacts
                    SET org = CASE WHEN org = '' THEN ? ELSE org END,
                        name = CASE WHEN name = '' THEN ? ELSE name END,
                        roles = ?,
                        notes = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        row.get("org") or "",
                        row.get("name") or "",
                        merged_roles,
                        merged_notes,
                        now,
                        existing["id"],
                    ),
                )
                continue

            roles = ",".join(row.get("roles") or []) if isinstance(row.get("roles"), list) else (row.get("roles") or "")
            notes = row.get("notes") or ""
            conn.execute(
                """
                INSERT INTO contacts (
                    user_id, asn, org, name, email, roles, handle, rir, source, notes,
                    email_sent, email_sent_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?, ?)
                """,
                (
                    user_id,
                    row.get("asn"),
                    row.get("org") or "",
                    row.get("name") or "",
                    email,
                    roles,
                    row.get("handle") or "",
                    row.get("rir") or "ARIN",
                    row.get("source") or "arin",
                    notes,
                    now,
                    now,
                ),
            )
            imported += 1

    return {"imported": imported, "skipped": skipped, "duplicates": duplicates}


def _merge_notes(old: str | None, new: str) -> str:
    old = (old or "").strip()
    new = new.strip()
    if not new:
        return old
    if not old:
        return new
    if new in old:
        return old
    return f"{old} | {new}"


def _merge_roles(old: str | None, new: list[str] | str) -> str:
    items = []
    for value in [(old or ""), ",".join(new) if isinstance(new, list) else (new or "")]:
        for part in value.split(","):
            part = part.strip()
            if part and part not in items:
                items.append(part)
    return ",".join(items)


def mark_contact_sent(user_id: int, contact_id: int, *, sent: bool = True) -> bool:
    now = utc_now()
    with get_conn() as conn:
        cursor = conn.execute(
            """
            UPDATE contacts
            SET email_sent = ?, email_sent_at = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (1 if sent else 0, now if sent else None, now, contact_id, user_id),
        )
        return cursor.rowcount > 0


def delete_contact(user_id: int, contact_id: int) -> bool:
    with get_conn() as conn:
        cursor = conn.execute(
            "DELETE FROM contacts WHERE id = ? AND user_id = ?",
            (contact_id, user_id),
        )
        return cursor.rowcount > 0


def dedupe_contacts(*, user_id: int | None = None, conn: sqlite3.Connection | None = None) -> dict:
    removed = 0

    def run(connection: sqlite3.Connection) -> dict:
        nonlocal removed
        where = "WHERE user_id = ?" if user_id is not None else ""
        params = [user_id] if user_id is not None else []
        rows = connection.execute(
            f"""
            SELECT id, user_id, email, org, name, roles, notes, email_sent, email_sent_at, created_at
            FROM contacts
            {where}
            ORDER BY user_id, lower(email), email_sent DESC, created_at DESC, id DESC
            """,
            params,
        ).fetchall()

        seen: set[tuple[int, str]] = set()
        for row in rows:
            key = (row["user_id"], (row["email"] or "").lower())
            if key in seen:
                connection.execute("DELETE FROM contacts WHERE id = ?", (row["id"],))
                removed += 1
                continue
            seen.add(key)
        return {"removed": removed, "remaining": len(seen)}

    if conn is not None:
        return run(conn)

    with get_conn() as connection:
        return run(connection)


def list_scheduled_jobs(user_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, name, query, interval_hours, min_score, auto_import, enabled,
                   last_run_at, last_run_status, last_run_message, next_run_at,
                   created_at, updated_at
            FROM scheduled_jobs
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (user_id,),
        ).fetchall()
    jobs = []
    for row in rows:
        item = dict(row)
        item["auto_import"] = bool(item["auto_import"])
        item["enabled"] = bool(item["enabled"])
        jobs.append(item)
    return jobs


def get_scheduled_job(user_id: int, job_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM scheduled_jobs WHERE id = ? AND user_id = ?",
            (job_id, user_id),
        ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["auto_import"] = bool(item["auto_import"])
    item["enabled"] = bool(item["enabled"])
    return item


def create_scheduled_job(
    user_id: int,
    *,
    name: str,
    query: str,
    interval_hours: int,
    min_score: int,
    auto_import: bool,
    enabled: bool = True,
) -> dict:
    now = utc_now()
    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO scheduled_jobs (
                user_id, name, query, interval_hours, min_score, auto_import, enabled,
                next_run_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                name.strip(),
                query.strip(),
                interval_hours,
                min_score,
                1 if auto_import else 0,
                1 if enabled else 0,
                now,
                now,
                now,
            ),
        )
        job_id = cursor.lastrowid
    job = get_scheduled_job(user_id, job_id)
    assert job is not None
    return job


def update_scheduled_job(user_id: int, job_id: int, **fields) -> dict | None:
    allowed = {"name", "query", "interval_hours", "min_score", "auto_import", "enabled"}
    updates = {key: value for key, value in fields.items() if key in allowed and value is not None}
    if not updates:
        return get_scheduled_job(user_id, job_id)

    if "auto_import" in updates:
        updates["auto_import"] = 1 if updates["auto_import"] else 0
    if "enabled" in updates:
        updates["enabled"] = 1 if updates["enabled"] else 0

    updates["updated_at"] = utc_now()
    set_clause = ", ".join(f"{key} = ?" for key in updates)
    params = list(updates.values()) + [job_id, user_id]

    with get_conn() as conn:
        cursor = conn.execute(
            f"UPDATE scheduled_jobs SET {set_clause} WHERE id = ? AND user_id = ?",
            params,
        )
        if cursor.rowcount == 0:
            return None
    return get_scheduled_job(user_id, job_id)


def delete_scheduled_job(user_id: int, job_id: int) -> bool:
    with get_conn() as conn:
        cursor = conn.execute(
            "DELETE FROM scheduled_jobs WHERE id = ? AND user_id = ?",
            (job_id, user_id),
        )
        return cursor.rowcount > 0


def list_due_scheduled_jobs() -> list[dict]:
    now = utc_now()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM scheduled_jobs
            WHERE enabled = 1 AND (next_run_at IS NULL OR next_run_at <= ?)
            ORDER BY next_run_at ASC, id ASC
            """,
            (now,),
        ).fetchall()
    jobs = []
    for row in rows:
        item = dict(row)
        item["auto_import"] = bool(item["auto_import"])
        item["enabled"] = bool(item["enabled"])
        jobs.append(item)
    return jobs


def mark_job_run(job_id: int, *, status: str, message: str, interval_hours: int) -> None:
    now_dt = datetime.now(timezone.utc).replace(microsecond=0)
    next_run = (now_dt + timedelta(hours=interval_hours)).isoformat()
    now = now_dt.isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE scheduled_jobs
            SET last_run_at = ?, last_run_status = ?, last_run_message = ?,
                next_run_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (now, status, message[:500], next_run, now, job_id),
        )
