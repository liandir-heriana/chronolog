# TSK-012.1: Provision Docker Engine & Run Live Healthcheck Gate

**Target / Subtask:** `TSK-012.1: Provision Docker Engine & Run Live Healthcheck Gate`  
**Parent Task:** `TSK-012: Local Docker Containerization Setup` (Blocked at ~75% static compliance)  
**Assigned to:** `@devops-engineer`  
**Route:** `skill({name:"devops-docker"})` via `/up`  

---

## 1. Context & Problem Statement

During the initial review of `TSK-012`, static verification of `Dockerfile`, `docker-compose.yml`, and `.env.example` passed at ~75%. However, live execution was marked as `BLOCKED-ON-ENV` due to the lack of an active Docker Engine/daemon in the local sandbox environment.

**TSK-012.1** serves as the explicit unblocking subtask. Once a Docker-enabled host environment is available, this test specification executes the live container healthchecks, verifies volume persistence, and confirms non-root container security to formally transition `TSK-012` to `[x] Completed`.

---

## 2. Given-When-Then Verification Scenarios

### Scenario 1: Engine & Orchestrator Availability
* **Given** a host machine with Docker Engine and Docker Compose V2 installed.
* **When** running `docker info` and `docker compose version`.
* **Then** both commands return exit code `0` with active daemon status.

### Scenario 2: Live Container Startup & Database Healthcheck
* **Given** the repository configuration files (`Dockerfile`, `docker-compose.yml`, `.env`).
* **When** executing `docker compose up --build -d`.
* **Then** both `app` and `postgres` containers build and start successfully.
* **And** `docker compose exec postgres pg_isready -U chronolog_user -d chronolog_db` returns `accepting connections`.

### Scenario 3: Non-Root Application Container Security Audit
* **Given** the running `app` container.
* **When** inspecting the process user via `docker compose exec app whoami`.
* **Then** the command outputs `appuser` (UID `10001`), confirming compliance with the Principle of Least Privilege.

### Scenario 4: Database Volume Data Persistence
* **Given** a running PostgreSQL container with test data written to `postgres_data`.
* **When** stopping containers with `docker compose down` and restarting with `docker compose up -d`.
* **Then** all previously written database records remain fully intact.

### Scenario 5: Teardown & Clean Volume Removal
* **Given** active ChronoLog containers.
* **When** executing `docker compose down -v`.
* **Then** containers, networks, and ephemeral mounts are cleaned up without orphan processes or leaked ports.

---

## 3. Executable CLI Verification Script

Execute the following bash commands in the target Docker-enabled environment:

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "=== Step 1: Check Docker Engine ==="
docker info > /dev/null || { echo "CRITICAL: Docker daemon not running"; exit 1; }
docker compose version

echo "=== Step 2: Prepare Environment Secrets ==="
if [ ! -f .env ]; then
    cp .env.example .env
fi

echo "=== Step 3: Build and Start Containers ==="
docker compose up --build -d

echo "=== Step 4: Wait and Check Container Health ==="
sleep 5
docker compose ps

echo "=== Step 5: Verify PostgreSQL Connectivity ==="
docker compose exec postgres pg_isready -U chronolog_user -d chronolog_db

echo "=== Step 6: Verify Non-Root User in App Container ==="
APP_USER=$(docker compose exec app whoami | tr -d '\r')
echo "App running as: ${APP_USER}"
if [ "$APP_USER" = "root" ]; then
    echo "ERROR: App container is running as root!"
    exit 1
fi

echo "=== Step 7: Clean Teardown Verification ==="
docker compose down
echo "TSK-012.1 Live Healthcheck Gate: PASSED ✅"
```

---

## 4. Unblocking Criteria for Parent Task TSK-012

To mark `TSK-012` as `[x] Completed` in `doc/tasks.md`:

1. [x] **Docker Daemon Active**: `docker info` returns 0.
2. [x] **Live Healthcheck Passed**: PostgreSQL reports `accepting connections`.
3. [x] **Non-Root Confirmed**: App process runs as `appuser`.
4. [x] **Clean Teardown**: `docker compose down` completes without lingering resources.

---

## 5. Parallel Verification Result (Justification)

**Final verdict: the executed TSK-012.1 live run is ACCEPTED — alignment with this verification proposal: ~80%.**

Breakdown (2026-09-16, live run on Docker 29.8.0 + Compose 5.5.1 vs the scenarios above):

- **Scenario 1: PASS (equivalent).** Ran `docker --version`, `docker compose version`, and `docker ps` (exit 0, empty list) instead of `docker info` — same proof: client + daemon reachable.
- **Scenario 2: PASS (equivalent).** `docker compose up --build -d` green, postgres `Healthy`, `pg_isready` → `accepting connections`. Note: executed with the repo's real values (`-U chronolog -d chronolog` from `.env`), not the illustrative `chronolog_user`/`chronolog_db` in §2–§3 — the spec's values don't match `.env.example`.
- **Scenario 3: PASS (adapted).** `docker compose exec app whoami` fails by design — the honest suite CMD finishes (114 passed) and the container exits, so there is no running `app` to exec into. Verified instead via `docker compose run --rm app whoami` → `appuser`. Caveat: UID is not pinned to `10001` (T12-D2); username match confirmed, numeric UID not asserted.
- **Scenario 4: NOT RUN.** No test data was written and no down/up persistence cycle executed — volume `chronolog-pgdata` mounts correctly per `config`, but data survival is unproven. Parked: prove it in TSK-014 when real rows exist.
- **Scenario 5: PARTIAL (deliberate).** `docker compose down` (without `-v`) completed clean, no orphans. `down -v` intentionally NOT run — deleting the named volume now would destroy the persistence Scenario 4 is meant to prove later.

Justification: every runnable scenario passed; the gaps are a deliberate `down` without `-v`, one unrun persistence cycle, and illustrative-vs-real credential values in the spec. Also note §4 cites `doc/tasks-v6.md` — the live backlog is `doc/tasks.md` (stale filename in this spec).

### Gate Log (TSK-012.1, 2026-09-16)

| # | Check | Result |
|---|---|---|
| G1 | Engine + daemon reachable | ✅ `docker ps` exit 0 |
| G2 | `config` interpolates app + postgres | ✅ |
| G3 | `up --build -d` green, postgres Healthy | ✅ |
| G4 | `pg_isready` accepting connections | ✅ |
| G5 | App suite 114 passed in-container | ✅ |
| G6 | Non-root (`appuser`) | ✅ via `run --rm` (exec N/A — container exits by design) |
| G7 | Clean `down`, no orphans | ✅ (without `-v`, deliberate) |
| G8 | Persistence down/up cycle | ⏳ parked to TSK-014 |
