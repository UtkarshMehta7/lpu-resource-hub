"""In-memory fixed-window rate limiter."""

from __future__ import annotations

import pytest

from app.core.rate_limit import RateLimiter


def test_allows_up_to_the_limit_then_blocks() -> None:
    limiter = RateLimiter(max_requests=3, window_seconds=60.0)

    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is False


def test_keys_are_independent() -> None:
    limiter = RateLimiter(max_requests=1, window_seconds=60.0)

    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("5.6.7.8") is True
    assert limiter.allow("1.2.3.4") is False


def test_resets_after_the_window_elapses(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter = RateLimiter(max_requests=1, window_seconds=10.0)
    current_time = 1000.0
    monkeypatch.setattr("app.core.rate_limit.time.monotonic", lambda: current_time)

    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is False

    current_time += 10.01
    assert limiter.allow("1.2.3.4") is True
