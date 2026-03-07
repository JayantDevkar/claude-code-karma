"""Sync configuration management.

Identity and credentials only. Teams/members/projects live in SQLite.
"""

import json
import os
import re
import socket
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


KARMA_BASE = Path.home() / ".claude_karma"
SYNC_CONFIG_PATH = KARMA_BASE / "sync-config.json"


class SyncthingSettings(BaseModel):
    """Syncthing connection settings."""

    model_config = ConfigDict(frozen=True)

    api_url: str = Field(default="http://127.0.0.1:8384", description="Syncthing REST API URL")
    api_key: Optional[str] = Field(default=None, description="Syncthing API key")
    device_id: Optional[str] = Field(default=None, description="This device's Syncthing ID")


class SyncConfig(BaseModel):
    """Identity and credentials. Teams/members/projects live in SQLite."""

    model_config = ConfigDict(frozen=True)

    user_id: str = Field(..., description="User identity")
    machine_id: str = Field(
        default_factory=lambda: socket.gethostname(),
        description="Machine hostname",
    )
    syncthing: SyncthingSettings = Field(default_factory=SyncthingSettings)

    @field_validator("user_id")
    @classmethod
    def validate_user_id(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_\\-]+$", v):
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
        SYNC_CONFIG_PATH.write_text(json.dumps(self.model_dump(), indent=2) + "\n")
        os.chmod(SYNC_CONFIG_PATH, 0o600)
