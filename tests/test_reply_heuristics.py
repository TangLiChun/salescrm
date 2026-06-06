from app.pi_reply_heuristics import (
    _assistant_promises_tool_use,
    _content_is_tool_json_fragment,
    _meaningful_assistant_content,
    _parse_inline_tool_calls,
    _user_requests_continuation,
)


def test_meaningful_content_strips_tool_json_tail():
    assert _meaningful_assistant_content('我来查一下\n[{"name": "x"}]') == "我来查一下"


def test_meaningful_content_blank_for_pure_json_fragment():
    assert _meaningful_assistant_content('{"query": "isp"}') == ""


def test_tool_json_fragment_detection():
    assert _content_is_tool_json_fragment("[")
    assert _content_is_tool_json_fragment("[{")
    assert not _content_is_tool_json_fragment("这是正常的中文回复内容")


def test_promises_tool_use():
    assert _assistant_promises_tool_use("让我查一下")
    assert _assistant_promises_tool_use("好的，正在搜索：")
    assert not _assistant_promises_tool_use("已经为你找到了 3 个联系人。")


def test_user_requests_continuation():
    assert _user_requests_continuation("继续")
    assert _user_requests_continuation("还有吗")
    assert not _user_requests_continuation(
        "请帮我详细分析这家公司的网络架构和所有可能的对接人邮箱地址清单"
    )


def test_parse_inline_tool_calls_extracts_call():
    intro, calls = _parse_inline_tool_calls('好的[工具:list_contacts]{"q": "isp"}')
    assert calls and calls[0]["function"]["name"] == "list_contacts"
    assert "好的" in intro
