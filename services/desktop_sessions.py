"""
Desktop session detection and worktree merging service.

Claude Desktop creates git worktrees with random names for each "Claude Code"
session, causing the same project to appear as multiple phantom entries.
This service detects worktree projects and maps them back to real projects.

Two detection strategies:
- Strategy A: Worktree filesystem scan (fallback, cross-platform)
- Strategy B: Desktop metadata ingestion (primary, macOS)
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Worktree base directory
WORKTREE_BASE = Path.home() / ".claude-worktrees"

# Desktop metadata location (macOS)
DESKTOP_SESSIONS_DIR = (
    Path.home() / "Library" / "Application Support" / "Claude" / "claude-code-sessions"
)

# Cache for desktop metadata: (timestamp, data)
# Note: in-memory cache assumes single-process uvicorn (no workers)
_desktop_cache: tuple[float, dict[str, dict]] = (0.0, {})
_DESKTOP_CACHE_TTL = 60  # 60 seconds


# =============================================================================
# Strategy A: Worktree Path Detection (Fallback)
# =============================================================================


def is_worktree_project(encoded_name: str) -> bool:
    """
    Check if an encoded project dir is a worktree.

    Works on the ENCODED name directly. Checks for '-claude-worktrees-'
    which appears in both encoding variants:
    - Our encode_path: '-.claude-worktrees-' (dots preserved)
    - Claude Code's actual encoding: '--claude-worktrees-' (dots -> dashes)
    """
    return "-claude-worktrees-" in encoded_name


def extract_worktree_info(encoded_name: str) -> Optional[dict]:
    """
    Extract project_name and worktree_name by scanning the worktree base dir.

    Since decode_path is lossy (all dashes become slashes), we can't parse
    the encoded name. Instead, we scan ~/.claude-worktrees/ and find the
    directory whose encode_path matches.

    Returns:
        Dict with 'project_name' and 'worktree_name', or None.
    """
    if not is_worktree_project(encoded_name):
        return None

    if not WORKTREE_BASE.exists():
        return None

    from models.project import Project

    for project_dir in WORKTREE_BASE.iterdir():
        if not project_dir.is_dir():
            continue
        for worktree_dir in project_dir.iterdir():
            if not worktree_dir.is_dir():
                continue
            # Try standard encode_path (dots preserved)
            expected = Project.encode_path(str(worktree_dir))
            if expected == encoded_name:
                return {
                    "project_name": project_dir.name,
                    "worktree_name": worktree_dir.name,
                }
            # Try with dots replaced by dashes (Claude Code's actual encoding)
            expected_dots = expected.replace(".", "-")
            if expected_dots == encoded_name:
                return {
                    "project_name": project_dir.name,
                    "worktree_name": worktree_dir.name,
                }
    return None


# =============================================================================
# Strategy B: Desktop Metadata Ingestion (Primary, macOS)
# =============================================================================


def _load_desktop_metadata_impl() -> dict[str, dict]:
    """
    Parse all Desktop session JSON files.

    Returns:
        {cliSessionId -> {originCwd, worktreeName, title, model, isArchived, cwd}}
    """
    if not DESKTOP_SESSIONS_DIR.exists():
        return {}

    metadata: dict[str, dict] = {}

    try:
        # Iterate account UUID directories
        for account_dir in DESKTOP_SESSIONS_DIR.iterdir():
            if not account_dir.is_dir():
                continue
            # Iterate project UUID directories
            for project_dir in account_dir.iterdir():
                if not project_dir.is_dir():
                    continue
                # Read session JSON files
                for session_file in project_dir.glob("local_*.json"):
                    try:
                        data = json.loads(session_file.read_text(encoding="utf-8"))
                        cli_session_id = data.get("cliSessionId")
                        if not cli_session_id:
                            continue
                        metadata[cli_session_id] = {
                            "originCwd": data.get("originCwd"),
                            "worktreeName": data.get("worktreeName"),
                            "title": data.get("title"),
                            "model": data.get("model"),
                            "isArchived": data.get("isArchived", False),
                            "cwd": data.get("cwd"),
                        }
                    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                        continue
    except OSError:
        logger.debug("Could not read Desktop sessions directory")

    return metadata


def load_desktop_metadata() -> dict[str, dict]:
    """
    Load Desktop metadata with TTL cache.

    Returns:
        {cliSessionId -> {originCwd, worktreeName, title, model, isArchived}}
    """
    global _desktop_cache
    now = time.time()
    cached_time, cached_data = _desktop_cache

    if cached_data and (now - cached_time) < _DESKTOP_CACHE_TTL:
        return cached_data

    result = _load_desktop_metadata_impl()
    _desktop_cache = (now, result)
    return result


# =============================================================================
# Mapping Functions
# =============================================================================


def get_real_project_encoded_name(
    worktree_encoded_name: str, session_uuids: list[str]
) -> Optional[str]:
    """
    Given a worktree project's encoded name, find the real project's encoded_name.

    Strategy:
    1. Try Desktop metadata: look up session UUIDs -> originCwd -> encode_path
    2. Fallback: scan worktree base dir, extract project_name, find matching project

    Returns:
        The real project's encoded_name, or None if not resolvable.
    """
    from config import settings
    from models.project import Project

    # Strategy B (primary): Desktop metadata lookup
    desktop_meta = load_desktop_metadata()
    for uuid in session_uuids:
        if uuid in desktop_meta:
            origin_cwd = desktop_meta[uuid].get("originCwd")
            if origin_cwd:
                real_encoded = Project.encode_path(origin_cwd)
                # Verify the real project dir exists
                real_dir = settings.projects_dir / real_encoded
                if real_dir.exists():
                    return real_encoded

    # Strategy A (fallback): filesystem scan for project name
    wt_info = extract_worktree_info(worktree_encoded_name)
    if wt_info:
        project_name = wt_info["project_name"]
        # Scan existing project dirs for one whose path ends with the project name
        matches: list[str] = []
        try:
            for encoded_dir in settings.projects_dir.iterdir():
                if not encoded_dir.is_dir() or not encoded_dir.name.startswith("-"):
                    continue
                # Skip other worktree dirs
                if is_worktree_project(encoded_dir.name):
                    continue
                # Check if encoded name ends with the project name
                # e.g., "-Users-jayantdevkar-Documents-GitHub-claude-karma"
                # ends with "-claude-karma" for project_name="claude-karma"
                if encoded_dir.name.endswith("-" + project_name):
                    matches.append(encoded_dir.name)
        except OSError:
            pass

        if matches:
            if len(matches) > 1:
                logger.warning(
                    "Ambiguous worktree suffix match for '%s': %s (using first)",
                    project_name,
                    matches,
                )
            return matches[0]

    return None


def get_session_source(session_uuid: str) -> Optional[str]:
    """
    Return 'desktop' if session UUID exists in Desktop metadata, else None.

    This is used to tag individual sessions with their origin.
    """
    desktop_meta = load_desktop_metadata()
    if session_uuid in desktop_meta:
        return "desktop"
    return None
