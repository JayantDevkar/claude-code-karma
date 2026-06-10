"""
System (Linux) cron router — ADDITIVE feature, not part of upstream.

Endpoint:
  GET /cron/system   read-only view of the host's real cron daemon entries

Sources read (best-effort, each independent — a failure on one never blocks
the others):
  - the invoking user's crontab        (`crontab -l`)
  - the system crontab                 (/etc/crontab, has a user field)
  - drop-in jobs                       (/etc/cron.d/*, have a user field)
  - periodic run-parts directories     (/etc/cron.{hourly,daily,weekly,monthly})

Strictly read-only: we shell out to `crontab -l` and read files. We never
write, install, or remove any cron entry.

Kept in its own file (and its own route) so upstream pulls of the original
karma repo never conflict with it — the only shared edit is one
`include_router` line in main.py.
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query

from config import settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["cron"])

# cron macros (@daily ...) — value is the human label; next-run is left to
# croniter where it understands the alias, else None.
_MACROS = {
    "@reboot": "at boot",
    "@yearly": "yearly",
    "@annually": "yearly",
    "@monthly": "monthly",
    "@weekly": "weekly",
    "@daily": "daily",
    "@midnight": "daily (midnight)",
    "@hourly": "hourly",
}

_PERIODIC_DIRS = {
    "/etc/cron.hourly": "hourly",
    "/etc/cron.daily": "daily",
    "/etc/cron.weekly": "weekly",
    "/etc/cron.monthly": "monthly",
}

# VAR=value assignment lines inside a crontab — not jobs.
_ENV_RE = re.compile(r"^\s*[A-Za-z_][A-Za-z0-9_]*\s*=")


# Default install layout. Kept as a fallback so detection still works when
# the cron command references a symlinked `~/.claude` even if the API runs
# with a custom CLAUDE_KARMA_CLAUDE_BASE.
_DEFAULT_SKILL_RE = re.compile(r"[/\\]\.claude[/\\]skills[/\\]([^/\\\s]+)")
_DEFAULT_CLAUDE_MARKERS = (".claude/", ".claude\\", ".claude_karma/", ".claude_karma\\")


def _skill_from_configured_base(command: str) -> Optional[str]:
    """Match the skill name against the *configured* skills dir, so a custom
    CLAUDE_KARMA_CLAUDE_BASE (e.g. /opt/claude) is honoured, not just ~/.claude."""
    try:
        skills_dir = str(settings.skills_dir)
    except Exception:
        return None
    if not skills_dir:
        return None
    # Normalise both separators so the heuristic survives Windows-style paths.
    cmd = command.replace("\\", "/")
    base = skills_dir.replace("\\", "/").rstrip("/")
    m = re.search(re.escape(base) + r"/([^/\s]+)", cmd)
    return m.group(1) if m else None


def _classify(command: str, source: str) -> tuple[str, Optional[str]]:
    """
    Bucket an entry by origin → (origin, skill_name|None).

    Command path wins over source: a Claude skill scheduled from /etc/cron.d
    is still a skill. Origins: 'claude-skill', 'claude', 'system', 'user'.
    Detection is layout-aware (configured claude_base) with a ~/.claude
    fallback, so it works for any user on any install path.
    """
    skill = _skill_from_configured_base(command)
    if skill:
        return "claude-skill", skill
    m = _DEFAULT_SKILL_RE.search(command)
    if m:
        return "claude-skill", m.group(1)

    norm = command.replace("\\", "/")
    try:
        base = str(settings.claude_base).replace("\\", "/").rstrip("/")
    except Exception:
        base = ""
    if base and base in norm:
        return "claude", None
    if any(mark in command for mark in _DEFAULT_CLAUDE_MARKERS):
        return "claude", None

    if source == "/etc/crontab" or source.startswith("/etc/cron."):
        return "system", None
    return "user", None


def _next_run_iso(expr: str) -> Optional[str]:
    """Best-effort next fire time as ISO, or None if croniter can't parse."""
    try:
        from datetime import datetime

        from croniter import croniter

        if not croniter.is_valid(expr):
            return None
        return croniter(expr, datetime.now()).get_next(datetime).isoformat()
    except Exception:
        return None


def _human(expr: str) -> str:
    """Compact human label for the common cron shapes; falls back to raw."""
    if expr in _MACROS:
        return _MACROS[expr]
    parts = expr.split()
    if len(parts) != 5:
        return expr
    minute, hour, dom, month, dow = parts
    if expr == "* * * * *":
        return "every min"
    if minute.startswith("*/") and hour == "*":
        return f"every {minute[2:]} min"
    if hour.startswith("*/") and minute in ("0", "*"):
        return f"every {hour[2:]}h"
    if minute != "*" and hour != "*" and dom == "*" and month == "*" and dow == "*":
        return f"daily {hour.zfill(2)}:{minute.zfill(2)}"
    return expr


def _parse_line(line: str, *, has_user: bool, source: str) -> Optional[dict]:
    """Parse one crontab line into an entry dict, or None if it's not a job."""
    raw = line.rstrip("\n")
    stripped = raw.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if _ENV_RE.match(stripped):
        return None

    tokens = stripped.split()
    user = None

    if stripped.startswith("@"):
        macro = tokens[0]
        if macro not in _MACROS:
            return None
        rest = tokens[1:]
        if has_user:
            if not rest:
                return None
            user, rest = rest[0], rest[1:]
        command = " ".join(rest)
        expr = macro
    else:
        n_fields = 6 if has_user else 5
        if len(tokens) < n_fields + 1:
            return None
        expr = " ".join(tokens[:5])
        idx = 5
        if has_user:
            user = tokens[5]
            idx = 6
        command = " ".join(tokens[idx:])

    if not command:
        return None

    origin, skill = _classify(command, source)
    return {
        "schedule": expr,
        "schedule_human": _human(expr),
        "command": command,
        "user": user,
        "source": source,
        "origin": origin,
        "skill": skill,
        "next_run": _next_run_iso(expr),
        "raw": raw,
    }


def _read_user_crontab() -> tuple[list[dict], Optional[str]]:
    """`crontab -l` for the user running the API. Empty if none installed."""
    try:
        proc = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except FileNotFoundError:
        return [], "crontab binary not found"
    except subprocess.TimeoutExpired:
        return [], "crontab -l timed out"
    except Exception as exc:  # pragma: no cover - defensive
        return [], f"crontab -l failed: {exc}"

    if proc.returncode != 0:
        # "no crontab for <user>" is the normal empty case, not an error.
        msg = (proc.stderr or "").strip().lower()
        if "no crontab" in msg:
            return [], None
        return [], (proc.stderr or "crontab -l error").strip()

    entries = []
    for line in proc.stdout.splitlines():
        e = _parse_line(line, has_user=False, source="user crontab")
        if e:
            entries.append(e)
    return entries, None


def _read_file_crontab(path: Path, source: str) -> list[dict]:
    """Parse a system-style crontab file (entries carry a user field)."""
    try:
        text = path.read_text(errors="replace")
    except (FileNotFoundError, PermissionError, OSError):
        return []
    entries = []
    for line in text.splitlines():
        e = _parse_line(line, has_user=True, source=source)
        if e:
            entries.append(e)
    return entries


def _read_periodic() -> list[dict]:
    """List scripts in /etc/cron.{hourly,daily,weekly,monthly} (run-parts)."""
    entries = []
    for dir_path, label in _PERIODIC_DIRS.items():
        d = Path(dir_path)
        try:
            if not d.is_dir():
                continue
            for f in sorted(d.iterdir()):
                if f.name.startswith(".") or not f.is_file():
                    continue
                origin, skill = _classify(str(f), dir_path)
                entries.append(
                    {
                        "schedule": f"@{label}",
                        "schedule_human": label,
                        "command": str(f),
                        "user": "root",
                        "source": dir_path,
                        "origin": origin,
                        "skill": skill,
                        "next_run": None,
                        "raw": f"run-parts {dir_path} → {f.name}",
                    }
                )
        except (PermissionError, OSError):
            continue
    return entries


@router.get("/cron/system")
def list_system_cron(
    include_periodic: bool = Query(
        True,
        description="include /etc/cron.{hourly,daily,weekly,monthly} run-parts scripts",
    ),
) -> dict:
    """
    Read-only snapshot of the host cron daemon: the user crontab,
    /etc/crontab, /etc/cron.d/*, and (optionally) the run-parts periodic
    directories. This is the real OS cron table — distinct from Claude
    Code's session-scoped CronCreate jobs served by /cron.

    Works on Linux and macOS/BSD (anything with a `crontab` binary). On
    Windows the platform has no cron daemon, so the endpoint returns a clean
    `supported: false` payload instead of an error (scheduling there lives in
    Task Scheduler, which is out of scope).
    """
    platform = sys.platform

    if platform.startswith("win"):
        return {
            "entries": [],
            "count": 0,
            "by_source": {},
            "by_origin": {},
            "errors": [],
            "supported": False,
            "platform": platform,
            "note": "Windows has no cron daemon — scheduled tasks live in Task Scheduler.",
        }

    entries: list[dict] = []
    errors: list[str] = []

    user_entries, user_err = _read_user_crontab()
    entries.extend(user_entries)
    if user_err:
        errors.append(f"user crontab: {user_err}")

    entries.extend(_read_file_crontab(Path("/etc/crontab"), "/etc/crontab"))

    cron_d = Path("/etc/cron.d")
    try:
        if cron_d.is_dir():
            for f in sorted(cron_d.iterdir()):
                if f.name.startswith(".") or not f.is_file():
                    continue
                entries.extend(_read_file_crontab(f, f"/etc/cron.d/{f.name}"))
    except (PermissionError, OSError) as exc:
        errors.append(f"/etc/cron.d: {exc}")

    if include_periodic:
        entries.extend(_read_periodic())

    by_source: dict[str, int] = {}
    by_origin: dict[str, int] = {}
    for e in entries:
        by_source[e["source"]] = by_source.get(e["source"], 0) + 1
        by_origin[e["origin"]] = by_origin.get(e["origin"], 0) + 1

    return {
        "entries": entries,
        "count": len(entries),
        "by_source": by_source,
        "by_origin": by_origin,
        "errors": errors,
        "supported": True,
        "platform": platform,
    }
