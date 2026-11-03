"""Client-side admission control for Stage 6.8.

Gemini enforces requests per minute and tokens per minute per project. A
local token bucket per budget lets a service refuse or queue work before it
turns into a burst of 429s that every replica then retries at once.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable


def estimate_tokens(text: str) -> int:
    """Cheap pre-flight estimate (about 4 characters per token for English).

    Use `count_tokens` when you need the real number; this is for admission
    decisions that must not cost a network call.
    """
    return max(1, math.ceil(len(text) / 4))


class TokenBucket:
    """Holds up to `capacity` units and refills at `refill_per_second`.

    For a 1M tokens-per-minute quota with 20% headroom across 4 replicas:
    capacity = refill * 60 = 0.8 * 1_000_000 / 4 per replica.
    """

    def __init__(
        self,
        capacity: float,
        refill_per_second: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if capacity <= 0 or refill_per_second <= 0:
            raise ValueError("capacity and refill rate must be positive")
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self._clock = clock
        self._tokens = capacity
        self._updated = clock()

    def _refill(self) -> None:
        now = self._clock()
        elapsed = max(0.0, now - self._updated)
        self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_per_second)
        self._updated = now

    @property
    def available(self) -> float:
        self._refill()
        return self._tokens

    def try_acquire(self, amount: float = 1.0) -> bool:
        """Take `amount` if available. Never blocks."""
        if amount > self.capacity:
            raise ValueError("request is larger than the bucket can ever hold")
        self._refill()
        if self._tokens >= amount:
            self._tokens -= amount
            return True
        return False

    def wait_time(self, amount: float = 1.0) -> float:
        """Seconds until `amount` would be available (0.0 if it is now)."""
        self._refill()
        missing = amount - self._tokens
        return 0.0 if missing <= 0 else missing / self.refill_per_second
