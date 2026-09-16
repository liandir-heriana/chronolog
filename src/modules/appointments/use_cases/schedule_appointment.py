"""ChronoLog ScheduleAppointment use case (depends only on repository ports)."""

from __future__ import annotations

from datetime import datetime

from src.modules.appointments.domain.entities import Appointment
from src.modules.appointments.domain.exceptions import AppointmentValidationError
from src.modules.appointments.domain.repository_interfaces import (
    IAppointmentRepository,
)
from src.modules.appointments.domain.value_objects import AppointmentId
from src.modules.clients.domain.repository_interfaces import IClientRepository
from src.modules.clients.domain.value_objects import ClientId


class ScheduleAppointment:
    """Schedule a future appointment isolated by ``user_id``.

    Flow: verify the client exists AND belongs to ``user_id`` (IDOR
    prevention) -> validate the ``[starts_at, ends_at)`` window via
    ``Appointment.schedule`` (past / ends<=starts / naive rejected) ->
    reject overlaps via ``list_overlapping`` -> ``save`` and return.

    All failures raise :class:`AppointmentValidationError` (unified domain
    error; malformed ``client_id`` UUIDs surface as ``ClientValidationError``
    from the ``ClientId`` value object). Overlap uses the repository's
    half-open ``[starts_at, ends_at)`` semantics, so adjacent windows
    (``ends_at == starts_at``) are allowed and other users' appointments
    never block (query is scoped by ``user_id``).
    """

    def __init__(
        self,
        appointments: IAppointmentRepository,
        clients: IClientRepository,
    ) -> None:
        self._appointments = appointments
        self._clients = clients

    def execute(
        self,
        *,
        user_id: str,
        client_id: str,
        starts_at: datetime,
        ends_at: datetime,
        now: datetime,
    ) -> Appointment:
        """Create, persist, and return the scheduled appointment."""
        client = self._clients.find_by_id_and_user_id(ClientId(client_id), user_id)
        if client is None:
            raise AppointmentValidationError("Client not found for user")
        appointment = Appointment.schedule(
            id=AppointmentId.generate(),
            user_id=user_id,
            client_id=client.id.value,
            starts_at=starts_at,
            ends_at=ends_at,
            now=now,
        )
        if self._appointments.list_overlapping(user_id, starts_at, ends_at):
            raise AppointmentValidationError("Appointment overlaps an existing one")
        self._appointments.save(appointment)
        return appointment
