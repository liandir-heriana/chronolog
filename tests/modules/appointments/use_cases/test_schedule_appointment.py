"""TSK-009 RED: ScheduleAppointment use case with user data isolation.

Depends only on the IAppointmentRepository + IClientRepository ports (DIP)
via in-memory fakes. Written BEFORE production code — must FAIL on
collection until `src/modules/appointments/use_cases/schedule_appointment.py`
exists.

Contracts under test:
- ScheduleAppointment(appointments, clients).execute(
    *, user_id, client_id, starts_at, ends_at, now) -> Appointment
- Window validated via Appointment.schedule (past / ends<=starts / naive rejected).
- Client must exist AND belong to user_id (IDOR prevention).
- Overlap via repo.list_overlapping(user_id, starts_at, ends_at);
  any hit raises AppointmentValidationError; adjacent windows allowed.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.modules.appointments.domain.entities import Appointment
from src.modules.appointments.domain.exceptions import AppointmentValidationError
from src.modules.appointments.domain.repository_interfaces import (
    IAppointmentRepository,
)
from src.modules.appointments.domain.value_objects import AppointmentId
from src.modules.appointments.use_cases.schedule_appointment import ScheduleAppointment
from src.modules.clients.domain.entities import Client
from src.modules.clients.domain.repository_interfaces import IClientRepository
from src.modules.clients.domain.value_objects import ClientId, Email

NOW = datetime(2026, 9, 16, 11, 17, tzinfo=UTC)


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
    """Test-only fake of the IAppointmentRepository port (half-open overlap)."""

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


def _make_client(user_id: str) -> Client:
    return Client(
        id=ClientId.generate(),
        user_id=user_id,
        name="Ada Lovelace",
        email=Email("ada@example.com"),
    )


def _repos_with_client(user_id: str = "user-1") -> tuple[
    InMemoryAppointmentRepository, InMemoryClientRepository, Client
]:
    appointments: InMemoryAppointmentRepository = InMemoryAppointmentRepository()
    clients: InMemoryClientRepository = InMemoryClientRepository()
    client = _make_client(user_id)
    clients.save(client)
    return appointments, clients, client


def _window(
    start_offset_h: int = 24, duration_h: int = 1
) -> tuple[datetime, datetime]:
    starts_at = NOW + timedelta(hours=start_offset_h)
    return starts_at, starts_at + timedelta(hours=duration_h)


class TestScheduleAppointmentSuccess:
    def test_schedules_and_persists_appointment(self) -> None:
        appointments, clients, client = _repos_with_client("user-1")
        use_case = ScheduleAppointment(appointments, clients)
        starts_at, ends_at = _window()

        result = use_case.execute(
            user_id="user-1",
            client_id=client.id.value,
            starts_at=starts_at,
            ends_at=ends_at,
            now=NOW,
        )

        assert isinstance(result, Appointment)
        assert result.user_id == "user-1"
        assert result.client_id == client.id.value
        assert result.starts_at == starts_at
        assert result.ends_at == ends_at
        stored = appointments.find_by_id_and_user_id(result.id, "user-1")
        assert stored == result


class TestScheduleAppointmentWindowValidation:
    def test_rejects_start_in_the_past(self) -> None:
        appointments, clients, client = _repos_with_client("user-1")
        use_case = ScheduleAppointment(appointments, clients)
        past = NOW - timedelta(hours=1)

        with pytest.raises(AppointmentValidationError):
            use_case.execute(
                user_id="user-1",
                client_id=client.id.value,
                starts_at=past,
                ends_at=past + timedelta(hours=1),
                now=NOW,
            )
        assert appointments.list_by_user_id("user-1") == []

    def test_rejects_end_not_after_start(self) -> None:
        appointments, clients, client = _repos_with_client("user-1")
        use_case = ScheduleAppointment(appointments, clients)
        starts_at, _ = _window()

        with pytest.raises(AppointmentValidationError):
            use_case.execute(
                user_id="user-1",
                client_id=client.id.value,
                starts_at=starts_at,
                ends_at=starts_at,
                now=NOW,
            )
        assert appointments.list_by_user_id("user-1") == []

    def test_rejects_naive_datetimes(self) -> None:
        appointments, clients, client = _repos_with_client("user-1")
        use_case = ScheduleAppointment(appointments, clients)
        naive_start = datetime(2026, 9, 17, 10, 0)  # noqa: DTZ001 - naive is the case
        naive_end = datetime(2026, 9, 17, 11, 0)  # noqa: DTZ001 - naive is the case

        with pytest.raises(AppointmentValidationError):
            use_case.execute(
                user_id="user-1",
                client_id=client.id.value,
                starts_at=naive_start,
                ends_at=naive_end,
                now=NOW,
            )
        assert appointments.list_by_user_id("user-1") == []


class TestScheduleAppointmentClientOwnership:
    def test_rejects_unknown_client(self) -> None:
        appointments, clients, _ = _repos_with_client("user-1")
        use_case = ScheduleAppointment(appointments, clients)
        starts_at, ends_at = _window()

        with pytest.raises(AppointmentValidationError):
            use_case.execute(
                user_id="user-1",
                client_id=ClientId.generate().value,
                starts_at=starts_at,
                ends_at=ends_at,
                now=NOW,
            )
        assert appointments.list_by_user_id("user-1") == []

    def test_rejects_other_users_client_idor(self) -> None:
        appointments, clients, client = _repos_with_client("user-owner")
        use_case = ScheduleAppointment(appointments, clients)
        starts_at, ends_at = _window()

        with pytest.raises(AppointmentValidationError):
            use_case.execute(
                user_id="user-attacker",
                client_id=client.id.value,
                starts_at=starts_at,
                ends_at=ends_at,
                now=NOW,
            )
        assert appointments.list_by_user_id("user-attacker") == []
        assert appointments.list_by_user_id("user-owner") == []


class TestScheduleAppointmentOverlap:
    def _seed(
        self,
        appointments: InMemoryAppointmentRepository,
        clients: InMemoryClientRepository,
        client: Client,
    ) -> tuple[datetime, datetime]:
        base_start, base_end = _window(start_offset_h=48)
        existing = Appointment.schedule(
            id=AppointmentId.generate(),
            user_id="user-1",
            client_id=client.id.value,
            starts_at=base_start,
            ends_at=base_end,
            now=NOW,
        )
        appointments.save(existing)
        return base_start, base_end

    def test_rejects_overlapping_same_user(self) -> None:
        appointments, clients, client = _repos_with_client("user-1")
        base_start, base_end = self._seed(appointments, clients, client)
        use_case = ScheduleAppointment(appointments, clients)

        with pytest.raises(AppointmentValidationError):
            use_case.execute(
                user_id="user-1",
                client_id=client.id.value,
                starts_at=base_start + timedelta(minutes=30),
                ends_at=base_end + timedelta(hours=1),
                now=NOW,
            )
        assert len(appointments.list_by_user_id("user-1")) == 1

    def test_allows_adjacent_window(self) -> None:
        appointments, clients, client = _repos_with_client("user-1")
        base_start, base_end = self._seed(appointments, clients, client)
        use_case = ScheduleAppointment(appointments, clients)

        result = use_case.execute(
            user_id="user-1",
            client_id=client.id.value,
            starts_at=base_end,
            ends_at=base_end + timedelta(hours=1),
            now=NOW,
        )

        assert result.starts_at == base_end
        assert len(appointments.list_by_user_id("user-1")) == 2
        _ = base_start

    def test_other_users_overlap_does_not_block(self) -> None:
        appointments, clients, client = _repos_with_client("user-1")
        base_start, base_end = self._seed(appointments, clients, client)
        other_client = _make_client("user-2")
        clients.save(other_client)
        use_case = ScheduleAppointment(appointments, clients)

        result = use_case.execute(
            user_id="user-2",
            client_id=other_client.id.value,
            starts_at=base_start,
            ends_at=base_end,
            now=NOW,
        )

        assert result.user_id == "user-2"
        assert appointments.find_by_id_and_user_id(result.id, "user-2") == result
