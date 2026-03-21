"""Shared dependencies for sync v4 routers.

Provides connection, config, repo, and service factories used via FastAPI
Depends().  All domain imports are lazy to avoid circular imports and to
survive the deletion of v3 modules in Task 3.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import HTTPException


# Simple name validation (replaces sync_identity.validate_user_id)
_VALID_NAME = re.compile(r"^[a-zA-Z0-9_-]+$")


def validate_name(value: str, label: str = "name") -> None:
    """Validate a name is 2-64 chars, alphanumeric + dash/underscore."""
    if not value or not _VALID_NAME.match(value) or len(value) < 2 or len(value) > 64:
        raise HTTPException(
            400, f"Invalid {label}: must be 2-64 characters, [a-zA-Z0-9_-]"
        )


# ---------------------------------------------------------------------------
# FastAPI dependencies (overridable in tests via app.dependency_overrides)
# ---------------------------------------------------------------------------


def get_conn() -> sqlite3.Connection:
    """Return the SQLite writer connection."""
    from db.connection import get_writer_db

    return get_writer_db()


def get_read_conn() -> sqlite3.Connection:
    """Read-only connection for sync GET endpoints."""
    from db.connection import create_read_connection

    return create_read_connection()


async def require_config() -> Any:
    """Load SyncConfig from disk.  HTTPException 400 if not initialized."""
    from models.sync_config import SyncConfig

    config = SyncConfig.load()
    if config is None:
        raise HTTPException(400, "Not initialized. Run POST /sync/init first.")
    return config


async def get_optional_config() -> Any:
    """Load SyncConfig, returning None if not initialized (no error)."""
    from models.sync_config import SyncConfig

    return SyncConfig.load()


# ---------------------------------------------------------------------------
# Factories (called from router endpoints, NOT registered as Depends)
# ---------------------------------------------------------------------------


def make_repos() -> dict:
    """Instantiate all five v4 repositories (stateless, cheap)."""
    from repositories.team_repo import TeamRepository
    from repositories.member_repo import MemberRepository
    from repositories.project_repo import ProjectRepository
    from repositories.subscription_repo import SubscriptionRepository
    from repositories.event_repo import EventRepository

    return dict(
        teams=TeamRepository(),
        members=MemberRepository(),
        projects=ProjectRepository(),
        subs=SubscriptionRepository(),
        events=EventRepository(),
    )


def make_managers(config: Any):
    """Create (DeviceManager, FolderManager, MetadataService) from config.

    Returns a 3-tuple: (devices, folders, metadata).
    """
    from config import settings as app_settings
    from services.syncthing.client import SyncthingClient
    from services.syncthing.device_manager import DeviceManager
    from services.syncthing.folder_manager import FolderManager
    from services.sync.metadata_service import MetadataService

    api_key = config.syncthing.api_key if config.syncthing else ""
    client = SyncthingClient(api_url="http://localhost:8384", api_key=api_key)
    devices = DeviceManager(client)
    folders = FolderManager(client, karma_base=app_settings.karma_base)
    metadata = MetadataService(
        meta_base=app_settings.karma_base / "metadata-folders"
    )
    return devices, folders, metadata


def make_team_service(config: Any):
    """Build TeamService from runtime config."""
    from services.sync.team_service import TeamService

    repos = make_repos()
    devices, folders, metadata = make_managers(config)
    return TeamService(**repos, devices=devices, metadata=metadata, folders=folders)


def make_project_service(config: Any):
    """Build ProjectService from runtime config."""
    from services.sync.project_service import ProjectService

    repos = make_repos()
    _, folders, metadata = make_managers(config)
    return ProjectService(**repos, folders=folders, metadata=metadata)


def make_reconciliation_service(config: Any):
    """Build ReconciliationService from runtime config."""
    from services.sync.reconciliation_service import ReconciliationService

    repos = make_repos()
    devices, folders, metadata = make_managers(config)
    device_id = config.syncthing.device_id if config.syncthing else ""
    return ReconciliationService(
        **repos,
        devices=devices,
        folders=folders,
        metadata=metadata,
        my_member_tag=config.member_tag,
        my_device_id=device_id,
    )
