"""ChronoLog Appointment aggregate root + SessionNotes (pure domain, stdlib only)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

from src.modules.appointments.domain.exceptions import AppointmentValidationError
from src.modules.appointments.domain.value_objects import (
    AppointmentId,
    SessionNoteId,
)

_MAX_CONTENT_LEN = 5000


class AppointmentStatus(str, Enum):
    """Lifecycle states of an appointment."""

    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


def _validated_ref(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise AppointmentValidationError(f"Appointment {label} must not be empty")
    return normalized


def _validated_window(
    starts_at: datetime, ends_at: datetime, now: datetime | None
) -> None:
    if starts_at.tzinfo is None or ends_at.tzinfo is None:
        raise AppointmentValidationError("Appointment datetimes must be timezone-aware")
    if ends_at <= starts_at:
        raise AppointmentValidationError("Appointment ends_at must be after starts_at")
    if now is not None:
        if now.tzinfo is None:
            raise AppointmentValidationError("Reference now must be timezone-aware")
        if starts_at < now:
            raise AppointmentValidationError("Appointment cannot be scheduled in the past")


def _validated_content(content: str) -> str:
    normalized = content.strip()
    if not normalized or len(normalized) > _MAX_CONTENT_LEN:
        raise AppointmentValidationError("Session notes content is invalid")
    return normalized


@dataclass
class SessionNotes:
    """Manual session summary bound to one completed appointment."""

    id: SessionNoteId
    appointment_id: AppointmentId
    user_id: str
    content: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        self.user_id = _validated_ref(self.user_id, "owner user_id")
        self.content = _validated_content(self.content)
        if self.created_at.tzinfo is None:
            raise AppointmentValidationError("Session notes created_at must be timezone-aware")

    def update_content(self, content: str, appointment: Appointment) -> None:
        """Edit notes only while bound to the same completed appointment."""
        if appointment.id != self.appointment_id:
            raise AppointmentValidationError("Notes belong to another appointment")
        if appointment.status is not AppointmentStatus.COMPLETED:
            raise AppointmentValidationError("Notes are editable only once completed")
        self.content = _validated_content(content)


@dataclass
class Appointment:
    """Appointment aggregate root owned by a single professional (`user_id`)."""

    id: AppointmentId
    user_id: str
    client_id: str
    starts_at: datetime
    ends_at: datetime
    status: AppointmentStatus = AppointmentStatus.SCHEDULED

    def __post_init__(self) -> None:
        self.user_id = _validated_ref(self.user_id, "owner user_id")
        self.client_id = _validated_ref(self.client_id, "client_id")
        _validated_window(self.starts_at, self.ends_at, None)

    @classmethod
    def schedule(
        cls,
        id: AppointmentId,
        user_id: str,
        client_id: str,
        starts_at: datetime,
        ends_at: datetime,
        *,
        now: datetime,
    ) -> Appointment:
        """Schedule a future appointment; `now` is explicit for testability."""
        _validated_ref(user_id, "owner user_id")
        _validated_ref(client_id, "client_id")
        _validated_window(starts_at, ends_at, now)
        return cls(
            id=id,
            user_id=user_id.strip(),
            client_id=client_id.strip(),
            starts_at=starts_at,
            ends_at=ends_at,
        )

    def complete(self) -> None:
        """Mark a scheduled appointment as completed."""
        if self.status is not AppointmentStatus.SCHEDULED:
            raise AppointmentValidationError("Only scheduled appointments can complete")
        self.status = AppointmentStatus.COMPLETED

    def cancel(self) -> None:
        """Cancel a scheduled appointment."""
        if self.status is not AppointmentStatus.SCHEDULED:
            raise AppointmentValidationError("Only scheduled appointments can cancel")
        self.status = AppointmentStatus.CANCELLED

    def attach_notes(self, content: str) -> SessionNotes:
        """Bind manual session notes; allowed only once completed."""
        if self.status is not AppointmentStatus.COMPLETED:
            raise AppointmentValidationError("Notes require a completed appointment")
        return SessionNotes(
            id=SessionNoteId.generate(),
            appointment_id=self.id,
            user_id=self.user_id,
            content=_validated_content(content),
        )
