import pytest

from app.agent_chat import MAX_LLM_CALLS_PER_TURN, agent_chat_stream
from tests.conftest import collect_events, event_types
from tests.fake_llm import FakeLLM, content_message


async def _noop_tools(user_id, name, args, emit):
    return {"contacts": [], "total": 0}


@pytest.mark.asyncio
async def test_budget_guard_stops_runaway_loop():
    # Intro-only replies + a fallback-triggering user message ("运营商") make every
    # round end in a fallback CRM search, so the loop keeps invoking the LLM across
    # rounds. Without the budget guard it would run MAX_TOOL_ROUNDS*(nudges+1) calls;
    # the guard must cap it at MAX_LLM_CALLS_PER_TURN. Script more than the cap so the
    # FakeLLM never runs dry before the guard fires.
    fake = FakeLLM([content_message("让我查一下") for _ in range(MAX_LLM_CALLS_PER_TURN + 12)])
    events = await collect_events(
        agent_chat_stream(1, "列出运营商联系人", [], llm_client=fake, tool_runner=_noop_tools)
    )
    assert event_types(events)[-1] == "done"
    assert len(fake.calls) <= MAX_LLM_CALLS_PER_TURN
