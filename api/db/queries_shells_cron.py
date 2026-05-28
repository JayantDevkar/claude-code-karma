"""
Query helpers for background_shells, shell_polls, cron_jobs, and
cron_state_snapshots.

Mirrors the per-domain pattern established by ticket_queries.py — keeps
domain-scoped query code out of the central queries.py module.

Cron fires are derived on read (NOT persisted): infer_cron_fires() walks
the session JSONL and matches assistant turn timestamps against the cron
expression's scheduled times. The matching window and confidence formula
live here so we can tune them without re-indexing.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Fire-inference tuning. A scheduled time matches an assistant turn if the
# turn timestamp lies within ±FIRE_WINDOW_SECONDS, with confidence scoring
# from 1.0 at 0s offset down to FIRE_CONFIDENCE_FLOOR at the window edge.
# Matches below FIRE_CONFIDENCE_FLOOR are dropped.
FIRE_WINDOW_SECONDS = 60
FIRE_CONFIDENCE_FLOOR = 0.4

# Path under ~/.claude where project subdirs live.
_PROJECTS_SUBDIR = "projects"


# ============================================================================
# Time helpers
# ============================================================================


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp string to a tz-aware datetime."""
    if not ts:
        return None
    if ts.endswith("Z"):
        ts = ts[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {k: row[k] for k in row.keys()}


# ============================================================================
# Background shells
# ============================================================================


def get_shells_for_session(
    conn: sqlite3.Connection,
    session_uuid: str,
    include_polls: bool = True,
) -> List[Dict[str, Any]]:
    """
    Return all background_shells rows for a session, optionally with their
    polls attached as a nested list.

    Ordered by spawned_at DESC.
    """
    shells = [
        _row_to_dict(r)
        for r in conn.execute(
            """
            SELECT * FROM background_shells
            WHERE session_uuid = ?
            ORDER BY spawned_at DESC
            """,
            (session_uuid,),
        )
    ]

    if include_polls and shells:
        shell_ids = [s["id"] for s in shells]
        placeholders = ",".join("?" * len(shell_ids))
        polls_by_shell: Dict[int, List[Dict[str, Any]]] = {sid: [] for sid in shell_ids}
        for r in conn.execute(
            f"""
            SELECT * FROM shell_polls
            WHERE shell_row_id IN ({placeholders})
            ORDER BY polled_at ASC
            """,
            shell_ids,
        ):
            polls_by_shell[r["shell_row_id"]].append(_row_to_dict(r))
        for s in shells:
            s["polls"] = polls_by_shell.get(s["id"], [])

    return shells


def get_shells_global(
    conn: sqlite3.Connection,
    project_encoded_name: Optional[str] = None,
    status: Optional[str] = None,  # 'running' | 'closed' | None
    tool_name: Optional[str] = None,  # 'Bash' | 'Monitor' | None
    limit: int = 200,
    include_polls: bool = True,
) -> List[Dict[str, Any]]:
    """
    Aggregated background_shells view across all sessions, joined to
    sessions + projects for display labels.

    Always-fast path: idx_bg_shells_spawned drives the ORDER BY, sessions PK
    handles the project join, projects PK handles the name join.
    """
    where: List[str] = []
    params: List[Any] = []

    if project_encoded_name:
        where.append("s.project_encoded_name = ?")
        params.append(project_encoded_name)
    if status == "running":
        where.append("bs.terminated_at IS NULL")
    elif status == "closed":
        where.append("bs.terminated_at IS NOT NULL")
    if tool_name:
        where.append("bs.tool_name = ?")
        params.append(tool_name)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    params.append(int(limit))

    shells = [
        _row_to_dict(r)
        for r in conn.execute(
            f"""
            SELECT bs.*,
                   s.project_encoded_name,
                   s.slug              AS session_slug,
                   p.display_name      AS project_display_name
            FROM background_shells bs
            JOIN sessions  s ON s.uuid = bs.session_uuid
            LEFT JOIN projects p ON p.encoded_name = s.project_encoded_name
            {where_sql}
            ORDER BY bs.spawned_at DESC
            LIMIT ?
            """,
            params,
        )
    ]

    if include_polls and shells:
        shell_ids = [s["id"] for s in shells]
        placeholders = ",".join("?" * len(shell_ids))
        polls_by_shell: Dict[int, List[Dict[str, Any]]] = {sid: [] for sid in shell_ids}
        for r in conn.execute(
            f"""
            SELECT * FROM shell_polls
            WHERE shell_row_id IN ({placeholders})
            ORDER BY polled_at ASC
            """,
            shell_ids,
        ):
            polls_by_shell[r["shell_row_id"]].append(_row_to_dict(r))
        for s in shells:
            s["polls"] = polls_by_shell.get(s["id"], [])

    return shells


def get_shells_project_rollup(
    conn: sqlite3.Connection,
) -> List[Dict[str, Any]]:
    """
    Per-project shell counts. Used by the sidebar / overview tiles.
    """
    return [
        _row_to_dict(r)
        for r in conn.execute(
            """
            SELECT s.project_encoded_name              AS project_encoded_name,
                   p.display_name                       AS project_display_name,
                   COUNT(*)                             AS shell_count,
                   SUM(CASE WHEN bs.terminated_at IS NULL THEN 1 ELSE 0 END)
                                                        AS running_count,
                   SUM(bs.total_output_bytes)           AS total_output_bytes
            FROM background_shells bs
            JOIN sessions  s ON s.uuid = bs.session_uuid
            LEFT JOIN projects p ON p.encoded_name = s.project_encoded_name
            GROUP BY s.project_encoded_name
            ORDER BY shell_count DESC
            """
        )
    ]


# ============================================================================
# Cron jobs
# ============================================================================


def get_cron_for_session(
    conn: sqlite3.Connection,
    session_uuid: str,
    include_fires: bool = True,
    claude_projects_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """
    Cron jobs for a session, optionally augmented with on-read fire inference.

    The latest cron-state snapshot (if any) is also attached so the UI can
    show ground-truth live state next to the inferred history.
    """
    jobs = [
        _row_to_dict(r)
        for r in conn.execute(
            """
            SELECT * FROM cron_jobs
            WHERE session_uuid = ?
            ORDER BY created_at DESC
            """,
            (session_uuid,),
        )
    ]
    if not jobs:
        return []

    # Attach latest cron-state snapshot once (CTE-equivalent: single fetch).
    snap = get_latest_cron_state(conn, session_uuid)
    for j in jobs:
        j["latest_state"] = snap  # None when no hook installed

    if include_fires and claude_projects_dir is not None:
        # Resolve session JSONL path via the session row's project_encoded_name.
        row = conn.execute(
            "SELECT project_encoded_name FROM sessions WHERE uuid = ?",
            (session_uuid,),
        ).fetchone()
        if row:
            jsonl_path = (
                claude_projects_dir
                / _PROJECTS_SUBDIR
                / row[0]
                / f"{session_uuid}.jsonl"
            )
            if jsonl_path.exists():
                # Read JSONL once and infer fires for all jobs in a single pass.
                fires_by_job = infer_cron_fires_bulk(jsonl_path, jobs)
                for j in jobs:
                    j["fires"] = fires_by_job.get(j["tool_use_id"], [])
            else:
                for j in jobs:
                    j["fires"] = []
        else:
            for j in jobs:
                j["fires"] = []
    else:
        for j in jobs:
            j["fires"] = []

    return jobs


def get_cron_global(
    conn: sqlite3.Connection,
    project_encoded_name: Optional[str] = None,
    active_only: bool = False,
    limit: int = 200,
    include_fires: bool = True,
    claude_projects_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """
    Aggregated cron jobs across all sessions. `active_only=True` filters to
    jobs that are not explicitly deleted AND whose 7-day TTL has not expired.

    When `include_fires=True` and `claude_projects_dir` is provided, fire
    inference is run per session (grouping jobs to read each JSONL once) and
    the latest cron-state snapshot is attached. Works identically to the
    per-session path — the session's JSONL is already on disk whether the
    session is live or closed.
    """
    where: List[str] = []
    params: List[Any] = []

    if project_encoded_name:
        where.append("s.project_encoded_name = ?")
        params.append(project_encoded_name)
    if active_only:
        where.append("cj.deleted_at IS NULL")
        where.append("cj.ttl_expires_at > ?")
        params.append(_now_utc().isoformat().replace("+00:00", "Z"))

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    params.append(int(limit))

    rows = [
        _row_to_dict(r)
        for r in conn.execute(
            f"""
            SELECT cj.*,
                   s.project_encoded_name,
                   s.slug              AS session_slug,
                   p.display_name      AS project_display_name
            FROM cron_jobs cj
            JOIN sessions  s ON s.uuid = cj.session_uuid
            LEFT JOIN projects p ON p.encoded_name = s.project_encoded_name
            {where_sql}
            ORDER BY cj.created_at DESC
            LIMIT ?
            """,
            params,
        )
    ]

    if not rows:
        return rows

    if include_fires and claude_projects_dir is not None:
        # Group by session so we read each JSONL file exactly once.
        from collections import defaultdict
        by_session: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for j in rows:
            by_session[j["session_uuid"]].append(j)

        for session_uuid, jobs in by_session.items():
            snap = get_latest_cron_state(conn, session_uuid)
            enc = jobs[0].get("project_encoded_name")
            if enc:
                jsonl_path = (
                    claude_projects_dir
                    / _PROJECTS_SUBDIR
                    / enc
                    / f"{session_uuid}.jsonl"
                )
                fires_map = (
                    infer_cron_fires_bulk(jsonl_path, jobs)
                    if jsonl_path.exists()
                    else {}
                )
            else:
                fires_map = {}
            for j in jobs:
                j["fires"] = fires_map.get(j["tool_use_id"], [])
                j["latest_state"] = snap
    else:
        for j in rows:
            j["fires"] = []
            j["latest_state"] = None

    return rows


def get_cron_project_rollup(
    conn: sqlite3.Connection,
) -> List[Dict[str, Any]]:
    """Per-project cron job counts."""
    now_iso = _now_utc().isoformat().replace("+00:00", "Z")
    return [
        _row_to_dict(r)
        for r in conn.execute(
            """
            SELECT s.project_encoded_name                AS project_encoded_name,
                   p.display_name                         AS project_display_name,
                   COUNT(*)                               AS cron_count,
                   SUM(CASE
                       WHEN cj.deleted_at IS NULL AND cj.ttl_expires_at > ?
                       THEN 1 ELSE 0 END)                 AS active_count
            FROM cron_jobs cj
            JOIN sessions  s ON s.uuid = cj.session_uuid
            LEFT JOIN projects p ON p.encoded_name = s.project_encoded_name
            GROUP BY s.project_encoded_name
            ORDER BY cron_count DESC
            """,
            (now_iso,),
        )
    ]


# ============================================================================
# Cron live-state snapshots
# ============================================================================


def get_latest_cron_state(
    conn: sqlite3.Connection,
    session_uuid: str,
) -> Optional[Dict[str, Any]]:
    """
    Return the most recent cron-state snapshot for a session, or None when
    the cron_state_capture.py hook has not been installed (or no relevant
    tool calls have fired yet).
    """
    row = conn.execute(
        """
        SELECT id, session_uuid, captured_at, trigger_event, payload_json
        FROM cron_state_snapshots
        WHERE session_uuid = ?
        ORDER BY captured_at DESC
        LIMIT 1
        """,
        (session_uuid,),
    ).fetchone()
    return _row_to_dict(row) if row else None


# ============================================================================
# On-read cron-fire inference
# ============================================================================


def infer_cron_fires_bulk(
    jsonl_path: Path,
    cron_jobs: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Infer fires for multiple cron jobs by reading the JSONL file exactly once.

    Returns a dict keyed by tool_use_id → list of fire dicts.

    All jobs must belong to the same session (same JSONL file). The single-pass
    approach is O(N_messages + N_jobs * N_scheduled) vs the old per-job approach
    which was O(N_jobs * N_messages).
    """
    result: Dict[str, List[Dict[str, Any]]] = {j["tool_use_id"]: [] for j in cron_jobs}
    if not cron_jobs:
        return result

    try:
        from croniter import croniter
    except ImportError:
        logger.debug("croniter not installed; cron fire inference skipped")
        return result

    now = _now_utc()

    # Build per-job schedule metadata and overall time bounds for the scan.
    job_metas: List[Dict[str, Any]] = []
    scan_start = now  # will be tightened to earliest created_at
    scan_end = datetime(1970, 1, 1, tzinfo=timezone.utc)  # will be max end

    for j in cron_jobs:
        created_at = _parse_iso(j.get("created_at"))
        deleted_at = _parse_iso(j.get("deleted_at"))
        ttl_expires_at = _parse_iso(j.get("ttl_expires_at"))
        cron_expr = j.get("cron_expression")
        if not created_at or not cron_expr:
            continue

        end = min(filter(None, [deleted_at, ttl_expires_at, now]))
        if end <= created_at:
            continue

        try:
            it = croniter(cron_expr, created_at)
        except (ValueError, KeyError):
            continue

        scheduled: List[datetime] = []
        for _ in range(10000):
            nxt = it.get_next(datetime)
            if nxt > end:
                break
            scheduled.append(nxt)
            if not j.get("recurring"):
                break

        if not scheduled:
            continue

        job_metas.append({
            "tool_use_id": j["tool_use_id"],
            "created_at": created_at,
            "end": end,
            "scheduled": scheduled,
        })

        if created_at < scan_start:
            scan_start = created_at
        if end > scan_end:
            scan_end = end

    if not job_metas:
        return result

    # Read JSONL once, collecting assistant turns within the overall bounds.
    assistant_turns: List[Dict[str, Any]] = []
    try:
        with jsonl_path.open("r", encoding="utf-8", errors="replace") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if obj.get("type") != "assistant":
                    continue
                ts = _parse_iso(obj.get("timestamp"))
                if not ts or ts < scan_start or ts > scan_end:
                    continue
                excerpt: Optional[str] = None
                msg = obj.get("message") or {}
                content = msg.get("content")
                if isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("type") == "text":
                            t = c.get("text") or ""
                            if isinstance(t, str) and t.strip():
                                excerpt = t[:500]
                                break
                assistant_turns.append({
                    "uuid": obj.get("uuid"),
                    "ts": ts,
                    "excerpt": excerpt,
                })
    except OSError as e:
        logger.debug("cannot read JSONL for fire inference: %s", e)
        return result

    if not assistant_turns:
        return result

    # Match each job's scheduled times against assistant turns. Claim tracking
    # is per-job so one turn can serve as evidence for different jobs' fires.
    for meta in job_metas:
        claimed_turns: set = set()
        fires: List[Dict[str, Any]] = []
        relevant_turns = [
            t for t in assistant_turns
            if meta["created_at"] <= t["ts"] <= meta["end"]
        ]
        for s_time in meta["scheduled"]:
            best_turn = None
            best_delta: Optional[float] = None
            for turn in relevant_turns:
                if turn["uuid"] in claimed_turns:
                    continue
                delta = abs((turn["ts"] - s_time).total_seconds())
                if delta > FIRE_WINDOW_SECONDS:
                    continue
                if best_delta is None or delta < best_delta:
                    best_delta = delta
                    best_turn = turn
            if best_turn is None or best_delta is None:
                continue
            confidence = 1.0 - (best_delta / FIRE_WINDOW_SECONDS)
            if confidence < FIRE_CONFIDENCE_FLOOR:
                continue
            claimed_turns.add(best_turn["uuid"])
            fires.append({
                "fired_at": best_turn["ts"].isoformat().replace("+00:00", "Z"),
                "triggering_message_uuid": best_turn["uuid"],
                "inference_confidence": round(confidence, 3),
                "inference_source": "jsonl",
                "outcome_excerpt": best_turn["excerpt"],
            })
        result[meta["tool_use_id"]] = fires

    return result


def infer_cron_fires(
    jsonl_path: Path,
    cron_job: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Single-job wrapper around infer_cron_fires_bulk. Kept for test compatibility."""
    # Ensure a stable key exists; tests may omit tool_use_id.
    _sentinel = cron_job.get("tool_use_id") or "__single__"
    job = dict(cron_job)
    job.setdefault("tool_use_id", _sentinel)
    bulk = infer_cron_fires_bulk(jsonl_path, [job])
    return bulk.get(_sentinel, [])
