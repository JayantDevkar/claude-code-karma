"""Tests for sync_pairing v4 router."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from unittest.mock import MagicMock, AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.sync.pairing_service import PairingInfo


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
def mock_pairing_svc():
    svc = MagicMock()
    svc.generate_code = MagicMock(return_value="ABCD-1234-EFGH")
    svc.validate_code = MagicMock()
    return svc


@pytest.fixture
def mock_device_mgr():
    mgr = MagicMock()
    mgr.list_connected = AsyncMock(return_value=["DEV-A", "DEV-B"])
    return mgr


@pytest.fixture
def client(mock_config, mock_pairing_svc, mock_device_mgr):
    from routers.sync_pairing import router, get_pairing_svc, get_device_mgr
    from routers.sync_deps import require_config

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_config] = lambda: mock_config
    app.dependency_overrides[get_pairing_svc] = lambda: mock_pairing_svc
    app.dependency_overrides[get_device_mgr] = lambda: mock_device_mgr
    return TestClient(app)


class TestGenerateCode:
    def test_returns_code(self, client, mock_pairing_svc):
        resp = client.get("/sync/pairing/code")
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == "ABCD-1234-EFGH"
        assert data["member_tag"] == "jayant.macbook"
        mock_pairing_svc.generate_code.assert_called_once_with(
            "jayant.macbook", "DEV-SELF"
        )

    def test_no_device_id_returns_400(self, client, mock_config):
        mock_config.syncthing.device_id = ""
        resp = client.get("/sync/pairing/code")
        assert resp.status_code == 400


class TestValidateCode:
    def test_valid_code(self, client, mock_pairing_svc):
        mock_pairing_svc.validate_code.return_value = PairingInfo(
            member_tag="ayush.laptop",
            device_id="DEV-A",
        )
        resp = client.post(
            "/sync/pairing/validate",
            json={"code": "ABCD-1234"},
        )
        assert resp.status_code == 200
        assert resp.json()["member_tag"] == "ayush.laptop"
        assert resp.json()["device_id"] == "DEV-A"

    def test_invalid_code_returns_400(self, client, mock_pairing_svc):
        mock_pairing_svc.validate_code.side_effect = ValueError("bad code")
        resp = client.post(
            "/sync/pairing/validate",
            json={"code": "BAD"},
        )
        assert resp.status_code == 400

    def test_missing_code_returns_422(self, client):
        resp = client.post("/sync/pairing/validate", json={})
        assert resp.status_code == 422


class TestListDevices:
    def test_returns_devices(self, client):
        resp = client.get("/sync/devices")
        assert resp.status_code == 200
        data = resp.json()
        assert data["my_device_id"] == "DEV-SELF"
        assert data["connected_devices"] == ["DEV-A", "DEV-B"]

    def test_device_manager_error_returns_empty(self, client, mock_device_mgr):
        mock_device_mgr.list_connected.side_effect = Exception("unreachable")
        resp = client.get("/sync/devices")
        assert resp.status_code == 200
        assert resp.json()["connected_devices"] == []
