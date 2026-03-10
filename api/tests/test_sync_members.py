"""Tests for sync team member management endpoints (SQLite-backed)."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

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

    # Pre-populate a team
    conn.execute("INSERT INTO sync_teams (name, backend) VALUES (?, ?)", ("my-team", "syncthing"))
    conn.commit()

    monkeypatch.setattr("services.sync_identity._get_sync_conn", lambda: conn)

    config_path = tmp_path / "sync-config.json"
    config_path.write_text('{"user_id": "jayant", "machine_id": "mac", "syncthing": {"api_key": "test-key", "device_id": "MY-DEVICE-ID"}}')
    monkeypatch.setattr("karma.config.SYNC_CONFIG_PATH", config_path)

    return conn


class TestAddMember:
    def test_add_member_success(self, mock_db):
        from main import app
        client = TestClient(app)

        with patch("services.sync_identity.get_proxy") as mock_get_proxy:
            mock_proxy = MagicMock()
            mock_proxy.add_device.return_value = {"ok": True}
            mock_get_proxy.return_value = mock_proxy

            resp = client.post("/sync/teams/my-team/members", json={
                "name": "alice",
                "device_id": "ALICE-DEVICE-ID-123",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["name"] == "alice"

        row = mock_db.execute("SELECT * FROM sync_members WHERE name = ?", ("alice",)).fetchone()
        assert row is not None
        assert row["device_id"] == "ALICE-DEVICE-ID-123"

    def test_add_member_team_not_found(self, mock_db):
        from main import app
        client = TestClient(app)
        resp = client.post("/sync/teams/nope/members", json={
            "name": "alice", "device_id": "AAAA",
        })
        assert resp.status_code == 404

    def test_add_member_invalid_name(self, mock_db):
        from main import app
        client = TestClient(app)
        resp = client.post("/sync/teams/my-team/members", json={
            "name": "../evil", "device_id": "AAAA",
        })
        assert resp.status_code == 400

    def test_add_member_not_initialized(self, tmp_path, monkeypatch):
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        ensure_schema(conn)
        monkeypatch.setattr("services.sync_identity._get_sync_conn", lambda: conn)
        monkeypatch.setattr("karma.config.SYNC_CONFIG_PATH", tmp_path / "nope.json")

        from main import app
        client = TestClient(app)
        # Team doesn't exist in DB → 404
        resp = client.post("/sync/teams/my-team/members", json={
            "name": "alice", "device_id": "AAAA",
        })
        assert resp.status_code == 404


class TestRemoveMember:
    def test_remove_member_success(self, mock_db):
        mock_db.execute(
            "INSERT INTO sync_members (team_name, name, device_id) VALUES (?, ?, ?)",
            ("my-team", "alice", "ALICE-ID"),
        )
        mock_db.commit()

        from main import app
        client = TestClient(app)

        with patch("services.sync_identity.get_proxy") as mock_get_proxy:
            mock_proxy = MagicMock()
            mock_get_proxy.return_value = mock_proxy
            resp = client.delete("/sync/teams/my-team/members/alice")

        assert resp.status_code == 200
        row = mock_db.execute("SELECT * FROM sync_members WHERE name = ?", ("alice",)).fetchone()
        assert row is None

    def test_remove_member_not_found(self, mock_db):
        from main import app
        client = TestClient(app)
        resp = client.delete("/sync/teams/my-team/members/ghost")
        assert resp.status_code == 404
