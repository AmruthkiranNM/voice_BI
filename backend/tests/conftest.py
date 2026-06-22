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
