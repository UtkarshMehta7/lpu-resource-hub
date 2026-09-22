"""In-memory fixed-window rate limiting.

No Redis: a single process holds the counters in memory, behind a small
interface (`RateLimiter.allow`) so a shared backend can replace it later
without touching call sites. One limiter instance lives on `app.state`
(created by the lifespan, like the DB engine) rather than as an import-time
global, so each app instance -- including test apps -- owns independent
counters.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock

from fastapi import HTTPException, Request, status

AUTH_RATE_LIMIT_MAX_REQUESTS = 5
AUTH_RATE_LIMIT_WINDOW_SECONDS = 60.0


@dataclass
class RateLimiter:
    max_requests: int
    window_seconds: float
    _hits: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    _lock: Lock = field(default_factory=Lock)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            hits = [hit for hit in self._hits[key] if hit > cutoff]
            if len(hits) >= self.max_requests:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            return True


def create_auth_rate_limiter() -> RateLimiter:
    return RateLimiter(
        max_requests=AUTH_RATE_LIMIT_MAX_REQUESTS, window_seconds=AUTH_RATE_LIMIT_WINDOW_SECONDS
    )


def get_auth_rate_limiter(request: Request) -> RateLimiter:
    limiter: RateLimiter = request.app.state.auth_rate_limiter
    return limiter


def client_ip(request: Request) -> str:
    client = request.client
    return client.host if client else "unknown"


def enforce_auth_rate_limit(request: Request, email: str) -> None:
    """Rate-limits by IP+email, so one abusive IP can't lock out every account
    on it, and one targeted email can't be brute-forced from many IPs alone
    (each IP still gets its own budget against that email)."""
    limiter = get_auth_rate_limiter(request)
    key = f"{client_ip(request)}:{email.lower()}"
    if not limiter.allow(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Try again shortly.",
        )
