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
from datetime import UTC, date, datetime
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

# TSK-018.1: top-level navigation (auth-gated shell). Tabs live inside the
# hidden app shell so unauthenticated users never see data controls.
NAV_TABS: tuple[str, str, str, str] = ("Dashboard", "Clients", "Agenda", "History")

# TSK-018.2: user-friendly scheduling controls (no manual ISO, no UUIDs).
# Date comes from a calendar picker (gr.DateTime), time + duration from
# dropdowns. Values stay hidden (UUID) while labels show human names.
DURATION_CHOICES: tuple[str, str, str, str] = (
    "30 minutes",
    "60 minutes",
    "90 minutes",
    "120 minutes",
)
TIME_CHOICES: tuple[str, ...] = (
    "08:00",
    "08:30",
    "09:00",
    "09:30",
    "10:00",
    "10:30",
    "11:00",
    "11:30",
    "12:00",
    "12:30",
    "13:00",
    "13:30",
    "14:00",
    "14:30",
    "15:00",
    "15:30",
    "16:00",
    "16:30",
    "17:00",
    "17:30",
    "18:00",
    "18:30",
    "19:00",
    "19:30",
)

_STATUS_LABELS = {
    "scheduled": "Scheduled",
    "completed": "Completed",
    "cancelled": "Cancelled",
}


def format_status(status_value: str | Any) -> str:
    """Return a human-readable status label (Title case, never raw enum)."""
    inner = getattr(status_value, "value", status_value)
    try:
        text = str(inner or "")
    except (TypeError, ValueError):
        text = ""
    normalized = text.strip().lower()
    return _STATUS_LABELS.get(normalized, normalized.title() if normalized else "Unknown")


def format_client_label(client: Any) -> str:
    """Return a human-readable client label (name + email, no UUID)."""
    try:
        name = str(client.name)
    except (AttributeError, TypeError, ValueError):
        name = "Unknown client"
    try:
        email_val = str(client.email.value)
    except (AttributeError, TypeError, ValueError):
        email_val = ""
    label = name.strip() or "Unknown client"
    if email_val.strip():
        label = f"{label} <{email_val.strip()}>"
    return label


def _friendly_appt_line(starts_at: datetime, ends_at: datetime, client_name: str, status: str | Any) -> str:
    """Format one appointment line: name, date, time window, status (no ids)."""
    name = (client_name or "").strip() or "Unknown client"
    date_part = f"{starts_at:%d/%m/%Y}"
    window = f"{starts_at:%H:%M}–{ends_at:%H:%M} UTC"
    return f"{name} · {date_part} {window} · {format_status(status)}"


def parse_friendly_date(raw: Any) -> date:
    """Parse a calendar-picker date into a ``date`` (friendly errors only)."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise ValueError("Please choose a date from the calendar.")
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    if isinstance(raw, (int, float)):
        try:
            return datetime.fromtimestamp(float(raw), tz=UTC).date()
        except (ValueError, TypeError, OverflowError, OSError) as exc:
            raise ValueError("Please choose a valid date from the calendar.") from exc
    if isinstance(raw, str):
        text = raw.strip()
        # Gradio DateTime (string) may include time: try full text per format.
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
            try:
                return datetime.strptime(text, fmt).date()  # noqa: DTZ007 — date-only, no tz needed
            except ValueError:
                continue
        # ISO with timezone / space-separated datetime: take leading YYYY-MM-DD.
        try:
            return datetime.fromisoformat(text).date()
        except ValueError:
            pass
        # Bare "YYYY-MM-DD ..." prefix fallback.
        try:
            return datetime.strptime(text[:10], "%Y-%m-%d").date()  # noqa: DTZ007 — date-only, no tz needed
        except ValueError as exc:
            raise ValueError("Please choose a valid date from the calendar.") from exc
    raise ValueError("Please choose a valid date from the calendar.")


def parse_friendly_time(raw: Any) -> tuple[int, int]:
    """Parse an ``HH:MM`` time-slot choice into ``(hour, minute)``."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise ValueError("Please choose a start time.")
    text = str(raw).strip()
    parts = text.split(":")
    if len(parts) != 2:
        raise ValueError("Please choose a valid start time (e.g. 16:00).")
    try:
        hour = int(parts[0].strip())
        minute = int(parts[1].strip()[:2])
    except ValueError as exc:
        raise ValueError("Please choose a valid start time (e.g. 16:00).") from exc
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("Please choose a valid start time (e.g. 16:00).")
    return hour, minute


def parse_friendly_duration(raw: Any) -> int:
    """Parse a duration choice (``60 minutes`` / ``60`` / int) into minutes."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise ValueError("Please choose a duration.")
    if isinstance(raw, int) and not isinstance(raw, bool):
        minutes = raw
    elif isinstance(raw, float):
        minutes = int(raw)
    else:
        text = str(raw).strip().lower()
        digits = ""
        for ch in text:
            if ch.isdigit():
                digits += ch
            elif digits:
                break
        if not digits:
            raise ValueError("Please choose a valid duration (e.g. 60 minutes).")
        try:
            minutes = int(digits)
        except ValueError as exc:
            raise ValueError("Please choose a valid duration (e.g. 60 minutes).") from exc
        if "hour" in text and "minute" not in text and len(digits) <= 2:
            # "1 hour" / "2 hours" -> minutes.
            minutes = minutes * 60
    if minutes not in (15, 30, 45, 60, 90, 120, 180) and not (5 <= minutes <= 480):
        raise ValueError("Please choose a valid duration (e.g. 60 minutes).")
    return minutes


def compose_schedule_window(
    date_raw: Any, time_raw: Any, duration_raw: Any, _unused: Any = None
) -> tuple[datetime, datetime]:
    """Compose tz-aware ``(starts_at, ends_at)`` UTC from friendly controls.

    Accepts calendar-picker dates, ``HH:MM`` time slots and duration
    choices. Raises ``ValueError`` with user-facing guidance (never raw
    tracebacks); handlers convert it to inline messages.
    """
    picked = parse_friendly_date(date_raw)
    hour, minute = parse_friendly_time(time_raw)
    minutes = parse_friendly_duration(duration_raw)
    from datetime import timedelta

    starts_at = datetime(picked.year, picked.month, picked.day, hour, minute, tzinfo=UTC)
    ends_at = starts_at + timedelta(minutes=minutes)
    return starts_at, ends_at


def format_user_indicator(email: str | None) -> str:
    """Return a user-friendly signed-in label (email only, no ids/tokens)."""
    normalized = (email or "").strip()
    if not normalized:
        return ""
    return f"Signed in as {normalized}"


def auth_shell_visibility(authenticated: bool) -> tuple[bool, bool]:
    """Return ``(auth_visible, shell_visible)`` for one auth state.

    Pure visibility helper (no data access): unauthenticated shows only the
    auth screen, authenticated shows only the app shell.
    """
    return (not authenticated, authenticated)


def is_authenticated(token: str | None, deps: UIDeps) -> bool:
    """Return True when ``token`` resolves to a live session (no oracle)."""
    if not isinstance(token, str) or not token.strip():
        return False
    try:
        _require_ctx(token, deps)
    except (InvalidCredentialsError, ValueError, TypeError, AttributeError):
        return False
    return True


def handle_nav_select(tab: str) -> str:
    """Select a top-level tab without touching any data (pure, no deps)."""
    if tab in NAV_TABS:
        return tab
    return NAV_TABS[0]


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
    The label is the normalized account email (never ``user_id``/token).
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
    return ("Login ok.", session.token, (email or "").strip().lower())


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
    # TSK-018.2: human-readable confirmation, UUID stays internal.
    return f"Client saved: {client.name} <{client.email.value}>"


def _client_name_map(deps: UIDeps, user_id: str) -> dict[str, str]:
    """Map owned ``client_id -> name`` for human-readable lists (best-effort)."""
    try:
        clients = deps.clients_repo.list_by_user_id(user_id)
    except (ValueError, TypeError, AttributeError):
        return {}
    mapping: dict[str, str] = {}
    for client in clients:
        try:
            mapping[str(client.id.value)] = str(client.name)
        except (AttributeError, TypeError, ValueError):
            continue
    return mapping


def get_client_choices(token: str | None, deps: UIDeps) -> list[tuple[str, str]]:
    """Return ``[(label, value)]`` for owned clients (label=name, value=UUID).

    Labels are human-readable (``Name <email>``), values are internal UUIDs
    for dropdowns. Unauthenticated/invalid tokens yield ``[]`` (no traceback,
    no oracle). Foreign clients never appear (scoped by ``ctx.user_id``).
    """
    try:
        ctx = _require_ctx(token if isinstance(token, str) else "", deps)
    except (InvalidCredentialsError, ValueError, TypeError, AttributeError):
        return []
    try:
        clients = deps.clients_repo.list_by_user_id(ctx.user_id)
    except (ValueError, TypeError, AttributeError):
        return []
    ordered = sorted(clients, key=lambda c: str(getattr(c, "name", "")).lower())
    choices: list[tuple[str, str]] = []
    for client in ordered:
        try:
            cid = str(client.id.value)
            label = format_client_label(client)
        except (AttributeError, TypeError, ValueError):
            continue
        # Labels must never leak UUIDs (value holds the id, hidden).
        if cid in label:
            label = str(client.name)
        choices.append((label, cid))
    return choices


def get_appointment_choices(token: str | None, deps: UIDeps) -> list[tuple[str, str]]:
    """Return ``[(label, value)]`` for owned SCHEDULED appointments.

    Labels are human-readable (``Name · DD/MM/YYYY HH:MM–HH:MM UTC ·
    Scheduled``), values are internal UUIDs. Sorted ascending by
    ``starts_at``. Unauthenticated/invalid tokens yield ``[]``.
    """
    try:
        ctx = _require_ctx(token if isinstance(token, str) else "", deps)
    except (InvalidCredentialsError, ValueError, TypeError, AttributeError):
        return []
    try:
        appointments = deps.appointments_repo.list_by_user_id(ctx.user_id)
    except (ValueError, TypeError, AttributeError):
        return []
    names = _client_name_map(deps, ctx.user_id)
    scheduled = [
        a for a in appointments if str(getattr(getattr(a, "status", ""), "value", a.status)) == "scheduled"
    ]
    try:
        ordered = sorted(scheduled, key=lambda a: a.starts_at)
    except (TypeError, AttributeError, ValueError):
        ordered = scheduled
    choices: list[tuple[str, str]] = []
    for appt in ordered:
        try:
            aid = str(appt.id.value)
            cname = names.get(str(appt.client_id), "Unknown client")
            label = _friendly_appt_line(appt.starts_at, appt.ends_at, cname, appt.status)
        except (AttributeError, TypeError, ValueError):
            continue
        choices.append((label, aid))
    return choices


def handle_list_clients(token: str, deps: UIDeps) -> str:
    """List owned clients as human-readable lines (no UUIDs)."""
    try:
        ctx = _require_ctx(token, deps)
    except InvalidCredentialsError:
        return "Please log in first."
    try:
        clients = deps.clients_repo.list_by_user_id(ctx.user_id)
    except (ValueError, TypeError, AttributeError) as exc:
        return f"Could not load clients: {exc}"
    if not clients:
        return "(no clients yet) — add your first client using the form above."
    ordered = sorted(clients, key=lambda c: str(c.name).lower())
    lines = []
    for client in ordered:
        try:
            phone = client.phone.value if client.phone is not None else "-"
        except (AttributeError, TypeError, ValueError):
            phone = "-"
        lines.append(f"{client.name} <{client.email.value}> · {phone}")
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
    """Schedule an appointment for the authenticated owner (raw ISO path)."""
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
        text = str(exc)
        if "overlap" in text.lower():
            return "Scheduling failed: that time overlaps another appointment. Please choose another time."
        return f"Scheduling failed: {exc}"
    # TSK-018.2: human-readable confirmation (UUID internal, name shown).
    names = _client_name_map(deps, ctx.user_id)
    cname = names.get(str(appt.client_id), "your client")
    return f"Scheduled appointment with {cname} for {appt.starts_at:%d/%m/%Y %H:%M} UTC"


def _resolve_client_name(deps: UIDeps, user_id: str, client_id: str) -> str:
    """Best-effort owned client name (never raises, never leaks ids)."""
    try:
        from src.modules.clients.domain.value_objects import ClientId

        found = deps.clients_repo.find_by_id_and_user_id(ClientId(client_id), user_id)
    except (ValueError, TypeError, AttributeError):
        return "your client"
    if found is None:
        return "your client"
    try:
        return str(found.name)
    except (AttributeError, TypeError, ValueError):
        return "your client"


def handle_schedule_friendly(
    token: str | None,
    client_value: str | None,
    date_raw: Any,
    time_raw: Any,
    duration_raw: Any,
    deps: UIDeps,
) -> str:
    """Schedule via friendly controls (dropdown value + date/time/duration).

    Delegates to the existing ``ScheduleAppointment`` use-case (domain stays
    authoritative for overlap/ownership/window). All invalid/empty selections
    return inline guidance, never tracebacks, never UUIDs.
    """
    try:
        ctx = _require_ctx(token if isinstance(token, str) else "", deps)
    except InvalidCredentialsError:
        return "Please log in first."
    selected = (client_value or "").strip() if isinstance(client_value, str) else ""
    if not selected:
        return "Please choose one of your clients to schedule."
    try:
        starts_at, ends_at = compose_schedule_window(date_raw, time_raw, duration_raw)
    except (ValueError, TypeError, AttributeError) as exc:
        return f"Scheduling failed: {exc}"
    try:
        appt = deps.schedule_appointment.execute(
            user_id=ctx.user_id,
            client_id=selected,
            starts_at=starts_at,
            ends_at=ends_at,
            now=datetime.now(UTC),
        )
    except (ValueError, TypeError, AttributeError) as exc:
        text = str(exc)
        if "overlap" in text.lower():
            return "Scheduling failed: that time overlaps another appointment. Please choose another time."
        return f"Scheduling failed: {exc}"
    cname = _resolve_client_name(deps, ctx.user_id, appt.client_id)
    return f"Scheduled appointment with {cname} for {appt.starts_at:%d/%m/%Y %H:%M} UTC"


def handle_edit_appointment(
    token: str | None,
    appointment_value: str | None,
    date_raw: Any,
    time_raw: Any,
    duration_raw: Any,
    deps: UIDeps,
) -> str:
    """Reschedule an owned SCHEDULED appointment via friendly controls.

    Ownership via ``find_by_id_and_user_id``; window validated by reusing the
    domain ``Appointment.schedule`` factory; overlap via
    ``list_overlapping(..., exclude_appointment_id=self)``; persist via
    ``save``. Only orchestration lives here (no business rules moved).
    """
    try:
        ctx = _require_ctx(token if isinstance(token, str) else "", deps)
    except InvalidCredentialsError:
        return "Please log in first."
    selected = (appointment_value or "").strip() if isinstance(appointment_value, str) else ""
    if not selected:
        return "Please choose a scheduled appointment to edit."
    try:
        from src.modules.appointments.domain.entities import Appointment
        from src.modules.appointments.domain.value_objects import AppointmentId

        current = deps.appointments_repo.find_by_id_and_user_id(
            AppointmentId(selected), ctx.user_id
        )
    except (ValueError, TypeError, AttributeError) as exc:
        return f"Could not update appointment: {exc}"
    if current is None:
        return "That appointment was not found. It may belong to another user."
    try:
        status_val = str(current.status.value)
    except (AttributeError, TypeError, ValueError):
        status_val = str(getattr(current, "status", ""))
    if status_val != "scheduled":
        return "Only scheduled appointments can be edited."
    try:
        starts_at, ends_at = compose_schedule_window(date_raw, time_raw, duration_raw)
    except (ValueError, TypeError, AttributeError) as exc:
        return f"Could not update appointment: {exc}"
    try:
        # Reuse domain window validation (past / ends<=starts / naive).
        Appointment.schedule(
            id=current.id,
            user_id=current.user_id,
            client_id=current.client_id,
            starts_at=starts_at,
            ends_at=ends_at,
            now=datetime.now(UTC),
        )
    except (ValueError, TypeError, AttributeError) as exc:
        return f"Could not update appointment: {exc}"
    try:
        clashes = deps.appointments_repo.list_overlapping(
            ctx.user_id, starts_at, ends_at, exclude_appointment_id=current.id
        )
    except (ValueError, TypeError, AttributeError) as exc:
        return f"Could not update appointment: {exc}"
    if clashes:
        return "Could not update appointment: that time overlaps another appointment. Please choose another time."
    current.starts_at = starts_at
    current.ends_at = ends_at
    try:
        deps.appointments_repo.save(current)
    except (ValueError, TypeError, AttributeError) as exc:
        return f"Could not update appointment: {exc}"
    cname = _resolve_client_name(deps, ctx.user_id, current.client_id)
    return f"Appointment updated: {cname} on {starts_at:%d/%m/%Y %H:%M} UTC"


def handle_cancel_appointment(
    token: str | None, appointment_value: str | None, deps: UIDeps
) -> str:
    """Cancel an owned SCHEDULED appointment via the domain lifecycle.

    Loads via ``find_by_id_and_user_id`` (ownership), calls the existing
    ``Appointment.cancel()`` (only SCHEDULED may cancel), persists via
    ``save``. No new lifecycle invented.
    """
    try:
        ctx = _require_ctx(token if isinstance(token, str) else "", deps)
    except InvalidCredentialsError:
        return "Please log in first."
    selected = (appointment_value or "").strip() if isinstance(appointment_value, str) else ""
    if not selected:
        return "Please choose a scheduled appointment to cancel."
    try:
        from src.modules.appointments.domain.value_objects import AppointmentId

        current = deps.appointments_repo.find_by_id_and_user_id(
            AppointmentId(selected), ctx.user_id
        )
    except (ValueError, TypeError, AttributeError) as exc:
        return f"Cancel failed: {exc}"
    if current is None:
        return "That appointment was not found. It may belong to another user."
    try:
        current.cancel()
    except (ValueError, TypeError, AttributeError) as exc:
        return f"Cancel failed: {exc}"
    try:
        deps.appointments_repo.save(current)
    except (ValueError, TypeError, AttributeError) as exc:
        return f"Cancel failed: {exc}"
    cname = _resolve_client_name(deps, ctx.user_id, current.client_id)
    return f"Appointment cancelled: {cname} on {current.starts_at:%d/%m/%Y %H:%M} UTC"


def handle_agenda(token: str | None, deps: UIDeps) -> str:
    """Return the upcoming SCHEDULED agenda in chronological order (friendly)."""
    try:
        ctx = _require_ctx(token if isinstance(token, str) else "", deps)
    except InvalidCredentialsError:
        return "Please log in first."
    try:
        appointments = deps.appointments_repo.list_by_user_id(ctx.user_id)
    except (ValueError, TypeError, AttributeError) as exc:
        return f"Could not load agenda: {exc}"
    names = _client_name_map(deps, ctx.user_id)
    now = datetime.now(UTC)
    upcoming = []
    for appt in appointments:
        try:
            status_val = str(appt.status.value)
        except (AttributeError, TypeError, ValueError):
            continue
        if status_val != "scheduled":
            continue
        try:
            if appt.starts_at < now:
                continue
        except TypeError:
            continue
        upcoming.append(appt)
    if not upcoming:
        return "(no appointments yet) — no upcoming appointments. Use New appointment above to schedule."
    try:
        upcoming.sort(key=lambda a: a.starts_at)
    except (TypeError, AttributeError):
        pass
    lines = ["Upcoming appointments"]
    for appt in upcoming:
        try:
            cname = names.get(str(appt.client_id), "Unknown client")
            lines.append(
                _friendly_appt_line(appt.starts_at, appt.ends_at, cname, appt.status)
            )
        except (AttributeError, TypeError, ValueError):
            continue
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# TSK-018.3 polish: dashboard, search/filter, profiles, cancel confirmation.
# Pure orchestration over owned reads + GetClientHistory; no business rules,
# no new ports, no analytics. All messages concise and UUID-free.
# ---------------------------------------------------------------------------


def _day_greeting(now: datetime) -> str:
    """Return a time-of-day greeting (presentation formatting only)."""
    try:
        hour = now.hour
    except (AttributeError, TypeError, ValueError):
        return "Hello"
    if hour < 12:
        return "Good morning"
    if hour < 20:
        return "Good afternoon"
    return "Good evening"


def handle_dashboard(token: str | None, deps: UIDeps) -> str:
    """Return the lightweight landing overview (counts + today's list).

    Reads owned clients/appointments only (``ctx.user_id``), counts today /
    upcoming / clients / scheduled, and lists today's appointments as
    ``HH:MM  Name`` lines. Empty states carry the next action.
    """
    try:
        ctx = _require_ctx(token if isinstance(token, str) else "", deps)
    except InvalidCredentialsError:
        return "Please log in first."
    try:
        clients = deps.clients_repo.list_by_user_id(ctx.user_id)
        appointments = deps.appointments_repo.list_by_user_id(ctx.user_id)
    except (ValueError, TypeError, AttributeError) as exc:
        return f"Could not load dashboard: {exc}"
    names = _client_name_map(deps, ctx.user_id)
    now = datetime.now(UTC)
    today = now.date()
    n_today = 0
    n_upcoming = 0
    n_scheduled = 0
    today_items: list[tuple[datetime, str]] = []
    for appt in appointments or []:
        try:
            status_val = str(appt.status.value)
            starts = appt.starts_at
        except (AttributeError, TypeError, ValueError):
            continue
        if status_val == "scheduled":
            n_scheduled += 1
            try:
                is_upcoming = starts >= now
            except TypeError:
                is_upcoming = False
            if is_upcoming:
                n_upcoming += 1
        try:
            is_today = starts.date() == today
        except (AttributeError, TypeError, ValueError):
            is_today = False
        if is_today:
            n_today += 1
            cname = names.get(str(appt.client_id), "Unknown client")
            try:
                line = f"{starts:%H:%M}  {cname}"
            except (AttributeError, TypeError, ValueError):
                continue
            today_items.append((starts, line))
    try:
        today_items.sort(key=lambda item: item[0])
    except (TypeError, AttributeError):
        pass
    head = (
        f"{_day_greeting(now)} — here's your day at a glance.\n"
        f"Today: {n_today} appointment(s) · Upcoming: {n_upcoming} · "
        f"Clients: {len(clients or [])} · Scheduled: {n_scheduled}"
    )
    if today_items:
        body = "Today's appointments\n" + "\n".join(
            line for _, line in today_items
        )
        return head + "\n\n" + body
    parts = [head, "No appointments today."]
    if not (clients or []):
        parts.append("No clients yet — add your first client in Clients.")
    if n_upcoming == 0:
        parts.append(
            "No upcoming appointments — use + New appointment in Agenda to schedule."
        )
    return "\n".join(parts)


def handle_quick_new_client(token: str | None, deps: UIDeps) -> str:
    """Point the user at client creation (dashboard quick action)."""
    try:
        _require_ctx(token if isinstance(token, str) else "", deps)
    except InvalidCredentialsError:
        return "Please log in first."
    return "Open the Clients tab, fill the form, and click Register client."


def handle_quick_new_appointment(
    token: str | None, deps: UIDeps
) -> tuple[list[tuple[str, str]], str]:
    """Prepare the Agenda client list (dashboard quick action).

    Returns ``(choices, message)`` — choices refresh the scheduler
    dropdown so the Agenda tab is ready, message tells where to go.
    """
    try:
        _require_ctx(token if isinstance(token, str) else "", deps)
    except InvalidCredentialsError:
        return ([], "Please log in first.")
    choices = get_client_choices(token, deps)
    return (
        choices,
        "Client list ready: open the Agenda tab, choose a client, pick a date and time.",
    )


def search_client_choices(
    token: str | None, query: str | None, deps: UIDeps
) -> list[tuple[str, str]]:
    """Filter owned clients by name/email/phone substring (case-insensitive).

    Blank queries return every owned client; invalid tokens or non-string
    queries yield ``[]``. Labels stay human-readable, values stay hidden.
    """
    if not isinstance(query, str):
        return []
    if not query.strip():
        return get_client_choices(token, deps)
    try:
        ctx = _require_ctx(token if isinstance(token, str) else "", deps)
    except (InvalidCredentialsError, ValueError, TypeError, AttributeError):
        return []
    try:
        clients = deps.clients_repo.list_by_user_id(ctx.user_id)
    except (ValueError, TypeError, AttributeError):
        return []
    needle = query.strip().lower()
    matches = []
    for client in clients or []:
        try:
            name = str(client.name)
            email_val = str(client.email.value)
            phone_val = (
                str(client.phone.value) if client.phone is not None else ""
            )
        except (AttributeError, TypeError, ValueError):
            continue
        haystack = f"{name} {email_val} {phone_val}".lower()
        if needle in haystack:
            matches.append(client)
    ordered = sorted(matches, key=lambda c: str(getattr(c, "name", "")).lower())
    choices: list[tuple[str, str]] = []
    for client in ordered:
        try:
            cid = str(client.id.value)
            label = format_client_label(client)
        except (AttributeError, TypeError, ValueError):
            continue
        if cid in label:
            label = str(client.name)
        choices.append((label, cid))
    return choices


def handle_client_profile(
    token: str | None, client_value: str | None, deps: UIDeps
) -> str:
    """Return one client's profile: identity, upcoming, history, notes.

    History comes from the existing ``GetClientHistory`` use-case
    (chronological, no parallel implementation); notes reuse the
    adapter-local bridge. Ends with the schedule next action.
    """
    try:
        ctx = _require_ctx(token if isinstance(token, str) else "", deps)
    except InvalidCredentialsError:
        return "Please log in first."
    selected = (client_value or "").strip() if isinstance(client_value, str) else ""
    if not selected:
        return "Please choose one of your clients to view the profile."
    try:
        history = deps.get_history.execute(
            user_id=ctx.user_id, client_id=selected
        )
    except (ValueError, TypeError, AttributeError):
        return "That client was not found. It may belong to another user."
    client = history.client
    try:
        phone_val = client.phone.value if client.phone is not None else ""
    except (AttributeError, TypeError, ValueError):
        phone_val = ""
    identity = f"{client.name} <{client.email.value}>"
    if phone_val.strip():
        identity = f"{identity} · {phone_val.strip()}"
    now = datetime.now(UTC)
    upcoming_lines = []
    for appt in history.appointments:
        try:
            status_val = str(appt.status.value)
            starts = appt.starts_at
        except (AttributeError, TypeError, ValueError):
            continue
        if status_val != "scheduled":
            continue
        try:
            if starts < now:
                continue
        except TypeError:
            continue
        try:
            upcoming_lines.append(
                _friendly_appt_line(starts, appt.ends_at, client.name, appt.status)
            )
        except (AttributeError, TypeError, ValueError):
            continue
    history_lines = []
    notes_blocks = []
    for appt in history.appointments:
        try:
            history_lines.append(
                _friendly_appt_line(
                    appt.starts_at, appt.ends_at, client.name, appt.status
                )
            )
        except (AttributeError, TypeError, ValueError):
            continue
        content = _notes_text(deps, appt.id.value, ctx.user_id)
        if content:
            notes_blocks.append(f"[{appt.starts_at:%d/%m/%Y %H:%M}]\n{content}")
    parts = [identity]
    parts.append(f"Upcoming appointments ({len(upcoming_lines)})")
    if upcoming_lines:
        parts.extend(upcoming_lines)
    else:
        parts.append("No upcoming appointments for this client.")
    parts.append(f"History ({len(history_lines)} appointment(s))")
    if history_lines:
        parts.extend(history_lines)
    else:
        parts.append("No history for this client yet.")
    parts.append("Session notes")
    if notes_blocks:
        parts.extend(notes_blocks)
    else:
        parts.append("(no session notes yet)")
    parts.append("To schedule: open Agenda, choose this client, pick a date and time.")
    return "\n".join(parts)


def handle_profile_schedule_action(
    token: str | None, client_value: str | None, deps: UIDeps
) -> tuple[str | None, str]:
    """Target the Agenda scheduler at one owned client (profile action).

    Returns ``(client_uuid_or_None, message)`` — the UUID feeds the
    scheduler dropdown value (hidden), the message names the next step.
    """
    try:
        ctx = _require_ctx(token if isinstance(token, str) else "", deps)
    except InvalidCredentialsError:
        return (None, "Please log in first.")
    selected = (client_value or "").strip() if isinstance(client_value, str) else ""
    if not selected:
        return (None, "Please choose one of your clients to schedule.")
    try:
        from src.modules.clients.domain.value_objects import ClientId

        found = deps.clients_repo.find_by_id_and_user_id(
            ClientId(selected), ctx.user_id
        )
    except (ValueError, TypeError, AttributeError):
        return (None, "That client was not found. It may belong to another user.")
    if found is None:
        return (None, "That client was not found. It may belong to another user.")
    try:
        cname = str(found.name)
    except (AttributeError, TypeError, ValueError):
        cname = "your client"
    return (selected, f"Ready: open Agenda to schedule with {cname}.")


def request_cancel_confirmation(
    token: str | None, appointment_value: str | None, deps: UIDeps
) -> str:
    """Preview a cancellation and ask for explicit confirmation.

    Side-effect free: the appointment stays scheduled until the existing
    ``handle_cancel_appointment`` runs (Confirm cancel button).
    """
    try:
        ctx = _require_ctx(token if isinstance(token, str) else "", deps)
    except InvalidCredentialsError:
        return "Please log in first."
    selected = (
        (appointment_value or "").strip()
        if isinstance(appointment_value, str)
        else ""
    )
    if not selected:
        return "Please choose a scheduled appointment to cancel."
    try:
        from src.modules.appointments.domain.value_objects import AppointmentId

        current = deps.appointments_repo.find_by_id_and_user_id(
            AppointmentId(selected), ctx.user_id
        )
    except (ValueError, TypeError, AttributeError):
        return "That appointment was not found. It may belong to another user."
    if current is None:
        return "That appointment was not found. It may belong to another user."
    try:
        status_val = str(current.status.value)
    except (AttributeError, TypeError, ValueError):
        status_val = str(getattr(current, "status", ""))
    if status_val != "scheduled":
        return "Only scheduled appointments can be cancelled."
    cname = _resolve_client_name(deps, ctx.user_id, current.client_id)
    return (
        f"Are you sure you want to cancel {cname} on "
        f"{current.starts_at:%d/%m/%Y %H:%M} UTC? Click 'Confirm cancel' to proceed."
    )


def handle_list_appointments(token: str, deps: UIDeps) -> str:
    """List owned appointments as human-readable lines (no ids)."""
    try:
        ctx = _require_ctx(token, deps)
    except InvalidCredentialsError:
        return "Please log in first."
    try:
        appointments = deps.appointments_repo.list_by_user_id(ctx.user_id)
    except (ValueError, TypeError, AttributeError) as exc:
        return f"Could not load appointments: {exc}"
    if not appointments:
        return "(no appointments yet) — schedule your first appointment in Agenda."
    names = _client_name_map(deps, ctx.user_id)
    try:
        ordered = sorted(appointments, key=lambda a: a.starts_at)
    except (TypeError, AttributeError):
        ordered = appointments
    lines = []
    for appt in ordered:
        try:
            cname = names.get(str(appt.client_id), "Unknown client")
            lines.append(
                _friendly_appt_line(appt.starts_at, appt.ends_at, cname, appt.status)
            )
        except (AttributeError, TypeError, ValueError):
            continue
    return "\n".join(lines) if lines else "(no appointments yet) — schedule your first appointment in Agenda."


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
    """Return ``(summary, notes_view)`` for one owned client (no ids)."""
    try:
        ctx = _require_ctx(token, deps)
    except InvalidCredentialsError:
        return ("Please log in first.", "")
    selected = (client_id or "").strip() if isinstance(client_id, str) else ""
    if not selected:
        return ("Please choose one of your clients to view history.", "")
    try:
        history = deps.get_history.execute(
            user_id=ctx.user_id, client_id=selected
        )
    except (ValueError, TypeError, AttributeError) as exc:
        return (f"History failed: {exc}", "")
    header = (
        f"{history.client.name} <{history.client.email.value}> "
        f"({len(history.appointments)} appointment(s))"
    )
    if not history.appointments:
        return (header + "\nNo history for this client yet.", "(no session notes yet)")
    appt_lines = []
    notes_blocks = []
    for appt in history.appointments:
        try:
            label = _friendly_appt_line(
                appt.starts_at, appt.ends_at, history.client.name, appt.status
            )
        except (AttributeError, TypeError, ValueError):
            continue
        appt_lines.append(label)
        content = _notes_text(deps, appt.id.value, ctx.user_id)
        if content:
            notes_blocks.append(f"[{appt.starts_at:%d/%m/%Y %H:%M}]\n{content}")
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
    selected = (appointment_id or "").strip() if isinstance(appointment_id, str) else ""
    if not selected:
        return "Complete failed: please choose a scheduled appointment."
    content_text = content or ""
    try:
        result = deps.complete_appointment.execute(
            appointment_id=selected,
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
    cname = _resolve_client_name(deps, ctx.user_id, result.client_id)
    return (
        f"Completed appointment for {cname} on "
        f"{result.starts_at:%d/%m/%Y %H:%M} UTC with notes "
        f"({len(content_text.strip())} chars)."
    )


# ---------------------------------------------------------------------------
# Gradio wiring (thin; handlers above hold the logic)
# ---------------------------------------------------------------------------


def build_demo(deps: UIDeps) -> gr.Blocks:
    """Build the auth-gated ChronoLog shell (TSK-018.1 + 018.2 + 018.3).

    Unauthenticated: only the auth screen is visible. Authenticated: the
    app shell with ``Dashboard | Clients | Agenda | History`` plus a
    user indicator and Logout. Tab visibility alone never touches data —
    every data view loads only through an explicit authenticated action.

    TSK-018.2: no UUID textboxes. Clients/appointments are chosen from
    human-readable dropdowns (label=name, value=UUID hidden); scheduling
    uses calendar date + time-slot + duration controls composing tz-aware
    UTC windows via :func:`compose_schedule_window`.

    TSK-018.3: Dashboard landing (counts + today's list + quick actions),
    client search/filter + profile view (identity, upcoming, history via
    ``GetClientHistory``, notes, schedule action), and confirm-before-cancel
    (Cancel previews, Confirm cancel executes). Logout clears every view.
    """
    with gr.Blocks(title="ChronoLog") as demo:
        gr.Markdown("# ChronoLog — Appointment & Session Management (MVP)")
        token_state = gr.State("")

        with gr.Column(visible=True) as auth_screen:
            gr.Markdown("## ChronoLog\nSign in to manage appointments.")
            email = gr.Textbox(label="Email", placeholder="pro@example.com")
            password = gr.Textbox(
                label="Password", type="password", placeholder="minimum 8 characters"
            )
            with gr.Row():
                login_btn = gr.Button("Login", variant="primary")
                register_btn = gr.Button("Create account")
            auth_message = gr.Textbox(label="Sign-in message", interactive=False)

        with gr.Column(visible=False) as app_shell:
            with gr.Row():
                gr.Markdown("## ChronoLog")
                user_indicator = gr.Textbox(
                    label="Signed in as", interactive=False
                )
                logout_btn = gr.Button("Logout")

            with gr.Tabs():
                with gr.Tab("Dashboard"):
                    gr.Markdown(
                        "Your day at a glance — refresh to update counts."
                    )
                    dashboard_view = gr.Textbox(
                        label="Dashboard overview",
                        value="Press Refresh dashboard to load your overview.",
                        interactive=False,
                    )
                    with gr.Row():
                        dash_refresh = gr.Button("Refresh dashboard")
                        quick_client = gr.Button("+ New client")
                        quick_appt = gr.Button("+ New appointment")
                    dash_status = gr.Textbox(label="Result", interactive=False)
                with gr.Tab("Clients"):
                    gr.Markdown(
                        "Register a client profile — the list refreshes automatically."
                    )
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
                        label="My clients",
                        interactive=False,
                    )
                    search = gr.Textbox(
                        label="Search clients",
                        placeholder="Type a name or email...",
                    )
                    with gr.Row():
                        search_btn = gr.Button("Search")
                        profile_btn = gr.Button("View profile")
                    profile_client = gr.Dropdown(
                        label="Profile client",
                        choices=[],
                        info="Choose one of your clients",
                    )
                    profile_view = gr.Textbox(
                        label="Client profile",
                        interactive=False,
                    )
                    sched_for_client_btn = gr.Button("Schedule for this client")
                with gr.Tab("Agenda"):
                    gr.Markdown("## New appointment")
                    gr.Markdown(
                        "Choose one of your clients, pick a date and time, "
                        "then create the appointment."
                    )
                    sched_client = gr.Dropdown(
                        label="Client",
                        choices=[],
                        info="Choose one of your clients",
                    )
                    sched_date = gr.DateTime(
                        label="Date",
                        include_time=False,
                        type="string",
                        timezone="UTC",
                    )
                    sched_time = gr.Dropdown(
                        label="Time",
                        choices=list(TIME_CHOICES),
                        info="Start time",
                    )
                    sched_duration = gr.Dropdown(
                        label="Duration",
                        choices=list(DURATION_CHOICES),
                        value="60 minutes",
                    )
                    with gr.Row():
                        sched_btn = gr.Button("Create appointment", variant="primary")
                        agenda_refresh = gr.Button("Refresh agenda")
                    sched_status = gr.Textbox(label="Result", interactive=False)
                    agenda_view = gr.Textbox(
                        label="Upcoming agenda",
                        interactive=False,
                    )
                    gr.Markdown("## Manage scheduled appointments")
                    gr.Markdown(
                        "Choose a scheduled appointment to edit or cancel. "
                        "Completing happens in History with session notes."
                    )
                    appt_select = gr.Dropdown(
                        label="Appointment",
                        choices=[],
                        info="Choose a scheduled appointment",
                    )
                    edit_date = gr.DateTime(
                        label="New date",
                        include_time=False,
                        type="string",
                        timezone="UTC",
                    )
                    edit_time = gr.Dropdown(
                        label="New time",
                        choices=list(TIME_CHOICES),
                    )
                    edit_duration = gr.Dropdown(
                        label="New duration",
                        choices=list(DURATION_CHOICES),
                        value="60 minutes",
                    )
                    with gr.Row():
                        edit_btn = gr.Button("Edit appointment")
                        cancel_btn = gr.Button("Cancel appointment")
                        confirm_cancel_btn = gr.Button("Confirm cancel")
                    manage_status = gr.Textbox(label="Result", interactive=False)
                with gr.Tab("History"):
                    gr.Markdown("Client history plus manual session notes review.")
                    hist_client = gr.Dropdown(
                        label="Client",
                        choices=[],
                        info="Choose one of your clients",
                    )
                    with gr.Row():
                        hist_btn = gr.Button("Load history", variant="primary")
                        hist_refresh = gr.Button("Refresh clients")
                    hist_summary = gr.Textbox(
                        label="Client + appointments", interactive=False
                    )
                    hist_notes = gr.Textbox(label="Session notes", interactive=False)
                    gr.Markdown("Complete an appointment with manual notes:")
                    complete_appt = gr.Dropdown(
                        label="Appointment",
                        choices=[],
                        info="Choose a scheduled appointment",
                    )
                    complete_notes = gr.Textbox(
                        label="Session notes",
                        lines=4,
                        placeholder="Manual summary...",
                    )
                    with gr.Row():
                        complete_btn = gr.Button("Complete with notes")
                        appt_refresh = gr.Button("Refresh appointments")
                    complete_status = gr.Textbox(label="Result", interactive=False)

        def _login(
            email_v: str, password_v: str
        ) -> tuple[str, str, str, Any, Any]:
            """Login and toggle auth->shell visibility (no data fetch)."""
            message, token, label = handle_login(
                email_v, password_v, "gradio-ui", deps
            )
            authenticated = bool(token)
            auth_vis, shell_vis = auth_shell_visibility(authenticated)
            indicator = format_user_indicator(label) if authenticated else ""
            return (
                message,
                token,
                indicator,
                gr.update(visible=auth_vis),
                gr.update(visible=shell_vis),
            )

        def _register(email_v: str, password_v: str) -> str:
            return handle_register(email_v, password_v, deps)

        def _logout_and_clear(
            token_v: str,
        ) -> tuple[Any, ...]:
            """Revoke the session and clear every data view (no stale rows)."""
            status, cleared, _label = handle_logout(token_v, deps)
            auth_vis, shell_vis = auth_shell_visibility(False)
            return (
                status,
                cleared,
                "",
                gr.update(visible=auth_vis),
                gr.update(visible=shell_vis),
                "",
                "(no clients yet) — add your first client using the form above.",
                "",
                "(no appointments yet) — no upcoming appointments. Use New appointment above to schedule.",
                "",
                "",
                "",
                "",
                gr.update(choices=[], value=None),
                gr.update(choices=[], value=None),
                gr.update(choices=[], value=None),
                gr.update(choices=[], value=None),
                "",
                "",
                "",
                gr.update(choices=[], value=None),
                "",
            )

        def _register_client_and_refresh(
            t: str, n: str, e: str, p: str
        ) -> tuple[str, str, Any, Any, Any]:
            status = handle_create_client(t, n, e, p, deps)
            listing = handle_list_clients(t, deps)
            choices = get_client_choices(t, deps)
            return (
                status,
                listing,
                gr.update(choices=choices, value=None),
                gr.update(choices=choices, value=None),
                gr.update(choices=choices, value=None),
            )

        def _refresh_clients(t: str) -> tuple[str, Any, Any, Any]:
            listing = handle_list_clients(t, deps)
            choices = get_client_choices(t, deps)
            return (
                listing,
                gr.update(choices=choices, value=None),
                gr.update(choices=choices, value=None),
                gr.update(choices=choices, value=None),
            )

        def _create_and_refresh_agenda(
            t: str, c: str | None, d: Any, ti: Any, du: Any
        ) -> tuple[str, str, Any, Any]:
            status = handle_schedule_friendly(t, c, d, ti, du, deps)
            agenda = handle_agenda(t, deps)
            appts = get_appointment_choices(t, deps)
            return (
                status,
                agenda,
                gr.update(choices=appts, value=None),
                gr.update(choices=appts, value=None),
            )

        def _refresh_agenda(t: str) -> tuple[str, Any, Any, Any]:
            agenda = handle_agenda(t, deps)
            clients = get_client_choices(t, deps)
            appts = get_appointment_choices(t, deps)
            return (
                agenda,
                gr.update(choices=clients, value=None),
                gr.update(choices=appts, value=None),
                gr.update(choices=appts, value=None),
            )

        def _edit_and_refresh(
            t: str, a: str | None, d: Any, ti: Any, du: Any
        ) -> tuple[str, str, Any, Any]:
            status = handle_edit_appointment(t, a, d, ti, du, deps)
            agenda = handle_agenda(t, deps)
            appts = get_appointment_choices(t, deps)
            return (
                status,
                agenda,
                gr.update(choices=appts, value=None),
                gr.update(choices=appts, value=None),
            )

        def _cancel_and_refresh(t: str, a: str | None) -> tuple[str, str, Any, Any]:
            status = handle_cancel_appointment(t, a, deps)
            agenda = handle_agenda(t, deps)
            appts = get_appointment_choices(t, deps)
            return (
                status,
                agenda,
                gr.update(choices=appts, value=None),
                gr.update(choices=appts, value=None),
            )

        def _quick_appt_and_guide(t: str) -> tuple[Any, str]:
            choices, message = handle_quick_new_appointment(t, deps)
            return (gr.update(choices=choices, value=None), message)

        def _profile_to_agenda(t: str, c: str | None) -> tuple[Any, str]:
            value, message = handle_profile_schedule_action(t, c, deps)
            choices = get_client_choices(t, deps)
            return (gr.update(choices=choices, value=value), message)

        def _refresh_hist_clients(t: str) -> tuple[Any, str, str]:
            choices = get_client_choices(t, deps)
            return (gr.update(choices=choices, value=None), "", "")

        def _refresh_appt_choices(t: str) -> tuple[Any, Any, str]:
            appts = get_appointment_choices(t, deps)
            return (
                gr.update(choices=appts, value=None),
                gr.update(choices=appts, value=None),
                handle_agenda(t, deps),
            )

        # Clients tab wiring.
        client_save.click(
            _register_client_and_refresh,
            inputs=[token_state, name, client_email, phone],
            outputs=[client_status, client_list, sched_client, hist_client, profile_client],
        )
        client_refresh.click(
            _refresh_clients,
            inputs=[token_state],
            outputs=[client_list, sched_client, hist_client, profile_client],
        )
        # Agenda tab wiring.
        sched_btn.click(
            _create_and_refresh_agenda,
            inputs=[token_state, sched_client, sched_date, sched_time, sched_duration],
            outputs=[sched_status, agenda_view, appt_select, complete_appt],
        )
        agenda_refresh.click(
            _refresh_agenda,
            inputs=[token_state],
            outputs=[agenda_view, sched_client, appt_select, complete_appt],
        )
        edit_btn.click(
            _edit_and_refresh,
            inputs=[token_state, appt_select, edit_date, edit_time, edit_duration],
            outputs=[manage_status, agenda_view, appt_select, complete_appt],
        )
        # TSK-018.3 polish wiring: dashboard, search/profile, cancel confirm.
        # Cancel asks for confirmation first; Confirm runs the domain cancel.
        cancel_btn.click(
            lambda t, a: request_cancel_confirmation(t, a, deps),
            inputs=[token_state, appt_select],
            outputs=[manage_status],
        )
        confirm_cancel_btn.click(
            _cancel_and_refresh,
            inputs=[token_state, appt_select],
            outputs=[manage_status, agenda_view, appt_select, complete_appt],
        )
        dash_refresh.click(
            lambda t: handle_dashboard(t, deps),
            inputs=[token_state],
            outputs=[dashboard_view],
        )
        quick_client.click(
            lambda t: handle_quick_new_client(t, deps),
            inputs=[token_state],
            outputs=[dash_status],
        )
        quick_appt.click(
            _quick_appt_and_guide,
            inputs=[token_state],
            outputs=[sched_client, dash_status],
        )
        search_btn.click(
            lambda t, q: gr.update(
                choices=search_client_choices(t, q, deps), value=None
            ),
            inputs=[token_state, search],
            outputs=[profile_client],
        )
        profile_btn.click(
            lambda t, c: handle_client_profile(t, c, deps),
            inputs=[token_state, profile_client],
            outputs=[profile_view],
        )
        sched_for_client_btn.click(
            _profile_to_agenda,
            inputs=[token_state, profile_client],
            outputs=[sched_client, client_status],
        )
        # History tab wiring.
        hist_btn.click(
            lambda t, c: handle_history(t, c, deps),
            inputs=[token_state, hist_client],
            outputs=[hist_summary, hist_notes],
        )
        hist_refresh.click(
            _refresh_hist_clients,
            inputs=[token_state],
            outputs=[hist_client, hist_summary, hist_notes],
        )
        appt_refresh.click(
            _refresh_appt_choices,
            inputs=[token_state],
            outputs=[appt_select, complete_appt, agenda_view],
        )
        complete_btn.click(
            lambda t, a, c: _complete_and_refresh(t, a, c, deps),
            inputs=[token_state, complete_appt, complete_notes],
            outputs=[
                complete_status,
                agenda_view,
                appt_select,
                complete_appt,
                hist_summary,
                hist_notes,
            ],
        )

        login_btn.click(
            _login,
            inputs=[email, password],
            outputs=[
                auth_message,
                token_state,
                user_indicator,
                auth_screen,
                app_shell,
            ],
        )
        register_btn.click(
            _register, inputs=[email, password], outputs=[auth_message]
        )
        # Logout last: clears the session AND every data view so the next
        # user never sees stale rows (all components exist by now).
        logout_btn.click(
            _logout_and_clear,
            inputs=[token_state],
            outputs=[
                auth_message,
                token_state,
                user_indicator,
                auth_screen,
                app_shell,
                client_status,
                client_list,
                sched_status,
                agenda_view,
                manage_status,
                hist_summary,
                hist_notes,
                complete_status,
                sched_client,
                appt_select,
                hist_client,
                complete_appt,
                dashboard_view,
                dash_status,
                search,
                profile_client,
                profile_view,
            ],
        )
    return demo


def _complete_and_refresh(
    t: str, a: str, c: str, deps: UIDeps
) -> tuple[str, str, Any, Any, str, str]:
    """Complete, then refresh agenda + choices + history (best-effort)."""
    status = handle_complete(t, a, c, deps)
    agenda = handle_agenda(t, deps)
    appts = get_appointment_choices(t, deps)
    try:
        ctx = _require_ctx(t, deps)
        from src.modules.appointments.domain.value_objects import (
            AppointmentId,
        )

        appt = deps.appointments_repo.find_by_id_and_user_id(
            AppointmentId((a or "").strip()), ctx.user_id
        )
        if appt is not None:
            hist_summary, hist_notes = handle_history(t, appt.client_id, deps)
        else:
            hist_summary, hist_notes = "", ""
    except (ValueError, TypeError, AttributeError):
        hist_summary, hist_notes = "", ""
    return (
        status,
        agenda,
        gr.update(choices=appts, value=None),
        gr.update(choices=appts, value=None),
        hist_summary,
        hist_notes,
    )
