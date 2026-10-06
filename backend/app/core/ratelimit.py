"""Tiny in-process sliding-window rate limiter (per key)."""
from __future__ import annotations

import time
from collections import defaultdict, deque

from .config import get_settings

settings = get_settings()
_buckets: dict[str, deque[float]] = defaultdict(deque)


def check_rate_limit(key: str, limit: int | None = None, window_seconds: int = 60) -> bool:
    """Return True if allowed, False if the key exceeded the limit."""
    limit = limit or settings.rate_limit_per_minute
    now = time.time()
    bucket = _buckets[key]
    while bucket and bucket[0] <= now - window_seconds:
        bucket.popleft()
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    return True
