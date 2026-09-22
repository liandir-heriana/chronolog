"""TSK-018.1 RED: authentication-gated UI & navigation foundation.

Unauthenticated users see ONLY the auth screen; authenticated users see the
app shell with Dashboard|Clients|Agenda|History. Logout clears all user
state; second user sees no stale data; no UUIDs/tokens/user_id in chrome.
Existing auth/session guarantees must remain unchanged.
"""

from __future__ import annotations

import re

from src.presentation import app as A
from src.presentation.app import (
    NAV_TABS,
    auth_shell_visibility,
    format_user_indicator,
    handle_nav_select,
    is_authenticated,
)
from tests.presentation.test_app_wiring import _deps, _login

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)


def _walk(block):  # type: ignore[no-untyped-def]
    """Yield every nested Gradio component."""
    yield block
    for child in getattr(block, "children", []) or []:
        yield from _walk(child)


def _labels(demo):  # type: ignore[no-untyped-def]
    return [getattr(c, "label", None) for c in _walk(demo)]


def _tab_labels(demo):  # type: ignore[no-untyped-def]
    import gradio as gr

    return [c.label for c in _walk(demo) if isinstance(c, gr.Tab)]


def test_nav_tabs_are_dashboard_clients_agenda_history() -> None:
    assert NAV_TABS == ("Dashboard", "Clients", "Agenda", "History")


def test_unauthenticated_state_shows_only_auth_screen() -> None:
    deps, _ = _deps()
    assert is_authenticated("", deps) is False
    assert is_authenticated("bogus-token", deps) is False
    assert is_authenticated(None, deps) is False  # type: ignore[arg-type]
    auth_visible, shell_visible = auth_shell_visibility(False)
    assert (auth_visible, shell_visible) == (True, False)
    demo = A.build_demo(deps)
    # Initial visibility: auth column shown, app shell hidden.
    columns = [c for c in _walk(demo) if type(c).__name__ == "Column"]
    vis = sorted([(bool(getattr(c, "visible", True))) for c in columns])
    assert False in vis and True in vis
    # All four nav tabs exist but live inside the hidden shell.
    for tab in ("Dashboard", "Clients", "Agenda", "History"):
        assert tab in _tab_labels(demo)


def test_login_transitions_to_authenticated_shell() -> None:
    deps, _ = _deps()
    A.handle_register("gate1@example.com", "s3cret-pass", deps)
    message, token, label = A.handle_login(
        "gate1@example.com", "s3cret-pass", "test-ip", deps
    )
    assert message == "Login ok." and token
    assert is_authenticated(token, deps) is True
    auth_visible, shell_visible = auth_shell_visibility(True)
    assert (auth_visible, shell_visible) == (False, True)
    # User indicator shows the email, never UUID/token/user_id internals.
    assert "gate1@example.com" in label
    assert _UUID_RE.search(label) is None
    assert token not in label
    shown = format_user_indicator("gate1@example.com")
    assert "gate1@example.com" in shown
    assert _UUID_RE.search(shown) is None


def test_logout_clears_all_user_data_views() -> None:
    deps, _ = _deps()
    token = _login(deps, "gate2@example.com")
    A.handle_create_client(token, "Alice", "alice@g2.com", "", deps)
    assert "Alice" in A.handle_list_clients(token, deps)
    message, cleared, _ = A.handle_logout(token, deps)
    assert message == "Logged out." and cleared == ""
    assert is_authenticated(token, deps) is False
    assert A.handle_list_clients(token, deps) == "Please log in first."
    assert A.handle_list_appointments(token, deps) == "Please log in first."
    auth_visible, shell_visible = auth_shell_visibility(False)
    assert (auth_visible, shell_visible) == (True, False)


def test_second_user_sees_no_stale_data() -> None:
    deps, _ = _deps()
    token_a = _login(deps, "userA@example.com")
    A.handle_create_client(token_a, "AliceA", "aliceA@x.com", "", deps)
    assert "AliceA" in A.handle_list_clients(token_a, deps)
    A.handle_logout(token_a, deps)
    token_b = _login(deps, "userB@example.com")
    listed_b = A.handle_list_clients(token_b, deps)
    assert "AliceA" not in listed_b
    assert "(no clients yet)" in listed_b


def test_no_sensitive_identifiers_in_ui_chrome() -> None:
    deps, _ = _deps()
    demo = A.build_demo(deps)
    labels = [str(lb or "") for lb in _labels(demo)]
    chrome = " || ".join(labels)
    assert "Auth status" not in chrome
    assert "user_id" not in chrome
    assert "Signed in as (user_id)" not in chrome
    for lb in labels:
        low = lb.lower()
        assert "token" not in low
    # Login label itself never leaks token/UUID.
    A.handle_register("gate3@example.com", "s3cret-pass", deps)
    _, token, label = A.handle_login(
        "gate3@example.com", "s3cret-pass", "test-ip", deps
    )
    assert token not in label
    assert _UUID_RE.search(label) is None


def test_navigation_performs_no_data_access() -> None:
    # Pure selection helper: must not touch repos even when they explode.
    class ExplodingRepo:
        def __getattr__(self, _name):  # type: ignore[no-untyped-def]
            raise AssertionError("navigation must not touch data")

    for tab in ("Dashboard", "Clients", "Agenda", "History"):
        assert handle_nav_select(tab) == tab
    # Unknown tab falls back to Dashboard without data access.
    assert handle_nav_select("Nope") == "Dashboard"
    deps, _ = _deps()
    deps.clients_repo = ExplodingRepo()  # type: ignore[assignment]
    deps.appointments_repo = ExplodingRepo()  # type: ignore[assignment]
    assert handle_nav_select("Clients") == "Clients"


def test_existing_auth_guarantees_unchanged() -> None:
    deps, _ = _deps()
    # Unauthenticated handlers still gated.
    assert A.handle_list_clients("", deps) == "Please log in first."
    assert A.handle_list_appointments("bogus", deps) == "Please log in first."
    summary, _ = A.handle_history("", "c", deps)
    assert summary == "Please log in first."
    # Expired sessions still rejected.
    from src.modules.auth.domain.entities import AuthSession

    stale = AuthSession.issue("user-1", ttl_hours=-1)
    deps.sessions.save(stale)
    assert A.handle_list_clients(stale.token, deps) == "Please log in first."
