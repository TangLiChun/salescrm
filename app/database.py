from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.security import hash_password

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = ROOT_DIR / "data" / "salescrm.db"

FOLLOW_UP_STATUSES = ("new", "contacted", "replied", "invalid", "interested")


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
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
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
    if "follow_up_status" not in columns:
        conn.execute(
            "ALTER TABLE contacts ADD COLUMN follow_up_status TEXT NOT NULL DEFAULT 'new'"
        )
        conn.execute(
            "UPDATE contacts SET follow_up_status = 'contacted' WHERE email_sent = 1"
        )

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


def check_db() -> bool:
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1").fetchone()
        return True
    except sqlite3.Error:
        return False


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
                follow_up_status TEXT NOT NULL DEFAULT 'new',
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

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS contact_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(contact_id) REFERENCES contacts(id),
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE INDEX IF NOT EXISTS idx_contacts_user_id ON contacts(user_id);
            CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email);
            CREATE INDEX IF NOT EXISTS idx_contact_notes_contact ON contact_notes(contact_id, created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_next_run ON scheduled_jobs(enabled, next_run_at);

            CREATE TABLE IF NOT EXISTS job_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                message TEXT,
                leads_found INTEGER NOT NULL DEFAULT 0,
                imported INTEGER NOT NULL DEFAULT 0,
                ran_at TEXT NOT NULL,
                FOREIGN KEY(job_id) REFERENCES scheduled_jobs(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_job_runs_job_id ON job_runs(job_id, ran_at DESC);
            """
        )

        _migrate_contacts(conn)

        from app.settings_store import init_settings

        init_settings(conn)

        row = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()
        if row["count"] == 0:
            admin_user = conn.execute(
                "SELECT value FROM app_settings WHERE key = 'default_admin_user'"
            ).fetchone()["value"]
            admin_pass = conn.execute(
                "SELECT value FROM app_settings WHERE key = 'default_admin_password'"
            ).fetchone()["value"]
            now = utc_now()
            conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (admin_user, hash_password(admin_pass), now),
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


def get_user_auth_by_id(user_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT id, username, password_hash FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()


def update_user_password(user_id: int, new_password: str) -> bool:
    with get_conn() as conn:
        cursor = conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(new_password), user_id),
        )
        return cursor.rowcount > 0


def _contact_from_row(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["email_sent"] = bool(data.get("email_sent"))
    if not data.get("follow_up_status"):
        data["follow_up_status"] = "new"
    return data


def _contact_filter_clause(
    user_id: int,
    *,
    status: str = "all",
    follow_up_status: str | None = None,
    q: str | None = None,
) -> tuple[str, list[object]]:
    clauses = ["user_id = ?"]
    params: list[object] = [user_id]
    if status == "sent":
        clauses.append("email_sent = 1")
    elif status == "unsent":
        clauses.append("email_sent = 0")
    if follow_up_status and follow_up_status != "all":
        clauses.append("follow_up_status = ?")
        params.append(follow_up_status)
    if q and q.strip():
        like = f"%{q.strip().lower()}%"
        clauses.append(
            "(lower(org) LIKE ? OR lower(name) LIKE ? OR lower(email) LIKE ? "
            "OR lower(notes) LIKE ? OR lower(roles) LIKE ?)"
        )
        params.extend([like, like, like, like, like])
    return " AND ".join(clauses), params


def count_contacts(
    user_id: int,
    *,
    status: str = "all",
    follow_up_status: str | None = None,
    q: str | None = None,
) -> int:
    where, params = _contact_filter_clause(
        user_id, status=status, follow_up_status=follow_up_status, q=q
    )
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT COUNT(*) AS count FROM contacts WHERE {where}",
            params,
        ).fetchone()
    return int(row["count"])


def list_contacts(
    user_id: int,
    *,
    status: str = "all",
    follow_up_status: str | None = None,
    q: str | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> list[dict]:
    where, params = _contact_filter_clause(
        user_id, status=status, follow_up_status=follow_up_status, q=q
    )
    sql = f"""
        SELECT id, asn, org, name, email, roles, handle, rir, source, notes,
               email_sent, email_sent_at, follow_up_status, created_at, updated_at
        FROM contacts
        WHERE {where}
        ORDER BY email_sent ASC, created_at DESC, id DESC
    """
    if limit is not None:
        sql += " LIMIT ? OFFSET ?"
        params = [*params, limit, offset]
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_contact_from_row(row) for row in rows]


def contact_exists(user_id: int, email: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM contacts WHERE user_id = ? AND lower(email) = lower(?) LIMIT 1",
            (user_id, email.strip()),
        ).fetchone()
    return row is not None


def import_contacts(user_id: int, rows: list[dict]) -> dict:
    from app.import_filters import email_allowed_for_import

    imported = 0
    skipped = 0
    duplicates = 0
    filtered = 0
    now = utc_now()

    with get_conn() as conn:
        for row in rows:
            email = (row.get("email") or "").strip().lower()
            if not email or row.get("error"):
                skipped += 1
                continue
            if not email_allowed_for_import(email):
                filtered += 1
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
                    email_sent, email_sent_at, follow_up_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, 'new', ?, ?)
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

    return {"imported": imported, "skipped": skipped, "duplicates": duplicates, "filtered": filtered}


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
        if sent:
            cursor = conn.execute(
                """
                UPDATE contacts
                SET email_sent = 1, email_sent_at = ?, follow_up_status = 'contacted', updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (now, now, contact_id, user_id),
            )
        else:
            cursor = conn.execute(
                """
                UPDATE contacts
                SET email_sent = 0, email_sent_at = NULL, updated_at = ?
                WHERE id = ? AND user_id = ?
                """,
                (now, contact_id, user_id),
            )
        return cursor.rowcount > 0


def update_contact_follow_up_status(
    user_id: int, contact_id: int, follow_up_status: str
) -> bool:
    if follow_up_status not in FOLLOW_UP_STATUSES:
        return False
    now = utc_now()
    with get_conn() as conn:
        cursor = conn.execute(
            """
            UPDATE contacts
            SET follow_up_status = ?, updated_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (follow_up_status, now, contact_id, user_id),
        )
        return cursor.rowcount > 0


def update_contact(
    user_id: int,
    contact_id: int,
    *,
    org: str | None = None,
    name: str | None = None,
    notes: str | None = None,
    roles: str | None = None,
) -> dict | None:
    updates: dict[str, object] = {}
    if org is not None:
        updates["org"] = org.strip()
    if name is not None:
        updates["name"] = name.strip()
    if notes is not None:
        updates["notes"] = notes.strip()
    if roles is not None:
        updates["roles"] = roles.strip()
    if not updates:
        with get_conn() as conn:
            row = conn.execute(
                """
                SELECT id, asn, org, name, email, roles, handle, rir, source, notes,
                       email_sent, email_sent_at, follow_up_status, created_at, updated_at
                FROM contacts WHERE id = ? AND user_id = ?
                """,
                (contact_id, user_id),
            ).fetchone()
        return _contact_from_row(row) if row else None

    updates["updated_at"] = utc_now()
    set_clause = ", ".join(f"{key} = ?" for key in updates)
    params = list(updates.values()) + [contact_id, user_id]

    with get_conn() as conn:
        cursor = conn.execute(
            f"UPDATE contacts SET {set_clause} WHERE id = ? AND user_id = ?",
            params,
        )
        if cursor.rowcount == 0:
            return None
        row = conn.execute(
            """
            SELECT id, asn, org, name, email, roles, handle, rir, source, notes,
                   email_sent, email_sent_at, follow_up_status, created_at, updated_at
            FROM contacts WHERE id = ? AND user_id = ?
            """,
            (contact_id, user_id),
        ).fetchone()
    return _contact_from_row(row) if row else None


def bulk_update_contacts(
    user_id: int,
    contact_ids: list[int],
    *,
    follow_up_status: str | None = None,
    email_sent: bool | None = None,
) -> dict:
    updated = 0
    for contact_id in contact_ids:
        if follow_up_status is not None:
            if update_contact_follow_up_status(user_id, contact_id, follow_up_status):
                updated += 1
        elif email_sent is not None:
            if mark_contact_sent(user_id, contact_id, sent=email_sent):
                updated += 1
    return {"updated": updated, "requested": len(contact_ids)}


def bulk_delete_contacts(user_id: int, contact_ids: list[int]) -> dict:
    deleted = 0
    for contact_id in contact_ids:
        if delete_contact(user_id, contact_id):
            deleted += 1
    return {"deleted": deleted, "requested": len(contact_ids)}


def _contact_owned(conn: sqlite3.Connection, user_id: int, contact_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM contacts WHERE id = ? AND user_id = ?",
        (contact_id, user_id),
    ).fetchone()
    return row is not None


def list_contact_notes(user_id: int, contact_id: int) -> list[dict] | None:
    with get_conn() as conn:
        if not _contact_owned(conn, user_id, contact_id):
            return None
        rows = conn.execute(
            """
            SELECT id, contact_id, user_id, body, created_at
            FROM contact_notes
            WHERE contact_id = ? AND user_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (contact_id, user_id),
        ).fetchall()
    return [dict(row) for row in rows]


def create_contact_note(user_id: int, contact_id: int, body: str) -> dict | None:
    text = body.strip()
    if not text:
        return None
    now = utc_now()
    with get_conn() as conn:
        if not _contact_owned(conn, user_id, contact_id):
            return None
        cursor = conn.execute(
            """
            INSERT INTO contact_notes (contact_id, user_id, body, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (contact_id, user_id, text, now),
        )
        note_id = cursor.lastrowid
        row = conn.execute(
            "SELECT id, contact_id, user_id, body, created_at FROM contact_notes WHERE id = ?",
            (note_id,),
        ).fetchone()
    return dict(row) if row else None


def delete_contact_note(user_id: int, contact_id: int, note_id: int) -> bool:
    with get_conn() as conn:
        if not _contact_owned(conn, user_id, contact_id):
            return False
        cursor = conn.execute(
            """
            DELETE FROM contact_notes
            WHERE id = ? AND contact_id = ? AND user_id = ?
            """,
            (note_id, contact_id, user_id),
        )
        return cursor.rowcount > 0


def delete_contact(user_id: int, contact_id: int) -> bool:
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM contact_notes WHERE contact_id = ? AND user_id = ?",
            (contact_id, user_id),
        )
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


def insert_job_run(
    job_id: int,
    *,
    status: str,
    message: str,
    leads_found: int = 0,
    imported: int = 0,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO job_runs (job_id, status, message, leads_found, imported, ran_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (job_id, status, message[:500], leads_found, imported, utc_now()),
        )


def list_job_runs(user_id: int, job_id: int, *, limit: int = 20) -> list[dict] | None:
    if get_scheduled_job(user_id, job_id) is None:
        return None
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, job_id, status, message, leads_found, imported, ran_at
            FROM job_runs
            WHERE job_id = ?
            ORDER BY ran_at DESC, id DESC
            LIMIT ?
            """,
            (job_id, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def list_email_templates(user_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, name, subject, body, created_at, updated_at
            FROM email_templates
            WHERE user_id = ?
            ORDER BY updated_at DESC, id DESC
            """,
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_email_template(user_id: int, template_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, name, subject, body, created_at, updated_at
            FROM email_templates
            WHERE id = ? AND user_id = ?
            """,
            (template_id, user_id),
        ).fetchone()
    return dict(row) if row else None


def create_email_template(
    user_id: int, *, name: str, subject: str = "", body: str = ""
) -> dict:
    now = utc_now()
    with get_conn() as conn:
        cursor = conn.execute(
            """
            INSERT INTO email_templates (user_id, name, subject, body, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, name.strip(), subject, body, now, now),
        )
        template_id = cursor.lastrowid
    return get_email_template(user_id, template_id)  # type: ignore[arg-type]


def update_email_template(
    user_id: int,
    template_id: int,
    *,
    name: str | None = None,
    subject: str | None = None,
    body: str | None = None,
) -> dict | None:
    updates: dict[str, object] = {}
    if name is not None:
        updates["name"] = name.strip()
    if subject is not None:
        updates["subject"] = subject
    if body is not None:
        updates["body"] = body
    if not updates:
        return get_email_template(user_id, template_id)

    updates["updated_at"] = utc_now()
    set_clause = ", ".join(f"{key} = ?" for key in updates)
    params = list(updates.values()) + [template_id, user_id]

    with get_conn() as conn:
        cursor = conn.execute(
            f"UPDATE email_templates SET {set_clause} WHERE id = ? AND user_id = ?",
            params,
        )
        if cursor.rowcount == 0:
            return None
    return get_email_template(user_id, template_id)


def delete_email_template(user_id: int, template_id: int) -> bool:
    with get_conn() as conn:
        cursor = conn.execute(
            "DELETE FROM email_templates WHERE id = ? AND user_id = ?",
            (template_id, user_id),
        )
        return cursor.rowcount > 0


def get_contact_stats(user_id: int) -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT follow_up_status, email_sent, source, date(created_at) AS day
            FROM contacts
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchall()

    by_status: dict[str, int] = {}
    by_source: dict[str, int] = {}
    sent = 0
    unsent = 0
    recent: dict[str, int] = {}

    for row in rows:
        status = row["follow_up_status"] or "new"
        by_status[status] = by_status.get(status, 0) + 1
        source = row["source"] or "unknown"
        by_source[source] = by_source.get(source, 0) + 1
        if row["email_sent"]:
            sent += 1
        else:
            unsent += 1
        if row["day"]:
            recent[row["day"]] = recent.get(row["day"], 0) + 1

    recent_imports = [
        {"date": day, "count": count}
        for day, count in sorted(recent.items(), reverse=True)[:14]
    ]
    recent_imports.reverse()

    return {
        "total": len(rows),
        "sent": sent,
        "unsent": unsent,
        "by_follow_up_status": by_status,
        "by_source": by_source,
        "recent_imports": recent_imports,
    }


def _csv_cell(value: object) -> str:
    return f'"{str(value or "").replace(chr(34), chr(34) * 2)}"'


def contacts_to_csv(contacts: list[dict]) -> str:
    headers = [
        "org",
        "name",
        "email",
        "roles",
        "asn",
        "source",
        "follow_up_status",
        "email_sent",
        "notes",
        "created_at",
    ]
    lines = [",".join(headers)]
    for contact in contacts:
        row = [
            contact.get("org") or "",
            contact.get("name") or "",
            contact.get("email") or "",
            contact.get("roles") or "",
            str(contact.get("asn") or ""),
            contact.get("source") or "",
            contact.get("follow_up_status") or "new",
            "1" if contact.get("email_sent") else "0",
            contact.get("notes") or "",
            contact.get("created_at") or "",
        ]
        lines.append(",".join(_csv_cell(v) for v in row))
    return "\n".join(lines) + "\n"
