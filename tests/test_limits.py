from __future__ import annotations

import pytest

from app.limits import TokenBucket, estimate_tokens


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_bucket_refills_over_time() -> None:
    clock = FakeClock()
    bucket = TokenBucket(capacity=100, refill_per_second=10, clock=clock)
    assert bucket.try_acquire(100)
    assert not bucket.try_acquire(1)
    assert bucket.wait_time(50) == pytest.approx(5.0)
    clock.now = 5.0
    assert bucket.try_acquire(50)
    clock.now = 1_000.0
    assert bucket.available == pytest.approx(100)


def test_bucket_rejects_impossible_requests() -> None:
    with pytest.raises(ValueError):
        TokenBucket(capacity=0, refill_per_second=1)
    with pytest.raises(ValueError):
        TokenBucket(capacity=10, refill_per_second=1).try_acquire(11)


def test_estimate_tokens_is_never_zero() -> None:
    assert estimate_tokens("") == 1
    assert estimate_tokens("x" * 400) == 100
