#!/usr/bin/env python3
"""
Project identity sidecar writer for Claude Code Karma.

Fires on SessionStart. Reads the session's cwd, asks git for the
`remote.origin.url` and the repo toplevel, and writes
`karma-project.json` next to the session transcript
(~/.claude/projects/<encoded>/). After the user syncs ~/.claude to
another machine, Karma there can match the project by git identity
instead of the machine-specific encoded path.

Sidecar shape:

    {
      "git_identity": "owner/repo",
      "subdir": "api",
      "project_path": "/Users/me/repo/api",
      "written_by": "hook"
    }

Silent on every failure — this hook NEVER blocks SessionStart.
Stdlib only; Python 3.9+.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

SIDECAR_NAME = "karma-project.json"
TMP_NAME = ".karma-project.json.tmp"

# Inlined from api/services/git_identity.py (hooks can't import api).
_SCP_RE = re.compile(r"^[^@]+@[^:]+:(?P<path>.+)$")
_URL_RE = re.compile(r"^[a-z]+://(?:[^@/]+@)?[^/]+/(?P<path>.+)$", re.IGNORECASE)


def normalize_git_url(url: Optional[str]) -> Optional[str]:
    """Parse a git remote URL into canonical `owner/repo` (lowercase)."""
    if not url:
        return None
    url = url.strip()
    if not url:
        return None

    # A scheme URL with a port (ssh://git@host:2222/...) would also match the scp regex
    m = _URL_RE.match(url) if "://" in url else _SCP_RE.match(url)
    if m is None:
        return None

    path = m.group("path").strip("/")
    if path.lower().endswith(".git"):
        path = path[:-4]

    parts = [p for p in path.split("/") if p]
    # Azure DevOps: https://dev.azure.com/org/project/_git/repo
    if len(parts) >= 3 and parts[-2] == "_git":
        del parts[-2]
    if len(parts) < 2:
        return None

    owner, repo = parts[-2], parts[-1]
    return f"{owner}/{repo}".lower()


def _git(cwd: str, *args: str) -> Optional[str]:
    """Run `git -C cwd <args>`; return stripped stdout or None."""
    try:
        result = subprocess.run(
            ["git", "-C", cwd, *args],
            capture_output=True,
            # git prints UTF-8 paths; the locale codec would mangle them on Windows
            encoding="utf-8",
            errors="replace",
            timeout=2,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None
    if result.returncode != 0:
        return None
    out = result.stdout.strip()
    return out or None


def _norm_path(p: str) -> str:
    return p.replace("\\", "/").rstrip("/")


def _relative(cwd: str, root: str) -> Optional[str]:
    c, r = _norm_path(cwd), _norm_path(root)
    if c.lower() == r.lower():
        return ""
    prefix = r + "/"
    if c.lower().startswith(prefix.lower()):
        return c[len(prefix) :]
    return None


def compute_subdir(cwd: str, git_root: str) -> Optional[str]:
    """cwd relative to git_root, '/'-separated; '' at root, None if unrelated."""
    rel = _relative(cwd, git_root)
    if rel is None:
        try:
            rel = _relative(os.path.realpath(cwd), os.path.realpath(git_root))
        except (OSError, ValueError):
            rel = None
    return rel


def build_identity(cwd: str) -> Optional[dict]:
    """Return the sidecar dict for cwd, or None if no git identity."""
    if not cwd:
        return None
    identity = normalize_git_url(_git(cwd, "config", "--get", "remote.origin.url"))
    if not identity:
        return None
    root = _git(cwd, "rev-parse", "--show-toplevel")
    if root is None:
        # rev-parse failed or timed out: the subdir is unknown, so write nothing
        return None
    subdir = compute_subdir(cwd, root)
    if subdir is None:
        # A wrong subdir would merge this project into its repo root elsewhere
        return None
    return {
        "git_identity": identity,
        "subdir": subdir,
        "project_path": cwd,
        "written_by": "hook",
    }


def write_sidecar(project_dir: Path, data: dict) -> bool:
    """Atomically write the sidecar; skip if unchanged. Never raises."""
    target = project_dir / SIDECAR_NAME
    try:
        existing = json.loads(target.read_text(encoding="utf-8"))
        if isinstance(existing, dict) and all(
            existing.get(k) == data[k]
            for k in ("git_identity", "subdir", "project_path")
        ):
            return False
    except (OSError, ValueError):
        pass

    tmp = project_dir / "{}.{}".format(TMP_NAME, os.getpid())
    try:
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, target)
        return True
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        return False


def main() -> None:
    """Hook entry point. Never raises, never blocks SessionStart."""
    try:
        # Claude Code sends UTF-8; the locale codec (cp1252 on Windows) would mangle paths
        raw = sys.stdin.buffer.read().decode("utf-8")
        if not raw:
            return
        payload = json.loads(raw)
    except (ValueError, OSError):
        return
    if not isinstance(payload, dict):
        return

    cwd = payload.get("cwd") or ""
    transcript_path = payload.get("transcript_path") or ""
    if not isinstance(cwd, str) or not isinstance(transcript_path, str):
        return
    if not cwd or not transcript_path:
        return

    project_dir = Path(transcript_path).parent
    # Only ever write into <claude config dir>/projects/<encoded>
    try:
        config_dir = Path(
            os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude"
        )
        projects_dir = (config_dir / "projects").resolve()
        if project_dir.resolve().parent != projects_dir or not project_dir.is_dir():
            return
    except (OSError, RuntimeError):
        return

    data = build_identity(cwd)
    if data is None:
        return
    write_sidecar(project_dir, data)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # absolutely never block SessionStart
        pass
    sys.exit(0)
