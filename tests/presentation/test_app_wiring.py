"""TSK-016: presentation handler wiring (fakes, no server, no DB).

Proves every Gradio handler routes through the middleware with
``ctx.user_id`` into the real use-cases (no SQL, no domain rules here).
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta

from src.core.security.rate_limit import LoginRateLimiter
from src.modules.appointments.domain.entities import Appointment
from src.modules.appointments.domain.repository_interfaces import IAppointmentRepository
from src.modules.appointments.domain.value_objects import AppointmentId
from src.modules.appointments.use_cases.complete_appointment import CompleteAppointment
from src.modules.appointments.use_cases.get_client_history import GetClientHistory
from src.modules.appointments.use_cases.schedule_appointment import ScheduleAppointment
from src.modules.auth.domain.entities import AuthSession, User
from src.modules.auth.domain.repository_interfaces import (
    ISessionRepository,
    IUserRepository,
)
from src.modules.auth.domain.security import hash_token
from src.modules.auth.domain.value_objects import UserEmail
from src.modules.auth.use_cases.authenticate_user import AuthenticateUser
from src.modules.auth.use_cases.register_user import RegisterUser
from src.modules.clients.domain.entities import Client
from src.modules.clients.domain.repository_interfaces import IClientRepository
from src.modules.clients.domain.value_objects import ClientId
from src.modules.clients.use_cases.register_client import RegisterClient
from src.presentation.app import (
    UIDeps,
    build_demo,
    handle_complete,
    handle_create_client,
    handle_history,
    handle_list_appointments,
    handle_list_clients,
    handle_login,
    handle_logout,
    handle_register,
    handle_schedule,
)


class FakeUsers(IUserRepository):
    def __init__(self) -> None:
        self._by_email: dict[str, User] = {}

    def save(self, user: User) -> None:
        self._by_email[user.email.value] = user

    def find_by_email(self, email: UserEmail) -> User | None:
        return self._by_email.get(email.value)


class FakeClients(IClientRepository):
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


class FakeAppointments(IAppointmentRepository):
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
            if exclude_appointment_id is not None and appt.id == exclude_appointment_id:
                continue
            if appt.starts_at < ends_at and starts_at < appt.ends_at:
                result.append(copy.copy(appt))
        return result


class FakeSessions(ISessionRepository):
    def __init__(self) -> None:
        self._by_hash: dict[str, AuthSession] = {}

    def save(self, session: AuthSession) -> None:
        self._by_hash[hash_token(session.token)] = session

    def find_by_token_hash(self, token_hash: str) -> AuthSession | None:
        return self._by_hash.get(token_hash)

    def delete_by_token_hash(self, token_hash: str) -> None:
        self._by_hash.pop(token_hash, None)

    def delete_expired(self, now: datetime) -> int:
        expired = [h for h, s in self._by_hash.items() if s.is_expired(now)]
        for h in expired:
            del self._by_hash[h]
        return len(expired)


def _deps(
    *, max_attempts: int = 5, window_seconds: int = 300
) -> tuple[UIDeps, FakeSessions]:
    users, clients, appointments, sessions = (
        FakeUsers(),
        FakeClients(),
        FakeAppointments(),
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
        limiter=LoginRateLimiter(
            max_attempts=max_attempts, window_seconds=window_seconds
        ),
    )
    return deps, sessions


def _login(deps: UIDeps, email: str = "pro@example.com") -> str:
    handle_register(email, "s3cret-pass", deps)
    message, token, _label = handle_login(email, "s3cret-pass", "test-ip", deps)
    assert message == "Login ok." and token
    return token


def test_register_then_login_round_trip() -> None:
    deps, _ = _deps()
    assert "Please log in" in handle_register("pro@example.com", "s3cret-pass", deps)
    message, token, label = handle_login(
        "pro@example.com", "s3cret-pass", "test-ip", deps
    )
    assert (message, bool(token), bool(label)) == ("Login ok.", True, True)


def test_register_duplicate_reports_failure() -> None:
    deps, _ = _deps()
    handle_register("a@example.com", "s3cret-pass", deps)
    assert "failed" in handle_register("a@example.com", "s3cret-pass", deps).lower()


def test_login_wrong_password_generic_and_empty_token() -> None:
    deps, _ = _deps()
    handle_register("pro@example.com", "s3cret-pass", deps)
    message, token, _label = handle_login(
        "pro@example.com", "wrong-pass", "test-ip", deps
    )
    assert message == "Invalid email or password"
    assert token == ""


def test_login_throttle_preserves_generic_error() -> None:
    deps, _ = _deps(max_attempts=2, window_seconds=300)
    handle_register("t@example.com", "s3cret-pass", deps)
    handle_login("t@example.com", "bad-1", "ip-1", deps)
    handle_login("t@example.com", "bad-1", "ip-1", deps)
    message, token, _ = handle_login("t@example.com", "bad-1", "ip-1", deps)
    assert message == "Invalid email or password"
    assert token == ""


def test_unauthenticated_handlers_require_login() -> None:
    deps, _ = _deps()
    assert handle_create_client("", "A", "a@example.com", "", deps) == "Please log in first."
    assert handle_list_clients("bogus", deps) == "Please log in first."
    assert handle_schedule("", "c", "2026-10-15 10:00", "2026-10-15 11:00", deps) == (
        "Please log in first."
    )
    assert handle_list_appointments("", deps) == "Please log in first."
    summary, _ = handle_history("", "c", deps)
    assert summary == "Please log in first."
    assert handle_complete("", "a", "notes", deps) == "Please log in first."


def test_expired_token_rejected_by_handlers() -> None:
    deps, sessions = _deps()
    stale = AuthSession.issue("user-1", ttl_hours=-1)
    sessions.save(stale)
    assert handle_list_clients(stale.token, deps) == "Please log in first."


def test_clients_register_list_and_validation() -> None:
    deps, _ = _deps()
    token = _login(deps)
    assert "(no clients yet)" in handle_list_clients(token, deps)
    ok = handle_create_client(token, "Alice", "alice@example.com", "", deps)
    assert "Client saved" in ok
    listed = handle_list_clients(token, deps)
    assert "Alice" in listed and "alice@example.com" in listed
    bad = handle_create_client(token, "Bob", "not-an-email", "", deps)
    assert "failed" in bad.lower()


def test_scheduler_schedule_list_overlap_and_bad_input() -> None:
    deps, _ = _deps()
    token = _login(deps)
    handle_create_client(token, "Alice", "alice@example.com", "", deps)
    client_id = handle_list_clients(token, deps).split(" | ")[0]
    ok = handle_schedule(token, client_id, "2026-10-15 10:00", "2026-10-15 11:00", deps)
    assert "Scheduled" in ok
    overlap = handle_schedule(
        token, client_id, "2026-10-15 10:30", "2026-10-15 11:30", deps
    )
    assert "failed" in overlap.lower()
    bad = handle_schedule(token, client_id, "not-a-date", "2026-10-15 11:00", deps)
    assert "failed" in bad.lower()
    listed = handle_list_appointments(token, deps)
    assert "scheduled" in listed


def test_history_and_complete_flow() -> None:
    deps, _ = _deps()
    token = _login(deps)
    handle_create_client(token, "Alice", "alice@example.com", "", deps)
    client_id = handle_list_clients(token, deps).split(" | ")[0]
    handle_schedule(token, client_id, "2026-10-15 10:00", "2026-10-15 11:00", deps)
    appt_id = handle_list_appointments(token, deps).split(" | ")[0]
    summary, _notes = handle_history(token, client_id, deps)
    assert "Alice" in summary
    done = handle_complete(token, appt_id, "First session went well.", deps)
    assert "Completed" in done
    summary2, _notes2 = handle_history(token, client_id, deps)
    assert "completed" in summary2
    bad = handle_complete(token, appt_id, "   ", deps)
    assert "failed" in bad.lower()


def test_history_unknown_client_reports_failure() -> None:
    deps, _ = _deps()
    token = _login(deps)
    summary, _ = handle_history(
        token, "00000000-0000-4000-8000-000000000000", deps
    )
    assert "failed" in summary.lower()


def test_logout_revokes_token() -> None:
    deps, _ = _deps()
    token = _login(deps)
    message, cleared, _ = handle_logout(token, deps)
    assert message == "Logged out." and cleared == ""
    assert handle_list_clients(token, deps) == "Please log in first."


def test_build_demo_returns_blocks() -> None:
    import gradio as gr

    deps, _ = _deps()
    demo = build_demo(deps)
    assert isinstance(demo, gr.Blocks)


def test_future_appointments_accepted_past_rejected() -> None:
    deps, _ = _deps()
    token = _login(deps)
    handle_create_client(token, "Alice", "alice@example.com", "", deps)
    client_id = handle_list_clients(token, deps).split(" | ")[0]
    future = datetime.now(UTC) + timedelta(days=30)
    ok = handle_schedule(
        token,
        client_id,
        future.strftime("%Y-%m-%d %H:%M"),
        (future + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M"),
        deps,
    )
    assert "Scheduled" in ok
    past = handle_schedule(
        token, client_id, "2020-01-01 10:00", "2020-01-01 11:00", deps
    )
    assert "failed" in past.lower()
