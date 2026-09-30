"""Shared pytest fixtures."""

import os
import sys
import tempfile

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)


@pytest.fixture
def temp_database(monkeypatch):
    """Provide an isolated SQLite database path for tests."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.db")
        monkeypatch.setattr("config.DATABASE_PATH", db_path)
        monkeypatch.setattr("services.database.DATABASE_PATH", db_path)
        yield db_path


@pytest.fixture
def authenticated_client(temp_database):
    """
    A TestClient that is signed in.

    Upload, dataset and query routes sit behind require_auth, so an anonymous
    request is correctly rejected with 401 before it ever reaches the argument
    checks these tests are about. Overriding the dependency signs the request
    in as user 1 and sets the same context variable the real dependency sets,
    so per-user database resolution behaves as it does in production.
    """
    from fastapi.testclient import TestClient

    from main import app
    from services.auth import current_user_id, require_auth

    def _as_test_user():
        current_user_id.set(1)
        return {"id": 1, "email": "test@example.com"}

    app.dependency_overrides[require_auth] = _as_test_user
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(require_auth, None)
        current_user_id.set(None)
