"""TSK-017: None-input hardening (Gradio edge — never leak tracebacks).

Audit found handlers raised ``AttributeError`` on ``None`` inputs (cleared
fields / programmatic calls). Every path must return a friendly UI error.
Covers register/login/client/schedule; complete-None is covered via the
unknown-appointment friendly path plus ``content or ""`` normalization.
"""

from __future__ import annotations

from src.presentation import app as A
from tests.presentation.test_app_wiring import _deps, _login


def test_none_client_name_returns_friendly_error() -> None:
    deps, _ = _deps()
    token = _login(deps, "n17a@example.com")
    out = A.handle_create_client(token, None, "a@b.com", "", deps)  # type: ignore[arg-type]
    assert "failed" in out.lower()


def test_none_client_email_returns_friendly_error() -> None:
    deps, _ = _deps()
    token = _login(deps, "n17b@example.com")
    out = A.handle_create_client(token, "A", None, "", deps)  # type: ignore[arg-type]
    assert "failed" in out.lower()


def test_none_schedule_starts_returns_hint_error() -> None:
    deps, _ = _deps()
    token = _login(deps, "n17c@example.com")
    A.handle_create_client(token, "Alice", "alice@x.com", "", deps)
    cid = A.handle_list_clients(token, deps).split(" | ")[0]
    out = A.handle_schedule(token, cid, None, "2026-10-15 11:00", deps)  # type: ignore[arg-type]
    assert "failed" in out.lower()


def test_none_register_returns_friendly_error() -> None:
    deps, _ = _deps()
    out = A.handle_register(None, "s3cret-pass", deps)  # type: ignore[arg-type]
    assert "failed" in out.lower()


def test_none_login_stays_generic_with_empty_token() -> None:
    deps, _ = _deps()
    A.handle_register("n17d@example.com", "s3cret-pass", deps)
    message, token, _ = A.handle_login(None, "s3cret-pass", "ip", deps)  # type: ignore[arg-type]
    assert token == ""
    assert message == "Invalid email or password"


def test_none_complete_content_returns_friendly_error() -> None:
    deps, _ = _deps()
    token = _login(deps, "n17e@example.com")
    A.handle_create_client(token, "Alice", "alice@x.com", "", deps)
    cid = A.handle_list_clients(token, deps).split(" | ")[0]
    A.handle_schedule(token, cid, "2026-11-15 10:00", "2026-11-15 11:00", deps)
    aid = A.handle_list_appointments(token, deps).split(" | ")[0]
    out = A.handle_complete(token, aid, None, deps)  # type: ignore[arg-type]
    assert "failed" in out.lower()
