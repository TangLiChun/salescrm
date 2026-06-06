import pytest

from tests.conftest import collect_events
from tests.fake_llm import FakeLLM, content_message, error_response, tool_call


@pytest.mark.asyncio
async def test_fake_llm_yields_scripted_text():
    fake = FakeLLM([content_message("你好")])
    events = await collect_events(fake(messages=[], tools=None))
    assert {"type": "content_delta", "text": "你好"} in events
    msg = [e for e in events if e["type"] == "message"][0]["message"]
    assert msg["content"] == "你好"
    assert "tool_calls" not in msg


@pytest.mark.asyncio
async def test_fake_llm_yields_tool_calls():
    fake = FakeLLM([content_message("查一下", tool_calls=[tool_call("list_contacts", {"q": "isp"})])])
    events = await collect_events(fake(messages=[], tools=None))
    msg = [e for e in events if e["type"] == "message"][0]["message"]
    assert msg["tool_calls"][0]["function"]["name"] == "list_contacts"


@pytest.mark.asyncio
async def test_fake_llm_advances_per_call_and_records():
    fake = FakeLLM([content_message("first"), content_message("second")])
    await collect_events(fake(messages=[{"role": "user", "content": "hi"}], tools=None))
    second = await collect_events(fake(messages=[], tools=None, tool_choice="required"))
    assert [e for e in second if e["type"] == "message"][0]["message"]["content"] == "second"
    assert len(fake.calls) == 2
    assert fake.calls[1]["tool_choice"] == "required"


@pytest.mark.asyncio
async def test_fake_llm_error_response():
    fake = FakeLLM([error_response("boom")])
    events = await collect_events(fake(messages=[], tools=None))
    assert events == [{"type": "error", "message": "boom"}]


@pytest.mark.asyncio
async def test_fake_llm_runs_out_of_script():
    fake = FakeLLM([content_message("only one")])
    await collect_events(fake(messages=[], tools=None))
    with pytest.raises(AssertionError):
        await collect_events(fake(messages=[], tools=None))
