"""
Cron router.

Endpoints:
  GET /cron                          global list, filters: project/active_only
  GET /cron/project-rollup           counts per project (total + active)
  GET /sessions/{uuid}/cron          per-session list with fires inferred on read

Fire inference uses croniter to match assistant turn timestamps against
the cron expression's scheduled times. Inference is computed on read
(NOT persisted) so we can tune the matching window without re-indexing.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from config import settings
from db.connection import sqlite_read
from db.queries_shells_cron import (
    get_cron_for_session,
    get_cron_global,
    get_cron_project_rollup,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["cron"])


def _claude_root() -> Path:
    """The root of Claude Code's local storage; project JSONLs live under
    `{root}/projects/{encoded}/{uuid}.jsonl`. Indirected so tests can stub."""
    return settings.claude_base


# ---------------------------------------------------------------------------
# Global
# ---------------------------------------------------------------------------


@router.get("/cron")
def list_cron_global(
    project: Optional[str] = Query(None, description="encoded project name filter"),
    active_only: bool = Query(
        False,
        description="filter to jobs not deleted AND whose 7d TTL has not expired",
    ),
    limit: int = Query(200, ge=1, le=1000),
) -> dict:
    """
    Aggregated cron_jobs across all sessions, joined to sessions + projects.
    Ordered by created_at DESC.
    """
    with sqlite_read() as conn:
        conn.row_factory = sqlite3.Row
        rows = get_cron_global(
            conn,
            project_encoded_name=project,
            active_only=active_only,
            limit=limit,
        )
    return {"jobs": rows, "count": len(rows)}


@router.get("/cron/project-rollup")
def cron_project_rollup() -> dict:
    """Per-project counts: total cron jobs, active jobs (within TTL, undeleted)."""
    with sqlite_read() as conn:
        conn.row_factory = sqlite3.Row
        rows = get_cron_project_rollup(conn)
    return {"projects": rows, "count": len(rows)}


# ---------------------------------------------------------------------------
# Per-session
# ---------------------------------------------------------------------------


@router.get("/sessions/{uuid}/cron")
def list_cron_for_session(
    uuid: str,
    include_fires: bool = Query(
        True,
        description="infer cron fires by matching assistant turns against scheduled times",
    ),
) -> dict:
    """
    Cron jobs for a session, ordered by created_at DESC. When
    include_fires=True, each job is augmented with on-read fire inference
    (confidence-scored, source='jsonl') plus the latest cron-state hook
    snapshot if one exists.
    """
    with sqlite_read() as conn:
        conn.row_factory = sqlite3.Row
        if not conn.execute("SELECT 1 FROM sessions WHERE uuid = ?", (uuid,)).fetchone():
            raise HTTPException(status_code=404, detail="session not found")

        jobs = get_cron_for_session(
            conn,
            uuid,
            include_fires=include_fires,
            claude_projects_dir=_claude_root() if include_fires else None,
        )
    return {"jobs": jobs, "count": len(jobs), "session_uuid": uuid}
