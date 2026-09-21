"""TSK-018.2 RED: user-friendly client, appointment & agenda workflow.

Users must manage appointments without UUIDs or raw ISO datetimes:
client selector shows names (UUID hidden as value), date+time+duration
controls compose tz-aware windows, edit/cancel/complete via existing
use-cases/domain lifecycle, overlap still rejected friendly, invalid
selections never traceback, lists show name/date/time/status, Agenda
chronological upcoming, empty states guide next action.
"""

from __future__ import annotations

import re

from src.presentation import app as A
from tests.presentation.test_app_wiring import _deps, _login

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def _walk(block):  # type: ignore[no-untyped-def]
    yield block
    for child in getattr(block, "children", []) or []:
        yield from _walk(child)


def _labels(demo):  # type: ignore[no-untyped-def]
    return [str(getattr(c, "label", "") or "") for c in _walk(demo)]


def _buttons(demo):  # type: ignore[no-untyped-def]
    import gradio as gr

    return [str(getattr(c, "value", "") or "") for c in _walk(demo) if isinstance(c, gr.Button)]


def test_client_selector_shows_own_names_no_uuids() -> None:
    deps, _ = _deps()
    token = _login(deps, "fw1@example.com")
    A.handle_create_client(token, "John Smith", "john@fw1.com", "", deps)
    A.handle_create_client(token, "Maria Garcia", "maria@fw1.com", "", deps)
    choices = A.get_client_choices(token, deps)
    assert len(choices) == 2
    labels = [label for label, _value in choices]
    values = [value for _label, value in choices]
    assert any("John Smith" in lb for lb in labels)
    assert any("Maria Garcia" in lb for lb in labels)
    for lb in labels:
        assert _UUID_RE.search(lb) is None
    for val in values:
        assert _UUID_RE.search(str(val)) is not None


def test_client_selector_isolates_foreign_clients() -> None:
    deps, _ = _deps()
    token_a = _login(deps, "fwA@example.com")
    A.handle_create_client(token_a, "AliceA", "aliceA@x.com", "", deps)
    uuid_a = A.get_client_choices(token_a, deps)[0][1]
    A.handle_logout(token_a, deps)
    token_b = _login(deps, "fwB@example.com")
    choices_b = A.get_client_choices(token_b, deps)
    assert choices_b == []
    assert all(uuid_a != val for _lb, val in choices_b)
    # Foreign UUID must not be usable by user B (ownership holds).
    out = A.handle_schedule_friendly(token_b, uuid_a, "2026-11-20", "10:00", "60 minutes", deps)
    assert "failed" in out.lower() or "not found" in out.lower() or "choose" in out.lower()
    assert _UUID_RE.search(out) is None


def test_create_without_uuid_or_iso_via_date_time_duration() -> None:
    deps, _ = _deps()
    token = _login(deps, "fw2@example.com")
    A.handle_create_client(token, "John Smith", "john@fw2.com", "", deps)
    client_val = A.get_client_choices(token, deps)[0][1]
    out = A.handle_schedule_friendly(token, client_val, "2026-11-21", "16:00", "60 minutes", deps)
    assert "scheduled" in out.lower()
    assert "John Smith" in out
    assert _UUID_RE.search(out) is None
    assert "2026-11-21" not in out or "/" in out or "21/11/2026" in out


def test_compose_window_is_tz_aware_and_friendly_errors() -> None:
    starts, ends = A.compose_schedule_window("2026-11-22", "10:00", "60 minutes", None)  # type: ignore[arg-type]
    assert starts.tzinfo is not None and ends.tzinfo is not None
    assert (ends - starts).total_seconds() == 3600
    # Invalid/empty inputs raise ValueError (handlers convert to friendly, no traceback).
    for bad in [
        (None, "10:00", "60 minutes"),
        ("2026-11-22", None, "60 minutes"),
        ("2026-11-22", "10:00", None),
        ("", "10:00", "60 minutes"),
        ("not-a-date", "10:00", "60 minutes"),
        ("2026-11-22", "25:99", "60 minutes"),
    ]:
        try:
            A.compose_schedule_window(*bad, None)  # type: ignore[arg-type]
        except ValueError:
            pass
        else:
            raise AssertionError(f"expected ValueError for {bad!r}")


def test_overlap_still_rejected_with_friendly_message() -> None:
    deps, _ = _deps()
    token = _login(deps, "fw3@example.com")
    A.handle_create_client(token, "John Smith", "john@fw3.com", "", deps)
    client_val = A.get_client_choices(token, deps)[0][1]
    ok = A.handle_schedule_friendly(token, client_val, "2026-11-23", "14:00", "60 minutes", deps)
    assert "scheduled" in ok.lower()
    overlap = A.handle_schedule_friendly(token, client_val, "2026-11-23", "14:30", "60 minutes", deps)
    assert "overlap" in overlap.lower()
    assert "failed" in overlap.lower() or "could not" in overlap.lower()
    assert _UUID_RE.search(overlap) is None
    assert "Traceback" not in overlap


def test_edit_appointment_preserves_validation() -> None:
    deps, _ = _deps()
    token = _login(deps, "fw4@example.com")
    A.handle_create_client(token, "John Smith", "john@fw4.com", "", deps)
    client_val = A.get_client_choices(token, deps)[0][1]
    A.handle_schedule_friendly(token, client_val, "2026-11-24", "10:00", "60 minutes", deps)
    A.handle_schedule_friendly(token, client_val, "2026-11-24", "12:00", "60 minutes", deps)
    first_val = A.get_appointment_choices(token, deps)[0][1]
    # Move first to a free slot -> success, human-readable, no UUID.
    edited = A.handle_edit_appointment(token, first_val, "2026-11-24", "11:00", "30 minutes", deps)
    assert "updated" in edited.lower() or "edited" in edited.lower()
    assert _UUID_RE.search(edited) is None
    # Move into overlap with second -> rejected friendly.
    clash = A.handle_edit_appointment(token, first_val, "2026-11-24", "12:15", "60 minutes", deps)
    assert "overlap" in clash.lower()
    assert "Traceback" not in clash


def test_cancel_appointment_uses_domain_lifecycle() -> None:
    deps, _ = _deps()
    token = _login(deps, "fw5@example.com")
    A.handle_create_client(token, "John Smith", "john@fw5.com", "", deps)
    client_val = A.get_client_choices(token, deps)[0][1]
    A.handle_schedule_friendly(token, client_val, "2026-11-25", "10:00", "60 minutes", deps)
    appt_val = A.get_appointment_choices(token, deps)[0][1]
    done = A.handle_cancel_appointment(token, appt_val, deps)
    assert "cancel" in done.lower()
    assert _UUID_RE.search(done) is None
    # Second cancel -> friendly lifecycle error, no traceback.
    again = A.handle_cancel_appointment(token, appt_val, deps)
    assert "failed" in again.lower() or "only scheduled" in again.lower()
    assert "Traceback" not in again
    # Cancelled no longer appears in schedulable choices.
    assert all(val != appt_val for _lb, val in A.get_appointment_choices(token, deps))


def test_complete_flows_into_session_notes() -> None:
    deps, _ = _deps()
    token = _login(deps, "fw6@example.com")
    A.handle_create_client(token, "John Smith", "john@fw6.com", "", deps)
    client_val = A.get_client_choices(token, deps)[0][1]
    A.handle_schedule_friendly(token, client_val, "2026-11-26", "10:00", "60 minutes", deps)
    appt_val = A.get_appointment_choices(token, deps)[0][1]
    done = A.handle_complete(token, appt_val, "Patient reported improvement.", deps)
    assert "completed" in done.lower()
    summary, _notes = A.handle_history(token, client_val, deps)
    assert "John Smith" in summary
    assert "completed" in summary.lower()
    assert _UUID_RE.search(summary) is None


def test_invalid_empty_selections_never_traceback() -> None:
    deps, _ = _deps()
    token = _login(deps, "fw7@example.com")
    for fn in [
        lambda: A.handle_schedule_friendly(token, "", "2026-11-27", "10:00", "60 minutes", deps),
        lambda: A.handle_schedule_friendly(token, None, "2026-11-27", "10:00", "60 minutes", deps),  # type: ignore[arg-type]
        lambda: A.handle_schedule_friendly(token, "not-a-uuid", "2026-11-27", "10:00", "60 minutes", deps),
        lambda: A.handle_edit_appointment(token, "", "2026-11-27", "10:00", "60 minutes", deps),
        lambda: A.handle_edit_appointment(token, None, None, None, None, deps),  # type: ignore[arg-type]
        lambda: A.handle_cancel_appointment(token, "", deps),
        lambda: A.handle_cancel_appointment(token, None, deps),  # type: ignore[arg-type]
        lambda: A.handle_complete(token, "", "", deps),
        lambda: A.get_client_choices("", deps),
        lambda: A.get_appointment_choices("bogus", deps),
        lambda: A.handle_agenda("", deps),
        lambda: A.handle_agenda("bogus", deps),
    ]:
        out = fn()
        text = str(out)
        assert "Traceback" not in text
        assert "AttributeError" not in text
        assert _UUID_RE.search(text) is None


def test_appointment_lists_are_human_readable() -> None:
    deps, _ = _deps()
    token = _login(deps, "fw8@example.com")
    A.handle_create_client(token, "John Smith", "john@fw8.com", "", deps)
    client_val = A.get_client_choices(token, deps)[0][1]
    A.handle_schedule_friendly(token, client_val, "2026-11-28", "16:00", "60 minutes", deps)
    listed = A.handle_list_appointments(token, deps)
    assert "John Smith" in listed
    assert "28/11/2026" in listed or "2026" in listed
    assert "16:00" in listed
    assert "Scheduled" in listed or "scheduled" in listed
    assert _UUID_RE.search(listed) is None
    clients_view = A.handle_list_clients(token, deps)
    assert "John Smith" in clients_view
    assert _UUID_RE.search(clients_view) is None


def test_agenda_is_chronological_upcoming() -> None:
    deps, _ = _deps()
    token = _login(deps, "fw9@example.com")
    A.handle_create_client(token, "John Smith", "john@fw9.com", "", deps)
    client_val = A.get_client_choices(token, deps)[0][1]
    A.handle_schedule_friendly(token, client_val, "2026-12-03", "12:00", "60 minutes", deps)
    A.handle_schedule_friendly(token, client_val, "2026-12-01", "09:00", "60 minutes", deps)
    A.handle_schedule_friendly(token, client_val, "2026-12-02", "10:30", "60 minutes", deps)
    agenda = A.handle_agenda(token, deps)
    assert "John Smith" in agenda
    assert _UUID_RE.search(agenda) is None
    first = agenda.index("01/12/2026") if "01/12/2026" in agenda else agenda.index("2026-12-01")
    second = agenda.index("02/12/2026") if "02/12/2026" in agenda else agenda.index("2026-12-02")
    third = agenda.index("03/12/2026") if "03/12/2026" in agenda else agenda.index("2026-12-03")
    assert first < second < third


def test_empty_states_guide_next_action() -> None:
    deps, _ = _deps()
    token = _login(deps, "fw10@example.com")
    clients_view = A.handle_list_clients(token, deps)
    assert "no clients yet" in clients_view.lower()
    assert "add" in clients_view.lower() or "register" in clients_view.lower() or "new" in clients_view.lower()
    agenda = A.handle_agenda(token, deps)
    assert "no appointment" in agenda.lower()
    assert "new" in agenda.lower() or "schedule" in agenda.lower()
    appts = A.handle_list_appointments(token, deps)
    assert "no appointment" in appts.lower()
    assert _UUID_RE.search(clients_view + agenda + appts) is None


def test_demo_has_friendly_controls_and_no_uuid_inputs() -> None:
    deps, _ = _deps()
    demo = A.build_demo(deps)
    labels = _labels(demo)
    chrome = " || ".join(labels)
    assert "UUID" not in chrome
    assert "user_id" not in chrome
    assert "Token" not in chrome and "token" not in chrome.lower()
    low = chrome.lower()
    assert "client" in low
    assert "date" in low
    assert "time" in low
    assert "duration" in low
    buttons = " || ".join(_buttons(demo)).lower()
    assert "create appointment" in buttons or "new appointment" in buttons
    assert "edit" in buttons
    assert "cancel" in buttons
    assert "complete" in buttons
    # Dropdowns for client/appointment selectors exist.
    import gradio as gr

    dropdowns = [c for c in _walk(demo) if isinstance(c, gr.Dropdown)]
    assert len(dropdowns) >= 3
    drop_labels = [str(getattr(c, "label", "") or "").lower() for c in dropdowns]
    assert any("client" in lb for lb in drop_labels)
    assert any("appointment" in lb for lb in drop_labels)
