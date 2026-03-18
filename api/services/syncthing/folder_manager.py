"""
FolderManager — high-level operations on Syncthing folder configuration.

Wraps SyncthingClient to provide idempotent folder creation/deletion and
declarative device-list management for karma outbox/inbox/metadata folders.
"""

from pathlib import Path
from typing import List, Set

from services.syncthing.client import SyncthingClient


# ---------------------------------------------------------------------------
# Helper functions (importable independently)
# ---------------------------------------------------------------------------


def build_outbox_folder_id(member_tag: str, suffix: str) -> str:
    """Return the Syncthing folder ID for an outbox folder."""
    return f"karma-out--{member_tag}--{suffix}"


def build_metadata_folder_id(team_name: str) -> str:
    """Return the Syncthing folder ID for a team metadata folder."""
    return f"karma-meta--{team_name}"


# ---------------------------------------------------------------------------
# FolderManager
# ---------------------------------------------------------------------------


class FolderManager:
    """Manages Syncthing folder configuration for karma sync folders."""

    def __init__(self, client: SyncthingClient, karma_base: Path) -> None:
        self._client = client
        self._karma_base = karma_base

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    async def get_configured_folders(self) -> list[dict]:
        """Return all configured Syncthing folders."""
        return await self._client.get_config_folders()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_folder_ids(self) -> Set[str]:
        folders = await self._client.get_config_folders()
        return {f["id"] for f in folders}

    def _folder_path(self, folder_id: str) -> str:
        return str(self._karma_base / folder_id)

    def _make_folder_config(
        self,
        folder_id: str,
        folder_type: str,
        devices: List[dict] = None,
    ) -> dict:
        return {
            "id": folder_id,
            "label": folder_id,
            "path": self._folder_path(folder_id),
            "type": folder_type,
            "devices": devices or [],
            "rescanIntervalS": 3600,
            "fsWatcherEnabled": True,
            "fsWatcherDelayS": 10,
            "ignorePerms": False,
            "autoNormalize": True,
        }

    # ------------------------------------------------------------------
    # Outbox / Inbox
    # ------------------------------------------------------------------

    async def ensure_metadata_folder(self, team_name: str) -> None:
        """Create a sendreceive metadata folder if it does not already exist."""
        folder_id = build_metadata_folder_id(team_name)
        existing_ids = await self._get_folder_ids()
        if folder_id in existing_ids:
            return
        folder = self._make_folder_config(folder_id, "sendreceive")
        # Metadata folders live under metadata-folders/ subdirectory
        folder["path"] = str(self._karma_base / "metadata-folders" / folder_id)
        await self._client.put_config_folder(folder)

    async def ensure_outbox_folder(self, member_tag: str, folder_suffix: str) -> None:
        """Create a sendonly outbox folder if it does not already exist."""
        folder_id = build_outbox_folder_id(member_tag, folder_suffix)
        existing_ids = await self._get_folder_ids()
        if folder_id in existing_ids:
            return
        folder = self._make_folder_config(folder_id, "sendonly")
        await self._client.put_config_folder(folder)

    async def ensure_inbox_folder(
        self,
        remote_member_tag: str,
        folder_suffix: str,
        remote_device_id: str,
    ) -> None:
        """Create a receiveonly inbox folder mirroring the remote's outbox.

        The folder ID is identical to the remote's outbox ID so Syncthing
        can match them automatically.
        """
        folder_id = build_outbox_folder_id(remote_member_tag, folder_suffix)
        existing_ids = await self._get_folder_ids()
        if folder_id in existing_ids:
            return
        devices = [{"deviceID": remote_device_id, "encryptionPassword": ""}]
        folder = self._make_folder_config(folder_id, "receiveonly", devices=devices)
        await self._client.put_config_folder(folder)

    async def remove_outbox_folder(self, member_tag: str, folder_suffix: str) -> None:
        """Delete an outbox folder from Syncthing config."""
        folder_id = build_outbox_folder_id(member_tag, folder_suffix)
        await self._client.delete_config_folder(folder_id)

    # ------------------------------------------------------------------
    # Declarative device-list management
    # ------------------------------------------------------------------

    async def set_folder_devices(self, folder_id: str, device_ids: Set[str]) -> None:
        """Replace the device list on a folder declaratively.

        If the folder is not found, this is a no-op.
        """
        all_folders = await self._client.get_config_folders()
        folder = next((f for f in all_folders if f["id"] == folder_id), None)
        if folder is None:
            return
        updated = dict(folder)
        updated["devices"] = [{"deviceID": did, "encryptionPassword": ""} for did in device_ids]
        await self._client.put_config_folder(updated)

    async def remove_device_from_team_folders(
        self,
        folder_suffixes: List[str],
        member_tags: List[str],
        device_id: str,
    ) -> None:
        """Remove a device from all team folders matching the given suffixes/member_tags."""
        target_ids = {
            build_outbox_folder_id(mt, suffix)
            for mt in member_tags
            for suffix in folder_suffixes
        }
        all_folders = await self._client.get_config_folders()
        for folder in all_folders:
            if folder["id"] not in target_ids:
                continue
            existing_devices = folder.get("devices", [])
            updated_devices = [d for d in existing_devices if d["deviceID"] != device_id]
            if len(updated_devices) == len(existing_devices):
                # device was not present — skip unnecessary write
                continue
            updated = dict(folder)
            updated["devices"] = updated_devices
            await self._client.put_config_folder(updated)

    # ------------------------------------------------------------------
    # Cleanup helpers
    # ------------------------------------------------------------------

    async def cleanup_team_folders(
        self,
        folder_suffixes: List[str],
        member_tags: List[str],
        team_name: str,
    ) -> None:
        """Delete all outbox folders for this team plus the metadata folder."""
        target_ids = {
            build_outbox_folder_id(mt, suffix)
            for mt in member_tags
            for suffix in folder_suffixes
        }
        meta_id = build_metadata_folder_id(team_name)
        target_ids.add(meta_id)

        all_folders = await self._client.get_config_folders()
        for folder in all_folders:
            if folder["id"] in target_ids:
                await self._client.delete_config_folder(folder["id"])

    async def cleanup_project_folders(
        self,
        folder_suffix: str,
        member_tags: List[str],
    ) -> None:
        """Delete all outbox/inbox folders for a specific project suffix."""
        target_ids = {
            build_outbox_folder_id(mt, folder_suffix) for mt in member_tags
        }
        all_folders = await self._client.get_config_folders()
        for folder in all_folders:
            if folder["id"] in target_ids:
                await self._client.delete_config_folder(folder["id"])
