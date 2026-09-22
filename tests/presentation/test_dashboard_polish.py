"""TSK-018.3 RED: dashboard, client profiles, history & UX polish.

Dashboard is the default landing view (today/upcoming/clients/scheduled
counts + quick actions). Clients support search/filter + profile view
(identity, upcoming, history via GetClientHistory, notes, schedule action).
History is chronological with human statuses and no UUIDs. Cancelling asks
for confirmation first. Errors stay friendly (no tracebacks) and empty
states guide the next action. Logout clears dashboard state too.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from src.core.security.rate_limit import LoginRateLimiter
from src.modules.appointments.domain.entities import Appointment
from src.modules.appointments.use_cases.complete_appointment import CompleteAppointment
from src.modules.appointments.use_cases.get_client_history import GetClientHistory
from src.modules.appointments.use_cases.schedule_appointment import ScheduleAppointment
from src.modules.auth.use_cases.authenticate_user import AuthenticateUser
from src.modules.auth.use_cases.register_user import RegisterUser
from src.modules.clients.use_cases.register_client import RegisterClient
from src.presentation import app as A
from src.presentation.app import UIDeps
from tests.presentation.test_app_wiring import (
    FakeAppointments,
    FakeClients,
    FakeSessions,
    FakeUsers,
    _deps,
    _login,
)

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


class NotesFakeAppointments(FakeAppointments):
    """Fake repo plus the adapter-local notes bridge (save/find notes)."""

    def __init__(self) -> None:
        super().__init__()
        self._notes: dict[str, object] = {}

    def save_with_notes(self, appointment: Appointment, notes: object) -> None:
        self.save(appointment)
        self._notes[f"{appointment.user_id}:{appointment.id.value}"] = notes

    def find_notes_by_appointment_and_user_id(
        self, appointment_id: object, user_id: str
    ) -> object | None:
        key = f"{user_id}:{getattr(appointment_id, 'value', appointment_id)}"
        return self._notes.get(key)


def _notes_deps() -> tuple[UIDeps, FakeSessions]:
    users, clients, appointments, sessions = (
        FakeUsers(),
        FakeClients(),
        NotesFakeAppointments(),
        FakeSessions(),
    )
    deps = UIDeps(
        register_user=RegisterUser(users),
        authenticate_user=AuthenticateUser(users),
        register_client=RegisterClient(clients),
        schedule_appointment=ScheduleAppointment(appointments, clients),
        complete_appointment=CompleteAppointment(appointments),
        get_history=GetClientHistory(clients, appointments),
        sessions=sessions,
        clients_repo=clients,
        appointments_repo=appointments,
        limiter=LoginRateLimiter(max_attempts=5, window_seconds=300),
    )
    return deps, sessions


def _iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M")


def _walk(block):  # type: ignore[no-untyped-def]
    yield block
    for child in getattr(block, "children", []) or []:
        yield from _walk(child)


def _labels(demo):  # type: ignore[no-untyped-def]
    return [str(getattr(c, "label", "") or "") for c in _walk(demo)]


def _buttons(demo):  # type: ignore[no-untyped-def]
    import gradio as gr

    return [str(getattr(c, "value", "") or "") for c in _walk(demo) if isinstance(c, gr.Button)]


# --- Dashboard -----------------------------------------------------------


def test_dashboard_counts_and_today_list() -> None:
    deps, _ = _deps()
    token = _login(deps, "dash1@example.com")
    A.handle_create_client(token, "John Smith", "john@dash1.com", "", deps)
    A.handle_create_client(token, "Maria Garcia", "maria@dash1.com", "", deps)
    john = next(v for lb, v in A.get_client_choices(token, deps) if "John" in lb)
    maria = next(v for lb, v in A.get_client_choices(token, deps) if "Maria" in lb)
    now = datetime.now(UTC)
    first, second, third = now + timedelta(hours=1), now + timedelta(hours=2), now + timedelta(days=1, hours=1)
    A.handle_schedule(token, john, _iso(first), _iso(first + timedelta(minutes=60)), deps)
    A.handle_schedule(token, maria, _iso(second), _iso(second + timedelta(minutes=30)), deps)
    A.handle_schedule(token, john, _iso(third), _iso(third + timedelta(minutes=60)), deps)
    view = A.handle_dashboard(token, deps)
    today = now.date()
    expected_today = sum(1 for m in (first, second, third) if m.date() == today)
    assert f"Today: {expected_today}" in view
    assert "Upcoming: 3" in view
    assert "Clients: 2" in view
    assert "Scheduled: 3" in view
    if expected_today:
        assert "John Smith" in view
    else:
        # Midnight edge (23:xx UTC run): +1h/+2h rolled to tomorrow, and
        # the third was already tomorrow — counts above still prove the math.
        assert "No appointments today." in view
    assert "Good morning" in view or "Good afternoon" in view or "Good evening" in view
    assert _UUID_RE.search(view) is None
    assert "Traceback" not in view


def test_dashboard_quick_actions_prepare_next_step() -> None:
    deps, _ = _deps()
    token = _login(deps, "dash2@example.com")
    assert A.handle_quick_new_client(token, deps) != ""
    assert "Clients" in A.handle_quick_new_client(token, deps)
    choices, message = A.handle_quick_new_appointment(token, deps)
    assert "Agenda" in message
    assert choices == []
    A.handle_create_client(token, "John Smith", "john@dash2.com", "", deps)
    choices2, _ = A.handle_quick_new_appointment(token, deps)
    assert len(choices2) == 1
    assert A.handle_quick_new_client("bogus", deps) == "Please log in first."
    assert A.handle_quick_new_appointment("bogus", deps)[1] == "Please log in first."


def test_dashboard_empty_states_guide_next_action() -> None:
    deps, _ = _deps()
    token = _login(deps, "dash3@example.com")
    view = A.handle_dashboard(token, deps)
    assert "Today: 0" in view
    assert "Clients: 0" in view
    assert "no clients yet" in view.lower()
    assert "no upcoming appointment" in view.lower()
    assert "new" in view.lower() or "add" in view.lower() or "schedule" in view.lower()
    assert _UUID_RE.search(view) is None
    assert A.handle_dashboard("bogus", deps) == "Please log in first."
    assert A.handle_dashboard("", deps) == "Please log in first."


# --- Search / filter -----------------------------------------------------


def test_client_search_filters_by_name_email_phone() -> None:
    deps, _ = _deps()
    token = _login(deps, "search1@example.com")
    A.handle_create_client(token, "John Smith", "john@search1.com", "+34600111222", deps)
    A.handle_create_client(token, "Maria Garcia", "maria@search1.com", "", deps)
    A.handle_create_client(token, "Pedro Lopez", "pedro@search1.com", "", deps)
    maria = [lb for lb, _v in A.search_client_choices(token, "maria", deps)]
    assert len(maria) == 1 and "Maria Garcia" in maria[0]
    by_phone = [lb for lb, _v in A.search_client_choices(token, "600111222", deps)]
    assert len(by_phone) == 1 and "John Smith" in by_phone[0]
    by_email = [lb for lb, _v in A.search_client_choices(token, "pedro@search1", deps)]
    assert len(by_email) == 1 and "Pedro Lopez" in by_email[0]
    assert len(A.search_client_choices(token, "", deps)) == 3
    assert len(A.search_client_choices(token, "   ", deps)) == 3
    assert A.search_client_choices(token, "nobody-here", deps) == []
    for _lb, val in A.search_client_choices(token, "", deps):
        assert _UUID_RE.search(str(val)) is not None


def test_search_never_tracebacks_or_leaks() -> None:
    deps, _ = _deps()
    token = _login(deps, "search2@example.com")
    assert A.search_client_choices("bogus", "maria", deps) == []
    assert A.search_client_choices("", "maria", deps) == []
    assert A.search_client_choices(token, None, deps) == []  # type: ignore[arg-type]
    out = A.search_client_choices(token, "maria", deps)
    assert _UUID_RE.search(" || ".join(lb for lb, _v in out)) is None


# --- Client profile ------------------------------------------------------


def test_client_profile_shows_identity_upcoming_history_notes_action() -> None:
    deps, _ = _notes_deps()
    token = _login(deps, "prof1@example.com")
    A.handle_create_client(token, "John Smith", "john@prof1.com", "+34600111222", deps)
    client_val = A.get_client_choices(token, deps)[0][1]
    now = datetime.now(UTC)
    past = now + timedelta(hours=1)
    future = now + timedelta(days=2)
    A.handle_schedule(token, client_val, _iso(past), _iso(past + timedelta(minutes=60)), deps)
    A.handle_schedule(token, client_val, _iso(future), _iso(future + timedelta(minutes=60)), deps)
    appt_val = A.get_appointment_choices(token, deps)[0][1]
    A.handle_complete(token, appt_val, "Patient sleeps better.", deps)
    profile = A.handle_client_profile(token, client_val, deps)
    assert "John Smith" in profile
    assert "john@prof1.com" in profile
    assert "+34600111222" in profile
    assert "Upcoming" in profile
    assert "History" in profile
    assert "Completed" in profile
    assert "Scheduled" in profile
    assert "Patient sleeps better." in profile
    assert "Agenda" in profile
    assert _UUID_RE.search(profile) is None
    assert "Traceback" not in profile


def test_client_profile_empty_history_and_notes() -> None:
    deps, _ = _deps()
    token = _login(deps, "prof2@example.com")
    A.handle_create_client(token, "Maria Garcia", "maria@prof2.com", "", deps)
    client_val = A.get_client_choices(token, deps)[0][1]
    profile = A.handle_client_profile(token, client_val, deps)
    assert "Maria Garcia" in profile
    assert "No upcoming appointments for this client." in profile
    assert "No history for this client yet." in profile
    assert "(no session notes yet)" in profile
    assert _UUID_RE.search(profile) is None


def test_client_profile_rejects_unknown_empty_and_foreign() -> None:
    deps, _ = _deps()
    token_a = _login(deps, "profA@example.com")
    A.handle_create_client(token_a, "AliceA", "aliceA@x.com", "", deps)
    uuid_a = A.get_client_choices(token_a, deps)[0][1]
    token_b = _login(deps, "profB@example.com")
    foreign = A.handle_client_profile(token_b, uuid_a, deps)
    assert "not found" in foreign.lower()
    assert _UUID_RE.search(foreign) is None
    unknown = A.handle_client_profile(
        token_b, "00000000-0000-4000-8000-000000000000", deps
    )
    assert "not found" in unknown.lower()
    assert A.handle_client_profile(token_b, "", deps).lower().startswith("please choose")
    assert A.handle_client_profile(token_b, None, deps).lower().startswith("please choose")  # type: ignore[arg-type]
    assert A.handle_client_profile(token_b, "not-a-uuid", deps).lower().startswith(
        ("that client", "could not")
    )
    assert "Traceback" not in foreign + unknown
    assert A.handle_client_profile("bogus", uuid_a, deps) == "Please log in first."


def test_profile_schedule_action_targets_owned_client() -> None:
    deps, _ = _deps()
    token = _login(deps, "prof3@example.com")
    A.handle_create_client(token, "John Smith", "john@prof3.com", "", deps)
    client_val = A.get_client_choices(token, deps)[0][1]
    value, message = A.handle_profile_schedule_action(token, client_val, deps)
    assert value == client_val
    assert "Agenda" in message
    assert _UUID_RE.search(message) is None
    value2, message2 = A.handle_profile_schedule_action(token, "", deps)
    assert value2 is None and "choose" in message2.lower()
    value3, _ = A.handle_profile_schedule_action("bogus", client_val, deps)
    assert value3 is None


# --- History -------------------------------------------------------------


def test_history_chronological_human_status_no_uuid() -> None:
    deps, _ = _deps()
    token = _login(deps, "hist1@example.com")
    A.handle_create_client(token, "John Smith", "john@hist1.com", "", deps)
    client_val = A.get_client_choices(token, deps)[0][1]
    base = datetime.now(UTC) + timedelta(days=10)
    moments = [base + timedelta(days=2), base, base + timedelta(days=1)]
    for moment in moments:
        A.handle_schedule(token, client_val, _iso(moment), _iso(moment + timedelta(minutes=60)), deps)
    ordered_vals = [v for _lb, v in A.get_appointment_choices(token, deps)]
    A.handle_complete(token, ordered_vals[0], "First notes.", deps)
    A.handle_cancel_appointment(token, ordered_vals[1], deps)
    summary, notes = A.handle_history(token, client_val, deps)
    assert "John Smith" in summary
    first = summary.index(f"{base:%d/%m/%Y}")
    second = summary.index(f"{(base + timedelta(days=1)):%d/%m/%Y}")
    third = summary.index(f"{(base + timedelta(days=2)):%d/%m/%Y}")
    assert first < second < third
    assert "Completed" in summary
    assert "Scheduled" in summary
    assert "Cancelled" in summary
    assert _UUID_RE.search(summary) is None
    assert "Traceback" not in summary + notes


def test_complete_then_history_shows_notes() -> None:
    deps, _ = _notes_deps()
    token = _login(deps, "hist2@example.com")
    A.handle_create_client(token, "Maria Garcia", "maria@hist2.com", "", deps)
    client_val = A.get_client_choices(token, deps)[0][1]
    moment = datetime.now(UTC) + timedelta(days=3)
    A.handle_schedule(token, client_val, _iso(moment), _iso(moment + timedelta(minutes=60)), deps)
    appt_val = A.get_appointment_choices(token, deps)[0][1]
    done = A.handle_complete(token, appt_val, "Patient reported improvement.", deps)
    assert "completed" in done.lower()
    summary, notes = A.handle_history(token, client_val, deps)
    assert "completed" in summary.lower()
    assert "Patient reported improvement." in notes
    assert _UUID_RE.search(summary + notes) is None


# --- Friendly errors / empty states --------------------------------------


def test_polish_errors_are_concise_and_friendly() -> None:
    deps, _ = _deps()
    token = _login(deps, "pol1@example.com")
    outputs = [
        A.handle_dashboard("bogus", deps),
        A.handle_client_profile(token, "not-a-uuid", deps),
        A.request_cancel_confirmation(token, "not-a-uuid", deps),
        A.handle_quick_new_client("", deps),
        A.handle_history(token, "", deps)[0],
    ]
    for out in outputs:
        assert "Traceback" not in out
        assert "AttributeError" not in out
        assert "NoneType" not in out
        assert _UUID_RE.search(out) is None
        assert len(out) <= 300


def test_empty_states_cover_all_views() -> None:
    deps, _ = _deps()
    token = _login(deps, "pol2@example.com")
    dashboard = A.handle_dashboard(token, deps)
    clients = A.handle_list_clients(token, deps)
    agenda = A.handle_agenda(token, deps)
    assert "no clients yet" in dashboard.lower()
    assert "no clients yet" in clients.lower()
    assert "no upcoming appointment" in dashboard.lower()
    assert "no upcoming appointment" in agenda.lower() or "no appointment" in agenda.lower()
    for view in (dashboard, clients, agenda):
        assert "new" in view.lower() or "add" in view.lower() or "schedule" in view.lower()


# --- Confirm on cancel ----------------------------------------------------


def test_cancel_preview_asks_confirmation_first() -> None:
    deps, _ = _deps()
    token = _login(deps, "cancel1@example.com")
    A.handle_create_client(token, "John Smith", "john@cancel1.com", "", deps)
    client_val = A.get_client_choices(token, deps)[0][1]
    moment = datetime.now(UTC) + timedelta(days=4)
    A.handle_schedule(token, client_val, _iso(moment), _iso(moment + timedelta(minutes=60)), deps)
    appt_val = A.get_appointment_choices(token, deps)[0][1]
    preview = A.request_cancel_confirmation(token, appt_val, deps)
    assert "sure" in preview.lower() or "confirm" in preview.lower()
    assert "Confirm cancel" in preview
    assert "John Smith" in preview
    assert _UUID_RE.search(preview) is None
    # Preview alone must not cancel: still scheduled + selectable.
    assert any(v == appt_val for _lb, v in A.get_appointment_choices(token, deps))
    done = A.handle_cancel_appointment(token, appt_val, deps)
    assert "cancel" in done.lower()


def test_cancel_preview_rejects_bad_selection() -> None:
    deps, _ = _deps()
    token = _login(deps, "cancel2@example.com")
    assert "choose" in A.request_cancel_confirmation(token, "", deps).lower()
    assert "choose" in A.request_cancel_confirmation(token, None, deps).lower()  # type: ignore[arg-type]
    unknown = A.request_cancel_confirmation(
        token, "00000000-0000-4000-8000-000000000000", deps
    )
    assert "not found" in unknown.lower()
    assert _UUID_RE.search(unknown) is None
    assert A.request_cancel_confirmation("bogus", "x", deps) == "Please log in first."


def test_cancel_preview_refuses_non_scheduled() -> None:
    deps, _ = _deps()
    token = _login(deps, "cancel3@example.com")
    A.handle_create_client(token, "John Smith", "john@cancel3.com", "", deps)
    client_val = A.get_client_choices(token, deps)[0][1]
    moment = datetime.now(UTC) + timedelta(days=5)
    A.handle_schedule(token, client_val, _iso(moment), _iso(moment + timedelta(minutes=60)), deps)
    appt_val = A.get_appointment_choices(token, deps)[0][1]
    A.handle_complete(token, appt_val, "Some notes here.", deps)
    refused = A.request_cancel_confirmation(token, appt_val, deps)
    assert "only scheduled" in refused.lower()
    assert "Traceback" not in refused


# --- Logout + isolation ---------------------------------------------------


def test_logout_clears_dashboard_and_all_state() -> None:
    deps, _ = _deps()
    token = _login(deps, "logout1@example.com")
    A.handle_create_client(token, "John Smith", "john@logout1.com", "", deps)
    assert "Clients: 1" in A.handle_dashboard(token, deps)
    message, cleared, _ = A.handle_logout(token, deps)
    assert message == "Logged out." and cleared == ""
    assert A.handle_dashboard(token, deps) == "Please log in first."
    assert A.get_client_choices(token, deps) == []
    assert A.search_client_choices(token, "john", deps) == []
    assert A.handle_client_profile(token, "x", deps) == "Please log in first."
    assert A.handle_agenda(token, deps) == "Please log in first."
    assert A.request_cancel_confirmation(token, "x", deps) == "Please log in first."


def test_cross_user_isolation_dashboard_profile_search() -> None:
    deps, _ = _deps()
    token_a = _login(deps, "isoA@example.com")
    A.handle_create_client(token_a, "AliceA", "aliceA@x.com", "", deps)
    uuid_a = A.get_client_choices(token_a, deps)[0][1]
    moment = datetime.now(UTC) + timedelta(days=6)
    A.handle_schedule(token_a, uuid_a, _iso(moment), _iso(moment + timedelta(minutes=60)), deps)
    token_b = _login(deps, "isoB@example.com")
    view_b = A.handle_dashboard(token_b, deps)
    assert "Clients: 0" in view_b
    assert "AliceA" not in view_b
    assert A.search_client_choices(token_b, "alice", deps) == []
    foreign = A.handle_client_profile(token_b, uuid_a, deps)
    assert "not found" in foreign.lower()
    assert "AliceA" not in foreign
    assert _UUID_RE.search(view_b + foreign) is None


class FailingClients(FakeClients):
    """Clients repo suffering an outage (read raises, like a DB failure)."""

    def list_by_user_id(self, user_id: str) -> list:
        raise ValueError("db down")


class FailingAppointments(FakeAppointments):
    """Appointments repo suffering an outage (read raises)."""

    def list_by_user_id(self, user_id: str) -> list:
        raise ValueError("db down")


def _outage_deps() -> tuple[UIDeps, FakeSessions]:
    users, sessions = FakeUsers(), FakeSessions()
    clients, appointments = FailingClients(), FailingAppointments()
    deps = UIDeps(
        register_user=RegisterUser(users),
        authenticate_user=AuthenticateUser(users),
        register_client=RegisterClient(clients),
        schedule_appointment=ScheduleAppointment(appointments, clients),
        complete_appointment=CompleteAppointment(appointments),
        get_history=GetClientHistory(clients, appointments),
        sessions=sessions,
        clients_repo=clients,
        appointments_repo=appointments,
        limiter=LoginRateLimiter(max_attempts=5, window_seconds=300),
    )
    return deps, sessions


def test_day_greeting_branches() -> None:
    assert A._day_greeting(datetime(2026, 1, 1, 8, 0, tzinfo=UTC)) == "Good morning"
    assert A._day_greeting(datetime(2026, 1, 1, 14, 0, tzinfo=UTC)) == "Good afternoon"
    assert A._day_greeting(datetime(2026, 1, 1, 22, 0, tzinfo=UTC)) == "Good evening"
    assert A._day_greeting(None) == "Hello"  # type: ignore[arg-type]


def test_repo_outage_stays_friendly() -> None:
    deps, _ = _outage_deps()
    token = _login(deps, "outage1@example.com")
    dashboard = A.handle_dashboard(token, deps)
    assert dashboard.startswith("Could not load dashboard")
    assert "Traceback" not in dashboard
    assert _UUID_RE.search(dashboard) is None
    assert A.search_client_choices(token, "alice", deps) == []


def test_profile_schedule_action_rejects_malformed_and_foreign() -> None:
    deps, _ = _deps()
    token_a = _login(deps, "schedA@example.com")
    A.handle_create_client(token_a, "AliceA", "aliceA@x.com", "", deps)
    uuid_a = A.get_client_choices(token_a, deps)[0][1]
    value_bad, message_bad = A.handle_profile_schedule_action(token_a, "not-a-uuid", deps)
    assert value_bad is None
    assert "not found" in message_bad.lower()
    assert _UUID_RE.search(message_bad) is None
    token_b = _login(deps, "schedB@example.com")
    value_foreign, message_foreign = A.handle_profile_schedule_action(token_b, uuid_a, deps)
    assert value_foreign is None
    assert "not found" in message_foreign.lower()
    assert "AliceA" not in message_foreign


def test_demo_chrome_labels_consistent_no_internals() -> None:
    deps, _ = _deps()
    demo = A.build_demo(deps)
    labels = _labels(demo)
    chrome = " || ".join(labels)
    assert "UUID" not in chrome
    assert "user_id" not in chrome
    assert "token" not in chrome.lower()
    low = chrome.lower()
    assert "dashboard overview" in low
    assert "search clients" in low
    assert "client profile" in low
    assert "confirm cancel" not in low  # button, not label (checked below)
    buttons = " || ".join(_buttons(demo)).lower()
    assert "+ new client" in buttons
    assert "+ new appointment" in buttons
    assert "refresh dashboard" in buttons
    assert "view profile" in buttons
    assert "confirm cancel" in buttons
    assert "search" in buttons
