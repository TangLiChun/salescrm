"""Execute-before-confirm gate for Pi's destructive tools.

The gate is server-controlled (allow_destructive), NOT a model-settable arg, so a
misbehaving model can never self-confirm a deletion. Worst case is a no-op.
"""

from __future__ import annotations

from typing import Any

from app import agent_chat


async def _noop_emit(*_args: Any, **_kwargs: Any) -> None:
    return None


async def test_delete_contacts_requires_confirmation(monkeypatch) -> None:
    ran = {"deleted": False}

    def _boom(*_a: Any, **_k: Any) -> dict:
        ran["deleted"] = True
        return {"deleted": 99}

    monkeypatch.setattr(agent_chat, "get_contact", lambda uid, cid: {"id": cid, "email": "x@y.com"})
    monkeypatch.setattr(agent_chat, "bulk_delete_contacts", _boom)
    monkeypatch.setattr(agent_chat, "delete_contact", _boom)

    result = await agent_chat._run_tool(1, "delete_contacts", {"contact_ids": [1, 2]}, _noop_emit)
    assert result.get("confirm_required") is True
    assert result["name"] == "delete_contacts"
    assert result["pending_args"] == {"contact_ids": [1, 2]}
    assert "2" in result["summary"]
    assert ran["deleted"] is False  # nothing executed without confirmation


async def test_delete_contacts_executes_when_allowed(monkeypatch) -> None:
    monkeypatch.setattr(
        agent_chat, "get_contact", lambda uid, cid: {"id": cid, "email": "x@y.com", "roles": []}
    )
    monkeypatch.setattr(
        agent_chat,
        "bulk_delete_contacts",
        lambda uid, ids: {"deleted": len(ids), "requested": len(ids)},
    )
    result = await agent_chat._run_tool(
        1,
        "delete_contacts",
        {"contact_ids": [1, 2]},
        _noop_emit,
        allow_destructive=True,
    )
    assert not result.get("confirm_required")
    assert result["deleted"] == 2
    assert result["undo_kind"] == "contacts"


async def test_dedupe_requires_confirmation(monkeypatch) -> None:
    ran = {"v": False}

    def _dedupe(**_k: Any) -> dict:
        ran["v"] = True
        return {"removed": 0, "remaining": 0, "removed_rows": []}

    monkeypatch.setattr(agent_chat, "dedupe_contacts", _dedupe)
    result = await agent_chat._run_tool(1, "dedupe_contacts", {}, _noop_emit)
    assert result.get("confirm_required") is True
    assert ran["v"] is False


async def test_reset_prefs_requires_confirmation(monkeypatch) -> None:
    ran = {"v": False}

    def _reset(_uid: int) -> dict:
        ran["v"] = True
        return {}

    monkeypatch.setattr(agent_chat, "reset_prefs", _reset)
    result = await agent_chat._run_tool(1, "reset_lead_preferences", {}, _noop_emit)
    assert result.get("confirm_required") is True
    assert ran["v"] is False


async def test_non_destructive_tool_not_gated(monkeypatch) -> None:
    monkeypatch.setattr(agent_chat, "get_prefs", lambda uid: {"min_score_hint": 60})
    monkeypatch.setattr(agent_chat, "preference_hints_for_llm", lambda prefs: "hints")
    result = await agent_chat._run_tool(1, "get_lead_preferences", {}, _noop_emit)
    assert not result.get("confirm_required")
