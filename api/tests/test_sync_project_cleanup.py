"""Tests for project removal data cleanup."""

import sqlite3
from pathlib import Path

import pytest
from db.schema import ensure_schema


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c


def test_cleanup_data_for_project_removes_remote_sessions(conn, tmp_path):
    """Removing a project should clean up remote session files and DB rows."""
    from db.sync_queries import create_team, upsert_member

    create_team(conn, "acme", backend="syncthing")
    upsert_member(conn, "acme", "ayush", device_id="AYUSH-DID")

    # Create fake remote session files
    remote_dir = tmp_path / "remote-sessions" / "ayush" / "-Users-test-proj"
    remote_dir.mkdir(parents=True)
    (remote_dir / "session1.jsonl").write_text("{}")
    (remote_dir / "session2.jsonl").write_text("{}")

    # Create fake DB session rows (need jsonl_mtime for NOT NULL constraint)
    conn.execute(
        "INSERT INTO sessions (uuid, project_encoded_name, source, remote_user_id, jsonl_mtime) VALUES (?, ?, ?, ?, ?)",
        ("sess-1", "-Users-test-proj", "remote", "ayush", 1000.0),
    )
    conn.execute(
        "INSERT INTO sessions (uuid, project_encoded_name, source, remote_user_id, jsonl_mtime) VALUES (?, ?, ?, ?, ?)",
        ("sess-2", "-Users-test-proj", "remote", "ayush", 1001.0),
    )
    # Session from different project (should NOT be deleted)
    conn.execute(
        "INSERT INTO sessions (uuid, project_encoded_name, source, remote_user_id, jsonl_mtime) VALUES (?, ?, ?, ?, ?)",
        ("sess-other", "-Users-other", "remote", "ayush", 1002.0),
    )
    conn.commit()

    from db.sync_queries import cleanup_data_for_project
    stats = cleanup_data_for_project(conn, "acme", "-Users-test-proj", base_path=tmp_path)

    assert stats["sessions_deleted"] == 2
    assert not remote_dir.exists(), "Remote session directory should be deleted"

    # Other project's session should survive
    remaining = conn.execute(
        "SELECT COUNT(*) FROM sessions WHERE project_encoded_name = '-Users-other'"
    ).fetchone()[0]
    assert remaining == 1
