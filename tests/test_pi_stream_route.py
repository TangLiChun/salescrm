import pytest

import app.auth as auth
import app.database as database
import app.settings_store as settings_store

database.init_db = lambda: None
settings_store.get_setting = lambda key, default="": default
auth.session_secret = lambda: "test-secret"

from app import main  # noqa: E402
from app.agent_chat import is_pi_thread_streaming, release_pi_thread  # noqa: E402


class FakeRequest:
    async def is_disconnected(self) -> bool:
        return False


async def _read_stream_text(response) -> str:
    chunks: list[str] = []
    async for chunk in response.body_iterator:
        if isinstance(chunk, bytes):
            chunks.append(chunk.decode("utf-8"))
        else:
            chunks.append(str(chunk))
    return "".join(chunks)


@pytest.fixture(autouse=True)
def configured_pi_route(monkeypatch):
    monkeypatch.setattr(main, "llm_configured", lambda: True)
    monkeypatch.setattr(main, "has_active_pi_agent_job", lambda user_id, thread_id: False)


@pytest.mark.asyncio
async def test_pi_stream_route_turns_uncaught_agent_exception_into_sse_error(monkeypatch):
    thread_id = "route-error"

    async def broken_agent_stream(*args, **kwargs):
        raise RuntimeError("boom")
        yield  # pragma: no cover

    monkeypatch.setattr(main, "agent_chat_stream", broken_agent_stream)

    try:
        response = await main.agent_chat_stream_route(
            main.AgentChatRequest(message="hello", history=[], thread_id=thread_id),
            {"id": 1, "username": "test"},
            FakeRequest(),
        )
        text = await _read_stream_text(response)
    finally:
        release_pi_thread(1, thread_id)

    assert '"type": "error"' in text
    assert "Reasonix 执行失败" in text
    assert '"type": "done"' in text
    assert not is_pi_thread_streaming(1, thread_id)


@pytest.mark.asyncio
async def test_pi_stream_route_releases_thread_when_history_persist_fails(monkeypatch):
    thread_id = "persist-error"

    async def ok_agent_stream(*args, **kwargs):
        yield {"type": "assistant_done", "text": "完成"}
        yield {"type": "done"}

    def broken_persist(*args, **kwargs):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(main, "agent_chat_stream", ok_agent_stream)
    monkeypatch.setattr(main, "append_pi_thread_history_entries", broken_persist)

    try:
        response = await main.agent_chat_stream_route(
            main.AgentChatRequest(message="hello", history=[], thread_id=thread_id),
            {"id": 1, "username": "test"},
            FakeRequest(),
        )
        text = await _read_stream_text(response)
    finally:
        release_pi_thread(1, thread_id)

    assert '"type": "assistant_done"' in text
    assert '"type": "done"' in text
    assert not is_pi_thread_streaming(1, thread_id)
