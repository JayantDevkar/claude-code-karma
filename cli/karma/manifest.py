"""Sync manifest model — describes what was synced and when."""

from datetime import datetime, timezone
from typing import Dict, Optional
from pydantic import BaseModel, ConfigDict, Field


class SessionEntry(BaseModel):
    """Metadata for a single synced session."""

    model_config = ConfigDict(frozen=True)

    uuid: str
    mtime: str = Field(..., description="ISO timestamp of session file modification time")
    size_bytes: int
    worktree_name: Optional[str] = Field(default=None, description="Worktree name if session is from a worktree")
    git_branch: Optional[str] = Field(default=None, description="Git branch the session was on")


class SkillDefinitionEntry(BaseModel):
    """Skill definition content from the exporting machine's filesystem."""

    model_config = ConfigDict(frozen=True)

    content: Optional[str] = Field(default=None, description="SKILL.md body text")
    description: Optional[str] = Field(
        default=None, description="Description parsed from YAML frontmatter"
    )
    category: str = Field(
        ..., description="Classification category (e.g., plugin_skill, custom_skill)"
    )
    base_directory: Optional[str] = Field(
        default=None, description="Parent directory of the skill file on the source machine"
    )


class SyncManifest(BaseModel):
    """Manifest describing a sync snapshot."""

    model_config = ConfigDict(frozen=True)

    version: int = Field(default=1)
    user_id: str
    machine_id: str
    member_tag: Optional[str] = Field(default=None, description="Sender identity: user_id.machine_tag")
    device_id: Optional[str] = Field(default=None, description="Syncthing device ID of the source machine")
    project_path: str = Field(..., description="Original project path on source machine")
    project_encoded: str = Field(..., description="Claude-encoded project directory name")
    synced_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )
    session_count: int
    sessions: list[SessionEntry]
    git_identity: Optional[str] = Field(
        default=None, description="Normalized git remote identity: owner/repo"
    )
    team_name: Optional[str] = Field(
        default=None, description="Team this sync belongs to"
    )
    proj_suffix: Optional[str] = Field(
        default=None,
        description="Agreed Syncthing folder ID suffix (e.g., 'acme-org-acme-app' for git, 'experiments' for non-git)",
    )
    skill_classifications: Dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Invocation name → category mapping from the exporting machine's filesystem. "
            "E.g. {'feature-dev:feature-dev': 'plugin_command', 'superpowers:brainstorming': 'plugin_skill'}. "
            "Used by the importing side to classify remote skills/commands correctly "
            "without relying on the local plugin cache."
        ),
    )
    skill_definitions: Dict[str, SkillDefinitionEntry] = Field(
        default_factory=dict,
        description=(
            "skill_name → definition entry with content read from the exporting machine's "
            "filesystem. Provides authoritative skill content so the importing machine "
            "does not need heuristic JSONL extraction."
        ),
    )
