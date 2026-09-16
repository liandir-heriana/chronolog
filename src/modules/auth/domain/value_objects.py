"""ChronoLog auth value objects: UserId, UserEmail (pure, stdlib only)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from src.modules.auth.domain.exceptions import UserValidationError

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
_MAX_EMAIL_LEN = 254


@dataclass(frozen=True)
class UserId:
    """Identity value object for a User; doubles as the AuthZ `user_id`."""

    value: str

    def __post_init__(self) -> None:
        try:
            normalized = str(UUID(self.value))
        except (ValueError, AttributeError, TypeError) as exc:
            raise UserValidationError(f"Invalid user id: {self.value!r}") from exc
        object.__setattr__(self, "value", normalized)

    @classmethod
    def generate(cls) -> UserId:
        """Create a new random user id."""
        return cls(str(uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class UserEmail:
    """Validated, normalized account email (auth-owned, never plaintext secret)."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()
        if (
            not normalized
            or len(normalized) > _MAX_EMAIL_LEN
            or " " in normalized
            or _EMAIL_RE.match(normalized) is None
        ):
            raise UserValidationError(f"Invalid email: {self.value!r}")
        object.__setattr__(self, "value", normalized)
