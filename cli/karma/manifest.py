"""Sync manifest model — describes what was synced and when."""

from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class SessionEntry(BaseModel):
    """Metadata for a single synced session."""

    model_config = ConfigDict(frozen=True)

    uuid: str
    mtime: str = Field(..., description="ISO timestamp of session file modification time")
    size_bytes: int
    worktree_name: Optional[str] = Field(default=None, description="Worktree name if session is from a worktree")
    git_branch: Optional[str] = Field(default=None, description="Git branch the session was on")


class SyncManifest(BaseModel):
    """Manifest describing a sync snapshot."""

    model_config = ConfigDict(frozen=True)

    version: int = Field(default=1)
    user_id: str
    machine_id: str
    project_path: str = Field(..., description="Original project path on source machine")
    project_encoded: str = Field(..., description="Claude-encoded project directory name")
    synced_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )
    session_count: int
    sessions: list[SessionEntry]
    previous_cid: Optional[str] = Field(
        default=None, description="CID of the previous sync for chain history"
    )
    git_identity: Optional[str] = Field(
        default=None, description="Normalized git remote identity: owner/repo"
    )
    sync_backend: Optional[str] = Field(
        default=None, description="Sync backend used: 'ipfs', 'syncthing', or None"
    )
    team_name: Optional[str] = Field(
        default=None, description="Team this sync belongs to"
    )
    proj_suffix: Optional[str] = Field(
        default=None,
        description="Agreed Syncthing folder ID suffix (e.g., 'acme-org-acme-app' for git, 'experiments' for non-git)",
    )
