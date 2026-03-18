"""
Project model for Claude Code project directories.

Projects are stored in ~/.claude/projects/ with path-encoded directory names.
"""

from __future__ import annotations

import re
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, Union

from cachetools import TTLCache
from pydantic import BaseModel, ConfigDict, Field

from config import settings

# Thread-safe TTL cache for JSONL file counts (Phase 2 fix)
# - maxsize=1000 prevents unbounded memory growth
# - ttl=5.0 ensures freshness checks are accurate
_jsonl_count_cache: TTLCache = TTLCache(maxsize=1000, ttl=5.0)


def get_cached_jsonl_count(project_dir: Path) -> int:
    """
    Get session JSONL file count with thread-safe 5-second TTL cache.

    Counts only session files (UUID.jsonl), excluding agent files (agent-*.jsonl).
    This matches what sessions-index.json tracks, ensuring accurate freshness checks.

    This avoids expensive glob() calls on every request when checking
    if the session index is fresh. Uses cachetools.TTLCache for:
    - Thread-safe operations in concurrent FastAPI requests
    - Automatic expiration and cleanup of old entries
    - Bounded memory usage (max 1000 entries)

    Args:
        project_dir: Path to the project directory

    Returns:
        Number of session .jsonl files (excludes agent-*.jsonl)
    """
    key = str(project_dir)

    if key in _jsonl_count_cache:
        return _jsonl_count_cache[key]

    # Count only session files, not agent files
    # Sessions are UUID.jsonl, agents are agent-*.jsonl
    count = sum(1 for f in project_dir.glob("*.jsonl") if not f.name.startswith("agent-"))
    _jsonl_count_cache[key] = count
    return count


if TYPE_CHECKING:
    from datetime import datetime

    from .agent import Agent
    from .session import Session
    from .session_index import SessionIndex, SessionIndexEntry

PathLike = Union[str, Path]


def _is_absolute_path(path: str) -> bool:
    """Check if a path is absolute, recognizing both Unix and Windows formats.

    Unlike Path.is_absolute(), this works cross-platform: a Windows path like
    'C:\\Users\\test' is recognized as absolute even when running on macOS/Linux.
    This is important for reading session data synced from other operating systems.
    """
    # Unix absolute path
    if path.startswith("/"):
        return True
    # Windows absolute path: drive letter followed by colon and separator
    if re.match(r"^[A-Za-z]:[/\\]", path):
        return True
    # Windows UNC path
    if path.startswith("\\\\") or path.startswith("//"):
        return True
    return False


class Project(BaseModel):
    """
    Represents a Claude Code project directory under ~/.claude/projects/.

    Claude encodes an absolute project path by replacing '/' with '-':
      /Users/me/repo -> -Users-me-repo

    Attributes:
        path: Original absolute project path (e.g., /Users/me/repo)
        encoded_name: Encoded directory name (e.g., -Users-me-repo)
        claude_projects_dir: Base ~/.claude/projects directory
    """

    model_config = ConfigDict(frozen=True, ignored_types=(cached_property,))

    path: str = Field(..., description="Original absolute project path (e.g., /Users/me/repo)")
    encoded_name: str = Field(..., description="Encoded directory name (e.g., -Users-me-repo)")
    claude_projects_dir: Path = Field(
        default_factory=lambda: settings.projects_dir,
        description="Base ~/.claude/projects directory",
    )

    @staticmethod
    def encode_path(path: PathLike) -> str:
        """
        Encode a project path to Claude's directory name format.

        Unix:    /Users/me/repo  -> -Users-me-repo   (leading / -> leading -)
        Windows: C:\\Code\\Tools -> C--Code-Tools     (colon -> dash, backslash -> dash)

        Args:
            path: Absolute project path

        Returns:
            Encoded directory name (e.g., -Users-me-repo or C--Code-Tools)
        """
        p = str(path)
        # Normalise Windows backslashes
        p = p.replace("\\", "/")
        if p.startswith("/"):
            # Unix absolute path: strip leading slash, prepend dash
            p = p[1:]
            return "-" + p.replace("/", "-")
        else:
            # Windows absolute path like C:/Code/Tools
            # Claude Code encodes colon and slash both as dash -> C--Code-Tools
            return p.replace(":", "-").replace("/", "-")

    @staticmethod
    def decode_path(encoded: str) -> str:
        """
        Decode a Claude directory name back to original path.

        Unix:    -Users-me-repo  -> /Users/me/repo
        Windows: C--Code-Tools   -> C:/Code/Tools

        Note: This is lossy if the original path contained '-' characters.
        Use _extract_real_path_from_sessions() for accurate path recovery.

        Args:
            encoded: Encoded directory name

        Returns:
            Decoded absolute path (may be incorrect if original had dashes)
        """
        if encoded.startswith("-"):
            # Unix encoded path: -Users-me-repo -> /Users/me/repo
            return "/" + encoded[1:].replace("-", "/")

        # Windows encoded path: C--Code-Tools -> C:/Code/Tools
        # Pattern: single drive letter followed by --
        win_match = re.match(r"^([A-Za-z])--(.*)", encoded)
        if win_match:
            drive = win_match.group(1).upper()
            rest = win_match.group(2).replace("-", "/")
            return f"{drive}:/{rest}"

        # Fallback: treat as Unix-style without leading slash
        return "/" + encoded.replace("-", "/")

    @staticmethod
    def _extract_real_path_from_sessions(project_dir: Path) -> Optional[str]:
        """
        Extract the real project path from session files.

        Reads the first few lines of the first session file to find the 'cwd'
        field which contains the actual project path.

        Args:
            project_dir: Path to the project's Claude data directory

        Returns:
            Real project path or None if not found
        """
        import json

        if not project_dir.exists():
            return None

        # Find the first session file (not agent-*.jsonl)
        session_files = sorted(
            [p for p in project_dir.glob("*.jsonl") if not p.name.startswith("agent-")]
        )
        if not session_files:
            return None

        # Try multiple session files (some may be empty or lack cwd)
        for session_file in session_files[:5]:  # Try up to 5 session files
            try:
                with open(session_file, "r", encoding="utf-8") as f:
                    for i, line in enumerate(f):
                        if i > 50:  # Check first 50 lines per file
                            break
                        try:
                            data = json.loads(line.strip())
                            cwd = data.get("cwd")
                            if cwd and _is_absolute_path(cwd):
                                # Normalize Windows backslashes to forward slashes
                                return cwd.replace("\\", "/")
                        except json.JSONDecodeError:
                            continue
            except (OSError, PermissionError, UnicodeDecodeError):
                continue

        return None

    @classmethod
    def from_path(
        cls, path: PathLike, *, claude_projects_dir: Optional[PathLike] = None
    ) -> "Project":
        """
        Create a Project from an absolute project path.

        Args:
            path: Absolute path to the project directory
            claude_projects_dir: Optional override for ~/.claude/projects

        Returns:
            Project instance

        Raises:
            ValueError: If path is not absolute
        """
        p = Path(path)
        if not p.is_absolute():
            raise ValueError(f"Project path must be absolute, got: {path}")

        base = (
            Path(claude_projects_dir) if claude_projects_dir is not None else settings.projects_dir
        )
        p_str = str(path)
        return cls(path=p_str, encoded_name=cls.encode_path(p_str), claude_projects_dir=base)

    @classmethod
    def from_encoded_name(
        cls,
        encoded_name: str,
        *,
        claude_projects_dir: Optional[PathLike] = None,
        skip_path_recovery: bool = False,
    ) -> "Project":
        """
        Create a Project from an encoded directory name.

        Attempts to recover the real project path from session data.
        Falls back to lossy decode_path if no sessions exist.

        Args:
            encoded_name: Encoded directory name (e.g., -Users-me-repo)
            claude_projects_dir: Optional override for ~/.claude/projects
            skip_path_recovery: If True, skip reading session files and use
                lossy decode_path directly. Useful for list operations where
                performance matters more than path accuracy.

        Returns:
            Project instance
        """
        base = (
            Path(claude_projects_dir) if claude_projects_dir is not None else settings.projects_dir
        )
        project_dir = base / encoded_name

        if skip_path_recovery:
            # Fast path: use lossy decode without reading session files
            real_path = cls.decode_path(encoded_name)
        else:
            # Try to extract real path from session cwd field
            real_path = cls._extract_real_path_from_sessions(project_dir)

            # Validate extracted path matches encoded name (catch corrupted sessions)
            if real_path is not None and cls.encode_path(real_path) != encoded_name:
                real_path = None

            # Fall back to lossy decode if no valid path found
            if real_path is None:
                real_path = cls.decode_path(encoded_name)

        return cls(path=real_path, encoded_name=encoded_name, claude_projects_dir=base)

    @property
    def project_dir(self) -> Path:
        """Path to the project's Claude data directory."""
        return self.claude_projects_dir / self.encoded_name

    @property
    def exists(self) -> bool:
        """Check if the project directory exists."""
        return self.project_dir.exists()

    @property
    def is_git_repository(self) -> bool:
        """Check if the project path is a git repository.

        Uses .exists() to handle both normal repos (.git is directory)
        and worktrees/submodules (.git is a file).

        Returns:
            True if .git exists at the project path, False otherwise.
        """
        try:
            git_path = Path(self.path) / ".git"
            return git_path.exists()
        except (OSError, PermissionError):
            return False

    @cached_property
    def git_root_path(self) -> Optional[str]:
        """Git repository root path, or None if not in a git repo.

        For submodules, returns the parent (superproject) repository root
        to enable proper grouping of submodules under their parent repos.
        """
        from utils import resolve_git_root

        return resolve_git_root(self.path)

    @property
    def is_nested_project(self) -> bool:
        """True if project is inside a git repo but not at the root.

        A project is nested if:
        - git_root_path is not None (is in a git repo)
        - project path != git_root_path (not at the git root)

        Returns:
            True if the project is nested within a git repository,
            False if at the git root or not in a git repo.
        """
        git_root = self.git_root_path
        if git_root is None:
            return False
        # Normalize paths for comparison (resolve symlinks, trailing slashes)
        project_path = Path(self.path).resolve()
        root_path = Path(git_root).resolve()
        return project_path != root_path

    @cached_property
    def slug(self) -> str:
        """URL-friendly project slug: lowercased name + 4-char hash."""
        from utils import compute_project_slug

        return compute_project_slug(self.encoded_name, self.path)

    @cached_property
    def display_name(self) -> str:
        """Human-readable project name (last path component)."""
        return Path(self.path).name

    @property
    def claude_base_dir(self) -> Path:
        """Get the base ~/.claude directory."""
        return self.claude_projects_dir.parent

    # =========================================================================
    # Session Index (Phase 1 optimization)
    # =========================================================================

    @property
    def session_index_path(self) -> Path:
        """Path to sessions-index.json for this project."""
        return self.project_dir / "sessions-index.json"

    def load_sessions_index(self) -> Optional["SessionIndex"]:
        """
        Load the sessions index if available.

        Returns pre-computed session metadata from sessions-index.json,
        avoiding the need to parse individual JSONL files.

        Returns:
            SessionIndex or None if index doesn't exist
        """
        from .session_index import SessionIndex

        return SessionIndex.load(self.session_index_path)

    def list_session_index_entries(self) -> List["SessionIndexEntry"]:
        """
        List session metadata from index, sorted by modified time (newest first).

        Falls back to empty list if index unavailable.

        Returns:
            List of SessionIndexEntry sorted by modified descending
        """
        index = self.load_sessions_index()
        if index is None:
            return []
        return index.get_entries_sorted_by_modified(reverse=True)

    # =========================================================================
    # Session listing
    # =========================================================================

    def _get_jsonl_paths(self) -> tuple[List[Path], List[Path]]:
        """
        Single directory traversal returning (session_paths, agent_paths).

        This is an optimization to avoid multiple glob() calls on the same directory.
        Sessions are sorted by name, agents are sorted by name.

        Returns:
            Tuple of (session_paths, agent_paths)
        """
        if not self.project_dir.exists():
            return [], []

        sessions: List[Path] = []
        agents: List[Path] = []

        for p in self.project_dir.glob("*.jsonl"):
            if not p.is_file():
                continue
            if p.name.startswith("agent-"):
                agents.append(p)
            else:
                sessions.append(p)

        return sorted(sessions, key=lambda p: p.name), sorted(agents, key=lambda p: p.name)

    def list_session_paths(self) -> List[Path]:
        """
        List main session JSONL file paths.

        Main sessions are UUID-named .jsonl files (excludes agent-*.jsonl).

        Returns:
            Sorted list of session file paths
        """
        return self._get_jsonl_paths()[0]

    def list_sessions(self) -> List["Session"]:
        """
        List all main sessions for this project.

        Returns:
            List of Session instances
        """
        from .session import Session

        return [
            Session.from_path(p, claude_base_dir=self.claude_base_dir)
            for p in self.list_session_paths()
        ]

    def get_session(self, uuid: str) -> Optional["Session"]:
        """
        Get a specific session by UUID.

        Args:
            uuid: Session UUID

        Returns:
            Session instance or None if not found
        """
        from .session import Session

        jsonl_path = self.project_dir / f"{uuid}.jsonl"
        if jsonl_path.exists():
            return Session.from_path(jsonl_path, claude_base_dir=self.claude_base_dir)
        return None

    # =========================================================================
    # Agent listing
    # =========================================================================

    def list_agent_paths(self) -> List[Path]:
        """
        List standalone agent JSONL file paths (agent-*.jsonl at project root).

        Returns:
            Sorted list of agent file paths
        """
        return self._get_jsonl_paths()[1]

    def list_agents(self) -> List["Agent"]:
        """
        List all standalone agents for this project.

        Returns:
            List of Agent instances
        """
        from .agent import Agent

        return [Agent.from_path(p) for p in self.list_agent_paths()]

    def get_agent(self, agent_id: str) -> Optional["Agent"]:
        """
        Get a specific standalone agent by ID.

        Args:
            agent_id: Agent short hex ID

        Returns:
            Agent instance or None if not found
        """
        from .agent import Agent

        jsonl_path = self.project_dir / f"agent-{agent_id}.jsonl"
        if jsonl_path.exists():
            return Agent.from_path(jsonl_path)
        return None

    # =========================================================================
    # Aggregate queries
    # =========================================================================

    @property
    def session_count(self) -> int:
        """Count of main sessions."""
        return len(self.list_session_paths())

    @property
    def agent_count(self) -> int:
        """Count of standalone agents."""
        return len(self.list_agent_paths())

    def get_all_subagents(self) -> List["Agent"]:
        """
        Get all subagents across all sessions.

        Returns:
            Flattened list of all subagents
        """
        subagents: List["Agent"] = []
        for session in self.list_sessions():
            subagents.extend(session.list_subagents())
        return subagents

    # =========================================================================
    # Phase 4: Early date filtering
    # =========================================================================

    def list_sessions_filtered(
        self,
        start_date: Optional["datetime"] = None,
        end_date: Optional["datetime"] = None,
        limit: Optional[int] = None,
        sort_by_mtime: bool = True,
    ) -> List["Session"]:
        """
        List sessions with early filtering by file modification time.

        Filters by file mtime before parsing JSONL, avoiding unnecessary I/O.
        This is a Phase 4 optimization for date-filtered queries.

        Args:
            start_date: Filter sessions with start_time >= start_date
            end_date: Filter sessions with start_time <= end_date
            limit: Maximum number of sessions to return
            sort_by_mtime: Sort by modification time (most recent first)

        Returns:
            List of Session instances matching criteria
        """
        from datetime import datetime, timezone

        from .session import Session

        if not self.project_dir.exists():
            return []

        # Get all session JSONL files
        jsonl_files = [
            p
            for p in self.project_dir.glob("*.jsonl")
            if p.is_file() and not p.name.startswith("agent-")
        ]

        # Pre-filter by file modification time if date range specified
        if start_date or end_date:
            filtered_files = []
            for f in jsonl_files:
                try:
                    mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)

                    # File mtime >= session end_time, so use as upper bound proxy
                    # A session modified before start_date can't have activity after it
                    if start_date and mtime < start_date:
                        continue

                    filtered_files.append(f)
                except (OSError, PermissionError):
                    continue
            jsonl_files = filtered_files

        # Sort by modification time (most recent first) for efficiency
        if sort_by_mtime:
            try:
                jsonl_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            except (OSError, PermissionError):
                pass

        # Apply limit after pre-filtering but before loading sessions
        # Note: This is an optimization - actual filtering happens after load
        if limit:
            # Get more than needed to account for post-load filtering
            jsonl_files = jsonl_files[: limit * 2] if limit * 2 < len(jsonl_files) else jsonl_files

        # Load and filter sessions
        sessions = []
        for jsonl_path in jsonl_files:
            try:
                session = Session.from_path(jsonl_path, claude_base_dir=self.claude_base_dir)

                # Precise filtering after loading (using cached start_time)
                if start_date and session.start_time and session.start_time < start_date:
                    continue
                if end_date and session.start_time and session.start_time > end_date:
                    continue

                sessions.append(session)

                # Early exit if we have enough sessions
                if limit and len(sessions) >= limit:
                    break
            except Exception:
                continue

        return sessions

    def get_latest_session_time_fast(self) -> Optional["datetime"]:
        """
        Get latest session time using only file modification times.

        Avoids parsing JSONL entirely - uses file mtime as proxy.
        This is a Phase 4 optimization for project listing.

        Returns:
            Datetime of the most recently modified session file, or None
        """
        from datetime import datetime, timezone

        if not self.project_dir.exists():
            return None

        jsonl_files = [
            p
            for p in self.project_dir.glob("*.jsonl")
            if p.is_file() and not p.name.startswith("agent-")
        ]

        if not jsonl_files:
            return None

        try:
            # Use file mtime as proxy for session activity time
            latest_file = max(jsonl_files, key=lambda f: f.stat().st_mtime)
            mtime = datetime.fromtimestamp(latest_file.stat().st_mtime, tz=timezone.utc)
            return mtime
        except (OSError, PermissionError, ValueError):
            return None
