"""ChronoLog GetClientHistory use case (depends only on repository ports)."""

from __future__ import annotations

from dataclasses import dataclass

from src.modules.appointments.domain.entities import Appointment
from src.modules.appointments.domain.exceptions import AppointmentValidationError
from src.modules.appointments.domain.repository_interfaces import (
    IAppointmentRepository,
)
from src.modules.clients.domain.entities import Client
from src.modules.clients.domain.repository_interfaces import IClientRepository
from src.modules.clients.domain.value_objects import ClientId


@dataclass(frozen=True)
class ClientHistory:
    """Read model for a client profile plus chronological appointments.

    Kept in ``use_cases`` (not ``domain/``) so the pure domain stays free of
    application read shapes, and kept minimal (no DTO layer in MVP): the
    profile is the ``Client`` entity and history items are ``Appointment``
    entities sorted ascending by ``starts_at``. Session notes travel with
    the aggregate via ``Appointment.attach_notes`` (no separate notes
    lookup), so a ``COMPLETED`` appointment in ``appointments`` proves its
    notes can attach with bound content/user.
    """

    client: Client
    appointments: tuple[Appointment, ...]


class GetClientHistory:
    """Compile a client profile plus past chronological appointments.

    Flow: coerce ``ClientId`` (malformed UUIDs surface the VO's
    ``ClientValidationError``, honest shape error) -> load the client via
    ``find_by_id_and_user_id`` (unknown id AND foreign client raise the same
    ``AppointmentValidationError``, no oracle) -> list via
    ``list_by_client_and_user_id`` scoped by ``user_id`` (other users'
    appointments never leak) -> sort ascending by ``starts_at`` and return
    a frozen ``ClientHistory`` (empty tuple when zero appointments, not an
    error).
    """

    def __init__(
        self,
        clients: IClientRepository,
        appointments: IAppointmentRepository,
    ) -> None:
        self._clients = clients
        self._appointments = appointments

    def execute(self, *, user_id: str, client_id: str) -> ClientHistory:
        """Return the owned client profile with chronological appointments."""
        identity = ClientId(client_id)
        client = self._clients.find_by_id_and_user_id(identity, user_id)
        if client is None:
            raise AppointmentValidationError("Client not found for user")
        history = self._appointments.list_by_client_and_user_id(
            client.id.value, user_id
        )
        ordered = tuple(sorted(history, key=lambda appt: appt.starts_at))
        return ClientHistory(client=client, appointments=ordered)
