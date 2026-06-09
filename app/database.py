from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

import psycopg

from app.db import get_conn
from app.security import hash_password
from arin_lookup import parse_asn

FOLLOW_UP_STATUSES = ("new", "contacted", "replied", "invalid", "interested")
LEAD_REVIEW_STATUSES = ("pending", "approved", "skipped", "imported")

CONTACT_SELECT_SQL = """
    id, asn, org, name, email, roles, handle, rir, source, notes,
    linkedin, x, facebook,
    email_sent, email_sent_at, follow_up_status, created_at, updated_at
"""


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


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
        conn.execute("ALTER TABLE contacts ADD COLUMN email_sent BOOLEAN NOT NULL DEFAULT FALSE")
    if "email_sent_at" not in columns:
        conn.execute("ALTER TABLE contacts ADD COLUMN email_sent_at TIMESTAMPTZ")
    if "follow_up_status" not in columns:
        conn.execute("ALTER TABLE contacts ADD COLUMN follow_up_status TEXT NOT NULL DEFAULT 'new'")
        conn.execute("UPDATE contacts SET follow_up_status = 'contacted' WHERE email_sent = TRUE")
    for social_col in ("linkedin", "x", "facebook"):
        if social_col not in columns:
            conn.execute(f"ALTER TABLE contacts ADD COLUMN {social_col} TEXT NOT NULL DEFAULT ''")

    dedupe_contacts(conn=conn)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_contacts_user_email ON contacts(user_id, email)")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_contacts_user_email_unique ON contacts(user_id, email)"
    )


def _migrate_scheduled_jobs(conn) -> None:
    columns = _table_columns(conn, "scheduled_jobs")
    if "interval_minutes" not in columns:
        conn.execute(
            "ALTER TABLE scheduled_jobs ADD COLUMN interval_minutes INTEGER NOT NULL DEFAULT 1440"
        )
        conn.execute(
            "UPDATE scheduled_jobs SET interval_minutes = interval_hours * 60 WHERE interval_minutes = 1440"
        )
    if "run_mode" not in columns:
        conn.execute(
            "ALTER TABLE scheduled_jobs ADD COLUMN run_mode TEXT NOT NULL DEFAULT 'interval'"
        )
    if "cooldown_minutes" not in columns:
        conn.execute(
            "ALTER TABLE scheduled_jobs ADD COLUMN cooldown_minutes INTEGER NOT NULL DEFAULT 15"
        )
    if "running_at" not in columns:
        conn.execute("ALTER TABLE scheduled_jobs ADD COLUMN running_at TIMESTAMPTZ")
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_scheduled_jobs_due
            ON scheduled_jobs(enabled, next_run_at, running_at)
        """
    )


def _migrate_background_jobs(conn) -> None:
    columns = _table_columns(conn, "background_jobs")
    if "checkpoint_json" not in columns:
        conn.execute(
            """
            ALTER TABLE background_jobs
            ADD COLUMN checkpoint_json TEXT
            """
        )


def _migrate_pi_chat_threads(conn) -> None:
    columns = _table_columns(conn, "pi_chat_threads")
    if "context_summary" not in columns:
        conn.execute(
            "ALTER TABLE pi_chat_threads ADD COLUMN context_summary TEXT NOT NULL DEFAULT ''"
        )
    if "context_summary_through" not in columns:
        conn.execute(
            "ALTER TABLE pi_chat_threads ADD COLUMN context_summary_through INTEGER NOT NULL DEFAULT 0"
        )


def _migrate_user_lead_preferences(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_lead_preferences (
            user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            prefs_json TEXT NOT NULL DEFAULT '{}',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def _migrate_lead_reviews(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lead_reviews (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'pending',
            query TEXT NOT NULL DEFAULT '',
            lead_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            org TEXT NOT NULL DEFAULT '',
            email TEXT NOT NULL DEFAULT '',
            asn INTEGER,
            source TEXT NOT NULL DEFAULT '',
            score INTEGER NOT NULL DEFAULT 0,
            reason TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            reviewed_at TIMESTAMPTZ
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_lead_reviews_user_status ON lead_reviews(user_id, status, updated_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_lead_reviews_user_email ON lead_reviews(user_id, lower(email))"
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
    "user_lead_preferences",
    "lead_reviews",
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
            CREATE TABLE IF NOT EXISTS email_outbox (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
                template_id INTEGER,
                to_email TEXT NOT NULL,
                subject TEXT NOT NULL DEFAULT '',
                body_text TEXT NOT NULL DEFAULT '',
                body_html TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'queued',
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT NOT NULL DEFAULT '',
                scheduled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                sent_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_email_outbox_claim "
            "ON email_outbox (status, scheduled_at)"
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
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_job_runs_job_id ON job_runs(job_id, ran_at DESC)"
        )
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
        _migrate_scheduled_jobs(conn)
        _migrate_background_jobs(conn)
        _migrate_pi_chat_threads(conn)
        _migrate_user_lead_preferences(conn)
        _migrate_lead_reviews(conn)

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
            "OR lower(notes) LIKE %s OR lower(roles) LIKE %s "
            "OR lower(linkedin) LIKE %s OR lower(x) LIKE %s OR lower(facebook) LIKE %s)"
        )
        params.extend([like, like, like, like, like, like, like, like])
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
        SELECT {CONTACT_SELECT_SQL}
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
            f"""
            SELECT {CONTACT_SELECT_SQL}
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
    """Normalize import payloads so org/name/social URLs are preserved across all import paths."""
    from app.social_contacts import extract_social_fields_from_row

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
    normalized.update(extract_social_fields_from_row(row))
    asn_raw = row.get("asn")
    if asn_raw is not None and str(asn_raw).strip():
        parsed_asn = parse_asn(str(asn_raw))
        normalized["asn"] = parsed_asn
    elif "asn" in normalized:
        normalized.pop("asn", None)
    return normalized


def import_contacts(user_id: int, rows: list[dict]) -> dict:
    from app.import_filters import email_allowed_for_import
    from app.social_contacts import merge_social_fields

    imported = 0
    skipped = 0
    duplicates = 0
    filtered = 0
    imported_rows: list[dict] = []
    reviewed_emails: set[str] = set()
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
                """
                SELECT id, org, name, roles, notes, linkedin, x, facebook
                FROM contacts WHERE user_id = %s AND lower(email) = %s
                """,
                (user_id, email),
            ).fetchone()
            if existing:
                duplicates += 1
                reviewed_emails.add(email)
                merged_notes = _merge_notes(existing["notes"], row.get("notes") or "")
                merged_roles = _merge_roles(existing["roles"], row.get("roles") or [])
                existing_org = (existing["org"] or "").strip()
                existing_name = (existing["name"] or "").strip()
                merged_org = existing_org or (row.get("org") or "").strip()
                merged_name = existing_name or (row.get("name") or "").strip()
                social = merge_social_fields(existing, row)
                conn.execute(
                    """
                    UPDATE contacts
                    SET org = %s,
                        name = %s,
                        roles = %s,
                        notes = %s,
                        linkedin = %s,
                        x = %s,
                        facebook = %s,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (
                        merged_org,
                        merged_name,
                        merged_roles,
                        merged_notes,
                        social["linkedin"],
                        social["x"],
                        social["facebook"],
                        now,
                        existing["id"],
                    ),
                )
                continue

            roles = (
                ",".join(row.get("roles") or [])
                if isinstance(row.get("roles"), list)
                else (row.get("roles") or "")
            )
            notes = row.get("notes") or ""
            social = merge_social_fields({}, row)
            conn.execute(
                """
                INSERT INTO contacts (
                    user_id, asn, org, name, email, roles, handle, rir, source, notes,
                    linkedin, x, facebook,
                    email_sent, email_sent_at, follow_up_status, created_at, updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, NULL, 'new', %s, %s)
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
                    social["linkedin"],
                    social["x"],
                    social["facebook"],
                    now,
                    now,
                ),
            )
            imported += 1
            reviewed_emails.add(email)
            imported_rows.append(
                {
                    "email": email,
                    "org": row.get("org") or "",
                    "name": row.get("name") or "",
                    "roles": row.get("roles") or roles,
                    "source": row.get("source") or "arin",
                    "notes": notes,
                }
            )

        if reviewed_emails:
            conn.execute(
                """
                UPDATE lead_reviews
                SET status = 'imported', reviewed_at = %s, updated_at = %s
                WHERE user_id = %s
                  AND status = 'pending'
                  AND lower(email) = ANY(%s)
                """,
                (now, now, user_id, sorted(reviewed_emails)),
            )

    if imported_rows:
        try:
            from app.lead_preferences import record_import_feedback

            record_import_feedback(user_id, imported_rows)
        except Exception:
            pass

    return {
        "imported": imported,
        "skipped": skipped,
        "duplicates": duplicates,
        "filtered": filtered,
    }


def _lead_review_payload(lead: dict, *, query: str = "") -> dict:
    email = (lead.get("email") or "").strip().lower()
    asn_raw = lead.get("asn")
    asn: int | None = None
    if asn_raw is not None and str(asn_raw).strip():
        try:
            asn = parse_asn(str(asn_raw))
        except ValueError:
            asn = None
    return {
        "lead_json": lead,
        "query": query.strip(),
        "org": (lead.get("org") or lead.get("network_name") or "").strip(),
        "email": email,
        "asn": asn,
        "source": (lead.get("source") or "ai-lead").strip(),
        "score": int(lead.get("lead_score") or lead.get("score") or 0),
        "reason": (lead.get("lead_reason") or lead.get("source_detail") or "").strip(),
    }


def _lead_review_from_row(row: dict | None) -> dict:
    if not row:
        return {}
    item = dict(row)
    lead = item.get("lead_json") or {}
    if isinstance(lead, str):
        try:
            lead = json.loads(lead)
        except json.JSONDecodeError:
            lead = {}
    item["lead"] = lead
    item.pop("lead_json", None)
    item["created_at"] = _iso(item.get("created_at"))
    item["updated_at"] = _iso(item.get("updated_at"))
    item["reviewed_at"] = _iso(item.get("reviewed_at"))
    return item


def save_lead_reviews(
    user_id: int,
    leads: list[dict],
    *,
    query: str = "",
    status: str = "pending",
) -> dict:
    status = status if status in LEAD_REVIEW_STATUSES else "pending"
    inserted = 0
    updated = 0
    skipped = 0
    now = utc_now()
    with get_conn() as conn:
        for lead in leads:
            payload = _lead_review_payload(lead, query=query)
            if not payload["email"]:
                skipped += 1
                continue
            existing = conn.execute(
                """
                SELECT id
                FROM lead_reviews
                WHERE user_id = %s
                  AND lower(email) = lower(%s)
                  AND status = 'pending'
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """,
                (user_id, payload["email"]),
            ).fetchone()
            if existing:
                conn.execute(
                    """
                    UPDATE lead_reviews
                    SET query = %s,
                        lead_json = %s::jsonb,
                        org = %s,
                        asn = %s,
                        source = %s,
                        score = %s,
                        reason = %s,
                        updated_at = %s
                    WHERE id = %s AND user_id = %s
                    """,
                    (
                        payload["query"],
                        json.dumps(payload["lead_json"], ensure_ascii=False),
                        payload["org"],
                        payload["asn"],
                        payload["source"],
                        payload["score"],
                        payload["reason"],
                        now,
                        existing["id"],
                        user_id,
                    ),
                )
                updated += 1
                continue
            conn.execute(
                """
                INSERT INTO lead_reviews (
                    user_id, status, query, lead_json, org, email, asn, source, score, reason,
                    created_at, updated_at, reviewed_at
                )
                VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    status,
                    payload["query"],
                    json.dumps(payload["lead_json"], ensure_ascii=False),
                    payload["org"],
                    payload["email"],
                    payload["asn"],
                    payload["source"],
                    payload["score"],
                    payload["reason"],
                    now,
                    now,
                    now if status != "pending" else None,
                ),
            )
            inserted += 1
    return {"inserted": inserted, "updated": updated, "skipped": skipped}


def list_lead_reviews(user_id: int, *, status: str = "pending", limit: int = 100) -> list[dict]:
    if status not in LEAD_REVIEW_STATUSES and status != "all":
        status = "pending"
    params: list[object] = [user_id]
    where = "user_id = %s"
    if status != "all":
        where += " AND status = %s"
        params.append(status)
    params.append(min(max(int(limit), 1), 200))
    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT id, status, query, lead_json, org, email, asn, source, score, reason,
                   created_at, updated_at, reviewed_at
            FROM lead_reviews
            WHERE {where}
            ORDER BY
              CASE status WHEN 'pending' THEN 0 WHEN 'approved' THEN 1 WHEN 'imported' THEN 2 ELSE 3 END,
              score DESC, updated_at DESC, id DESC
            LIMIT %s
            """,
            params,
        ).fetchall()
    return [_lead_review_from_row(row) for row in rows]


def update_lead_review_status(user_id: int, review_id: int, status: str) -> dict | None:
    if status not in LEAD_REVIEW_STATUSES:
        return None
    now = utc_now()
    with get_conn() as conn:
        row = conn.execute(
            """
            UPDATE lead_reviews
            SET status = %s, reviewed_at = %s, updated_at = %s
            WHERE id = %s AND user_id = %s
            RETURNING id, status, query, lead_json, org, email, asn, source, score, reason,
                      created_at, updated_at, reviewed_at
            """,
            (status, now if status != "pending" else None, now, review_id, user_id),
        ).fetchone()
    return _lead_review_from_row(row) if row else None


def import_lead_reviews(user_id: int, review_ids: list[int]) -> dict:
    ids = sorted({int(value) for value in review_ids if int(value) > 0})
    if not ids:
        return {"imported": 0, "skipped": 0, "duplicates": 0, "filtered": 0, "updated": 0}
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, lead_json, score, reason, source
            FROM lead_reviews
            WHERE user_id = %s AND id = ANY(%s)
            """,
            (user_id, ids),
        ).fetchall()
    payload: list[dict] = []
    row_ids: list[int] = []
    for row in rows:
        lead = row["lead_json"] or {}
        if isinstance(lead, str):
            try:
                lead = json.loads(lead)
            except json.JSONDecodeError:
                lead = {}
        if not lead.get("email"):
            continue
        source = lead.get("source") or row.get("source") or "ai-lead"
        detail = lead.get("source_detail") or ""
        notes = f"AI评分 {row.get('score') or lead.get('lead_score') or 0} · {row.get('reason') or lead.get('lead_reason') or ''}"
        if detail:
            notes += f" · {detail}"
        payload.append({**lead, "source": source, "notes": notes.strip(" ·")})
        row_ids.append(int(row["id"]))

    result = (
        import_contacts(user_id, payload)
        if payload
        else {
            "imported": 0,
            "skipped": len(ids),
            "duplicates": 0,
            "filtered": 0,
        }
    )
    if row_ids:
        now = utc_now()
        with get_conn() as conn:
            conn.execute(
                """
                UPDATE lead_reviews
                SET status = 'imported', reviewed_at = %s, updated_at = %s
                WHERE user_id = %s AND id = ANY(%s)
                """,
                (now, now, user_id, row_ids),
            )
    result["updated"] = len(row_ids)
    return result


def get_workbench_summary(user_id: int) -> dict:
    now_dt = datetime.now(UTC).replace(microsecond=0)
    today = now_dt.date().isoformat()
    followup_before = (now_dt - timedelta(days=3)).isoformat()
    with get_conn() as conn:
        pending_reviews = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM lead_reviews
            WHERE user_id = %s AND status = 'pending'
            """,
            (user_id,),
        ).fetchone()["count"]
        imported_today = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM contacts
            WHERE user_id = %s AND created_at::date = %s::date
            """,
            (user_id, today),
        ).fetchone()["count"]
        unsent_new = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM contacts
            WHERE user_id = %s AND email_sent = FALSE AND follow_up_status = 'new'
            """,
            (user_id,),
        ).fetchone()["count"]
        due_followups = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM contacts
            WHERE user_id = %s
              AND follow_up_status = 'contacted'
              AND email_sent = TRUE
              AND COALESCE(email_sent_at, updated_at, created_at) <= %s
            """,
            (user_id, followup_before),
        ).fetchone()["count"]
        warm_contacts = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM contacts
            WHERE user_id = %s AND follow_up_status IN ('replied', 'interested')
            """,
            (user_id,),
        ).fetchone()["count"]
        followup_rows = conn.execute(
            f"""
            SELECT {CONTACT_SELECT_SQL}
            FROM contacts
            WHERE user_id = %s
              AND follow_up_status = 'contacted'
              AND email_sent = TRUE
              AND COALESCE(email_sent_at, updated_at, created_at) <= %s
            ORDER BY COALESCE(email_sent_at, updated_at, created_at) ASC, id ASC
            LIMIT 8
            """,
            (user_id, followup_before),
        ).fetchall()

    return {
        "today": today,
        "pending_reviews": int(pending_reviews),
        "imported_today": int(imported_today),
        "unsent_new": int(unsent_new),
        "due_followups": int(due_followups),
        "warm_contacts": int(warm_contacts),
        "review_items": list_lead_reviews(user_id, status="pending", limit=8),
        "followup_items": [_contact_from_row(row) for row in followup_rows],
        "new_items": list_contacts(
            user_id,
            status="unsent",
            follow_up_status="new",
            limit=8,
        ),
    }


def list_contact_organizations(user_id: int, *, limit: int = 80) -> list[dict]:
    contacts = list_contacts(user_id, limit=100000)
    groups: dict[str, dict] = {}
    for contact in contacts:
        org = (contact.get("org") or "").strip()
        email = contact.get("email") or ""
        domain = email.split("@", 1)[1] if "@" in email else ""
        key = org.lower() or f"domain:{domain.lower()}" or f"contact:{contact.get('id')}"
        group = groups.setdefault(
            key,
            {
                "org": org or domain or "—",
                "domain": domain,
                "asn": contact.get("asn"),
                "contacts": [],
                "roles": set(),
                "sent": 0,
                "warm": 0,
                "latest_at": contact.get("updated_at") or contact.get("created_at") or "",
            },
        )
        if not group.get("asn") and contact.get("asn"):
            group["asn"] = contact.get("asn")
        if contact.get("email_sent"):
            group["sent"] += 1
        if contact.get("follow_up_status") in {"replied", "interested"}:
            group["warm"] += 1
        for role in str(contact.get("roles") or "").split(","):
            role = role.strip()
            if role:
                group["roles"].add(role)
        group["contacts"].append(contact)
        latest = contact.get("updated_at") or contact.get("created_at") or ""
        if latest > (group.get("latest_at") or ""):
            group["latest_at"] = latest

    items = []
    for group in groups.values():
        group["roles"] = sorted(group["roles"])
        group["count"] = len(group["contacts"])
        group["contacts"] = group["contacts"][:8]
        items.append(group)
    items.sort(
        key=lambda item: (item["warm"], item["count"], item.get("latest_at") or ""), reverse=True
    )
    return items[: min(max(int(limit), 1), 200)]


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


def update_contact_follow_up_status(user_id: int, contact_id: int, follow_up_status: str) -> bool:
    if follow_up_status not in FOLLOW_UP_STATUSES:
        return False
    now = utc_now()
    with get_conn() as conn:
        row = conn.execute(
            f"""
            SELECT {CONTACT_SELECT_SQL}
            FROM contacts WHERE id = %s AND user_id = %s
            """,
            (contact_id, user_id),
        ).fetchone()
        if not row:
            return False
        cursor = conn.execute(
            """
            UPDATE contacts
            SET follow_up_status = %s, updated_at = %s
            WHERE id = %s AND user_id = %s
            """,
            (follow_up_status, now, contact_id, user_id),
        )
        updated = cursor.rowcount > 0

    if updated:
        try:
            from app.lead_preferences import record_status_feedback

            record_status_feedback(user_id, _contact_from_row(row), follow_up_status)
        except Exception:
            pass
    return updated


def update_contact(
    user_id: int,
    contact_id: int,
    *,
    org: str | None = None,
    name: str | None = None,
    notes: str | None = None,
    roles: str | None = None,
    linkedin: str | None = None,
    x: str | None = None,
    facebook: str | None = None,
) -> dict | None:
    from app.social_contacts import normalize_social_url

    updates: dict[str, object] = {}
    if org is not None:
        updates["org"] = org.strip()
    if name is not None:
        updates["name"] = name.strip()
    if notes is not None:
        updates["notes"] = notes.strip()
    if roles is not None:
        updates["roles"] = roles.strip()
    if linkedin is not None:
        updates["linkedin"] = normalize_social_url("linkedin", linkedin)
    if x is not None:
        updates["x"] = normalize_social_url("x", x)
    if facebook is not None:
        updates["facebook"] = normalize_social_url("facebook", facebook)
    if not updates:
        with get_conn() as conn:
            row = conn.execute(
                f"""
                SELECT {CONTACT_SELECT_SQL}
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
            f"""
            SELECT {CONTACT_SELECT_SQL}
            FROM contacts WHERE id = %s AND user_id = %s
            """,
            (contact_id, user_id),
        ).fetchone()
    return _contact_from_row(row) if row else None


def update_contact_social_fields(
    user_id: int,
    contact_id: int,
    *,
    linkedin: str = "",
    x: str = "",
    facebook: str = "",
) -> bool:
    from app.social_contacts import merge_social_fields

    contact = get_contact(user_id, contact_id)
    if not contact:
        return False
    merged = merge_social_fields(contact, {"linkedin": linkedin, "x": x, "facebook": facebook})
    if (
        merged["linkedin"] == (contact.get("linkedin") or "")
        and merged["x"] == (contact.get("x") or "")
        and merged["facebook"] == (contact.get("facebook") or "")
    ):
        return False
    now = utc_now()
    with get_conn() as conn:
        cursor = conn.execute(
            """
            UPDATE contacts
            SET linkedin = %s, x = %s, facebook = %s, updated_at = %s
            WHERE id = %s AND user_id = %s
            """,
            (merged["linkedin"], merged["x"], merged["facebook"], now, contact_id, user_id),
        )
        return cursor.rowcount > 0


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
        row = conn.execute(
            f"""
            SELECT {CONTACT_SELECT_SQL}
            FROM contacts WHERE id = %s AND user_id = %s
            """,
            (contact_id, user_id),
        ).fetchone()
        if not row:
            return False
        contact = _contact_from_row(row)
        conn.execute(
            "DELETE FROM contact_notes WHERE contact_id = %s AND user_id = %s",
            (contact_id, user_id),
        )
        cursor = conn.execute(
            "DELETE FROM contacts WHERE id = %s AND user_id = %s",
            (contact_id, user_id),
        )
        deleted = cursor.rowcount > 0

    if deleted:
        try:
            from app.lead_preferences import record_delete_feedback

            record_delete_feedback(user_id, contact)
        except Exception:
            pass
    return deleted


def dedupe_contacts(*, user_id: int | None = None, conn: Any | None = None) -> dict:
    removed = 0
    removed_rows: list[dict] = []

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
                removed_rows.append(
                    {
                        "email": row["email"],
                        "org": row["org"],
                        "name": row["name"],
                        "roles": row["roles"],
                        "notes": row["notes"],
                    }
                )
                continue
            seen.add(key)
        return {"removed": removed, "remaining": len(seen), "removed_rows": removed_rows}

    if conn is not None:
        return run(conn)

    with get_conn() as connection:
        return run(connection)


def _scheduled_job_from_row(row: dict | None) -> dict | None:
    if not row:
        return None
    item = dict(row)
    item["auto_import"] = bool(item.get("auto_import"))
    item["enabled"] = bool(item.get("enabled"))
    if not item.get("interval_minutes"):
        item["interval_minutes"] = int(item.get("interval_hours") or 24) * 60
    if not item.get("run_mode"):
        item["run_mode"] = "interval"
    if not item.get("cooldown_minutes"):
        item["cooldown_minutes"] = 15
    return item


def list_scheduled_jobs(user_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, name, query, interval_hours, interval_minutes, run_mode, cooldown_minutes,
                   min_score, auto_import, enabled, running_at,
                   last_run_at, last_run_status, last_run_message, next_run_at,
                   created_at, updated_at
            FROM scheduled_jobs
            WHERE user_id = %s
            ORDER BY created_at DESC, id DESC
            """,
            (user_id,),
        ).fetchall()
    return [job for row in rows if (job := _scheduled_job_from_row(dict(row)))]


def get_scheduled_job(user_id: int, job_id: int) -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM scheduled_jobs WHERE id = %s AND user_id = %s",
            (job_id, user_id),
        ).fetchone()
    return _scheduled_job_from_row(dict(row) if row else None)


def _resolve_interval_minutes(*, interval_minutes: int | None, interval_hours: int | None) -> int:
    if interval_minutes is not None:
        return max(15, min(int(interval_minutes), 10080))
    hours = interval_hours if interval_hours is not None else 24
    return max(15, min(int(hours) * 60, 10080))


def create_scheduled_job(
    user_id: int,
    *,
    name: str,
    query: str,
    interval_hours: int | None = None,
    interval_minutes: int | None = None,
    run_mode: str = "interval",
    cooldown_minutes: int = 15,
    min_score: int,
    auto_import: bool,
    enabled: bool = True,
) -> dict:
    minutes = _resolve_interval_minutes(
        interval_minutes=interval_minutes,
        interval_hours=interval_hours,
    )
    mode = "continuous" if str(run_mode).strip().lower() == "continuous" else "interval"
    cooldown = max(5, min(int(cooldown_minutes or 15), 1440))
    interval_hours_value = max(1, (minutes + 59) // 60)
    now = utc_now()
    with get_conn() as conn:
        row = conn.execute(
            """
            INSERT INTO scheduled_jobs (
                user_id, name, query, interval_hours, interval_minutes, run_mode, cooldown_minutes,
                min_score, auto_import, enabled, next_run_at, created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                user_id,
                name.strip(),
                query.strip(),
                interval_hours_value,
                minutes,
                mode,
                cooldown,
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
    allowed = {
        "name",
        "query",
        "interval_hours",
        "interval_minutes",
        "run_mode",
        "cooldown_minutes",
        "min_score",
        "auto_import",
        "enabled",
    }
    updates = {key: value for key, value in fields.items() if key in allowed and value is not None}
    if not updates:
        return get_scheduled_job(user_id, job_id)

    if "auto_import" in updates:
        updates["auto_import"] = bool(updates["auto_import"])
    if "enabled" in updates:
        updates["enabled"] = bool(updates["enabled"])
    if "run_mode" in updates:
        updates["run_mode"] = (
            "continuous" if str(updates["run_mode"]).strip().lower() == "continuous" else "interval"
        )
    if "cooldown_minutes" in updates:
        updates["cooldown_minutes"] = max(5, min(int(updates["cooldown_minutes"]), 1440))
    if "interval_minutes" in updates or "interval_hours" in updates:
        minutes = _resolve_interval_minutes(
            interval_minutes=updates.pop("interval_minutes", None),
            interval_hours=updates.pop("interval_hours", None),
        )
        updates["interval_minutes"] = minutes
        updates["interval_hours"] = max(1, (minutes + 59) // 60)

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


def list_due_scheduled_jobs(*, stale_running_minutes: int = 180) -> list[dict]:
    now = utc_now()
    stale_before = (
        datetime.now(UTC).replace(microsecond=0) - timedelta(minutes=stale_running_minutes)
    ).isoformat()
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM scheduled_jobs
            WHERE enabled = TRUE
              AND (next_run_at IS NULL OR next_run_at <= %s)
              AND (running_at IS NULL OR running_at <= %s)
            ORDER BY next_run_at ASC NULLS FIRST, id ASC
            """,
            (now, stale_before),
        ).fetchall()
    jobs = []
    for row in rows:
        job = _scheduled_job_from_row(dict(row))
        if job:
            jobs.append(job)
    return jobs


def claim_scheduled_job(job_id: int) -> bool:
    now = utc_now()
    stale_before = (datetime.now(UTC).replace(microsecond=0) - timedelta(hours=3)).isoformat()
    with get_conn() as conn:
        cursor = conn.execute(
            """
            UPDATE scheduled_jobs
            SET running_at = %s, updated_at = %s
            WHERE id = %s
              AND enabled = TRUE
              AND (running_at IS NULL OR running_at <= %s)
            """,
            (now, now, job_id, stale_before),
        )
        return cursor.rowcount > 0


def mark_job_run(
    job_id: int,
    *,
    status: str,
    message: str,
    interval_minutes: int,
    run_mode: str = "interval",
    cooldown_minutes: int = 15,
) -> None:
    now_dt = datetime.now(UTC).replace(microsecond=0)
    mode = "continuous" if str(run_mode).strip().lower() == "continuous" else "interval"
    if mode == "continuous":
        delay_minutes = max(5, min(int(cooldown_minutes or 15), 1440))
    else:
        delay_minutes = max(15, min(int(interval_minutes or 1440), 10080))
    next_run = (now_dt + timedelta(minutes=delay_minutes)).isoformat()
    now = now_dt.isoformat()
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE scheduled_jobs
            SET last_run_at = %s,
                last_run_status = %s,
                last_run_message = %s,
                next_run_at = %s,
                running_at = NULL,
                updated_at = %s
            WHERE id = %s
            """,
            (now, status, message[:500], next_run, now, job_id),
        )


def clear_job_running(job_id: int) -> None:
    now = utc_now()
    with get_conn() as conn:
        conn.execute(
            "UPDATE scheduled_jobs SET running_at = NULL, updated_at = %s WHERE id = %s",
            (now, job_id),
        )


def count_active_scheduled_jobs() -> dict[str, int]:
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) AS count FROM scheduled_jobs").fetchone()["count"]
        enabled = conn.execute(
            "SELECT COUNT(*) AS count FROM scheduled_jobs WHERE enabled = TRUE"
        ).fetchone()["count"]
        running = conn.execute(
            "SELECT COUNT(*) AS count FROM scheduled_jobs WHERE running_at IS NOT NULL"
        ).fetchone()["count"]
    return {"total": int(total), "enabled": int(enabled), "running": int(running)}


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


def create_email_template(user_id: int, *, name: str, subject: str = "", body: str = "") -> dict:
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


def enqueue_email(
    user_id, contact_id, template_id, to_email, subject, body_text, body_html, *, conn=None
):
    def run(c):
        return c.execute(
            """
            INSERT INTO email_outbox
              (user_id, contact_id, template_id, to_email, subject, body_text, body_html)
            VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id
            """,
            (user_id, contact_id, template_id, to_email, subject, body_text, body_html),
        ).fetchone()["id"]

    if conn is not None:
        return run(conn)
    with get_conn() as c:
        return run(c)


def email_queued_addresses(user_id, *, conn=None) -> set[str]:
    def run(c):
        rows = c.execute(
            "SELECT lower(to_email) AS e FROM email_outbox "
            "WHERE user_id=%s AND status IN ('queued','sending')",
            (user_id,),
        ).fetchall()
        return {r["e"] for r in rows}

    if conn is not None:
        return run(conn)
    with get_conn() as c:
        return run(c)


def count_sent_emails_today(user_id=None, *, conn=None) -> int:
    # user_id=None → count across all users (global rate limit for the single sender loop)
    where = "WHERE status = 'sent' AND sent_at::date = NOW()::date"
    params: tuple = ()
    if user_id is not None:
        where = "WHERE user_id=%s AND status = 'sent' AND sent_at::date = NOW()::date"
        params = (user_id,)

    def run(c):
        row = c.execute(f"SELECT COUNT(*) AS n FROM email_outbox {where}", params).fetchone()
        return int(row["n"]) if row else 0

    if conn is not None:
        return run(conn)
    with get_conn() as c:
        return run(c)


def last_sent_email_at(user_id=None, *, conn=None):
    # user_id=None → most recent send across all users (global interval gate)
    where = "WHERE status='sent'"
    params: tuple = ()
    if user_id is not None:
        where = "WHERE user_id=%s AND status='sent'"
        params = (user_id,)

    def run(c):
        row = c.execute(f"SELECT MAX(sent_at) AS t FROM email_outbox {where}", params).fetchone()
        return row["t"] if row else None

    if conn is not None:
        return run(conn)
    with get_conn() as c:
        return run(c)


def requeue_stale_sending_emails(*, conn=None) -> int:
    """Reset orphaned 'sending' rows back to 'queued'.

    The sender is a single in-process loop, so on startup any row left in
    'sending' is an orphan from a crash/restart mid-send. Requeue them so they
    are retried instead of being stuck forever.
    """

    def run(c):
        cur = c.execute(
            "UPDATE email_outbox SET status='queued', updated_at=NOW() WHERE status='sending'"
        )
        return cur.rowcount or 0

    if conn is not None:
        return run(conn)
    with get_conn() as c:
        return run(c)


def claim_next_queued_email(user_id=None, *, conn=None):
    where = (
        "WHERE user_id=%s AND status='queued'" if user_id is not None else "WHERE status='queued'"
    )
    params = (user_id,) if user_id is not None else ()
    sql = f"""
        UPDATE email_outbox SET status = 'sending', updated_at=NOW()
        WHERE id = (
            SELECT id FROM email_outbox {where}
            ORDER BY scheduled_at ASC FOR UPDATE SKIP LOCKED LIMIT 1
        )
        RETURNING id, user_id, contact_id, to_email, subject, body_text, body_html, attempts
    """

    def run(c):
        return c.execute(sql, params).fetchone()

    if conn is not None:
        return run(conn)
    with get_conn() as c:
        return run(c)


def mark_email_sent(email_id, *, conn=None):
    def run(c):
        c.execute(
            "UPDATE email_outbox SET status='sent', sent_at=NOW(), updated_at=NOW() WHERE id=%s",
            (email_id,),
        )

    if conn is not None:
        return run(conn)
    with get_conn() as c:
        return run(c)


def mark_email_failed(email_id, error, requeue, *, conn=None):
    status = "queued" if requeue else "failed"

    def run(c):
        c.execute(
            "UPDATE email_outbox SET status=%s, attempts=attempts+1, last_error=%s, "
            "updated_at=NOW() WHERE id=%s",
            (status, str(error)[:500], email_id),
        )

    if conn is not None:
        return run(conn)
    with get_conn() as c:
        return run(c)


def list_outbox(user_id, status=None, limit=200):
    where = "WHERE user_id=%s" + (" AND status=%s" if status else "")
    params = (user_id, status) if status else (user_id,)
    with get_conn() as c:
        rows = c.execute(
            f"SELECT id, contact_id, to_email, subject, status, attempts, last_error, "
            f"scheduled_at, sent_at FROM email_outbox {where} "
            f"ORDER BY scheduled_at DESC LIMIT {int(limit)}",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def update_outbox_status(user_id, email_id, status):
    with get_conn() as c:
        c.execute(
            "UPDATE email_outbox SET status=%s, updated_at=NOW() WHERE id=%s AND user_id=%s",
            (status, email_id, user_id),
        )


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
        {"date": day, "count": count} for day, count in sorted(recent.items(), reverse=True)[:14]
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
        "linkedin",
        "x",
        "facebook",
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
            contact.get("linkedin") or "",
            contact.get("x") or "",
            contact.get("facebook") or "",
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
    checkpoint: dict | None = None,
    clear_checkpoint: bool = False,
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
    if clear_checkpoint:
        fields.append("checkpoint_json = NULL")
    elif checkpoint is not None:
        fields.append("checkpoint_json = %s")
        values.append(_json.dumps(checkpoint, ensure_ascii=False))
    if finished_at:
        fields.append("finished_at = %s")
        values.append(utc_now())
    values.append(job_id)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE background_jobs SET {', '.join(fields)} WHERE id = %s",
            values,
        )


def list_resumable_background_jobs() -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT * FROM background_jobs
            WHERE status IN ('pending', 'running')
            ORDER BY created_at ASC
            """,
        ).fetchall()
    return [dict(row) for row in rows]


def has_active_pi_agent_job(user_id: int, thread_id: str) -> bool:
    if not thread_id:
        return False
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT 1 FROM background_jobs
            WHERE user_id = %s
              AND job_type = 'pi_agent'
              AND status IN ('pending', 'running')
              AND params_json::jsonb->>'thread_id' = %s
            LIMIT 1
            """,
            (user_id, thread_id),
        ).fetchone()
    return row is not None


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
