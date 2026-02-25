"""
Session index model for fast metadata loading from sessions-index.json.

Claude Code maintains a pre-computed index of session metadata at:
    ~/.claude/projects/{encoded-path}/sessions-index.json

This avoids parsing individual JSONL files for list views.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class SessionIndexEntry(BaseModel):
    """
    A single entry in sessions-index.json.

    Contains pre-computed metadata that would otherwise require
    parsing the full JSONL file.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True)

    session_id: str = Field(..., alias="sessionId")
    full_path: str = Field(..., alias="fullPath")
    file_mtime: int = Field(..., alias="fileMtime")
    first_prompt: Optional[str] = Field(None, alias="firstPrompt")
    summary: Optional[str] = Field(None, description="Claude's auto-generated session summary")
    message_count: int = Field(0, alias="messageCount")
    created: datetime
    modified: datetime
    git_branch: Optional[str] = Field(None, alias="gitBranch")
    project_path: Optional[str] = Field(None, alias="projectPath")
    is_sidechain: bool = Field(False, alias="isSidechain")

    @property
    def uuid(self) -> str:
        """Alias for session_id to match Session interface."""
        return self.session_id

    @property
    def start_time(self) -> datetime:
        """Alias for created to match Session interface."""
        return self.created

    @property
    def end_time(self) -> datetime:
        """Alias for modified to match Session interface."""
        return self.modified

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate duration from created to modified."""
        if self.created and self.modified:
            return (self.modified - self.created).total_seconds()
        return None

    @property
    def initial_prompt(self) -> Optional[str]:
        """Alias for first_prompt, truncated for display."""
        if self.first_prompt:
            return self.first_prompt[:500]
        return None


class SessionIndex(BaseModel):
    """
    The full sessions-index.json file structure.

    Contains version info and list of session entries.
    """

    model_config = ConfigDict(frozen=True)

    version: int = Field(1, description="Index format version")
    entries: List[SessionIndexEntry] = Field(default_factory=list)

    @classmethod
    def load(cls, index_path: Path) -> Optional["SessionIndex"]:
        """
        Load sessions index from file.

        Args:
            index_path: Path to sessions-index.json

        Returns:
            SessionIndex or None if file doesn't exist or is invalid
        """
        if not index_path.exists():
            return None

        try:
            with open(index_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return cls.model_validate(data)
        except (json.JSONDecodeError, OSError, ValueError):
            return None

    def get_entry(self, session_id: str) -> Optional[SessionIndexEntry]:
        """Get entry by session ID."""
        for entry in self.entries:
            if entry.session_id == session_id:
                return entry
        return None

    def get_entries_sorted_by_modified(self, reverse: bool = True) -> List[SessionIndexEntry]:
        """Get entries sorted by modified time."""
        return sorted(self.entries, key=lambda e: e.modified, reverse=reverse)
