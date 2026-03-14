"""Tests for metadata folder creation during team create/join."""

import json
from unittest.mock import MagicMock, patch
import pytest


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.user_id = "jayant"
    config.machine_id = "Mac-Mini"
    config.machine_tag = "mac-mini"
    config.member_tag = "jayant.mac-mini"
    config.syncthing = MagicMock()
    config.syncthing.device_id = "LEADER-DID"
    return config


@pytest.mark.asyncio
async def test_ensure_metadata_folder_creates_sendreceive(mock_config, tmp_path):
    """Metadata folder should be created as sendreceive type."""
    mock_proxy = MagicMock()
    mock_proxy.update_folder_devices = MagicMock(side_effect=ValueError("not found"))
    mock_proxy.add_folder = MagicMock()

    with patch("karma.config.KARMA_BASE", tmp_path):
        from services.sync_folders import ensure_metadata_folder

        await ensure_metadata_folder(
            mock_proxy, mock_config, "acme", ["LEADER-DID", "AYUSH-DID"]
        )

    # Verify add_folder was called with sendreceive type
    mock_proxy.add_folder.assert_called_once()
    call_args = mock_proxy.add_folder.call_args
    assert call_args[0][0] == "karma-meta--acme"  # folder_id
    assert call_args[0][3] == "sendreceive"  # folder_type


@pytest.mark.asyncio
async def test_ensure_metadata_folder_writes_team_info_for_creator(mock_config, tmp_path):
    """Creator should get team.json written."""
    mock_proxy = MagicMock()
    mock_proxy.update_folder_devices = MagicMock(side_effect=ValueError("not found"))
    mock_proxy.add_folder = MagicMock()

    with patch("karma.config.KARMA_BASE", tmp_path):
        from services.sync_folders import ensure_metadata_folder

        await ensure_metadata_folder(
            mock_proxy, mock_config, "acme", ["LEADER-DID"],
            is_creator=True,
        )

    team_file = tmp_path / "metadata-folders" / "acme" / "team.json"
    assert team_file.exists()
    data = json.loads(team_file.read_text())
    assert data["created_by"] == "jayant.mac-mini"
    assert data["name"] == "acme"


@pytest.mark.asyncio
async def test_ensure_metadata_folder_writes_own_member_state(mock_config, tmp_path):
    """Member's own state file should be written."""
    mock_proxy = MagicMock()
    mock_proxy.update_folder_devices = MagicMock(side_effect=ValueError("not found"))
    mock_proxy.add_folder = MagicMock()

    with patch("karma.config.KARMA_BASE", tmp_path):
        from services.sync_folders import ensure_metadata_folder

        await ensure_metadata_folder(
            mock_proxy, mock_config, "acme", ["LEADER-DID"],
        )

    state_file = tmp_path / "metadata-folders" / "acme" / "members" / "jayant.mac-mini.json"
    assert state_file.exists()
    data = json.loads(state_file.read_text())
    assert data["member_tag"] == "jayant.mac-mini"
    assert data["user_id"] == "jayant"


@pytest.mark.asyncio
async def test_ensure_metadata_folder_no_team_json_for_joiner(mock_config, tmp_path):
    """Non-creator joiner should NOT get team.json written."""
    mock_proxy = MagicMock()
    mock_proxy.update_folder_devices = MagicMock(side_effect=ValueError("not found"))
    mock_proxy.add_folder = MagicMock()

    with patch("karma.config.KARMA_BASE", tmp_path):
        from services.sync_folders import ensure_metadata_folder

        await ensure_metadata_folder(
            mock_proxy, mock_config, "acme", ["LEADER-DID"],
            is_creator=False,
        )

    team_file = tmp_path / "metadata-folders" / "acme" / "team.json"
    assert not team_file.exists()


@pytest.mark.asyncio
async def test_ensure_metadata_folder_updates_existing(mock_config, tmp_path):
    """If folder already exists, update_folder_devices succeeds (no add_folder)."""
    mock_proxy = MagicMock()
    mock_proxy.update_folder_devices = MagicMock()  # succeeds
    mock_proxy.add_folder = MagicMock()

    with patch("karma.config.KARMA_BASE", tmp_path):
        from services.sync_folders import ensure_metadata_folder

        await ensure_metadata_folder(
            mock_proxy, mock_config, "acme", ["LEADER-DID", "AYUSH-DID"],
        )

    mock_proxy.update_folder_devices.assert_called_once()
    mock_proxy.add_folder.assert_not_called()
