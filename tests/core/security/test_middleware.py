"""TSK-016 RED: server-side session middleware (D3 GREEN target).

Written BEFORE production code — must FAIL on collection until
`src/core/security/middleware.py` exists with
`authenticate_request` / `enforce_user_authorization` and
`src/modules/auth/domain/repository_interfaces.py` gains `ISessionRepository`.

Contract (verify/task15_test.md §3.1): `authenticate_request(auth_header)`
-> `AuthenticatedUserContext(user_id, ...)`; every use-case call site passes
`ctx.user_id` (never a client-supplied id). All auth failures (missing,
malformed, unknown, expired) raise the generic `InvalidCredentialsError`.
"""

from datetime import UTC, datetime, timedelta

import pytest

from src.core.security.middleware import (
    AuthenticatedUserContext,
    authenticate_request,
    enforce_user_authorization,
)
from src.modules.auth.domain.entities import AuthSession
from src.modules.auth.domain.exceptions import InvalidCredentialsError
from src.modules.auth.domain.repository_interfaces import ISessionRepository
from src.modules.auth.domain.security import hash_token

NOW = datetime(2026, 9, 17, 9, 55, tzinfo=UTC)


class InMemorySessionRepository(ISessionRepository):
    """Test-only fake of the ISessionRepository port."""

    def __init__(self) -> None:
        self._by_hash: dict[str, AuthSession] = {}

    def save(self, session: AuthSession) -> None:
        self._by_hash[hash_token(session.token)] = session

    def find_by_token_hash(self, token_hash: str) -> AuthSession | None:
        return self._by_hash.get(token_hash)

    def delete_by_token_hash(self, token_hash: str) -> None:
        self._by_hash.pop(token_hash, None)

    def delete_expired(self, now: datetime) -> int:
        expired = [h for h, s in self._by_hash.items() if s.is_expired(now)]
        for h in expired:
            del self._by_hash[h]
        return len(expired)


def _stored(user_id: str = "user-1", ttl_hours: float = 12) -> tuple[str, ISessionRepository]:
    repo: ISessionRepository = InMemorySessionRepository()
    session = AuthSession.issue(user_id, ttl_hours=ttl_hours)
    repo.save(session)
    return session.token, repo


def test_authenticates_bearer_token() -> None:
    token, repo = _stored("user-1")
    ctx = authenticate_request(f"Bearer {token}", repo, now=NOW)
    assert isinstance(ctx, AuthenticatedUserContext)
    assert ctx.user_id == "user-1"


def test_authenticates_raw_token_without_bearer_prefix() -> None:
    token, repo = _stored("user-1")
    ctx = authenticate_request(token, repo, now=NOW)
    assert ctx.user_id == "user-1"


@pytest.mark.parametrize("header", [None, "", "   ", "Bearer ", "Bearer not-a-token"])
def test_unknown_or_missing_token_raises_generic_error(header: str | None) -> None:
    _, repo = _stored("user-1")
    with pytest.raises(InvalidCredentialsError) as exc_info:
        authenticate_request(header, repo, now=NOW)
    assert str(exc_info.value) == InvalidCredentialsError.GENERIC_MESSAGE


def test_expired_token_rejected_with_generic_error() -> None:
    # NOTE (TSK-017 drive-by): was wall-clock flaky — `issue()` stamps real
    # `now()`, but the check pinned fixed NOW=09:55, so once real time passed
    # ~10:55 the token no longer looked expired at NOW. Default (real) `now`
    # keeps the intent deterministic: a -1h TTL is always expired on arrival.
    token, repo = _stored("user-1", ttl_hours=-1)
    with pytest.raises(InvalidCredentialsError):
        authenticate_request(f"Bearer {token}", repo)


def test_token_expiring_between_issue_and_request_rejected() -> None:
    repo: ISessionRepository = InMemorySessionRepository()
    session = AuthSession(
        token="tok",
        user_id="user-1",
        created_at=NOW - timedelta(hours=13),
        expires_at=NOW - timedelta(hours=1),
    )
    repo.save(session)
    with pytest.raises(InvalidCredentialsError):
        authenticate_request("tok", repo, now=NOW)


def test_enforce_passes_on_owner_match() -> None:
    ctx = AuthenticatedUserContext(
        user_id="user-1", token_hash="h", expires_at=NOW + timedelta(hours=1)
    )
    enforce_user_authorization(ctx, "user-1")  # must not raise


def test_enforce_rejects_cross_user_target() -> None:
    ctx = AuthenticatedUserContext(
        user_id="user-1", token_hash="h", expires_at=NOW + timedelta(hours=1)
    )
    with pytest.raises(ValueError):
        enforce_user_authorization(ctx, "user-attacker")
