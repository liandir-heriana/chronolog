"""TSK-016 RED: login throttle (D2 GREEN target, from verify/task15_test.md §3.2/D2).

Written BEFORE production code — must FAIL on collection until
`src/core/security/rate_limit.py` exists.

Contract: `LoginRateLimiter` blocks after N failures inside the window and
raises the GENERIC `InvalidCredentialsError` (never a new error type), so
throttling never becomes an enumeration oracle.
"""

from datetime import UTC, datetime, timedelta

import pytest

from src.core.security.rate_limit import LoginRateLimiter
from src.modules.auth.domain.exceptions import InvalidCredentialsError

NOW = datetime(2026, 9, 17, 9, 55, tzinfo=UTC)


def test_allows_attempts_under_limit() -> None:
    limiter = LoginRateLimiter(max_attempts=3, window_seconds=60)
    limiter.check("pro@example.com", now=NOW)
    limiter.record_failure("pro@example.com", now=NOW)
    limiter.record_failure("pro@example.com", now=NOW)
    limiter.check("pro@example.com", now=NOW)  # 2 < 3: still allowed


def test_blocks_over_limit_with_generic_error() -> None:
    limiter = LoginRateLimiter(max_attempts=3, window_seconds=60)
    for _ in range(3):
        limiter.record_failure("pro@example.com", now=NOW)
    with pytest.raises(InvalidCredentialsError) as exc_info:
        limiter.check("pro@example.com", now=NOW)
    assert str(exc_info.value) == InvalidCredentialsError.GENERIC_MESSAGE


def test_success_clears_failures() -> None:
    limiter = LoginRateLimiter(max_attempts=2, window_seconds=60)
    limiter.record_failure("a@example.com", now=NOW)
    limiter.record_success("a@example.com")
    limiter.check("a@example.com", now=NOW)  # must not raise


def test_window_slides_and_old_failures_expire() -> None:
    limiter = LoginRateLimiter(max_attempts=2, window_seconds=60)
    old = NOW - timedelta(seconds=61)
    limiter.record_failure("b@example.com", now=old)
    limiter.record_failure("b@example.com", now=old)
    limiter.check("b@example.com", now=NOW)  # outside window: allowed


def test_keys_are_isolated() -> None:
    limiter = LoginRateLimiter(max_attempts=1, window_seconds=60)
    limiter.record_failure("victim@example.com", now=NOW)
    limiter.check("other@example.com", now=NOW)  # different key unaffected
