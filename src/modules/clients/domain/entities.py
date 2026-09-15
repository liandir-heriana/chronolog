"""ChronoLog Client aggregate root (pure domain, stdlib only)."""

from __future__ import annotations

from dataclasses import dataclass

from src.modules.clients.domain.exceptions import ClientValidationError
from src.modules.clients.domain.value_objects import ClientId, Email, Phone

_MAX_NAME_LEN = 100


def _validated_name(name: str) -> str:
    normalized = name.strip()
    if not normalized or len(normalized) > _MAX_NAME_LEN:
        raise ClientValidationError(f"Invalid client name: {name!r}")
    return normalized


def _validated_user_id(user_id: str) -> str:
    normalized = user_id.strip()
    if not normalized:
        raise ClientValidationError("Client owner user_id must not be empty")
    return normalized


@dataclass
class Client:
    """Client aggregate root owned by a single professional (`user_id`)."""

    id: ClientId
    user_id: str
    name: str
    email: Email
    phone: Phone | None = None

    def __post_init__(self) -> None:
        self.user_id = _validated_user_id(self.user_id)
        self.name = _validated_name(self.name)

    def update_contact(
        self,
        name: str | None = None,
        email: Email | None = None,
        phone: Phone | None = None,
        clear_phone: bool = False,
    ) -> None:
        """Update contact data, revalidating every invariant."""
        if name is not None:
            self.name = _validated_name(name)
        if email is not None:
            self.email = email
        if clear_phone:
            self.phone = None
        elif phone is not None:
            self.phone = phone
