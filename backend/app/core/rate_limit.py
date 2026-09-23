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
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock

from fastapi import HTTPException, Request, status

AUTH_RATE_LIMIT_MAX_REQUESTS = 5
AUTH_RATE_LIMIT_WINDOW_SECONDS = 60.0
# Search is read-only and browsed interactively, so the budget is far larger
# than auth's -- it exists to stop scraping, not to slow down a user typing.
SEARCH_RATE_LIMIT_MAX_REQUESTS = 60
SEARCH_RATE_LIMIT_WINDOW_SECONDS = 60.0
# Collaboration requests notify a real person, so sending is budgeted per
# user (not IP): enough for genuine outreach, not enough to spam a department.
COLLABORATION_RATE_LIMIT_MAX_REQUESTS = 10
COLLABORATION_RATE_LIMIT_WINDOW_SECONDS = 3600.0


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


def create_search_rate_limiter() -> RateLimiter:
    return RateLimiter(
        max_requests=SEARCH_RATE_LIMIT_MAX_REQUESTS,
        window_seconds=SEARCH_RATE_LIMIT_WINDOW_SECONDS,
    )


def create_collaboration_rate_limiter() -> RateLimiter:
    return RateLimiter(
        max_requests=COLLABORATION_RATE_LIMIT_MAX_REQUESTS,
        window_seconds=COLLABORATION_RATE_LIMIT_WINDOW_SECONDS,
    )


def enforce_collaboration_rate_limit(request: Request, user_id: uuid.UUID) -> None:
    """Per-user budget for sending collaboration requests."""
    limiter: RateLimiter = request.app.state.collaboration_rate_limiter
    if not limiter.allow(str(user_id)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="You're sending requests too quickly. Try again later.",
        )


def get_auth_rate_limiter(request: Request) -> RateLimiter:
    limiter: RateLimiter = request.app.state.auth_rate_limiter
    return limiter


def enforce_search_rate_limit(request: Request) -> None:
    """Route dependency for the directory/search endpoints. Keyed by IP only:
    unlike auth there is no account being targeted."""
    limiter: RateLimiter = request.app.state.search_rate_limiter
    if not limiter.allow(client_ip(request)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Try again shortly.",
        )


def client_ip(request: Request) -> str:
    client = request.client
    return client.host if client else "unknown"


def enforce_auth_rate_limit(request: Request, identifier: str) -> None:
    """Rate-limits by IP + the identifier being tried (a registration number).

    Keyed on both so one abusive IP can't lock out every account behind it,
    and one targeted account can't be brute-forced from many IPs alone (each
    IP still gets its own budget against that account). This matters more now
    that the identifier is a registration number: those are sequential and
    semi-public, so guessing the *account* is trivial and only the password
    is secret.
    """
    limiter = get_auth_rate_limiter(request)
    key = f"{client_ip(request)}:{identifier.lower()}"
    if not limiter.allow(key):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Try again shortly.",
        )
