"""Tests for SyncthingProxy service layer."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from services.syncthing_proxy import SyncthingNotRunning, SyncthingProxy


class TestDetect:
    def test_detect_not_installed(self):
        """When SyncthingClient is unavailable, returns installed=False, running=False."""
        proxy = SyncthingProxy.__new__(SyncthingProxy)
        proxy._client = None

        with patch("services.syncthing_proxy.SyncthingClient", None):
            result = proxy.detect()

        assert result["installed"] is False
        assert result["running"] is False
        assert result.get("version") is None
        assert result.get("device_id") is None

    def test_detect_not_running(self):
        """When client exists but is_running() returns False."""
        mock_client = MagicMock()
        mock_client.is_running.return_value = False

        proxy = SyncthingProxy.__new__(SyncthingProxy)
        proxy._client = mock_client

        result = proxy.detect()

        assert result["installed"] is True
        assert result["running"] is False

    def test_detect_running_returns_version_and_device_id(self):
        """When Syncthing is running, returns version and device_id from system/status."""
        mock_client = MagicMock()
        mock_client.is_running.return_value = True
        mock_client.api_url = "http://127.0.0.1:8384"
        mock_client.headers = {"X-API-Key": "test-key"}

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "myID": "AAAA-BBBB-CCCC-DDDD-EEEE-FFFF-1111-2222",
            "version": "v1.27.5",
        }

        proxy = SyncthingProxy.__new__(SyncthingProxy)
        proxy._client = mock_client

        with patch("services.syncthing_proxy.requests.get", return_value=mock_response):
            result = proxy.detect()

        assert result["installed"] is True
        assert result["running"] is True
        assert result["version"] == "v1.27.5"
        assert result["device_id"] == "AAAA-BBBB-CCCC-DDDD-EEEE-FFFF-1111-2222"


class TestGetDevices:
    def test_get_devices_not_running_raises(self):
        """When client is None, get_devices() raises SyncthingNotRunning."""
        proxy = SyncthingProxy.__new__(SyncthingProxy)
        proxy._client = None

        with pytest.raises(SyncthingNotRunning):
            proxy.get_devices()

    def test_get_devices_returns_formatted(self):
        """Merges config devices with connection status."""
        mock_client = MagicMock()
        mock_client._get_config.return_value = {
            "devices": [
                {"deviceID": "AAAA-1111", "name": "alice-laptop"},
                {"deviceID": "BBBB-2222", "name": "bob-desktop"},
            ]
        }
        mock_client.get_connections.return_value = {
            "AAAA-1111": {"connected": True, "address": "192.168.1.10:22000"},
            # BBBB-2222 not in connections → not connected
        }

        proxy = SyncthingProxy.__new__(SyncthingProxy)
        proxy._client = mock_client

        result = proxy.get_devices()

        assert len(result) == 2
        device_map = {d["device_id"]: d for d in result}

        assert device_map["AAAA-1111"]["name"] == "alice-laptop"
        assert device_map["AAAA-1111"]["connected"] is True

        assert device_map["BBBB-2222"]["name"] == "bob-desktop"
        assert device_map["BBBB-2222"]["connected"] is False


class TestGetFolderStatus:
    def test_get_folder_status_not_running_raises(self):
        """When client is None, get_folder_status() raises SyncthingNotRunning."""
        proxy = SyncthingProxy.__new__(SyncthingProxy)
        proxy._client = None

        with pytest.raises(SyncthingNotRunning):
            proxy.get_folder_status()

    def test_get_folder_status_returns_list(self):
        """Returns folder list from get_folders()."""
        mock_client = MagicMock()
        mock_client.get_folders.return_value = [
            {"id": "karma-sync", "path": "/Users/alice/.claude_karma", "type": "sendonly"},
            {"id": "karma-remote", "path": "/Users/alice/.claude_karma/remote-sessions", "type": "receiveonly"},
        ]

        proxy = SyncthingProxy.__new__(SyncthingProxy)
        proxy._client = mock_client

        result = proxy.get_folder_status()

        assert len(result) == 2
        assert result[0]["id"] == "karma-sync"
        assert result[1]["id"] == "karma-remote"


class TestAddRemoveDevice:
    def test_add_device_not_running_raises(self):
        proxy = SyncthingProxy.__new__(SyncthingProxy)
        proxy._client = None

        with pytest.raises(SyncthingNotRunning):
            proxy.add_device("AAAA-1111", "alice")

    def test_add_device_delegates_to_client(self):
        mock_client = MagicMock()
        proxy = SyncthingProxy.__new__(SyncthingProxy)
        proxy._client = mock_client

        result = proxy.add_device("AAAA-1111", "alice")

        mock_client.add_device.assert_called_once_with("AAAA-1111", "alice")
        assert result["ok"] is True

    def test_remove_device_not_running_raises(self):
        proxy = SyncthingProxy.__new__(SyncthingProxy)
        proxy._client = None

        with pytest.raises(SyncthingNotRunning):
            proxy.remove_device("AAAA-1111")

    def test_remove_device_delegates_to_client(self):
        mock_client = MagicMock()
        proxy = SyncthingProxy.__new__(SyncthingProxy)
        proxy._client = mock_client

        result = proxy.remove_device("AAAA-1111")

        mock_client.remove_device.assert_called_once_with("AAAA-1111")
        assert result["ok"] is True


class TestGetEvents:
    def test_get_events_not_running_raises(self):
        proxy = SyncthingProxy.__new__(SyncthingProxy)
        proxy._client = None

        with pytest.raises(SyncthingNotRunning):
            proxy.get_events(since=0, limit=10)

    def test_get_events_returns_list(self):
        mock_client = MagicMock()
        mock_client.api_url = "http://127.0.0.1:8384"
        mock_client.headers = {}

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"id": 1, "type": "FolderSummary", "data": {}},
            {"id": 2, "type": "DeviceConnected", "data": {}},
        ]

        proxy = SyncthingProxy.__new__(SyncthingProxy)
        proxy._client = mock_client

        with patch("services.syncthing_proxy.requests.get", return_value=mock_response):
            result = proxy.get_events(since=0, limit=50)

        assert len(result) == 2
        assert result[0]["type"] == "FolderSummary"
