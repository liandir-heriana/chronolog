"""TSK-006 RED: Appointment + SessionNotes pure entities.

Business rules: no scheduling in the past, ends_at > starts_at,
session notes only attachable/editable once the appointment is completed.
Written BEFORE production code.
"""

from datetime import UTC, datetime, timedelta

import pytest

from src.modules.appointments.domain.entities import (
    Appointment,
    AppointmentStatus,
    SessionNotes,
)
from src.modules.appointments.domain.exceptions import AppointmentValidationError
from src.modules.appointments.domain.value_objects import AppointmentId, SessionNoteId

NOW = datetime(2026, 9, 15, 14, 50, tzinfo=UTC)


def _window(days: int = 1, hours: int = 1) -> tuple[datetime, datetime]:
    start = NOW + timedelta(days=days)
    return start, start + timedelta(hours=hours)


def _appointment(**over: object) -> Appointment:
    start, end = _window()
    kwargs: dict[str, object] = {
        "id": AppointmentId.generate(),
        "user_id": "user-1",
        "client_id": "client-1",
        "starts_at": start,
        "ends_at": end,
    }
    kwargs.update(over)
    return Appointment.schedule(**kwargs, now=NOW)  # type: ignore[arg-type]


class TestSchedule:
    def test_schedules_valid_appointment(self) -> None:
        appt = _appointment()
        assert appt.status is AppointmentStatus.SCHEDULED
        assert appt.user_id == "user-1"

    def test_rejects_start_in_the_past(self) -> None:
        past = NOW - timedelta(hours=1)
        with pytest.raises(AppointmentValidationError):
            _appointment(starts_at=past, ends_at=past + timedelta(hours=1))

    def test_rejects_end_not_after_start(self) -> None:
        start, _ = _window()
        with pytest.raises(AppointmentValidationError):
            _appointment(starts_at=start, ends_at=start)

    def test_rejects_naive_datetimes(self) -> None:
        naive = datetime(2026, 9, 16, 10, 0)  # noqa: DTZ001 - naive input is the test case
        with pytest.raises(AppointmentValidationError):
            _appointment(starts_at=naive, ends_at=naive + timedelta(hours=1))

    @pytest.mark.parametrize("field", ["user_id", "client_id"])
    def test_rejects_empty_owner_refs(self, field: str) -> None:
        with pytest.raises(AppointmentValidationError):
            _appointment(**{field: "   "})


class TestLifecycle:
    def test_complete_and_cancel(self) -> None:
        appt = _appointment()
        appt.complete()
        assert appt.status is AppointmentStatus.COMPLETED
        with pytest.raises(AppointmentValidationError):
            appt.complete()
        with pytest.raises(AppointmentValidationError):
            appt.cancel()

    def test_cancel_scheduled(self) -> None:
        appt = _appointment()
        appt.cancel()
        assert appt.status is AppointmentStatus.CANCELLED
        with pytest.raises(AppointmentValidationError):
            appt.cancel()


class TestSessionNotes:
    def test_notes_only_when_completed(self) -> None:
        appt = _appointment()
        with pytest.raises(AppointmentValidationError):
            appt.attach_notes("First impressions")
        appt.complete()
        notes = appt.attach_notes("  First session went well. ")
        assert isinstance(notes, SessionNotes)
        assert notes.content == "First session went well."
        assert notes.appointment_id == appt.id
        assert notes.user_id == appt.user_id

    @pytest.mark.parametrize("content", ["", "   ", "x" * 5001])
    def test_rejects_invalid_content(self, content: str) -> None:
        appt = _appointment()
        appt.complete()
        with pytest.raises(AppointmentValidationError):
            appt.attach_notes(content)

    def test_update_only_when_completed(self) -> None:
        appt = _appointment()
        appt.complete()
        notes = appt.attach_notes("v1")
        other = _appointment()
        other.complete()
        with pytest.raises(AppointmentValidationError):
            notes.update_content("v2", other)
        notes.update_content("  v2 refined ", appt)
        assert notes.content == "v2 refined"

    def test_ids(self) -> None:
        assert AppointmentId.generate() != AppointmentId.generate()
        assert SessionNoteId.generate() != SessionNoteId.generate()
        with pytest.raises(AppointmentValidationError):
            AppointmentId("nope")
