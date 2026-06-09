"""New Pi tools: workbench, email preview/queue (confirm-gated), lead reviews,
and date-aware system prompt."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

import app.agent_chat as agent_chat
from app.agent_chat import (
    PI_DESTRUCTIVE_TOOLS,
    SYSTEM_PROMPT,
    ToolEmitter,
    _run_tool,
    system_prompt_now,
    tool_result_summary,
)
from app.pi_parallel_tools import PARALLEL_SAFE_TOOLS


def emitter() -> ToolEmitter:
    return ToolEmitter(asyncio.Queue())


# ── 日期注入 ──────────────────────────────────────────────────────────


def test_system_prompt_now_contains_today_and_base_prompt():
    prompt = system_prompt_now()
    assert prompt.startswith(SYSTEM_PROMPT)
    assert datetime.now(UTC).date().isoformat() in prompt


# ── get_workbench ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_workbench_dispatch(monkeypatch):
    monkeypatch.setattr(
        agent_chat,
        "get_workbench_summary",
        lambda user_id: {"pending_reviews": 2, "imported_today": 5, "unsent_new": 7},
    )
    result = await _run_tool(1, "get_workbench", {}, emitter())
    assert result["pending_reviews"] == 2
    assert "待审 2" in tool_result_summary("get_workbench", result)


# ── 邮件：模板 / 预览 / 排队 ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_email_templates_strips_bodies(monkeypatch):
    monkeypatch.setattr(
        agent_chat,
        "list_email_templates",
        lambda user_id: [{"id": 1, "name": "拓客", "subject": "Hi {{name}}", "body": "x" * 9000}],
    )
    result = await _run_tool(1, "list_email_templates", {}, emitter())
    assert result["total"] == 1
    assert "body" not in result["templates"][0], "模板正文不应进上下文"


@pytest.mark.asyncio
async def test_preview_email_renders_for_contact(monkeypatch):
    monkeypatch.setattr(
        agent_chat, "get_email_template", lambda uid, tid: {"id": 3, "name": "拓客"}
    )
    monkeypatch.setattr(
        agent_chat, "get_contact", lambda uid, cid: {"id": 9, "email": "noc@example.com"}
    )
    monkeypatch.setattr(
        agent_chat,
        "render_email",
        lambda template, contact: ("主题", "正文文本", "<p>html</p>"),
    )
    result = await _run_tool(1, "preview_email", {"template_id": 3, "contact_id": 9}, emitter())
    assert result == {
        "template": "拓客",
        "to": "noc@example.com",
        "subject": "主题",
        "body_text": "正文文本",
    }


@pytest.mark.asyncio
async def test_preview_email_missing_template(monkeypatch):
    monkeypatch.setattr(agent_chat, "get_email_template", lambda uid, tid: None)
    result = await _run_tool(1, "preview_email", {"template_id": 99, "contact_id": 1}, emitter())
    assert result["error"]


@pytest.mark.asyncio
async def test_queue_emails_requires_confirmation(monkeypatch):
    assert "queue_emails" in PI_DESTRUCTIVE_TOOLS
    monkeypatch.setattr(
        agent_chat, "get_email_template", lambda uid, tid: {"id": 2, "name": "拓客"}
    )
    result = await _run_tool(
        1, "queue_emails", {"contact_ids": [1, 2, 3], "template_id": 2}, emitter()
    )
    assert result["confirm_required"] is True
    assert "3 个联系人" in result["summary"]
    assert "拓客" in result["summary"]
    assert result["pending_args"]["contact_ids"] == [1, 2, 3]


@pytest.mark.asyncio
async def test_queue_emails_runs_after_confirmation(monkeypatch):
    calls = {}

    def fake_queue(user_id, contact_ids, template_id, *, skip_sent=True):
        calls.update(
            user_id=user_id,
            contact_ids=contact_ids,
            template_id=template_id,
            skip_sent=skip_sent,
        )
        return {"queued": 2, "skipped": {"duplicate": 1}, "template": "拓客"}

    monkeypatch.setattr(agent_chat, "queue_emails_for_contacts", fake_queue)
    result = await _run_tool(
        7,
        "queue_emails",
        {"contact_ids": [1, 2, 3], "template_id": 2, "skip_sent": False},
        emitter(),
        allow_destructive=True,
    )
    assert result["queued"] == 2
    assert calls == {
        "user_id": 7,
        "contact_ids": [1, 2, 3],
        "template_id": 2,
        "skip_sent": False,
    }
    assert tool_result_summary("queue_emails", result) == "已排队 2 封邮件"


@pytest.mark.asyncio
async def test_queue_emails_validates_args(monkeypatch):
    result = await _run_tool(
        1, "queue_emails", {"contact_ids": [], "template_id": 2}, emitter(), allow_destructive=True
    )
    assert result["error"]


# ── 待审线索 ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_lead_reviews_dispatch(monkeypatch):
    monkeypatch.setattr(
        agent_chat,
        "list_lead_reviews",
        lambda uid, *, status, limit: [{"id": 1, "status": status}],
    )
    result = await _run_tool(1, "list_lead_reviews", {"status": "pending"}, emitter())
    assert result["total"] == 1
    assert result["status"] == "pending"

    bad = await _run_tool(1, "list_lead_reviews", {"status": "nonsense"}, emitter())
    assert bad["error"]


@pytest.mark.asyncio
async def test_import_lead_reviews_dispatch(monkeypatch):
    monkeypatch.setattr(
        agent_chat,
        "import_lead_reviews",
        lambda uid, ids: {"imported": len(ids), "skipped": 0},
    )
    monkeypatch.setattr(agent_chat, "count_contacts", lambda uid: 120)
    result = await _run_tool(1, "import_lead_reviews", {"review_ids": [4, 5]}, emitter())
    assert result["imported"] == 2
    assert result["total_contacts"] == 120

    empty = await _run_tool(1, "import_lead_reviews", {"review_ids": []}, emitter())
    assert empty["error"]


# ── 注册表一致性 ──────────────────────────────────────────────────────


def test_new_read_tools_are_parallel_safe_and_write_tools_are_not():
    for tool in ("get_workbench", "list_email_templates", "preview_email", "list_lead_reviews"):
        assert tool in PARALLEL_SAFE_TOOLS, tool
    for tool in ("queue_emails", "import_lead_reviews"):
        assert tool not in PARALLEL_SAFE_TOOLS, tool
