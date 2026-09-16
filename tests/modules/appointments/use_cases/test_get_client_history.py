"""TSK-011 RED: GetClientHistory use case (client profile + chronological history).

Depends only on the IClientRepository + IAppointmentRepository ports (DIP)
via in-memory fakes. Written BEFORE production code — must FAIL on
collection until `src/modules/appointments/use_cases/get_client_history.py`
exists.

Contracts under test:
- GetClientHistory(clients, appointments).execute(*, user_id, client_id)
  -> ClientHistory (frozen read model: client + appointments ascending).
- AuthZ via clients.find_by_id_and_user_id (unknown id AND foreign client
  surface as the same AppointmentValidationError, no oracle).
- History via appointments.list_by_client_and_user_id(client_id, user_id),
  sorted ascending by starts_at (chronological).
- Notes travel attached to completed appointments via the aggregate
  (T10-D1, no separate notes lookup): a COMPLETED appointment can still
  attach_notes with bound content/user.
- Zero appointments -> empty tuple (not error); other users' appointments
  never leak (query scoped by user_id).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.modules.appointments.domain.entities import Appointment, AppointmentStatus
from src.modules.appointments.domain.exceptions import AppointmentValidationError
from src.modules.appointments.domain.repository_interfaces import (
    IAppointmentRepository,
)
from src.modules.appointments.domain.value_objects import AppointmentId
from src.modules.appointments.use_cases.get_client_history import GetClientHistory
from src.modules.clients.domain.entities import Client
from src.modules.clients.domain.repository_interfaces import IClientRepository
from src.modules.clients.domain.value_objects import ClientId, Email

NOW = datetime(2026, 9, 16, 11, 46, tzinfo=UTC)


class InMemoryClientRepository(IClientRepository):
    """Test-only fake of the IClientRepository port."""

    def __init__(self) -> None:
        self._store: dict[str, Client] = {}

    def save(self, client: Client) -> None:
        self._store[f"{client.user_id}:{client.id.value}"] = client

    def find_by_id_and_user_id(
        self, client_id: ClientId, user_id: str
    ) -> Client | None:
        return self._store.get(f"{user_id}:{client_id.value}")

    def list_by_user_id(self, user_id: str) -> list[Client]:
        return [c for c in self._store.values() if c.user_id == user_id]


class InMemoryAppointmentRepository(IAppointmentRepository):
    """Test-only fake of the IAppointmentRepository port."""

    def __init__(self) -> None:
        self._store: dict[str, Appointment] = {}

    def save(self, appointment: Appointment) -> None:
        self._store[f"{appointment.user_id}:{appointment.id.value}"] = appointment

    def find_by_id_and_user_id(
        self, appointment_id: AppointmentId, user_id: str
    ) -> Appointment | None:
        return self._store.get(f"{user_id}:{appointment_id.value}")

    def list_by_user_id(self, user_id: str) -> list[Appointment]:
        return [a for a in self._store.values() if a.user_id == user_id]

    def list_by_client_and_user_id(
        self, client_id: str, user_id: str
    ) -> list[Appointment]:
        return [
            a
            for a in self._store.values()
            if a.user_id == user_id and a.client_id == client_id
        ]

    def list_overlapping(
        self,
        user_id: str,
        starts_at: datetime,
        ends_at: datetime,
        exclude_appointment_id: AppointmentId | None = None,
    ) -> list[Appointment]:
        result: list[Appointment] = []
        for appt in self._store.values():
            if appt.user_id != user_id:
                continue
            if (
                exclude_appointment_id is not None
                and appt.id == exclude_appointment_id
            ):
                continue
            if appt.starts_at < ends_at and starts_at < appt.ends_at:
                result.append(appt)
        return result


def _make_client(user_id: str = "user-1") -> Client:
    return Client(
        id=ClientId.generate(),
        user_id=user_id,
        name="Ada Lovelace",
        email=Email("ada@example.com"),
    )


def _past_window(days_ago: int, duration_h: int = 1) -> tuple[datetime, datetime]:
    starts_at = NOW - timedelta(days=days_ago)
    return starts_at, starts_at + timedelta(hours=duration_h)


def _seed_past(
    appointments: InMemoryAppointmentRepository,
    *,
    user_id: str,
    client_id: str,
    days_ago: int,
    completed_with_notes: str | None = None,
) -> Appointment:
    starts_at, ends_at = _past_window(days_ago)
    appt = Appointment(
        id=AppointmentId.generate(),
        user_id=user_id,
        client_id=client_id,
        starts_at=starts_at,
        ends_at=ends_at,
    )
    if completed_with_notes is not None:
        appt.complete()
        # Notes travel with the aggregate (T10-D1): attaching must succeed
        # and stay bound to the same appointment/user.
        notes = appt.attach_notes(completed_with_notes)
        assert notes.appointment_id == appt.id
        assert notes.user_id == user_id
        assert notes.content == completed_with_notes.strip()
    appointments.save(appt)
    return appt


def _repos_with_client(
    user_id: str = "user-1",
) -> tuple[InMemoryAppointmentRepository, InMemoryClientRepository, Client]:
    appointments: InMemoryAppointmentRepository = InMemoryAppointmentRepository()
    clients: InMemoryClientRepository = InMemoryClientRepository()
    client = _make_client(user_id)
    clients.save(client)
    return appointments, clients, client


class TestGetClientHistorySuccess:
    def test_returns_profile_plus_chronological_appointments_with_notes(self) -> None:
        appointments, clients, client = _repos_with_client("user-1")
        first = _seed_past(
            appointments,
            user_id="user-1",
            client_id=client.id.value,
            days_ago=2,
            completed_with_notes="  First session went well. ",
        )
        second = _seed_past(
            appointments,
            user_id="user-1",
            client_id=client.id.value,
            days_ago=1,
        )
        use_case = GetClientHistory(clients, appointments)

        result = use_case.execute(user_id="user-1", client_id=client.id.value)

        assert result.client == client
        assert result.client.id == client.id
        assert [a.id for a in result.appointments] == [first.id, second.id]
        assert result.appointments[0].starts_at < result.appointments[1].starts_at
        assert result.appointments[0].status is AppointmentStatus.COMPLETED
        # Notes still attachable on the completed appointment (bound content).
        notes = result.appointments[0].attach_notes("First session went well.")
        assert notes.appointment_id == first.id
        assert notes.user_id == "user-1"
        assert notes.content == "First session went well."


class TestGetClientHistoryIdor:
    def test_unknown_client_rejected(self) -> None:
        appointments, clients, _ = _repos_with_client("user-1")
        use_case = GetClientHistory(clients, appointments)

        with pytest.raises(AppointmentValidationError):
            use_case.execute(
                user_id="user-1", client_id=ClientId.generate().value
            )

    def test_foreign_client_rejected_same_error_no_oracle(self) -> None:
        appointments, clients, owned = _repos_with_client("user-owner")
        use_case = GetClientHistory(clients, appointments)

        with pytest.raises(AppointmentValidationError) as foreign_exc:
            use_case.execute(user_id="user-attacker", client_id=owned.id.value)
        with pytest.raises(AppointmentValidationError) as unknown_exc:
            use_case.execute(
                user_id="user-attacker", client_id=ClientId.generate().value
            )
        assert str(foreign_exc.value) == str(unknown_exc.value)


class TestGetClientHistoryEmpty:
    def test_client_with_zero_appointments_returns_empty(self) -> None:
        appointments, clients, client = _repos_with_client("user-1")
        use_case = GetClientHistory(clients, appointments)

        result = use_case.execute(user_id="user-1", client_id=client.id.value)

        assert result.client == client
        assert list(result.appointments) == []


class TestGetClientHistoryIsolation:
    def test_other_users_appointments_never_leak(self) -> None:
        appointments, clients, client = _repos_with_client("user-1")
        mine = _seed_past(
            appointments,
            user_id="user-1",
            client_id=client.id.value,
            days_ago=2,
        )
        # Same client_id string but owned by another user must stay invisible.
        _seed_past(
            appointments,
            user_id="user-2",
            client_id=client.id.value,
            days_ago=1,
        )
        use_case = GetClientHistory(clients, appointments)

        result = use_case.execute(user_id="user-1", client_id=client.id.value)

        assert [a.id for a in result.appointments] == [mine.id]
        assert all(a.user_id == "user-1" for a in result.appointments)


class TestGetClientHistoryOrdering:
    def test_unsorted_seed_still_returned_sorted_ascending(self) -> None:
        appointments, clients, client = _repos_with_client("user-1")
        newest = _seed_past(
            appointments, user_id="user-1", client_id=client.id.value, days_ago=1
        )
        oldest = _seed_past(
            appointments, user_id="user-1", client_id=client.id.value, days_ago=3
        )
        middle = _seed_past(
            appointments, user_id="user-1", client_id=client.id.value, days_ago=2
        )
        use_case = GetClientHistory(clients, appointments)

        result = use_case.execute(user_id="user-1", client_id=client.id.value)

        assert [a.id for a in result.appointments] == [
            oldest.id,
            middle.id,
            newest.id,
        ]
        starts = [a.starts_at for a in result.appointments]
        assert starts == sorted(starts)
