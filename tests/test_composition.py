"""TSK-016: composition root wiring (no DB connection made)."""

import os

import pytest

from src.composition import build_context, migrations_dir, resolve_dsn


def test_resolve_dsn_prefers_explicit() -> None:
    assert resolve_dsn("postgresql://u:p@h:5432/db") == "postgresql://u:p@h:5432/db"


def test_resolve_dsn_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://env:env@localhost:5432/envdb")
    assert resolve_dsn() == "postgresql://env:env@localhost:5432/envdb"


def test_resolve_dsn_raises_without_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError):
        resolve_dsn()


def test_migrations_dir_lists_v001_v002_v003() -> None:
    base = migrations_dir()
    assert (base / "V001__users_clients.sql").is_file()
    assert (base / "V002__appointments_session_notes.sql").is_file()
    assert (base / "V003__sessions.sql").is_file()


def test_build_context_wires_all_use_cases() -> None:
    ctx = build_context("postgresql://u:p@localhost:5432/db")
    assert ctx.register_user is not None
    assert ctx.authenticate_user is not None
    assert ctx.register_client is not None
    assert ctx.schedule_appointment is not None
    assert ctx.complete_appointment is not None
    assert ctx.get_history is not None
    assert ctx.limiter.max_attempts == 5
    assert os.getenv("HOME") is not None  # sanity: no secrets asserted here
