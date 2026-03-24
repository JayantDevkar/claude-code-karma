"""
Tests for FolderManager — ensure_outbox_folder, ensure_inbox_folder,
remove_outbox_folder, set_folder_devices, remove_device_from_team_folders,
cleanup_team_folders, cleanup_project_folders, and helper functions.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from unittest.mock import AsyncMock, MagicMock, call

import pytest

from services.syncthing.client import SyncthingClient
from services.syncthing.folder_manager import (
    FolderManager,
    build_metadata_folder_id,
    build_outbox_folder_id,
)

MEMBER_TAG = "alice.laptop"
REMOTE_MEMBER_TAG = "bob.desktop"
FOLDER_SUFFIX = "abc123"
TEAM_NAME = "team-alpha"
DEVICE_ID = "AAAAAAA-BBBBBBB-CCCCCCC-DDDDDDD-EEEEEEE-FFFFFFF-GGGGGGG-HHHHHHH"
DEVICE_ID_2 = "ZZZZZZZ-YYYYYYY-XXXXXXX-WWWWWWW-VVVVVVV-UUUUUUU-TTTTTTT-SSSSSSS"


@pytest.fixture
def mock_client():
    client = MagicMock(spec=SyncthingClient)
    client.get_config_folders = AsyncMock(return_value=[])
    client.put_config_folder = AsyncMock()
    client.delete_config_folder = AsyncMock()
    return client


@pytest.fixture
def karma_base(tmp_path):
    base = tmp_path / ".claude_karma"
    base.mkdir()
    return base


@pytest.fixture
def manager(mock_client, karma_base):
    return FolderManager(client=mock_client, karma_base=karma_base)


class TestBuildOutboxFolderId:
    def test_builds_correct_id(self):
        fid = build_outbox_folder_id("alice.laptop", "abc123")
        assert fid == "karma-out--alice.laptop--abc123"

    def test_different_member_tag(self):
        fid = build_outbox_folder_id("bob.desktop", "xyz789")
        assert fid == "karma-out--bob.desktop--xyz789"


class TestBuildMetadataFolderId:
    def test_builds_correct_id(self):
        fid = build_metadata_folder_id("team-alpha")
        assert fid == "karma-meta--team-alpha"

    def test_different_team(self):
        fid = build_metadata_folder_id("my-team")
        assert fid == "karma-meta--my-team"


class TestEnsureOutboxFolder:
    async def test_creates_folder_when_absent(self, manager, mock_client):
        mock_client.get_config_folders.return_value = []
        await manager.ensure_outbox_folder(MEMBER_TAG, FOLDER_SUFFIX)
        mock_client.put_config_folder.assert_called_once()

    async def test_folder_id_is_correct(self, manager, mock_client):
        mock_client.get_config_folders.return_value = []
        await manager.ensure_outbox_folder(MEMBER_TAG, FOLDER_SUFFIX)
        folder_arg = mock_client.put_config_folder.call_args[0][0]
        assert folder_arg["id"] == f"karma-out--{MEMBER_TAG}--{FOLDER_SUFFIX}"

    async def test_folder_type_is_sendonly(self, manager, mock_client):
        mock_client.get_config_folders.return_value = []
        await manager.ensure_outbox_folder(MEMBER_TAG, FOLDER_SUFFIX)
        folder_arg = mock_client.put_config_folder.call_args[0][0]
        assert folder_arg["type"] == "sendonly"

    async def test_folder_path_under_karma_base(self, manager, mock_client, karma_base):
        mock_client.get_config_folders.return_value = []
        await manager.ensure_outbox_folder(MEMBER_TAG, FOLDER_SUFFIX)
        folder_arg = mock_client.put_config_folder.call_args[0][0]
        assert folder_arg["path"].startswith(str(karma_base))

    async def test_skips_creation_when_already_exists(self, manager, mock_client):
        folder_id = build_outbox_folder_id(MEMBER_TAG, FOLDER_SUFFIX)
        mock_client.get_config_folders.return_value = [{"id": folder_id}]
        await manager.ensure_outbox_folder(MEMBER_TAG, FOLDER_SUFFIX)
        mock_client.put_config_folder.assert_not_called()


class TestEnsureInboxFolder:
    async def test_creates_folder_when_absent(self, manager, mock_client):
        mock_client.get_config_folders.return_value = []
        await manager.ensure_inbox_folder(REMOTE_MEMBER_TAG, FOLDER_SUFFIX, DEVICE_ID)
        mock_client.put_config_folder.assert_called_once()

    async def test_folder_id_matches_remote_outbox(self, manager, mock_client):
        """Inbox folder ID mirrors the remote's outbox folder ID."""
        mock_client.get_config_folders.return_value = []
        await manager.ensure_inbox_folder(REMOTE_MEMBER_TAG, FOLDER_SUFFIX, DEVICE_ID)
        folder_arg = mock_client.put_config_folder.call_args[0][0]
        expected_id = f"karma-out--{REMOTE_MEMBER_TAG}--{FOLDER_SUFFIX}"
        assert folder_arg["id"] == expected_id

    async def test_folder_type_is_receiveonly(self, manager, mock_client):
        mock_client.get_config_folders.return_value = []
        await manager.ensure_inbox_folder(REMOTE_MEMBER_TAG, FOLDER_SUFFIX, DEVICE_ID)
        folder_arg = mock_client.put_config_folder.call_args[0][0]
        assert folder_arg["type"] == "receiveonly"

    async def test_folder_includes_remote_device(self, manager, mock_client):
        mock_client.get_config_folders.return_value = []
        await manager.ensure_inbox_folder(REMOTE_MEMBER_TAG, FOLDER_SUFFIX, DEVICE_ID)
        folder_arg = mock_client.put_config_folder.call_args[0][0]
        device_ids = [d["deviceID"] for d in folder_arg.get("devices", [])]
        assert DEVICE_ID in device_ids

    async def test_skips_when_already_exists(self, manager, mock_client):
        folder_id = build_outbox_folder_id(REMOTE_MEMBER_TAG, FOLDER_SUFFIX)
        mock_client.get_config_folders.return_value = [{"id": folder_id}]
        await manager.ensure_inbox_folder(REMOTE_MEMBER_TAG, FOLDER_SUFFIX, DEVICE_ID)
        mock_client.put_config_folder.assert_not_called()


class TestRemoveOutboxFolder:
    async def test_deletes_folder(self, manager, mock_client):
        await manager.remove_outbox_folder(MEMBER_TAG, FOLDER_SUFFIX)
        expected_id = build_outbox_folder_id(MEMBER_TAG, FOLDER_SUFFIX)
        mock_client.delete_config_folder.assert_called_once_with(expected_id)


class TestSetFolderDevices:
    async def test_updates_folder_device_list(self, manager, mock_client):
        folder_id = "karma-out--alice.laptop--abc"
        mock_client.get_config_folders.return_value = [
            {"id": folder_id, "devices": [{"deviceID": DEVICE_ID}]}
        ]
        await manager.set_folder_devices(folder_id, {DEVICE_ID_2})
        folder_arg = mock_client.put_config_folder.call_args[0][0]
        device_ids = [d["deviceID"] for d in folder_arg["devices"]]
        assert device_ids == [DEVICE_ID_2]

    async def test_replaces_device_list_declaratively(self, manager, mock_client):
        """Old devices are removed, new ones set."""
        folder_id = "karma-out--alice.laptop--abc"
        mock_client.get_config_folders.return_value = [
            {"id": folder_id, "devices": [{"deviceID": DEVICE_ID}, {"deviceID": DEVICE_ID_2}]}
        ]
        await manager.set_folder_devices(folder_id, {DEVICE_ID})
        folder_arg = mock_client.put_config_folder.call_args[0][0]
        device_ids = [d["deviceID"] for d in folder_arg["devices"]]
        assert DEVICE_ID in device_ids
        assert DEVICE_ID_2 not in device_ids

    async def test_noop_when_folder_not_found(self, manager, mock_client):
        mock_client.get_config_folders.return_value = []
        await manager.set_folder_devices("nonexistent-folder", {DEVICE_ID})
        mock_client.put_config_folder.assert_not_called()


class TestRemoveDeviceFromTeamFolders:
    async def test_removes_device_from_matching_folders(self, manager, mock_client):
        folder_id_1 = build_outbox_folder_id("alice.laptop", FOLDER_SUFFIX)
        folder_id_2 = build_outbox_folder_id("bob.desktop", FOLDER_SUFFIX)
        mock_client.get_config_folders.return_value = [
            {"id": folder_id_1, "devices": [{"deviceID": DEVICE_ID}, {"deviceID": DEVICE_ID_2}]},
            {"id": folder_id_2, "devices": [{"deviceID": DEVICE_ID}]},
        ]
        await manager.remove_device_from_team_folders(
            folder_suffixes=[FOLDER_SUFFIX],
            member_tags=["alice.laptop", "bob.desktop"],
            device_id=DEVICE_ID,
        )
        # Both matching folders should be updated
        assert mock_client.put_config_folder.call_count == 2

    async def test_only_touches_matching_folders(self, manager, mock_client):
        """Folders with different suffix/member are not touched."""
        folder_id_match = build_outbox_folder_id("alice.laptop", FOLDER_SUFFIX)
        folder_id_other = build_outbox_folder_id("alice.laptop", "other-suffix")
        mock_client.get_config_folders.return_value = [
            {"id": folder_id_match, "devices": [{"deviceID": DEVICE_ID}]},
            {"id": folder_id_other, "devices": [{"deviceID": DEVICE_ID}]},
        ]
        await manager.remove_device_from_team_folders(
            folder_suffixes=[FOLDER_SUFFIX],
            member_tags=["alice.laptop"],
            device_id=DEVICE_ID,
        )
        # Only the matching folder updated
        assert mock_client.put_config_folder.call_count == 1
        folder_arg = mock_client.put_config_folder.call_args[0][0]
        assert folder_arg["id"] == folder_id_match


class TestCleanupTeamFolders:
    async def test_deletes_all_team_related_folders(self, manager, mock_client):
        outbox_1 = build_outbox_folder_id("alice.laptop", FOLDER_SUFFIX)
        outbox_2 = build_outbox_folder_id("bob.desktop", FOLDER_SUFFIX)
        meta = build_metadata_folder_id(TEAM_NAME)
        mock_client.get_config_folders.return_value = [
            {"id": outbox_1},
            {"id": outbox_2},
            {"id": meta},
            {"id": "karma-out--carol.pc--other"},  # different suffix, should NOT be deleted
        ]
        await manager.cleanup_team_folders(
            folder_suffixes=[FOLDER_SUFFIX],
            member_tags=["alice.laptop", "bob.desktop"],
            team_name=TEAM_NAME,
        )
        deleted = [c[0][0] for c in mock_client.delete_config_folder.call_args_list]
        assert outbox_1 in deleted
        assert outbox_2 in deleted
        assert meta in deleted
        assert "karma-out--carol.pc--other" not in deleted

    async def test_deletes_metadata_folder(self, manager, mock_client):
        meta = build_metadata_folder_id(TEAM_NAME)
        mock_client.get_config_folders.return_value = [{"id": meta}]
        await manager.cleanup_team_folders(
            folder_suffixes=[],
            member_tags=[],
            team_name=TEAM_NAME,
        )
        mock_client.delete_config_folder.assert_called_with(meta)


class TestCleanupProjectFolders:
    async def test_deletes_outbox_and_inbox_for_project(self, manager, mock_client):
        outbox = build_outbox_folder_id("alice.laptop", FOLDER_SUFFIX)
        remote_inbox = build_outbox_folder_id("bob.desktop", FOLDER_SUFFIX)
        unrelated = build_outbox_folder_id("alice.laptop", "other")
        mock_client.get_config_folders.return_value = [
            {"id": outbox},
            {"id": remote_inbox},
            {"id": unrelated},
        ]
        await manager.cleanup_project_folders(
            folder_suffix=FOLDER_SUFFIX,
            member_tags=["alice.laptop", "bob.desktop"],
        )
        deleted = [c[0][0] for c in mock_client.delete_config_folder.call_args_list]
        assert outbox in deleted
        assert remote_inbox in deleted
        assert unrelated not in deleted

    async def test_no_deletions_when_no_matching_folders(self, manager, mock_client):
        mock_client.get_config_folders.return_value = [
            {"id": "karma-out--alice.laptop--other"}
        ]
        await manager.cleanup_project_folders(
            folder_suffix=FOLDER_SUFFIX,
            member_tags=["alice.laptop"],
        )
        mock_client.delete_config_folder.assert_not_called()
