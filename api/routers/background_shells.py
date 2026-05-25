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
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from db.connection import sqlite_read
from db.queries_shells_cron import (
    get_shells_for_session,
    get_shells_global,
    get_shells_project_rollup,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["background-shells"])


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
        description="'Bash' or 'Monitor'",
        pattern="^(Bash|Monitor)$",
    ),
    limit: int = Query(200, ge=1, le=1000),
) -> dict:
    """
    Aggregated background_shells across all sessions, joined to sessions +
    projects for display labels. Ordered by spawned_at DESC.
    """
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
