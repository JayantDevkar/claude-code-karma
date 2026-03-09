"""Tests for sync status API endpoints."""

import json
import sqlite3
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from main import app
from db.schema import ensure_schema

client = TestClient(app)


@pytest.fixture
def mock_db(tmp_path, monkeypatch):
    """In-memory SQLite with schema, patched into the router."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_schema(conn)

    monkeypatch.setattr("routers.sync_status.get_writer_db", lambda: conn)
    monkeypatch.setattr("routers.sync_status._get_sync_conn", lambda: conn)

    config_path = tmp_path / "sync-config.json"
    config_path.write_text(json.dumps({
        "user_id": "alice", "machine_id": "mac", "syncthing": {},
    }))
    monkeypatch.setattr("karma.config.SYNC_CONFIG_PATH", config_path)

    from routers.sync_status import _invalidate_identity_cache
    _invalidate_identity_cache()

    return conn


class TestSyncStatus:
    def test_sync_status_no_config(self, tmp_path, monkeypatch):
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        ensure_schema(conn)
        monkeypatch.setattr("routers.sync_status.get_writer_db", lambda: conn)
        monkeypatch.setattr("routers.sync_status._get_sync_conn", lambda: conn)
        monkeypatch.setattr("karma.config.SYNC_CONFIG_PATH", tmp_path / "nonexistent.json")

        from routers.sync_status import _invalidate_identity_cache
        _invalidate_identity_cache()

        resp = client.get("/sync/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is False

    def test_sync_status_with_config(self, mock_db):
        # Add a team with a member and project
        mock_db.execute("INSERT INTO sync_teams (name, backend) VALUES (?, ?)", ("beta", "syncthing"))
        mock_db.execute("INSERT INTO sync_members (team_name, name, device_id) VALUES (?, ?, ?)",
                        ("beta", "bob", "AAAA-BBBB"))
        mock_db.execute("INSERT INTO projects (encoded_name) VALUES (?)", ("-app",))
        mock_db.execute("INSERT INTO sync_team_projects (team_name, project_encoded_name, path) VALUES (?, ?, ?)",
                        ("beta", "-app", "/app"))
        mock_db.commit()

        resp = client.get("/sync/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is True
        assert data["user_id"] == "alice"
        assert "beta" in data["teams"]
        assert data["teams"]["beta"]["member_count"] == 1
        assert data["teams"]["beta"]["project_count"] == 1

    def test_sync_teams_endpoint(self, mock_db):
        mock_db.execute("INSERT INTO sync_teams (name, backend) VALUES (?, ?)", ("alpha", "syncthing"))
        mock_db.execute("INSERT INTO sync_teams (name, backend) VALUES (?, ?)", ("beta", "syncthing"))
        mock_db.execute("INSERT INTO sync_members (team_name, name, device_id) VALUES (?, ?, ?)",
                        ("beta", "bob", "XXXX"))
        mock_db.commit()

        resp = client.get("/sync/teams")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["teams"]) == 2

    def test_sync_status_corrupt_config(self, tmp_path, monkeypatch):
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        ensure_schema(conn)
        monkeypatch.setattr("routers.sync_status.get_writer_db", lambda: conn)
        monkeypatch.setattr("routers.sync_status._get_sync_conn", lambda: conn)

        config_path = tmp_path / "sync-config.json"
        config_path.write_text("not valid json{{{")
        monkeypatch.setattr("karma.config.SYNC_CONFIG_PATH", config_path)

        from routers.sync_status import _invalidate_identity_cache
        _invalidate_identity_cache()

        resp = client.get("/sync/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is False

    def test_sync_teams_no_config(self, tmp_path, monkeypatch):
        conn = sqlite3.connect(":memory:", check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        ensure_schema(conn)
        monkeypatch.setattr("routers.sync_status.get_writer_db", lambda: conn)
        monkeypatch.setattr("routers.sync_status._get_sync_conn", lambda: conn)
        monkeypatch.setattr("karma.config.SYNC_CONFIG_PATH", tmp_path / "nonexistent.json")

        from routers.sync_status import _invalidate_identity_cache
        _invalidate_identity_cache()

        resp = client.get("/sync/teams")
        assert resp.status_code == 200
        data = resp.json()
        assert data["teams"] == []


class TestSyncDetect:
    def test_detect_not_running(self, monkeypatch):
        mock_proxy = MagicMock()
        mock_proxy.detect.return_value = {"installed": False, "running": False}
        monkeypatch.setattr("routers.sync_status.get_proxy", lambda: mock_proxy)
        resp = client.get("/sync/detect")
        assert resp.status_code == 200
        data = resp.json()
        assert data["installed"] is False
        assert data["running"] is False

    def test_detect_running(self, monkeypatch):
        mock_proxy = MagicMock()
        mock_proxy.detect.return_value = {
            "installed": True,
            "running": True,
            "version": "v1.27.0",
            "device_id": "AAAA-BBBB-CCCC",
        }
        monkeypatch.setattr("routers.sync_status.get_proxy", lambda: mock_proxy)
        resp = client.get("/sync/detect")
        assert resp.status_code == 200
        data = resp.json()
        assert data["installed"] is True
        assert data["running"] is True
        assert data["version"] == "v1.27.0"
        assert data["device_id"] == "AAAA-BBBB-CCCC"

    def test_detect_syncthing_not_running_exception(self, monkeypatch):
        from services.syncthing_proxy import SyncthingNotRunning

        mock_proxy = MagicMock()
        mock_proxy.detect.side_effect = SyncthingNotRunning("not running")
        monkeypatch.setattr("routers.sync_status.get_proxy", lambda: mock_proxy)
        resp = client.get("/sync/detect")
        assert resp.status_code == 503
        assert resp.json()["detail"] == "Syncthing is not running"


class TestSyncDevices:
    def test_list_devices(self, monkeypatch):
        mock_proxy = MagicMock()
        mock_proxy.get_devices.return_value = [
            {"device_id": "AAAA-BBBB", "name": "laptop", "connected": True},
            {"device_id": "CCCC-DDDD", "name": "server", "connected": False},
        ]
        monkeypatch.setattr("routers.sync_status.get_proxy", lambda: mock_proxy)
        resp = client.get("/sync/devices")
        assert resp.status_code == 200
        data = resp.json()
        assert "devices" in data
        assert len(data["devices"]) == 2
        assert data["devices"][0]["name"] == "laptop"

    def test_list_devices_syncthing_not_running(self, monkeypatch):
        from services.syncthing_proxy import SyncthingNotRunning

        mock_proxy = MagicMock()
        mock_proxy.get_devices.side_effect = SyncthingNotRunning("not running")
        monkeypatch.setattr("routers.sync_status.get_proxy", lambda: mock_proxy)
        resp = client.get("/sync/devices")
        assert resp.status_code == 503

    def test_add_device(self, monkeypatch):
        mock_proxy = MagicMock()
        mock_proxy.add_device.return_value = {
            "ok": True,
            "device_id": "AAAA-BBBB",
            "name": "laptop",
        }
        monkeypatch.setattr("routers.sync_status.get_proxy", lambda: mock_proxy)
        resp = client.post("/sync/devices", json={"device_id": "AAAA-BBBB", "name": "laptop"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["device_id"] == "AAAA-BBBB"

    def test_add_device_invalid_id(self, monkeypatch):
        mock_proxy = MagicMock()
        monkeypatch.setattr("routers.sync_status.get_proxy", lambda: mock_proxy)
        resp = client.post(
            "/sync/devices",
            json={"device_id": "invalid device id!", "name": "laptop"},
        )
        assert resp.status_code == 400

    def test_add_device_syncthing_not_running(self, monkeypatch):
        from services.syncthing_proxy import SyncthingNotRunning

        mock_proxy = MagicMock()
        mock_proxy.add_device.side_effect = SyncthingNotRunning("not running")
        monkeypatch.setattr("routers.sync_status.get_proxy", lambda: mock_proxy)
        resp = client.post(
            "/sync/devices", json={"device_id": "AAAA-BBBB", "name": "laptop"}
        )
        assert resp.status_code == 503

    def test_remove_device(self, monkeypatch):
        mock_proxy = MagicMock()
        mock_proxy.remove_device.return_value = {"ok": True, "device_id": "AAAA-BBBB"}
        monkeypatch.setattr("routers.sync_status.get_proxy", lambda: mock_proxy)
        resp = client.delete("/sync/devices/AAAA-BBBB")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True

    def test_remove_device_invalid_id(self, monkeypatch):
        mock_proxy = MagicMock()
        monkeypatch.setattr("routers.sync_status.get_proxy", lambda: mock_proxy)
        resp = client.delete("/sync/devices/invalid device!")
        assert resp.status_code == 400

    def test_remove_device_syncthing_not_running(self, monkeypatch):
        from services.syncthing_proxy import SyncthingNotRunning

        mock_proxy = MagicMock()
        mock_proxy.remove_device.side_effect = SyncthingNotRunning("not running")
        monkeypatch.setattr("routers.sync_status.get_proxy", lambda: mock_proxy)
        resp = client.delete("/sync/devices/AAAA-BBBB")
        assert resp.status_code == 503


class TestSyncProjects:
    def test_list_projects(self, monkeypatch):
        mock_proxy = MagicMock()
        mock_proxy.get_folder_status.return_value = [
            {"id": "folder1", "label": "Project A", "path": "/home/user/projectA"},
            {"id": "folder2", "label": "Project B", "path": "/home/user/projectB"},
        ]
        monkeypatch.setattr("routers.sync_status.get_proxy", lambda: mock_proxy)
        resp = client.get("/sync/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert "folders" in data
        assert len(data["folders"]) == 2
        assert data["folders"][0]["label"] == "Project A"

    def test_list_projects_syncthing_not_running(self, monkeypatch):
        from services.syncthing_proxy import SyncthingNotRunning

        mock_proxy = MagicMock()
        mock_proxy.get_folder_status.side_effect = SyncthingNotRunning("not running")
        monkeypatch.setattr("routers.sync_status.get_proxy", lambda: mock_proxy)
        resp = client.get("/sync/projects")
        assert resp.status_code == 503

    def test_list_projects_empty(self, monkeypatch):
        mock_proxy = MagicMock()
        mock_proxy.get_folder_status.return_value = []
        monkeypatch.setattr("routers.sync_status.get_proxy", lambda: mock_proxy)
        resp = client.get("/sync/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert data["folders"] == []


class TestSyncActivity:
    def test_get_events(self, mock_db, monkeypatch):
        from db.sync_queries import create_team, log_event
        create_team(mock_db, "alpha", "syncthing")
        log_event(mock_db, "team_created", team_name="alpha")
        log_event(mock_db, "member_added", team_name="alpha", member_name="bob")

        mock_proxy = MagicMock()
        mock_proxy.get_bandwidth.return_value = {"upload_rate": 100, "download_rate": 200, "upload_total": 1000, "download_total": 2000}
        monkeypatch.setattr("routers.sync_status.get_proxy", lambda: mock_proxy)

        resp = client.get("/sync/activity")
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert len(data["events"]) == 2

    def test_get_events_with_params(self, mock_db, monkeypatch):
        from db.sync_queries import create_team, log_event
        create_team(mock_db, "alpha", "syncthing")
        log_event(mock_db, "team_created", team_name="alpha")

        mock_proxy = MagicMock()
        mock_proxy.get_bandwidth.return_value = {"upload_rate": 0, "download_rate": 0, "upload_total": 0, "download_total": 0}
        monkeypatch.setattr("routers.sync_status.get_proxy", lambda: mock_proxy)

        resp = client.get("/sync/activity?limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["events"]) == 1

    def test_get_events_empty(self, mock_db, monkeypatch):
        mock_proxy = MagicMock()
        mock_proxy.get_bandwidth.return_value = {"upload_rate": 0, "download_rate": 0, "upload_total": 0, "download_total": 0}
        monkeypatch.setattr("routers.sync_status.get_proxy", lambda: mock_proxy)

        resp = client.get("/sync/activity")
        assert resp.status_code == 200
        data = resp.json()
        assert data["events"] == []


class TestSyncInit:
    def test_init_syncthing(self, monkeypatch):
        mock_proxy = MagicMock()
        mock_proxy.detect.return_value = {
            "installed": True,
            "running": True,
            "version": "v1.27.0",
            "device_id": "AAAA-BBBB-CCCC",
        }
        monkeypatch.setattr("routers.sync_status.get_proxy", lambda: mock_proxy)

        monkeypatch.setattr(
            "karma.syncthing.read_local_api_key",
            lambda: "fake-api-key",
        )

        saved = []
        monkeypatch.setattr(
            "karma.config.SyncConfig.save",
            lambda self: saved.append(self),
        )

        resp = client.post("/sync/init", json={"user_id": "alice", "backend": "syncthing"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["user_id"] == "alice"
        assert data["device_id"] == "AAAA-BBBB-CCCC"
        assert data["machine_id"] is not None
        assert len(saved) == 1

    def test_init_invalid_user_id(self, monkeypatch):
        resp = client.post("/sync/init", json={"user_id": "bad user!@#", "backend": "syncthing"})
        assert resp.status_code == 400

    def test_init_syncthing_not_running(self, monkeypatch):
        mock_proxy = MagicMock()
        mock_proxy.detect.return_value = {
            "installed": True,
            "running": False,
        }
        monkeypatch.setattr("routers.sync_status.get_proxy", lambda: mock_proxy)

        resp = client.post("/sync/init", json={"user_id": "alice", "backend": "syncthing"})
        assert resp.status_code == 503
