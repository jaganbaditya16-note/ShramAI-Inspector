"""In-process sliding-window rate limiter.

Suitable for single-instance deployments. Multi-instance production
deployments should enforce limits at the gateway or with a shared store
(documented in docs/security/security.md). Buckets are identified by
``(bucket_name, client_ip)``.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass

from ..core.errors import RateLimited


@dataclass(frozen=True)
class RateLimitRule:
    name: str
    per_minute: int


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, rule: RateLimitRule, identity: str, *, now: float | None = None) -> None:
        """Raise :class:`RateLimited` when the caller exceeds the rule."""
        current = time.monotonic() if now is None else now
        window_start = current - 60.0
        key = f"{rule.name}:{identity}"
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] < window_start:
                hits.popleft()
            if len(hits) >= rule.per_minute:
                retry_after = max(1, int(60 - (current - hits[0])))
                raise RateLimited(
                    "Too many requests. Please retry shortly.",
                    details={"retry_after_seconds": retry_after},
                )
            hits.append(current)

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


limiter = SlidingWindowLimiter()
