# TSK-017 — Connect UI Forms to Application Use Cases (Depth Audit + Polish) — Verification Report

Target: `TSK-017: Connect UI Forms to Application Use Cases`
Assignee: `@frontend-dev` via `skill({name:"ui-integration"})`
Started: 2026-09-17 10:43 (UTC) / Completed: 2026-09-17 11:25 (UTC)
Branch: `feature/TSK-017-ui-usecase-wiring` (worked on current branch, no new branches). No commit (per instructions).

> TSK-016 built `src/presentation/app.py` (Login/Register + Clients/Scheduler/
> History tabs, `ctx.user_id` on every action, 10-step smoke green). TSK-017 is
> DEPTH, not rebuild: audit every form→use-case path for gaps the smoke didn't
> cover, and polish. Result: wiring was complete; audit found **3 real
> traceback leaks (None inputs)** + **2 UX gaps (no auto-refresh, logout left
> stale rows)**. Fixed with RED-first tests. No domain/use-case changes.

---

## 1. Audit scope

Every form→use-case path was exercised live (fakes + live postgres), checking:

1. Input validation: blank names, malformed emails/phones, past dates,
   `end<=start`, malformed dates, empty/blank notes, unknown/malformed
   client & appointment ids — must return friendly UI errors, never tracebacks.
2. `None` inputs (Gradio edge: cleared fields / programmatic calls / future
   dropdowns with no selection) — must never leak `AttributeError` tracebacks.
3. Empty states: no clients / appointments / history render clean messages.
4. Session expiry mid-use on **every** handler shows re-login, not crash.
5. Logout revokes the session everywhere (token cleared, post-logout blocked).
6. Throttle message stays generic in UI (no oracle).
7. Lists refresh after each mutation (register → appears; schedule → appears;
   complete → status + notes visible).
8. Cross-user isolation via handlers (user B never sees/uses user A's rows).
9. Boundary: no SQL/domain logic in UI; no adapter imports outside
   `composition.py`; every call carries `ctx.user_id`.

Method: `/tmp/opencode/audit17.py` (40 checks, fakes) + RED file
(`/tmp/opencode/test_red17.py`, 5 checks) + `/tmp/opencode/smoke17.py`
(38 checks, live postgres via `src.composition` + UI handlers + `demo.config`
wiring counts + loopback check).

---

## 2. Per-path results table

| # | Path | Before | After | Evidence |
|---|---|---|---|---|
| 1 | Blank name `""` / `"   "` | ✅ friendly (`Invalid client name`) | ✅ unchanged | audit ok, smoke ok |
| 2 | Malformed email (no-at / empty / inner space) | ✅ friendly (`Invalid email`) | ✅ unchanged | audit ok, smoke ok |
| 3 | Malformed phone (`abc` / too short) | ✅ friendly (`Invalid phone`) | ✅ unchanged | audit ok, smoke ok |
| 4 | Valid phone `+34600111222` / empty phone | ✅ saved | ✅ unchanged | audit ok, smoke ok |
| 5 | Past dates | ✅ friendly (`cannot be scheduled in the past`) | ✅ unchanged | audit ok, smoke ok |
| 6 | `end==start` / `end<start` | ✅ friendly (`ends_at must be after starts_at`) | ✅ unchanged | audit ok, smoke ok |
| 7 | Malformed / empty date text | ✅ friendly (hint `YYYY-MM-DD HH:MM…`) | ✅ unchanged | audit ok, smoke ok |
| 8 | Unknown / malformed client id (schedule) | ✅ friendly (`Client not found` / `Invalid client id`) | ✅ unchanged | audit ok, smoke ok |
| 9 | Empty / blank notes | ✅ friendly (`Session notes content is invalid`) | ✅ unchanged | audit ok, smoke ok |
| 10 | Unknown / malformed appointment id | ✅ friendly (`Appointment not found` / `Invalid appointment id`) | ✅ unchanged | audit ok, smoke ok |
| 11 | Empty states (clients / appointments / history-notes) | ✅ `(no clients yet)` / `(no appointments yet)` / `(no session notes yet)` | ✅ unchanged | audit ok, smoke ok |
| 12 | Expiry on all 6 handlers | ✅ `Please log in first.` | ✅ unchanged | audit ok, smoke ok |
| 13 | Logout (revoke + post-logout block + empty-token no-op) | ✅ revoked, blocked | ✅ **hardened: clears all 10 views** (see §5 D3) | audit ok, smoke ok |
| 14 | Throttle generic (`Invalid email or password`, empty token) | ✅ generic | ✅ unchanged | audit ok, smoke ok |
| 15 | Cross-user isolation (list empty, foreign-client schedule rejected) | ✅ no leak | ✅ unchanged | audit ok, smoke ok |
| 16 | **`None` name / email / starts** | ❌ **`AttributeError` traceback leak** (3/40 failed) | ✅ friendly (`Invalid client name: ''` / `Invalid email: ''` / date hint) | RED 5 failed → GREEN 5 passed; `test_none_hardening.py` 6 passed; audit 40/40 |
| 17 | **`None` register email / login email** | ❌ **leak** (`_throttle_keys` / `UserEmail`) | ✅ friendly / generic (no oracle) | RED → GREEN, same suites |
| 18 | **`None` complete content** | ❌ **leak when appointment exists** (masked in first audit by unknown-id path) | ✅ friendly (`Session notes content is invalid`) | new regression test passes live+fake |
| 19 | **Register → list refresh** | ❌ manual Refresh required (smoke didn't cover wiring) | ✅ auto: save→2 outputs (status+list) | `demo.config` counts `(4,2)` ×2; live save→appears |
| 20 | **Schedule → list refresh** | ❌ manual Refresh required | ✅ auto: schedule→2 outputs | counts; live schedule→appears |
| 21 | **Complete → status/notes visible** | ❌ manual reload required | ✅ auto: complete→4 outputs (status+sched+hist×2, best-effort history via appointment→client lookup) | counts `(3,4)`; live status+notes visible |
| 22 | TSK-016 middleware test `test_expired_token_rejected_with_generic_error` | ❌ **wall-clock flaky** (pinned NOW=09:55 vs real `issue()` time; fails after ~10:55 UTC) — pre-existing, not TSK-017 | ✅ deterministic (default real `now`) | full suite 187 green; note in §5 D4 |

Backend gaps: **none** — all validation already lived in domain/use-cases and
passed through correctly. Zero domain/use-case production changes.

---

## 3. Live evidence

RED (before fix, presentation only):

```text
.venv/bin/python -m pytest tests/presentation/test_red17_tmp.py -q
FAILED test_red_none_client_name_friendly - AttributeError: 'NoneType' object has no attribute 'strip'
FAILED test_red_none_client_email_friendly - AttributeError ...
FAILED test_red_none_schedule_starts_friendly - AttributeError ...
FAILED test_red_none_register_friendly - AttributeError ...
FAILED test_red_none_login_generic - AttributeError ... (_throttle_keys)
5 failed
audit17.py: AUDIT GAPS FOUND: 37/40 (3 None traceback leaks)
```

GREEN (unit, no DB): `181 passed` baseline held; after fix + 6 regression tests:

```text
.venv/bin/python -m pytest tests/ -q --cov=src --cov-fail-under=85   # postgres Healthy
TOTAL  1100 stmts, 118 miss → 89.27% (≥85)
187 passed in ~11s   (181 + 6 test_none_hardening)
```

Docker + live smoke (rebuilt image with new presentation code):

```text
docker compose up --build -d     # app Up (python -m src.main), postgres Healthy
docker logs chronolog-app        # * Running on local URL: http://0.0.0.0:7860
curl localhost:7860/             # HTTP 200 (Gradio 6.27.0 blocks JSON ok)
ss -ltn                          # 127.0.0.1:7860 + 127.0.0.1:5432 (loopback only)
PYTHONPATH=. .venv/bin/python /tmp/opencode/smoke17.py   # live postgres via UI handlers:
  register/login ok, middleware resolves token
  empty clients / blank name / bad email / bad phone / None name / None email → friendly
  client saved → list shows Alice (refresh path)
  bad date / None starts / past / end<=start / unknown client → friendly
  scheduled → list shows scheduled; overlap rejected
  history shows Alice, blank/None notes → friendly
  completed → list shows completed, history shows notes
  userB empty, userB cannot use userA client
  expiry on all 6 handlers → Please log in first.
  throttle generic + empty token; logout revokes + post-logout blocked
  wiring counts [(1,1),(1,1),(1,10),(2,1),(2,2),(2,3),(3,4),(4,2),(4,2)]
    = save→2, schedule→2, complete→4, logout→10
  SMOKE17 ALL GREEN
docker compose down              # network removed, no -v, volume kept
```

No secrets logged: DSNs/passwords never printed; `.env` untracked+ignored
(`git check-ignore .env` ok).

---

## 4. Gates

| Gate | Command | Result |
|---|---|---|
| pytest + cov ≥ 85% | `pytest tests/ -q --cov=src --cov-fail-under=85` (live) | ✅ 187 passed, 89.27% |
| ruff | `ruff check src tests` | ✅ All checks passed |
| mypy | `mypy src` | ✅ no issues in 48 source files |
| bandit | `bandit -r src` | ✅ 0 high/critical (1 medium B104 bind-all — required in-container, LAN gated at compose loopback; 1 low B106 `token=""` false positive) |
| boundary domain | `grep -rE "sqlalchemy\|gradio\|fastapi" src/modules/*/domain` | ✅ 0 matches |
| boundary use-cases | `grep -rE "sqlalchemy\|gradio\|fastapi" src/modules/*/use_cases` | ✅ 0 matches |
| gradio scope | `grep -rln gradio src/` | ✅ only `src/presentation/app.py` (+pycache) |
| no adapter imports in UI | `grep -rnE "^(import\|from).*Postgres\|psycopg2\|sqlalchemy" src/presentation/ src/main.py src/core/` | ✅ 0 (only prose mention in docstring; composition owns `psycopg2` by design) |
| AuthZ `user_id` | every handler resolves `ctx` + passes `ctx.user_id`; cross-user live test green | ✅ covered |
| docker | `up --build` → curl 200 → smoke 38/38 → `down` (no `-v`) | ✅ ok |

---

## 5. Verdict + %

**VERDICT: PASS — TSK-017 100% delivered (depth audit + polish) with all DoD gates green.**

- New tests: 6 (`tests/presentation/test_none_hardening.py`) + full suite 187/187 (100%).
- Coverage: 89.27% total (≥85 gate).
- No domain/use-case production changes (audit proved passthrough complete).
- Files changed: `src/presentation/app.py` (None hardening + auto-refresh wiring
  + logout-clear), `tests/presentation/test_none_hardening.py` (new),
  `tests/core/security/test_middleware.py` (1-line flake fix, test-only).
- TSK-017 ready for `[x]` closure. Next: TSK-018 (final suite + coverage).

### Decision table

| Decision | Options considered | Chosen | Why |
|---|---|---|---|
| None-input fix layer | Domain guards vs presentation normalization | Presentation `or ""` + `(ValueError,TypeError,AttributeError)` catch | Domain correctly validates strings; `None` never reaches it in production (Gradio sends `""`) — normalize at the boundary, keep domain pure, no port changes |
| Login None-error shape | Friendly `Register failed`-style vs generic | Generic `Invalid email or password` | Anti-oracle (D2/D4): None-email must be indistinguishable from wrong-password |
| Auto-refresh mechanism | Change handler signatures (tuples) vs compose in wiring | Compose in `build_demo` (`_save_client_and_refresh`, `_schedule_and_refresh`, `_complete_and_refresh`) | Handler API frozen (13 existing tests untouched); wiring-only polish, single round-trip per click, Refresh buttons kept as manual fallback |
| Complete refresh depth | Status-list only vs +history | Status + best-effort history (appointment→client lookup, `ValueError/TypeError/AttributeError` → empty) | Satisfies "status/notes visible" without new port methods (T10-D1 frozen); never leaks wiring errors |
| Logout scope | Token-only (status quo) vs clear-all-views | Clear all 10 outputs (status, token, user, client×2, sched×2, hist×2, complete) | Privacy: next user at same browser never sees stale rows; placeholders match empty states |
| Flaky middleware test | Leave red vs fix production vs fix test | 1-line test-only fix (default real `now`) | Production `issue()`/`is_expired` correct; test mixed real issue-time with pinned check-time — wall-clock flake, intent preserved, no behavior change |
| Backend changes | Add validation vs none | None (honest: no gaps found in passthrough) | Every domain rule already surfaced friendly through handlers; evidence in §2 rows 1–15 |
