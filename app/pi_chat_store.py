from __future__ import annotations

import json
import secrets
from typing import Any

from psycopg.types.json import Json

from app.database import get_conn, utc_now
from app.pi_context import (
    MAX_STORED_MESSAGES,
    MAX_STORED_TOOL_SUMMARY_CHARS,
    SUMMARIZE_BATCH_SIZE,
    build_llm_messages,
    context_stats,
    should_compress_thread,
    summarize_history_batch,
)
from app.settings_store import get_setting

MAX_THREADS_PER_USER = 50
MAX_LLM_HISTORY_MESSAGES = 100


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
            summary = str(item.get("summary") or "").strip()
            if len(summary) > MAX_STORED_TOOL_SUMMARY_CHARS:
                summary = summary[:MAX_STORED_TOOL_SUMMARY_CHARS] + "…"
            entry: dict[str, Any] = {
                "role": "tool",
                "name": str(item.get("name")),
                "summary": summary,
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


def _thread_row_to_dict(row: dict) -> dict[str, Any]:
    history = _load_history(row["history_json"])
    through = int(row.get("context_summary_through") or 0)
    if through > len(history):
        through = len(history)
    thread = {
        "id": row["id"],
        "title": row["title"] or "",
        "history": history,
        "context_summary": row.get("context_summary") or "",
        "context_summary_through": through,
        "created_at": _iso(row["created_at"]),
        "updated_at": _iso(row["updated_at"]),
    }
    thread["context_stats"] = context_stats(
        history,
        context_summary=thread["context_summary"],
        summary_through=through,
        model=get_setting("llm_model", ""),
    )
    return thread


def list_pi_threads(user_id: int) -> list[dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, title, history_json, context_summary, context_summary_through,
                   created_at, updated_at
            FROM pi_chat_threads
            WHERE user_id = %s
            ORDER BY updated_at DESC
            LIMIT %s
            """,
            (user_id, MAX_THREADS_PER_USER),
        ).fetchall()
    threads: list[dict[str, Any]] = []
    for row in rows:
        item = _thread_row_to_dict(dict(row))
        threads.append(
            {
                "id": item["id"],
                "title": item["title"],
                "message_count": len(item["history"]),
                "context_summary_through": item["context_summary_through"],
                "has_context_summary": bool((item.get("context_summary") or "").strip()),
                "created_at": item["created_at"],
                "updated_at": item["updated_at"],
            }
        )
    return threads


def get_pi_thread(user_id: int, thread_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT id, title, history_json, context_summary, context_summary_through,
                   created_at, updated_at
            FROM pi_chat_threads
            WHERE user_id = %s AND id = %s
            """,
            (user_id, thread_id),
        ).fetchone()
    if not row:
        return None
    return _thread_row_to_dict(dict(row))


def update_thread_context(
    user_id: int,
    thread_id: str,
    *,
    context_summary: str,
    context_summary_through: int,
) -> None:
    now = utc_now()
    with get_conn() as conn:
        conn.execute(
            """
            UPDATE pi_chat_threads
            SET context_summary = %s,
                context_summary_through = %s,
                updated_at = %s
            WHERE user_id = %s AND id = %s
            """,
            (
                (context_summary or "")[:6000],
                max(0, int(context_summary_through)),
                now,
                user_id,
                thread_id,
            ),
        )


def append_pi_thread_history_entries(
    user_id: int,
    thread_id: str,
    entries: list[dict[str, Any]],
) -> None:
    if not thread_id or not entries:
        return
    thread = get_pi_thread(user_id, thread_id)
    base_history = list((thread or {}).get("history") or [])
    upsert_pi_thread(user_id, thread_id, history=base_history + entries)


def maybe_compress_thread_context(
    user_id: int, thread_id: str, *, usage_percent: int = 0
) -> dict[str, Any] | None:
    thread = get_pi_thread(user_id, thread_id)
    if not thread:
        return None

    history = thread["history"]
    summary = str(thread.get("context_summary") or "")
    through = int(thread.get("context_summary_through") or 0)
    if not should_compress_thread(len(history), through, usage_percent=usage_percent):
        return thread

    batch_end = min(
        through + SUMMARIZE_BATCH_SIZE,
        len(history) - MAX_LLM_HISTORY_MESSAGES,
    )
    if batch_end <= through:
        return thread

    batch = history[through:batch_end]
    new_summary = summarize_history_batch(summary, batch)
    update_thread_context(
        user_id,
        thread_id,
        context_summary=new_summary,
        context_summary_through=batch_end,
    )
    return get_pi_thread(user_id, thread_id)


def compress_thread_context_until_current(
    user_id: int,
    thread_id: str,
    *,
    max_rounds: int = 24,
) -> dict[str, Any] | None:
    """Run summary batches until recent window is satisfied or max_rounds reached."""
    thread = get_pi_thread(user_id, thread_id)
    if not thread:
        return None

    for _ in range(max_rounds):
        history_len = len(thread["history"])
        through = int(thread.get("context_summary_through") or 0)
        summary = str(thread.get("context_summary") or "")
        usage_percent = int(
            context_stats(
                thread["history"],
                context_summary=summary,
                summary_through=through,
                model=get_setting("llm_model", ""),
            ).get("usage_percent")
            or 0
        )
        if not should_compress_thread(history_len, through, usage_percent=usage_percent):
            return thread

        before = through
        thread = (
            maybe_compress_thread_context(user_id, thread_id, usage_percent=usage_percent) or thread
        )
        after = int(thread.get("context_summary_through") or 0)
        if after <= before:
            return thread

    return thread


def create_pi_thread(
    user_id: int,
    *,
    title: str = "",
    history: list[dict[str, Any]] | None = None,
    context_summary: str = "",
    context_summary_through: int = 0,
) -> dict[str, Any]:
    now = utc_now()
    thread_id = new_thread_id()
    payload = _normalize_history(history or [])
    summary = (context_summary or "")[:6000]
    through = max(0, min(int(context_summary_through), len(payload)))
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO pi_chat_threads (
                id, user_id, title, history_json, context_summary, context_summary_through,
                created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (thread_id, user_id, title.strip(), Json(payload), summary, through, now, now),
        )
    return {
        "id": thread_id,
        "title": title.strip(),
        "history": payload,
        "context_summary": summary,
        "context_summary_through": through,
        "created_at": now,
        "updated_at": now,
    }


def fork_pi_thread(user_id: int, thread_id: str, through_index: int) -> dict[str, Any] | None:
    """Create a branch thread with history copied up to through_index (exclusive end)."""
    parent = get_pi_thread(user_id, thread_id)
    if not parent:
        return None
    history = list(parent.get("history") or [])
    end = max(0, min(int(through_index), len(history)))
    branch_history = history[:end]
    parent_through = int(parent.get("context_summary_through") or 0)
    summary = str(parent.get("context_summary") or "")
    if end <= parent_through:
        summary_through = end
    else:
        summary_through = min(parent_through, len(branch_history))
    base_title = (parent.get("title") or "").strip() or "对话"
    title = f"分支 · {base_title[:40]}"
    return create_pi_thread(
        user_id,
        title=title,
        history=branch_history,
        context_summary=summary if summary_through > 0 else "",
        context_summary_through=summary_through,
    )


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
        through = min(int(existing.get("context_summary_through") or 0), len(next_history))
        with get_conn() as conn:
            conn.execute(
                """
                UPDATE pi_chat_threads
                SET title = %s,
                    history_json = %s,
                    context_summary_through = %s,
                    updated_at = %s
                WHERE user_id = %s AND id = %s
                """,
                (next_title, Json(next_history), through, now, user_id, thread_id),
            )
        return {
            **existing,
            "title": next_title,
            "history": next_history,
            "context_summary_through": through,
            "updated_at": now,
        }

    next_title = (title or "").strip()
    next_history = _normalize_history(history or [])
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO pi_chat_threads (
                id, user_id, title, history_json, context_summary, context_summary_through,
                created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (thread_id, user_id, next_title, Json(next_history), "", 0, now, now),
        )
    return {
        "id": thread_id,
        "title": next_title,
        "history": next_history,
        "context_summary": "",
        "context_summary_through": 0,
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


def history_for_llm(
    history: list[dict[str, Any]],
    *,
    context_summary: str = "",
    summary_through: int = 0,
) -> list[dict[str, str]]:
    return build_llm_messages(
        history,
        context_summary=context_summary,
        summary_through=summary_through,
    )
