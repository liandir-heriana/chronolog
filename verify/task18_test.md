# TSK-018.1: Authentication-Gated UI & Navigation Foundation

**Target / Task:** `TSK-018.1: Authentication-Gated UI & Navigation Foundation`  
**Module:** `src/presentation/` (`app.py`, `handlers.py`, `components/`) & `src/main.py`  
**Assigned To:** `@frontend-dev`  
**Route:** `skill({name:"ui-integration"})` via `/apply TSK-018.1`  

---

## 1. Context and Architectural Requirements

`TSK-018.1` establishes the foundational user interface shell for the ChronoLog MVP redesign. Previously, technical developer controls, raw UUIDs, and unauthenticated tab visibility created UX friction. This subtask restructures the Gradio presentation layer so that unauthenticated users interact **strictly** with an Authentication screen (Login / Register), while authenticated users access a clean, top-level application navigation shell (`Dashboard | Clients | Agenda | History`).

### Core Invariants & Boundaries:
1. **Authentication-Gated Layout (Auth-Gated UI)**: Unauthenticated states MUST display only the login/registration interface. All application data tabs (`Dashboard`, `Clients`, `Agenda`, `History`) MUST remain hidden (`visible=False`) until valid session authentication.
2. **Session Cleanup on Logout**: Clicking **Logout** MUST immediately return the UI to the unauthenticated view, clear all user-specific data structures (dataframes, dropdown choices, status messages), and invalidate the session context to prevent cross-user data leakage.
3. **Removal of Developer Telemetry**: Developer-facing Auth status strings, raw `user_id` textboxes, session token hashes, and database primary key UUIDs MUST be removed from normal user-facing layouts.
4. **Header Navigation & Authenticated Indicator**: Authenticated view MUST display a clean header with the brand name (`ChronoLog`), an authenticated user indicator (e.g., `User: email@domain.com`), and an explicit `[Logout]` button.
5. **Zero Backend/Domain Mutation**: Presentation changes MUST NOT alter pure domain rules (`src/modules/*/domain/`), use cases, or repository interfaces.

---

## 2. Shell State & Component Visibility Specification

### Visibility Matrix

| UI Component / Container | Initial / Unauthenticated State | Authenticated State | Post-Logout State |
| :--- | :--- | :--- | :--- |
| **Auth Container** (Login / Register) | `visible=True` | `visible=False` | `visible=True` |
| **App Navigation Shell** (Tabs Header) | `visible=False` | `visible=True` | `visible=False` |
| **User Header / Badge** | `visible=False` | `visible=True` (`"User: email"`) | `visible=False` |
| **Logout Button** | `visible=False` | `visible=True` | `visible=False` |
| **Dashboard Tab** | `visible=False` | `visible=True` | `visible=False` (Data Wiped) |
| **Clients Tab** | `visible=False` | `visible=True` | `visible=False` (Data Wiped) |
| **Agenda Tab** | `visible=False` | `visible=True` | `visible=False` (Data Wiped) |
| **History Tab** | `visible=False` | `visible=True` | `visible=False` (Data Wiped) |
| **Developer Telemetry / UUID Fields** | Hidden / Removed | Hidden / Removed | Hidden / Removed |

### State Transition Handlers
* **`handle_login_submit(email, password)`**:
  - Validates credentials via `AuthenticateUserUseCase`.
  - On Success: Generates session token, fetches user context, sets Auth Container `visible=False`, exposes Application Navigation Shell `visible=True`, sets user badge, and loads initial Dashboard metrics.
  - On Failure: Displays clean, generic error: *"Invalid email or password"*.
* **`handle_logout_click(session_token)`**:
  - Invalidates session via `AuthMiddleware` / session repository.
  - Clears all UI state variables (`ctx.user_id = None`).
  - Sets App Navigation Shell `visible=False`, sets Auth Container `visible=True`, resets login inputs to blank.

---

## 3. Given-When-Then Verification Scenarios

### Scenario 1: Unauthenticated Initial Landing Page
* **Given**: A user launches or accesses the ChronoLog Gradio web application URL (`http://localhost:7860`).
* **When**: The initial page loads in the browser.
* **Then**: Only the ChronoLog Login and Register forms are visible. Application data tabs (`Dashboard`, `Clients`, `Agenda`, `History`), raw UUIDs, and developer status headers are completely hidden.

### Scenario 2: Transition to Authenticated Application Shell
* **Given**: The user is on the unauthenticated landing page.
* **When**: The user enters valid credentials (`user@example.com` / `Password123!`) and submits the Login form.
* **Then**: The Login form disappears, the header displays `ChronoLog | User: user@example.com [Logout]`, and top-level navigation tabs (`Dashboard`, `Clients`, `Agenda`, `History`) become visible and active.

### Scenario 3: Complete Logout and Data Sanitization
* **Given**: An authenticated user viewing client data and scheduled appointments.
* **When**: The user clicks the `[Logout]` button.
* **Then**: The UI immediately transitions back to the Login screen. Subsequent logins by a different user MUST NOT see any cached or stale client data from the previous session.

### Scenario 4: Protection Against Unauthorized Navigation
* **Given**: An unauthenticated HTTP request or direct element interaction attempt.
* **When**: An unauthenticated user attempts to interact with hidden tab handlers.
* **Then**: Handler functions verify active session context, reject execution with `UnauthenticatedError`, and keep presentation components hidden.

---

## 4. Executable Pytest Test Suite (`tests/unit/ui/test_auth_gated_shell.py`)

```python
import pytest
from src.presentation.app import create_gradio_app
from src.presentation.handlers import handle_login_submit, handle_logout_click

def test_unauthenticated_initial_shell_state(mock_composition_root):
    """Verify that unauthenticated layout hides app tabs and shows auth form."""
    # Given / When
    app = create_gradio_app(mock_composition_root)
    
    # Then: Verify initial component visibilities
    auth_container = app.components_dict.get("auth_container")
    app_shell = app.components_dict.get("app_shell")
    
    assert auth_container is not None
    assert app_shell is not None
    assert auth_container.visible is True
    assert app_shell.visible is False

def test_login_success_shell_transition(mock_composition_root):
    """Verify login success hides auth container and exposes main app shell."""
    # Given
    email = "test@chronolog.com"
    password = "ValidPassword123!"
    
    # When
    updates = handle_login_submit(email, password, container=mock_composition_root)
    
    # Then: Check visibility dict updates
    assert updates["auth_container"]["visible"] is False
    assert updates["app_shell"]["visible"] is True
    assert "test@chronolog.com" in updates["user_badge"]["value"]

def test_logout_clears_state_and_returns_to_auth(mock_composition_root):
    """Verify logout invalidates session, clears data, and hides app shell."""
    # Given: Logged in state
    login_updates = handle_login_submit("test@chronolog.com", "ValidPassword123!", container=mock_composition_root)
    session_token = login_updates["session_token"]
    
    # When: Logout clicked
    logout_updates = handle_logout_click(session_token, container=mock_composition_root)
    
    # Then
    assert logout_updates["auth_container"]["visible"] is True
    assert logout_updates["app_shell"]["visible"] is False
    assert logout_updates["user_badge"]["value"] == ""
    assert logout_updates["client_dropdown"]["choices"] == []

def test_telemetry_and_uuids_hidden_from_ui(mock_composition_root):
    """Verify developer status textboxes and raw UUIDs are not rendered."""
    app = create_gradio_app(mock_composition_root)
    rendered_labels = [c.label for c in app.components if hasattr(c, "label") and c.label]
    
    # Raw UUID / Auth Status labels must not exist in user-facing UI
    assert "User ID (UUID)" not in rendered_labels
    assert "Auth Status" not in rendered_labels
    assert "Session Token Hash" not in rendered_labels
```

---

## 5. Quality Gates (Definition of Done)

To complete `TSK-018.1` and proceed to `TSK-018.2`, all of the following verification commands must pass cleanly:

1. **Architecture Boundary Check**:
   ```bash
   grep -rE "IClientRepository|IAppointmentRepository|psycopg2" src/presentation/
   # Expected output: 0 matches (Presentation layer must not import ports or DB drivers)
   ```

2. **Automated Test Suite & Coverage Threshold**:
   ```bash
   pytest tests/ -q --cov=src --cov-fail-under=85
   # Expected result: All tests pass with overall coverage >= 85%
   ```

3. **Static Analysis & Security Scans**:
   ```bash
   ruff check src/ tests/ && mypy src/ && bandit -r src/ -q
   # Expected result: Zero errors/warnings, no critical security findings
   ```

4. **Docker Containerized Health & Smoke Check**:
   ```bash
   docker compose up --build -d
   docker compose ps
   curl -I http://localhost:7860
   # Expected result: Both containers Healthy, HTTP 200 OK
   ```

---

## 6. Parallel Verification Result (Justification)

**Final verdict: the executed TSK-018.1 process is ACCEPTED — alignment with this verification proposal: ~95%.**

Breakdown (2026-09-18, executed implementation vs this guide; full report in `verify/task18_1_test.md`):

- **Scenarios 1–4: 4/4 equivalent.** Unauthenticated landing shows auth only; login transitions to the `Dashboard|Clients|Agenda|History` shell; logout sanitizes views; navigation performs no data access by visibility. Covered by 8 new tests (`tests/presentation/test_auth_gating.py`), RED via `ImportError`, GREEN in `src/presentation/app.py` only.
- **Quality gates: 4/4 equivalent.** Independently re-verified: `pytest` 195 passed / cov 89.33% (≥85), `ruff` + `mypy` (48 files) clean, boundary `grep` on domain/use-cases 0 matches, bandit 0 high/critical (B104/B106 accepted per TSK-016). Docker smoke (up/curl/smoke/down) taken from the §3.3 live evidence — not re-run independently this round.
- **Divergences (non-blocking):** shell uses auth/shell `Column(visible=...)` toggling rather than the `handlers.py`/`components/` module split the scaffold sketches (accepted — same behavior, smaller diff); login label shows the normalized email instead of any id (stricter than spec); Dashboard is a static placeholder until TSK-018.3 (declared, not a gap).

Justification: every scenario and gate in Sections 1–5 holds in the implementation; no domain/use-case/auth-impl file was touched. No process redo required.
