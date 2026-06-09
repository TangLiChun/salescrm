"""In-memory sliding-window rate limiting for login brute-force protection.

Single-process by design: the app runs as one uvicorn worker. If the
deployment ever scales out, move this state to Postgres or Redis.
"""

from __future__ import annotations

import threading
import time
from collections import deque


class SlidingWindowLimiter:
    """Block a key after too many recorded failures within a time window."""

    def __init__(
        self,
        max_failures: int = 5,
        window_seconds: float = 300.0,
        *,
        clock=time.monotonic,
        max_keys: int = 10_000,
    ) -> None:
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._clock = clock
        self._max_keys = max_keys
        self._failures: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        bucket = self._failures.setdefault(key, deque())
        cutoff = now - self.window_seconds
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        return bucket

    def retry_after(self, key: str) -> int:
        """Seconds until the key may retry; 0 when not blocked."""
        now = self._clock()
        with self._lock:
            bucket = self._prune(key, now)
            if len(bucket) < self.max_failures:
                if not bucket:
                    self._failures.pop(key, None)
                return 0
            oldest = bucket[0]
            return max(1, int(oldest + self.window_seconds - now) + 1)

    def record_failure(self, key: str) -> None:
        now = self._clock()
        with self._lock:
            if len(self._failures) >= self._max_keys and key not in self._failures:
                # Drop expired buckets before refusing to grow; an attacker
                # rotating keys must not evict active counters.
                cutoff = now - self.window_seconds
                for stale in [k for k, b in self._failures.items() if not b or b[-1] <= cutoff]:
                    self._failures.pop(stale, None)
                if len(self._failures) >= self._max_keys:
                    return
            self._prune(key, now).append(now)

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


login_limiter = SlidingWindowLimiter(max_failures=5, window_seconds=300.0)
