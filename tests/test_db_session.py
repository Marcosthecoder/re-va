"""Tests for db.session: the real (file-based) engine/session factory.
Uses a temp DATABASE_URL so the test suite never touches the project's
actual re_va.db. db.session is imported for the first time inside this
test (it hasn't been imported anywhere else), so monkeypatching the env
var beforehand actually takes effect at module load time.
"""
from __future__ import annotations

import importlib
import sys


def test_init_db_and_get_session_against_temp_sqlite_file(tmp_path, monkeypatch):
    db_path = tmp_path / "test_re_va.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    sys.modules.pop("db.session", None)
    db_session_module = importlib.import_module("db.session")

    assert db_session_module.DATABASE_URL == f"sqlite:///{db_path}"
    db_session_module.init_db()
    assert db_path.exists()

    session = db_session_module.get_session()
    try:
        from db.models import Deal

        assert session.query(Deal).count() == 0
    finally:
        session.close()

    sys.modules.pop("db.session", None)
