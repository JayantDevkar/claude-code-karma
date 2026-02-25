"""
Plan model for Claude Code plan markdown files.

Plans are stored at ~/.claude/plans/{slug}.md and represent project
planning documents created during Claude Code's "plan mode". Each plan
has a slug identifier (e.g., "abundant-dancing-newell") derived from
the filename.

Example plan structure:
    ~/.claude/plans/
    ├── abundant-dancing-newell.md
    ├── serene-wandering-pike.md
    └── calm-thinking-doe.md

Each plan file contains markdown content with metadata available through
file system timestamps.
"""

from __future__ import annotations

import logging
import platform
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


class Plan(BaseModel):
    """
    Represents a Claude Code plan markdown file from ~/.claude/plans/.

    Plans are project planning documents with a unique slug identifier.
    The model provides methods to extract metadata and content from the
    markdown files.

    Attributes:
        slug: Plan identifier (filename without .md extension)
        content: Full markdown content of the plan
        created: File creation timestamp
        modified: File modification timestamp
    """

    model_config = ConfigDict(frozen=True)

    slug: str = Field(..., description="Plan identifier (filename without .md)")
    content: str = Field(..., description="Full markdown content")
    created: datetime = Field(..., description="File creation time")
    modified: datetime = Field(..., description="Last modification time")

    @property
    def word_count(self) -> int:
        """
        Count words in plan content.

        Returns:
            Number of words in content (whitespace-separated)
        """
        return len(self.content.split())

    @property
    def size_bytes(self) -> int:
        """
        Calculate size of content in bytes.

        Returns:
            UTF-8 encoded size in bytes
        """
        return len(self.content.encode("utf-8"))

    def extract_title(self) -> Optional[str]:
        """
        Extract first h1 header from markdown content.

        Searches for lines starting with "# " and extracts the title text.
        Returns None if no h1 header is found.

        Returns:
            Title text without the "# " prefix, or None if not found

        Example:
            >>> plan.content = "# Fix File Activity\\n\\nSome content"
            >>> plan.extract_title()
            "Fix File Activity"
        """
        match = re.search(r"^#\s+(.+)$", self.content, re.MULTILINE)
        if match:
            return match.group(1).strip()
        return None

    @classmethod
    def from_path(cls, path: Path) -> Optional["Plan"]:
        """
        Load a plan from a markdown file path.

        Reads the file content and metadata to create a Plan instance.
        Handles platform-specific creation time retrieval (st_birthtime on
        macOS/BSD, falls back to st_mtime on Linux).

        Args:
            path: Path to the .md plan file

        Returns:
            Plan instance, or None if file doesn't exist or cannot be read

        Example:
            >>> plan = Plan.from_path(Path("~/.claude/plans/my-plan.md"))
            >>> if plan:
            ...     print(f"Plan: {plan.slug}, {plan.word_count} words")
        """
        if not path.exists() or not path.is_file():
            logger.debug(f"Plan file not found or not a file: {path}")
            return None

        try:
            stat = path.stat()
            content = path.read_text(encoding="utf-8")
            slug = path.stem  # filename without .md extension

            # Get creation time (platform-specific)
            # macOS/BSD: st_birthtime (true creation time)
            # Linux: st_ctime (inode change time, not creation time)
            # Windows: st_ctime (creation time)
            system = platform.system()
            if system == "Darwin" or system.startswith("BSD"):
                # macOS and BSD have st_birthtime
                created_timestamp = stat.st_birthtime
            elif system == "Windows":
                # Windows st_ctime is creation time
                created_timestamp = stat.st_ctime
            else:
                # Linux doesn't have reliable creation time
                # Fall back to modification time as best approximation
                created_timestamp = stat.st_mtime

            return cls(
                slug=slug,
                content=content,
                created=datetime.fromtimestamp(created_timestamp),
                modified=datetime.fromtimestamp(stat.st_mtime),
            )
        except (OSError, UnicodeDecodeError) as e:
            logger.warning(f"Failed to load plan from {path}: {e}")
            return None

    @classmethod
    def list_all(cls, plans_dir: Path) -> list["Plan"]:
        """
        List all plans from a directory, sorted by modified time descending.

        Loads all .md files in the directory and returns them as Plan instances,
        ordered with most recently modified first. Skips files that cannot be
        loaded (missing, corrupt, or permission errors).

        Args:
            plans_dir: Directory containing plan .md files (e.g., ~/.claude/plans)

        Returns:
            List of Plan instances, sorted by modified time (newest first)

        Example:
            >>> plans_dir = Path.home() / ".claude" / "plans"
            >>> plans = Plan.list_all(plans_dir)
            >>> for plan in plans:
            ...     print(f"{plan.slug}: modified {plan.modified}")
        """
        if not plans_dir.exists():
            logger.debug(f"Plans directory does not exist: {plans_dir}")
            return []

        plans = []
        for path in plans_dir.glob("*.md"):
            plan = cls.from_path(path)
            if plan:
                plans.append(plan)

        # Sort by modified time, newest first
        return sorted(plans, key=lambda p: p.modified, reverse=True)


def get_plans_dir() -> Path:
    """
    Get the ~/.claude/plans directory path.

    Returns:
        Path to the plans directory
    """
    return Path.home() / ".claude" / "plans"


def load_plan(slug: str) -> Optional[Plan]:
    """
    Load a specific plan by slug.

    Args:
        slug: Plan identifier (filename without .md)

    Returns:
        Plan instance, or None if not found

    Example:
        >>> plan = load_plan("abundant-dancing-newell")
        >>> if plan:
        ...     print(plan.extract_title())
    """
    plans_dir = get_plans_dir()
    plan_file = plans_dir / f"{slug}.md"
    return Plan.from_path(plan_file)


def load_all_plans() -> list[Plan]:
    """
    Load all plans from the ~/.claude/plans directory.

    Returns:
        List of Plan instances, sorted by modified time (newest first)

    Example:
        >>> plans = load_all_plans()
        >>> print(f"Found {len(plans)} plans")
    """
    plans_dir = get_plans_dir()
    return Plan.list_all(plans_dir)
