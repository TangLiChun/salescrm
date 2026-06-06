import os

import pytest

from app.pi_llm_client import stream_chat

pytestmark = pytest.mark.skipif(
    os.getenv("PI_LIVE_LLM") != "1",
    reason="set PI_LIVE_LLM=1 (and configure LLM settings) to run live smoke",
)


@pytest.mark.asyncio
async def test_live_stream_returns_text():
    events = [
        e async for e in stream_chat([{"role": "user", "content": "用一个字回答：你好吗"}], None)
    ]
    assert any(e["type"] == "content_delta" for e in events)
    assert [e for e in events if e["type"] == "message"]
