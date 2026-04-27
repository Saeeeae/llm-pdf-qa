import time

from app.pipeline.dlq import KEY, pop_eligible, push


def test_push_then_pop_eligible(fake_redis):
    push({"type": "convert", "rel": "a.pdf", "retry_count": 0, "next_retry": 0})
    results = pop_eligible(time.time())
    assert len(results) == 1
    assert results[0]["rel"] == "a.pdf"


def test_pop_not_eligible_future_retry(fake_redis):
    push({"type": "convert", "rel": "b.pdf", "retry_count": 0, "next_retry": time.time() + 9999})
    results = pop_eligible(time.time())
    assert results == []
    # Entry remains in queue
    assert fake_redis.llen(KEY) == 1


def test_pop_respects_max_retry_count(fake_redis):
    # retry_count >= 3 should not be eligible
    push({"type": "convert", "rel": "c.pdf", "retry_count": 3, "next_retry": 0})
    results = pop_eligible(time.time())
    assert results == []


def test_retry_count_increment_pattern(fake_redis):
    push({"type": "convert", "rel": "d.pdf", "retry_count": 0, "next_retry": 0})
    items = pop_eligible(time.time())
    assert len(items) == 1
    item = items[0]
    new_count = item["retry_count"] + 1
    push({**item, "retry_count": new_count, "next_retry": time.time() + (2 ** new_count) * 60})
    # Not eligible yet
    results = pop_eligible(time.time())
    assert results == []


def test_multiple_entries_partial_eligibility(fake_redis):
    push({"type": "convert", "rel": "e.pdf", "retry_count": 0, "next_retry": 0})
    push({"type": "convert", "rel": "f.pdf", "retry_count": 0, "next_retry": time.time() + 9999})
    results = pop_eligible(time.time())
    assert len(results) == 1
    assert results[0]["rel"] == "e.pdf"
