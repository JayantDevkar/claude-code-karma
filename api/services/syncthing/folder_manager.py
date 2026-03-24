"""
FolderManager — high-level operations on Syncthing folder configuration.

Wraps SyncthingClient to provide idempotent folder creation/deletion and
declarative device-list management for karma outbox/inbox/metadata folders.

Also provides folder-ID parsing utilities (``parse_member_tag``,
``parse_outbox_id``) that were previously in ``services.folder_id``.
"""

import logging
import sqlite3
from pathlib import Path
from typing import List, Optional, Set

from services.syncthing.client import SyncthingClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OUTBOX_PREFIX = "karma-out--"


# ---------------------------------------------------------------------------
# Helper functions (importable independently)
# ---------------------------------------------------------------------------


def build_outbox_folder_id(member_tag: str, suffix: str) -> str:
    """Return the Syncthing folder ID for an outbox folder."""
    return f"karma-out--{member_tag}--{suffix}"


def build_metadata_folder_id(team_name: str) -> str:
    """Return the Syncthing folder ID for a team metadata folder."""
    return f"karma-meta--{team_name}"


def resolve_folder_path(karma_base: Path, folder_id: str) -> Path:
    """Return the filesystem path for a Syncthing folder.

    Metadata folders (karma-meta--*) live under metadata-folders/ subdirectory.
    All other folders (karma-out--*) live flat under karma_base.
    """
    if folder_id.startswith("karma-meta--"):
        return karma_base / "metadata-folders" / folder_id
    return karma_base / folder_id


def resolve_folder_type(folder_id: str) -> str:
    """Return the Syncthing folder type for a given folder ID.

    Metadata folders are sendreceive; outbox folders are sendonly by default.
    """
    if folder_id.startswith("karma-meta--"):
        return "sendreceive"
    return "receiveonly"


def build_folder_config(
    karma_base: Path,
    folder_id: str,
    folder_type: str,
    devices: List[dict] | None = None,
) -> dict:
    """Build a Syncthing folder configuration dict.

    Single source of truth for the 10-key config dict used when creating
    or accepting Syncthing folders.  All call sites (FolderManager, reconciler,
    pending-folder router) should use this instead of constructing dicts inline.
    """
    return {
        "id": folder_id,
        "label": folder_id,
        "path": str(resolve_folder_path(karma_base, folder_id)),
        "type": folder_type,
        "devices": devices or [],
        "rescanIntervalS": 3600,
        "fsWatcherEnabled": True,
        "fsWatcherDelayS": 10,
        "ignorePerms": False,
        "autoNormalize": True,
    }


def parse_outbox_id(folder_id: str) -> Optional[tuple[str, str]]:
    """Parse ``karma-out--{username}--{suffix}`` into ``(username, suffix)``.

    Returns ``None`` if the folder ID does not match the expected format.
    """
    if not folder_id.startswith(OUTBOX_PREFIX):
        return None
    rest = folder_id[len(OUTBOX_PREFIX):]
    parts = rest.split("--")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return parts[0], parts[1]


def parse_member_tag(member_tag: str) -> tuple[str, Optional[str]]:
    """Parse member_tag into (user_id, machine_tag).

    Format: ``{user_id}.{machine_tag}`` or bare ``{user_id}`` (legacy).
    Splits on the FIRST dot only.

    Returns:
        (user_id, machine_tag) -- machine_tag is None if no dot present.
    """
    if "." in member_tag:
        user_id, machine_tag_part = member_tag.split(".", 1)
        return user_id, machine_tag_part
    return member_tag, None


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
        return str(resolve_folder_path(self._karma_base, folder_id))

    def _make_folder_config(
        self,
        folder_id: str,
        folder_type: str,
        devices: List[dict] = None,
    ) -> dict:
        return build_folder_config(self._karma_base, folder_id, folder_type, devices)

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

    def _is_folder_needed_by_other_team(
        self,
        conn: sqlite3.Connection,
        folder_suffix: str,
        member_tag: str,
        team_name: str,
    ) -> bool:
        """Check if another team still needs a folder with this suffix for this member.

        Returns True if at least one other team has an active subscription
        (offered/accepted/paused) for a project with the same folder_suffix.
        """
        row = conn.execute(
            """
            SELECT COUNT(*) FROM sync_subscriptions s
            JOIN sync_projects p
              ON s.team_name = p.team_name
             AND s.project_git_identity = p.git_identity
            WHERE p.folder_suffix = ?
              AND s.member_tag = ?
              AND s.status IN ('offered', 'accepted', 'paused')
              AND s.team_name != ?
            """,
            (folder_suffix, member_tag, team_name),
        ).fetchone()
        return row[0] > 0

    async def cleanup_team_folders(
        self,
        folder_suffixes: List[str],
        member_tags: List[str],
        team_name: str,
        conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        """Delete all outbox folders for this team plus the metadata folder.

        If ``conn`` is provided, each outbox folder is checked against other
        teams' subscriptions before deletion.  Folders still needed by another
        team are skipped.  The metadata folder (team-scoped) is always deleted.

        When ``conn`` is None the legacy behaviour is preserved: all matching
        folders are deleted unconditionally.
        """
        meta_id = build_metadata_folder_id(team_name)

        all_folders = await self._client.get_config_folders()
        for folder in all_folders:
            fid = folder["id"]

            # Metadata folder is always team-scoped — safe to delete
            if fid == meta_id:
                await self._client.delete_config_folder(fid)
                continue

            # Check each outbox folder
            for mt in member_tags:
                for suffix in folder_suffixes:
                    if fid != build_outbox_folder_id(mt, suffix):
                        continue
                    if conn is not None and self._is_folder_needed_by_other_team(
                        conn, suffix, mt, team_name,
                    ):
                        logger.info(
                            "cleanup_team_folders: skipping folder %s "
                            "(still needed by another team)",
                            fid,
                        )
                        continue
                    await self._client.delete_config_folder(fid)

    async def cleanup_project_folders(
        self,
        folder_suffix: str,
        member_tags: List[str],
        conn: Optional[sqlite3.Connection] = None,
        team_name: Optional[str] = None,
    ) -> None:
        """Delete all outbox/inbox folders for a specific project suffix.

        If ``conn`` and ``team_name`` are provided, each folder is checked
        against other teams' subscriptions before deletion.  Folders still
        needed by another team are skipped.

        When ``conn`` is None the legacy behaviour is preserved.
        """
        # Build a map from folder_id → member_tag for cross-team lookups
        folder_to_member: dict[str, str] = {
            build_outbox_folder_id(mt, folder_suffix): mt for mt in member_tags
        }
        all_folders = await self._client.get_config_folders()
        for folder in all_folders:
            fid = folder["id"]
            mt = folder_to_member.get(fid)
            if mt is None:
                continue

            if conn is not None and team_name is not None:
                if self._is_folder_needed_by_other_team(
                    conn, folder_suffix, mt, team_name,
                ):
                    logger.info(
                        "cleanup_project_folders: skipping folder %s "
                        "(still needed by another team)",
                        fid,
                    )
                    continue

            await self._client.delete_config_folder(fid)
