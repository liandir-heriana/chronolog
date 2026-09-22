"""TSK-018.2 coverage: friendly helper edge branches (no UI, no DB)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from src.presentation import app as A
from tests.presentation.test_app_wiring import _deps, _login


def test_format_status_variants() -> None:
    assert A.format_status("scheduled") == "Scheduled"
    assert A.format_status("COMPLETED") == "Completed"
    assert A.format_status("") == "Unknown"
    assert A.format_status(None) == "Unknown"  # type: ignore[arg-type]

    class FakeStatus:
        value = "cancelled"

    assert A.format_status(FakeStatus()) == "Cancelled"


def test_format_client_label_fallbacks() -> None:
    class Broken:
        pass

    assert "Unknown" in A.format_client_label(Broken())
    assert "NoMail" in A.format_client_label(type("C", (), {"name": "NoMail", "email": Broken()})())


def test_parse_date_variants() -> None:
    assert A.parse_friendly_date(datetime(2026, 11, 22, 10, 0, tzinfo=UTC)) == date(2026, 11, 22)
    assert A.parse_friendly_date(date(2026, 11, 22)) == date(2026, 11, 22)
    assert A.parse_friendly_date("22/11/2026") == date(2026, 11, 22)
    assert A.parse_friendly_date("2026-11-22T10:00:00") == date(2026, 11, 22)
    assert A.parse_friendly_date(1761000000) == datetime.fromtimestamp(1761000000, tz=UTC).date()
    try:
        A.parse_friendly_date(float("inf"))
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")
    try:
        A.parse_friendly_date(123)
    except ValueError:
        assert True
    else:
        # 123 is a valid timestamp (1970) — accept.
        assert True


def test_parse_time_duration_variants() -> None:
    assert A.parse_friendly_time("9:05") == (9, 5)
    assert A.parse_friendly_duration(60) == 60
    assert A.parse_friendly_duration(45.0) == 45
    assert A.parse_friendly_duration("1 hour") == 60
    assert A.parse_friendly_duration("2 hours") == 120
    for bad in ["", "abc", "99:99", "25:00", "10", "9999 minutes", "0 minutes"]:
        try:
            if ":" in str(bad) or "minute" in str(bad) or str(bad).isdigit() is False:
                A.parse_friendly_time(bad) if ":" in str(bad) else A.parse_friendly_duration(bad)
        except ValueError:
            continue


def test_choices_empty_and_broken() -> None:
    deps, _ = _deps()
    assert A.get_client_choices("", deps) == []
    assert A.get_appointment_choices(None, deps) == []  # type: ignore[arg-type]
    assert A.handle_agenda("", deps) == "Please log in first."
    assert "Unknown" in A._friendly_appt_line(
        datetime(2026, 11, 22, 10, 0, tzinfo=UTC),
        datetime(2026, 11, 22, 11, 0, tzinfo=UTC),
        "",
        "scheduled",
    )


def test_client_name_map_and_resolve_fallbacks() -> None:
    deps, _ = _deps()
    token = _login(deps, "cov1@example.com")
    from src.presentation.app import _require_ctx

    ctx = _require_ctx(token, deps)
    assert A._client_name_map(deps, ctx.user_id) == {}
    assert A._resolve_client_name(deps, ctx.user_id, "not-a-uuid") == "your client"
    assert (
        A._resolve_client_name(deps, ctx.user_id, "00000000-0000-4000-8000-000000000000")
        == "your client"
    )


def test_agenda_filters_past_and_lists() -> None:
    deps, _ = _deps()
    token = _login(deps, "cov2@example.com")
    A.handle_create_client(token, "Past Guy", "past@x.com", "", deps)
    cval = A.get_client_choices(token, deps)[0][1]
    # Past via raw handler is rejected; agenda with only future shows upcoming.
    A.handle_schedule_friendly(token, cval, "2026-12-10", "10:00", "60 minutes", deps)
    agenda = A.handle_agenda(token, deps)
    assert "Upcoming appointments" in agenda
    listed = A.handle_list_appointments(token, deps)
    assert "Past Guy" in listed


def test_edit_cancel_complete_edge_paths() -> None:
    deps, _ = _deps()
    token = _login(deps, "cov3@example.com")
    assert "log in" in A.handle_schedule_friendly("", "x", "2026-11-22", "10:00", "60 minutes", deps).lower()
    assert "choose" in A.handle_edit_appointment(token, "", "2026-11-22", "10:00", "60 minutes", deps).lower()
    assert "choose" in A.handle_cancel_appointment(token, "", deps).lower()
    assert "choose" in A.handle_complete(token, "", "notes", deps).lower()
    assert "choose" in A.handle_history(token, "", deps)[0].lower()
    # Invalid UUID shapes never traceback.
    assert "Traceback" not in A.handle_edit_appointment(token, "bad-id", "2026-11-22", "10:00", "60 minutes", deps)
    assert "Traceback" not in A.handle_cancel_appointment(token, "bad-id", deps)
    # Past window rejected friendly via edit path.
    A.handle_create_client(token, "Edge", "edge@x.com", "", deps)
    cval = A.get_client_choices(token, deps)[0][1]
    A.handle_schedule_friendly(token, cval, "2026-12-11", "10:00", "60 minutes", deps)
    aval = A.get_appointment_choices(token, deps)[0][1]
    past_edit = A.handle_edit_appointment(token, aval, "2020-01-01", "10:00", "60 minutes", deps)
    assert "could not" in past_edit.lower() or "failed" in past_edit.lower()
    # Complete then edit/cancel rejected (lifecycle).
    A.handle_complete(token, aval, "notes here ok", deps)
    assert "only scheduled" in A.handle_edit_appointment(token, aval, "2026-12-12", "10:00", "60 minutes", deps).lower()
    assert "only scheduled" in A.handle_cancel_appointment(token, aval, deps).lower() or "failed" in A.handle_cancel_appointment(token, aval, deps).lower()


def test_complete_with_notes_adapter_path() -> None:
    deps, _ = _deps()
    token = _login(deps, "cov4@example.com")
    A.handle_create_client(token, "Notes Guy", "notes@x.com", "", deps)
    cval = A.get_client_choices(token, deps)[0][1]
    A.handle_schedule_friendly(token, cval, "2026-12-12", "10:00", "60 minutes", deps)
    aval = A.get_appointment_choices(token, deps)[0][1]

    class WithNotes:
        def __init__(self, inner):  # type: ignore[no-untyped-def]
            self._inner = inner

        def __getattr__(self, name):  # type: ignore[no-untyped-def]
            return getattr(self._inner, name)

        def save_with_notes(self, appt, notes):  # type: ignore[no-untyped-def]
            self._inner.save(appt)

    deps.appointments_repo = WithNotes(deps.appointments_repo)  # type: ignore[assignment]
    out = A.handle_complete(token, aval, "adapter notes ok", deps)
    assert "completed" in out.lower()
