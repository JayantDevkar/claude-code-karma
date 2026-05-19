#!/usr/bin/env python3
"""
Branch-name → ticket-link detector for Claude Code Karma.

Fires on SessionStart. Reads the session's cwd, asks git for the current
branch, matches against user-configured patterns (default: Linear/Jira
style `ABC-123`), and POSTs a link to the karma API. Silent on every
failure — this hook NEVER blocks SessionStart.

Configuration (~/.claude_karma/config.json):

    {
      "branch_detect_enabled": false,
      "ticket_branch_patterns": [
        {"regex": "(?P<key>[A-Z][A-Z0-9_]+-\\d+)", "provider": "linear"}
      ]
    }

Opt-in: branch_detect_enabled defaults to False so users must explicitly
flip it on to avoid surprise links on personal-projects directories.

See: docs/superpowers/specs/2026-05-13-session-ticket-linking-design.md
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

API_BASE = os.environ.get("CLAUDE_KARMA_API", "http://localhost:8000")
CONFIG_PATH = Path.home() / ".claude_karma" / "config.json"
LIVE_SESSIONS_DIR = Path.home() / ".claude_karma" / "live-sessions"
LOG_PATH = Path.home() / ".claude_karma" / "logs" / "ticket_branch_detector.log"
HTTP_TIMEOUT_SEC = 3

DEFAULT_CONFIG = {
    "branch_detect_enabled": False,
    "ticket_branch_patterns": [],
}


def _log(msg: str) -> None:
    """Append a timestamped line to the hook log. Best-effort."""
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with LOG_PATH.open("a") as f:
            f.write(f"{ts} {msg}\n")
    except Exception:
        pass


def load_config() -> dict:
    """Load ~/.claude_karma/config.json with sensible defaults on any error."""
    if not CONFIG_PATH.exists():
        return DEFAULT_CONFIG
    try:
        loaded = json.loads(CONFIG_PATH.read_text())
        if not isinstance(loaded, dict):
            return DEFAULT_CONFIG
        return {**DEFAULT_CONFIG, **loaded}
    except (OSError, json.JSONDecodeError) as e:
        _log(f"config load failed: {e!r}")
        return DEFAULT_CONFIG


def git_current_branch(cwd: str) -> Optional[str]:
    """Return the current git branch, or None if not in a git repo / detached HEAD."""
    if not cwd:
        return None
    try:
        result = subprocess.run(
            ["git", "symbolic-ref", "--short", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return None

    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    return branch or None


def lookup_slug_from_live_sessions(cwd: str) -> Optional[str]:
    """Best-effort slug lookup via the live-sessions tracker's state files.

    Picks the live-sessions entry whose `cwd` matches and whose
    `last_updated` is most recent. Returns None if nothing matches —
    the link will then be deduped by session_uuid only, which is fine
    for first-of-its-kind sessions.
    """
    if not cwd or not LIVE_SESSIONS_DIR.exists():
        return None

    best_slug: Optional[str] = None
    best_ts = ""

    try:
        for path in LIVE_SESSIONS_DIR.glob("*.json"):
            try:
                data = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if data.get("cwd") != cwd:
                continue
            ts = data.get("last_updated") or data.get("started_at") or ""
            if ts >= best_ts:
                best_ts = ts
                best_slug = data.get("slug")
    except OSError:
        return None

    return best_slug


def match_pattern(branch: str, patterns: list) -> Optional[tuple[str, str]]:
    """Return (provider, ref) for the first matching pattern, else None."""
    for entry in patterns:
        if not isinstance(entry, dict):
            continue
        regex = entry.get("regex")
        provider = entry.get("provider")
        if not regex or provider not in ("linear", "jira", "github"):
            continue
        try:
            m = re.search(regex, branch)
        except re.error as e:
            _log(f"bad regex {regex!r}: {e!r}")
            continue
        if not m:
            continue
        if "key" in m.groupdict() and m.group("key"):
            ref = m.group("key")
        else:
            ref = m.group(0)
        return provider, ref
    return None


def post_link(
    session_uuid: str,
    ref: str,
    provider: str,
    session_slug: Optional[str],
) -> bool:
    """POST the link to karma. Returns True on success; never raises."""
    url = f"{API_BASE}/sessions/{session_uuid}/tickets"
    body: dict = {
        "ref": ref,
        "provider": provider,
        "source": "branch",
    }
    if session_slug:
        body["session_slug"] = session_slug

    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SEC)
        return True
    except (urllib.error.URLError, OSError) as e:
        _log(f"POST {url} failed: {e!r}")
        return False


def main() -> None:
    """Hook entry point. Never raises, never blocks SessionStart."""
    try:
        raw = sys.stdin.read()
        if not raw:
            return
        payload = json.loads(raw)
    except (json.JSONDecodeError, OSError):
        return

    session_uuid = payload.get("session_id")
    cwd = payload.get("cwd") or ""
    if not session_uuid:
        return

    config = load_config()
    if not config.get("branch_detect_enabled"):
        return

    patterns = config.get("ticket_branch_patterns") or []
    if not patterns:
        return

    branch = git_current_branch(cwd)
    if not branch:
        return

    matched = match_pattern(branch, patterns)
    if matched is None:
        return

    provider, ref = matched
    slug = lookup_slug_from_live_sessions(cwd)
    post_link(session_uuid, ref, provider, slug)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # absolutely never block SessionStart
        _log(f"unexpected error: {e!r}")
    sys.exit(0)
