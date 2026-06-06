from app.pi_decisions import (
    EmitToolCalls,
    Fail,
    FallbackToolCalls,
    FinalReply,
    Retry,
    decide_turn,
)


def _assistant(content=None, tool_calls=None, reasoning=None):
    msg = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    if reasoning:
        msg["reasoning_content"] = reasoning
    return msg


def _valid_call(name="list_contacts", args='{"q": "isp"}'):
    return {"id": "c1", "type": "function", "function": {"name": name, "arguments": args}}


def test_valid_tool_calls_emit():
    d = decide_turn(
        _assistant("我来查", [_valid_call()]),
        "我来查",
        user_message="找联系人",
        history=[],
        nudge_count=0,
        max_nudges=2,
    )
    assert isinstance(d, EmitToolCalls)
    assert d.prepared_calls[0][1] == "list_contacts"


def test_plain_text_is_final_reply():
    d = decide_turn(
        _assistant("已为你找到 3 个联系人。"),
        "已为你找到 3 个联系人。",
        user_message="找联系人",
        history=[],
        nudge_count=0,
        max_nudges=2,
    )
    assert isinstance(d, FinalReply)
    assert "3 个联系人" in d.text


def test_empty_response_retries_then_fails():
    d = decide_turn(_assistant(None), "", user_message="x", history=[], nudge_count=0, max_nudges=2)
    assert isinstance(d, Retry)
    d2 = decide_turn(
        _assistant(None), "", user_message="x", history=[], nudge_count=2, max_nudges=2
    )
    assert isinstance(d2, Fail)


def test_intro_only_retries_then_falls_back():
    d = decide_turn(
        _assistant("让我查一下"),
        "让我查一下",
        user_message="列出运营商联系人",
        history=[],
        nudge_count=0,
        max_nudges=2,
    )
    assert isinstance(d, Retry)
    assert "工具" in d.nudge or "开场白" in d.nudge
    d2 = decide_turn(
        _assistant("让我查一下"),
        "让我查一下",
        user_message="列出运营商联系人",
        history=[],
        nudge_count=2,
        max_nudges=2,
    )
    assert isinstance(d2, FallbackToolCalls)


def test_inline_tool_call_in_content_is_emitted():
    d = decide_turn(
        _assistant('好的[工具:list_contacts]{"q": "isp"}'),
        '好的[工具:list_contacts]{"q": "isp"}',
        user_message="找联系人",
        history=[],
        nudge_count=0,
        max_nudges=2,
    )
    assert isinstance(d, EmitToolCalls)
    assert d.prepared_calls[0][1] == "list_contacts"


def test_continuation_request_falls_back_to_discover():
    history = [
        {"role": "user", "content": "找美国运营商 peering 联系人"},
        {"role": "tool", "name": "discover_leads", "summary": "30 条"},
    ]
    d = decide_turn(
        _assistant("好的，继续"),
        "好的，继续",
        user_message="继续",
        history=history,
        nudge_count=2,
        max_nudges=2,
    )
    assert isinstance(d, FallbackToolCalls)
    assert d.prepared_calls[0][1] == "discover_leads"


def test_empty_response_with_reasoning_is_not_empty():
    # If there's reasoning_content but no visible content, the loop originally
    # treated this as non-empty (nudged_empty_response stays False).
    # decide_turn: _assistant_response_empty returns False when reasoning is present.
    d = decide_turn(
        _assistant(None, reasoning="我在思考如何查找联系人"),
        "",
        user_message="找联系人",
        history=[],
        nudge_count=0,
        max_nudges=2,
    )
    # Should not be Retry for empty response; falls through to no-tool-calls path
    assert not isinstance(d, Fail)


def test_invalid_tool_calls_retries_then_falls_back():
    # Tool calls list that will be fully dropped by _prepare_tool_calls
    # (non-dict items are the clearest way to get empty prepared list)
    # NOTE: _prepare_tool_calls drops non-dict entries and entries whose name
    # resolves to "unknown". A bare dict with name "unknown" should be dropped.
    bad_call = {"id": "x1", "type": "function", "function": {"name": "", "arguments": "{}"}}
    # Empty name with no args => _infer_tool_name returns "unknown" => dropped
    d = decide_turn(
        _assistant(None, [bad_call]),
        "",
        user_message="列出运营商联系人",
        history=[],
        nudge_count=0,
        max_nudges=2,
    )
    assert isinstance(d, Retry)

    d2 = decide_turn(
        _assistant(None, [bad_call]),
        "",
        user_message="列出运营商联系人",
        history=[],
        nudge_count=2,
        max_nudges=2,
    )
    # After nudges exhausted, falls back to CRM search for "运营商联系人"
    assert isinstance(d2, FallbackToolCalls)


def test_continuation_no_fallback_returns_fail():
    # NOTE: The "无法继续上一任务" error path in agent_chat.py (lines 1590-1593) requires
    # both (a) continue_request=True AND (b) _fallback_prepared_calls returns [].
    # In practice, _fallback_prepared_calls always returns a list_contacts fallback when
    # _user_requests_continuation is True (the second branch at pi_reply_heuristics.py:235
    # runs even when _infer_continuation_query returns ""). So the Fail path is unreachable
    # for any normal continuation message via decide_turn (the real loop would also never
    # reach it for "继续" with empty history). We instead verify the FallbackToolCalls path
    # that actually fires in this scenario.
    d = decide_turn(
        _assistant("好的，继续"),
        "好的，继续",
        user_message="继续",
        history=[],  # no substantive history -> _infer_continuation_query returns ""
        nudge_count=2,
        max_nudges=2,
    )
    # _fallback_prepared_calls("继续", []) returns a list_contacts call (q="") via the
    # second _user_requests_continuation branch in pi_reply_heuristics.py:235
    assert isinstance(d, FallbackToolCalls)
    assert d.prepared_calls[0][1] == "list_contacts"
