"""
Sessions router - session details, file activity, subagents, tools.

Phase 3: HTTP caching with conditional request support.
"""

import heapq
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from command_helpers import is_plugin_skill
from schemas import SessionSummary
from services.desktop_sessions import get_session_source


def _skill_plugin_name(skill_name: str) -> str | None:
    """Extract plugin name from a skill name (full or short form)."""
    if ":" in skill_name:
        return skill_name.split(":")[0]
    if is_plugin_skill(skill_name):
        return skill_name  # Short-form: plugin name IS the skill name
    return None


def _enrich_chain_titles_by_slug(summaries: list[SessionSummary]) -> None:
    """Propagate titles across sessions sharing the same slug+project (O(n))."""
    # Build slug+project → first title found
    slug_titles: dict[tuple[str, str], str] = {}
    for s in summaries:
        if s.slug and s.project_encoded_name and s.session_titles:
            key = (s.project_encoded_name, s.slug)
            if key not in slug_titles:
                slug_titles[key] = s.session_titles[0]
    # Propagate to untitled siblings
    for s in summaries:
        if s.slug and s.project_encoded_name and not s.session_titles:
            title = slug_titles.get((s.project_encoded_name, s.slug))
            if title:
                s.chain_title = title


# Import unified filter classes from services
from services.session_filter import (
    SearchScope,
    SessionFilter,
    SessionMetadata,
    SessionStatus,
    determine_session_status,
)
from services.session_title_cache import title_cache

logger = logging.getLogger(__name__)

# Add models and api to path
api_path = Path(__file__).parent.parent
models_path = api_path.parent.parent
sys.path.insert(0, str(api_path))
sys.path.insert(0, str(models_path))

# Phase 2: Single-pass data collection
from collectors import (
    collect_session_data,
    collect_subagent_info,
)
from config import FILE_TOOL_MAPPINGS, settings
from http_caching import (
    build_cache_headers,
    cacheable,
    check_conditional_request,
    get_file_cache_info,
)
from models import Session, ToolUseBlock
from models.plan import load_plan
from models.project import get_cached_jsonl_count

# Phase 4: Parallel processing
from parallel import process_subagents_parallel
from schemas import (
    AllSessionsResponse,
    CommandUsage,
    CompactionSummary,
    ContinuationSessionInfo,
    FileActivity,
    InitialPrompt,
    PlanDetail,
    ProjectFilterOption,
    SessionDetail,
    SessionWithContext,
    SkillUsage,
    StatusFilterOption,
    SubagentSummary,
    TaskSchema,
    TodoItemSchema,
)
from services.session_lookup import (
    _is_valid_session_filename,
    find_session,
    find_session_by_message_uuid,
    find_session_with_project,
)
from utils import (
    collect_tool_results,
    compute_project_slug,
    get_initial_prompt,
    get_initial_prompt_from_index,
    is_encoded_project_dir,
    normalize_timezone,
    parse_timestamp_range,
)

router = APIRouter()


def detect_command_source(
    name: str, project_encoded_name: str | None = None
) -> tuple[str, str | None]:
    """Detect the source of a command: builtin, plugin, project, user, or unknown."""
    from command_helpers import BUILTIN_CLI_COMMANDS
    from config import settings

    # Built-in CLI commands (/exit, /compact, /model, etc.)
    if name in BUILTIN_CLI_COMMANDS:
        return ("builtin", None)

    # Plugin commands contain ':'
    if ":" in name:
        plugin_name = name.split(":")[0]
        return ("plugin", plugin_name)

    # Check project-level commands
    if project_encoded_name:
        try:
            from models import Project

            proj = Project.from_encoded_name(project_encoded_name, skip_path_recovery=True)
            project_path = proj.path
        except Exception:
            project_path = None
        if project_path:
            project_cmd = Path(project_path) / ".claude" / "commands" / f"{name}.md"
            if project_cmd.is_file():
                return ("project", None)

    # Check user-level commands
    user_cmd = settings.commands_dir / f"{name}.md"
    if user_cmd.is_file():
        return ("user", None)

    return ("unknown", None)


# =============================================================================
# All Sessions Listing Endpoint (Global Sessions Page)
# =============================================================================


def _get_project_name(path: str) -> str:
    """Extract human-readable project name from path (last path component)."""
    return Path(path).name


def _count_subagents_fast(project_dir: Path, session_uuid: str) -> int:
    """
    Count subagents using filesystem glob without loading Session.

    This is much faster than Session.count_subagents() which may parse JSONL.

    Args:
        project_dir: Path to project directory (e.g., ~/.claude/projects/-Users-...)
        session_uuid: Session UUID

    Returns:
        Number of subagent JSONL files
    """
    subagents_dir = project_dir / session_uuid / "subagents"
    if not subagents_dir.exists():
        return 0
    return len(list(subagents_dir.glob("agent-*.jsonl")))


def _list_all_projects_with_sessions_optimized() -> tuple[
    list[SessionMetadata], list[ProjectFilterOption]
]:
    """
    List all projects with their sessions using optimized index-first loading.

    Phase 5 Optimization: Uses sessions-index.json when available to avoid
    loading full Session objects. Falls back to Session loading only when
    index is unavailable.

    Returns:
        Tuple of (all_session_metadata, project_options) where:
        - all_session_metadata: List of SessionMetadata (lightweight)
        - project_options: List of ProjectFilterOption for filter dropdowns
    """
    from models import Project

    projects_dir = settings.projects_dir
    if not projects_dir.exists():
        return [], []

    all_sessions: list[SessionMetadata] = []
    project_options: list[ProjectFilterOption] = []

    for encoded_dir in projects_dir.iterdir():
        if not encoded_dir.is_dir() or not is_encoded_project_dir(encoded_dir.name):
            continue
        try:
            # Use skip_path_recovery=True for performance - we'll get accurate
            # path from session index or JSONL if needed
            project = Project.from_encoded_name(encoded_dir.name, skip_path_recovery=True)

            # Try to use session index first (Phase 1 optimization)
            # But detect stale indexes by comparing to actual JSONL file count
            index = project.load_sessions_index()
            jsonl_count = get_cached_jsonl_count(project.project_dir)
            index_is_fresh = (
                index
                and index.entries
                # Index is considered fresh if it has at least 90% of JSONL files
                # (some JSONL files may be empty sessions filtered out by the index)
                and len(index.entries) >= jsonl_count * 0.9
            )
            if index_is_fresh:
                # Fast path: use pre-computed metadata from index
                valid_entries = [e for e in index.entries if e.message_count > 0]
                if valid_entries:
                    # Get accurate project path from first index entry
                    project_path = valid_entries[0].project_path or project.path
                    project_options.append(
                        ProjectFilterOption(
                            encoded_name=encoded_dir.name,
                            path=project_path,
                            name=Path(project_path).name,
                            slug=compute_project_slug(encoded_dir.name, project_path),
                            display_name=Path(project_path).name,
                            session_count=len(valid_entries),
                        )
                    )
                    for entry in valid_entries:
                        # Get initial_prompt from index, but if index shows "No prompt"
                        # (which is often stale), try loading from the actual session
                        initial_prompt = get_initial_prompt_from_index(entry.first_prompt)
                        if initial_prompt is None and entry.first_prompt == "No prompt":
                            # Index may be stale - try loading actual prompt from session
                            try:
                                jsonl_path = project.project_dir / f"{entry.session_id}.jsonl"
                                if jsonl_path.exists():
                                    session = Session.from_path(jsonl_path)
                                    initial_prompt = get_initial_prompt(session, max_length=500)
                            except Exception:
                                pass  # Keep None on error
                        all_sessions.append(
                            SessionMetadata(
                                uuid=entry.session_id,
                                encoded_name=encoded_dir.name,
                                project_path=project_path,
                                message_count=entry.message_count,
                                start_time=entry.created,
                                end_time=entry.modified,
                                # Note: sessions-index.json doesn't have slug field.
                                # entry.summary is the session title, NOT the slug.
                                # Set to None so frontend falls back to UUID prefix.
                                slug=None,
                                initial_prompt=initial_prompt,
                                git_branch=entry.git_branch,
                                # Use summary for display title
                                title=entry.summary,
                            )
                        )
            else:
                # Fallback: load sessions the traditional way
                # (index missing, empty, or stale)
                sessions = project.list_sessions()
                valid_sessions = [s for s in sessions if s.message_count > 0]

                if valid_sessions:
                    project_options.append(
                        ProjectFilterOption(
                            encoded_name=encoded_dir.name,
                            path=project.path,
                            name=Path(project.path).name,
                            slug=compute_project_slug(encoded_dir.name, project.path),
                            display_name=Path(project.path).name,
                            session_count=len(valid_sessions),
                        )
                    )
                    for session in valid_sessions:
                        all_sessions.append(
                            SessionMetadata(
                                uuid=session.uuid,
                                encoded_name=encoded_dir.name,
                                project_path=project.path,
                                message_count=session.message_count,
                                start_time=session.start_time,
                                end_time=session.end_time,
                                slug=session.slug,
                                initial_prompt=get_initial_prompt(session),
                                git_branch=next(iter(session.get_git_branches()), None),
                                # Use first session_title for display if available
                                title=session.session_titles[0] if session.session_titles else None,
                                _session=session,
                            )
                        )
        except Exception:
            continue

    # Enrich session metadata with cached titles and slugs
    # This populates session_titles for efficient server-side search
    # without N+1 JSONL loading in matches_metadata()
    for meta in all_sessions:
        cached = title_cache.get_entry(meta.encoded_name, meta.uuid)
        if cached:
            meta.session_titles = cached.titles
            if cached.slug and not meta.slug:
                meta.slug = cached.slug

    return all_sessions, project_options


@router.get("/all", response_model=AllSessionsResponse)
def get_all_sessions(
    request: Request,
    response: Response,
    search: Optional[str] = None,
    project: Optional[str] = None,
    branch: Optional[str] = None,
    scope: SearchScope = SearchScope.BOTH,
    status: SessionStatus = SessionStatus.ALL,
    start_ts: Optional[int] = None,
    end_ts: Optional[int] = None,
    page: int = 1,
    per_page: int = 50,
) -> AllSessionsResponse:
    """
    List all sessions across all projects with optional filtering.

    This endpoint powers the global /sessions page, providing sessions
    with full project context for display and filtering.

    Phase 9: SQLite-first with automatic fallback to JSONL-based loading.
    SQLite path handles filtering, sorting, pagination, and status counting
    entirely in SQL — typically 10-40x faster than the JSONL path.

    Args:
        search: Optional search term to filter by slug, initial_prompt, or project path
        project: Optional project encoded_name to filter by
        branch: Optional branch name to filter by (requires project filter)
        scope: Search scope - titles, prompts, or both (default: both)
        status: Status filter - all, active, completed, error (default: all)
        start_ts: Filter sessions starting after this Unix timestamp (milliseconds)
        end_ts: Filter sessions starting before this Unix timestamp (milliseconds)
        page: Page number (1-indexed, default 1)
        per_page: Items per page (default 50)

    Returns:
        AllSessionsResponse with sessions, project filter options, and status options
    """
    # Parse date range timestamps (shared by both paths)
    start_dt, end_dt = parse_timestamp_range(start_ts, end_ts)

    # Resolve project slug to encoded_name if needed
    if project and not is_encoded_project_dir(project):
        try:
            from db.connection import create_read_connection
            from db.queries import query_project_by_slug

            conn = create_read_connection()
            try:
                row = query_project_by_slug(conn, project)
                if row:
                    project = row["encoded_name"]
            finally:
                conn.close()
        except Exception:
            pass

    # Compute offset from page/per_page
    per_page = max(1, min(per_page, 200))
    offset = (page - 1) * per_page
    limit = per_page

    result = None

    # Try SQLite path first
    if settings.use_sqlite:
        try:
            from db.indexer import is_db_ready

            if is_db_ready():
                result = _get_all_sessions_sqlite(
                    search=search,
                    project=project,
                    branch=branch,
                    scope=scope,
                    status=status,
                    start_dt=start_dt,
                    end_dt=end_dt,
                    start_ts=start_ts,
                    end_ts=end_ts,
                    limit=limit,
                    offset=offset,
                )
        except sqlite3.Error as e:
            logger.warning("SQLite query failed, falling back to JSONL: %s", e)

    # Fallback: JSONL-based loading (original Phase 5 code)
    if result is None:
        result = _get_all_sessions_jsonl(
            search=search,
            project=project,
            branch=branch,
            scope=scope,
            status=status,
            start_dt=start_dt,
            end_dt=end_dt,
            start_ts=start_ts,
            end_ts=end_ts,
            limit=limit,
            offset=offset,
        )

    # Cache Control Logic
    # Disable caching if any filter is active (search results should be fresh)
    has_filters = any([search, project, branch, status != SessionStatus.ALL, start_ts, end_ts])

    if has_filters:
        # No cache for filtered views
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
    else:
        # Cache default view for 60s (private)
        # Note: We manually apply headers instead of using @cacheable to support conditional logic
        headers = build_cache_headers(
            max_age=60,
            stale_while_revalidate=120,
            private=True,
            etag=None,  # Skip expensive ETag calc for now
        )
        response.headers.update(headers)

    return result


def _get_all_sessions_sqlite(
    search,
    project,
    branch,
    scope,
    status,
    start_dt,
    end_dt,
    start_ts,
    end_ts,
    limit,
    offset,
) -> AllSessionsResponse:
    """
    SQLite-backed implementation of get_all_sessions.

    Handles filtering, sorting, pagination, and status counting
    entirely in SQL. Typically 10-40x faster than the JSONL path.
    """
    from db.connection import create_read_connection
    from db.queries import query_all_sessions

    conn = create_read_connection()
    try:
        result = query_all_sessions(
            conn,
            search=search,
            project=project,
            branch=branch,
            scope=scope.value if scope else "both",
            status=status.value if status else "all",
            start_dt=start_dt,
            end_dt=end_dt,
            limit=limit,
            offset=offset,
        )

        total = result["total"]
        page = (offset // limit) + 1 if limit > 0 else 1
        total_pages = (total + limit - 1) // limit if limit > 0 else 1

        # Build slug lookup from project_options
        slug_lookup = {opt["encoded_name"]: opt.get("slug") for opt in result["project_options"]}

        # Convert SQL rows to SessionWithContext
        sessions_with_context = []
        for row in result["sessions"]:
            start_time = _parse_iso(row.get("start_time"))
            end_time = _parse_iso(row.get("end_time"))

            session_context = SessionWithContext(
                uuid=row["uuid"],
                slug=row.get("slug"),
                project_encoded_name=row["project_encoded_name"],
                project_path=row.get("project_path") or "",
                project_name=_get_project_name(row.get("project_path") or ""),
                project_slug=slug_lookup.get(row["project_encoded_name"]),
                message_count=row.get("message_count", 0),
                start_time=start_time,
                end_time=end_time,
                duration_seconds=row.get("duration_seconds"),
                models_used=row.get("models_used", []),
                subagent_count=row.get("subagent_count", 0),
                has_todos=False,
                initial_prompt=row.get("initial_prompt"),
                git_branches=row.get("git_branches", []),
                session_titles=row.get("session_titles", [])
                or title_cache.get_titles(row["project_encoded_name"], row["uuid"])
                or [],
                session_source=get_session_source(row["uuid"]),
            )
            sessions_with_context.append(session_context)

        _enrich_chain_titles_by_slug(sessions_with_context)

        # Build project options
        project_options = [ProjectFilterOption(**opt) for opt in result["project_options"]]

        # Build status options
        sc = result["status_counts"]
        total_before_status = sum(sc.values())
        status_options = [
            StatusFilterOption(value="all", label="All", count=total_before_status),
            StatusFilterOption(value="active", label="Active", count=sc.get("active", 0)),
            StatusFilterOption(value="completed", label="Completed", count=sc.get("completed", 0)),
            StatusFilterOption(value="error", label="Error", count=sc.get("error", 0)),
        ]

        # Build applied_filters
        applied_filters = {}
        if search:
            applied_filters["search"] = search
        if scope != SearchScope.BOTH:
            applied_filters["scope"] = scope.value
        if project:
            applied_filters["project"] = project
        if branch:
            applied_filters["branch"] = branch
        if status != SessionStatus.ALL:
            applied_filters["status"] = status.value
        if start_ts:
            applied_filters["start_ts"] = start_ts
        if end_ts:
            applied_filters["end_ts"] = end_ts

        return AllSessionsResponse(
            sessions=sessions_with_context,
            total=total,
            page=page,
            per_page=limit,
            total_pages=total_pages,
            projects=project_options,
            status_options=status_options,
            applied_filters=applied_filters,
        )
    finally:
        conn.close()


def _get_all_sessions_jsonl(
    search,
    project,
    branch,
    scope,
    status,
    start_dt,
    end_dt,
    start_ts,
    end_ts,
    limit,
    offset,
) -> AllSessionsResponse:
    """
    Original JSONL-based implementation of get_all_sessions.

    Used as fallback when SQLite is unavailable or disabled.
    """
    all_sessions, project_options = _list_all_projects_with_sessions_optimized()
    project_options.sort(key=lambda p: p.session_count, reverse=True)

    search_lower = search.lower() if search else None
    status_counts = {"active": 0, "completed": 0, "error": 0}
    filtered_sessions = []

    filter_without_status = SessionFilter(
        search=search_lower,
        search_scope=scope,
        status=SessionStatus.ALL,
        date_from=start_dt,
        date_to=end_dt,
        project_encoded_name=project,
        branch=branch,
    )
    filter_without_status._search_lower = search_lower

    for meta in all_sessions:
        if filter_without_status.matches_metadata(meta):
            session_status = determine_session_status(meta)
            if session_status in status_counts:
                status_counts[session_status] += 1
            if status == SessionStatus.ALL or session_status == status.value:
                filtered_sessions.append(meta)

    total = len(filtered_sessions)
    page = (offset // limit) + 1 if limit > 0 else 1
    total_pages = (total + limit - 1) // limit if limit > 0 else 1

    needed = offset + limit
    if needed < total and needed < total // 2:
        top_sessions = heapq.nlargest(
            needed,
            filtered_sessions,
            key=lambda m: normalize_timezone(m.start_time),
        )
        paginated_sessions = top_sessions[offset:]
    else:
        filtered_sessions.sort(
            key=lambda m: normalize_timezone(m.start_time),
            reverse=True,
        )
        paginated_sessions = filtered_sessions[offset : offset + limit]

    # Build slug lookup from project_options
    jsonl_slug_lookup = {
        opt.encoded_name: opt.slug for opt in project_options if hasattr(opt, "slug") and opt.slug
    }

    sessions_with_context = []
    for meta in paginated_sessions:
        duration_seconds = None
        if meta.start_time and meta.end_time:
            duration_seconds = (meta.end_time - meta.start_time).total_seconds()

        slug = meta.slug
        session_titles = (
            list(meta.session_titles)
            if meta.session_titles
            else ([meta.title] if meta.title else [])
        )
        models_used: list[str] = []
        subagent_count = 0

        project_dir = settings.projects_dir / meta.encoded_name
        subagent_count = _count_subagents_fast(project_dir, meta.uuid)

        if meta._session is not None:
            try:
                loaded_session = meta._session
                if slug is None:
                    slug = loaded_session.slug
                if loaded_session.session_titles:
                    session_titles = loaded_session.session_titles
                models_used = list(loaded_session.get_models_used())
            except Exception:
                pass

        session_context = SessionWithContext(
            uuid=meta.uuid,
            slug=slug,
            project_encoded_name=meta.encoded_name,
            project_path=meta.project_path,
            project_name=_get_project_name(meta.project_path),
            project_slug=jsonl_slug_lookup.get(meta.encoded_name),
            message_count=meta.message_count,
            start_time=meta.start_time,
            end_time=meta.end_time,
            duration_seconds=duration_seconds,
            models_used=models_used,
            subagent_count=subagent_count,
            has_todos=False,
            initial_prompt=meta.initial_prompt,
            git_branches=[meta.git_branch] if meta.git_branch else [],
            session_titles=session_titles,
            session_source=get_session_source(meta.uuid),
        )
        sessions_with_context.append(session_context)

    _enrich_chain_titles_by_slug(sessions_with_context)

    total_before_status = sum(status_counts.values())
    status_options = [
        StatusFilterOption(value="all", label="All", count=total_before_status),
        StatusFilterOption(value="active", label="Active", count=status_counts["active"]),
        StatusFilterOption(value="completed", label="Completed", count=status_counts["completed"]),
        StatusFilterOption(value="error", label="Error", count=status_counts["error"]),
    ]

    applied_filters = {}
    if search:
        applied_filters["search"] = search
    if scope != SearchScope.BOTH:
        applied_filters["scope"] = scope.value
    if project:
        applied_filters["project"] = project
    if branch:
        applied_filters["branch"] = branch
    if status != SessionStatus.ALL:
        applied_filters["status"] = status.value
    if start_ts:
        applied_filters["start_ts"] = start_ts
    if end_ts:
        applied_filters["end_ts"] = end_ts

    return AllSessionsResponse(
        sessions=sessions_with_context,
        total=total,
        page=page,
        per_page=limit,
        total_pages=total_pages,
        projects=project_options,
        status_options=status_options,
        applied_filters=applied_filters,
    )


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO 8601 datetime string, returning None on failure."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


@router.get("/by-message/{message_uuid}")
def get_session_by_message_uuid(message_uuid: str) -> ContinuationSessionInfo:
    """
    Find a session that contains a message with the given UUID.

    Used to link continuation marker sessions to their continuation sessions.
    The leaf_uuid from SessionTitleMessage can be used to find the session where
    the conversation continued.

    Args:
        message_uuid: The UUID of a message to search for

    Returns:
        ContinuationSessionInfo with session UUID, project encoded name, and slug

    Raises:
        HTTPException: 404 if no session contains the given message UUID
    """
    # SQLite fast path
    try:
        from db.connection import sqlite_read
        from db.queries import query_session_by_message_uuid

        with sqlite_read() as conn:
            if conn is not None:
                row = query_session_by_message_uuid(conn, message_uuid)
                if row:
                    return ContinuationSessionInfo(
                        session_uuid=row["session_uuid"],
                        project_encoded_name=row["project_encoded_name"],
                        slug=row["slug"],
                    )
    except Exception:
        pass

    # JSONL fallback
    result = find_session_by_message_uuid(message_uuid)
    if not result:
        raise HTTPException(
            status_code=404,
            detail=f"No session found containing message with UUID: {message_uuid}",
        )

    return ContinuationSessionInfo(
        session_uuid=result.session.uuid,
        project_encoded_name=result.project_encoded_name,
        slug=result.session.slug,
    )


@router.get("/continuation/{session_uuid}")
def get_continuation_session(session_uuid: str) -> ContinuationSessionInfo:
    """
    Find the continuation session for a given continuation marker session.

    Searches for a session with the same slug that has actual conversation
    (not just file snapshots). Falls back to finding any session with the
    same slug that started after this session.

    Args:
        session_uuid: The UUID of the continuation marker session

    Returns:
        ContinuationSessionInfo with session UUID, project encoded name, and slug

    Raises:
        HTTPException: 404 if no continuation session found
    """
    # SQLite fast path
    try:
        from db.connection import sqlite_read
        from db.queries import query_continuation_session, query_source_session

        with sqlite_read() as conn:
            if conn is not None:
                source = query_source_session(conn, session_uuid)
                if source:
                    row = query_continuation_session(
                        conn,
                        project=source["project_encoded_name"],
                        source_uuid=session_uuid,
                        slug=source["slug"],
                        source_end_time=source["end_time"],
                    )
                    if row:
                        return ContinuationSessionInfo(
                            session_uuid=row["uuid"],
                            project_encoded_name=row["project_encoded_name"],
                            slug=row["slug"],
                        )
    except Exception:
        pass

    # JSONL fallback
    source_result = find_session_with_project(session_uuid)
    if not source_result:
        raise HTTPException(status_code=404, detail="Session not found")

    source_session = source_result.session
    project_encoded_name = source_result.project_encoded_name
    source_slug = source_session.slug
    source_end_time = source_session.end_time

    # Get the project directory
    projects_dir = settings.projects_dir
    project_dir = projects_dir / project_encoded_name

    if not project_dir.exists():
        raise HTTPException(status_code=404, detail="Project not found")

    # Search for continuation session with same slug
    candidates = []
    for jsonl_path in project_dir.glob("*.jsonl"):
        if not _is_valid_session_filename(jsonl_path):
            continue
        # Skip the source session itself
        if jsonl_path.stem == session_uuid:
            continue

        try:
            candidate = Session.from_path(jsonl_path)

            # Skip if it's also a continuation marker (no real messages)
            if candidate.is_continuation_marker:
                continue

            # Match by slug if available
            if source_slug and candidate.slug == source_slug:
                candidates.append(candidate)
            # Or find sessions that started around when this one ended
            elif source_end_time and candidate.start_time:
                # If candidate started within 1 minute of source ending, likely continuation
                time_diff = abs((candidate.start_time - source_end_time).total_seconds())
                if time_diff < 60:
                    candidates.append(candidate)

        except Exception:
            continue

    if not candidates:
        raise HTTPException(
            status_code=404,
            detail="Could not find continuation session",
        )

    # Return the most recent candidate (most likely the actual continuation)
    best_candidate = max(candidates, key=lambda s: s.start_time or s.end_time)

    return ContinuationSessionInfo(
        session_uuid=best_candidate.uuid,
        project_encoded_name=project_encoded_name,
        slug=best_candidate.slug,
    )


def extract_file_activity_from_tool(
    block: ToolUseBlock,
    timestamp: datetime,
    actor: str,
    actor_type: str,
) -> Optional[FileActivity]:
    """Extract file activity from a tool use block."""
    tool_name = block.name
    tool_input = block.input

    if tool_name not in FILE_TOOL_MAPPINGS:
        return None

    operation, path_field = FILE_TOOL_MAPPINGS[tool_name]

    # Extract path from input
    path_value = tool_input.get(path_field)

    # Fallback for older/different tool versions
    if path_value is None and path_field == "file_path":
        path_value = tool_input.get("path")

    if path_value is None:
        return None

    # Handle list of paths (e.g., SemanticSearch target_directories)
    if isinstance(path_value, list):
        path_value = path_value[0] if path_value else None

    if not path_value:
        return None

    return FileActivity(
        path=str(path_value),
        operation=operation,
        actor=actor,
        actor_type=actor_type,
        timestamp=timestamp,
        tool_name=tool_name,
    )


@router.get("/{uuid}")
def get_session(uuid: str, request: Request, fresh: bool = False):
    """
    Get detailed session information.

    Phase 3: Supports HTTP caching with ETag and conditional requests.
    Returns 304 Not Modified if content hasn't changed.

    Args:
        uuid: Session UUID
        fresh: If true, use minimal cache (1s) for live session polling
               and clear in-memory session cache to get fresh values
    """
    result = find_session_with_project(uuid)
    if not result:
        raise HTTPException(status_code=404, detail="Session not found")

    session = result.session
    project_encoded_name = result.project_encoded_name

    # Compute display name from session's working directory
    project_display_name = None
    working_dirs = list(session.get_working_directories())
    if working_dirs:
        from pathlib import Path

        project_display_name = Path(working_dirs[0]).name

    # Clear session cache for fresh requests (live session polling)
    # This ensures message_count, duration, tokens, etc. are recomputed
    if fresh:
        session.clear_cache()

    # Phase 3: Check conditional request headers (single stat() call)
    etag, last_modified = get_file_cache_info(session.jsonl_path)

    conditional_response = check_conditional_request(request, etag, last_modified)
    if conditional_response:
        return conditional_response

    # Build full response
    usage = session.get_usage_summary()
    tools_used = session.get_tools_used()
    skills_used = session.get_skills_used()
    skills_mentioned = session.get_skills_mentioned()
    commands_used = session.get_commands_used()

    # Get initial prompt using shared helper
    initial_prompt = get_initial_prompt(session)

    # Extract image attachments from first user message
    first_user_msg = next(session.iter_user_messages(), None)
    initial_prompt_images = (
        list(first_user_msg.image_attachments)
        if first_user_msg and first_user_msg.image_attachments
        else []
    )

    # Load todos
    todos: list[TodoItemSchema] = []
    try:
        todo_items = session.list_todos()
        todos = [
            TodoItemSchema(
                content=t.content,
                status=t.status,
                active_form=t.active_form,
            )
            for t in todo_items
        ]
    except Exception:
        pass  # Todos are optional, don't fail the request

    # Load tasks (new task system with dependencies)
    tasks: list[TaskSchema] = []
    try:
        task_items = session.list_tasks()
        tasks = [
            TaskSchema(
                id=t.id,
                subject=t.subject,
                description=t.description,
                status=t.status,
                active_form=t.active_form,
                blocks=t.blocks,
                blocked_by=t.blocked_by,
            )
            for t in task_items
        ]
    except Exception:
        pass  # Tasks are optional, don't fail the request

    # Lightweight chain check (avoids full chain build)
    has_chain = False
    try:
        from db.connection import create_read_connection
        from db.queries import query_session_has_chain

        _conn = create_read_connection()
        try:
            has_chain = query_session_has_chain(_conn, uuid)
        finally:
            _conn.close()
    except Exception:
        pass  # DB unavailable, frontend will still try /chain as fallback

    response_data = SessionDetail(
        uuid=session.uuid,
        slug=session.slug,
        project_encoded_name=project_encoded_name,
        project_display_name=project_display_name,
        message_count=session.message_count,
        start_time=session.start_time,
        end_time=session.end_time,
        duration_seconds=session.duration_seconds,
        models_used=list(session.get_models_used()),
        subagent_count=session.count_subagents(),
        has_todos=session.has_todos,
        session_source=get_session_source(session.uuid),
        todo_count=len(todos),
        initial_prompt=initial_prompt,
        initial_prompt_images=initial_prompt_images,
        tools_used=dict(tools_used),
        git_branches=list(session.get_git_branches()),
        working_directories=list(session.get_working_directories()),
        total_input_tokens=usage.total_input,
        total_output_tokens=usage.output_tokens,
        cache_hit_rate=usage.cache_hit_rate,
        total_cost=session.get_total_cost(),
        todos=todos,
        tasks=tasks,
        has_tasks=session.has_tasks,
        has_chain=has_chain,
        # Continuation session detection fields
        is_continuation_marker=session.is_continuation_marker,
        file_snapshot_count=session.file_snapshot_count,
        # Project context (summaries from PREVIOUS sessions)
        project_context_summaries=session.project_context_summaries or [],
        project_context_leaf_uuids=session.project_context_leaf_uuids or [],
        # Session titles (generated names, NOT compaction)
        session_titles=session.session_titles
        or title_cache.get_titles(project_encoded_name, uuid)
        or [],
        # Session compaction (TRUE compaction from CompactBoundaryMessage)
        was_compacted=session.was_compacted,
        compaction_summary_count=session.compaction_summary_count,
        compaction_summaries=[
            CompactionSummary(
                summary=detail.get("content") or "Conversation compacted",
                trigger=detail.get("trigger"),
                pre_tokens=detail.get("pre_tokens"),
                timestamp=detail.get("timestamp"),
            )
            for detail in (session.compaction_summaries or [])
        ],
        message_type_breakdown=session.get_message_type_breakdown(),
        # Skill usage tracking (keys are (name, invocation_source) tuples)
        skills_used=[
            SkillUsage(
                name=skill_name,
                count=count,
                is_plugin=is_plugin_skill(skill_name),
                plugin=_skill_plugin_name(skill_name),
                invocation_source=inv_source,
            )
            for (skill_name, inv_source), count in skills_used.items()
        ],
        # Skills mentioned in user prompts but not invoked
        skills_mentioned=[
            SkillUsage(
                name=skill_name,
                count=count,
                is_plugin=is_plugin_skill(skill_name),
                plugin=_skill_plugin_name(skill_name),
                invocation_source=inv_source,
            )
            for (skill_name, inv_source), count in skills_mentioned.items()
        ],
        # Command usage tracking (keys are (name, invocation_source) tuples)
        commands_used=[
            CommandUsage(
                name=cmd_name,
                count=count,
                source=source,
                plugin=plugin,
                invocation_source=inv_source,
            )
            for (cmd_name, inv_source), count in commands_used.items()
            for source, plugin in [detect_command_source(cmd_name, project_encoded_name)]
        ],
    )

    # Phase 3: Add cache headers to response
    # Use minimal cache for live session polling
    cache_headers = build_cache_headers(
        etag=etag,
        last_modified=last_modified,
        max_age=1 if fresh else 60,
        stale_while_revalidate=2 if fresh else 300,
        private=True,
    )

    return JSONResponse(
        content=response_data.model_dump(mode="json"),
        headers=cache_headers,
    )


@router.get("/{uuid}/todos")
@cacheable(max_age=60, stale_while_revalidate=300, private=True)
def get_session_todos(uuid: str, request: Request) -> list[TodoItemSchema]:
    """
    Get all todo items for a session.

    Returns the current state of todos from ~/.claude/todos/{uuid}-*.json
    Phase 3: Cached for 60s with stale-while-revalidate.
    """
    session = find_session(uuid)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {uuid} not found")

    try:
        todos = session.list_todos()
        return [
            TodoItemSchema(
                content=todo.content,
                status=todo.status,
                active_form=todo.active_form,
            )
            for todo in todos
        ]
    except Exception as e:
        # Log error but return empty list (todos are optional)
        logger.warning(f"Failed to load todos for session {uuid}: {e}")
        return []


@router.get("/{uuid}/tasks")
def get_session_tasks(
    uuid: str,
    request: Request,
    fresh: bool = False,
    since: Optional[str] = None,
):
    """
    Get task items for a session (new task system with dependency tracking).

    Returns the current state of tasks from ~/.claude/tasks/{uuid}/*.json
    Tasks have dependency tracking via blocks/blockedBy fields.

    Args:
        uuid: Session UUID
        fresh: If true, use minimal cache (1s) for live session polling
        since: ISO timestamp string - only return tasks modified after this time.
               Used for incremental fetching during live polling.

    Returns:
        List of TaskSchema with updated_at timestamps
    """
    session = find_session(uuid)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {uuid} not found")

    # Parse the since parameter if provided
    since_dt: Optional[datetime] = None
    if since:
        try:
            # Handle ISO format with Z suffix
            since_str = since.replace("Z", "+00:00")
            since_dt = datetime.fromisoformat(since_str)
        except ValueError:
            logger.warning(f"Invalid 'since' timestamp format: {since}")
            # Continue without filtering

    try:
        tasks = session.list_tasks()
        tasks_dir = session.tasks_dir

        task_schemas = []
        for task in tasks:
            # Determine updated_at from file mtime or session end time
            updated_at: Optional[datetime] = None
            task_file = tasks_dir / f"{task.id}.json"

            if task_file.exists():
                # Use file modification time
                mtime = task_file.stat().st_mtime
                updated_at = datetime.fromtimestamp(mtime, tz=timezone.utc)
            else:
                # For reconstructed tasks, use session end time or current time
                updated_at = session.end_time or datetime.now(timezone.utc)

            # Filter by since parameter if provided
            if since_dt and updated_at:
                # Use normalize_timezone for proper timezone comparison
                normalized_updated = normalize_timezone(updated_at)
                normalized_since = normalize_timezone(since_dt)

                if normalized_updated <= normalized_since:
                    continue  # Skip tasks not modified since the given time

            task_schemas.append(
                TaskSchema(
                    id=task.id,
                    subject=task.subject,
                    description=task.description,
                    status=task.status,
                    active_form=task.active_form,
                    blocks=task.blocks,
                    blocked_by=task.blocked_by,
                    updated_at=updated_at,
                )
            )

        # Add cache headers - minimal cache for live polling
        response_data = [t.model_dump(mode="json") for t in task_schemas]
        headers = {
            "Cache-Control": f"private, max-age={1 if fresh else 60}, stale-while-revalidate={2 if fresh else 300}"
        }
        return JSONResponse(content=response_data, headers=headers)

    except Exception as e:
        # Log error but return empty list (tasks are optional)
        logger.warning(f"Failed to load tasks for session {uuid}: {e}")
        return JSONResponse(content=[], headers={"Cache-Control": "private, max-age=1"})


@router.get("/{uuid}/file-activity")
def get_file_activity(uuid: str, request: Request, fresh: bool = False):
    """
    Get all file operations in a session with actor attribution.

    Phase 2 optimization: Uses single-pass data collection.
    Phase 3: Cached for 5min (historical data rarely changes).
    Phase 3 DRY: Uses shared conversation_endpoints service.

    Args:
        uuid: Session UUID
        fresh: If true, use minimal cache (1s) for live session polling
    """
    from services.conversation_endpoints import build_file_activities

    session = find_session(uuid)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Single-pass collection with subagents (uses existing collectors.py)
    data = collect_session_data(session, include_subagents=True)

    # Use shared service for building activities (handles sorting)
    activities = build_file_activities(data.file_operations)

    # Add cache headers - minimal cache for live polling
    response_data = [a.model_dump(mode="json") for a in activities]
    headers = {
        "Cache-Control": f"private, max-age={1 if fresh else 300}, stale-while-revalidate={2 if fresh else 600}"
    }
    return JSONResponse(content=response_data, headers=headers)


@router.get("/{uuid}/subagents")
def get_subagents(uuid: str, request: Request, fresh: bool = False):
    """
    Get all subagents in a session with their tool usage.

    Phase 2 optimization: Reduced from 4+ passes to 2 passes
    (1 for main session + tool results, 1 per subagent).
    Phase 3: Cached for 5min (historical data rarely changes).

    Args:
        uuid: Session UUID
        fresh: If true, use minimal cache (1s) for live session polling
    """
    session = find_session(uuid)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Single-pass collection of main session data (extracts Task -> type mappings)
    session_data = collect_session_data(session, include_subagents=False)

    # Pre-build subagent lookup for tool results
    subagent_lookup: dict[str, str | None] = {}
    for sa in session.list_subagents():
        subagent_lookup[sa.agent_id] = sa.slug

    # Collect tool results (still needs its own pass for UserMessage parsing)
    tool_results = collect_tool_results(session, extract_spawned_agent=True, parse_xml=True)

    # Collect subagent info using pre-collected session data
    subagents_info = collect_subagent_info(session, session_data, tool_results)

    # Convert to response schema
    summaries = [
        SubagentSummary(
            agent_id=info.agent_id,
            slug=info.slug,
            subagent_type=info.subagent_type,
            tools_used=dict(info.tool_counts),
            message_count=info.message_count,
            initial_prompt=info.initial_prompt,
        )
        for info in subagents_info
    ]

    # Log unmatched subagents for debugging
    for info in subagents_info:
        if info.subagent_type is None and info.initial_prompt:
            logger.debug(
                f"Subagent {info.agent_id} unmatched. "
                f"Prompt: '{(info.initial_prompt or '')[:50]}...'"
            )

    # Add cache headers - minimal cache for live polling
    from fastapi.responses import JSONResponse

    response_data = [s.model_dump(mode="json") for s in summaries]
    headers = {
        "Cache-Control": f"private, max-age={1 if fresh else 300}, stale-while-revalidate={2 if fresh else 600}"
    }
    return JSONResponse(content=response_data, headers=headers)


@router.get("/{uuid}/subagents/parallel")
async def get_subagents_parallel(uuid: str, request: Request):
    """
    Get all subagents in a session using parallel processing.

    Phase 4 optimization: Processes subagent JSONL files concurrently
    using a thread pool. This is faster for sessions with many subagents
    (10+) as it reduces I/O wait time.

    Falls back to sequential processing for sessions with few subagents.
    """
    session = find_session(uuid)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    subagents = session.list_subagents()

    # For small numbers of subagents, parallel overhead isn't worth it
    if len(subagents) < 5:
        # Use the standard sequential endpoint logic
        session_data = collect_session_data(session, include_subagents=False)
        subagent_lookup: dict[str, str | None] = {}
        for sa in subagents:
            subagent_lookup[sa.agent_id] = sa.slug
        tool_results = collect_tool_results(session, extract_spawned_agent=True, parse_xml=True)
        subagents_info = collect_subagent_info(session, session_data, tool_results)

        return [
            SubagentSummary(
                agent_id=info.agent_id,
                slug=info.slug,
                subagent_type=info.subagent_type,
                tools_used=dict(info.tool_counts),
                message_count=info.message_count,
                initial_prompt=info.initial_prompt,
            )
            for info in subagents_info
        ]

    # Phase 4: Use parallel processing for many subagents
    subagent_data = await process_subagents_parallel(subagents)

    # Build response summaries
    summaries = [
        SubagentSummary(
            agent_id=data["agent_id"],
            slug=data.get("slug"),
            subagent_type=None,  # Type matching not done in parallel mode
            tools_used=data.get("tool_counts", {}),
            message_count=data.get("message_count", 0),
            initial_prompt=data.get("initial_prompt"),
        )
        for data in subagent_data
    ]

    return summaries


@router.get("/{uuid}/tools")
def get_tools(uuid: str, request: Request, fresh: bool = False):
    """
    Get tool usage breakdown for a session.

    Phase 2 optimization: Uses single-pass data collection.
    Phase 3: Cached for 5min (historical data rarely changes).
    Phase 3 DRY: Uses shared conversation_endpoints service.

    Args:
        uuid: Session UUID
        fresh: If true, use minimal cache (1s) for live session polling
    """
    from services.conversation_endpoints import build_tool_usage_summaries

    session = find_session(uuid)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Single-pass collection with subagents
    data = collect_session_data(session, include_subagents=True)

    # Use shared service for building tool summaries
    summaries = build_tool_usage_summaries(
        data.session_tool_counts,
        data.subagent_tool_counts,
    )

    # Add cache headers - minimal cache for live polling
    response_data = [s.model_dump(mode="json") for s in summaries]
    headers = {
        "Cache-Control": f"private, max-age={1 if fresh else 300}, stale-while-revalidate={2 if fresh else 600}"
    }
    return JSONResponse(content=response_data, headers=headers)


@router.get("/{uuid}/initial-prompt")
@cacheable(max_age=300, stale_while_revalidate=600, private=True)
def get_session_initial_prompt(uuid: str, request: Request):
    """
    Get the initial prompt (first user message) for a session.

    Phase 3: Cached for 5min (historical data, never changes).
    """
    session = find_session(uuid)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Use shared helper to get the prompt content
    prompt_content = get_initial_prompt(session)
    if prompt_content is None:
        raise HTTPException(status_code=404, detail="No user messages found in session")

    # Get timestamp from first user message for the response
    for msg in session.iter_user_messages():
        return InitialPrompt(
            content=msg.content,
            timestamp=msg.timestamp,
            image_attachments=list(msg.image_attachments) if msg.image_attachments else [],
        )

    raise HTTPException(status_code=404, detail="No user messages found in session")


@router.get("/{uuid}/timeline")
def get_timeline(uuid: str, request: Request, fresh: bool = False):
    """
    Get chronological timeline of events in a session.

    Phase 3: Cached for 60s with stale-while-revalidate.
    Phase 3 DRY: Uses shared conversation_endpoints service.

    Args:
        uuid: Session UUID
        fresh: If true, use minimal cache (1s) for live session polling
    """
    from services.conversation_endpoints import build_conversation_timeline

    session = find_session(uuid)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get working directories for relative path conversion
    working_dirs = list(session.get_working_directories())

    # Pre-build a map of subagent IDs to slugs for quick lookup
    subagent_info: dict[str, str | None] = {}
    for sa in session.list_subagents():
        subagent_info[sa.agent_id] = sa.slug

    # Use shared service for building timeline
    events = build_conversation_timeline(
        conversation=session,
        working_dirs=working_dirs,
        actor="session",
        actor_type="session",
        subagent_info=subagent_info,
    )

    # Add cache headers - minimal cache for live polling
    response_data = [e.model_dump(mode="json") for e in events]
    headers = {
        "Cache-Control": f"private, max-age={1 if fresh else 60}, stale-while-revalidate={2 if fresh else 300}"
    }
    return JSONResponse(content=response_data, headers=headers)


# ============================================================================
# Session Relationship Endpoints
# ============================================================================


@router.get("/{uuid}/relationships")
@cacheable(max_age=300, stale_while_revalidate=600, private=True)
def get_session_relationships(uuid: str, request: Request):
    """
    Get relationships for a session (parents, children, chain position).

    Returns both inbound (this session resumed FROM) and outbound
    (this session PROVIDED CONTEXT TO) relationships with confidence scores.

    Detection methods:
    - leaf_uuid (95% confidence): Direct reference in JSONL
    - slug_match (85% confidence): Same slug + time proximity

    Phase 3: Cached for 5min (relationships rarely change).
    """
    from schemas import SessionRelationshipSchema
    from services.session_relationships import get_resolver

    result = find_session_with_project(uuid)
    if not result:
        raise HTTPException(status_code=404, detail="Session not found")
    resolver = get_resolver(result.session.jsonl_path.parent)
    relationships = resolver.find_relationships(result.session)

    # Convert to schema format
    return [
        SessionRelationshipSchema(
            source_uuid=rel.source_uuid,
            target_uuid=rel.target_uuid,
            relationship_type=rel.relationship_type.value,
            source_slug=rel.source_slug,
            target_slug=rel.target_slug,
            detected_via=rel.detected_via,
            confidence=rel.confidence,
            source_end_time=rel.source_end_time,
            target_start_time=rel.target_start_time,
        ).model_dump(mode="json")
        for rel in relationships
    ]


@router.get("/{uuid}/chain")
@cacheable(max_age=300, stale_while_revalidate=600, private=True)
def get_session_chain(uuid: str, request: Request):
    """
    Get the full session chain (ancestors + descendants).

    Returns a tree structure with all related sessions ordered from
    root ancestor to leaf descendants.

    Fast path: Uses SQLite DB (indexed leaf_uuid + slug matching).
    Fallback: Scans JSONL files if DB unavailable.

    Phase 3: Cached for 5min (chain structure rarely changes).
    """
    from schemas import SessionChainNodeSchema, SessionChainSchema

    # Fast path: DB-backed query (no JSONL scanning)
    try:
        from db.connection import create_read_connection
        from db.queries import query_session_chain

        conn = create_read_connection()
        try:
            db_chain = query_session_chain(conn, uuid)
            if db_chain:
                # Return dict directly — data is already validated from DB,
                # skip Pydantic model instantiation + serialization overhead
                return db_chain
        finally:
            conn.close()
    except Exception:
        logger.debug("DB-backed chain query failed, falling back to JSONL")

    # Fallback: JSONL-based chain building (cached resolver per project)
    from services.session_relationships import get_resolver

    result = find_session_with_project(uuid)
    if not result:
        raise HTTPException(status_code=404, detail="Session not found")

    resolver = get_resolver(result.session.jsonl_path.parent)
    chain = resolver.build_chain(uuid)

    nodes = [
        SessionChainNodeSchema(
            uuid=node.uuid,
            slug=node.slug,
            start_time=node.start_time,
            end_time=node.end_time,
            is_current=node.is_current,
            chain_depth=node.chain_depth,
            parent_uuid=node.parent_uuid,
            children_uuids=node.children_uuids,
            was_compacted=node.was_compacted,
            is_continuation_marker=node.is_continuation_marker,
            message_count=node.message_count,
            initial_prompt=node.initial_prompt,
        ).model_dump(mode="json")
        for node in chain.nodes
    ]

    return SessionChainSchema(
        current_session_uuid=chain.current_session_uuid,
        nodes=nodes,
        root_uuid=chain.root_uuid,
        total_sessions=chain.total_sessions,
        max_depth=chain.max_depth,
        total_compactions=chain.total_compactions,
    ).model_dump(mode="json")


# ============================================================================
# Session-Plan Linking Endpoints
# ============================================================================


@router.get("/{uuid}/plan", response_model=PlanDetail)
@cacheable(max_age=300, stale_while_revalidate=600, private=True)
def get_session_plan(uuid: str, request: Request) -> PlanDetail | None:
    """
    Get the plan associated with a session.

    Plans are stored in ~/.claude/plans/{slug}.md and are linked to sessions
    by matching the session's slug to the plan's slug (filename without .md).

    Args:
        uuid: Session UUID

    Returns:
        PlanDetail with full plan content and metadata

    Raises:
        HTTPException: 404 if session not found or no plan for this session
    """
    # Find the session
    session = find_session(uuid)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get the session's slug
    session_slug = session.slug
    if not session_slug:
        raise HTTPException(
            status_code=404,
            detail="Session has no slug - cannot determine associated plan",
        )

    # Try to load the plan with the matching slug
    plan = load_plan(session_slug)
    if not plan:
        return None

    # Convert to PlanDetail schema
    return PlanDetail(
        slug=plan.slug,
        title=plan.extract_title(),
        preview=plan.content[:500] if plan.content else "",
        word_count=plan.word_count,
        created=plan.created,
        modified=plan.modified,
        size_bytes=plan.size_bytes,
        content=plan.content,
    )


# ============================================================================
# Session Title Management
# ============================================================================


class SetTitleRequest(BaseModel):
    """Request body for setting a session title."""

    title: str


@router.post("/{uuid}/title")
def set_session_title(uuid: str, request: SetTitleRequest):
    """
    Set or update a session title.

    Used by SessionEnd hook and manual override. Updates both the
    SessionTitleCache and SQLite database (if available).

    Args:
        uuid: Session UUID
        request: Request body with title

    Returns:
        JSON response with status, uuid, and title

    Raises:
        HTTPException: 404 if session not found
    """
    # Find the session to get its project (encoded_name)
    result = find_session_with_project(uuid)
    if not result:
        raise HTTPException(status_code=404, detail="Session not found")

    encoded_name = result.project_encoded_name
    title = request.title

    # Update SessionTitleCache
    title_cache.set_title(encoded_name, uuid, title)

    # Update SQLite if available
    if settings.use_sqlite:
        try:
            from db.connection import get_writer_db

            conn = get_writer_db()
            # Get existing titles, prepend new one
            row = conn.execute(
                "SELECT session_titles FROM sessions WHERE uuid = ?", (uuid,)
            ).fetchone()

            if row:
                existing_titles = []
                if row["session_titles"]:
                    try:
                        existing_titles = json.loads(row["session_titles"])
                    except json.JSONDecodeError:
                        pass

                # Prepend new title if not already present
                if title not in existing_titles:
                    new_titles = [title] + existing_titles
                else:
                    new_titles = existing_titles

                conn.execute(
                    "UPDATE sessions SET session_titles = ? WHERE uuid = ?",
                    (json.dumps(new_titles), uuid),
                )
                conn.commit()
        except Exception as e:
            logger.warning("Failed to update SQLite for session %s: %s", uuid, e)
            # Don't fail the request if SQLite update fails

    return JSONResponse(
        content={"status": "ok", "uuid": uuid, "title": title},
        status_code=200,
    )
