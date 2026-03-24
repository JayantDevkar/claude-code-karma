"""
Tests for SyncthingClient — pure HTTP wrapper for Syncthing REST API.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from services.syncthing.client import SyncthingClient


@pytest.fixture
def client():
    return SyncthingClient(api_url="http://localhost:8384", api_key="test-api-key")


@pytest.fixture
def mock_response():
    def _make(json_data, status_code=200):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = status_code
        resp.json.return_value = json_data
        resp.raise_for_status = MagicMock()
        return resp

    return _make


class TestSyncthingClientInit:
    def test_stores_api_url(self):
        c = SyncthingClient(api_url="http://host:8384", api_key="key")
        assert c.api_url == "http://host:8384"

    def test_stores_api_key(self):
        c = SyncthingClient(api_url="http://host:8384", api_key="key")
        assert c.api_key == "key"

    def test_default_timeout(self):
        c = SyncthingClient(api_url="http://host:8384", api_key="key")
        assert c.timeout == 30.0

    def test_custom_timeout(self):
        c = SyncthingClient(api_url="http://host:8384", api_key="key", timeout=10.0)
        assert c.timeout == 10.0


class TestSyncthingClientHeaders:
    def test_headers_include_api_key(self, client):
        headers = client._headers()
        assert headers["X-API-Key"] == "test-api-key"

    def test_headers_include_content_type(self, client):
        headers = client._headers()
        assert headers["Content-Type"] == "application/json"


class TestGetSystemStatus:
    async def test_returns_json(self, client, mock_response):
        expected = {"myID": "DEVICE-ID-1234", "uptime": 12345}
        with patch.object(client, "_get", new=AsyncMock(return_value=expected)):
            result = await client.get_system_status()
        assert result == expected

    async def test_calls_correct_endpoint(self, client, mock_response):
        with patch.object(client, "_get", new=AsyncMock(return_value={})) as mock_get:
            await client.get_system_status()
        mock_get.assert_called_once_with("/rest/system/status")


class TestGetConnections:
    async def test_returns_connections_json(self, client):
        expected = {"connections": {"DEVICE-ABC": {"connected": True}}}
        with patch.object(client, "_get", new=AsyncMock(return_value=expected)):
            result = await client.get_connections()
        assert result == expected

    async def test_calls_correct_endpoint(self, client):
        with patch.object(client, "_get", new=AsyncMock(return_value={})) as mock_get:
            await client.get_connections()
        mock_get.assert_called_once_with("/rest/system/connections")


class TestGetConfig:
    async def test_returns_config(self, client):
        expected = {"version": 37, "devices": [], "folders": []}
        with patch.object(client, "_get", new=AsyncMock(return_value=expected)):
            result = await client.get_config()
        assert result == expected

    async def test_calls_correct_endpoint(self, client):
        with patch.object(client, "_get", new=AsyncMock(return_value={})) as mock_get:
            await client.get_config()
        mock_get.assert_called_once_with("/rest/config")


class TestPostConfig:
    async def test_posts_config(self, client):
        config = {"version": 37, "devices": [], "folders": []}
        with patch.object(client, "_post", new=AsyncMock(return_value=None)) as mock_post:
            await client.post_config(config)
        mock_post.assert_called_once_with("/rest/config", json=config)


class TestGetConfigDevices:
    async def test_returns_devices_list(self, client):
        expected = [{"deviceID": "AAAA-BBBB", "name": "my-laptop"}]
        with patch.object(client, "_get", new=AsyncMock(return_value=expected)):
            result = await client.get_config_devices()
        assert result == expected

    async def test_calls_correct_endpoint(self, client):
        with patch.object(client, "_get", new=AsyncMock(return_value=[])) as mock_get:
            await client.get_config_devices()
        mock_get.assert_called_once_with("/rest/config/devices")


class TestPutConfigDevice:
    async def test_puts_device(self, client):
        device = {"deviceID": "AAAA-BBBB", "name": "laptop", "addresses": ["dynamic"]}
        with patch.object(client, "_put", new=AsyncMock(return_value=None)) as mock_put:
            await client.put_config_device(device)
        mock_put.assert_called_once_with("/rest/config/devices/AAAA-BBBB", json=device)


class TestDeleteConfigDevice:
    async def test_deletes_device(self, client):
        with patch.object(client, "_delete", new=AsyncMock(return_value=None)) as mock_del:
            await client.delete_config_device("AAAA-BBBB")
        mock_del.assert_called_once_with("/rest/config/devices/AAAA-BBBB")


class TestGetConfigFolders:
    async def test_returns_folders_list(self, client):
        expected = [{"id": "karma-out--user.host--abc", "label": "test"}]
        with patch.object(client, "_get", new=AsyncMock(return_value=expected)):
            result = await client.get_config_folders()
        assert result == expected

    async def test_calls_correct_endpoint(self, client):
        with patch.object(client, "_get", new=AsyncMock(return_value=[])) as mock_get:
            await client.get_config_folders()
        mock_get.assert_called_once_with("/rest/config/folders")


class TestPutConfigFolder:
    async def test_puts_folder(self, client):
        folder = {"id": "karma-out--user.host--abc", "type": "sendonly"}
        with patch.object(client, "_put", new=AsyncMock(return_value=None)) as mock_put:
            await client.put_config_folder(folder)
        mock_put.assert_called_once_with("/rest/config/folders/karma-out--user.host--abc", json=folder)


class TestDeleteConfigFolder:
    async def test_deletes_folder(self, client):
        with patch.object(client, "_delete", new=AsyncMock(return_value=None)) as mock_del:
            await client.delete_config_folder("karma-out--user.host--abc")
        mock_del.assert_called_once_with("/rest/config/folders/karma-out--user.host--abc")


class TestGetPendingDevices:
    async def test_returns_pending_devices(self, client):
        expected = {"ZZZZ-YYYY": {"name": "unknown", "time": "2026-01-01T00:00:00Z"}}
        with patch.object(client, "_get", new=AsyncMock(return_value=expected)):
            result = await client.get_pending_devices()
        assert result == expected

    async def test_calls_correct_endpoint(self, client):
        with patch.object(client, "_get", new=AsyncMock(return_value={})) as mock_get:
            await client.get_pending_devices()
        mock_get.assert_called_once_with("/rest/cluster/pending/devices")


class TestGetPendingFolders:
    async def test_returns_pending_folders(self, client):
        expected = {"karma-join--user.host--team1": {"offeredBy": {"AAAA": {}}}}
        with patch.object(client, "_get", new=AsyncMock(return_value=expected)):
            result = await client.get_pending_folders()
        assert result == expected

    async def test_calls_correct_endpoint(self, client):
        with patch.object(client, "_get", new=AsyncMock(return_value={})) as mock_get:
            await client.get_pending_folders()
        mock_get.assert_called_once_with("/rest/cluster/pending/folders")


class TestGetFolderStatus:
    async def test_returns_folder_status(self, client):
        expected = {"state": "idle", "inSyncFiles": 42}
        with patch.object(client, "_get", new=AsyncMock(return_value=expected)):
            result = await client.get_folder_status("karma-out--user.host--abc")
        assert result == expected

    async def test_passes_folder_id_as_param(self, client):
        with patch.object(client, "_get", new=AsyncMock(return_value={})) as mock_get:
            await client.get_folder_status("my-folder-id")
        mock_get.assert_called_once_with("/rest/db/status", params={"folder": "my-folder-id"})


class TestPostFolderRescan:
    async def test_posts_rescan(self, client):
        with patch.object(client, "_post", new=AsyncMock(return_value=None)) as mock_post:
            await client.post_folder_rescan("my-folder-id")
        mock_post.assert_called_once_with(
            "/rest/db/scan", params={"folder": "my-folder-id"}
        )


class TestHttpMethods:
    """Test actual HTTP method dispatch (with mocked httpx client)."""

    async def test_get_uses_get_verb(self, client):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.json.return_value = {"ok": True}
        mock_resp.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await client._get("/rest/system/status")

        mock_http.get.assert_called_once()
        assert result == {"ok": True}

    async def test_post_uses_post_verb(self, client):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            await client._post("/rest/config", json={"key": "val"})

        mock_http.post.assert_called_once()

    async def test_put_uses_put_verb(self, client):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.put = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            await client._put("/rest/config/devices", json={"deviceID": "X"})

        mock_http.put.assert_called_once()

    async def test_delete_uses_delete_verb(self, client):
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.delete = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            await client._delete("/rest/config/devices/AAAA")

        mock_http.delete.assert_called_once()
