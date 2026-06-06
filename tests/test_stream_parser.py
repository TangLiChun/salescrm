from app.pi_stream_parser import (
    assemble_message,
    consume_stream_chunk,
    merge_tool_call_delta,
    parse_sse_line,
    parse_sse_or_json_lines,
)


def _consume(chunk):
    content, reasoning, tools, emitted = [], [], {}, [False]
    events = consume_stream_chunk(
        chunk,
        content_parts=content,
        reasoning_parts=reasoning,
        tool_calls=tools,
        emit_content_delta=True,
        tool_status_emitted=emitted,
    )
    return content, reasoning, tools, events


def test_content_delta_emitted():
    content, _, _, events = _consume({"choices": [{"delta": {"content": "hi"}}]})
    assert content == ["hi"]
    assert {"type": "content_delta", "text": "hi"} in events


def test_tool_call_delta_accumulates_arguments():
    tools = {}
    merge_tool_call_delta(tools, {"index": 0, "id": "c1", "function": {"name": "list_contacts"}})
    merge_tool_call_delta(tools, {"index": 0, "function": {"arguments": '{"q":'}})
    merge_tool_call_delta(tools, {"index": 0, "function": {"arguments": ' "isp"}'}})
    assert tools[0]["function"]["name"] == "list_contacts"
    assert tools[0]["function"]["arguments"] == '{"q": "isp"}'


def test_assemble_message_drops_empty_tool_slots():
    tools = {0: {"id": "", "type": "function", "function": {"name": "", "arguments": ""}}}
    msg = assemble_message(["hello"], [], tools)
    assert msg["content"] == "hello"
    assert "tool_calls" not in msg


def test_assemble_message_assigns_missing_id():
    tools = {0: {"id": "", "type": "function", "function": {"name": "x", "arguments": "{}"}}}
    msg = assemble_message([], [], tools)
    assert msg["tool_calls"][0]["id"].startswith("call_")


def test_finish_reason_is_preserved():
    content, reasoning, tools, emitted, finish_reasons = [], [], {}, [False], []
    events = consume_stream_chunk(
        {"choices": [{"delta": {"content": "hi"}, "finish_reason": "length"}]},
        content_parts=content,
        reasoning_parts=reasoning,
        tool_calls=tools,
        emit_content_delta=True,
        tool_status_emitted=emitted,
        finish_reasons=finish_reasons,
    )
    msg = assemble_message(content, reasoning, tools, finish_reasons)
    assert finish_reasons == ["length"]
    assert msg["finish_reason"] == "length"
    assert {"type": "content_delta", "text": "hi"} in events


def test_parse_sse_line():
    assert parse_sse_line("data: [DONE]") is None
    assert parse_sse_line("") is None
    assert parse_sse_line('data: {"a": 1}') == {"a": 1}
    assert parse_sse_line('{"b": 2}') == {"b": 2}


def test_parse_sse_or_json_lines_fallback_to_single_json():
    body = b'{"choices": [{"message": {"content": "hi"}}]}'
    chunks = parse_sse_or_json_lines(body)
    assert chunks and chunks[0]["choices"][0]["message"]["content"] == "hi"
