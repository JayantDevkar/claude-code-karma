"""Tests for Syncthing REST API wrapper."""

from unittest.mock import patch, MagicMock
import pytest

from karma.syncthing import SyncthingClient


class TestSyncthingClient:
    def test_init_defaults(self):
        client = SyncthingClient()
        assert client.api_url == "http://127.0.0.1:8384"

    def test_init_custom(self):
        client = SyncthingClient(api_url="http://localhost:9999", api_key="abc")
        assert client.api_url == "http://localhost:9999"
        assert client.headers["X-API-Key"] == "abc"

    @patch("karma.syncthing.requests.get")
    def test_is_running_true(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {"myID": "XXXX"})
        client = SyncthingClient()
        assert client.is_running() is True

    @patch("karma.syncthing.requests.get")
    def test_is_running_false_connection_error(self, mock_get):
        import requests
        mock_get.side_effect = requests.ConnectionError()
        client = SyncthingClient()
        assert client.is_running() is False

    @patch("karma.syncthing.requests.get")
    def test_get_device_id(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"myID": "AAAAAAA-BBBBBBB-CCCCCCC-DDDDDDD"}
        )
        client = SyncthingClient(api_key="test")
        device_id = client.get_device_id()
        assert device_id == "AAAAAAA-BBBBBBB-CCCCCCC-DDDDDDD"

    @patch("karma.syncthing.requests.get")
    def test_get_connections(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "connections": {
                    "DEVICE1": {"connected": True},
                    "DEVICE2": {"connected": False},
                }
            }
        )
        client = SyncthingClient(api_key="test")
        conns = client.get_connections()
        assert "DEVICE1" in conns
        assert conns["DEVICE1"]["connected"] is True

    @patch("karma.syncthing.requests.get")
    @patch("karma.syncthing.requests.put")
    def test_add_device(self, mock_put, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"devices": [], "folders": []}
        )
        mock_put.return_value = MagicMock(status_code=200)

        client = SyncthingClient(api_key="test")
        client.add_device("NEWDEVICE-ID", "alice")

        mock_put.assert_called_once()
        put_data = mock_put.call_args[1]["json"]
        assert any(d["deviceID"] == "NEWDEVICE-ID" for d in put_data["devices"])

    @patch("karma.syncthing.requests.get")
    @patch("karma.syncthing.requests.put")
    def test_add_folder(self, mock_put, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"devices": [], "folders": []}
        )
        mock_put.return_value = MagicMock(status_code=200)

        client = SyncthingClient(api_key="test")
        client.add_folder("karma-out-alice", "/tmp/sync", ["DEVICE1"], folder_type="sendonly")

        mock_put.assert_called_once()
        put_data = mock_put.call_args[1]["json"]
        folder = put_data["folders"][0]
        assert folder["id"] == "karma-out-alice"
        assert folder["type"] == "sendonly"

    @patch("karma.syncthing.requests.get")
    def test_get_pending_folders(self, mock_get):
        pending = {
            "karma-team-proj": {
                "offeredBy": {"DEVICE-ABC": {"time": "2026-03-05T03:45:06Z"}}
            }
        }
        mock_get.return_value = MagicMock(status_code=200, json=lambda: pending)
        client = SyncthingClient(api_key="test")
        result = client.get_pending_folders()
        assert "karma-team-proj" in result
        assert "DEVICE-ABC" in result["karma-team-proj"]["offeredBy"]

    @patch("karma.syncthing.requests.get")
    def test_get_pending_folders_empty(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200, json=lambda: {})
        client = SyncthingClient(api_key="test")
        assert client.get_pending_folders() == {}

    @patch("karma.syncthing.requests.get")
    def test_find_folder_by_path(self, mock_get):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "devices": [],
                "folders": [
                    {"id": "f1", "path": "/tmp/inbox/alice", "type": "receiveonly"},
                    {"id": "f2", "path": "/tmp/outbox/me", "type": "sendonly"},
                ],
            },
        )
        client = SyncthingClient(api_key="test")
        assert client.find_folder_by_path("/tmp/inbox/alice")["id"] == "f1"
        assert client.find_folder_by_path("/nonexistent") is None
