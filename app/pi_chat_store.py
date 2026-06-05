from __future__ import annotations

import json
import secrets
from typing import Any

from psycopg.types.json import Json

from app.database import get_conn, utc_now

MAX_THREADS_PER_USER = 50
MAX_STORED_MESSAGES = 200
MAX_LLM_HISTORY_MESSAGES = 80


def new_thread_id() -> str:
    return f"t_{secrets.token_hex(12)}"


def _load_history(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw or "[]")
        except json.JSONDecodeError:
            return []
    return _normalize_history(raw)


def _normalize_history(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        if role in ("user", "assistant"):
            content = str(item.get("content") or "").strip()
            if content:
                cleaned.append({"role": role, "content": content})
        elif role == "tool" and item.get("name"):
            entry: dict[str, Any] = {
                "role": "tool",
                "name": str(item.get("name")),
                "summary": str(item.get("summary") or ""),
            }
            preview = item.get("preview")
            if isinstance(preview, list) and preview:
                entry["preview"] = preview[:30]
            cleaned.append(entry)
    return cleaned[-MAX_STORED_MESSAGES:]


def _iso(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.isoformat()  # type: ignore[union-attr]


def list_pi_threads(user_id: int) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, title, history_json, created_at, updated_at
            FROM pi_chat_threads
            WHERE user_id = %s
            ORDER BY updated_at DESC
            LIMIT %s
            """,
            (user_id, MAX_THREADS_PER_USER),
        ).fetchall()
    threads: list[dict[str, Any]] = []
    for row in rows:
        history = _load_history(row["history_json"])
        threads.append(
            {
                "id": row["id"],
                "title": row["title"] or "",
                "message_count": len(history),
                "created_at": _iso(row["created_at"]),
                "updated_at": _iso(row["updated_at"]),
            }
        )
    return threads


def get_pi_thread(user_id: int, thread_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, title, history_json, created_at, updated_at
            FROM pi_chat_threads
            WHERE user_id = %s AND id = %s
            """,
            (user_id, thread_id),
        ).fetchone()
    if not row:
        return None
    history = _load_history(row["history_json"])
    return {
        "id": row["id"],
        "title": row["title"] or "",
        "history": history,
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
    }


def create_pi_thread(user_id: int, *, title: str = "", history: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    now = utc_now()
    thread_id = new_thread_id()
    payload = _normalize_history(history or [])
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO pi_chat_threads (id, user_id, title, history_json, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (thread_id, user_id, title.strip(), Json(payload), now, now),
        )
    return {
        "id": thread_id,
        "title": title.strip(),
        "history": payload,
        "created_at": now,
        "updated_at": now,
    }


def upsert_pi_thread(
    user_id: int,
    thread_id: str,
    *,
    title: str | None = None,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    existing = get_pi_thread(user_id, thread_id)
    now = utc_now()
    if existing:
        next_title = title.strip() if title is not None else existing["title"]
        next_history = _normalize_history(history if history is not None else existing["history"])
        with get_conn() as conn:
            conn.execute(
                """
                UPDATE pi_chat_threads
                SET title = %s, history_json = %s, updated_at = %s
                WHERE user_id = %s AND id = %s
                """,
                (next_title, Json(next_history), now, user_id, thread_id),
            )
        return {
            **existing,
            "title": next_title,
            "history": next_history,
            "updated_at": now,
        }

    next_title = (title or "").strip()
    next_history = _normalize_history(history or [])
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO pi_chat_threads (id, user_id, title, history_json, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (thread_id, user_id, next_title, Json(next_history), now, now),
        )
    return {
        "id": thread_id,
        "title": next_title,
        "history": next_history,
        "created_at": now,
        "updated_at": now,
    }


def delete_pi_thread(user_id: int, thread_id: str) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            "DELETE FROM pi_chat_threads WHERE user_id = %s AND id = %s",
            (user_id, thread_id),
        )
        return cur.rowcount > 0


def sync_pi_threads_from_client(user_id: int, threads: list[dict[str, Any]]) -> dict[str, Any]:
    imported = 0
    for item in threads[:MAX_THREADS_PER_USER]:
        thread_id = str(item.get("id") or "").strip()
        if not thread_id:
            continue
        history = _normalize_history(item.get("history") or [])
        if not history and not item.get("title"):
            continue
        upsert_pi_thread(
            user_id,
            thread_id,
            title=str(item.get("title") or ""),
            history=history,
        )
        imported += 1
    return {"imported": imported, "threads": list_pi_threads(user_id)}


def history_for_llm(history: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Build LLM context: recent user/assistant text plus tool summaries."""
    llm_messages: list[dict[str, str]] = []
    for item in history[-MAX_LLM_HISTORY_MESSAGES:]:
        role = item.get("role")
        if role in ("user", "assistant"):
            content = str(item.get("content") or "").strip()
            if content:
                llm_messages.append({"role": role, "content": content})
        elif role == "tool":
            name = str(item.get("name") or "tool")
            summary = str(item.get("summary") or "").strip()
            if summary:
                llm_messages.append(
                    {
                        "role": "assistant",
                        "content": f"[工具 {name} 结果摘要]\n{summary}",
                    }
                )
    return llm_messages
