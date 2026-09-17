"""ChronoLog Gradio dashboard (presentation only, no business rules).

Thin driving adapter: every handler resolves the session token from
``gr.State`` via the middleware (``authenticate_request`` +
``enforce_user_authorization``) and passes ``ctx.user_id`` — never a
client-supplied id — into the injected use-cases. No SQL, no validation
logic, no adapter imports here (wiring lives in ``src/composition.py``).

Allowed imports (contract): use-cases (typing/call), ``ISessionRepository``
+ ``IClientRepository`` + ``IAppointmentRepository`` ports (typing only),
middleware + limiter + ``hash_token``/``AuthSession`` session contract.
Forbidden: ``Postgres*``, ``psycopg2``, ``sqlalchemy`` (asserted by grep).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import gradio as gr

from src.core.security.middleware import (
    authenticate_request,
    enforce_user_authorization,
)
from src.core.security.rate_limit import LoginRateLimiter
from src.modules.appointments.domain.repository_interfaces import (
    IAppointmentRepository,
)
from src.modules.appointments.use_cases.complete_appointment import CompleteAppointment
from src.modules.appointments.use_cases.get_client_history import GetClientHistory
from src.modules.appointments.use_cases.schedule_appointment import ScheduleAppointment
from src.modules.auth.domain.exceptions import InvalidCredentialsError
from src.modules.auth.domain.repository_interfaces import ISessionRepository
from src.modules.auth.domain.security import hash_token
from src.modules.auth.use_cases.authenticate_user import AuthenticateUser
from src.modules.auth.use_cases.register_user import RegisterUser
from src.modules.clients.domain.repository_interfaces import IClientRepository
from src.modules.clients.use_cases.register_client import RegisterClient

_DATETIME_HINT = "YYYY-MM-DD HH:MM (UTC assumed, e.g. 2026-10-15 10:00)"


@dataclass
class UIDeps:
    """Injected collaborators (built by the composition root)."""

    register_user: RegisterUser
    authenticate_user: AuthenticateUser
    register_client: RegisterClient
    schedule_appointment: ScheduleAppointment
    complete_appointment: CompleteAppointment
    get_history: GetClientHistory
    sessions: ISessionRepository
    clients_repo: IClientRepository
    appointments_repo: IAppointmentRepository
    limiter: LoginRateLimiter


# ---------------------------------------------------------------------------
# Pure handlers (Gradio-free, unit-tested with fakes)
# ---------------------------------------------------------------------------


def handle_register(email: str, password: str, deps: UIDeps) -> str:
    """Register an account; user logs in separately (explicit step)."""
    try:
        user = deps.register_user.execute(email=email or "", password=password or "")
    except (ValueError, TypeError, AttributeError) as exc:
        return f"Register failed: {exc}"
    return f"Registered {user.email.value}. Please log in."


def _throttle_keys(email: str | None, client_ip: str | None) -> tuple[str, str]:
    normalized = (email or "").strip().lower()
    ip = (client_ip or "").strip() or "unknown"
    return f"email:{normalized}", f"ip:{ip}"


def handle_login(
    email: str, password: str, client_ip: str, deps: UIDeps
) -> tuple[str, str, str]:
    """Login with per-email AND per-IP throttle; generic error preserved.

    Returns ``(message, token, user_label)`` — token is ``""`` on failure.
    """
    email_key, ip_key = _throttle_keys(email, client_ip)
    now = datetime.now(UTC)
    try:
        deps.limiter.check(email_key, now=now)
        deps.limiter.check(ip_key, now=now)
    except InvalidCredentialsError:
        return (InvalidCredentialsError.GENERIC_MESSAGE, "", "")
    try:
        session = deps.authenticate_user.execute(
            email=email or "", password=password or ""
        )
    except (InvalidCredentialsError, TypeError, AttributeError):
        deps.limiter.record_failure(email_key, now=now)
        deps.limiter.record_failure(ip_key, now=now)
        return (InvalidCredentialsError.GENERIC_MESSAGE, "", "")
    deps.limiter.record_success(email_key)
    deps.limiter.record_success(ip_key)
    deps.sessions.save(session)
    return ("Login ok.", session.token, session.user_id)


def handle_logout(token: str, deps: UIDeps) -> tuple[str, str, str]:
    """Revoke the session (logout); missing tokens are a no-op success."""
    if token:
        deps.sessions.delete_by_token_hash(hash_token(token))
    return ("Logged out.", "", "")


def _require_ctx(token: str, deps: UIDeps) -> Any:
    ctx = authenticate_request(token if token else None, deps.sessions)
    enforce_user_authorization(ctx, ctx.user_id)
    return ctx


def handle_create_client(
    token: str, name: str, email: str, phone: str, deps: UIDeps
) -> str:
    """Register a client for the authenticated owner."""
    try:
        ctx = _require_ctx(token, deps)
    except InvalidCredentialsError:
        return "Please log in first."
    try:
        client = deps.register_client.execute(
            user_id=ctx.user_id,
            name=name or "",
            email=email or "",
            phone=phone or None,
        )
    except (ValueError, TypeError, AttributeError) as exc:
        return f"Client registration failed: {exc}"
    return f"Client saved: {client.id.value} ({client.name})"


def handle_list_clients(token: str, deps: UIDeps) -> str:
    """List owned clients as ``id | name | email | phone`` lines."""
    try:
        ctx = _require_ctx(token, deps)
    except InvalidCredentialsError:
        return "Please log in first."
    clients = deps.clients_repo.list_by_user_id(ctx.user_id)
    if not clients:
        return "(no clients yet)"
    lines = []
    for client in clients:
        phone = client.phone.value if client.phone is not None else "-"
        lines.append(
            f"{client.id.value} | {client.name} | {client.email.value} | {phone}"
        )
    return "\n".join(lines)


def _parse_moment(raw: str | None, label: str) -> datetime:
    text = (raw or "").strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            moment = datetime.strptime(text, fmt)  # noqa: DTZ007 — UTC attached below
            break
        except ValueError:
            continue
    else:
        try:
            moment = datetime.fromisoformat(text)
        except ValueError as exc:
            raise ValueError(f"{label}: expected {_DATETIME_HINT}") from exc
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment


def handle_schedule(
    token: str,
    client_id: str,
    starts_raw: str,
    ends_raw: str,
    deps: UIDeps,
) -> str:
    """Schedule an appointment for the authenticated owner."""
    try:
        ctx = _require_ctx(token, deps)
    except InvalidCredentialsError:
        return "Please log in first."
    try:
        starts_at = _parse_moment(starts_raw, "starts_at")
        ends_at = _parse_moment(ends_raw, "ends_at")
        appt = deps.schedule_appointment.execute(
            user_id=ctx.user_id,
            client_id=(client_id or "").strip(),
            starts_at=starts_at,
            ends_at=ends_at,
            now=datetime.now(UTC),
        )
    except (ValueError, TypeError, AttributeError) as exc:
        return f"Scheduling failed: {exc}"
    return f"Scheduled: {appt.id.value} [{appt.starts_at:%Y-%m-%d %H:%M} UTC]"


def handle_list_appointments(token: str, deps: UIDeps) -> str:
    """List owned appointments as ``id | client | window | status`` lines."""
    try:
        ctx = _require_ctx(token, deps)
    except InvalidCredentialsError:
        return "Please log in first."
    appointments = deps.appointments_repo.list_by_user_id(ctx.user_id)
    if not appointments:
        return "(no appointments yet)"
    lines = []
    for appt in appointments:
        lines.append(
            f"{appt.id.value} | {appt.client_id} | "
            f"{appt.starts_at:%Y-%m-%d %H:%M}->{appt.ends_at:%H:%M} UTC | "
            f"{appt.status.value}"
        )
    return "\n".join(lines)


def _notes_text(
    deps: UIDeps, appointment_id: str, user_id: str
) -> str | None:
    """Best-effort notes lookup (adapter-local; port has no notes query)."""
    finder: Callable[..., Any] | None = getattr(
        deps.appointments_repo, "find_notes_by_appointment_and_user_id", None
    )
    if not callable(finder):
        return None
    try:
        from src.modules.appointments.domain.value_objects import AppointmentId

        notes = finder(AppointmentId(appointment_id), user_id)
    except ValueError:
        return None
    return notes.content if notes is not None else None


def handle_history(token: str, client_id: str, deps: UIDeps) -> tuple[str, str]:
    """Return ``(summary, notes_view)`` for one owned client."""
    try:
        ctx = _require_ctx(token, deps)
    except InvalidCredentialsError:
        return ("Please log in first.", "")
    try:
        history = deps.get_history.execute(
            user_id=ctx.user_id, client_id=(client_id or "").strip()
        )
    except (ValueError, TypeError, AttributeError) as exc:
        return (f"History failed: {exc}", "")
    header = (
        f"{history.client.name} <{history.client.email.value}> "
        f"({len(history.appointments)} appointment(s))"
    )
    if not history.appointments:
        return (header, "(no session notes yet)")
    appt_lines = []
    notes_blocks = []
    for appt in history.appointments:
        appt_lines.append(
            f"{appt.id.value} | {appt.starts_at:%Y-%m-%d %H:%M} UTC | "
            f"{appt.status.value}"
        )
        content = _notes_text(deps, appt.id.value, ctx.user_id)
        if content:
            notes_blocks.append(f"[{appt.id.value}]\n{content}")
    notes_view = "\n\n".join(notes_blocks) if notes_blocks else "(no session notes yet)"
    return (header + "\n" + "\n".join(appt_lines), notes_view)


def handle_complete(
    token: str, appointment_id: str, content: str, deps: UIDeps
) -> str:
    """Complete an appointment and persist manual session notes.

    T10-D1 bridge (documented in one place): the ``CompleteAppointment``
    use-case validates notes but persists only the appointment row through
    the frozen port. When the injected repo exposes the adapter-local
    ``save_with_notes``, the same validated content is persisted in ONE
    transaction; with fakes the port save already holds the status.
    """
    try:
        ctx = _require_ctx(token, deps)
    except InvalidCredentialsError:
        return "Please log in first."
    content_text = content or ""
    try:
        result = deps.complete_appointment.execute(
            appointment_id=(appointment_id or "").strip(),
            user_id=ctx.user_id,
            content=content_text,
        )
    except (ValueError, TypeError, AttributeError) as exc:
        return f"Complete failed: {exc}"
    saver: Callable[..., Any] | None = getattr(
        deps.appointments_repo, "save_with_notes", None
    )
    if callable(saver):
        try:
            notes = result.attach_notes(content_text)
            saver(result, notes)
        except (ValueError, TypeError, AttributeError) as exc:  # defensive only
            return f"Complete failed: {exc}"
    return f"Completed {result.id.value} with notes ({len(content_text.strip())} chars)."


# ---------------------------------------------------------------------------
# Gradio wiring (thin; handlers above hold the logic)
# ---------------------------------------------------------------------------


def build_demo(deps: UIDeps) -> gr.Blocks:
    """Build the ChronoLog dashboard (auth + Clients/Scheduler/History tabs)."""
    with gr.Blocks(title="ChronoLog") as demo:
        gr.Markdown("# ChronoLog — Appointment & Session Management (MVP)")
        token_state = gr.State("")
        with gr.Row():
            email = gr.Textbox(label="Email", placeholder="pro@example.com")
            password = gr.Textbox(
                label="Password", type="password", placeholder="minimum 8 characters"
            )
        with gr.Row():
            login_btn = gr.Button("Login", variant="primary")
            register_btn = gr.Button("Register")
            logout_btn = gr.Button("Logout")
        auth_status = gr.Textbox(label="Auth status", interactive=False)
        user_label = gr.Textbox(label="Signed in as (user_id)", interactive=False)

        def _login(email_v: str, password_v: str) -> tuple[str, str, str]:
            return handle_login(email_v, password_v, "gradio-ui", deps)

        def _register(email_v: str, password_v: str) -> str:
            return handle_register(email_v, password_v, deps)

        def _logout_and_clear(
            token_v: str,
        ) -> tuple[str, str, str, str, str, str, str, str, str, str]:
            """Revoke the session and clear every data view (no stale rows)."""
            status, cleared, label = handle_logout(token_v, deps)
            return (
                status,
                cleared,
                label,
                "",
                "(no clients yet)",
                "",
                "(no appointments yet)",
                "",
                "",
                "",
            )

        def _save_client_and_refresh(
            t: str, n: str, e: str, p: str
        ) -> tuple[str, str]:
            """Register then immediately refresh the client list (TSK-017)."""
            status = handle_create_client(t, n, e, p, deps)
            return status, handle_list_clients(t, deps)

        def _schedule_and_refresh(
            t: str, c: str, s: str, e: str
        ) -> tuple[str, str]:
            """Schedule then immediately refresh the appointment list."""
            status = handle_schedule(t, c, s, e, deps)
            return status, handle_list_appointments(t, deps)

        def _complete_and_refresh(
            t: str, a: str, c: str
        ) -> tuple[str, str, str, str]:
            """Complete, then refresh status list + history (best-effort)."""
            status = handle_complete(t, a, c, deps)
            sched_view = handle_list_appointments(t, deps)
            try:
                ctx = _require_ctx(t, deps)
                from src.modules.appointments.domain.value_objects import (
                    AppointmentId,
                )

                appt = deps.appointments_repo.find_by_id_and_user_id(
                    AppointmentId((a or "").strip()), ctx.user_id
                )
                if appt is not None:
                    hist_summary, hist_notes = handle_history(
                        t, appt.client_id, deps
                    )
                else:
                    hist_summary, hist_notes = "", ""
            except (ValueError, TypeError, AttributeError):
                hist_summary, hist_notes = "", ""
            return status, sched_view, hist_summary, hist_notes

        login_btn.click(
            _login, inputs=[email, password], outputs=[auth_status, token_state, user_label]
        )
        register_btn.click(_register, inputs=[email, password], outputs=[auth_status])

        with gr.Tabs():
            with gr.Tab("Clients"):
                gr.Markdown("Register a client profile — the list refreshes automatically.")
                name = gr.Textbox(label="Full name", placeholder="Alice Smith")
                client_email = gr.Textbox(
                    label="Client email", placeholder="alice@example.com"
                )
                phone = gr.Textbox(
                    label="Phone (optional)", placeholder="+34600111222"
                )
                with gr.Row():
                    client_save = gr.Button("Register client", variant="primary")
                    client_refresh = gr.Button("Refresh list")
                client_status = gr.Textbox(label="Result", interactive=False)
                client_list = gr.Textbox(
                    label="My clients (id | name | email | phone)", interactive=False
                )
                client_save.click(
                    _save_client_and_refresh,
                    inputs=[token_state, name, client_email, phone],
                    outputs=[client_status, client_list],
                )
                client_refresh.click(
                    lambda t: handle_list_clients(t, deps),
                    inputs=[token_state],
                    outputs=[client_list],
                )
            with gr.Tab("Scheduler"):
                gr.Markdown(
                    "Schedule with a client id from the Clients tab. "
                    f"Times: {_DATETIME_HINT}."
                )
                sched_client = gr.Textbox(label="Client id (UUID)")
                starts = gr.Textbox(
                    label="Starts at", placeholder="2026-10-15 10:00"
                )
                ends = gr.Textbox(label="Ends at", placeholder="2026-10-15 11:00")
                with gr.Row():
                    sched_btn = gr.Button("Schedule", variant="primary")
                    sched_refresh = gr.Button("Refresh list")
                sched_status = gr.Textbox(label="Result", interactive=False)
                sched_list = gr.Textbox(
                    label="My appointments (id | client | window | status)",
                    interactive=False,
                )
                sched_btn.click(
                    _schedule_and_refresh,
                    inputs=[token_state, sched_client, starts, ends],
                    outputs=[sched_status, sched_list],
                )
                sched_refresh.click(
                    lambda t: handle_list_appointments(t, deps),
                    inputs=[token_state],
                    outputs=[sched_list],
                )
            with gr.Tab("History"):
                gr.Markdown("Client history plus manual session notes review.")
                hist_client = gr.Textbox(label="Client id (UUID)")
                hist_btn = gr.Button("Load history", variant="primary")
                hist_summary = gr.Textbox(label="Client + appointments", interactive=False)
                hist_notes = gr.Textbox(label="Session notes", interactive=False)
                hist_btn.click(
                    lambda t, c: handle_history(t, c, deps),
                    inputs=[token_state, hist_client],
                    outputs=[hist_summary, hist_notes],
                )
                gr.Markdown("Complete an appointment with manual notes:")
                complete_appt = gr.Textbox(label="Appointment id (UUID)")
                complete_notes = gr.Textbox(
                    label="Session notes", lines=4, placeholder="Manual summary..."
                )
                complete_btn = gr.Button("Complete with notes")
                complete_status = gr.Textbox(label="Result", interactive=False)
                complete_btn.click(
                    _complete_and_refresh,
                    inputs=[token_state, complete_appt, complete_notes],
                    outputs=[
                        complete_status,
                        sched_list,
                        hist_summary,
                        hist_notes,
                    ],
                )
        # Logout last: clears the session AND every data view so the next
        # user never sees stale rows (all components exist by now).
        logout_btn.click(
            _logout_and_clear,
            inputs=[token_state],
            outputs=[
                auth_status,
                token_state,
                user_label,
                client_status,
                client_list,
                sched_status,
                sched_list,
                hist_summary,
                hist_notes,
                complete_status,
            ],
        )
    return demo
