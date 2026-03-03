"""Sync configuration management."""

import json
import socket
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


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

    @staticmethod
    def load() -> Optional["SyncConfig"]:
        """Load config from disk. Returns None if not initialized."""
        if not SYNC_CONFIG_PATH.exists():
            return None
        data = json.loads(SYNC_CONFIG_PATH.read_text())
        return SyncConfig(**data)

    def save(self) -> None:
        """Persist config to disk."""
        SYNC_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        SYNC_CONFIG_PATH.write_text(
            json.dumps(self.model_dump(), indent=2) + "\n"
        )
