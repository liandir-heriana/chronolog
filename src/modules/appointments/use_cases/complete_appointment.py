"""ChronoLog CompleteAppointment use case (depends only on repository port)."""

from __future__ import annotations

from src.modules.appointments.domain.entities import Appointment
from src.modules.appointments.domain.exceptions import AppointmentValidationError
from src.modules.appointments.domain.repository_interfaces import (
    IAppointmentRepository,
)
from src.modules.appointments.domain.value_objects import AppointmentId


class CompleteAppointment:
    """Complete a scheduled appointment and link manual session notes.

    Flow: load via ``find_by_id_and_user_id`` (unknown id AND foreign
    appointment raise the same ``AppointmentValidationError``, no oracle)
    -> ``appointment.complete()`` (already-completed/cancelled rejected by
    the domain) -> ``appointment.attach_notes(content)`` (empty/blank/
    overlong rejected, bound to the same completed appointment/user) ->
    ``save`` the aggregate and return it.

    Notes persist with the aggregate via ``save`` (no ``save_session_notes``
    port method); the ``SessionNotes`` created by ``attach_notes`` carries
    the validated, bound content for the infrastructure adapter.
    """

    def __init__(self, appointments: IAppointmentRepository) -> None:
        self._appointments = appointments

    def execute(
        self,
        *,
        appointment_id: str,
        user_id: str,
        content: str,
    ) -> Appointment:
        """Mark completed, validate notes, persist, and return the appointment."""
        appointment = self._appointments.find_by_id_and_user_id(
            AppointmentId(appointment_id), user_id
        )
        if appointment is None:
            raise AppointmentValidationError("Appointment not found for user")
        appointment.complete()
        appointment.attach_notes(content)
        self._appointments.save(appointment)
        return appointment
