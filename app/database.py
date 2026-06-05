from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import psycopg

from app.db import db_path, get_conn
from app.security import hash_password

FOLLOW_UP_STATUSES = ("new", "contacted", "replied", "invalid", "interested")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _iso(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _table_columns(conn, table: str) -> set[str]:
    rows = conn.execute(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        """,
        (table,),
    ).fetchall()
    return {row["column_name"] for row in rows}


def _migrate_contacts(conn) -> None:
    columns = _table_columns(conn, "contacts")
    if "email_sent" not in columns:
        conn.execute(
            "ALTER TABLE contacts ADD COLUMN email_sent BOOLEAN NOT NULL DEFAULT FALSE"
        )
    if "email_sent_at" not in columns:
        conn.execute("ALTER TABLE contacts ADD COLUMN email_sent_at TIMESTAMPTZ")
    if "follow_up_status" not in columns:
        conn.execute(
            "ALTER TABLE contacts ADD COLUMN follow_up_status TEXT NOT NULL DEFAULT 'new'"
        )
        conn.execute(
            "UPDATE contacts SET follow_up_status = 'contacted' WHERE email_sent = TRUE"
        )

    dedupe_contacts(conn=conn)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_contacts_user_email ON contacts(user_id, email)")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_contacts_user_email_unique ON contacts(user_id, email)"
    )


REQUIRED_TABLES = (
    "users",
    "contacts",
    "scheduled_jobs",
    "background_jobs",
    "app_settings",
    "contact_notes",
    "job_runs",
    "email_templates",
    "pi_chat_threads",
    "asn_lookup_cache",
)


def check_db() -> bool:
    try:
        with get_conn() as conn:
            conn.execute("SELECT 1").fetchone()
        return True
    except psycopg.Error:
        return False


def check_schema() -> bool:
    try:
        with get_conn() as conn:
            for table in REQUIRED_TABLES:
                row = conn.execute(
                    """
                    SELECT 1
                    FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = %s
                    """,
                    (table,),
                ).fetchone()
                if not row:
                    return False
        return True
    except psycopg.Error:
        return False


def init_db() -> None:
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS contacts (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                asn INTEGER,
                org TEXT,
                name TEXT,
                email TEXT NOT NULL,
                roles TEXT,
                handle TEXT,
                rir TEXT,
                source TEXT NOT NULL DEFAULT 'arin',
                notes TEXT,
                email_sent BOOLEAN NOT NULL DEFAULT FALSE,
                email_sent_at TIMESTAMPTZ,
                follow_up_status TEXT NOT NULL DEFAULT 'new',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS scheduled_jobs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                name TEXT NOT NULL,
                query TEXT NOT NULL,
                interval_hours INTEGER NOT NULL DEFAULT 24,
                min_score INTEGER NOT NULL DEFAULT 60,
                auto_import BOOLEAN NOT NULL DEFAULT TRUE,
                enabled BOOLEAN NOT NULL DEFAULT TRUE,
                last_run_at TIMESTAMPTZ,
                last_run_status TEXT,
                last_run_message TEXT,
                next_run_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS contact_notes (
                id SERIAL PRIMARY KEY,
                contact_id INTEGER NOT NULL REFERENCES contacts(id),
                user_id INTEGER NOT NULL REFERENCES users(id),
                body TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS job_runs (
                id SERIAL PRIMARY KEY,
                job_id INTEGER NOT NULL REFERENCES scheduled_jobs(id) ON DELETE CASCADE,
                status TEXT NOT NULL,
                message TEXT,
                leads_found INTEGER NOT NULL DEFAULT 0,
                imported INTEGER NOT NULL DEFAULT 0,
                ran_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS email_templates (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                name TEXT NOT NULL,
                subject TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS background_jobs (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                job_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                params_json TEXT NOT NULL DEFAULT '{}',
                progress_json TEXT NOT NULL DEFAULT '{}',
                result_json TEXT,
                message TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                finished_at TIMESTAMPTZ
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS asn_lookup_cache (
                cache_key TEXT PRIMARY KEY,
                asn INTEGER NOT NULL,
                rir TEXT,
                payload_json TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                expires_at TIMESTAMPTZ NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pi_chat_threads (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                title TEXT NOT NULL DEFAULT '',
                history_json JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_contacts_user_id ON contacts(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_contact_notes_contact ON contact_notes(contact_id, created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_next_run ON scheduled_jobs(enabled, next_run_at)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_job_runs_job_id ON job_runs(job_id, ran_at DESC)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_email_templates_user ON email_templates(user_id, updated_at DESC)"
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_background_jobs_user_status
                ON background_jobs(user_id, status, updated_at DESC)
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_asn_lookup_cache_expires ON asn_lookup_cache(expires_at)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_pi_chat_threads_user ON pi_chat_threads(user_id, updated_at DESC)"
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
                "INSERT INTO users (username, password_hash, created_at) VALUES (%s, %s, %s)",
                (admin_user, hash_password(admin_pass), now),
            )


def get_user_by_username(username: str) -> dict | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT id, username, password_hash FROM users WHERE username = %s",
            (username.strip(),),
        ).fetchone()


def get_agent_owner_user_id() -> int | None:
    from app.settings_store import get_setting

    username = get_setting("default_admin_user", "admin")
    row = get_user_by_username(username)
    if row:
        return int(row["id"])
    with get_conn() as conn:
        first = conn.execute("SELECT id FROM users ORDER BY id LIMIT 1").fetchone()
    return int(first["id"]) if first else None


def get_user_by_id(user_id: int) -> dict | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT id, username FROM users WHERE id = %s",
            (user_id,),
        ).fetchone()


def get_user_auth_by_id(user_id: int) -> dict | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT id, username, password_hash FROM users WHERE id = %s",
            (user_id,),
        ).fetchone()


def update_user_password(user_id: int, new_password: str) -> bool:
    with get_conn() as conn:
        cursor = conn.execute(
            "UPDATE users SET password_hash = %s WHERE id = %s",
            (hash_password(new_password), user_id),
        )
        return cursor.rowcount > 0


def _contact_from_row(row: dict | None) -> dict:
    if not row:
        return {}
    data = dict(row)
    data["email_sent"] = bool(data.get("email_sent"))
    data["created_at"] = _iso(data.get("created_at"))
    data["updated_at"] = _iso(data.get("updated_at"))
    data["email_sent_at"] = _iso(data.get("email_sent_at"))
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
    clauses = ["user_id = %s"]
    params: list[object] = [user_id]
    if status == "sent":
        clauses.append("email_sent = TRUE")
    elif status == "unsent":
        clauses.append("email_sent = FALSE")
    if follow_up_status and follow_up_status != "all":
        clauses.append("follow_up_status = %s")
        params.append(follow_up_status)
    if q and q.strip():
        like = f"%{q.strip().lower()}%"
        clauses.append(
            "(lower(org) LIKE %s OR lower(name) LIKE %s OR lower(email) LIKE %s "
            "OR lower(notes) LIKE %s OR lower(roles) LIKE %s)"
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
        sql += " LIMIT %s OFFSET %s"
        params = [*params, limit, offset]
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [_contact_from_row(row) for row in rows]


def get_contact(user_id: int, contact_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, asn, org, name, email, roles, handle, rir, source, notes,
                   email_sent, email_sent_at, follow_up_status, created_at, updated_at
            FROM contacts
            WHERE id = %s AND user_id = %s
            """,
            (contact_id, user_id),
        ).fetchone()
    return _contact_from_row(row) if row else None


def list_contact_emails(user_id: int) -> set[str]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT lower(email) AS email FROM contacts WHERE user_id = %s",
            (user_id,),
        ).fetchall()
    return {row["email"] for row in rows if row["email"]}


def contact_exists(user_id: int, email: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM contacts WHERE user_id = %s AND lower(email) = lower(%s) LIMIT 1",
            (user_id, email.strip()),
        ).fetchone()
    return row is not None


def _pick_import_text(*values: object) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def normalize_import_row(row: dict) -> dict:
    """Normalize import payloads so org/name are preserved across all import paths."""
    normalized = dict(row)
    org = _pick_import_text(
        row.get("org"),
        row.get("organization"),
        row.get("company"),
        row.get("network_name"),
    )
    name = _pick_import_text(
        row.get("name"),
        row.get("contact_name"),
        row.get("contact"),
        row.get("fn"),
    )
    handle = _pick_import_text(row.get("handle"))
    if not name and handle and not handle.upper().startswith(("ORG", "NET", "AS-", "AS")):
        name = handle

    normalized["org"] = org
    normalized["name"] = name
    if not normalized.get("asn") and row.get("asn"):
        normalized["asn"] = row.get("asn")
    return normalized


def import_contacts(user_id: int, rows: list[dict]) -> dict:
    from app.import_filters import email_allowed_for_import

    imported = 0
    skipped = 0
    duplicates = 0
    filtered = 0
    now = utc_now()

    with get_conn() as conn:
        for raw_row in rows:
            row = normalize_import_row(raw_row)
            email = (row.get("email") or "").strip().lower()
            if not email or row.get("error"):
                skipped += 1
                continue
            if not email_allowed_for_import(email):
                filtered += 1
                continue

            existing = conn.execute(
                "SELECT id, org, name, roles, notes FROM contacts WHERE user_id = %s AND lower(email) = %s",
                (user_id, email),
            ).fetchone()
            if existing:
                duplicates += 1
                merged_notes = _merge_notes(existing["notes"], row.get("notes") or "")
                merged_roles = _merge_roles(existing["roles"], row.get("roles") or [])
                existing_org = (existing["org"] or "").strip()
                existing_name = (existing["name"] or "").strip()
                merged_org = existing_org or (row.get("org") or "").strip()
                merged_name = existing_name or (row.get("name") or "").strip()
                conn.execute(
                    """
                    UPDATE contacts
                    SET org = %s,
                        name = %s,
                        roles = %s,
                        notes = %s,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (
                        merged_org,
                        merged_name,
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
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, NULL, 'new', %s, %s)
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
                SET email_sent = TRUE, email_sent_at = %s, follow_up_status = 'contacted', updated_at = %s
                WHERE id = %s AND user_id = %s
                """,
                (now, now, contact_id, user_id),
            )
        else:
            cursor = conn.execute(
                """
                UPDATE contacts
                SET email_sent = FALSE, email_sent_at = NULL, updated_at = %s
                WHERE id = %s AND user_id = %s
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
            SET follow_up_status = %s, updated_at = %s
            WHERE id = %s AND user_id = %s
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
                FROM contacts WHERE id = %s AND user_id = %s
                """,
                (contact_id, user_id),
            ).fetchone()
        return _contact_from_row(row) if row else None

    updates["updated_at"] = utc_now()
    set_clause = ", ".join(f"{key} = %s" for key in updates)
    params = list(updates.values()) + [contact_id, user_id]

    with get_conn() as conn:
        cursor = conn.execute(
            f"UPDATE contacts SET {set_clause} WHERE id = %s AND user_id = %s",
            params,
        )
        if cursor.rowcount == 0:
            return None
        row = conn.execute(
            """
            SELECT id, asn, org, name, email, roles, handle, rir, source, notes,
                   email_sent, email_sent_at, follow_up_status, created_at, updated_at
            FROM contacts WHERE id = %s AND user_id = %s
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


def _contact_owned(conn: Any, user_id: int, contact_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM contacts WHERE id = %s AND user_id = %s",
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
            WHERE contact_id = %s AND user_id = %s
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
        row = conn.execute(
            """
            INSERT INTO contact_notes (contact_id, user_id, body, created_at)
            VALUES (%s, %s, %s, %s)
            RETURNING id, contact_id, user_id, body, created_at
            """,
            (contact_id, user_id, text, now),
        ).fetchone()
    return dict(row) if row else None


def delete_contact_note(user_id: int, contact_id: int, note_id: int) -> bool:
    with get_conn() as conn:
        if not _contact_owned(conn, user_id, contact_id):
            return False
        cursor = conn.execute(
            """
            DELETE FROM contact_notes
            WHERE id = %s AND contact_id = %s AND user_id = %s
            """,
            (note_id, contact_id, user_id),
        )
        return cursor.rowcount > 0


def delete_contact(user_id: int, contact_id: int) -> bool:
    with get_conn() as conn:
        conn.execute(
            "DELETE FROM contact_notes WHERE contact_id = %s AND user_id = %s",
            (contact_id, user_id),
        )
        cursor = conn.execute(
            "DELETE FROM contacts WHERE id = %s AND user_id = %s",
            (contact_id, user_id),
        )
        return cursor.rowcount > 0


def dedupe_contacts(*, user_id: int | None = None, conn: Any | None = None) -> dict:
    removed = 0

    def run(connection: Any) -> dict:
        nonlocal removed
        where = "WHERE user_id = %s" if user_id is not None else ""
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
                connection.execute("DELETE FROM contacts WHERE id = %s", (row["id"],))
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
            WHERE user_id = %s
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
            "SELECT * FROM scheduled_jobs WHERE id = %s AND user_id = %s",
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
        row = conn.execute(
            """
            INSERT INTO scheduled_jobs (
                user_id, name, query, interval_hours, min_score, auto_import, enabled,
                next_run_at, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                user_id,
                name.strip(),
                query.strip(),
                interval_hours,
                min_score,
                auto_import,
                enabled,
                now,
                now,
                now,
            ),
        ).fetchone()
        job_id = int(row["id"])
    job = get_scheduled_job(user_id, job_id)
    assert job is not None
    return job


def update_scheduled_job(user_id: int, job_id: int, **fields) -> dict | None:
    allowed = {"name", "query", "interval_hours", "min_score", "auto_import", "enabled"}
    updates = {key: value for key, value in fields.items() if key in allowed and value is not None}
    if not updates:
        return get_scheduled_job(user_id, job_id)

    if "auto_import" in updates:
        updates["auto_import"] = bool(updates["auto_import"])
    if "enabled" in updates:
        updates["enabled"] = bool(updates["enabled"])

    updates["updated_at"] = utc_now()
    set_clause = ", ".join(f"{key} = %s" for key in updates)
    params = list(updates.values()) + [job_id, user_id]

    with get_conn() as conn:
        cursor = conn.execute(
            f"UPDATE scheduled_jobs SET {set_clause} WHERE id = %s AND user_id = %s",
            params,
        )
        if cursor.rowcount == 0:
            return None
    return get_scheduled_job(user_id, job_id)


def delete_scheduled_job(user_id: int, job_id: int) -> bool:
    with get_conn() as conn:
        cursor = conn.execute(
            "DELETE FROM scheduled_jobs WHERE id = %s AND user_id = %s",
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
            WHERE enabled = TRUE AND (next_run_at IS NULL OR next_run_at <= %s)
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
            SET last_run_at = %s, last_run_status = %s, last_run_message = %s,
                next_run_at = %s, updated_at = %s
            WHERE id = %s
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
            VALUES (%s, %s, %s, %s, %s, %s)
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
            WHERE job_id = %s
            ORDER BY ran_at DESC, id DESC
            LIMIT %s
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
            WHERE user_id = %s
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
            WHERE id = %s AND user_id = %s
            """,
            (template_id, user_id),
        ).fetchone()
    return dict(row) if row else None


def create_email_template(
    user_id: int, *, name: str, subject: str = "", body: str = ""
) -> dict:
    now = utc_now()
    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO email_templates (user_id, name, subject, body, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (user_id, name.strip(), subject, body, now, now),
        ).fetchone()
        template_id = int(row["id"])
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
    set_clause = ", ".join(f"{key} = %s" for key in updates)
    params = list(updates.values()) + [template_id, user_id]

    with get_conn() as conn:
        cursor = conn.execute(
            f"UPDATE email_templates SET {set_clause} WHERE id = %s AND user_id = %s",
            params,
        )
        if cursor.rowcount == 0:
            return None
    return get_email_template(user_id, template_id)


def delete_email_template(user_id: int, template_id: int) -> bool:
    with get_conn() as conn:
        cursor = conn.execute(
            "DELETE FROM email_templates WHERE id = %s AND user_id = %s",
            (template_id, user_id),
        )
        return cursor.rowcount > 0


def get_contact_stats(user_id: int) -> dict:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT follow_up_status, email_sent, source, (created_at::date)::text AS day
            FROM contacts
            WHERE user_id = %s
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


def create_background_job(user_id: int, job_type: str, params: dict) -> dict:
    import json as _json

    now = utc_now()
    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO background_jobs (
                user_id, job_type, status, params_json, progress_json, created_at, updated_at
            ) VALUES (%s, %s, 'pending', %s, '{}', %s, %s)
            RETURNING id
            """,
            (user_id, job_type, _json.dumps(params, ensure_ascii=False), now, now),
        ).fetchone()
        job_id = int(row["id"])
    job = get_background_job(job_id, user_id=user_id)
    assert job is not None
    return job


def get_background_job(job_id: int, *, user_id: int | None = None) -> dict | None:
    with get_conn() as conn:
        if user_id is None:
            row = conn.execute(
                "SELECT * FROM background_jobs WHERE id = %s",
                (job_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM background_jobs WHERE id = %s AND user_id = %s",
                (job_id, user_id),
            ).fetchone()
    return dict(row) if row else None


def list_background_jobs(user_id: int, *, active_only: bool = False) -> list[dict]:
    query = "SELECT * FROM background_jobs WHERE user_id = %s"
    params: list[object] = [user_id]
    if active_only:
        query += " AND status IN ('pending', 'running')"
    query += " ORDER BY updated_at DESC LIMIT 50"
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def update_background_job(
    job_id: int,
    *,
    status: str | None = None,
    message: str | None = None,
    progress: dict | None = None,
    result: dict | None = None,
    finished_at: bool = False,
) -> None:
    import json as _json

    fields: list[str] = ["updated_at = %s"]
    values: list[object] = [utc_now()]
    if status is not None:
        fields.append("status = %s")
        values.append(status)
    if message is not None:
        fields.append("message = %s")
        values.append(message[:500])
    if progress is not None:
        fields.append("progress_json = %s")
        values.append(_json.dumps(progress, ensure_ascii=False))
    if result is not None:
        fields.append("result_json = %s")
        values.append(_json.dumps(result, ensure_ascii=False))
    if finished_at:
        fields.append("finished_at = %s")
        values.append(utc_now())
    values.append(job_id)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE background_jobs SET {', '.join(fields)} WHERE id = %s",
            values,
        )


def mark_interrupted_background_jobs() -> None:
    now = utc_now()
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE background_jobs
            SET status = 'error',
                message = '服务重启，任务中断',
                updated_at = %s,
                finished_at = %s
            WHERE status IN ('pending', 'running')
            """,
            (now, now),
        )
