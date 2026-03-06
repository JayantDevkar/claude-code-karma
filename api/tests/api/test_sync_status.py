"""Tests for sync status API endpoints."""

import json
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


class TestSyncStatus:
    def test_sync_status_no_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "routers.sync_status.SYNC_CONFIG_PATH",
            tmp_path / "nonexistent.json",
        )
        resp = client.get("/sync/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is False

    def test_sync_status_with_config(self, tmp_path, monkeypatch):
        config_path = tmp_path / "sync-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "user_id": "alice",
                    "machine_id": "mac",
                    "teams": {
                        "beta": {
                            "backend": "syncthing",
                            "projects": {"app": {"path": "/app", "encoded_name": "-app"}},
                            "syncthing_members": {"bob": {"syncthing_device_id": "AAAA-BBBB"}},
                            "ipfs_members": {},
                        }
                    },
                    "projects": {},
                    "team": {},
                }
            )
        )
        monkeypatch.setattr("routers.sync_status.SYNC_CONFIG_PATH", config_path)
        resp = client.get("/sync/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is True
        assert data["user_id"] == "alice"
        assert "beta" in data["teams"]
        assert data["teams"]["beta"]["member_count"] == 1
        assert data["teams"]["beta"]["project_count"] == 1

    def test_sync_teams_endpoint(self, tmp_path, monkeypatch):
        config_path = tmp_path / "sync-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "user_id": "alice",
                    "machine_id": "mac",
                    "teams": {
                        "alpha": {
                            "backend": "ipfs",
                            "projects": {},
                            "ipfs_members": {"carol": {"ipns_key": "abc123"}},
                            "syncthing_members": {},
                        },
                        "beta": {
                            "backend": "syncthing",
                            "projects": {},
                            "ipfs_members": {},
                            "syncthing_members": {"bob": {"syncthing_device_id": "XXXX"}},
                        },
                    },
                    "projects": {},
                    "team": {},
                }
            )
        )
        monkeypatch.setattr("routers.sync_status.SYNC_CONFIG_PATH", config_path)
        resp = client.get("/sync/teams")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["teams"]) == 2
        # Verify members are correctly read from split dicts
        team_names = {t["name"]: t for t in data["teams"]}
        assert "carol" in team_names["alpha"]["members"]
        assert "bob" in team_names["beta"]["members"]

    def test_sync_status_corrupt_config(self, tmp_path, monkeypatch):
        config_path = tmp_path / "sync-config.json"
        config_path.write_text("not valid json{{{")
        monkeypatch.setattr("routers.sync_status.SYNC_CONFIG_PATH", config_path)
        resp = client.get("/sync/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is False

    def test_sync_teams_no_config(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "routers.sync_status.SYNC_CONFIG_PATH",
            tmp_path / "nonexistent.json",
        )
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
    def test_get_events(self, monkeypatch):
        mock_proxy = MagicMock()
        mock_proxy.get_events.return_value = [
            {"id": 1, "type": "FolderSummary", "time": "2026-03-05T10:00:00Z"},
            {"id": 2, "type": "StateChanged", "time": "2026-03-05T10:01:00Z"},
        ]
        monkeypatch.setattr("routers.sync_status.get_proxy", lambda: mock_proxy)
        resp = client.get("/sync/activity")
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert len(data["events"]) == 2
        assert data["events"][0]["type"] == "FolderSummary"

    def test_get_events_with_params(self, monkeypatch):
        mock_proxy = MagicMock()
        mock_proxy.get_events.return_value = []
        monkeypatch.setattr("routers.sync_status.get_proxy", lambda: mock_proxy)
        resp = client.get("/sync/activity?since=100&limit=10")
        assert resp.status_code == 200
        mock_proxy.get_events.assert_called_once_with(100, 10)

    def test_get_events_syncthing_not_running(self, monkeypatch):
        from services.syncthing_proxy import SyncthingNotRunning

        mock_proxy = MagicMock()
        mock_proxy.get_events.side_effect = SyncthingNotRunning("not running")
        monkeypatch.setattr("routers.sync_status.get_proxy", lambda: mock_proxy)
        resp = client.get("/sync/activity")
        assert resp.status_code == 503

    def test_get_events_empty(self, monkeypatch):
        mock_proxy = MagicMock()
        mock_proxy.get_events.return_value = []
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

        # Mock read_local_api_key (imported inside the endpoint)
        monkeypatch.setattr(
            "karma.syncthing.read_local_api_key",
            lambda: "fake-api-key",
        )

        # Mock SyncConfig.save to avoid writing to disk
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

    def test_init_ipfs(self, monkeypatch):
        saved = []
        monkeypatch.setattr(
            "karma.config.SyncConfig.save",
            lambda self: saved.append(self),
        )

        resp = client.post("/sync/init", json={"user_id": "bob", "backend": "ipfs"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["user_id"] == "bob"
        assert data["device_id"] is None
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


class TestSyncProjectEndpoints:
    def _make_mock_config(self, projects=None):
        """Create a mock SyncConfig with the given projects dict."""
        mock_config = MagicMock()
        mock_config.projects = projects if projects is not None else {}

        def mock_model_copy(update=None):
            new_mock = MagicMock()
            new_mock.projects = update.get("projects", mock_config.projects) if update else mock_config.projects
            new_mock.save = MagicMock()
            return new_mock

        mock_config.model_copy = mock_model_copy
        return mock_config

    def test_enable_project(self, monkeypatch):
        mock_config = self._make_mock_config()
        mock_project_config = MagicMock()

        def mock_load_sync_config():
            MockProjectConfig = MagicMock(return_value=mock_project_config)
            return mock_config, MagicMock, MockProjectConfig

        monkeypatch.setattr(
            "routers.sync_status._load_sync_config",
            mock_load_sync_config,
        )

        resp = client.post("/sync/projects/-Users-alice-my-project/enable")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["project"] == "-Users-alice-my-project"

    def test_disable_project(self, monkeypatch):
        mock_config = self._make_mock_config(
            projects={"-Users-alice-my-project": MagicMock()}
        )

        def mock_load_sync_config():
            return mock_config, MagicMock, MagicMock

        monkeypatch.setattr(
            "routers.sync_status._load_sync_config",
            mock_load_sync_config,
        )

        resp = client.post("/sync/projects/-Users-alice-my-project/disable")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["project"] == "-Users-alice-my-project"

    def test_sync_now(self, monkeypatch):
        resp = client.post("/sync/projects/-Users-alice-my-project/sync-now")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["project"] == "-Users-alice-my-project"
        assert data["message"] == "Sync triggered"

    def test_enable_not_initialized(self, monkeypatch):
        def mock_load_sync_config():
            return None, MagicMock, MagicMock

        monkeypatch.setattr(
            "routers.sync_status._load_sync_config",
            mock_load_sync_config,
        )

        resp = client.post("/sync/projects/-Users-alice-my-project/enable")
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Not initialized"

    def test_enable_invalid_name(self, monkeypatch):
        resp = client.post("/sync/projects/invalid%20name!@/enable")
        assert resp.status_code == 400

    def test_disable_not_initialized(self, monkeypatch):
        def mock_load_sync_config():
            return None, MagicMock, MagicMock

        monkeypatch.setattr(
            "routers.sync_status._load_sync_config",
            mock_load_sync_config,
        )

        resp = client.post("/sync/projects/-Users-alice-my-project/disable")
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Not initialized"
