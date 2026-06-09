from app.pi_context import (
    is_context_overflow_error,
    is_valid_compression_cut,
    next_compression_batch_end,
)


def test_is_context_overflow_error():
    assert is_context_overflow_error("maximum context length exceeded")
    assert is_context_overflow_error("上下文过长，请压缩")
    assert not is_context_overflow_error("rate limit exceeded")


def test_valid_compression_cut_respects_tool_chain():
    history = [
        {"role": "user", "content": "a"},
        {"role": "assistant", "content": "call tool"},
        {"role": "tool", "name": "x", "summary": "ok"},
        {"role": "user", "content": "b"},
    ]
    assert is_valid_compression_cut(history, 1)
    assert not is_valid_compression_cut(history, 2)
    assert not is_valid_compression_cut(history, 3)
    assert is_valid_compression_cut(history, 4)


def test_next_compression_batch_end_snaps_before_tool_orphan():
    history = [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "tool", "name": "t", "summary": "r"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2"},
    ]
    end = next_compression_batch_end(history, 0, 3, len(history))
    assert end in (1, 4)
    assert is_valid_compression_cut(history, end)
