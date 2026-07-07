"""
In-process rate limiting.

There is no auth yet, so the URL itself is the only gate: these limits stop a
shared/leaked link (or a runaway script) from burning the LLM quota or
hammering the API. In-memory sliding windows fit the single-replica,
stateless-v1 design — no Redis until the app itself outgrows one process.
"""

import os
import threading
import time
from dataclasses import dataclass
from typing import Callable, Dict, List

from fastapi import Request


@dataclass
class RateLimits:
    """Knobs, overridable via env on the deployment."""

    api_per_minute: int = int(os.getenv("API_RATE_LIMIT_PER_MINUTE", "120"))
    screenings_per_hour_per_ip: int = int(os.getenv("SCREENINGS_PER_HOUR_PER_IP", "20"))
    screenings_per_hour_global: int = int(os.getenv("SCREENINGS_PER_HOUR_GLOBAL", "60"))


class SlidingWindowLimiter:
    """Thread-safe sliding-window counter keyed by caller."""

    def __init__(self, limit: int, window_seconds: float, clock: Callable[[], float] = time.monotonic):
        self.limit = limit
        self.window = window_seconds
        self.clock = clock
        self._hits: Dict[str, List[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, int]:
        """Returns (allowed, retry_after_seconds)."""
        now = self.clock()
        with self._lock:
            hits = [t for t in self._hits.get(key, []) if now - t < self.window]
            if len(hits) >= self.limit:
                retry_after = int(self.window - (now - hits[0])) + 1
                self._hits[key] = hits
                return False, retry_after
            hits.append(now)
            self._hits[key] = hits
            return True, 0


def client_ip(request: Request) -> str:
    """Caller identity: first X-Forwarded-For hop behind a proxy (Railway),
    else the socket peer."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
