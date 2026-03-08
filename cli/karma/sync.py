"""Sync utilities — path encoding, git identity detection, Claude project discovery."""

import re
import subprocess
from pathlib import Path
from typing import Optional


def encode_project_path(path: str) -> str:
    """Encode a project path the same way Claude Code does.

    Unix:    /Users/alice/repo  → -Users-alice-repo
    Windows: C:\\Users\\alice\\repo → -C-Users-alice-repo
    """
    p = path.replace("\\", "/")
    # Strip leading slash (Unix) or drive letter colon (Windows: C:/)
    if p.startswith("/"):
        p = p[1:]
    p = p.replace(":", "")
    return "-" + p.replace("/", "-")


def detect_git_identity(project_path: str) -> Optional[str]:
    """Detect git identity from origin remote URL, normalized to lowercase owner/repo.

    SSH:   git@github.com:Owner/Repo.git → owner/repo
    HTTPS: https://github.com/Owner/Repo.git → owner/repo
    Non-git / no origin → None
    """
    try:
        result = subprocess.run(
            ["git", "-C", project_path, "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        url = result.stdout.strip()
        if not url:
            return None

        # SSH: git@github.com:Owner/Repo.git
        ssh_match = re.match(r"^[\w.-]+@[\w.-]+:(.*?)(?:\.git)?$", url)
        if ssh_match:
            return ssh_match.group(1).lower()

        # HTTPS: https://github.com/Owner/Repo.git
        https_match = re.match(r"^https?://[^/]+/(.*?)(?:\.git)?$", url)
        if https_match:
            return https_match.group(1).lower()

        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return None


def find_claude_project_dir(project_path: str) -> Optional[Path]:
    """Find the Claude project directory for a given project path."""
    encoded = encode_project_path(project_path)
    claude_dir = Path.home() / ".claude" / "projects" / encoded
    if claude_dir.is_dir():
        return claude_dir
    return None
