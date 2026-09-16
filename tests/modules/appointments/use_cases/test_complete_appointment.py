"""TSK-010 RED: CompleteAppointment use case with session notes.

Depends only on the IAppointmentRepository port (DIP) via an in-memory
fake. Written BEFORE production code — must FAIL on collection until
`src/modules/appointments/use_cases/complete_appointment.py` exists.

Contracts under test:
- CompleteAppointment(repo).execute(
    *, appointment_id, user_id, content) -> Appointment
- AuthZ via repo.find_by_id_and_user_id (unknown id AND foreign
  appointment surface as the same AppointmentValidationError, no oracle).
- Lifecycle via Appointment.complete (already-completed/cancelled rejected).
- Notes via Appointment.attach_notes (empty/blank/overlong rejected,
  bound to the same completed appointment/user).
- Persistence via repo.save(appointment) (aggregate save, no
  save_session_notes port method per T10-D1).
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta

import pytest

from src.modules.appointments.domain.entities import (
    Appointment,
    AppointmentStatus,
)
from src.modules.appointments.domain.exceptions import AppointmentValidationError
from src.modules.appointments.domain.repository_interfaces import (
    IAppointmentRepository,
)
from src.modules.appointments.domain.value_objects import AppointmentId
from src.modules.appointments.use_cases.complete_appointment import (
    CompleteAppointment,
)

NOW = datetime(2026, 9, 16, 11, 30, tzinfo=UTC)


class InMemoryAppointmentRepository(IAppointmentRepository):
    """Test-only fake of the IAppointmentRepository port.

    Copies on save/find/list so a fetched aggregate can be mutated
    without leaking into stored state before save (faithful to a real
    persistence adapter).
    """

    def __init__(self) -> None:
        self._store: dict[str, Appointment] = {}

    def save(self, appointment: Appointment) -> None:
        self._store[f"{appointment.user_id}:{appointment.id.value}"] = copy.copy(
            appointment
        )

    def find_by_id_and_user_id(
        self, appointment_id: AppointmentId, user_id: str
    ) -> Appointment | None:
        stored = self._store.get(f"{user_id}:{appointment_id.value}")
        return copy.copy(stored) if stored is not None else None

    def list_by_user_id(self, user_id: str) -> list[Appointment]:
        return [copy.copy(a) for a in self._store.values() if a.user_id == user_id]

    def list_by_client_and_user_id(
        self, client_id: str, user_id: str
    ) -> list[Appointment]:
        return [
            copy.copy(a)
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
                result.append(copy.copy(appt))
        return result


def _window(
    start_offset_h: int = 24, duration_h: int = 1
) -> tuple[datetime, datetime]:
    starts_at = NOW + timedelta(hours=start_offset_h)
    return starts_at, starts_at + timedelta(hours=duration_h)


def _scheduled(user_id: str = "user-1") -> Appointment:
    starts_at, ends_at = _window()
    return Appointment.schedule(
        id=AppointmentId.generate(),
        user_id=user_id,
        client_id="client-1",
        starts_at=starts_at,
        ends_at=ends_at,
        now=NOW,
    )


def _seed(repo: InMemoryAppointmentRepository, appt: Appointment) -> Appointment:
    repo.save(appt)
    return appt


class TestCompleteAppointmentSuccess:
    def test_completes_and_links_notes(self) -> None:
        repo = InMemoryAppointmentRepository()
        appt = _seed(repo, _scheduled("user-1"))
        use_case = CompleteAppointment(repo)

        result = use_case.execute(
            appointment_id=appt.id.value,
            user_id="user-1",
            content="  First session went well. ",
        )

        assert isinstance(result, Appointment)
        assert result.id == appt.id
        assert result.user_id == "user-1"
        assert result.status is AppointmentStatus.COMPLETED
        stored = repo.find_by_id_and_user_id(appt.id, "user-1")
        assert stored is not None
        assert stored.status is AppointmentStatus.COMPLETED

    def test_notes_bound_to_appointment_and_user(self) -> None:
        repo = InMemoryAppointmentRepository()
        appt = _seed(repo, _scheduled("user-1"))
        use_case = CompleteAppointment(repo)

        result = use_case.execute(
            appointment_id=appt.id.value,
            user_id="user-1",
            content="Progress noted.",
        )

        notes = result.attach_notes("Progress noted.")
        assert notes.appointment_id == appt.id
        assert notes.user_id == "user-1"
        assert notes.content == "Progress noted."


class TestCompleteAppointmentIdor:
    def test_unknown_id_rejected(self) -> None:
        repo = InMemoryAppointmentRepository()
        use_case = CompleteAppointment(repo)

        with pytest.raises(AppointmentValidationError):
            use_case.execute(
                appointment_id=AppointmentId.generate().value,
                user_id="user-1",
                content="Notes.",
            )

    def test_foreign_appointment_rejected_same_error(self) -> None:
        repo = InMemoryAppointmentRepository()
        appt = _seed(repo, _scheduled("user-owner"))
        use_case = CompleteAppointment(repo)

        with pytest.raises(AppointmentValidationError) as foreign_exc:
            use_case.execute(
                appointment_id=appt.id.value,
                user_id="user-attacker",
                content="Unauthorized note.",
            )
        with pytest.raises(AppointmentValidationError) as unknown_exc:
            use_case.execute(
                appointment_id=AppointmentId.generate().value,
                user_id="user-attacker",
                content="Unauthorized note.",
            )
        assert str(foreign_exc.value) == str(unknown_exc.value)
        assert repo.list_by_user_id("user-attacker") == []
        stored = repo.find_by_id_and_user_id(appt.id, "user-owner")
        assert stored is not None
        assert stored.status is AppointmentStatus.SCHEDULED


class TestCompleteAppointmentLifecycle:
    def test_already_completed_rejected(self) -> None:
        repo = InMemoryAppointmentRepository()
        appt = _scheduled("user-1")
        appt.complete()
        _seed(repo, appt)
        use_case = CompleteAppointment(repo)

        with pytest.raises(AppointmentValidationError):
            use_case.execute(
                appointment_id=appt.id.value,
                user_id="user-1",
                content="More notes.",
            )

    def test_cancelled_rejected(self) -> None:
        repo = InMemoryAppointmentRepository()
        appt = _scheduled("user-1")
        appt.cancel()
        _seed(repo, appt)
        use_case = CompleteAppointment(repo)

        with pytest.raises(AppointmentValidationError):
            use_case.execute(
                appointment_id=appt.id.value,
                user_id="user-1",
                content="Late notes.",
            )
        stored = repo.find_by_id_and_user_id(appt.id, "user-1")
        assert stored is not None
        assert stored.status is AppointmentStatus.CANCELLED


class TestCompleteAppointmentNotesValidation:
    @pytest.mark.parametrize("content", ["", "   "])
    def test_rejects_empty_or_blank_notes(self, content: str) -> None:
        repo = InMemoryAppointmentRepository()
        appt = _seed(repo, _scheduled("user-1"))
        use_case = CompleteAppointment(repo)

        with pytest.raises(AppointmentValidationError):
            use_case.execute(
                appointment_id=appt.id.value,
                user_id="user-1",
                content=content,
            )
        stored = repo.find_by_id_and_user_id(appt.id, "user-1")
        assert stored is not None
        assert stored.status is AppointmentStatus.SCHEDULED

    def test_rejects_overlong_notes(self) -> None:
        repo = InMemoryAppointmentRepository()
        appt = _seed(repo, _scheduled("user-1"))
        use_case = CompleteAppointment(repo)

        with pytest.raises(AppointmentValidationError):
            use_case.execute(
                appointment_id=appt.id.value,
                user_id="user-1",
                content="x" * 5001,
            )
        stored = repo.find_by_id_and_user_id(appt.id, "user-1")
        assert stored is not None
        assert stored.status is AppointmentStatus.SCHEDULED

    def test_rejects_malformed_appointment_id(self) -> None:
        repo = InMemoryAppointmentRepository()
        use_case = CompleteAppointment(repo)

        with pytest.raises(AppointmentValidationError):
            use_case.execute(
                appointment_id="nope",
                user_id="user-1",
                content="Notes.",
            )
