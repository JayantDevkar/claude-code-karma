"""
Tool result model for Claude Code session tool outputs.

Large tool outputs are stored in {session-uuid}/tool-results/toolu_xxx.txt
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

# Pattern for valid tool use IDs
TOOL_USE_ID_PATTERN = re.compile(r"^toolu_[A-Za-z0-9_-]+$")


class ToolResult(BaseModel):
    """
    A stored tool result from a session.

    Tool results exceeding a size threshold are written to disk
    rather than stored inline in the JSONL.

    File location: {session-uuid}/tool-results/toolu_{id}.txt

    Attributes:
        tool_use_id: The tool use ID (toolu_xxx)
        path: Path to the result file
    """

    model_config = ConfigDict(frozen=True)

    tool_use_id: str = Field(..., description="Tool use ID (e.g., toolu_xxx)")
    path: Path = Field(..., description="Path to the tool result file")

    @field_validator("tool_use_id")
    @classmethod
    def validate_tool_use_id(cls, v: str) -> str:
        """Validate tool_use_id matches toolu_xxx format."""
        if not TOOL_USE_ID_PATTERN.match(v):
            raise ValueError(f"Invalid tool_use_id format: {v}. Expected 'toolu_xxx'")
        return v

    @field_validator("path")
    @classmethod
    def validate_path(cls, v: Path) -> Path:
        """Validate path is in tool-results directory with .txt extension."""
        if "tool-results" not in v.parts:
            raise ValueError(f"Tool result path must be in tool-results/ directory: {v}")
        if v.suffix != ".txt":
            raise ValueError(f"Tool result file must have .txt extension: {v}")
        return v

    @classmethod
    def from_path(cls, path: Path) -> "ToolResult":
        """
        Create a ToolResult from a file path.

        Extracts the tool_use_id from the filename.

        Args:
            path: Path to tool result file (e.g., toolu_01ABC.txt)

        Returns:
            ToolResult instance

        Raises:
            ValueError: If path format is invalid
        """
        # Extract tool_use_id from filename (remove .txt extension)
        tool_use_id = path.stem
        return cls(tool_use_id=tool_use_id, path=path)

    def read_content(self) -> str:
        """
        Read the tool result content from disk.

        Returns:
            Tool result content as string

        Raises:
            FileNotFoundError: If the result file doesn't exist
        """
        return self.path.read_text(encoding="utf-8")

    def read_content_safe(self) -> Optional[str]:
        """
        Read tool result content, returning None if file doesn't exist.

        Returns:
            Tool result content or None if file not found
        """
        try:
            return self.read_content()
        except FileNotFoundError:
            return None

    @property
    def exists(self) -> bool:
        """Check if the tool result file exists."""
        return self.path.exists()

    @property
    def size_bytes(self) -> int:
        """Get the size of the tool result file in bytes."""
        if not self.exists:
            return 0
        return self.path.stat().st_size
