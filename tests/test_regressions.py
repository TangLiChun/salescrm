import pytest

from app.agent_chat import agent_chat_stream
from tests.conftest import assistant_text, collect_events, event_types
from tests.fake_llm import FakeLLM, content_message, tool_call


async def _noop_tools(user_id, name, args, emit):
    return {"contacts": [], "total": 0}


@pytest.mark.asyncio
async def test_regression_intro_only_does_not_stop_25733dc():
    # "让我查一下" alone must not end the turn without doing work.
    fake = FakeLLM(
        [
            content_message("让我查一下"),
            content_message("好的", tool_calls=[tool_call("list_contacts", {"q": ""})]),
            content_message("已列出。"),
        ]
    )
    events = await collect_events(
        agent_chat_stream(1, "列出联系人", [], llm_client=fake, tool_runner=_noop_tools)
    )
    assert any(e["type"] == "tool_start" for e in events)
    assert event_types(events)[-1] == "done"


@pytest.mark.asyncio
async def test_regression_empty_reply_no_blank_bubble_0a34da1():
    fake = FakeLLM([content_message(""), content_message(""), content_message("")])
    events = await collect_events(
        agent_chat_stream(1, "x", [], llm_client=fake, tool_runner=_noop_tools)
    )
    # No empty assistant_done bubbles; ends on a real error + done.
    assert all(str(e.get("text") or "").strip() for e in events if e["type"] == "assistant_done")
    assert any(e["type"] == "error" for e in events)
    assert event_types(events)[-1] == "done"


@pytest.mark.asyncio
async def test_regression_invalid_tool_call_no_infinite_loop_de9d52b():
    # Truly-malformed tool calls (empty name+args) are dropped by _prepare_tool_calls.
    # With a non-keyword user message there is no fallback, so decide_turn must Retry a
    # bounded number of times then Fail — never loop forever.
    bad = {"id": "x", "type": "function", "function": {"name": "", "arguments": ""}}
    fake = FakeLLM([content_message("", tool_calls=[bad]) for _ in range(5)])
    events = await collect_events(
        agent_chat_stream(1, "做点什么", [], llm_client=fake, tool_runner=_noop_tools)
    )
    assert event_types(events)[-1] == "done"
    assert any(e["type"] == "error" for e in events)
    assert len(fake.calls) <= 4  # bounded: ~3 calls (2 retries + final) then Fail


@pytest.mark.asyncio
async def test_regression_tool_json_not_in_bubble_de9d52b():
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


@pytest.mark.asyncio
async def test_regression_continue_resumes_discover_25733dc():
    # NOTE: user_message="继续" keeps _user_requests_continuation=True every round, so
    # each non-tool-call LLM response cycles through Retry×2 then FallbackToolCalls.
    # We script 3 intro-only replies (rounds the Retry path) to trigger FallbackToolCalls
    # with discover_leads, then provide direct tool_call responses for subsequent rounds
    # so the loop terminates within MAX_TOOL_ROUNDS (12).
    history = [
        {"role": "user", "content": "找美国运营商 peering 联系人"},
        {"role": "tool", "name": "discover_leads", "summary": "30 条"},
    ]
    seen = []

    async def tools(user_id, name, args, emit):
        seen.append(name)
        return {"lead_count": 0, "leads": []}

    # 3 intro-only replies trigger FallbackToolCalls→discover_leads (round 0).
    # 11 direct tool-call replies let rounds 1-11 each complete in one LLM call.
    # 1 final text reply for _stream_text_reply at the round cap (round 11).
    fake = FakeLLM(
        [content_message("好的，继续") for _ in range(3)]
        + [
            content_message("继续搜索", tool_calls=[tool_call("list_contacts", {"q": ""})])
            for _ in range(11)
        ]
        + [content_message("已扩展搜索完成。")]
    )
    await collect_events(agent_chat_stream(1, "继续", history, llm_client=fake, tool_runner=tools))
    assert "discover_leads" in seen


@pytest.mark.asyncio
async def test_regression_round_cap_produces_summary_a5d4291():
    # Model always calls a tool; loop must summarize at the round cap rather than error.
    # NOTE: _stream_text_reply (called at round cap) consumes the 13th FakeLLM response
    # (another tool-call reply) and extracts its content ("查") as the summary text.
    # The 21st response ("这是最终总结。") is never reached. The assertion validates
    # that *some* non-empty text was produced (regression: used to error instead).
    # Total LLM calls = 12 (one per round) + 1 (_stream_text_reply) = 13.
    fake = FakeLLM(
        [
            content_message("查", tool_calls=[tool_call("list_contacts", {"q": "x"})])
            for _ in range(20)
        ]
        + [content_message("这是最终总结。")]
    )
    events = await collect_events(
        agent_chat_stream(1, "不停地搜", [], llm_client=fake, tool_runner=_noop_tools)
    )
    assert event_types(events)[-1] == "done"
    assert assistant_text(events).strip()  # produced a final textual summary


@pytest.mark.asyncio
async def test_regression_llm_error_finishes_cleanly_af37be6():
    from tests.fake_llm import error_response

    fake = FakeLLM([error_response("LLM 请求失败 (500): upstream")])
    events = await collect_events(
        agent_chat_stream(1, "x", [], llm_client=fake, tool_runner=_noop_tools)
    )
    assert any(e["type"] == "error" for e in events)
    assert event_types(events)[-1] == "done"
    # The stream-interrupted false-positive regression: a clean error must still end in done.
