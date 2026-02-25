"""
Live Sessions router - read active session state from ~/.claude_karma/live-sessions/

These endpoints are designed for frequent polling to display live session status
on the frontend homepage. Cache times are intentionally short (1s) for near-real-time updates.

Session States (written by hooks):
- LIVE: Session actively running (tool execution)
- WAITING: Claude needs user input (AskUserQuestion, permission dialog)
- STOPPED: Agent finished but session still open
- STALE: User has been idle for 60+ seconds
- ENDED: Session terminated

Computed Status (based on state + activity):
- active: LIVE state with recent activity (< 30s idle)
- idle: LIVE state with no recent activity (> 30s but < 5min idle)
- waiting: WAITING state (Claude needs user input)
- stopped: STOPPED state (agent done, session open)
- stale: STALE state (user idle 60s+)
- ended: ENDED state (session terminated or auto-ended on session handoff)

The frontend uses idle_seconds for progressive visual styling (yellow → red as idle time increases).
"""

import logging
import sys
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

# Add models path
api_path = Path(__file__).parent.parent
sys.path.insert(0, str(api_path))

from config import Settings, settings
from http_caching import cacheable
from models.bounded_cache import BoundedCache, BoundedCacheConfig
from models.live_session import (
    LiveSessionState,
    SessionState,
    SessionStatus,
    cleanup_old_session_files,
    delete_live_session,
    load_all_live_sessions_async,
    load_live_session,
)
from models.project import Project
from schemas import LiveSessionsResponse, LiveSessionSummary

logger = logging.getLogger(__name__)

router = APIRouter()

# Cache for session stats: session_id -> (message_count, subagent_count, slug)
# Short TTL (30s) since live sessions change frequently
_session_stats_cache: BoundedCache[tuple[int | None, int | None, str | None]] = BoundedCache(
    BoundedCacheConfig(max_size=200, ttl_seconds=30)
)

# Cache for project session indexes: project_name -> {uuid: Session}
# Slightly longer TTL since project structure changes less often
_project_sessions_cache: BoundedCache[dict] = BoundedCache(
    BoundedCacheConfig(max_size=50, ttl_seconds=60)
)

# Activity threshold (seconds)
IDLE_THRESHOLD = 30  # Consider idle after 30s without activity


# =============================================================================
# Dependencies
# =============================================================================


def get_settings() -> Settings:
    """Dependency to get application settings."""
    return settings


# =============================================================================
# Helper Functions
# =============================================================================


# Stale threshold - when STOPPED becomes stale (60 seconds)
STALE_THRESHOLD = 60


def determine_status(state: LiveSessionState) -> SessionStatus:
    """
    Determine the computed status of a session based on state and activity.

    State → status mapping with idle thresholds:
    - STARTING state → starting (waiting for first prompt)
    - ENDED state → ended
    - STALE state → stale
    - WAITING state → waiting (persists until session ends)
    - STOPPED + idle > 60s → stale (computed)
    - STOPPED state → stopped
    - LIVE + idle > 30s → idle
    - LIVE + idle < 30s → active

    The frontend uses idle_seconds for progressive visual styling.
    """
    # STARTING - session began but no messages yet
    if state.state == SessionState.STARTING:
        return SessionStatus.STARTING

    # ENDED is terminal - session is done
    if state.state == SessionState.ENDED:
        return SessionStatus.ENDED

    # STALE - explicitly set by idle_prompt hook
    if state.state == SessionState.STALE:
        return SessionStatus.STALE

    # WAITING - Claude needs user input (persists until user responds or session ends)
    # Never becomes stale - user must respond
    if state.state == SessionState.WAITING:
        return SessionStatus.WAITING_INPUT

    # STOPPED that's been idle 60+ seconds becomes STALE
    # This handles cases where idle_prompt hook doesn't fire
    if state.state == SessionState.STOPPED:
        if state.idle_seconds > STALE_THRESHOLD:
            return SessionStatus.STALE
        return SessionStatus.STOPPED

    # LIVE state - check for idle threshold
    if state.idle_seconds > IDLE_THRESHOLD:
        return SessionStatus.IDLE

    return SessionStatus.ACTIVE


def state_to_summary(
    state: LiveSessionState,
    message_count: int | None = None,
    subagent_count: int | None = None,
    slug_override: str | None = None,
) -> LiveSessionSummary:
    """Convert LiveSessionState to LiveSessionSummary response schema.

    Args:
        state: The live session state from tracking files
        message_count: Optional message count from session JSONL (for live stats)
        subagent_count: Optional subagent count from session (for live stats)
        slug_override: Optional session slug from JSONL (fallback if not in state)
    """
    status = determine_status(state)

    # Prefer slug from state (tracker-provided), fallback to JSONL-loaded slug
    slug = state.slug or slug_override

    # Convert subagents to dict for serialization
    subagents_dict = None
    if state.subagents:
        subagents_dict = {
            agent_id: {
                "agent_id": s.agent_id,
                "agent_type": s.agent_type,
                "status": s.status.value if hasattr(s.status, "value") else str(s.status),
                "transcript_path": s.transcript_path,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            }
            for agent_id, s in state.subagents.items()
        }

    return LiveSessionSummary(
        session_id=state.session_id,
        state=state.state.value,
        status=status.value,
        cwd=state.cwd,
        project_encoded_name=state.resolved_project_encoded_name,
        started_at=state.started_at,
        updated_at=state.updated_at,
        duration_seconds=state.duration_seconds,
        idle_seconds=state.idle_seconds,
        last_hook=state.last_hook,
        permission_mode=state.permission_mode,
        end_reason=state.end_reason,
        transcript_exists=state.transcript_exists,
        # Session stats (from JSONL - fallback for subagent_count)
        message_count=message_count,
        subagent_count=subagent_count or state.total_subagent_count,
        slug=slug,
        session_ids=state.session_ids,
        # Rich subagent tracking (from hooks - real-time)
        subagents=subagents_dict,
        active_subagent_count=state.active_subagent_count,
        total_subagent_count=state.total_subagent_count,
    )


def batch_load_session_stats(
    states: list[LiveSessionState], config: Settings
) -> dict[str, tuple[int | None, int | None, str | None]]:
    """Batch load session stats with caching.

    Uses two-level caching:
    1. Per-session stats cache (30s TTL)
    2. Project session index cache (60s TTL)

    Groups by project to avoid loading the same project multiple times (fixes N+1 query).

    PERF: Skips expensive JSONL parsing for ENDED sessions — their stats are not needed
    for live display. The frontend falls back to historical session data for ended sessions.
    The hook-provided slug (state.slug) is used instead of loading from JSONL.

    Returns: dict mapping session_id -> (message_count, subagent_count, slug)
    """
    from collections import defaultdict

    results: dict[str, tuple[int | None, int | None, str | None]] = {}
    uncached_by_project: dict[str, list[str]] = defaultdict(list)

    # First pass: check cache, skip ENDED sessions (use hook data only)
    for state in states:
        # ENDED sessions: use hook-provided data, skip expensive JSONL parse.
        # Frontend falls back to historical session data (session.message_count)
        # via `liveSession?.message_count ?? session.message_count` in SessionCard.
        if state.state == SessionState.ENDED:
            results[state.session_id] = (None, state.total_subagent_count, state.slug)
            continue

        if not state.project_encoded_name:
            results[state.session_id] = (None, None, state.slug)
            continue

        cached = _session_stats_cache.get(state.session_id)
        if cached is not None:
            results[state.session_id] = cached
        else:
            uncached_by_project[state.project_encoded_name].append(state.session_id)

    # Second pass: batch load uncached (only non-ENDED sessions reach here)
    for project_name, session_ids in uncached_by_project.items():
        try:
            # Check project sessions cache
            session_index = _project_sessions_cache.get(project_name)
            if session_index is None:
                project = Project.from_encoded_name(
                    project_name,
                    claude_projects_dir=config.projects_dir,
                    skip_path_recovery=True,  # perf: encoded name already known
                )
                sessions = project.list_sessions()
                session_index = {s.uuid: s for s in sessions}
                _project_sessions_cache[project_name] = session_index

            for sid in session_ids:
                if sid in session_index:
                    s = session_index[sid]
                    stats = (s.message_count, s.count_subagents(), s.slug)
                else:
                    stats = (None, None, None)
                results[sid] = stats
                _session_stats_cache[sid] = stats

        except Exception as e:
            logger.debug(f"Could not load sessions for {project_name}: {e}")
            for sid in session_ids:
                stats = (None, None, None)
                results[sid] = stats

    return results


def load_session_stats(
    session_id: str, project_encoded_name: str | None, config: Settings
) -> tuple[int | None, int | None, str | None]:
    """Load session stats from JSONL for live updates.

    Returns:
        Tuple of (message_count, subagent_count, slug) or (None, None, None) if session not found.
    """
    if not project_encoded_name:
        return None, None, None

    try:
        # Find the session JSONL file
        project = Project.from_encoded_name(
            project_encoded_name, claude_projects_dir=config.projects_dir
        )
        sessions = project.list_sessions()

        for session in sessions:
            if session.uuid == session_id:
                # Clear cache to ensure fresh data
                session.clear_cache()
                return (
                    session.message_count,
                    session.count_subagents(),
                    session.slug,
                )
    except Exception as e:
        logger.debug(f"Could not load session stats for {session_id}: {e}")

    return None, None, None


# =============================================================================
# Endpoints
# =============================================================================


@router.get("", response_model=LiveSessionsResponse)
@cacheable(max_age=1, stale_while_revalidate=2, private=True)
async def list_live_sessions(
    request: Request,
    config: Annotated[Settings, Depends(get_settings)],
) -> LiveSessionsResponse:
    """
    List all tracked live sessions with their current state.

    Short cache (1s) for real-time status monitoring.
    Returns all sessions including ended ones.

    Sessions are sorted by updated_at (most recent first).

    Note: This endpoint now loads session stats (including slug from JSONL)
    for proper matching with sessions on the frontend /sessions page.
    """
    states = await load_all_live_sessions_async()

    # Batch load all stats at once (fixes N+1 query)
    stats_map = batch_load_session_stats(states, config)

    sessions: list[LiveSessionSummary] = []
    active_count = 0
    idle_count = 0
    ended_count = 0

    for state in states:
        # Get stats from batch-loaded map
        message_count, subagent_count, slug = stats_map.get(state.session_id, (None, None, None))
        summary = state_to_summary(state, message_count, subagent_count, slug)
        sessions.append(summary)

        # Count by status category
        if summary.status == "ended":
            ended_count += 1
        elif summary.status == "idle":
            idle_count += 1
        else:
            active_count += 1

    # Sort by last activity (most recent first)
    sessions.sort(key=lambda s: s.updated_at, reverse=True)

    return LiveSessionsResponse(
        total=len(sessions),
        active_count=active_count,
        idle_count=idle_count,
        ended_count=ended_count,
        sessions=sessions,
    )


# How long to show ended sessions in live view (5 minutes)
ENDED_DISPLAY_THRESHOLD = 300

# How long to show ended sessions on project page (45 minutes)
PROJECT_ENDED_DISPLAY_THRESHOLD = 2700


@router.get("/active", response_model=list[LiveSessionSummary])
@cacheable(max_age=1, stale_while_revalidate=2, private=True)
async def list_active_sessions(
    request: Request,
    config: Annotated[Settings, Depends(get_settings)],
) -> list[LiveSessionSummary]:
    """
    List sessions for the live view.

    Includes:
    - All LIVE, WAITING, STOPPED, STALE sessions
    - ENDED sessions for 5 minutes after ending (then filtered out)

    Frontend uses idle_seconds for progressive visual styling (yellow → red).
    """
    states = await load_all_live_sessions_async()

    # Batch load all stats at once (fixes N+1 query)
    stats_map = batch_load_session_stats(states, config)

    active_sessions: list[LiveSessionSummary] = []

    for state in states:
        status = determine_status(state)

        # Get stats from batch-loaded map
        message_count, subagent_count, slug = stats_map.get(state.session_id, (None, None, None))

        # Skip ghost sessions (ended with no transcript)
        if status == SessionStatus.ENDED and not state.transcript_exists:
            continue

        # Include ended sessions for 5 minutes, then filter them out
        if status == SessionStatus.ENDED:
            if state.idle_seconds <= ENDED_DISPLAY_THRESHOLD:
                active_sessions.append(state_to_summary(state, message_count, subagent_count, slug))
        else:
            active_sessions.append(state_to_summary(state, message_count, subagent_count, slug))

    # Sort by last activity (most recent first)
    active_sessions.sort(key=lambda s: s.updated_at, reverse=True)

    return active_sessions


@router.get("/project/{project_encoded_name}", response_model=list[LiveSessionSummary])
@cacheable(max_age=1, stale_while_revalidate=2, private=True)
async def list_project_live_sessions(
    project_encoded_name: str,
    request: Request,
    config: Annotated[Settings, Depends(get_settings)],
) -> list[LiveSessionSummary]:
    """
    List live sessions for a specific project with session stats.

    Includes:
    - All LIVE, WAITING, STOPPED, STALE sessions for the project
    - ENDED sessions for 45 minutes after ending (then filtered out)

    This endpoint includes session stats (message_count, subagent_count, slug)
    loaded from the session JSONL files for real-time updates on project page.
    """
    states = await load_all_live_sessions_async()

    # Filter by project using resolved name (handles submodule→parent mapping)
    project_states = [
        state for state in states if state.resolved_project_encoded_name == project_encoded_name
    ]

    # Batch load all stats at once (fixes N+1 query)
    stats_map = batch_load_session_stats(project_states, config)

    project_sessions: list[LiveSessionSummary] = []

    for state in project_states:
        status = determine_status(state)

        # Get stats from batch-loaded map
        message_count, subagent_count, slug = stats_map.get(state.session_id, (None, None, None))

        # Skip ghost sessions (ended with no transcript)
        if status == SessionStatus.ENDED and not state.transcript_exists:
            continue

        # Include ended sessions for 45 minutes, then filter them out
        if status == SessionStatus.ENDED:
            if state.idle_seconds <= PROJECT_ENDED_DISPLAY_THRESHOLD:
                project_sessions.append(
                    state_to_summary(state, message_count, subagent_count, slug)
                )
        else:
            project_sessions.append(state_to_summary(state, message_count, subagent_count, slug))

    # Sort by last activity (most recent first)
    project_sessions.sort(key=lambda s: s.updated_at, reverse=True)

    return project_sessions


@router.get("/{session_id}", response_model=LiveSessionSummary)
@cacheable(max_age=5, stale_while_revalidate=10, private=True)
def get_live_session(
    session_id: str,
    request: Request,
    config: Annotated[Settings, Depends(get_settings)],
) -> LiveSessionSummary:
    """
    Get state for a specific live session.

    Returns 404 if session not being tracked.
    """
    state = load_live_session(session_id)

    if state is None:
        raise HTTPException(
            status_code=404,
            detail=f"Live session not found: {session_id}",
        )

    return state_to_summary(state)


# Threshold for allowing cleanup (5 minutes)
CLEANUP_THRESHOLD = 300


@router.delete("/{session_id}", status_code=204)
def cleanup_live_session(
    session_id: str,
    request: Request,
    config: Annotated[Settings, Depends(get_settings)],
) -> None:
    """
    Remove a session state file.

    Can be called by frontend or scheduled cleanup to remove sessions that
    ended or have been idle for 5+ minutes.

    Only removes sessions that are ended or idle for 5+ minutes.
    """
    state = load_live_session(session_id)

    if state is None:
        raise HTTPException(
            status_code=404,
            detail=f"Live session not found: {session_id}",
        )

    status = determine_status(state)

    # Allow deletion if ended OR idle for 5+ minutes
    can_delete = status == SessionStatus.ENDED or state.idle_seconds > CLEANUP_THRESHOLD

    if not can_delete:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete active session (status: {status.value}, "
            f"idle: {int(state.idle_seconds)}s). "
            f"Only ended or idle (5+ min) sessions can be deleted.",
        )

    success = delete_live_session(session_id)
    if not success:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete session file: {session_id}",
        )

    logger.info(f"Cleaned up live session: {session_id}")


OLD_SESSION_THRESHOLD = 4500  # 75 minutes in seconds


# Ghost session threshold - ENDED sessions with no transcript older than this are auto-deleted
GHOST_SESSION_THRESHOLD = 300  # 5 minutes


@router.post("/cleanup-old", status_code=200)
async def cleanup_stuck_sessions(
    request: Request,
    config: Annotated[Settings, Depends(get_settings)],
) -> dict:
    """
    Delete live session files that are:
    1. IDLE status AND older than 75 minutes (sessions in LIVE state but inactive)
    2. ENDED with no transcript AND older than 5 minutes (ghost sessions)

    Returns: {"deleted": N, "kept": N, "ghosts_deleted": N}
    """
    states = await load_all_live_sessions_async()

    deleted = 0
    kept = 0
    ghosts_deleted = 0

    for state in states:
        status = determine_status(state)

        # Clean up idle sessions whose status hasn't changed in 75+ minutes
        # idle_seconds = time since last hook update, so this confirms
        # the session has been stuck in idle state for the full threshold
        if status == SessionStatus.IDLE and state.idle_seconds > OLD_SESSION_THRESHOLD:
            identifier = state.slug or state.session_id
            if delete_live_session(identifier):
                deleted += 1
                logger.info(
                    f"Cleaned up idle session: {identifier} (status: {status.value}, idle: {int(state.idle_seconds)}s)"
                )
            else:
                kept += 1
        # Clean up ghost sessions (ENDED, no transcript, older than 5 minutes)
        elif (
            status == SessionStatus.ENDED
            and not state.transcript_exists
            and state.idle_seconds > GHOST_SESSION_THRESHOLD
        ):
            identifier = state.slug or state.session_id
            if delete_live_session(identifier):
                ghosts_deleted += 1
                logger.info(f"Cleaned up ghost session: {identifier} (no transcript, ended)")
            else:
                kept += 1
        else:
            kept += 1

    logger.info(
        f"Session cleanup: deleted={deleted}, ghosts={ghosts_deleted}, kept={kept}"
    )
    return {"deleted": deleted, "kept": kept, "ghosts_deleted": ghosts_deleted}


@router.post("/cleanup", status_code=200)
def cleanup_duplicate_sessions(
    request: Request,
    config: Annotated[Settings, Depends(get_settings)],
) -> dict:
    """
    Clean up duplicate and old session state files.

    This endpoint removes:
    - Session_id-based files that have been superseded by slug-based files
    - Duplicate slug files (keeps the most recently updated one)

    Use this after migrating to slug-based tracking to clean up old files.
    """
    result = cleanup_old_session_files()
    logger.info(
        f"Cleaned up live sessions: deleted={result['deleted']}, "
        f"kept={result['kept']}, errors={result['errors']}"
    )
    return result
