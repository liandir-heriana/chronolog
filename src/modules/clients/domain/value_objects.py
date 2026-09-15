"""ChronoLog clients value objects: ClientId, Email, Phone (pure, stdlib only)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from src.modules.clients.domain.exceptions import ClientValidationError

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
_PHONE_CLEAN_RE = re.compile(r"[\s\-().]+")
_PHONE_RE = re.compile(r"^\+?\d{7,15}$")
_MAX_EMAIL_LEN = 254


@dataclass(frozen=True)
class ClientId:
    """Identity value object for a Client aggregate root."""

    value: str

    def __post_init__(self) -> None:
        try:
            normalized = str(UUID(self.value))
        except (ValueError, AttributeError, TypeError) as exc:
            raise ClientValidationError(f"Invalid client id: {self.value!r}") from exc
        object.__setattr__(self, "value", normalized)

    @classmethod
    def generate(cls) -> ClientId:
        """Create a new random client id."""
        return cls(str(uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Email:
    """Validated, normalized email address value object."""

    value: str

    def __post_init__(self) -> None:
        normalized = self.value.strip().lower()
        if (
            not normalized
            or len(normalized) > _MAX_EMAIL_LEN
            or " " in normalized
            or _EMAIL_RE.match(normalized) is None
        ):
            raise ClientValidationError(f"Invalid email: {self.value!r}")
        object.__setattr__(self, "value", normalized)


@dataclass(frozen=True)
class Phone:
    """Validated, normalized phone number value object (digits, optional leading +)."""

    value: str

    def __post_init__(self) -> None:
        normalized = _PHONE_CLEAN_RE.sub("", self.value.strip())
        if _PHONE_RE.match(normalized) is None:
            raise ClientValidationError(f"Invalid phone: {self.value!r}")
        object.__setattr__(self, "value", normalized)
