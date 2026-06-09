from __future__ import annotations

from app.pi_chat_store import fork_pi_thread


def test_fork_pi_thread_copies_prefix_history(monkeypatch) -> None:
    parent = {
        "id": "t_parent",
        "title": "主对话",
        "history": [
            {"role": "user", "content": "a"},
            {"role": "assistant", "content": "b"},
            {"role": "user", "content": "c"},
        ],
        "context_summary": "摘要",
        "context_summary_through": 2,
    }
    captured: dict = {}

    def fake_get_pi_thread(user_id: int, thread_id: str):
        assert user_id == 7
        assert thread_id == "t_parent"
        return parent

    def fake_create_pi_thread(user_id: int, **kwargs):
        captured.update(kwargs)
        return {
            "id": "t_child",
            "title": kwargs["title"],
            "history": kwargs["history"],
            "context_summary": kwargs.get("context_summary", ""),
            "context_summary_through": kwargs.get("context_summary_through", 0),
        }

    monkeypatch.setattr("app.pi_chat_store.get_pi_thread", fake_get_pi_thread)
    monkeypatch.setattr("app.pi_chat_store.create_pi_thread", fake_create_pi_thread)

    child = fork_pi_thread(7, "t_parent", 2)
    assert child is not None
    assert child["id"] == "t_child"
    assert child["title"] == "分支 · 主对话"
    assert captured["history"] == parent["history"][:2]
    assert captured["context_summary_through"] == 2
