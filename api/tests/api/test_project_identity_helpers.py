"""
Unit tests for the slug↔encoded_name resolution helpers in
`api/routers/projects.py`.

Two helpers under test:
  resolve_project_identifier(id)  — strict: raises 404 on unknown.
  safely_resolve_project(id)      — filter-friendly: returns input
                                    verbatim on unknown, None on None.

The strict variant is exercised end-to-end via every endpoint that
takes a project from the URL path; the filter variant has subtle
"empty filter" semantics that deserve direct coverage.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

_api_dir = Path(__file__).resolve().parent.parent
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))


@pytest.fixture
def memory_db(monkeypatch):
    """Patch the writer + read connections to a single shared in-memory
    SQLite. `safely_resolve_project` uses `sqlite_read()` internally, so
    we need both connection paths to point at the same DB to seed test
    rows."""
    import db.connection as connection
    from db.schema import ensure_schema

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_schema(conn)

    # sqlite_read() opens its own connection via get_db_path; route both
    # the writer and the path resolver at the in-memory DB. The simplest
    # way: patch sqlite_read to yield our conn directly.
    from contextlib import contextmanager

    @contextmanager
    def fake_read():
        yield conn

    monkeypatch.setattr(connection, "sqlite_read", fake_read)
    yield conn
    conn.close()


def _seed_project(conn, *, slug: str, encoded_name: str) -> None:
    conn.execute(
        "INSERT INTO projects (encoded_name, slug, display_name) VALUES (?, ?, ?)",
        (encoded_name, slug, encoded_name),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# safely_resolve_project — filter-friendly variant
# ---------------------------------------------------------------------------


def test_safely_resolve_project_none_returns_none():
    """`None` in → `None` out. Means "no filter applied" downstream."""
    from routers.projects import safely_resolve_project

    assert safely_resolve_project(None) is None


def test_safely_resolve_project_empty_string_returns_none():
    """Empty string also short-circuits to None (no filter)."""
    from routers.projects import safely_resolve_project

    assert safely_resolve_project("") is None


def test_safely_resolve_project_encoded_name_returns_input(memory_db):
    """encoded_name (starts with '-') is recognized and returned verbatim
    by `resolve_project_identifier`; our wrapper preserves that."""
    from routers.projects import safely_resolve_project

    # Mock is_worktree_project to return False (avoid filesystem checks)
    with patch("services.desktop_sessions.is_worktree_project", return_value=False):
        assert safely_resolve_project("-Users-me-myrepo") == "-Users-me-myrepo"


def test_safely_resolve_project_known_slug_returns_encoded_name(memory_db):
    """Known slug → resolved encoded_name. This is the bug-fix happy path:
    the frontend sends a slug, the API resolves to encoded_name internally."""
    from routers.projects import safely_resolve_project

    _seed_project(memory_db, slug="myrepo-1044", encoded_name="-Users-me-myrepo")

    with patch("services.desktop_sessions.is_worktree_project", return_value=False):
        assert safely_resolve_project("myrepo-1044") == "-Users-me-myrepo"


def test_safely_resolve_project_unknown_identifier_returns_input(memory_db):
    """Unknown identifier (not a slug, not an encoded_name) → returned
    verbatim so downstream queries get a clean SQL miss rather than 404.
    This is the load-bearing semantic — filter endpoints expect empty
    results for unknown filters, never exceptions."""
    from routers.projects import safely_resolve_project

    with patch("services.desktop_sessions.is_worktree_project", return_value=False):
        # No row seeded, no fallback match — the strict helper would 404.
        assert safely_resolve_project("does-not-exist") == "does-not-exist"


# ---------------------------------------------------------------------------
# resolve_project_identifier — strict variant (sanity check)
# ---------------------------------------------------------------------------


def test_resolve_project_identifier_raises_on_unknown(memory_db):
    """Strict variant must raise 404 on unknown — that's the contract
    that `safely_resolve_project` deliberately inverts."""
    from routers.projects import resolve_project_identifier

    with patch("services.desktop_sessions.is_worktree_project", return_value=False):
        with pytest.raises(HTTPException) as exc:
            resolve_project_identifier("does-not-exist")
        assert exc.value.status_code == 404


def test_resolve_project_identifier_returns_encoded_for_known_slug(memory_db):
    """Sanity: the strict variant still resolves slugs correctly."""
    from routers.projects import resolve_project_identifier

    _seed_project(memory_db, slug="myrepo-1044", encoded_name="-Users-me-myrepo")

    with patch("services.desktop_sessions.is_worktree_project", return_value=False):
        assert resolve_project_identifier("myrepo-1044") == "-Users-me-myrepo"
