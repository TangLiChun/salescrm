"""Undo capture for Pi's destructive tools (delete / dedupe / reset prefs).

These exercise the capture wiring without a live DB: dedupe_contacts accepts a
fake connection, and _run_tool's DB calls are module-level imports we monkeypatch.
"""
from __future__ import annotations

from typing import Any

from app import agent_chat
from app.database import dedupe_contacts


async def _noop_emit(*_args: Any, **_kwargs: Any) -> None:
    return None


class _FakeCursor:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def fetchall(self) -> list[dict]:
        return self._rows


class _FakeConn:
    """SELECT returns preset rows; DELETE records the id it was given."""

    def __init__(self, rows: list[dict]):
        self._rows = rows
        self.deleted_ids: list[int] = []

    def execute(self, sql: str, params: Any = None) -> _FakeCursor:
        verb = " ".join(sql.split()).upper()
        if verb.startswith("DELETE"):
            self.deleted_ids.append(params[0])
            return _FakeCursor([])
        return _FakeCursor(self._rows)


def test_dedupe_contacts_returns_removed_rows() -> None:
    rows = [
        {"id": 1, "user_id": 1, "email": "a@x.com", "org": "X", "name": "A",
         "roles": "noc", "notes": "", "email_sent": True, "email_sent_at": None, "created_at": None},
        {"id": 2, "user_id": 1, "email": "A@x.com", "org": "X2", "name": "A2",
         "roles": "abuse", "notes": "dup", "email_sent": False, "email_sent_at": None, "created_at": None},
        {"id": 3, "user_id": 1, "email": "b@x.com", "org": "Y", "name": "B",
         "roles": "", "notes": "", "email_sent": False, "email_sent_at": None, "created_at": None},
    ]
    conn = _FakeConn(rows)
    result = dedupe_contacts(user_id=1, conn=conn)
    assert result["removed"] == 1
    assert conn.deleted_ids == [2]
    removed = result["removed_rows"]
    assert [r["email"] for r in removed] == ["A@x.com"]
    assert removed[0]["org"] == "X2"
    assert removed[0]["notes"] == "dup"


async def test_delete_contacts_includes_undo_payload(monkeypatch) -> None:
    captured = {
        11: {"id": 11, "email": "a@x.com", "org": "X", "name": "A", "roles": ["noc"], "notes": "hi"},
        12: {"id": 12, "email": "b@x.com", "org": "Y", "name": "B", "roles": [], "notes": ""},
    }
    monkeypatch.setattr(agent_chat, "get_contact", lambda uid, cid: captured.get(cid))
    monkeypatch.setattr(
        agent_chat, "bulk_delete_contacts",
        lambda uid, ids: {"deleted": len(ids), "requested": len(ids)},
    )
    result = await agent_chat._run_tool(
        1, "delete_contacts", {"contact_ids": [11, 12]}, _noop_emit, allow_destructive=True,
    )
    assert result["deleted"] == 2
    assert result["undo_kind"] == "contacts"
    assert {r["email"] for r in result["undo_payload"]} == {"a@x.com", "b@x.com"}
    # roles list is normalized to a comma string for re-import
    row = next(r for r in result["undo_payload"] if r["email"] == "a@x.com")
    assert row["roles"] == "noc"
    assert row["source"] == "undo-restore"


async def test_delete_single_contact_includes_undo_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_chat, "get_contact",
        lambda uid, cid: {"id": cid, "email": "solo@x.com", "org": "Z", "roles": ["abuse"]},
    )
    monkeypatch.setattr(agent_chat, "delete_contact", lambda uid, cid: True)
    result = await agent_chat._run_tool(
        1, "delete_contacts", {"contact_ids": [7]}, _noop_emit, allow_destructive=True,
    )
    assert result["deleted"] == 1
    assert result["undo_kind"] == "contacts"
    assert result["undo_payload"][0]["email"] == "solo@x.com"


async def test_reset_lead_preferences_includes_undo_payload(monkeypatch) -> None:
    prior = {"min_score_hint": 70, "stats": {"imports": 5}}
    monkeypatch.setattr(agent_chat, "get_prefs", lambda uid: prior)
    monkeypatch.setattr(agent_chat, "reset_prefs", lambda uid: {"min_score_hint": 60})
    result = await agent_chat._run_tool(
        1, "reset_lead_preferences", {}, _noop_emit, allow_destructive=True,
    )
    assert result["ok"] is True
    assert result["undo_kind"] == "prefs"
    assert result["undo_payload"] == prior
