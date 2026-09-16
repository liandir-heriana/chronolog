"""TSK-007 RED: IAppointmentRepository port (domain, pure DIP).

Written BEFORE production code. Must FAIL on collection until
`src/modules/appointments/domain/repository_interfaces.py` exists.
"""

import inspect
from abc import ABC
from datetime import UTC, datetime, timedelta

from src.modules.appointments.domain.entities import Appointment
from src.modules.appointments.domain.repository_interfaces import (
    IAppointmentRepository,
)
from src.modules.appointments.domain.value_objects import AppointmentId


def _make_appointment(
    user_id: str,
    client_id: str,
    start_offset_h: int = 24,
    duration_h: int = 1,
) -> Appointment:
    now = datetime.now(UTC)
    starts_at = now + timedelta(hours=start_offset_h)
    ends_at = starts_at + timedelta(hours=duration_h)
    return Appointment.schedule(
        id=AppointmentId.generate(),
        user_id=user_id,
        client_id=client_id,
        starts_at=starts_at,
        ends_at=ends_at,
        now=now,
    )


class TestIAppointmentRepositoryContract:
    def test_is_abstract_base_class(self) -> None:
        assert issubclass(IAppointmentRepository, ABC)

    def test_cannot_instantiate_directly(self) -> None:
        try:
            IAppointmentRepository()  # type: ignore[abstract]
        except TypeError:
            return
        raise AssertionError("IAppointmentRepository must not be directly instantiable")

    def test_declares_required_abstract_methods(self) -> None:
        assert set(IAppointmentRepository.__abstractmethods__) == {
            "save",
            "find_by_id_and_user_id",
            "list_by_user_id",
            "list_by_client_and_user_id",
            "list_overlapping",
        }

    def test_every_read_method_requires_user_id(self) -> None:
        for method_name in (
            "find_by_id_and_user_id",
            "list_by_user_id",
            "list_by_client_and_user_id",
            "list_overlapping",
        ):
            params = inspect.signature(
                getattr(IAppointmentRepository, method_name)
            ).parameters
            assert "user_id" in params, f"{method_name} must require user_id"


class InMemoryAppointmentRepository(IAppointmentRepository):
    """Minimal fake proving the port supports scoped + overlap lookups."""

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


class TestIAppointmentRepositoryIsolation:
    def test_round_trip_and_user_id_isolation(self) -> None:
        repo: IAppointmentRepository = InMemoryAppointmentRepository()
        mine = _make_appointment("user-1", "client-1")
        other = _make_appointment("user-2", "client-1")
        repo.save(mine)
        repo.save(other)

        assert repo.find_by_id_and_user_id(mine.id, "user-1") == mine
        assert repo.find_by_id_and_user_id(mine.id, "user-2") is None
        assert repo.find_by_id_and_user_id(other.id, "user-1") is None

        assert repo.list_by_user_id("user-1") == [mine]
        assert repo.list_by_client_and_user_id("client-1", "user-1") == [mine]
        assert repo.list_by_client_and_user_id("client-1", "user-2") == [other]
        assert repo.list_by_client_and_user_id("client-9", "user-1") == []

    def test_overlap_lookup_is_scoped_by_user_id(self) -> None:
        repo: IAppointmentRepository = InMemoryAppointmentRepository()
        mine = _make_appointment("user-1", "client-1")
        repo.save(mine)
        repo.save(_make_appointment("user-2", "client-1"))

        overlapping = repo.list_overlapping(
            "user-1", mine.starts_at, mine.ends_at
        )
        assert overlapping == [mine]

        # Other user's window-identical appointment must not leak in.
        other_only = repo.list_overlapping(
            "user-9", mine.starts_at, mine.ends_at
        )
        assert other_only == []

        # Non-overlapping window returns nothing.
        far_future_start = mine.ends_at + timedelta(hours=5)
        far_future_end = far_future_start + timedelta(hours=1)
        assert (
            repo.list_overlapping("user-1", far_future_start, far_future_end) == []
        )

        # Excluded id (self-update case) returns nothing.
        assert (
            repo.list_overlapping(
                "user-1",
                mine.starts_at,
                mine.ends_at,
                exclude_appointment_id=mine.id,
            )
            == []
        )
