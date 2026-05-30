"""
Background shells + cron extraction pass.

Scans a session JSONL once and folds out:
- background_shells     (Bash{run_in_background:true} / Monitor spawns)
- shell_polls           (BashOutput calls)
- cron_jobs             (CronCreate / CronDelete events)

Idempotent via UPSERT on UNIQUE(tool_use_id). The parent row's `id` is
preserved across re-indexes, so child CASCADE deletes do not churn and
shell_polls UNIQUE(shell_row_id, tool_use_id) deduplicates correctly.

cron_fires are NOT inserted here — they are derived on read in queries.py.

The cron_state_snapshots table is populated by a separate sweep over
~/.claude_karma/cron-state/{session_uuid}/events.jsonl files written by
the optional cron_state_capture.py hook. See sync_cron_state_snapshots().
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Max stored size for command and output excerpt blobs. Truncation is flagged
# in the row via *_truncated columns so the UI can show "…(truncated)".
COMMAND_MAX_BYTES = 4096
OUTPUT_EXCERPT_MAX_BYTES = 4096

# Cron jobs have a hard 7-day TTL in Claude Code — after this point even
# `claude --resume` cannot revive them.
CRON_TTL_DAYS = 7

# Shell ID extraction. Observed real format from Claude Code:
#   "Command running in background with ID: bh0udrq27"
# Also handle JSON-shaped results: "shell_id": "...". IDs are alphanumeric
# (not just hex) — observed lowercase letters + digits, 6-16 chars.
_SHELL_ID_RE = re.compile(
    r"(?:shell[_ ]?id|background with ID|with ID)[\":\s]*([a-z0-9]{6,16})",
    re.IGNORECASE,
)

# Modern Claude Code (post-BashOutput) reports the output file path in the
# Bash{run_in_background} tool_result and instructs the agent to Read it.
# Pattern: "Output is being written to: /private/tmp/.../tasks/abc.output."
_OUTPUT_FILE_RE = re.compile(
    r"Output is being written to:\s*(\S+\.output)",
    re.IGNORECASE,
)

# When a background shell exits naturally, Claude Code writes a user message
# whose content is a raw XML string (not a list of blocks):
#   <task-notification>
#     <task-id>bx93dg00s</task-id>
#     <tool-use-id>toolu_01Wqvk3U47...</tool-use-id>
#     <status>completed</status>
#     <summary>... completed (exit code 0)</summary>
#   </task-notification>
_TASK_NOTIF_TOOL_USE_ID_RE = re.compile(r"<tool-use-id>\s*(.*?)\s*</tool-use-id>")
_TASK_NOTIF_STATUS_RE = re.compile(r"<status>\s*(.*?)\s*</status>")
_TASK_NOTIF_EXIT_CODE_RE = re.compile(r"exit code\s+(\d+)", re.IGNORECASE)

# Cron job IDs are documented as 8-char alphanumeric. Real formats observed:
#   "Scheduled recurring job 18a4d15a"  (current Claude Code format)
#   "task created with ID: a4f9b2c1" or "id": "a4f9b2c1" in JSON.
_CRON_ID_RE = re.compile(
    r"(?:cron[_ ]?id|task[_ ]?id|\bjob|\bid)[\":\s]+([a-z0-9]{8})\b",
    re.IGNORECASE,
)


# ============================================================================
# Helpers
# ============================================================================


def _normalize_ts(ts: Optional[str]) -> Optional[str]:
    """Normalize ISO-8601 to a Z-suffix form for consistent lexicographic sort."""
    if not ts:
        return None
    if ts.endswith("+00:00"):
        return ts[:-6] + "Z"
    return ts


def _flatten_result_content(raw: Any) -> str:
    """
    tool_result.content is either a string OR a list of {type:'text',text:str}.

    Return a single concatenated string so we can run regex on either shape.
    """
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        parts: List[str] = []
        for c in raw:
            if isinstance(c, dict):
                t = c.get("text") or c.get("content") or ""
                if isinstance(t, str):
                    parts.append(t)
            elif isinstance(c, str):
                parts.append(c)
        return "\n".join(parts)
    return str(raw)


def _truncate(value: str, max_bytes: int) -> Tuple[str, bool]:
    """Return (truncated_value, was_truncated)."""
    if value is None:
        return "", False
    encoded = value.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return value, False
    return encoded[:max_bytes].decode("utf-8", errors="replace"), True


def _extract_shell_id(result_text: str) -> Optional[str]:
    m = _SHELL_ID_RE.search(result_text)
    return m.group(1) if m else None


def _extract_output_file(result_text: str) -> Optional[str]:
    m = _OUTPUT_FILE_RE.search(result_text)
    return m.group(1) if m else None


def _parse_task_notification(content: str) -> Optional[Dict[str, Any]]:
    """
    Parse a <task-notification> string written by Claude Code when a background
    shell exits naturally. Returns a dict with tool_use_id, terminated_by, and
    exit_code, or None if the string doesn't match.
    """
    if "<task-notification>" not in content:
        return None
    tu_m = _TASK_NOTIF_TOOL_USE_ID_RE.search(content)
    st_m = _TASK_NOTIF_STATUS_RE.search(content)
    if not tu_m or not st_m:
        return None
    status = st_m.group(1).lower()
    terminated_by = "timeout" if status == "timeout" else "natural"
    ec_m = _TASK_NOTIF_EXIT_CODE_RE.search(content)
    return {
        "tool_use_id": tu_m.group(1),
        "terminated_by": terminated_by,
        "exit_code": int(ec_m.group(1)) if ec_m else None,
    }


def _extract_cron_id(result_text: str) -> Optional[str]:
    m = _CRON_ID_RE.search(result_text)
    return m.group(1) if m else None


def _iter_jsonl(jsonl_path: Path) -> Iterator[Dict[str, Any]]:
    """Yield parsed lines from a JSONL file, skipping malformed lines."""
    with jsonl_path.open("r", encoding="utf-8", errors="replace") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


# ============================================================================
# Extraction
# ============================================================================


def extract_shells_and_cron(
    jsonl_path: Path,
    session_uuid: str,
    session_ended: bool,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Walk a session JSONL and build three row sets ready for UPSERT.

    Args:
        jsonl_path: path to the session's .jsonl file
        session_uuid: the session's UUID (FK)
        session_ended: True when the session has a known end_time; affects
            terminated_by for orphaned shells (session_end vs still-running)

    Returns:
        (shells, polls, crons) — each a list of dict rows for executemany.
    """
    # Keyed by spawn tool_use_id (always unique)
    shells_by_tool_use: Dict[str, Dict[str, Any]] = {}
    # Reverse index: shell_id (returned in result) -> tool_use_id, so we can
    # resolve BashOutput/KillShell which reference shell_id.
    shell_id_to_tu: Dict[str, str] = {}
    # Buffered BashOutput rows pending their tool_result (which carries bytes)
    pending_polls: Dict[str, Dict[str, Any]] = {}  # by BashOutput tool_use_id
    polls: List[Dict[str, Any]] = []
    # Modern Claude Code polls via Read on the output file instead of BashOutput.
    # Map: output_file_path → parent shell tool_use_id
    shell_output_files: Dict[str, str] = {}
    # Buffered Read-poll rows pending their tool_result
    pending_read_polls: Dict[str, Dict[str, Any]] = {}  # by Read tool_use_id

    # Cron, keyed by CronCreate tool_use_id
    crons_by_tool_use: Dict[str, Dict[str, Any]] = {}
    cron_id_to_tu: Dict[str, str] = {}

    for obj in _iter_jsonl(jsonl_path):
        ts = _normalize_ts(obj.get("timestamp"))
        msg = obj.get("message") or {}
        msg_uuid = obj.get("uuid")
        content = msg.get("content")

        # task-notification: user message whose content is a raw XML string
        # (not a list of blocks) written when a bg shell exits naturally.
        if isinstance(content, str):
            info = _parse_task_notification(content)
            if info:
                shell = shells_by_tool_use.get(info["tool_use_id"])
                if shell and shell["terminated_at"] is None:
                    shell["terminated_at"] = ts
                    shell["terminated_by"] = info["terminated_by"]
                    if info["exit_code"] is not None:
                        shell["exit_code"] = info["exit_code"]
            continue

        if not isinstance(content, list):
            continue

        for c in content:
            if not isinstance(c, dict):
                continue

            ctype = c.get("type")

            # ---- tool_use ----
            if ctype == "tool_use":
                name = c.get("name")
                tu_id = c.get("id")
                inp = c.get("input") or {}

                if not tu_id:
                    continue

                # Bash with run_in_background
                if name == "Bash" and inp.get("run_in_background"):
                    cmd, cmd_trunc = _truncate(inp.get("command") or "", COMMAND_MAX_BYTES)
                    shells_by_tool_use[tu_id] = {
                        "session_uuid": session_uuid,
                        "tool_use_id": tu_id,
                        "shell_id": None,
                        "tool_name": "Bash",
                        "command": cmd,
                        "command_truncated": 1 if cmd_trunc else 0,
                        "description": inp.get("description"),
                        "is_persistent": 0,
                        "timeout_ms": inp.get("timeout"),
                        "spawned_at": ts,
                        "terminated_at": None,
                        "terminated_by": None,
                        "exit_code": None,
                        "poll_count": 0,
                        "total_output_bytes": 0,
                        "last_output_at": None,
                        "spawn_message_uuid": msg_uuid,
                        "output_file_path": None,
                    }

                # Monitor (always background-like; streams output)
                elif name == "Monitor":
                    cmd, cmd_trunc = _truncate(inp.get("command") or "", COMMAND_MAX_BYTES)
                    shells_by_tool_use[tu_id] = {
                        "session_uuid": session_uuid,
                        "tool_use_id": tu_id,
                        "shell_id": None,
                        "tool_name": "Monitor",
                        "command": cmd,
                        "command_truncated": 1 if cmd_trunc else 0,
                        "description": inp.get("description"),
                        "is_persistent": 1 if inp.get("persistent") else 0,
                        "timeout_ms": inp.get("timeout_ms"),
                        "spawned_at": ts,
                        "terminated_at": None,
                        "terminated_by": None,
                        "exit_code": None,
                        "poll_count": 0,
                        "total_output_bytes": 0,
                        "last_output_at": None,
                        "spawn_message_uuid": msg_uuid,
                        "output_file_path": None,
                    }

                # BashOutput — buffer until we see the tool_result (which has bytes)
                elif name == "BashOutput":
                    pending_polls[tu_id] = {
                        "shell_id": inp.get("shell_id"),
                        "polled_at": ts,
                        "filter_pattern": inp.get("filter"),
                        "tool_use_id": tu_id,
                    }

                # Read on a known shell output file — modern polling path
                elif name == "Read":
                    file_path = inp.get("file_path") or ""
                    if file_path in shell_output_files:
                        pending_read_polls[tu_id] = {
                            "_parent_tool_use_id": shell_output_files[file_path],
                            "polled_at": ts,
                            "tool_use_id": tu_id,
                        }

                # KillShell — close out the parent shell
                elif name == "KillShell":
                    target_shell_id = inp.get("shell_id")
                    if target_shell_id and target_shell_id in shell_id_to_tu:
                        parent = shells_by_tool_use[shell_id_to_tu[target_shell_id]]
                        if parent["terminated_at"] is None:
                            parent["terminated_at"] = ts
                            parent["terminated_by"] = "kill"

                # CronCreate
                elif name == "CronCreate":
                    cron_expr = inp.get("cron") or ""
                    created_dt = _ts_to_datetime(ts) or datetime.now(timezone.utc)
                    ttl_expires = (created_dt + timedelta(days=CRON_TTL_DAYS)).isoformat()
                    if ttl_expires.endswith("+00:00"):
                        ttl_expires = ttl_expires[:-6] + "Z"
                    crons_by_tool_use[tu_id] = {
                        "session_uuid": session_uuid,
                        "tool_use_id": tu_id,
                        "cron_id": None,
                        "cron_expression": cron_expr,
                        "prompt": inp.get("prompt") or "",
                        "recurring": 1 if inp.get("recurring") else 0,
                        "created_at": ts,
                        "deleted_at": None,
                        "deleted_via": None,
                        "ttl_expires_at": ttl_expires,
                        "create_message_uuid": msg_uuid,
                    }

                # CronDelete — fold into parent if we can find it
                elif name == "CronDelete":
                    target_cron_id = inp.get("id") or inp.get("cron_id")
                    if target_cron_id and target_cron_id in cron_id_to_tu:
                        parent = crons_by_tool_use[cron_id_to_tu[target_cron_id]]
                        if parent["deleted_at"] is None:
                            parent["deleted_at"] = ts
                            parent["deleted_via"] = "CronDelete"

            # ---- tool_result ----
            elif ctype == "tool_result":
                ref_id = c.get("tool_use_id")
                if not ref_id:
                    continue
                text = _flatten_result_content(c.get("content"))

                # bg-shell spawn result → extract shell_id + output file path
                if ref_id in shells_by_tool_use:
                    row = shells_by_tool_use[ref_id]
                    sid = _extract_shell_id(text)
                    if sid and not row["shell_id"]:
                        row["shell_id"] = sid
                        shell_id_to_tu[sid] = ref_id
                    out_file = _extract_output_file(text)
                    if out_file:
                        shell_output_files[out_file] = ref_id
                        row["output_file_path"] = out_file

                # CronCreate result → extract cron_id
                elif ref_id in crons_by_tool_use:
                    row = crons_by_tool_use[ref_id]
                    cid = _extract_cron_id(text)
                    if cid and not row["cron_id"]:
                        row["cron_id"] = cid
                        cron_id_to_tu[cid] = ref_id

                # Read-on-output-file result → finalize as a poll
                elif ref_id in pending_read_polls:
                    poll_info = pending_read_polls.pop(ref_id)
                    parent_tu = poll_info["_parent_tool_use_id"]
                    parent = shells_by_tool_use.get(parent_tu)
                    if parent is not None:
                        excerpt, excerpt_trunc = _truncate(text, OUTPUT_EXCERPT_MAX_BYTES)
                        output_bytes = len(text.encode("utf-8", errors="replace"))
                        polls.append({
                            "_parent_tool_use_id": parent_tu,
                            "polled_at": poll_info["polled_at"],
                            "filter_pattern": None,
                            "output_bytes": output_bytes,
                            "output_excerpt": excerpt if output_bytes else None,
                            "output_truncated": 1 if excerpt_trunc else 0,
                            "tool_use_id": poll_info["tool_use_id"],
                        })
                        parent["poll_count"] += 1
                        parent["total_output_bytes"] += output_bytes
                        parent["last_output_at"] = poll_info["polled_at"]

                # BashOutput result → finalize the poll, update parent counters
                elif ref_id in pending_polls:
                    poll = pending_polls.pop(ref_id)
                    target_shell_id = poll.get("shell_id")
                    if not target_shell_id or target_shell_id not in shell_id_to_tu:
                        # Orphaned poll — shell we never saw spawn. Skip.
                        continue
                    parent_tu = shell_id_to_tu[target_shell_id]
                    parent = shells_by_tool_use[parent_tu]

                    excerpt, excerpt_trunc = _truncate(text, OUTPUT_EXCERPT_MAX_BYTES)
                    output_bytes = len(text.encode("utf-8", errors="replace"))

                    polls.append({
                        "_parent_tool_use_id": parent_tu,  # resolved to FK at write time
                        "polled_at": poll["polled_at"],
                        "filter_pattern": poll["filter_pattern"],
                        "output_bytes": output_bytes,
                        "output_excerpt": excerpt if output_bytes else None,
                        "output_truncated": 1 if excerpt_trunc else 0,
                        "tool_use_id": poll["tool_use_id"],
                    })

                    # Update parent aggregates
                    parent["poll_count"] += 1
                    parent["total_output_bytes"] += output_bytes
                    parent["last_output_at"] = poll["polled_at"]

    # End-of-file: any shell still running gets the session_end marker IF the
    # session has actually ended. Otherwise leave it open — the indexer will
    # re-evaluate on the next pass.
    if session_ended:
        for row in shells_by_tool_use.values():
            if row["terminated_at"] is None:
                row["terminated_at"] = row["last_output_at"] or row["spawned_at"]
                row["terminated_by"] = "session_end"

    return (
        list(shells_by_tool_use.values()),
        polls,
        list(crons_by_tool_use.values()),
    )


def _ts_to_datetime(ts: Optional[str]) -> Optional[datetime]:
    """Parse ISO-8601 (with Z or +00:00) to a tz-aware datetime."""
    if not ts:
        return None
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


# ============================================================================
# Persistence — UPSERT
# ============================================================================


_UPSERT_SHELL_SQL = """
INSERT INTO background_shells (
    session_uuid, tool_use_id, shell_id, tool_name, command, command_truncated,
    description, is_persistent, timeout_ms, spawned_at, terminated_at,
    terminated_by, exit_code, poll_count, total_output_bytes, last_output_at,
    spawn_message_uuid, output_file_path
) VALUES (
    :session_uuid, :tool_use_id, :shell_id, :tool_name, :command, :command_truncated,
    :description, :is_persistent, :timeout_ms, :spawned_at, :terminated_at,
    :terminated_by, :exit_code, :poll_count, :total_output_bytes, :last_output_at,
    :spawn_message_uuid, :output_file_path
)
ON CONFLICT(tool_use_id) DO UPDATE SET
    shell_id           = excluded.shell_id,
    command            = excluded.command,
    command_truncated  = excluded.command_truncated,
    description        = excluded.description,
    is_persistent      = excluded.is_persistent,
    timeout_ms         = excluded.timeout_ms,
    spawned_at         = excluded.spawned_at,
    terminated_at      = excluded.terminated_at,
    terminated_by      = excluded.terminated_by,
    exit_code          = excluded.exit_code,
    poll_count         = excluded.poll_count,
    total_output_bytes = excluded.total_output_bytes,
    last_output_at     = excluded.last_output_at,
    spawn_message_uuid = excluded.spawn_message_uuid,
    output_file_path   = excluded.output_file_path
"""

_UPSERT_POLL_SQL = """
INSERT INTO shell_polls (
    shell_row_id, polled_at, filter_pattern, output_bytes,
    output_excerpt, output_truncated, tool_use_id
) VALUES (
    :shell_row_id, :polled_at, :filter_pattern, :output_bytes,
    :output_excerpt, :output_truncated, :tool_use_id
)
ON CONFLICT(shell_row_id, tool_use_id) DO UPDATE SET
    polled_at        = excluded.polled_at,
    filter_pattern   = excluded.filter_pattern,
    output_bytes     = excluded.output_bytes,
    output_excerpt   = excluded.output_excerpt,
    output_truncated = excluded.output_truncated
"""

_UPSERT_CRON_SQL = """
INSERT INTO cron_jobs (
    session_uuid, tool_use_id, cron_id, cron_expression, prompt, recurring,
    created_at, deleted_at, deleted_via, ttl_expires_at, create_message_uuid
) VALUES (
    :session_uuid, :tool_use_id, :cron_id, :cron_expression, :prompt, :recurring,
    :created_at, :deleted_at, :deleted_via, :ttl_expires_at, :create_message_uuid
)
ON CONFLICT(tool_use_id) DO UPDATE SET
    cron_id             = excluded.cron_id,
    cron_expression     = excluded.cron_expression,
    prompt              = excluded.prompt,
    recurring           = excluded.recurring,
    created_at          = excluded.created_at,
    deleted_at          = excluded.deleted_at,
    deleted_via         = excluded.deleted_via,
    ttl_expires_at      = excluded.ttl_expires_at,
    create_message_uuid = excluded.create_message_uuid
"""


def persist_shells_and_cron(
    conn: sqlite3.Connection,
    session_uuid: str,
    shells: List[Dict[str, Any]],
    polls: List[Dict[str, Any]],
    crons: List[Dict[str, Any]],
) -> None:
    """
    UPSERT all rows for one session and clear the needs_shell_cron_reindex flag.

    Polls reference their parent by `_parent_tool_use_id`; we resolve to the
    parent row's primary key inside this function so the caller does not need
    to know about IDs.
    """
    # Upsert shells first so we can resolve poll FKs
    for s in shells:
        conn.execute(_UPSERT_SHELL_SQL, s)

    # Build a map: tool_use_id -> background_shells.id
    if polls:
        tu_ids = list({p["_parent_tool_use_id"] for p in polls})
        placeholders = ",".join("?" * len(tu_ids))
        id_map = {
            row[0]: row[1]
            for row in conn.execute(
                f"SELECT tool_use_id, id FROM background_shells WHERE tool_use_id IN ({placeholders})",
                tu_ids,
            )
        }
        for p in polls:
            parent_id = id_map.get(p["_parent_tool_use_id"])
            if parent_id is None:
                # Shouldn't happen (we just upserted), but be defensive.
                continue
            conn.execute(_UPSERT_POLL_SQL, {
                "shell_row_id": parent_id,
                "polled_at": p["polled_at"],
                "filter_pattern": p["filter_pattern"],
                "output_bytes": p["output_bytes"],
                "output_excerpt": p["output_excerpt"],
                "output_truncated": p["output_truncated"],
                "tool_use_id": p["tool_use_id"],
            })

    for c in crons:
        conn.execute(_UPSERT_CRON_SQL, c)

    # Clear the per-session reindex flag now that we've processed it.
    conn.execute(
        "UPDATE sessions SET needs_shell_cron_reindex = 0 WHERE uuid = ?",
        (session_uuid,),
    )


# ============================================================================
# Cron live-state hook ingestion
# ============================================================================


def sync_cron_state_snapshots(conn: sqlite3.Connection, karma_dir: Path) -> int:
    """
    Read cron-state event logs written by the optional hook and upsert into
    cron_state_snapshots.

    Looks at: {karma_dir}/cron-state/{session_uuid}/events.jsonl

    Returns: number of new snapshots inserted (excluding dupes).
    """
    state_root = karma_dir / "cron-state"
    if not state_root.exists():
        return 0

    inserted = 0
    for session_dir in state_root.iterdir():
        if not session_dir.is_dir():
            continue
        session_uuid = session_dir.name
        events_path = session_dir / "events.jsonl"
        if not events_path.exists():
            continue

        for obj in _iter_jsonl(events_path):
            captured_at = _normalize_ts(obj.get("captured_at"))
            trigger_event = obj.get("trigger_event")
            if not captured_at or trigger_event not in {
                "CronCreate", "CronDelete", "CronList", "session_start"
            }:
                continue

            payload = obj.get("tool_response") or obj.get("payload") or {}
            try:
                cur = conn.execute(
                    """
                    INSERT INTO cron_state_snapshots
                        (session_uuid, captured_at, trigger_event, payload_json)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(session_uuid, trigger_event, captured_at) DO NOTHING
                    """,
                    (session_uuid, captured_at, trigger_event, json.dumps(payload)),
                )
                if cur.rowcount > 0:
                    inserted += 1
            except sqlite3.IntegrityError:
                # FK violation: session_uuid doesn't exist in sessions table yet.
                # That's expected for in-flight sessions; skip for now.
                continue

    return inserted
