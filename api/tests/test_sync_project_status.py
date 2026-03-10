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

    def test_received_counts_from_unlisted_dirs(self, mock_db, tmp_path, monkeypatch):
        """Received counts should scan filesystem, not just DB members."""
        encoded = "-Users-jay-karma"

        # DB: team with NO members, but one project
        mock_db.execute("INSERT INTO sync_teams (name, backend) VALUES (?, ?)", ("t1", "syncthing"))
        mock_db.execute("INSERT INTO projects (encoded_name) VALUES (?)", (encoded,))
        mock_db.execute("INSERT INTO sync_team_projects (team_name, project_encoded_name, path) VALUES (?, ?, ?)",
                        ("t1", encoded, "/Users/jay/karma"))
        mock_db.commit()

        # Local sessions
        projects_dir = tmp_path / ".claude" / "projects"
        (projects_dir / encoded).mkdir(parents=True)
        (projects_dir / encoded / "s1.jsonl").write_text('{"type":"user"}\n')

        # Outbox (local user)
        outbox = tmp_path / "remote-sessions" / "jay" / encoded / "sessions"
        outbox.mkdir(parents=True)
        (outbox / "s1.jsonl").write_text("data")

        # Remote dir with hostname (NOT in sync_members)
        hostname_inbox = tmp_path / "remote-sessions" / "Bobs-Mac.local" / encoded / "sessions"
        hostname_inbox.mkdir(parents=True)
        (hostname_inbox / "b1.jsonl").write_text("data")
        (hostname_inbox / "b2.jsonl").write_text("data")
        (hostname_inbox / "b3.jsonl").write_text("data")

        from main import app
        client = TestClient(app)

        with patch("pathlib.Path.home", return_value=tmp_path), \
             patch("karma.config.KARMA_BASE", tmp_path):
            resp = client.get("/sync/teams/t1/project-status")

        assert resp.status_code == 200
        p = resp.json()["projects"][0]
        # Should find 3 sessions from Bobs-Mac.local even though it's not a DB member
        assert p["received_counts"]["Bobs-Mac.local"] == 3

    def test_received_counts_resolves_manifest_user_id(self, mock_db, tmp_path, monkeypatch):
        """Received counts should use manifest user_id as fallback when no device_id."""
        import json
        encoded = "-Users-jay-karma"

        mock_db.execute("INSERT INTO sync_teams (name, backend) VALUES (?, ?)", ("t1", "syncthing"))
        mock_db.execute("INSERT INTO projects (encoded_name) VALUES (?)", (encoded,))
        mock_db.execute("INSERT INTO sync_team_projects (team_name, project_encoded_name, path) VALUES (?, ?, ?)",
                        ("t1", encoded, "/Users/jay/karma"))
        mock_db.commit()

        (tmp_path / ".claude" / "projects" / encoded).mkdir(parents=True)

        # Remote dir named by hostname, with manifest containing user_id but NO device_id
        remote_dir = tmp_path / "remote-sessions" / "Alices-MacBook.local" / encoded
        sessions_dir = remote_dir / "sessions"
        sessions_dir.mkdir(parents=True)
        (sessions_dir / "a1.jsonl").write_text("data")
        (remote_dir / "manifest.json").write_text(json.dumps({
            "version": 1,
            "user_id": "alice",
            "machine_id": "Alices-MacBook.local",
            "session_count": 1,
            "sessions": [],
        }))

        from main import app
        client = TestClient(app)

        with patch("pathlib.Path.home", return_value=tmp_path), \
             patch("karma.config.KARMA_BASE", tmp_path):
            resp = client.get("/sync/teams/t1/project-status")

        assert resp.status_code == 200
        p = resp.json()["projects"][0]
        # Key should be "alice" (from manifest user_id fallback), not "Alices-MacBook.local"
        assert "alice" in p["received_counts"]
        assert p["received_counts"]["alice"] == 1

    def test_received_counts_resolves_via_device_id(self, mock_db, tmp_path, monkeypatch):
        """Primary path: manifest.device_id → sync_members DB → member name."""
        import json
        encoded = "-Users-jay-karma"

        # DB: team with alice as member (device_id known)
        mock_db.execute("INSERT INTO sync_teams (name, backend) VALUES (?, ?)", ("t1", "syncthing"))
        mock_db.execute("INSERT INTO sync_members (team_name, name, device_id) VALUES (?, ?, ?)",
                        ("t1", "alice", "ALICE-DEVICE-ABC"))
        mock_db.execute("INSERT INTO projects (encoded_name) VALUES (?)", (encoded,))
        mock_db.execute("INSERT INTO sync_team_projects (team_name, project_encoded_name, path) VALUES (?, ?, ?)",
                        ("t1", encoded, "/Users/jay/karma"))
        mock_db.commit()

        (tmp_path / ".claude" / "projects" / encoded).mkdir(parents=True)

        # Remote dir named by hostname, manifest has device_id matching DB
        remote_dir = tmp_path / "remote-sessions" / "Alices-MacBook-Pro.local" / encoded
        sessions_dir = remote_dir / "sessions"
        sessions_dir.mkdir(parents=True)
        (sessions_dir / "a1.jsonl").write_text("data")
        (sessions_dir / "a2.jsonl").write_text("data")
        (remote_dir / "manifest.json").write_text(json.dumps({
            "version": 1,
            "user_id": "alice-old-name",
            "machine_id": "Alices-MacBook-Pro.local",
            "device_id": "ALICE-DEVICE-ABC",
            "session_count": 2,
            "sessions": [],
        }))

        from main import app
        client = TestClient(app)

        with patch("pathlib.Path.home", return_value=tmp_path), \
             patch("karma.config.KARMA_BASE", tmp_path):
            resp = client.get("/sync/teams/t1/project-status")

        assert resp.status_code == 200
        p = resp.json()["projects"][0]
        # Key should be "alice" (from DB via device_id), NOT "alice-old-name" or hostname
        assert "alice" in p["received_counts"]
        assert p["received_counts"]["alice"] == 2

    def test_empty_projects(self, mock_db):
        mock_db.execute("INSERT INTO sync_teams (name, backend) VALUES (?, ?)", ("t1", "syncthing"))
        mock_db.commit()

        from main import app
        client = TestClient(app)
        resp = client.get("/sync/teams/t1/project-status")
        assert resp.status_code == 200
        assert resp.json()["projects"] == []
