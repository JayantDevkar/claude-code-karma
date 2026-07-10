"""Tests for sync_pending v4 router (pending devices + folders)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from unittest.mock import MagicMock, AsyncMock, PropertyMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.user_id = "jayant"
    config.member_tag = "jayant.macbook"
    config.syncthing = MagicMock()
    config.syncthing.device_id = "DEV-SELF"
    config.syncthing.api_key = "test-key"
    return config


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.get_pending_devices = AsyncMock(return_value={})
    client.get_pending_folders = AsyncMock(return_value={})
    client.put_config_device = AsyncMock()
    client.put_config_folder = AsyncMock()
    client.dismiss_pending_device = AsyncMock()
    client.dismiss_pending_folder = AsyncMock()
    return client


@pytest.fixture
def mock_folder_mgr():
    mgr = MagicMock()
    mgr.ensure_inbox_folder = AsyncMock()
    return mgr


@pytest.fixture
def client(mock_config, mock_client, mock_folder_mgr):
    from routers.sync_pending import router, get_syncthing_client, get_folder_mgr
    from routers.sync_deps import require_config

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_config] = lambda: mock_config
    app.dependency_overrides[get_syncthing_client] = lambda: mock_client
    app.dependency_overrides[get_folder_mgr] = lambda: mock_folder_mgr
    return TestClient(app)


# ---------------------------------------------------------------------------
# Pending devices
# ---------------------------------------------------------------------------


class TestListPendingDevices:
    def test_empty(self, client):
        resp = client.get("/sync/pending-devices")
        assert resp.status_code == 200
        assert resp.json()["devices"] == []

    def test_returns_devices(self, client, mock_client):
        mock_client.get_pending_devices.return_value = {
            "DEV-A": {"name": "alice", "address": "192.168.1.2:22000", "time": "2026-03-18T10:00:00Z"},
            "DEV-B": {"name": "bob", "address": "192.168.1.3:22000", "time": "2026-03-18T10:05:00Z"},
        }
        resp = client.get("/sync/pending-devices")
        assert resp.status_code == 200
        devices = resp.json()["devices"]
        assert len(devices) == 2
        ids = {d["device_id"] for d in devices}
        assert "DEV-A" in ids
        assert "DEV-B" in ids

    def test_syncthing_error_returns_empty(self, client, mock_client):
        mock_client.get_pending_devices.side_effect = Exception("unreachable")
        resp = client.get("/sync/pending-devices")
        assert resp.status_code == 200
        assert resp.json()["devices"] == []


class TestAcceptPendingDevice:
    def test_returns_ok(self, client, mock_client):
        resp = client.post(
            "/sync/pending-devices/DEV-A/accept",
            json={},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert resp.json()["device_id"] == "DEV-A"
        mock_client.put_config_device.assert_called_once()
        call_args = mock_client.put_config_device.call_args[0][0]
        assert call_args["deviceID"] == "DEV-A"

    def test_with_name(self, client, mock_client):
        resp = client.post(
            "/sync/pending-devices/DEV-A/accept",
            json={"name": "Alice Laptop"},
        )
        assert resp.status_code == 200
        call_args = mock_client.put_config_device.call_args[0][0]
        assert call_args["name"] == "Alice Laptop"

    def test_syncthing_error_returns_500(self, client, mock_client):
        mock_client.put_config_device.side_effect = Exception("config error")
        resp = client.post(
            "/sync/pending-devices/DEV-A/accept",
            json={},
        )
        assert resp.status_code == 500

    def test_empty_body_accepted(self, client, mock_client):
        resp = client.post("/sync/pending-devices/DEV-A/accept", json={})
        assert resp.status_code == 200


class TestDismissPendingDevice:
    def test_returns_ok(self, client, mock_client):
        resp = client.delete("/sync/pending-devices/DEV-A")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        mock_client.dismiss_pending_device.assert_called_once_with("DEV-A")

    def test_syncthing_error_returns_500(self, client, mock_client):
        mock_client.dismiss_pending_device.side_effect = Exception("fail")
        resp = client.delete("/sync/pending-devices/DEV-A")
        assert resp.status_code == 500


# ---------------------------------------------------------------------------
# Pending folders
# ---------------------------------------------------------------------------


class TestListPendingFolders:
    def test_empty(self, client):
        resp = client.get("/sync/pending")
        assert resp.status_code == 200
        assert resp.json()["folders"] == []

    def test_returns_folders(self, client, mock_client):
        mock_client.get_pending_folders.return_value = {
            "karma-out--alice.laptop--user-repo": {
                "DEV-A": {
                    "label": "karma-out--alice.laptop--user-repo",
                    "time": "2026-03-18T10:00:00Z",
                }
            },
        }
        resp = client.get("/sync/pending")
        assert resp.status_code == 200
        folders = resp.json()["folders"]
        assert len(folders) == 1
        f = folders[0]
        assert f["folder_id"] == "karma-out--alice.laptop--user-repo"
        assert f["from_device"] == "DEV-A"
        assert f["from_member"] == "alice.laptop"
        assert f["folder_type"] == "out"

    def test_multiple_devices_per_folder(self, client, mock_client):
        mock_client.get_pending_folders.return_value = {
            "karma-out--a.mac--repo": {
                "DEV-A": {"label": "folder", "time": "t1"},
                "DEV-B": {"label": "folder", "time": "t2"},
            },
        }
        resp = client.get("/sync/pending")
        folders = resp.json()["folders"]
        assert len(folders) == 2

    def test_syncthing_error_returns_empty(self, client, mock_client):
        mock_client.get_pending_folders.side_effect = Exception("unreachable")
        resp = client.get("/sync/pending")
        assert resp.status_code == 200
        assert resp.json()["folders"] == []


class TestAcceptPendingFolder:
    def test_returns_ok(self, client, mock_client):
        mock_client.get_pending_folders.return_value = {
            "karma-out--alice.laptop--repo": {
                "DEV-A": {"label": "karma-out--alice.laptop--repo", "time": "t1"},
            },
        }
        with patch("config.settings") as mock_settings:
            mock_settings.karma_base = Path("/tmp/karma-test")
            resp = client.post("/sync/pending/accept/karma-out--alice.laptop--repo")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        mock_client.put_config_folder.assert_called_once()

    def test_folder_not_found_returns_404(self, client, mock_client):
        mock_client.get_pending_folders.return_value = {}
        resp = client.post("/sync/pending/accept/nonexistent-folder")
        assert resp.status_code == 404


class TestRejectPendingFolder:
    def test_returns_ok(self, client, mock_client):
        resp = client.post(
            "/sync/pending/reject/karma-out--alice.laptop--repo",
            json={"device_id": "DEV-A"},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        mock_client.dismiss_pending_folder.assert_called_once_with(
            "karma-out--alice.laptop--repo", "DEV-A"
        )

    def test_syncthing_error_returns_500(self, client, mock_client):
        mock_client.dismiss_pending_folder.side_effect = Exception("fail")
        resp = client.post(
            "/sync/pending/reject/karma-out--alice.laptop--repo",
            json={"device_id": "DEV-A"},
        )
        assert resp.status_code == 500

    def test_missing_device_id_returns_422(self, client):
        resp = client.post("/sync/pending/reject/some-folder", json={})
        assert resp.status_code == 422
