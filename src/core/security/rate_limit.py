"""ChronoLog login rate limiter (stdlib only, no framework imports).

TSK-016 (D2): per-email (+ per-IP, composed by the caller into one key)
throttle that preserves the generic ``InvalidCredentialsError`` — throttling
never becomes an enumeration oracle. Lives OUTSIDE ``AuthenticateUser`` so
the pure use-case stays clock/state-free (TSK-015 D2 verdict).

Usage from the presentation layer::

    limiter.check(key, now=now)          # raises generic error if throttled
    try:
        session = authenticate.execute(email=email, password=password)
    except InvalidCredentialsError:
        limiter.record_failure(key, now=now)
        raise
    limiter.record_success(key)
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from src.modules.auth.domain.exceptions import InvalidCredentialsError


class LoginRateLimiter:
    """Sliding-window in-memory limiter keyed by an opaque string.

    Args:
        max_attempts: failures allowed inside the window before blocking.
        window_seconds: sliding window length.
    """

    def __init__(self, *, max_attempts: int = 5, window_seconds: int = 300) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if window_seconds < 1:
            raise ValueError("window_seconds must be >= 1")
        self._max_attempts = max_attempts
        self._window_seconds = window_seconds
        self._failures: dict[str, list[datetime]] = defaultdict(list)

    @property
    def max_attempts(self) -> int:
        """Return the configured failure budget per window."""
        return self._max_attempts

    @property
    def window_seconds(self) -> int:
        """Return the configured sliding-window length in seconds."""
        return self._window_seconds

    def _prune(self, key: str, now: datetime) -> list[datetime]:
        cutoff = now.timestamp() - self._window_seconds
        fresh = [t for t in self._failures.get(key, []) if t.timestamp() > cutoff]
        if fresh:
            self._failures[key] = fresh
        else:
            self._failures.pop(key, None)
        return fresh

    def check(self, key: str, *, now: datetime | None = None) -> None:
        """Raise generic ``InvalidCredentialsError`` when ``key`` is throttled."""
        moment = now or datetime.now(UTC)
        if len(self._prune(key, moment)) >= self._max_attempts:
            raise InvalidCredentialsError()

    def record_failure(self, key: str, *, now: datetime | None = None) -> None:
        """Record one failed login for ``key``."""
        moment = now or datetime.now(UTC)
        if moment.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        self._failures[key].append(moment)
        self._prune(key, moment)

    def record_success(self, key: str) -> None:
        """Clear failures for ``key`` after a successful login."""
        self._failures.pop(key, None)
