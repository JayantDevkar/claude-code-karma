"""Shared test fixtures for CLI tests."""

import sqlite3
import sys
from pathlib import Path

import pytest

# Add API to path for schema module
_API_PATH = str(Path(__file__).parent.parent.parent / "api")
if _API_PATH not in sys.path:
    sys.path.insert(0, _API_PATH)


@pytest.fixture
def mock_db(monkeypatch):
    """In-memory SQLite with schema, patched into the CLI."""
    from db.schema import ensure_schema

    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_schema(conn)

    monkeypatch.setattr("karma.main._get_db", lambda: conn)
    return conn
