"""Sync configuration management."""

import json
import os
import re
import socket
from pathlib import Path
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


KARMA_BASE = Path.home() / ".claude_karma"
SYNC_CONFIG_PATH = KARMA_BASE / "sync-config.json"


class ProjectConfig(BaseModel):
    """Configuration for a synced project."""

    model_config = ConfigDict(frozen=True)

    path: str = Field(..., description="Absolute path to project directory")
    encoded_name: str = Field(..., description="Claude-encoded project name")
    last_sync_cid: Optional[str] = Field(default=None, description="CID from last sync")
    last_sync_at: Optional[str] = Field(default=None, description="ISO timestamp of last sync")


class TeamMember(BaseModel):
    """A team member's IPNS identity."""

    model_config = ConfigDict(frozen=True)

    ipns_key: str = Field(..., description="IPNS key ID for resolving latest sync")

    @field_validator("ipns_key")
    @classmethod
    def validate_ipns_key(cls, v: str) -> str:
        if not v or len(v) > 128 or v.startswith("-"):
            raise ValueError("IPNS key must be non-empty, under 128 chars, and not start with dash")
        if not re.match(r"^[a-zA-Z0-9]+$", v):
            raise ValueError("IPNS key must be alphanumeric")
        return v


class SyncthingSettings(BaseModel):
    """Syncthing connection settings."""

    model_config = ConfigDict(frozen=True)

    api_url: str = Field(default="http://127.0.0.1:8384", description="Syncthing REST API URL")
    api_key: Optional[str] = Field(default=None, description="Syncthing API key")
    device_id: Optional[str] = Field(default=None, description="This device's Syncthing ID")


class TeamMemberSyncthing(BaseModel):
    """A team member identified by Syncthing device ID."""

    model_config = ConfigDict(frozen=True)

    syncthing_device_id: str = Field(..., description="Syncthing device ID")

    @field_validator("syncthing_device_id")
    @classmethod
    def validate_device_id(cls, v: str) -> str:
        if not v or len(v) > 128:
            raise ValueError("Device ID must be non-empty and under 128 chars")
        return v


class TeamConfig(BaseModel):
    """Configuration for a team with its own sync backend."""

    model_config = ConfigDict(frozen=True)

    backend: Literal["ipfs", "syncthing"] = Field(..., description="Sync backend for this team")
    projects: dict[str, ProjectConfig] = Field(default_factory=dict)
    ipfs_members: dict[str, TeamMember] = Field(default_factory=dict)
    syncthing_members: dict[str, TeamMemberSyncthing] = Field(default_factory=dict)
    owner_device_id: Optional[str] = Field(default=None, description="Owner's Syncthing device ID")
    owner_ipns_key: Optional[str] = Field(default=None, description="Owner's IPNS key")

    @property
    def members(self) -> dict:
        """Unified view of all members regardless of backend."""
        result = dict(self.ipfs_members)
        result.update(self.syncthing_members)
        return result


class SyncConfig(BaseModel):
    """Root sync configuration stored at ~/.claude_karma/sync-config.json."""

    model_config = ConfigDict(frozen=True)

    user_id: str = Field(..., description="User identity (e.g., 'alice')")
    machine_id: str = Field(
        default_factory=lambda: socket.gethostname(),
        description="Machine hostname for multi-device identification",
    )
    projects: dict[str, ProjectConfig] = Field(default_factory=dict)
    team: dict[str, TeamMember] = Field(default_factory=dict)
    ipfs_api: str = Field(default="http://127.0.0.1:5001", description="Kubo API endpoint")
    teams: dict[str, TeamConfig] = Field(default_factory=dict)
    syncthing: SyncthingSettings = Field(default_factory=SyncthingSettings)

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_\-]+$", v):
            raise ValueError("user_id must be alphanumeric, dash, or underscore")
        return v

    @staticmethod
    def load() -> Optional["SyncConfig"]:
        """Load config from disk. Returns None if not initialized."""
        if not SYNC_CONFIG_PATH.exists():
            return None
        try:
            data = json.loads(SYNC_CONFIG_PATH.read_text())
            return SyncConfig(**data)
        except (json.JSONDecodeError, ValueError) as e:
            raise RuntimeError(f"Corrupt config at {SYNC_CONFIG_PATH}: {e}") from e

    def save(self) -> None:
        """Persist config to disk."""
        SYNC_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        SYNC_CONFIG_PATH.write_text(
            json.dumps(self.model_dump(), indent=2) + "\n"
        )
        os.chmod(SYNC_CONFIG_PATH, 0o600)
