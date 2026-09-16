"""ChronoLog appointments repository port (pure domain, stdlib + domain only)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from src.modules.appointments.domain.entities import Appointment
from src.modules.appointments.domain.value_objects import AppointmentId


class IAppointmentRepository(ABC):
    """Persistence port for the Appointment aggregate root.

    Every read is scoped by ``user_id`` so a professional can only
    access their own appointments (IDOR prevention). ``save`` carries
    the owner inside ``appointment.user_id``.
    """

    @abstractmethod
    def save(self, appointment: Appointment) -> None:
        """Persist a new or updated appointment."""
        raise NotImplementedError

    @abstractmethod
    def find_by_id_and_user_id(
        self, appointment_id: AppointmentId, user_id: str
    ) -> Appointment | None:
        """Return the appointment owned by ``user_id``, or ``None``."""
        raise NotImplementedError

    @abstractmethod
    def list_by_user_id(self, user_id: str) -> list[Appointment]:
        """List all appointments owned by ``user_id``."""
        raise NotImplementedError

    @abstractmethod
    def list_by_client_and_user_id(
        self, client_id: str, user_id: str
    ) -> list[Appointment]:
        """List appointments of one client, scoped by ``user_id``."""
        raise NotImplementedError

    @abstractmethod
    def list_overlapping(
        self,
        user_id: str,
        starts_at: datetime,
        ends_at: datetime,
        exclude_appointment_id: AppointmentId | None = None,
    ) -> list[Appointment]:
        """List ``user_id`` appointments overlapping ``[starts_at, ends_at)``.

        ``exclude_appointment_id`` skips one id (self-update case).
        """
        raise NotImplementedError
