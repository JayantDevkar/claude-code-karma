"""Syncthing abstraction layer — pure HTTP wrappers and domain managers."""

from services.syncthing.client import SyncthingClient
from services.syncthing.device_manager import DeviceManager
from services.syncthing.folder_manager import (
    FolderManager,
    build_metadata_folder_id,
    build_outbox_folder_id,
    parse_member_tag,
    parse_outbox_id,
)

__all__ = [
    "SyncthingClient",
    "DeviceManager",
    "FolderManager",
    "build_outbox_folder_id",
    "build_metadata_folder_id",
    "parse_member_tag",
    "parse_outbox_id",
]
