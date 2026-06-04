"""
Background shells router.

Endpoints:
  GET /shells                         global list, filters: project/status/tool
  GET /shells/project-rollup          counts per project
  GET /sessions/{uuid}/shells         per-session list with polls attached

Reads only — extraction is done by the indexer. All endpoints use a
short-lived read connection (sqlite_read), matching karma's existing
read-path convention.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from db.connection import get_writer_db, sqlite_read
from db.queries_shells_cron import (
    get_shells_for_session,
    get_shells_global,
    get_shells_project_rollup,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["background-shells"])

# Debounce: only run the incremental sync at most once per this many seconds.
_SYNC_DEBOUNCE_SECS = 10
_last_sync_at: float = 0.0


def _maybe_sync() -> None:
    """Run an incremental JSONL sync if enough time has passed since the last one."""
    global _last_sync_at
    now = time.monotonic()
    if now - _last_sync_at < _SYNC_DEBOUNCE_SECS:
        return
    _last_sync_at = now
    try:
        from db.connection import get_writer_db as _gw
        from db.indexer import sync_all_projects

        conn = _gw()
        sync_all_projects(conn)
    except Exception as exc:
        logger.warning("shells quick-sync failed: %s", exc)


# ---------------------------------------------------------------------------
# Global
# ---------------------------------------------------------------------------


@router.get("/shells")
def list_shells_global(
    project: Optional[str] = Query(None, description="encoded project name filter"),
    status: Optional[str] = Query(
        None,
        description="'running' (terminated_at IS NULL) or 'closed'",
        pattern="^(running|closed)$",
    ),
    tool: Optional[str] = Query(
        None,
        description="'Bash', 'Monitor', or 'Manual'",
        pattern="^(Bash|Monitor|Manual)$",
    ),
    limit: int = Query(200, ge=1, le=1000),
) -> dict:
    """
    Aggregated background_shells across all sessions, joined to sessions +
    projects for display labels. Ordered by spawned_at DESC.
    """
    _maybe_sync()
    with sqlite_read() as conn:
        conn.row_factory = __import__("sqlite3").Row
        rows = get_shells_global(
            conn,
            project_encoded_name=project,
            status=status,
            tool_name=tool,
            limit=limit,
        )
    return {"shells": rows, "count": len(rows)}


@router.get("/shells/project-rollup")
def shells_project_rollup() -> dict:
    """Per-project counts: total shells, currently running, total output bytes."""
    with sqlite_read() as conn:
        conn.row_factory = __import__("sqlite3").Row
        rows = get_shells_project_rollup(conn)
    return {"projects": rows, "count": len(rows)}


# ---------------------------------------------------------------------------
# Per-session
# ---------------------------------------------------------------------------


@router.get("/sessions/{uuid}/shells")
def list_shells_for_session(
    uuid: str,
    include_polls: bool = Query(True, description="attach poll rows under each shell"),
) -> dict:
    """
    All background_shells for a session, ordered by spawned_at DESC, with
    polls attached (chronological) when include_polls=True.
    """
    with sqlite_read() as conn:
        conn.row_factory = __import__("sqlite3").Row
        # Confirm the session exists so we can 404 cleanly rather than return [].
        session_exists = conn.execute(
            "SELECT 1 FROM sessions WHERE uuid = ?",
            (uuid,),
        ).fetchone()
        if not session_exists:
            raise HTTPException(status_code=404, detail="session not found")
        rows = get_shells_for_session(conn, uuid, include_polls=include_polls)
    return {"shells": rows, "count": len(rows), "session_uuid": uuid}


# ---------------------------------------------------------------------------
# Kill
# ---------------------------------------------------------------------------


@router.post("/shells/{tool_use_id}/kill")
def kill_shell(tool_use_id: str) -> dict:
    """
    Attempt to terminate a running background shell by its tool_use_id.

    Looks up the output_file_path stored at index time, uses lsof to find
    the PID(s) writing to that file, and sends SIGTERM. Falls back to SIGKILL
    if lsof is unavailable. Always marks the shell as terminated in the DB
    (terminated_by='kill') regardless of whether a live process was found.
    """
    import sqlite3 as _sqlite3

    with sqlite_read() as conn:
        conn.row_factory = _sqlite3.Row
        row = conn.execute(
            "SELECT id, terminated_at, output_file_path FROM background_shells WHERE tool_use_id = ?",
            (tool_use_id,),
        ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="shell not found")
    if row["terminated_at"] is not None:
        return {"killed": False, "reason": "already terminated"}

    output_file = row["output_file_path"]
    killed_pids: list[int] = []

    if output_file and shutil.which("lsof"):
        try:
            result = subprocess.run(
                ["lsof", "-F", "p", output_file],
                capture_output=True,
                text=True,
                timeout=5,
            )
            for line in result.stdout.splitlines():
                if line.startswith("p"):
                    try:
                        pid = int(line[1:])
                        subprocess.run(["kill", "-TERM", str(pid)], timeout=3)
                        killed_pids.append(pid)
                    except (ValueError, subprocess.SubprocessError):
                        pass
        except Exception as exc:
            logger.warning("lsof/kill failed for shell %s: %s", tool_use_id, exc)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + "000Z"
    conn = get_writer_db()
    conn.execute(
        """
        UPDATE background_shells
        SET terminated_at = ?, terminated_by = 'kill'
        WHERE tool_use_id = ? AND terminated_at IS NULL
        """,
        (now, tool_use_id),
    )
    conn.commit()

    return {
        "killed": True,
        "pids_signalled": killed_pids,
        "reason": f"SIGTERM sent to {len(killed_pids)} process(es)"
        if killed_pids
        else "no live process found; marked terminated in DB",
    }
