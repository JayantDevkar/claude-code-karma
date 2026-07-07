#!/usr/bin/env python3
"""
Cron live-state capture hook for Claude Code Karma.

Optional PostToolUse hook. Watches CronCreate / CronDelete / CronList tool
calls and writes per-session event logs + the latest CronList snapshot to:

    ~/.claude_karma/cron-state/{session_uuid}/
        events.jsonl     append-only — one record per CronCreate/Delete/List
        snapshot.json    overwrite   — the latest CronList response

The karma indexer ingests events.jsonl into the cron_state_snapshots SQLite
table (idempotent via UNIQUE(session_uuid, trigger_event, captured_at)).

Why this is opt-in:
    Cron state in Claude Code lives in-memory only; karma can normally
    reconstruct CronCreate/CronDelete events from JSONL after the fact.
    The hook adds ground-truth CronList snapshots so karma can show "what
    is scheduled RIGHT NOW" instead of only "what was scheduled in this
    session's history." Off by default to keep karma minimal.

Install:
    Add to ~/.claude/settings.json:
        "hooks": {
            "PostToolUse": [{
                "matcher": "CronCreate|CronDelete|CronList",
                "hooks": [{
                    "type": "command",
                    "command": "/path/to/claude-karma/hooks/cron_state_capture.py"
                }]
            }]
        }

The hook silently no-ops on any error so it never blocks a Claude Code
session. Errors are logged to ~/.claude_karma/cron-state/.errors.log so
they remain debuggable.
"""

from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

KARMA_BASE = Path.home() / ".claude_karma"
STATE_ROOT = KARMA_BASE / "cron-state"
ERROR_LOG = STATE_ROOT / ".errors.log"

WATCH_TOOLS = {"CronCreate", "CronDelete", "CronList"}


def _now_z() -> str:
    """ISO-8601 with Z suffix; matches karma's stored timestamp format."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _log_error(detail: str) -> None:
    """Append to a per-user error log. Best-effort: ignores write failures."""
    try:
        STATE_ROOT.mkdir(parents=True, exist_ok=True)
        with ERROR_LOG.open("a", encoding="utf-8") as fp:
            fp.write(f"{_now_z()}\t{detail}\n")
    except OSError:
        pass


def main() -> int:
    """Read PostToolUse event JSON from stdin and persist if relevant."""
    try:
        raw = sys.stdin.read()
        if not raw:
            return 0
        event: Dict[str, Any] = json.loads(raw)
    except (json.JSONDecodeError, OSError) as e:
        _log_error(f"stdin parse: {e}")
        return 0

    tool_name = event.get("tool_name")
    if tool_name not in WATCH_TOOLS:
        return 0

    session_uuid = event.get("session_id") or event.get("sessionId")
    if not session_uuid:
        _log_error("missing session_id")
        return 0

    try:
        out_dir = STATE_ROOT / session_uuid
        out_dir.mkdir(parents=True, exist_ok=True)

        record = {
            "captured_at": _now_z(),
            "trigger_event": tool_name,
            "tool_input": event.get("tool_input"),
            "tool_response": event.get("tool_response"),
            "cwd": event.get("cwd"),
        }

        # Append every event to events.jsonl. Atomic line-write — no rotation,
        # files stay small (one line per cron tool call).
        with (out_dir / "events.jsonl").open("a", encoding="utf-8") as fp:
            fp.write(json.dumps(record, default=str) + "\n")

        # On CronList: overwrite snapshot.json with the live state.
        if tool_name == "CronList":
            snapshot = {
                "captured_at": record["captured_at"],
                "session_uuid": session_uuid,
                "jobs": event.get("tool_response"),
            }
            snapshot_path = out_dir / "snapshot.json"
            tmp_path = snapshot_path.with_suffix(".json.tmp")
            with tmp_path.open("w", encoding="utf-8") as fp:
                json.dump(snapshot, fp, indent=2, default=str)
            tmp_path.replace(snapshot_path)  # atomic on POSIX
    except OSError as e:
        _log_error(f"write: {e}")
        return 0
    except Exception:  # noqa: BLE001 — hook must never propagate
        _log_error(f"unexpected:\n{traceback.format_exc()}")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
