"""Tests for adding/removing projects to sync groups (SQLite-backed)."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.schema import ensure_schema


@pytest.fixture(autouse=True)
def _reset_singletons():
    import services.sync_identity as mod
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

    # Pre-populate a team with a member
    conn.execute("INSERT INTO sync_teams (name, backend) VALUES (?, ?)", ("my-team", "syncthing"))
    conn.execute(
        "INSERT INTO sync_members (team_name, name, device_id) VALUES (?, ?, ?)",
        ("my-team", "alice", "ALICE-ID"),
    )
    conn.commit()

    monkeypatch.setattr("services.sync_identity._get_sync_conn", lambda: conn)

    config_path = tmp_path / "sync-config.json"
    config_path.write_text('{"user_id": "jayant", "machine_id": "mac", "syncthing": {}}')
    monkeypatch.setattr("karma.config.SYNC_CONFIG_PATH", config_path)

    # Mock Path.home() so validate_project_path accepts test paths
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    return conn


class TestAddProjectToTeam:
    def test_add_project_success(self, mock_db, tmp_path):
        from main import app
        client = TestClient(app)

        proj_path = str(tmp_path / "Documents" / "GitHub" / "claude-karma")
        resp = client.post("/sync/teams/my-team/projects", json={
            "name": "claude-karma",
            "path": proj_path,
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["encoded_name"].startswith("-")

        # Verify in DB
        rows = mock_db.execute("SELECT * FROM sync_team_projects WHERE team_name = ?", ("my-team",)).fetchall()
        assert len(rows) == 1

    def test_add_project_team_not_found(self, mock_db, tmp_path):
        from main import app
        client = TestClient(app)
        resp = client.post("/sync/teams/nope/projects", json={
            "name": "x", "path": str(tmp_path / "x"),
        })
        assert resp.status_code == 404

    def test_add_project_not_initialized(self, tmp_path, monkeypatch):
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        ensure_schema(conn)
        monkeypatch.setattr("services.sync_identity._get_sync_conn", lambda: conn)
        monkeypatch.setattr("karma.config.SYNC_CONFIG_PATH", tmp_path / "nope.json")
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        from main import app
        client = TestClient(app)
        # Team doesn't exist → 404
        resp = client.post("/sync/teams/my-team/projects", json={
            "name": "x", "path": str(tmp_path / "x"),
        })
        assert resp.status_code == 404


    def test_add_project_creates_outbox_and_inboxes(self, mock_db, tmp_path, monkeypatch):
        """Adding a project to a team with existing members creates outbox + inbox folders."""
        from unittest.mock import MagicMock, patch

        # Add a second member so we have someone to create inboxes for
        mock_db.execute(
            "INSERT INTO sync_members (team_name, name, device_id) VALUES (?, ?, ?)",
            ("my-team", "bob", "BOB-ID"),
        )
        mock_db.commit()

        # Mock SyncConfig with identity
        mock_config = MagicMock()
        mock_config.user_id = "jayant"
        mock_config.syncthing.device_id = "JAYANT-ID"
        mock_config.syncthing.api_key = None

        # Mock proxy
        mock_proxy = MagicMock()
        mock_proxy.update_folder_devices = MagicMock(side_effect=ValueError("not found"))
        mock_proxy.add_folder = MagicMock(return_value={"ok": True})

        monkeypatch.setattr("services.sync_identity._load_identity", lambda: mock_config)
        monkeypatch.setattr("services.sync_identity.get_proxy", lambda: mock_proxy)

        from main import app
        client = TestClient(app)

        resp = client.post("/sync/teams/my-team/projects", json={
            "name": "test-proj",
            "path": str(tmp_path / "test-proj"),
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["syncthing_folder_created"] is True

        # Verify folders_created has both outbox and inboxes
        fc = data["folders_created"]
        assert fc["outboxes"] == 1
        assert fc["inboxes"] == 2  # alice + bob
        assert fc["errors"] == []

        # Verify add_folder was called for outbox + 2 inboxes = 3 calls
        assert mock_proxy.add_folder.call_count == 3

        # Verify inbox folder IDs contain member names
        inbox_calls = [
            c for c in mock_proxy.add_folder.call_args_list
            if "receiveonly" in str(c)
        ]
        inbox_ids = [c[0][0] for c in inbox_calls]
        assert any("alice" in fid for fid in inbox_ids)
        assert any("bob" in fid for fid in inbox_ids)


class TestRemoveProjectFromTeam:
    def test_remove_project_success(self, mock_db):
        encoded = "-Users-jayant-GitHub-claude-karma"
        mock_db.execute(
            "INSERT INTO projects (encoded_name, project_path) VALUES (?, ?)",
            (encoded, "/Users/jayant/GitHub/claude-karma"),
        )
        mock_db.execute(
            "INSERT INTO sync_team_projects (team_name, project_encoded_name, path) VALUES (?, ?, ?)",
            ("my-team", encoded, "/Users/jayant/GitHub/claude-karma"),
        )
        mock_db.commit()

        from main import app
        client = TestClient(app)
        resp = client.delete(f"/sync/teams/my-team/projects/{encoded}")
        assert resp.status_code == 200

        row = mock_db.execute(
            "SELECT * FROM sync_team_projects WHERE project_encoded_name = ?", (encoded,)
        ).fetchone()
        assert row is None

    def test_remove_project_not_found(self, mock_db):
        from main import app
        client = TestClient(app)
        resp = client.delete("/sync/teams/my-team/projects/nope")
        assert resp.status_code == 404
