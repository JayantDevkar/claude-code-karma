"""
OS-specific path detection for Cursor IDE storage.

Cursor inherits VS Code's Electron storage layout, with one Cursor-specific
addition (`~/.cursor/`) used for per-project artifacts (plans, MCP configs,
agent transcripts) on all three OSes.
"""

import os
import platform
from pathlib import Path


def cursor_global_db_path() -> Path:
    """Path to Cursor's master state.vscdb (chat store, ~2 GB on heavy use)."""
    home = Path.home()
    system = platform.system()
    if system == "Darwin":
        return (
            home / "Library/Application Support/Cursor/User/globalStorage/state.vscdb"
        )
    if system == "Linux":
        return home / ".config/Cursor/User/globalStorage/state.vscdb"
    if system == "Windows":
        appdata = os.environ.get("APPDATA")
        if not appdata:
            appdata = str(home / "AppData" / "Roaming")
        return Path(appdata) / "Cursor/User/globalStorage/state.vscdb"
    raise NotImplementedError(f"Unsupported OS: {system}")


def cursor_workspace_storage_dir() -> Path:
    """Directory holding per-workspace state.vscdb files keyed by 16-hex hash."""
    return cursor_global_db_path().parent.parent / "workspaceStorage"


def cursor_user_dir() -> Path:
    """~/.cursor — Cursor's per-user CLI-style state (same on all OSes)."""
    return Path.home() / ".cursor"


def cursor_plans_dir() -> Path:
    """~/.cursor/plans — flat directory of `<slug>_<8hex>.plan.md` files."""
    return cursor_user_dir() / "plans"


def cursor_skills_dir() -> Path:
    """User-defined Cursor skills (may not exist on every machine)."""
    return cursor_user_dir() / "skills"


def cursor_builtin_skills_dir() -> Path:
    """Bundled Cursor skills shipped with the IDE."""
    return cursor_user_dir() / "skills-cursor"


def cursor_projects_dir() -> Path:
    """~/.cursor/projects/<encoded>/ — per-project MCP + agent-transcripts."""
    return cursor_user_dir() / "projects"


def detect_cursor_install() -> bool:
    """True if Cursor's master state.vscdb exists at the expected path."""
    try:
        return cursor_global_db_path().is_file()
    except (KeyError, NotImplementedError):
        return False
