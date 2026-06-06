import pytest

from app.agent_chat import agent_chat_stream
from tests.conftest import assistant_text, collect_events, event_types
from tests.fake_llm import FakeLLM, content_message, tool_call


async def _noop_tools(user_id, name, args, emit):
    return {"ok": True, "name": name, "echo_args": args}


@pytest.mark.asyncio
async def test_plain_text_reply_no_tools():
    fake = FakeLLM([content_message("这是直接回答。")])
    events = await collect_events(
        agent_chat_stream(1, "你好", [], llm_client=fake, tool_runner=_noop_tools)
    )
    assert "这是直接回答。" in assistant_text(events)
    assert event_types(events)[-1] == "done"
    assert not any(e["type"] == "tool_start" for e in events)


@pytest.mark.asyncio
async def test_single_tool_then_summary():
    async def tools(user_id, name, args, emit):
        return {"contacts": [{"id": 1, "email": "a@b.com"}], "total": 1}

    fake = FakeLLM(
        [
            content_message("我来查一下", tool_calls=[tool_call("list_contacts", {"q": "isp"})]),
            content_message("找到 1 个联系人。"),
        ]
    )
    events = await collect_events(
        agent_chat_stream(1, "找 isp 联系人", [], llm_client=fake, tool_runner=tools)
    )
    types = event_types(events)
    assert "tool_start" in types
    assert "tool_result" in types
    assert "找到 1 个联系人。" in assistant_text(events)
    assert types[-1] == "done"


@pytest.mark.asyncio
async def test_intro_only_then_recovers_with_tool():
    # First reply is intro-only ("让我查一下"); loop must nudge, second reply calls a tool.
    fake = FakeLLM(
        [
            content_message("让我查一下"),
            content_message("好的", tool_calls=[tool_call("list_contacts", {"q": ""})]),
            content_message("已为你列出联系人。"),
        ]
    )
    events = await collect_events(
        agent_chat_stream(1, "列出联系人", [], llm_client=fake, tool_runner=_noop_tools)
    )
    assert any(e["type"] == "tool_start" for e in events)
    assert event_types(events)[-1] == "done"


@pytest.mark.asyncio
async def test_error_from_llm_surfaces_and_finishes():
    from tests.fake_llm import error_response

    fake = FakeLLM([error_response("LLM 请求失败 (500)")])
    events = await collect_events(
        agent_chat_stream(1, "x", [], llm_client=fake, tool_runner=_noop_tools)
    )
    assert any(e["type"] == "error" for e in events)
    assert event_types(events)[-1] == "done"


@pytest.mark.asyncio
async def test_tool_json_not_leaked_into_assistant_bubble():
    # Model emits tool JSON as content with no tool_calls field; must not show raw JSON to user.
    fake = FakeLLM(
        [
            content_message('{"name": "list_contacts", "arguments": {"q": "isp"}}'),
            content_message("完成。"),
        ]
    )
    events = await collect_events(
        agent_chat_stream(1, "找联系人", [], llm_client=fake, tool_runner=_noop_tools)
    )
    assert '"arguments"' not in assistant_text(events)
