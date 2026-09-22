"""ChronoLog demo seed (manual testing / course demo ONLY).

Flow: run AFTER pytest (integration tests TRUNCATE these tables),
demo in the UI, then `docker compose down -v` to wipe back to zero.
NEVER run against anything but your local environment.

Usage:
    docker compose up -d postgres && sleep 5
    .venv/bin/python db/seed_demo.py
    # ... demo at http://127.0.0.1:7860 ...
    docker compose down -v   # wipes demo data + volume

Content: 2 users (admin/admin, user/user) x 3 clients x 3 appointments
(1 COMPLETED with notes + 1 CANCELLED, both in the past for a believable
History, + 1 upcoming SCHEDULED for the Agenda). Re-runnable: previous demo
rows for these users are wiped first (users upserted by email).

Honesty note: passwords "admin"/"user" violate the domain minimum length
(MIN_PASSWORD_LENGTH=8, enforced in RegisterUser). The seed therefore writes
PBKDF2 rows directly in the exact on-disk format instead of going through
registration. Login (AuthenticateUser -> verify_password) is unaffected.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sys
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import psycopg2

DSN = os.getenv(
    "DATABASE_URL",
    "postgresql://chronolog:changeme@localhost:5432/chronolog",
)

# Same parameters as src.modules.auth.domain.security (seed-only duplicate,
# because the registration choke point rightly rejects short passwords).
_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 210_000


def _seed_hash(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITERATIONS)
    return f"{_ALGORITHM}${_ITERATIONS}${salt.hex()}${digest.hex()}"


USERS = [("admin@chronolog.test", "admin"), ("user@chronolog.test", "user")]

CLIENTS = [
    ("Ada Lovelace", "ada@example.com", "+34600111111"),
    ("Grace Hopper", "grace@example.com", "+34600222222"),
    ("Alan Turing", "alan@example.com", None),
]

NOW = datetime.now(UTC)


def main() -> int:
    with psycopg2.connect(DSN) as conn, conn.cursor() as cur:
        for email, password in USERS:
            user_id = str(uuid4())
            cur.execute(
                "INSERT INTO users (id, email, password_hash)"
                " VALUES (%s, %s, %s)"
                " ON CONFLICT (email) DO UPDATE SET password_hash = EXCLUDED.password_hash"
                " RETURNING id",
                (user_id, email, _seed_hash(password)),
            )
            row = cur.fetchone()
            assert row is not None
            owner = row[0]
            # Re-runnable: wipe previous demo rows (cascade clears appointments+notes).
            cur.execute("DELETE FROM clients WHERE user_id = %s", (owner,))
            print(f"user {email} -> {owner}")
            for idx, (name, cmail, phone) in enumerate(CLIENTS):
                client_id = str(uuid4())
                cur.execute(
                    "INSERT INTO clients (id, user_id, name, email, phone)"
                    " VALUES (%s, %s, %s, %s, %s)",
                    (client_id, owner, name, cmail, phone),
                )
                # Staggered per client (idx): no two appointments of the same
                # user share day+hour — a simultaneous Agenda would contradict
                # the no-overlap rule the demo is meant to showcase.
                # Clean wall-clock hours (not NOW offsets) for a professional look.
                # 1) COMPLETED in the past, with notes (History)
                done_start = (NOW - timedelta(days=5 - idx)).replace(
                    hour=10 + idx, minute=0, second=0, microsecond=0
                )
                appt_id = str(uuid4())
                cur.execute(
                    "INSERT INTO appointments (id, user_id, client_id, starts_at, ends_at, status)"
                    " VALUES (%s, %s, %s, %s, %s, 'completed')",
                    (appt_id, owner, client_id, done_start, done_start + timedelta(hours=1)),
                )
                cur.execute(
                    "INSERT INTO session_notes (id, appointment_id, user_id, content)"
                    " VALUES (%s, %s, %s, %s)",
                    (str(uuid4()), appt_id, owner, f"Demo notes for {name}."),
                )
                # 2) CANCELLED in the past (History)
                cx_start = (NOW - timedelta(days=2)).replace(
                    hour=12 + idx, minute=0, second=0, microsecond=0
                )
                cur.execute(
                    "INSERT INTO appointments (id, user_id, client_id, starts_at, ends_at, status)"
                    " VALUES (%s, %s, %s, %s, %s, 'cancelled')",
                    (str(uuid4()), owner, client_id, cx_start, cx_start + timedelta(hours=1)),
                )
                # 3) upcoming SCHEDULED (Agenda)
                start = (NOW + timedelta(days=1 + idx)).replace(
                    hour=9 + idx, minute=0, second=0, microsecond=0
                )
                cur.execute(
                    "INSERT INTO appointments (id, user_id, client_id, starts_at, ends_at, status)"
                    " VALUES (%s, %s, %s, %s, %s, 'scheduled')",
                    (str(uuid4()), owner, client_id, start, start + timedelta(hours=1)),
                )
                print(f"  client {name}: 1 completed w/ notes + 1 cancelled + 1 scheduled")
    print("seed OK: 2 users x 3 clients x 3 appointments (6 notes total)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
