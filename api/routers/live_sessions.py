"""
Live Sessions router - read active session state from ~/.claude_karma/live-sessions/

GET endpoints in this router are strictly read-only — they never delete
state files. Stale-file cleanup is owned by
``services.live_session_store.purge_old_files`` (invoked periodically by
the session reconciler) and by the explicit ``DELETE`` / ``POST /cleanup*``
endpoints below, which route writes through ``live_session_store`` so the
fcntl lock stays uncontested across hook scripts and the API process.

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

import asyncio
import logging
import re
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
from routers.projects import safely_resolve_project
from schemas import (
    LiveSessionsResponse,
    LiveSessionSummary,
    RemoteControlState,
    RemoteControlToggleRequest,
    RemoteControlToggleResult,
    TerminalFocusResult,
)
from services.remote_control import (
    can_send_remote_control,
    read_remote_control_state,
    type_remote_control_command,
)
from services.terminal_focus import can_focus, focus_terminal

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

# STARTING sessions older than this are silently ended (10 minutes)
STARTING_TIMEOUT = 600


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
    # After STARTING_TIMEOUT, silently treat as ended (stuck session)
    if state.state == SessionState.STARTING:
        if state.idle_seconds > STARTING_TIMEOUT:
            return SessionStatus.ENDED
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
    include_remote_control: bool = False,
    projects_dir: Path | None = None,
) -> LiveSessionSummary:
    """Convert LiveSessionState to LiveSessionSummary response schema.

    Args:
        state: The live session state from tracking files
        message_count: Optional message count from session JSONL (for live stats)
        subagent_count: Optional subagent count from session (for live stats)
        slug_override: Optional session slug from JSONL (fallback if not in state)
        include_remote_control: Read Remote Control state from the transcript.
            Off by default — it opens the JSONL, too costly for the 1s-polled
            list endpoints; only the single-session GET needs it.
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
                "duration_ms": getattr(s, "duration_ms", None),
            }
            for agent_id, s in state.subagents.items()
        }

    # Terminal identity (for the "open terminal" button). can_focus reflects
    # whether the *host running the API* has an identifier it could act on.
    terminal_dict = state.terminal.model_dump() if state.terminal else None

    remote_control = None
    can_remote_control = False
    if include_remote_control:
        can_remote_control = can_send_remote_control(terminal_dict)
        remote_control = RemoteControlState(
            **read_remote_control_state(state.transcript_path, state.session_ids, projects_dir)
        )

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
        terminal=terminal_dict,
        can_focus_terminal=can_focus(terminal_dict),
        remote_control=remote_control,
        can_remote_control=can_remote_control,
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
    # Accept either slug or encoded_name; resolve to canonical encoded_name
    # so live-session filtering matches what the indexer wrote. Without this,
    # a URL like /live-sessions/project/claude-karma-1044 (slug form, as
    # the frontend sends it) would never match resolved_project_encoded_name.
    project_encoded_name = safely_resolve_project(project_encoded_name) or project_encoded_name

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

    return state_to_summary(state, include_remote_control=True, projects_dir=config.projects_dir)


def _reject_cross_origin(request: Request, config: Settings) -> None:
    """CSRF guard for state-changing endpoints.

    Browsers always send an ``Origin`` header on cross-site POSTs, so any
    origin outside the CORS allowlist is a foreign web page poking the local
    API. Requests without an Origin (curl, same-host tools) are allowed.
    """
    origin = request.headers.get("origin")
    if origin and origin not in config.cors_origins:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Origin not allowed: {origin}. If this is your karma frontend, "
                "add it to cors_origins (CLAUDE_KARMA_CORS_ORIGINS)."
            ),
        )


@router.post("/{session_id}/focus-terminal", response_model=TerminalFocusResult)
def focus_session_terminal(
    session_id: str,
    request: Request,
    config: Annotated[Settings, Depends(get_settings)],
) -> TerminalFocusResult:
    """Raise the terminal window/pane this session is running in.

    Karma runs locally on the same machine as the tracked terminals, so this
    shells out to OS window managers (tmux / osascript / xdotool / wmctrl).
    The attempt is best-effort: a 200 with ``focused=false`` means we knew the
    method but couldn't complete it (e.g. tool missing). Returns 404 if the
    session isn't tracked, 400 if no terminal identity was captured, 403 for
    cross-origin browser requests.
    """
    _reject_cross_origin(request, config)
    state = load_live_session(session_id)
    if state is None:
        raise HTTPException(
            status_code=404,
            detail=f"Live session not found: {session_id}",
        )

    terminal_dict = state.terminal.model_dump() if state.terminal else None
    if not terminal_dict:
        raise HTTPException(
            status_code=400,
            detail=(
                "No terminal information was captured for this session. "
                "It may predate terminal tracking, or was started without a TTY."
            ),
        )

    result = focus_terminal(terminal_dict)
    return TerminalFocusResult(**result)


# /remote-control is typed into a session at *any* status except these three:
#   WAITING_INPUT — a permission / question / plan dialog is open; the trailing
#                   Enter of the injected command could select an answer.
#   STARTING      — no REPL yet, the keystrokes would be lost.
#   ENDED         — no live process to type into (also caught earlier, with a
#                   resume hint).
# ACTIVE is deliberately allowed: "a tool ran in the last 30s" doesn't mean one
# is running right now, and if one is, Claude Code queues the slash command
# until it finishes. Gating on ACTIVE (and, earlier, IDLE — review #2) made the
# toggle feel dead on exactly the live sessions you'd reach for it on.
_RC_BLOCKED_STATUSES = {
    SessionStatus.WAITING_INPUT,
    SessionStatus.STARTING,
    SessionStatus.ENDED,
}

# Confirm-poll budget. Reads the transcript BEFORE the first sleep (review #17)
# and is hard-bounded (review #3).
_RC_CONFIRM_ATTEMPTS = 6
_RC_CONFIRM_INTERVAL = 0.5
# After typing /remote-control on a session we believe is ON, wait this long
# then re-read the transcript: a fresh "is active" line means it was actually
# OFF and we just turned it on (not "opened the disconnect menu").
_RC_MENU_RENDER_WAIT = 1.0

# Serializes every Remote Control toggle in this process: one keystroke sequence
# into one terminal at a time, no pile-up under repeated clicks (review #3, #8).
_rc_lock = asyncio.Lock()

_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


def _rc_trusted_origin(request: Request, config: Settings) -> None:
    """Stricter CSRF gate for the keystroke-injecting toggle (review #4).

    ``cors_origins`` also trusts :5173/:3000 — any local dev server. Enabling
    Remote Control on the user's live sessions must be reachable only from
    Karma's own dashboard, so this checks ``rc_trusted_origins`` and also
    requires a custom header (which a cross-origin simple request cannot set,
    and setting it forces a CORS preflight the middleware then screens).
    """
    origin = request.headers.get("origin")
    if origin is not None and origin not in config.rc_trusted_origins:
        raise HTTPException(
            status_code=403,
            detail=(
                f"Origin {origin} may not toggle Remote Control — only the Karma "
                "dashboard on this machine can."
            ),
        )
    if request.headers.get("x-karma-rc") != "1":
        raise HTTPException(status_code=403, detail="Missing X-Karma-RC header.")


def _rc_result(op: dict, final: dict, want: str) -> RemoteControlToggleResult:
    confirmed = final["state"] == want
    detail = op["detail"]
    if not confirmed:
        detail += " — the transcript hasn't confirmed the new state yet."
    return RemoteControlToggleResult(
        sent=bool(op["sent"]),
        method=op["method"],
        detail=detail,
        confirmed=confirmed,
        state=final["state"],
        url=final.get("url"),
    )


async def _rc_poll_state(read_state, want: str) -> dict:
    """Read now, then re-read up to _RC_CONFIRM_ATTEMPTS times until ``want``."""
    final = await asyncio.to_thread(read_state)
    for _ in range(_RC_CONFIRM_ATTEMPTS):
        if final["state"] == want:
            return final
        await asyncio.sleep(_RC_CONFIRM_INTERVAL)
        final = await asyncio.to_thread(read_state)
    return final


@router.post("/{session_id}/remote-control", response_model=RemoteControlToggleResult)
async def toggle_session_remote_control(
    session_id: str,
    body: RemoteControlToggleRequest,
    request: Request,
    config: Annotated[Settings, Depends(get_settings)],
) -> RemoteControlToggleResult:
    """Turn Claude Code Remote Control on/off for a live session.

    Claude Code has no API for this — the only lever is the ``/remote-control``
    slash command typed inside the session (tmux / macOS Terminal.app / iTerm2).
    Turning it **on** is one command; turning it **off** types the command and
    then navigates the "Disconnect Remote Control" menu it opens.

    Honest by construction: ``sent=false`` means nothing was typed; ``sent=true,
    confirmed=false`` means keys went but the transcript hasn't caught up.
    404 unknown session, 400 no/unsupported terminal, 403 wrong origin,
    409 session not at its prompt / state unreadable / another toggle running.
    """
    _rc_trusted_origin(request, config)
    if not _SESSION_ID_RE.match(session_id):
        raise HTTPException(status_code=400, detail="Invalid session id.")
    if _rc_lock.locked():
        raise HTTPException(
            status_code=409,
            detail="Another Remote Control toggle is in progress — try again in a moment.",
        )

    async with _rc_lock:
        state = load_live_session(session_id)
        if state is None:
            raise HTTPException(status_code=404, detail=f"Live session not found: {session_id}")

        terminal_dict = state.terminal.model_dump() if state.terminal else None
        if not terminal_dict:
            raise HTTPException(
                status_code=400,
                detail=(
                    "No terminal information was captured for this session. "
                    "It may predate terminal tracking, or was started without a TTY."
                ),
            )
        if not can_send_remote_control(terminal_dict):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Remote Control toggling needs a live tmux / macOS Terminal.app / "
                    "iTerm2 session on the machine running Karma (with its process "
                    "still alive)."
                ),
            )

        status = determine_status(state)
        if status == SessionStatus.ENDED:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Session has ended. Resume it with Remote Control instead: "
                    f"`claude --resume {state.session_id} --remote-control`."
                ),
            )
        if status in _RC_BLOCKED_STATUSES:
            reason = {
                SessionStatus.WAITING_INPUT: "has a prompt open waiting for your answer",
                SessionStatus.STARTING: "is still starting up",
            }.get(status, f"is {status.value}")
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Session {reason} — typing /remote-control now could collide with it. "
                    "Try again once it's ready."
                ),
            )

        def read_state() -> dict:
            return read_remote_control_state(
                state.transcript_path, state.session_ids, config.projects_dir
            )

        current = await asyncio.to_thread(read_state)
        if current["state"] == "unknown":
            raise HTTPException(
                status_code=409,
                detail=(
                    "Karma can't read this session's Remote Control state from its "
                    "transcript, so it won't blind-toggle. Use /remote-control in the "
                    "terminal directly."
                ),
            )
        if current["state"] == body.desired:
            return RemoteControlToggleResult(
                sent=False,
                method="none",
                detail=f"Remote Control is already {body.desired}.",
                confirmed=True,
                state=current["state"],
                url=current.get("url"),
            )

        # Step 1 — type `/remote-control` (turns ON if off; opens the disconnect
        # menu if on).
        typed = await asyncio.to_thread(type_remote_control_command, terminal_dict)
        if not typed["sent"]:
            return RemoteControlToggleResult(
                sent=False,
                method=typed["method"],
                detail=typed["detail"],
                confirmed=False,
                state=current["state"],
                url=current.get("url"),
            )

        if body.desired == "on":
            final = await _rc_poll_state(read_state, "on")
            return _rc_result(typed, final, "on")

        # desired == "off": typing /remote-control opens the "Disconnect Remote
        # Control" menu (RC has no headless off). Karma doesn't navigate it —
        # it raises the terminal and the user picks "Disconnect this session".
        await asyncio.sleep(_RC_MENU_RENDER_WAIT)
        mid = await asyncio.to_thread(read_state)
        if mid["state"] == "off":
            return _rc_result(typed, mid, "off")  # already gone (race) — done
        if (
            mid["state"] == "on"
            and mid.get("at")
            and current.get("at")
            and str(mid["at"]) > str(current["at"])
        ):
            # A NEW "is active" line appeared: the transcript was stale, RC was
            # actually OFF and the command just turned it ON — no menu opened.
            return RemoteControlToggleResult(
                sent=True,
                method=typed["method"],
                detail=(
                    "Remote Control was off — turned it on instead. Click again to "
                    "open the disconnect menu."
                ),
                confirmed=False,
                state="on",
                url=mid.get("url"),
            )

        # The disconnect menu is open — bring the terminal forward and hand off.
        focus = await asyncio.to_thread(focus_terminal, terminal_dict)
        raised = " and brought it to the front" if focus.get("focused") else ""
        return RemoteControlToggleResult(
            sent=True,
            method="menu-open",
            detail=(
                f"Opened the “Disconnect Remote Control” menu in this session's terminal{raised} "
                "— select “Disconnect this session” there."
            ),
            confirmed=False,
            state="on",
            url=current.get("url"),
        )


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
    3. STARTING state AND older than 10 minutes (stuck starting sessions)

    Returns: {"deleted": N, "kept": N, "ghosts_deleted": N, "starting_deleted": N}
    """
    states = await load_all_live_sessions_async()

    deleted = 0
    kept = 0
    ghosts_deleted = 0
    starting_deleted = 0

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
        # Clean up stuck STARTING sessions older than 10 minutes
        # Check raw state BEFORE ghost check — determine_status() maps these
        # to ENDED after STARTING_TIMEOUT, so without this ordering they'd
        # be misclassified as ghosts
        elif state.state == SessionState.STARTING and state.idle_seconds > STARTING_TIMEOUT:
            identifier = state.slug or state.session_id
            if delete_live_session(identifier):
                starting_deleted += 1
                logger.info(
                    f"Cleaned up stuck starting session: {identifier} (idle: {int(state.idle_seconds)}s)"
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
        f"Session cleanup: deleted={deleted}, ghosts={ghosts_deleted}, "
        f"starting={starting_deleted}, kept={kept}"
    )
    return {
        "deleted": deleted,
        "kept": kept,
        "ghosts_deleted": ghosts_deleted,
        "starting_deleted": starting_deleted,
    }


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
