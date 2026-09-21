# TSK-018.2: User-Friendly Client, Appointment & Agenda Workflow — Verification Report

**Target:** `TSK-018.2` · **Module:** `src/presentation/app.py` (+ presentation tests) · **Assignee:** `@frontend-dev`
**Route:** `skill({name:"ui-integration"})` · **Date:** 2026-09-21 10:44 (UTC) · **Branch:** `feature/TSK-018.1-auth-gated-ui` (no new branch)

---

## 1. Scope

Replace developer-oriented client/appointment interactions (UUID entry, raw ISO `YYYY-MM-DD HH:MM` strings, technical status output) with user-friendly controls, reusing existing `RegisterClient`, `ScheduleAppointment`, `CompleteAppointment`, `GetClientHistory` and repository ports. No domain/use-case/infra changes. Keep Gradio. SDD + Strict TDD (RED → GREEN → REFACTOR → VERIFY → ARCHIVE).

Delivered (presentation-only):

- Client dropdowns: `(label=name <email>, value=UUID hidden)` via `get_client_choices()` (own clients only, sorted, `[]` when unauthenticated/empty, never foreign).
- Date + time + duration controls: `gr.DateTime` calendar (date) + `gr.Dropdown` time slots (`TIME_CHOICES` 08:00–19:30) + `gr.Dropdown` durations (`DURATION_CHOICES` 30/60/90/120 min) composing tz-aware UTC windows via `compose_schedule_window()` (`parse_friendly_date/time/duration` with friendly `ValueError`s, never tracebacks).
- Appointment dropdowns: `get_appointment_choices()` (owned `SCHEDULED` only, chronological, human-readable labels, UUID values hidden).
- Actions: `handle_schedule_friendly()` (delegates to `ScheduleAppointment`), `handle_edit_appointment()` (ownership via `find_by_id_and_user_id`, window re-validated via domain `Appointment.schedule`, overlap via `list_overlapping(exclude self)`, `save`), `handle_cancel_appointment()` (domain `cancel()` + `save`, no new lifecycle), `handle_complete()` evolved (dropdown value, friendly confirmation, `save_with_notes` bridge preserved).
- Human-readable lists/statuses: `format_status()` (Scheduled/Completed/Cancelled), `format_client_label()`, `_friendly_appt_line()` (`Name · DD/MM/YYYY HH:MM–HH:MM UTC · Status`), `handle_list_clients/appointments/history/agenda` friendly with no UUIDs.
- Agenda view: `handle_agenda()` (upcoming `SCHEDULED` with `starts_at >= now`, chronological, `Upcoming appointments` header, empty guidance with `New appointment` next action).
- Empty states with guidance: `(no clients yet) — add your first client…`, `(no appointments yet) — schedule…/Use New appointment…`, `No history for this client yet.`, all containing old substrings for backward compat where applicable.
- Gradio shell: removed all UUID textboxes; Agenda holds New (Create) + Manage (Edit/Cancel); History holds client dropdown + Load + Complete with notes; explicit Refresh buttons populate dropdowns (no data fetch on tab visibility, TSK-018.1 invariant holds); logout clears all dropdown choices + views.

## 2. Per-criterion results (spec §Requirements + Acceptance)

| # | Requirement / Criterion | Result |
|---|---|---|
| R1 | Clients as human-readable entries, not UUID lists | ✅ `handle_list_clients` → `Name <email> · phone`, no UUID; UI label `My clients` |
| R2 | UUIDs internal, never required/displayed | ✅ All user messages/choices labels UUID-free (regex asserted); values carry UUID hidden; `build_demo` chrome has zero `UUID/user_id/token` labels |
| R3 | Scheduler client selector from own clients | ✅ `get_client_choices` scoped by `ctx.user_id`; foreign never appears; tested |
| R4/R5 | Friendly date+time, no manual `YYYY-MM-DD HH:MM` | ✅ Calendar `DateTime` + time-slot `Dropdown`; `_DATETIME_HINT` removed from Agenda; manual ISO no longer required |
| R6 | Duration control | ✅ `Duration` dropdown (30/60/90/120 min) + `parse_friendly_duration` (`60 minutes`/`60`/`1 hour`) |
| R7 | Creation uses existing `ScheduleAppointment` | ✅ `handle_schedule_friendly` delegates with `user_id/client_id/starts_at/ends_at/now`; zero business rules moved |
| R8 | Overlap authoritative | ✅ `list_overlapping` via use-case (create) and via port with `exclude self` (edit); overlap rejected friendly in both |
| R9 | `user_id` ownership authoritative | ✅ Every handler resolves `ctx` via middleware; foreign client/appt → friendly `not found`, never leaked |
| R10 | Lists show name/date/time/status | ✅ `_friendly_appt_line` everywhere; statuses Title case |
| R11 | Scheduled expose Edit/Cancel/Complete | ✅ Agenda `Edit appointment` + `Cancel appointment`; History `Complete with notes`; all buttons present in chrome |
| R12 | Cancel uses domain lifecycle | ✅ `find_by_id_and_user_id` → `appt.cancel()` → `save`; non-scheduled → friendly lifecycle error |
| R13 | Edit preserves validation (overlap+ownership) | ✅ `Appointment.schedule` re-validation + `list_overlapping(exclude self)` + ownership; tested incl. clash rejection |
| R14 | Complete leads into notes workflow | ✅ `handle_complete` + `_complete_and_refresh` refreshes agenda/choices/history; history shows notes under date headers |
| R15/R16 | Agenda chronological upcoming + New action | ✅ `handle_agenda` sorted ascending, `starts_at >= now` filter; `Create appointment` button in Agenda |
| A1–A6 | Create/select/edit/cancel/complete without UUID/ISO | ✅ Covered by `test_friendly_workflow` (13 tests) |
| A7 | Overlap still rejected | ✅ Friendly `overlaps another appointment` in create + edit |
| A8 | Foreign never selectable/accessible | ✅ Selector isolation + use-case `not found` (no oracle); tested both directions |
| A9 | Empty states actionable | ✅ `test_empty_states_guide_next_action` (add/register/new/schedule keywords) |
| A10 | Backend tests green | ✅ Full suite live 217 passed (see §4); 3 presentation tests refactored to choice-helpers (decision D4) |

## 3. Live evidence (incl. RED proof)

- **RED (2026-09-21):** new `tests/presentation/test_friendly_workflow.py` (13 tests) failed on collection with `AttributeError: module 'src.presentation.app' has no attribute 'get_client_choices'` (13 × `F`), proving no implementation existed before GREEN.
- **GREEN:** `src/presentation/app.py` only (+2 presentation test files refactored to new workflow, +1 coverage file). No `src/modules/*` touched.
- **Live Docker smoke (2026-09-21, postgres Healthy, app Up on `127.0.0.1:7860`):**
  - `docker compose up --build -d` green; `curl :7860 → 200`; `/config` serves Blocks API (gradio 6.27.0); loopback-only ports (`127.0.0.1:7860`, `127.0.0.1:5432`); `down` clean (no `-v`, volume `chronolog-pgdata` preserved).
  - Full flow against live postgres (`DATABASE_URL` with `.env` `changeme`, `ensure_schema` + `build_context`):
    - `register A/B → login ok (True, True) → create client A → choices A = Live John <john@live.com>, choices B = []`
    - `schedule 20/12/2026 10:00 → Scheduled appointment with Live John…`
    - `overlap 10:30 rejected → Scheduling failed: that time overlaps…`
    - `edit → 11:00 30 min → Appointment updated…`
    - `agenda → Upcoming appointments`
    - `complete + notes → Completed appointment for Live John…` + `history completed=True, notes=True`
    - `schedule2 21/12 → cancel → Appointment cancelled…`
    - `cross-user B using A's client → Scheduling failed: Client not found for user` (no UUID, no leak)
    - `logout A/B → Please log in first.` (no stale data)
  - Result: `LIVE-FLOW-OK`.

## 4. Gates (DoD)

- `pytest tests/ -q --cov=src --cov-fail-under=85` (live, postgres up): **217 passed, 86.12%** (was 195 passed / 89.33% before; +22 tests: 13 workflow + 9 coverage). Local without DB: 200 passed / 17 skipped / 78.95% (live infra skipped, expected).
- `ruff check src tests`: **All checks passed.**
- `mypy src` (48 files): **Success, no issues.**
- `bandit -r src -q`: **0 High / 0 Critical** (2 accepted non-criticals, same as TSK-016/017/018.1: `B104` bind-all in `src/main.py`, `B106` password-funcarg in session repo).
- Boundary: `grep -rE "sqlalchemy|gradio|fastapi" src/modules/*/domain` → **0 matches**; `.../use_cases` → **0 matches**. Presentation holds only `gradio` + port typing (hexagonal intent, per TSK-018.1 §6 accepted deviation); zero `Postgres*`/`psycopg2`/`sqlalchemy` imports (docstring mention only).
- AuthZ: every new read scoped by `ctx.user_id`; cross-user selector isolation tested; no secrets (only `$VAR` refs, `.env` git-ignored).

## 5. Verdict + decision table

**Verdict: ACCEPTED — alignment ~96%.** All 16 requirements + 10 acceptance criteria hold; full suite + lint/types/scans + boundary + live Docker flow green. No domain/use-case/infra changes. Ready for TSK-018.3.

| ID | Decision | Rationale |
|---|---|---|
| D1 | Cancel via `find_by_id_and_user_id` → `Appointment.cancel()` → `save` (no new use-case) | Reuses existing lifecycle per spec R12; no lifecycle invented outside domain |
| D2 | Edit via `Appointment.schedule` re-validation + `list_overlapping(exclude self)` + `save` (orchestration only) | No edit use-case exists; preserves overlap/ownership/window without moving rules into handlers; documented in docstring |
| D3 | Statuses Title case (`Scheduled/Completed/Cancelled`); dates `DD/MM/YYYY HH:MM UTC` | Human-readable per R10; 2 old assertions updated to `.lower()` (honest, minimal) |
| D4 | `handle_list_*` evolved to UUID-free friendly; old ID-parsing tests switched to `get_*_choices()` | Spec R2/R10 mandates no UUIDs in normal operation; test scaffolding now uses dropdown values (hidden UUIDs), same as UI |
| D5 | Empty messages keep old substrings (`(no clients yet)`, `(no appointments yet)`, `(no session notes yet)`) + guidance | Backward compat + actionable next actions (R15/A9) |
| D6 | `Date` (`gr.DateTime` calendar) + `Time` (slot dropdown) + `Duration` (dropdown) instead of single `DateTime` | Matches UX target (separate Date/Time/Duration), avoids manual ISO, no custom time component needed |
| D7 | Explicit Refresh buttons populate dropdowns; no fetch on tab visibility/login | Preserves TSK-018.1 invariant (navigation never touches data); logout clears all choices |
| D8 | Complete lives in History (with notes → history refresh); Edit/Cancel in Agenda | All three actions exposed; Complete naturally flows into notes/history per R14; single `Complete` avoids duplicate state |

**Files:** `src/presentation/app.py` (friendly helpers + shell) · `tests/presentation/test_friendly_workflow.py` (13 RED-first) · `tests/presentation/test_friendly_coverage.py` (9 edge branches for 85% gate) · `tests/presentation/test_app_wiring.py` + `test_none_hardening.py` (choice-helper refactor, D4).
