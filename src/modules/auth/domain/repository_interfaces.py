"""ChronoLog auth repository port (pure domain, stdlib + domain only)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from src.modules.auth.domain.entities import User
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
