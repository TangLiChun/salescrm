import pytest

from app.pi_context import (
    CONTEXT_USAGE_COMPRESS_PERCENT,
    MAX_RECENT_FULL_MESSAGES,
    SUMMARIZE_BATCH_SIZE,
    SUMMARIZE_TRIGGER_GAP,
    needs_summary_update,
    should_compress_thread,
)


def test_should_compress_when_needs_summary_update():
    history_len = MAX_RECENT_FULL_MESSAGES + SUMMARIZE_TRIGGER_GAP + 10
    assert needs_summary_update(history_len, 0)
    assert should_compress_thread(history_len, 0, usage_percent=0)
    assert should_compress_thread(history_len, 0, usage_percent=50)


def test_should_compress_when_usage_high_and_uncovered_exceeds_batch():
    history_len = 120
    summary_through = 50
    uncovered = history_len - summary_through
    assert uncovered > SUMMARIZE_BATCH_SIZE
    assert not needs_summary_update(history_len, summary_through)
    assert should_compress_thread(
        history_len,
        summary_through,
        usage_percent=CONTEXT_USAGE_COMPRESS_PERCENT,
    )
    assert should_compress_thread(history_len, summary_through, usage_percent=95)


def test_should_not_compress_when_usage_high_but_uncovered_within_batch():
    history_len = 70
    summary_through = 30
    uncovered = history_len - summary_through
    assert uncovered == SUMMARIZE_BATCH_SIZE
    assert not needs_summary_update(history_len, summary_through)
    assert not should_compress_thread(history_len, summary_through, usage_percent=90)


def test_should_not_compress_when_usage_below_threshold():
    history_len = 120
    summary_through = 0
    assert not needs_summary_update(history_len, summary_through)
    assert not should_compress_thread(history_len, summary_through, usage_percent=79)


@pytest.mark.parametrize(
    "usage_percent",
    [CONTEXT_USAGE_COMPRESS_PERCENT - 1, 0],
)
def test_usage_just_below_threshold_does_not_trigger_proactive_compress(usage_percent):
    history_len = 120
    summary_through = 0
    assert not needs_summary_update(history_len, summary_through)
    assert not should_compress_thread(
        history_len,
        summary_through,
        usage_percent=usage_percent,
    )
