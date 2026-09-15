"""ChronoLog appointments value objects: AppointmentId, SessionNoteId (pure)."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from src.modules.appointments.domain.exceptions import AppointmentValidationError


def _coerced_uuid(raw: str, label: str) -> str:
    try:
        return str(UUID(raw))
    except (ValueError, AttributeError, TypeError) as exc:
        raise AppointmentValidationError(f"Invalid {label}: {raw!r}") from exc


@dataclass(frozen=True)
class AppointmentId:
    """Identity value object for an Appointment aggregate root."""

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _coerced_uuid(self.value, "appointment id"))

    @classmethod
    def generate(cls) -> AppointmentId:
        """Create a new random appointment id."""
        return cls(str(uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class SessionNoteId:
    """Identity value object for SessionNotes."""

    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", _coerced_uuid(self.value, "session note id"))

    @classmethod
    def generate(cls) -> SessionNoteId:
        """Create a new random session note id."""
        return cls(str(uuid4()))

    def __str__(self) -> str:
        return self.value
