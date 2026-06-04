from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
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
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, email, roles),
                FOREIGN KEY(user_id) REFERENCES users(id)
            );

            CREATE INDEX IF NOT EXISTS idx_contacts_user_id ON contacts(user_id);
            CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email);
            """
        )

        row = conn.execute("SELECT COUNT(*) AS count FROM users").fetchone()
        if row["count"] == 0:
            now = utc_now()
            conn.execute(
                "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
                (DEFAULT_ADMIN_USER, hash_password(DEFAULT_ADMIN_PASSWORD), now),
            )


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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


def list_contacts(user_id: int) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, asn, org, name, email, roles, handle, rir, source, notes, created_at, updated_at
            FROM contacts
            WHERE user_id = ?
            ORDER BY created_at DESC, id DESC
            """,
            (user_id,),
        ).fetchall()
    return [dict(row) for row in rows]


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

            roles = ",".join(row.get("roles") or [])
            notes = row.get("notes") or ""
            payload = (
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
            )

            try:
                conn.execute(
                    """
                    INSERT INTO contacts (
                        user_id, asn, org, name, email, roles, handle, rir, source, notes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    payload,
                )
                imported += 1
            except sqlite3.IntegrityError:
                duplicates += 1

    return {"imported": imported, "skipped": skipped, "duplicates": duplicates}


def delete_contact(user_id: int, contact_id: int) -> bool:
    with get_conn() as conn:
        cursor = conn.execute(
            "DELETE FROM contacts WHERE id = ? AND user_id = ?",
            (contact_id, user_id),
        )
        return cursor.rowcount > 0
