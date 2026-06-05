from __future__ import annotations

import secrets
from typing import Any

from app.database import get_conn, utc_now

SECRET_KEYS = {
    "llm_api_key",
    "tavily_api_key",
    "serpapi_key",
    "brave_search_key",
    "zhipu_api_key",
    "session_secret",
    "default_admin_password",
    "agent_api_token",
}

DEFAULTS: dict[str, str] = {
    "default_admin_user": "admin",
    "default_admin_password": "admin123",
    "session_secret": "",
    "session_https_only": "0",
    "llm_api_key": "",
    "llm_base_url": "https://api.openai.com/v1",
    "llm_model": "gpt-4o-mini",
    "tavily_api_key": "",
    "serpapi_key": "",
    "brave_search_key": "",
    "zhipu_api_key": "",
    "zhipu_search_engine": "search_pro",
    "scheduler_enabled": "1",
    "scheduler_poll_seconds": "60",
    "import_blocklist": "",
    "import_allowlist": "",
    "agent_api_token": "",
}


def init_settings(conn) -> None:
    now = utc_now()
    for key, value in DEFAULTS.items():
        conn.execute(
            """
            INSERT OR IGNORE INTO app_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            """,
            (key, value, now),
        )

    row = conn.execute("SELECT value FROM app_settings WHERE key = 'session_secret'").fetchone()
    if row and not (row["value"] or "").strip():
        conn.execute(
            "UPDATE app_settings SET value = ?, updated_at = ? WHERE key = 'session_secret'",
            (secrets.token_hex(32), now),
        )

    row = conn.execute("SELECT value FROM app_settings WHERE key = 'agent_api_token'").fetchone()
    if row and not (row["value"] or "").strip():
        conn.execute(
            "UPDATE app_settings SET value = ?, updated_at = ? WHERE key = 'agent_api_token'",
            (secrets.token_urlsafe(32), now),
        )

    _migrate_bing_to_brave(conn)


def _migrate_bing_to_brave(conn) -> None:
    """One-time: copy legacy bing_search_key into brave_search_key."""
    bing = conn.execute(
        "SELECT value FROM app_settings WHERE key = 'bing_search_key'"
    ).fetchone()
    if not bing or not (bing["value"] or "").strip():
        return
    brave = conn.execute(
        "SELECT value FROM app_settings WHERE key = 'brave_search_key'"
    ).fetchone()
    if brave and (brave["value"] or "").strip():
        return
    now = utc_now()
    conn.execute(
        """
        INSERT INTO app_settings (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        ("brave_search_key", bing["value"].strip(), now),
    )


def get_setting(key: str, default: str = "") -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
    if not row:
        return DEFAULTS.get(key, default)
    value = row["value"]
    return value if value is not None else DEFAULTS.get(key, default)


def get_agent_api_token() -> str:
    import os

    env = os.getenv("AGENT_API_TOKEN", "").strip()
    if env:
        return env
    return get_setting("agent_api_token", "").strip()


def regenerate_agent_api_token() -> str:
    token = secrets.token_urlsafe(32)
    now = utc_now()
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO app_settings (key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """,
            ("agent_api_token", token, now),
        )
    return token


def get_settings() -> dict[str, str]:
    with get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
    values = dict(DEFAULTS)
    for row in rows:
        values[row["key"]] = row["value"]
    return values


def get_public_settings() -> dict[str, Any]:
    values = get_settings()
    return {
        "default_username": values.get("default_admin_user", "admin"),
        "default_password_hint": values.get("default_admin_password", "admin123"),
        "llm_configured": bool(values.get("llm_api_key", "").strip()),
        "agent_chat_enabled": bool(values.get("llm_api_key", "").strip()),
        "llm_model": values.get("llm_model", DEFAULTS["llm_model"]),
        "llm_base_url": values.get("llm_base_url", DEFAULTS["llm_base_url"]),
        "scheduler_enabled": values.get("scheduler_enabled", "1") != "0",
        "scheduler_poll_seconds": int(values.get("scheduler_poll_seconds", "60") or 60),
        "search_keys": {
            "zhipu": bool(
                get_setting("zhipu_api_key", "").strip()
                or (
                    "bigmodel.cn" in get_setting("llm_base_url", "").lower()
                    and get_setting("llm_api_key", "").strip()
                )
            ),
            "tavily": bool(values.get("tavily_api_key", "").strip()),
            "serpapi": bool(values.get("serpapi_key", "").strip()),
            "brave": bool(values.get("brave_search_key", "").strip()),
            "duckduckgo": True,
        },
    }


def get_settings_for_edit() -> dict[str, Any]:
    values = get_settings()
    payload: dict[str, Any] = {}
    for key, value in values.items():
        if key in SECRET_KEYS:
            payload[key] = mask_secret(value)
            payload[f"{key}_configured"] = bool(value.strip())
        else:
            payload[key] = value
    return payload


def mask_secret(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if len(value) <= 8:
        return "********"
    return f"{value[:4]}...{value[-4:]}"


def update_settings(updates: dict[str, str | None]) -> dict[str, Any]:
    allowed = set(DEFAULTS.keys())
    now = utc_now()
    with get_conn() as conn:
        for key, value in updates.items():
            if key not in allowed:
                continue
            if value is None:
                continue
            value = str(value)
            if key in SECRET_KEYS and not value.strip():
                continue
            if key in SECRET_KEYS and "..." in value:
                continue
            conn.execute(
                """
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
                """,
                (key, value.strip(), now),
            )
    return get_settings_for_edit()
