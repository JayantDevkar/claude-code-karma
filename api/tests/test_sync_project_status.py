"""Tests for per-project sync status endpoint (SQLite-backed)."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.schema import ensure_schema


@pytest.fixture(autouse=True)
def _reset_singletons():
    import routers.sync_status as mod
    mod._proxy = None
    mod._watcher = None
    yield
    mod._proxy = None
    mod._watcher = None


@pytest.fixture
def mock_db(tmp_path, monkeypatch):
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_schema(conn)

    monkeypatch.setattr("routers.sync_status.get_writer_db", lambda: conn)
    monkeypatch.setattr("routers.sync_status._get_sync_conn", lambda: conn)

    config_path = tmp_path / "sync-config.json"
    config_path.write_text('{"user_id": "jay", "machine_id": "mac", "syncthing": {}}')
    monkeypatch.setattr("karma.config.SYNC_CONFIG_PATH", config_path)

    from routers.sync_status import _invalidate_identity_cache
    _invalidate_identity_cache()

    return conn


class TestProjectStatus:
    def test_returns_counts(self, mock_db, tmp_path, monkeypatch):
        """GET /sync/teams/{team}/project-status returns local/packaged/received counts."""
        encoded = "-Users-jay-karma"

        # Set up DB: team, member, project
        mock_db.execute("INSERT INTO sync_teams (name, backend) VALUES (?, ?)", ("t1", "syncthing"))
        mock_db.execute("INSERT INTO sync_members (team_name, name, device_id) VALUES (?, ?, ?)",
                        ("t1", "alice", "ALICE"))
        mock_db.execute("INSERT INTO projects (encoded_name) VALUES (?)", (encoded,))
        mock_db.execute("INSERT INTO sync_team_projects (team_name, project_encoded_name, path) VALUES (?, ?, ?)",
                        ("t1", encoded, "/Users/jay/karma"))
        mock_db.commit()

        # Create directory structure in tmp_path
        projects_dir = tmp_path / ".claude" / "projects"
        main_dir = projects_dir / encoded
        main_dir.mkdir(parents=True)
        (main_dir / "s1.jsonl").write_text('{"type":"user"}\n')
        (main_dir / "s2.jsonl").write_text('{"type":"user"}\n')

        outbox = tmp_path / "remote-sessions" / "jay" / encoded / "sessions"
        outbox.mkdir(parents=True)
        (outbox / "s1.jsonl").write_text("data")

        inbox = tmp_path / "remote-sessions" / "alice" / encoded / "sessions"
        inbox.mkdir(parents=True)
        (inbox / "a1.jsonl").write_text("data")
        (inbox / "a2.jsonl").write_text("data")

        from main import app
        client = TestClient(app)

        with patch("pathlib.Path.home", return_value=tmp_path), \
             patch("karma.config.KARMA_BASE", tmp_path):
            resp = client.get("/sync/teams/t1/project-status")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["projects"]) == 1
        p = data["projects"][0]
        assert p["encoded_name"] == encoded
        assert p["local_count"] == 2
        assert p["packaged_count"] == 1
        assert p["received_counts"]["alice"] == 2
        assert p["gap"] == 1

    def test_team_not_found(self, mock_db):
        from main import app
        client = TestClient(app)
        resp = client.get("/sync/teams/nope/project-status")
        assert resp.status_code == 404

    def test_not_initialized(self, tmp_path, monkeypatch):
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        ensure_schema(conn)
        monkeypatch.setattr("routers.sync_status.get_writer_db", lambda: conn)
        monkeypatch.setattr("routers.sync_status._get_sync_conn", lambda: conn)
        monkeypatch.setattr("karma.config.SYNC_CONFIG_PATH", tmp_path / "nope.json")

        from routers.sync_status import _invalidate_identity_cache
        _invalidate_identity_cache()

        from main import app
        client = TestClient(app)
        resp = client.get("/sync/teams/t1/project-status")
        assert resp.status_code == 400

    def test_empty_projects(self, mock_db):
        mock_db.execute("INSERT INTO sync_teams (name, backend) VALUES (?, ?)", ("t1", "syncthing"))
        mock_db.commit()

        from main import app
        client = TestClient(app)
        resp = client.get("/sync/teams/t1/project-status")
        assert resp.status_code == 200
        assert resp.json()["projects"] == []
