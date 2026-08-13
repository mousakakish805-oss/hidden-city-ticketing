"""Client-side rate limiting for upstream provider calls.

The batch engine fans out a dozen searches at once; without this we would trip
provider quotas (the Amadeus test environment allows ~10 requests/second) and
get throttled mid-run.
"""

from __future__ import annotations

import asyncio
import time


class AsyncTokenBucket:
    """Token bucket allowing ``rate`` operations per second with a small burst."""

    def __init__(self, rate: float, burst: int | None = None) -> None:
        if rate <= 0:
            raise ValueError("rate must be positive")
        self._rate = float(rate)
        self._capacity = float(burst if burst is not None else max(1, int(rate)))
        self._tokens = self._capacity
        self._updated_at = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: float = 1.0) -> None:
        """Block until ``tokens`` are available, then consume them."""
        while True:
            async with self._lock:
                now = time.monotonic()
                self._tokens = min(
                    self._capacity, self._tokens + (now - self._updated_at) * self._rate
                )
                self._updated_at = now
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    return
                deficit = tokens - self._tokens
                wait_for = deficit / self._rate
            await asyncio.sleep(wait_for)
