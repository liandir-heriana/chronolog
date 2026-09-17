"""ChronoLog auth password hashing + token utilities (pure, stdlib only).

Decision: PBKDF2-HMAC-SHA256 from :mod:`hashlib` with a per-password random
salt from :mod:`secrets`. bcrypt/argon2 are not installed in the project
venv and would add native build dependencies; PBKDF2 keeps zero third-party
deps while remaining an OWASP-listed adaptive function. Revisit in TSK-015
if the security audit mandates argon2id.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from src.modules.auth.domain.exceptions import UserValidationError

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 210_000
_SALT_BYTES = 16
MIN_PASSWORD_LENGTH = 8


def hash_password(password: str) -> str:
    """Hash ``password``; never returns (or contains) the plaintext."""
    if len(password) < MIN_PASSWORD_LENGTH or not password.strip():
        raise UserValidationError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
        )
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"{_ALGORITHM}${_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    """Return True iff ``password`` matches the stored ``password_hash``.

    Malformed stored hashes safely return False instead of raising, so a
    corrupt row can never crash (or bypass) login.
    """
    try:
        algorithm, iterations, salt_hex, expected_hex = password_hash.split("$")
        if algorithm != _ALGORITHM:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
    except (ValueError, AttributeError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), expected_hex)


def generate_token() -> str:
    """Generate an opaque random session token (no identity data inside)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Return the ``sha256`` hex digest of a session ``token``.

    TSK-016 (D3): the ``sessions`` table stores only this hash (PK
    ``token_hash``), never the raw bearer token — a DB leak alone cannot
    impersonate. Lookup hashes the presented token with the same function.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
