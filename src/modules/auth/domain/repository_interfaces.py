"""ChronoLog auth repository port (pure domain, stdlib + domain only)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from src.modules.auth.domain.entities import AuthSession, User
from src.modules.auth.domain.value_objects import UserEmail


class IUserRepository(ABC):
    """Persistence port for the User aggregate root.

    Note on AuthZ scoping: lookups are keyed by email because registration
    and login run *before* a `user_id` exists. Once created, ``user.id``
    becomes the `user_id` that scopes every read in the clients and
    appointments ports (IDOR prevention downstream).
    """

    @abstractmethod
    def save(self, user: User) -> None:
        """Persist a new or updated user."""
        raise NotImplementedError

    @abstractmethod
    def find_by_email(self, email: UserEmail) -> User | None:
        """Return the user with ``email``, or ``None``."""
        raise NotImplementedError


class ISessionRepository(ABC):
    """Persistence port for opaque login sessions (TSK-016 D3).

    Stores ``sha256(token)`` (``token_hash`` PK), never the raw bearer
    token. The middleware resolves a presented token via
    ``find_by_token_hash(hash_token(token))`` and rejects expired rows;
    ``delete_by_token_hash`` implements logout and ``delete_expired``
    is the janitor. All methods are tenant-neutral by design (the token
    hash IS the lookup key); downstream isolation uses the returned
    ``session.user_id`` as `user_id`.
    """

    @abstractmethod
    def save(self, session: AuthSession) -> None:
        """Persist a session (upsert on ``token_hash``)."""
        raise NotImplementedError

    @abstractmethod
    def find_by_token_hash(self, token_hash: str) -> AuthSession | None:
        """Return the session for ``token_hash``, or ``None``."""
        raise NotImplementedError

    @abstractmethod
    def delete_by_token_hash(self, token_hash: str) -> None:
        """Delete one session (logout); missing hashes are a no-op."""
        raise NotImplementedError

    @abstractmethod
    def delete_expired(self, now: datetime) -> int:
        """Delete sessions with ``expires_at <= now``; return the count."""
        raise NotImplementedError
