"""Tests for settings cleanup on team delete."""

import sqlite3
import pytest
from db.schema import ensure_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


def test_delete_team_cleans_up_settings(conn):
    """Deleting a team should remove orphaned sync_settings entries."""
    from db.sync_queries import create_team, set_setting, delete_team

    create_team(conn, "acme", backend="syncthing")
    set_setting(conn, "team:acme", "auto_accept_members", "true")
    set_setting(conn, "member:acme:DEV-123", "sync_direction", "send_only")

    # Also set a setting for a different team (should NOT be cleaned)
    create_team(conn, "other", backend="syncthing")
    set_setting(conn, "team:other", "auto_accept_members", "false")

    delete_team(conn, "acme")

    # Acme settings should be gone
    rows = conn.execute(
        "SELECT * FROM sync_settings WHERE scope LIKE 'team:acme%' OR scope LIKE 'member:acme:%'"
    ).fetchall()
    assert len(rows) == 0, f"Expected 0 orphaned settings, found {len(rows)}"

    # Other team's settings should survive
    rows = conn.execute(
        "SELECT * FROM sync_settings WHERE scope LIKE 'team:other%'"
    ).fetchall()
    assert len(rows) == 1
