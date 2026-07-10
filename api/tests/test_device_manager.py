"""
Tests for DeviceManager — pair/unpair/ensure_paired/is_connected/list_connected.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.syncthing.client import SyncthingClient
from services.syncthing.device_manager import DeviceManager


@pytest.fixture
def mock_client():
    client = MagicMock(spec=SyncthingClient)
    # Make all methods async
    client.get_config_devices = AsyncMock()
    client.put_config_device = AsyncMock()
    client.delete_config_device = AsyncMock()
    client.get_connections = AsyncMock()
    return client


@pytest.fixture
def manager(mock_client):
    return DeviceManager(client=mock_client)


DEVICE_ID = "AAAAAAA-BBBBBBB-CCCCCCC-DDDDDDD-EEEEEEE-FFFFFFF-GGGGGGG-HHHHHHH"
DEVICE_ID_2 = "ZZZZZZZ-YYYYYYY-XXXXXXX-WWWWWWW-VVVVVVV-UUUUUUU-TTTTTTT-SSSSSSS"


class TestPair:
    async def test_adds_device_to_config(self, manager, mock_client):
        mock_client.get_config_devices.return_value = []
        await manager.pair(DEVICE_ID)
        mock_client.put_config_device.assert_called_once()
        call_args = mock_client.put_config_device.call_args[0][0]
        assert call_args["deviceID"] == DEVICE_ID

    async def test_device_has_dynamic_address(self, manager, mock_client):
        mock_client.get_config_devices.return_value = []
        await manager.pair(DEVICE_ID)
        call_args = mock_client.put_config_device.call_args[0][0]
        assert "dynamic" in call_args["addresses"]

    async def test_device_has_auto_accept(self, manager, mock_client):
        mock_client.get_config_devices.return_value = []
        await manager.pair(DEVICE_ID)
        call_args = mock_client.put_config_device.call_args[0][0]
        assert call_args["autoAcceptFolders"] is False

    async def test_pair_already_existing_overwrites(self, manager, mock_client):
        """pair() always calls put, even if device already exists."""
        mock_client.get_config_devices.return_value = [{"deviceID": DEVICE_ID}]
        await manager.pair(DEVICE_ID)
        mock_client.put_config_device.assert_called_once()


class TestUnpair:
    async def test_removes_device(self, manager, mock_client):
        await manager.unpair(DEVICE_ID)
        mock_client.delete_config_device.assert_called_once_with(DEVICE_ID)

    async def test_does_not_call_put(self, manager, mock_client):
        await manager.unpair(DEVICE_ID)
        mock_client.put_config_device.assert_not_called()


class TestEnsurePaired:
    async def test_pairs_when_not_present(self, manager, mock_client):
        mock_client.get_config_devices.return_value = []
        await manager.ensure_paired(DEVICE_ID)
        mock_client.put_config_device.assert_called_once()

    async def test_skips_pair_when_already_present(self, manager, mock_client):
        mock_client.get_config_devices.return_value = [{"deviceID": DEVICE_ID}]
        await manager.ensure_paired(DEVICE_ID)
        mock_client.put_config_device.assert_not_called()

    async def test_idempotent_multiple_calls(self, manager, mock_client):
        """Second call with device present skips put."""
        mock_client.get_config_devices.return_value = [{"deviceID": DEVICE_ID}]
        await manager.ensure_paired(DEVICE_ID)
        await manager.ensure_paired(DEVICE_ID)
        mock_client.put_config_device.assert_not_called()


class TestIsConnected:
    async def test_returns_true_when_connected(self, manager, mock_client):
        mock_client.get_connections.return_value = {
            "connections": {
                DEVICE_ID: {"connected": True},
            }
        }
        result = await manager.is_connected(DEVICE_ID)
        assert result is True

    async def test_returns_false_when_disconnected(self, manager, mock_client):
        mock_client.get_connections.return_value = {
            "connections": {
                DEVICE_ID: {"connected": False},
            }
        }
        result = await manager.is_connected(DEVICE_ID)
        assert result is False

    async def test_returns_false_when_device_absent(self, manager, mock_client):
        mock_client.get_connections.return_value = {"connections": {}}
        result = await manager.is_connected(DEVICE_ID)
        assert result is False

    async def test_returns_false_on_missing_connections_key(self, manager, mock_client):
        mock_client.get_connections.return_value = {}
        result = await manager.is_connected(DEVICE_ID)
        assert result is False


class TestListConnected:
    async def test_returns_connected_device_ids(self, manager, mock_client):
        mock_client.get_connections.return_value = {
            "connections": {
                DEVICE_ID: {"connected": True},
                DEVICE_ID_2: {"connected": False},
            }
        }
        result = await manager.list_connected()
        assert DEVICE_ID in result
        assert DEVICE_ID_2 not in result

    async def test_empty_when_none_connected(self, manager, mock_client):
        mock_client.get_connections.return_value = {
            "connections": {
                DEVICE_ID: {"connected": False},
            }
        }
        result = await manager.list_connected()
        assert result == []

    async def test_empty_on_no_connections_key(self, manager, mock_client):
        mock_client.get_connections.return_value = {}
        result = await manager.list_connected()
        assert result == []

    async def test_returns_all_connected(self, manager, mock_client):
        mock_client.get_connections.return_value = {
            "connections": {
                DEVICE_ID: {"connected": True},
                DEVICE_ID_2: {"connected": True},
            }
        }
        result = await manager.list_connected()
        assert sorted(result) == sorted([DEVICE_ID, DEVICE_ID_2])
