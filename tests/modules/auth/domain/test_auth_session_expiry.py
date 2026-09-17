"""TSK-016 RED: AuthSession expiry (D3 GREEN target, from verify/task15_test.md §3.2).

Written BEFORE production code — must FAIL until
`src/modules/auth/domain/entities.py` gains `expires_at` + `issue(ttl)` +
`is_expired`. Spec: `AuthSession.issue(user_id, *, ttl_hours=12)` sets
`expires_at = created_at + ttl`; `is_expired(now) -> bool`.
"""

from datetime import UTC, datetime, timedelta

from src.modules.auth.domain.entities import AuthSession


def test_issued_session_carries_expiry() -> None:
    session = AuthSession.issue("user-1")
    assert session.expires_at > session.created_at  # RED today: AttributeError


def test_expired_session_detects_expiry() -> None:
    session = AuthSession.issue("user-1", ttl_hours=-1)
    assert session.is_expired(datetime.now(UTC)) is True  # RED today: AttributeError


def test_default_ttl_is_twelve_hours() -> None:
    session = AuthSession.issue("user-1")
    delta = session.expires_at - session.created_at
    assert timedelta(hours=12) <= delta < timedelta(hours=12, seconds=60)


def test_fresh_session_is_not_expired() -> None:
    session = AuthSession.issue("user-1")
    assert session.is_expired(session.created_at) is False


def test_expiry_boundary_is_inclusive() -> None:
    session = AuthSession.issue("user-1", ttl_hours=1)
    assert session.is_expired(session.expires_at) is True
    just_before = session.expires_at - timedelta(seconds=1)
    assert session.is_expired(just_before) is False
