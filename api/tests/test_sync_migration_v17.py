"""Tests for schema migration v17 — sync_members identity columns."""

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


def test_sync_members_has_identity_columns(conn):
    """sync_members should have machine_id, machine_tag, member_tag columns."""
    cursor = conn.execute("PRAGMA table_info(sync_members)")
    columns = {row[1] for row in cursor.fetchall()}
    assert "machine_id" in columns
    assert "machine_tag" in columns
    assert "member_tag" in columns


def test_sync_rejected_folders_table_exists(conn):
    """sync_rejected_folders table should exist (for Phase 3, created here)."""
    cursor = conn.execute("PRAGMA table_info(sync_rejected_folders)")
    columns = {row[1] for row in cursor.fetchall()}
    assert "folder_id" in columns
    assert "team_name" in columns
    assert "rejected_at" in columns


def test_identity_columns_are_nullable(conn):
    """New columns must be nullable for backward compat."""
    conn.execute("INSERT INTO sync_teams (name, backend) VALUES ('test', 'syncthing')")
    # Insert member with only required fields — new columns should default to NULL
    conn.execute(
        "INSERT INTO sync_members (team_name, name, device_id) VALUES ('test', 'alice', 'DEV1')"
    )
    row = conn.execute(
        "SELECT machine_id, machine_tag, member_tag FROM sync_members WHERE device_id = 'DEV1'"
    ).fetchone()
    assert row["machine_id"] is None
    assert row["machine_tag"] is None
    assert row["member_tag"] is None


def test_member_tag_index_exists(conn):
    """idx_sync_members_tag index should exist on member_tag."""
    indexes = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='sync_members'"
    ).fetchall()
    index_names = {row[0] for row in indexes}
    assert "idx_sync_members_tag" in index_names
