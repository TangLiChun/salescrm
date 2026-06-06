import pytest

from app.pi_llm_client import RETRYABLE_STATUS, _next_backoff, stream_chat


def test_backoff_increases_and_is_bounded():
    delays = [_next_backoff(i) for i in range(5)]
    assert delays[0] < delays[1] < delays[2]
    assert all(d <= 20.0 for d in delays)


def test_retryable_status_set():
    assert 429 in RETRYABLE_STATUS and 503 in RETRYABLE_STATUS
    assert 400 not in RETRYABLE_STATUS


@pytest.mark.asyncio
async def test_stream_chat_yields_deltas_and_message(monkeypatch):
    from app import pi_llm_client as mod

    monkeypatch.setattr(
        mod, "_settings", lambda: ("key", "https://api.deepseek.com", "deepseek-chat")
    )
    monkeypatch.setattr(mod, "resolve_deepseek_thinking", lambda **_kw: None)

    sse_lines = [
        'data: {"choices": [{"delta": {"content": "你"}}]}',
        'data: {"choices": [{"delta": {"content": "好"}}]}',
        "data: [DONE]",
    ]

    class FakeResponse:
        status_code = 200
        headers: dict = {}

        async def aiter_lines(self):
            for line in sse_lines:
                yield line

        async def aread(self):
            return b""

        def raise_for_status(self):
            return None

    class FakeStreamCtx:
        async def __aenter__(self):
            return FakeResponse()

        async def __aexit__(self, *a):
            return False

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def stream(self, *a, **k):
            return FakeStreamCtx()

    monkeypatch.setattr(mod.httpx, "AsyncClient", FakeClient)

    events = [e async for e in stream_chat([{"role": "user", "content": "hi"}], None)]
    deltas = "".join(e["text"] for e in events if e["type"] == "content_delta")
    assert deltas == "你好"
    msg = [e for e in events if e["type"] == "message"][0]["message"]
    assert msg["content"] == "你好"


@pytest.mark.asyncio
async def test_stream_chat_retries_on_503_then_succeeds(monkeypatch):
    from app import pi_llm_client as mod

    monkeypatch.setattr(
        mod, "_settings", lambda: ("key", "https://api.deepseek.com", "deepseek-chat")
    )
    monkeypatch.setattr(mod, "resolve_deepseek_thinking", lambda **_kw: None)

    async def _instant_sleep(*_a, **_k):
        return None

    monkeypatch.setattr(mod.asyncio, "sleep", _instant_sleep)

    attempts = {"n": 0}

    class Resp503:
        status_code = 503
        headers: dict = {}

        async def aiter_lines(self):
            if False:
                yield ""

        async def aread(self):
            return b"overloaded"

    class Resp200:
        status_code = 200
        headers: dict = {}

        async def aiter_lines(self):
            yield 'data: {"choices": [{"delta": {"content": "ok"}}]}'
            yield "data: [DONE]"

        async def aread(self):
            return b""

    class Ctx:
        def __init__(self, resp):
            self._resp = resp

        async def __aenter__(self):
            return self._resp

        async def __aexit__(self, *a):
            return False

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def stream(self, *a, **k):
            attempts["n"] += 1
            return Ctx(Resp503() if attempts["n"] == 1 else Resp200())

    monkeypatch.setattr(mod.httpx, "AsyncClient", FakeClient)

    events = [e async for e in stream_chat([{"role": "user", "content": "hi"}], None)]
    assert attempts["n"] == 2  # retried once
    assert any(e["type"] == "content_delta" and e["text"] == "ok" for e in events)
