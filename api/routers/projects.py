"""
Projects router - list and get project details.

Phase 3: HTTP caching with Cache-Control headers.
"""

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from fastapi import APIRouter, HTTPException, Request

if TYPE_CHECKING:
    from schemas import SessionLookupResult

# Add models and api to path
api_path = Path(__file__).parent.parent
models_path = api_path.parent.parent
sys.path.insert(0, str(api_path))
sys.path.insert(0, str(models_path))

# Phase 3: HTTP caching
from http_caching import cacheable

logger = logging.getLogger(__name__)
from models import Project, Session, SessionIndexEntry

# Import analytics calculation function
from routers.analytics import _calculate_analytics_from_sessions
from schemas import (
    AgentSummary,
    BranchSummary,
    ProjectAnalytics,
    ProjectBranchesResponse,
    ProjectChainsResponse,
    ProjectDetail,
    ProjectMemoryResponse,
    ProjectSummary,
    SessionChainInfo,
    SessionChainInfoSummary,
    SessionChainNodeSchema,
    SessionChainSchema,
    SessionSummary,
    SkillItem,
)
from services.session_title_cache import title_cache


def _enrich_chain_titles(summaries: list[SessionSummary]) -> None:
    """Propagate titles across session chains for untitled sessions."""
    chains: dict[str, list[SessionSummary]] = {}
    for s in summaries:
        if s.chain_info:
            chains.setdefault(s.chain_info.chain_id, []).append(s)
    for chain_sessions in chains.values():
        if len(chain_sessions) < 2:
            continue
        donor_title = next((s.session_titles[0] for s in chain_sessions if s.session_titles), None)
        if not donor_title:
            continue
        for s in chain_sessions:
            if not s.session_titles:
                s.chain_title = donor_title


from services.desktop_sessions import get_session_source
from utils import (
    get_initial_prompt,
    get_initial_prompt_from_index,
    get_worktree_mappings_for_project,
    list_all_projects,
    normalize_timezone,
    parse_timestamp_range,
    resolve_git_root,
)

# TTL cache for remote session filesystem scans (avoids walking disk every request).
# Uses cachetools.TTLCache (bounded, auto-evicts) + threading.Lock to prevent
# thundering herd under concurrent FastAPI threadpool requests.
import threading as _threading

from cachetools import TTLCache as _TTLCache

_remote_sessions_cache = _TTLCache(maxsize=128, ttl=30.0)
_remote_cache_lock = _threading.Lock()


def _get_cached_remote_sessions(encoded_name: str) -> list:
    """Return remote sessions for a project, cached for 30s to avoid repeated filesystem walks."""
    cached = _remote_sessions_cache.get(encoded_name)
    if cached is not None:
        return cached

    with _remote_cache_lock:
        # Double-check after acquiring lock (another thread may have populated it)
        cached = _remote_sessions_cache.get(encoded_name)
        if cached is not None:
            return cached

        from services.remote_sessions import list_remote_sessions_for_project

        result = list_remote_sessions_for_project(encoded_name)
        _remote_sessions_cache[encoded_name] = result
        return result


router = APIRouter()


def resolve_project_identifier(identifier: str) -> str:
    """
    Resolve a project identifier (slug or encoded_name) to encoded_name.

    If identifier starts with '-', treat as encoded_name directly.
    Otherwise, try slug lookup via DB, then fall back to disk scan.

    Safety net: if the resolved encoded_name is a worktree project,
    redirect to the real project's encoded_name.

    Returns the encoded_name string.
    Raises HTTPException 404 if not found.
    """
    from services.desktop_sessions import (
        get_real_project_encoded_name,
        is_worktree_project,
    )

    if identifier.startswith("-"):
        # Safety net: redirect worktree encoded names to real project
        if is_worktree_project(identifier):
            try:
                from db.connection import sqlite_read

                with sqlite_read() as conn:
                    if conn is not None:
                        session_uuids = [
                            r[0]
                            for r in conn.execute(
                                "SELECT uuid FROM sessions WHERE project_encoded_name = ?",
                                (identifier,),
                            ).fetchall()
                        ]
                        real = get_real_project_encoded_name(identifier, session_uuids)
                        if real:
                            return real
            except Exception:
                pass
        return identifier

    # Try DB slug lookup
    try:
        from db.connection import sqlite_read
        from db.queries import query_project_by_slug

        with sqlite_read() as conn:
            if conn is not None:
                row = query_project_by_slug(conn, identifier)
                if row:
                    encoded = row["encoded_name"]
                    # Safety net: if slug resolved to a worktree project, redirect
                    if is_worktree_project(encoded):
                        session_uuids = [
                            r[0]
                            for r in conn.execute(
                                "SELECT uuid FROM sessions WHERE project_encoded_name = ?",
                                (encoded,),
                            ).fetchall()
                        ]
                        real = get_real_project_encoded_name(encoded, session_uuids)
                        if real:
                            return real
                    return encoded
    except Exception:
        pass

    # Fallback: scan all projects for matching slug
    for p in list_all_projects():
        if p.slug == identifier:
            return p.encoded_name

    raise HTTPException(status_code=404, detail=f"Project not found: {identifier}")


def _count_worktree_sessions(real_encoded: str) -> int:
    """Count sessions in worktree dirs mapped to a real project."""
    wt_encodeds = get_worktree_mappings_for_project(real_encoded)
    count = 0
    for wt_enc in wt_encodeds:
        try:
            wt_project = Project.from_encoded_name(wt_enc, skip_path_recovery=True)
            count += wt_project.session_count
        except Exception:
            continue
    return count


def _load_worktree_sessions(real_encoded: str) -> list[Session]:
    """Load all sessions from worktree dirs mapped to a real project."""
    wt_encodeds = get_worktree_mappings_for_project(real_encoded)
    sessions: list[Session] = []
    for wt_enc in wt_encodeds:
        try:
            wt_project = Project.from_encoded_name(wt_enc, skip_path_recovery=True)
            for s in wt_project.list_sessions():
                if s.message_count > 0:
                    sessions.append(s)
        except Exception:
            continue
    return sessions


# ============================================================================
# Slug Cache for Fast Lookups
# ============================================================================

# In-memory cache: project_encoded_name -> {slug -> session_uuid}
# This avoids scanning all JSONL files for slug lookups
_slug_cache: dict[str, dict[str, str]] = {}
_slug_cache_mtime: dict[str, float] = {}  # Track when cache was built


def _build_slug_cache(project: Project) -> dict[str, str]:
    """
    Build a slug -> UUID mapping for all sessions in a project.

    This scans all JSONL files once and caches the result.
    Returns a dict mapping slug to session UUID.
    """
    slug_map: dict[str, str] = {}

    for jsonl_path in project.project_dir.glob("*.jsonl"):
        stem = jsonl_path.stem
        if "-" not in stem:
            continue
        try:
            session = Session.from_path(jsonl_path)
            if session.message_count > 0 and session.slug:
                slug_map[session.slug] = session.uuid
        except Exception:
            continue

    return slug_map


def _get_slug_cache(project: Project) -> dict[str, str]:
    """
    Get or build the slug cache for a project.

    Cache is invalidated if the project directory mtime changes.
    """
    encoded_name = project.encoded_name

    # Check if cache exists and is fresh
    try:
        current_mtime = project.project_dir.stat().st_mtime
    except Exception:
        current_mtime = 0

    if encoded_name in _slug_cache:
        cached_mtime = _slug_cache_mtime.get(encoded_name, 0)
        # Cache is valid if directory hasn't been modified
        if current_mtime <= cached_mtime:
            return _slug_cache[encoded_name]

    # Build and cache
    slug_map = _build_slug_cache(project)
    _slug_cache[encoded_name] = slug_map
    _slug_cache_mtime[encoded_name] = current_mtime

    return slug_map


def session_to_summary(
    session: Session,
    chain_info: Optional[SessionChainInfoSummary] = None,
    session_source: Optional[str] = None,
    source: Optional[str] = None,
    remote_user_id: Optional[str] = None,
    remote_machine_id: Optional[str] = None,
) -> SessionSummary:
    """Convert a Session to SessionSummary."""
    initial_prompt = get_initial_prompt(session, max_length=500)

    return SessionSummary(
        uuid=session.uuid,
        slug=session.slug,
        message_count=session.message_count,
        start_time=session.start_time,
        end_time=session.end_time,
        duration_seconds=session.duration_seconds,
        models_used=list(session.get_models_used()),
        subagent_count=len(session.list_subagents()),
        has_todos=session.has_todos,
        initial_prompt=initial_prompt,
        summary=None,
        git_branches=list(session.get_git_branches()),
        chain_info=chain_info,
        session_titles=list(session.session_titles or []),
        session_source=session_source,
        source=source,
        remote_user_id=remote_user_id,
        remote_machine_id=remote_machine_id,
    )


def session_index_to_summary(
    entry: SessionIndexEntry,
    project_encoded_name: str,
    chain_info: Optional[SessionChainInfoSummary] = None,
    session_source: Optional[str] = None,
) -> SessionSummary:
    """
    Convert a SessionIndexEntry to SessionSummary without parsing JSONL.

    This is ~10x faster than session_to_summary() as it uses pre-computed
    metadata from sessions-index.json.
    """
    return SessionSummary(
        uuid=entry.session_id,
        slug=None,  # Not in index, will need Session for this
        project_encoded_name=project_encoded_name,
        message_count=entry.message_count,
        start_time=entry.created,
        end_time=entry.modified,
        duration_seconds=entry.duration_seconds,
        models_used=[],  # Not in index
        subagent_count=0,  # Not in index
        has_todos=False,  # Not in index
        todo_count=0,
        initial_prompt=get_initial_prompt_from_index(entry.first_prompt),
        summary=entry.summary,  # NEW: Claude's auto-summary
        git_branches=[entry.git_branch] if entry.git_branch else [],
        chain_info=chain_info,
        session_titles=title_cache.get_titles(project_encoded_name, entry.session_id) or [],
        session_source=session_source,
    )


def get_latest_session_time(project: Project):
    """
    Get the start time of the most recent session for a project.

    Phase 4 optimization: Uses file modification time as a proxy without
    parsing JSONL files at all. This is faster but returns mtime instead
    of actual session start_time.

    For the most accurate start_time (at cost of parsing one file), use
    the _get_latest_session_time_accurate fallback.
    """
    # Phase 4: Use fast mtime-based method (no file parsing)
    return project.get_latest_session_time_fast()


def _get_latest_session_time_accurate(project: Project):
    """
    Get the actual start_time of the most recent session.

    This parses the most recently modified JSONL file to get the
    actual session start_time. Use when accuracy is more important
    than speed.
    """
    jsonl_files = list(project.project_dir.glob("*.jsonl"))
    if not jsonl_files:
        return None

    latest_file = max(jsonl_files, key=lambda f: f.stat().st_mtime)

    try:
        session = Session.from_path(latest_file)
        return session.start_time
    except Exception:
        return None


@router.get("")
@cacheable(max_age=30, stale_while_revalidate=60, private=True)
def list_projects(request: Request):
    """
    List all projects with basic stats.

    Phase 3: Short cache (30s) - new projects/sessions may appear frequently.
    Phase 10: SQLite fast path — queries precomputed projects table, supplements
    with lightweight filesystem checks for git metadata.
    """
    # SQLite fast path
    try:
        from db.connection import sqlite_read
        from db.queries import query_all_projects

        with sqlite_read() as conn:
            if conn is not None:
                rows = query_all_projects(conn)
                if rows:
                    summaries = []
                    for row in rows:
                        path = row.get("project_path") or ""
                        encoded_name = row["encoded_name"]
                        is_git = False
                        git_root = None
                        is_nested = False
                        exists = False
                        if path:
                            p = Path(path)
                            exists = p.is_dir()
                            if exists:
                                is_git = (p / ".git").exists()
                                git_root = resolve_git_root(path)
                                if git_root is not None:
                                    is_nested = p.resolve() != Path(git_root).resolve()
                        summaries.append(
                            ProjectSummary(
                                path=path,
                                encoded_name=encoded_name,
                                slug=row.get("slug"),
                                display_name=row.get("display_name"),
                                session_count=row.get("session_count", 0),
                                agent_count=0,  # Not stored in DB; lightweight tradeoff
                                exists=exists,
                                is_git_repository=is_git,
                                git_root_path=git_root,
                                is_nested_project=is_nested,
                                latest_session_time=row.get("last_activity"),
                            )
                        )
                    return summaries
    except Exception as e:
        logger.warning("SQLite list_projects query failed, falling back: %s", e)

    # Fallback: filesystem scan
    projects = list_all_projects()
    return [
        ProjectSummary(
            path=p.path,
            encoded_name=p.encoded_name,
            slug=p.slug,
            display_name=p.display_name,
            session_count=p.session_count + _count_worktree_sessions(p.encoded_name),
            agent_count=p.agent_count,
            exists=p.exists,
            is_git_repository=p.is_git_repository,
            git_root_path=p.git_root_path,
            is_nested_project=p.is_nested_project,
            latest_session_time=get_latest_session_time(p),
        )
        for p in projects
    ]


@router.get("/{encoded_name}")
@cacheable(max_age=60, stale_while_revalidate=120, private=True)
def get_project(
    encoded_name: str,
    request: Request,
    page: int = 1,
    per_page: int = 50,
    search: Optional[str] = None,
):
    """
    Get project details with sessions list.

    Phase 3: Moderate cache (60s) - project metadata changes infrequently.

    Sessions include chain_info when they are part of a resumed session chain
    (multiple sessions sharing the same slug).

    Args:
        encoded_name: URL-encoded project path or project slug
        page: Page number (1-indexed, default 1)
        per_page: Items per page (default 50)
        search: Optional search term to filter by title, prompt, or slug

    Note: session_count in the response is the TOTAL count before pagination,
    allowing frontends to calculate total pages.
    """
    encoded_name = resolve_project_identifier(encoded_name)
    try:
        project = Project.from_encoded_name(encoded_name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Project not found: {e}") from e

    if not project.exists:
        raise HTTPException(status_code=404, detail="Project directory not found")

    # Compute offset from page/per_page
    per_page = max(1, min(per_page, 200))
    offset = (page - 1) * per_page
    limit = per_page

    # SQLite fast path — isolated try/excepts so enrichment failures
    # never trigger the expensive JSONL fallback.
    # One connection is reused for both queries; chain info failure is non-fatal.
    db_data = None
    db_chain_info: dict = {}
    try:
        from db.connection import sqlite_read
        from db.queries import query_chain_info_for_project, query_project_sessions

        with sqlite_read() as conn:
            if conn is not None:
                db_data = query_project_sessions(
                    conn, encoded_name, limit=limit, offset=offset, search=search
                )
                # Chain info — optional enrichment, degrade gracefully
                try:
                    db_chain_info = query_chain_info_for_project(conn, encoded_name)
                except Exception as e:
                    logger.debug("Chain info query failed (non-fatal): %s", e)
    except Exception as e:
        logger.warning("SQLite project sessions query failed, falling back: %s", e)

    if db_data is not None:

        # Build session summaries from SQL rows
        session_summaries = []
        for row in db_data["sessions"]:
            chain_info = None
            uuid = row["uuid"]
            if uuid in db_chain_info:
                ci = db_chain_info[uuid]
                chain_info = SessionChainInfoSummary(
                    chain_id=ci["chain_id"],
                    position=ci["position"],
                    total=ci["total"],
                    is_root=ci["is_root"],
                    is_latest=ci["is_latest"],
                )
            titles = row.get("session_titles", [])
            if not titles:
                titles = title_cache.get_titles(encoded_name, uuid) or []
            session_summaries.append(
                SessionSummary(
                    uuid=uuid,
                    slug=row.get("slug"),
                    message_count=row["message_count"],
                    start_time=row.get("start_time"),
                    end_time=row.get("end_time"),
                    duration_seconds=row.get("duration_seconds"),
                    models_used=row.get("models_used", []),
                    subagent_count=row.get("subagent_count", 0),
                    has_todos=False,
                    initial_prompt=row.get("initial_prompt"),
                    git_branches=row.get("git_branches", []),
                    session_titles=titles,
                    chain_info=chain_info,
                    session_source=row.get("session_source"),
                    source=row.get("source"),
                    remote_user_id=row.get("remote_user_id"),
                    remote_machine_id=row.get("remote_machine_id"),
                )
            )

        total_count = db_data["total"]

        # Merge unindexed remote sessions — optional enrichment
        # IMPORTANT: Only add remote sessions on the first page (offset==0).
        # Each page only knows its own UUIDs, so unindexed remote sessions
        # would be duplicated across every page response otherwise.
        remote_session_count = 0
        try:
            remote_metas = _get_cached_remote_sessions(encoded_name)
            remote_session_count = len(remote_metas)

            if remote_metas and offset == 0:
                indexed_uuids = {s.uuid for s in session_summaries}
                unindexed = [
                    m
                    for m in remote_metas
                    if m.uuid not in indexed_uuids
                ]

                for rmeta in unindexed:
                    titles = rmeta.session_titles or []
                    duration = None
                    if rmeta.start_time and rmeta.end_time:
                        duration = (
                            rmeta.end_time - rmeta.start_time
                        ).total_seconds()
                    session_summaries.append(
                        SessionSummary(
                            uuid=rmeta.uuid,
                            slug=rmeta.slug,
                            message_count=rmeta.message_count,
                            start_time=rmeta.start_time,
                            end_time=rmeta.end_time,
                            duration_seconds=duration,
                            models_used=[],
                            subagent_count=0,
                            has_todos=False,
                            initial_prompt=rmeta.initial_prompt,
                            git_branches=(
                                [rmeta.git_branch]
                                if rmeta.git_branch
                                else []
                            ),
                            session_titles=titles,
                            source=rmeta.source,
                            remote_user_id=rmeta.remote_user_id,
                            remote_machine_id=rmeta.remote_machine_id,
                        )
                    )

                total_count += len(unindexed)

                # Trigger background reindex so next request
                # won't need this disk check
                if unindexed:
                    import threading

                    from db.indexer import trigger_remote_reindex

                    threading.Thread(
                        target=trigger_remote_reindex,
                        daemon=True,
                    ).start()
        except Exception as e:
            logger.debug(
                "Remote session merge in SQLite fast path failed: %s",
                e,
            )

        _enrich_chain_titles(session_summaries)
        return ProjectDetail(
            path=project.path,
            encoded_name=project.encoded_name,
            slug=project.slug,
            display_name=project.display_name,
            session_count=total_count,
            agent_count=project.agent_count,
            exists=project.exists,
            is_git_repository=project.is_git_repository,
            git_root_path=project.git_root_path,
            is_nested_project=project.is_nested_project,
            sessions=session_summaries,
            remote_session_count=remote_session_count,
        )

    sessions = project.list_sessions()
    # Filter out empty sessions (no messages = no valid start_time)
    sessions = [s for s in sessions if s.message_count > 0]

    # Merge worktree sessions
    wt_sessions = _load_worktree_sessions(encoded_name)
    # Track which UUIDs are desktop sessions
    desktop_uuids: set[str] = {ws.uuid for ws in wt_sessions}
    # Also check regular sessions against desktop metadata
    for s in sessions:
        if get_session_source(s.uuid):
            desktop_uuids.add(s.uuid)
    sessions.extend(wt_sessions)

    # Merge remote sessions from Syncthing sync
    remote_metas = _get_cached_remote_sessions(encoded_name)
    remote_uuid_map: dict = {}
    existing_uuids = {s.uuid for s in sessions}
    for rmeta in remote_metas:
        remote_uuid_map[rmeta.uuid] = rmeta
        if rmeta.uuid in existing_uuids:
            continue
        try:
            remote_session = rmeta.get_session()
            sessions.append(remote_session)
            existing_uuids.add(rmeta.uuid)
        except Exception:
            pass

    # Apply search filter (JSONL fallback path)
    if search:
        search_lower = search.lower()

        def _matches_search(s: Session) -> bool:
            if s.slug and search_lower in s.slug.lower():
                return True
            prompt = get_initial_prompt(s, max_length=500)
            if prompt and search_lower in prompt.lower():
                return True
            for title in s.session_titles or []:
                if search_lower in title.lower():
                    return True
            return False

        sessions = [s for s in sessions if _matches_search(s)]

    # Store total count BEFORE limiting (for consistent counts with /sessions/all)
    total_session_count = len(sessions)

    # Build chain info for all sessions BEFORE limiting
    # This ensures chain info is accurate (knows total chain length)
    # Try to use DB connection for efficient chain detection
    from services.session_relationships import get_resolver

    resolver = get_resolver(project.project_dir)
    db_conn = None
    try:
        from db.connection import sqlite_read

        db_ctx = sqlite_read()
        db_conn = db_ctx.__enter__()
    except Exception:
        db_conn = None
        db_ctx = None
    try:
        chain_info_map = resolver.get_chain_info_for_all_sessions(sessions, conn=db_conn)
    finally:
        if db_ctx is not None:
            try:
                db_ctx.__exit__(None, None, None)
            except Exception:
                pass

    # Sort by start time descending (most recent first)
    sessions.sort(
        key=lambda s: normalize_timezone(s.start_time),
        reverse=True,
    )

    # Apply pagination (offset + limit)
    if limit is not None or offset > 0:
        end_idx = offset + limit if limit else None
        sessions = sessions[offset:end_idx]

    fallback_summaries = []
    for s in sessions:
        rmeta = remote_uuid_map.get(s.uuid)
        fallback_summaries.append(
            session_to_summary(
                s,
                chain_info_map.get(s.uuid),
                session_source="desktop" if s.uuid in desktop_uuids else None,
                source=rmeta.source if rmeta else None,
                remote_user_id=rmeta.remote_user_id if rmeta else None,
                remote_machine_id=rmeta.remote_machine_id if rmeta else None,
            )
        )
    _enrich_chain_titles(fallback_summaries)
    return ProjectDetail(
        path=project.path,
        encoded_name=project.encoded_name,
        slug=project.slug,
        display_name=project.display_name,
        session_count=total_session_count,
        agent_count=project.agent_count,
        exists=project.exists,
        is_git_repository=project.is_git_repository,
        git_root_path=project.git_root_path,
        is_nested_project=project.is_nested_project,
        sessions=fallback_summaries,
        remote_session_count=len(remote_uuid_map),
    )


def _lookup_session_in_project(
    project: Project,
    identifier: str,
    is_uuid_like: bool,
    encoded_name: str,
    project_path: str,
) -> Optional["SessionLookupResult"]:
    """
    Search for a session by slug or UUID in a single project directory.

    Returns SessionLookupResult if found, None otherwise.
    """
    from schemas import SessionLookupResult

    if is_uuid_like:
        # Try exact UUID match first
        exact_path = project.project_dir / f"{identifier}.jsonl"
        if exact_path.exists():
            try:
                session = Session.from_path(exact_path)
                if session.message_count > 0:
                    return SessionLookupResult(
                        uuid=session.uuid,
                        slug=session.slug,
                        project_encoded_name=encoded_name,
                        project_path=project_path,
                        message_count=session.message_count,
                        start_time=session.start_time,
                        end_time=session.end_time,
                        initial_prompt=get_initial_prompt(session, max_length=500),
                        matched_by="uuid",
                    )
            except Exception:
                pass

        # Try UUID prefix match
        for jsonl_path in project.project_dir.glob("*.jsonl"):
            stem = jsonl_path.stem
            if "-" not in stem:
                continue
            if stem.startswith(identifier):
                try:
                    session = Session.from_path(jsonl_path)
                    if session.message_count > 0:
                        return SessionLookupResult(
                            uuid=session.uuid,
                            slug=session.slug,
                            project_encoded_name=encoded_name,
                            project_path=project_path,
                            message_count=session.message_count,
                            start_time=session.start_time,
                            end_time=session.end_time,
                            initial_prompt=get_initial_prompt(session, max_length=500),
                            matched_by="uuid_prefix",
                        )
                except Exception:
                    continue

        # Try sessions-index.json for UUID matching
        index = project.load_sessions_index()
        if index and index.entries:
            for entry in index.entries:
                if entry.session_id.startswith(identifier) or entry.session_id == identifier:
                    jsonl_path = project.project_dir / f"{entry.session_id}.jsonl"
                    slug = None
                    if jsonl_path.exists():
                        try:
                            session = Session.from_path(jsonl_path)
                            slug = session.slug
                        except Exception:
                            pass
                    return SessionLookupResult(
                        uuid=entry.session_id,
                        slug=slug,
                        project_encoded_name=encoded_name,
                        project_path=entry.project_path or project_path,
                        message_count=entry.message_count,
                        start_time=entry.created,
                        end_time=entry.modified,
                        initial_prompt=get_initial_prompt_from_index(entry.first_prompt),
                        matched_by="uuid_prefix"
                        if entry.session_id.startswith(identifier)
                        else "uuid",
                    )
    else:
        # Slug match
        slug_cache = _get_slug_cache(project)
        if identifier in slug_cache:
            session_uuid = slug_cache[identifier]
            jsonl_path = project.project_dir / f"{session_uuid}.jsonl"
            if jsonl_path.exists():
                try:
                    session = Session.from_path(jsonl_path)
                    return SessionLookupResult(
                        uuid=session.uuid,
                        slug=session.slug,
                        project_encoded_name=encoded_name,
                        project_path=project_path,
                        message_count=session.message_count,
                        start_time=session.start_time,
                        end_time=session.end_time,
                        initial_prompt=get_initial_prompt(session, max_length=500),
                        matched_by="slug",
                    )
                except Exception:
                    pass

    return None


@router.get("/{encoded_name}/sessions/lookup")
@cacheable(max_age=30, stale_while_revalidate=60, private=True)
def lookup_session(
    encoded_name: str,
    identifier: str,
    request: Request,
):
    """
    Fast session lookup by slug or UUID prefix.

    This endpoint is optimized for the session page load flow, avoiding
    the need to fetch all sessions just to find one by slug/UUID.

    Matching priority:
    1. Exact slug match (from sessions-index.json or JSONL)
    2. UUID prefix match (first N characters of UUID)
    3. Exact UUID match

    Args:
        encoded_name: URL-encoded project path or project slug
        identifier: Session slug or UUID prefix to find

    Returns:
        SessionLookupResult with session UUID and basic metadata

    Raises:
        HTTPException: 404 if no matching session found
    """
    from schemas import SessionLookupResult

    encoded_name = resolve_project_identifier(encoded_name)
    try:
        project = Project.from_encoded_name(encoded_name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Project not found: {e}") from e

    if not project.exists:
        raise HTTPException(status_code=404, detail="Project directory not found")

    # SQLite fast path
    try:
        from db.connection import sqlite_read
        from db.queries import query_session_lookup

        with sqlite_read() as conn:
            if conn is not None:
                result = query_session_lookup(conn, encoded_name, identifier)
                if result:
                    return SessionLookupResult(
                        uuid=result["uuid"],
                        slug=result.get("slug"),
                        project_encoded_name=result["project_encoded_name"],
                        project_path=result.get("project_path", project.path),
                        message_count=result["message_count"],
                        start_time=result.get("start_time"),
                        end_time=result.get("end_time"),
                        initial_prompt=result.get("initial_prompt"),
                        matched_by=result["matched_by"],
                    )
    except Exception as e:
        logger.warning("SQLite session lookup failed, falling back: %s", e)

    # Determine if identifier looks like a UUID (hex chars and dashes)
    # This helps us optimize - UUID lookups can skip slug scanning
    is_uuid_like = all(c in "0123456789abcdef-" for c in identifier.lower())

    # Search main project first, then worktree projects
    result = _lookup_session_in_project(
        project, identifier, is_uuid_like, encoded_name, project.path
    )
    if result:
        return result

    # Worktree fallback: search worktree dirs mapped to this project
    wt_encodeds = get_worktree_mappings_for_project(encoded_name)
    for wt_enc in wt_encodeds:
        try:
            wt_project = Project.from_encoded_name(wt_enc, skip_path_recovery=True)
        except Exception:
            continue
        result = _lookup_session_in_project(
            wt_project, identifier, is_uuid_like, encoded_name, project.path
        )
        if result:
            return result

    # No matching session found through any path
    raise HTTPException(
        status_code=404,
        detail=f"No session found matching '{identifier}' in project",
    )


@router.get("/{encoded_name}/chains")
@cacheable(max_age=120, stale_while_revalidate=300, private=True)
def get_project_chains(encoded_name: str, request: Request) -> ProjectChainsResponse:
    """
    Get batch chain data for all sessions in a project.

    This endpoint computes session chains (resumed sessions sharing the same slug)
    for all sessions in a project in a single request, avoiding N+1 queries
    from the frontend.

    Returns chain info for each session and full chain data for display.
    """
    encoded_name = resolve_project_identifier(encoded_name)
    try:
        project = Project.from_encoded_name(encoded_name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Project not found: {e}") from e

    if not project.exists:
        raise HTTPException(status_code=404, detail="Project directory not found")

    # SQLite fast path
    try:
        from db.connection import sqlite_read
        from db.queries import query_project_chains

        with sqlite_read() as conn:
            if conn is not None:
                data = query_project_chains(conn, encoded_name)

                session_chains: dict[str, SessionChainInfo] = {}
                chains: list[SessionChainSchema] = []

                for slug, slug_sessions in data["chains"].items():
                    chain_length = len(slug_sessions)
                    nodes: list[SessionChainNodeSchema] = []
                    root_uuid = slug_sessions[0]["uuid"]

                    for idx, s in enumerate(slug_sessions):
                        is_root = idx == 0
                        is_latest = idx == chain_length - 1
                        parent_uuid = slug_sessions[idx - 1]["uuid"] if idx > 0 else None
                        children_uuids = (
                            [slug_sessions[idx + 1]["uuid"]] if idx < chain_length - 1 else []
                        )

                        session_chains[s["uuid"]] = SessionChainInfo(
                            chain_id=slug,
                            chain_position=idx,
                            chain_length=chain_length,
                            is_root=is_root,
                            is_latest=is_latest,
                            parent_uuid=parent_uuid,
                            detected_via="slug_match",
                        )

                        nodes.append(
                            SessionChainNodeSchema(
                                uuid=s["uuid"],
                                slug=slug,
                                start_time=s.get("start_time"),
                                end_time=s.get("end_time"),
                                is_current=False,
                                chain_depth=idx,
                                parent_uuid=parent_uuid,
                                children_uuids=children_uuids,
                                was_compacted=bool(s.get("was_compacted", 0)),
                                is_continuation_marker=bool(s.get("is_continuation_marker", 0)),
                                message_count=s.get("message_count", 0),
                                initial_prompt=s.get("initial_prompt"),
                            )
                        )

                    chains.append(
                        SessionChainSchema(
                            current_session_uuid=root_uuid,
                            nodes=nodes,
                            root_uuid=root_uuid,
                            total_sessions=chain_length,
                            max_depth=chain_length - 1,
                            total_compactions=sum(
                                s.get("compaction_count", 0) for s in slug_sessions
                            ),
                        )
                    )

                single_sessions = data["total_sessions"] - data["chained_sessions"]

                return ProjectChainsResponse(
                    project_encoded_name=encoded_name,
                    session_chains=session_chains,
                    chains=chains,
                    total_sessions=data["total_sessions"],
                    chained_sessions=data["chained_sessions"],
                    single_sessions=single_sessions,
                )
    except Exception as e:
        logger.warning("SQLite project chains query failed, falling back: %s", e)

    sessions = project.list_sessions()
    # Filter out empty sessions
    sessions = [s for s in sessions if s.message_count > 0]

    # Group sessions by slug
    slug_to_sessions: dict[str, list[Session]] = {}
    for session in sessions:
        slug = session.slug
        if slug:
            if slug not in slug_to_sessions:
                slug_to_sessions[slug] = []
            slug_to_sessions[slug].append(session)

    # Build chain info and full chains
    session_chains: dict[str, SessionChainInfo] = {}
    chains: list[SessionChainSchema] = []
    chained_sessions = 0
    single_sessions = 0

    for slug, slug_sessions in slug_to_sessions.items():
        if len(slug_sessions) < 2:
            single_sessions += len(slug_sessions)
            continue

        # Sort by start time (oldest first)
        slug_sessions.sort(key=lambda s: normalize_timezone(s.start_time))
        chain_length = len(slug_sessions)
        chained_sessions += chain_length

        # Build chain nodes
        nodes: list[SessionChainNodeSchema] = []
        root_uuid = slug_sessions[0].uuid

        for idx, session in enumerate(slug_sessions):
            is_root = idx == 0
            is_latest = idx == chain_length - 1
            parent_uuid = slug_sessions[idx - 1].uuid if idx > 0 else None
            children_uuids = [slug_sessions[idx + 1].uuid] if idx < chain_length - 1 else []

            # Build individual session chain info
            session_chains[session.uuid] = SessionChainInfo(
                chain_id=slug,
                chain_position=idx,
                chain_length=chain_length,
                is_root=is_root,
                is_latest=is_latest,
                parent_uuid=parent_uuid,
                detected_via="slug_match",
            )

            # Get initial prompt
            initial_prompt = get_initial_prompt(session, max_length=200)

            nodes.append(
                SessionChainNodeSchema(
                    uuid=session.uuid,
                    slug=session.slug,
                    start_time=session.start_time,
                    end_time=session.end_time,
                    is_current=False,  # No specific "current" in batch view
                    chain_depth=idx,
                    parent_uuid=parent_uuid,
                    children_uuids=children_uuids,
                    was_compacted=session.was_compacted,
                    is_continuation_marker=session.is_continuation_marker,
                    message_count=session.message_count,
                    initial_prompt=initial_prompt,
                )
            )

        # Create full chain
        chains.append(
            SessionChainSchema(
                current_session_uuid=root_uuid,
                nodes=nodes,
                root_uuid=root_uuid,
                total_sessions=chain_length,
                max_depth=chain_length - 1,
                total_compactions=sum(s.compaction_summary_count for s in slug_sessions),
            )
        )

    return ProjectChainsResponse(
        project_encoded_name=encoded_name,
        session_chains=session_chains,
        chains=chains,
        total_sessions=len(sessions),
        chained_sessions=chained_sessions,
        single_sessions=single_sessions,
    )


@router.get("/{encoded_name}/branches")
@cacheable(max_age=60, stale_while_revalidate=120, private=True)
def get_project_branches(encoded_name: str, request: Request):
    """
    Get aggregated branch information for a project.

    Returns all branches that sessions have touched, with session counts
    and active status (branch used in the most recent session).

    Phase 3: Moderate cache (60s) - branch data changes infrequently.
    """
    encoded_name = resolve_project_identifier(encoded_name)
    try:
        project = Project.from_encoded_name(encoded_name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Project not found: {e}") from e

    if not project.exists:
        raise HTTPException(status_code=404, detail="Project directory not found")

    # SQLite fast path
    try:
        from db.connection import sqlite_read
        from db.queries import query_project_branches

        with sqlite_read() as conn:
            if conn is not None:
                data = query_project_branches(conn, encoded_name)

                active_branch = data["active_branch"]
                branches = []
                active_branches = []

                # Fetch session UUIDs per branch
                uuid_rows = conn.execute(
                    """SELECT git_branch, uuid FROM sessions
                    WHERE project_encoded_name = :project AND git_branch IS NOT NULL
                    ORDER BY git_branch, start_time DESC""",
                    {"project": encoded_name},
                ).fetchall()
                sessions_by_branch = {}
                for row in uuid_rows:
                    branch = row["git_branch"]
                    if branch not in sessions_by_branch:
                        sessions_by_branch[branch] = []
                    sessions_by_branch[branch].append(row["uuid"])

                for b in data["branches"]:
                    is_active = b["name"] == active_branch
                    branches.append(
                        BranchSummary(
                            name=b["name"],
                            session_count=b["session_count"],
                            last_active=b["last_active"],
                            is_active=is_active,
                        )
                    )
                    if is_active:
                        active_branches.append(b["name"])

                return ProjectBranchesResponse(
                    branches=branches,
                    active_branches=active_branches,
                    sessions_by_branch=sessions_by_branch,
                )
    except Exception as e:
        logger.warning("SQLite project branches query failed, falling back: %s", e)

    # Aggregate: branch_name -> {session_uuids, last_active}
    branch_data: dict[str, dict] = {}
    most_recent_session_time: Optional[datetime] = None
    most_recent_session_branches: set[str] = set()

    for session in project.list_sessions():
        branches = session.get_git_branches()
        session_end = session.end_time or session.start_time

        # Track the most recent session and its branches
        if session_end:
            session_end = normalize_timezone(session_end)
            if most_recent_session_time is None or session_end > most_recent_session_time:
                most_recent_session_time = session_end
                most_recent_session_branches = set(branches)

        for branch in branches:
            if branch not in branch_data:
                branch_data[branch] = {"session_uuids": [], "last_active": None}

            branch_data[branch]["session_uuids"].append(session.uuid)

            # Track most recent activity for this branch
            if session_end:
                current_last = branch_data[branch]["last_active"]
                if current_last is None or session_end > current_last:
                    branch_data[branch]["last_active"] = session_end

    # Build response
    branches = []
    active_branches = []
    sessions_by_branch = {}

    for name, data in sorted(branch_data.items()):
        last_active = data["last_active"]
        # A branch is "active" if it was used in the most recent session
        is_active = name in most_recent_session_branches

        branches.append(
            BranchSummary(
                name=name,
                session_count=len(data["session_uuids"]),
                last_active=last_active,
                is_active=is_active,
            )
        )

        if is_active:
            active_branches.append(name)

        sessions_by_branch[name] = data["session_uuids"]

    # Sort branches by last_active (most recent first)
    branches.sort(
        key=lambda b: normalize_timezone(b.last_active),
        reverse=True,
    )

    return ProjectBranchesResponse(
        branches=branches,
        active_branches=active_branches,
        sessions_by_branch=sessions_by_branch,
    )


@router.get("/{encoded_name}/analytics", response_model=ProjectAnalytics)
@cacheable(max_age=120, stale_while_revalidate=300, private=True)
def get_project_analytics(
    encoded_name: str,
    request: Request,
    start_ts: Optional[int] = None,
    end_ts: Optional[int] = None,
):
    """
    Get comprehensive analytics for a project, optionally filtered by time range.

    Phase 3: Moderate cache (2min) - aggregated computed data.
    Phase 4: Uses early date filtering when date range specified.
    Phase 6: Simplified timestamp-based filtering (no timezone math needed).
    """
    encoded_name = resolve_project_identifier(encoded_name)
    try:
        project = Project.from_encoded_name(encoded_name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Project not found: {e}") from e

    if not project.exists:
        raise HTTPException(status_code=404, detail="Project directory not found")

    # Parse timestamp parameters to UTC datetimes
    start_dt, end_dt = parse_timestamp_range(start_ts, end_ts)

    # SQLite fast path (reuse analytics router's implementation)
    try:
        from routers.analytics import _get_analytics_sqlite

        sqlite_result = _get_analytics_sqlite(encoded_name, start_dt, end_dt, 0)
        if sqlite_result is not None:
            return sqlite_result
    except Exception:
        pass

    # Phase 4: Use early date filtering when date range specified
    if start_dt or end_dt:
        sessions = project.list_sessions_filtered(start_date=start_dt, end_date=end_dt)
    else:
        sessions = project.list_sessions()

    return _calculate_analytics_from_sessions(sessions)


@router.get("/projects/{encoded_name}/agents", response_model=list[AgentSummary])
@cacheable(max_age=60, stale_while_revalidate=120, private=True)
def get_project_agents(encoded_name: str, request: Request) -> list[AgentSummary]:
    """
    List agents specific to a project (stored in {project_path}/.claude/agents/).

    This is different from the global agents at ~/.claude/agents/.
    Returns agents defined within the project's directory structure.

    Args:
        encoded_name: URL-encoded project name
        request: FastAPI request object (for caching support)

    Returns:
        List of agent summaries sorted alphabetically by name

    Raises:
        HTTPException: 404 if project not found
    """
    encoded_name = resolve_project_identifier(encoded_name)
    try:
        project = Project.from_encoded_name(encoded_name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Project not found: {encoded_name}") from e

    # Project-specific agents directory: {project_path}/.claude/agents/
    project_path = Path(project.path)
    agents_dir = project_path / ".claude" / "agents"

    if not agents_dir.exists():
        return []

    agents: list[AgentSummary] = []

    try:
        for file_path in agents_dir.glob("*.md"):
            try:
                stat = file_path.stat()
                agents.append(
                    AgentSummary(
                        name=file_path.stem,
                        size_bytes=stat.st_size,
                        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                    )
                )
            except OSError:
                continue
    except OSError:
        return []

    # Sort alphabetically by name
    return sorted(agents, key=lambda a: a.name.lower())


@router.get("/projects/{encoded_name}/skills", response_model=list[SkillItem])
@cacheable(max_age=60, stale_while_revalidate=120, private=True)
def get_project_skills(
    encoded_name: str, path: str = "", request: Request = None
) -> list[SkillItem]:
    """
    List skills specific to a project (stored in {project_path}/.claude/skills/).

    This is different from the global skills at ~/.claude/skills/.
    Returns skills defined within the project's directory structure.

    Args:
        encoded_name: URL-encoded project name
        path: Optional subdirectory path relative to skills directory
        request: FastAPI request object (for caching support)

    Returns:
        List of skill items (files and directories) sorted by name

    Raises:
        HTTPException: 404 if project or path not found
    """
    encoded_name = resolve_project_identifier(encoded_name)
    try:
        project = Project.from_encoded_name(encoded_name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Project not found: {encoded_name}") from e

    # Project-specific skills directory: {project_path}/.claude/skills/
    project_path = Path(project.path)
    base_skills_dir = project_path / ".claude" / "skills"

    if not base_skills_dir.exists():
        return []

    # Determine target directory
    if not path:
        target_dir = base_skills_dir
    else:
        # Validate and sanitize path (prevent directory traversal)
        clean_path = path.strip("/").strip()
        if ".." in clean_path or not clean_path:
            raise HTTPException(status_code=400, detail="Invalid path")

        target_dir = (base_skills_dir / clean_path).resolve()

        # Ensure the resolved path is still within skills directory
        try:
            target_dir.relative_to(base_skills_dir)
        except ValueError as e:
            raise HTTPException(
                status_code=400, detail="Invalid path: outside skills directory"
            ) from e

    if not target_dir.exists():
        raise HTTPException(status_code=404, detail="Path not found")

    if not target_dir.is_dir():
        raise HTTPException(status_code=400, detail="Path is not a directory")

    items: list[SkillItem] = []

    try:
        for entry in target_dir.iterdir():
            # Skip hidden files and directories
            if entry.name.startswith("."):
                continue

            try:
                item_type = "directory" if entry.is_dir() else "file"
                rel_path = str(entry.relative_to(base_skills_dir))

                if item_type == "file":
                    stat = entry.stat()
                    items.append(
                        SkillItem(
                            name=entry.name,
                            path=rel_path,
                            type=item_type,
                            size_bytes=stat.st_size,
                            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                        )
                    )
                else:
                    items.append(
                        SkillItem(
                            name=entry.name,
                            path=rel_path,
                            type=item_type,
                        )
                    )
            except OSError:
                continue
    except OSError:
        return []

    # Sort: directories first, then files, alphabetically within each group
    return sorted(items, key=lambda x: (x.type == "file", x.name.lower()))


# ============================================================================
# Project Memory Endpoint
# ============================================================================


@router.get("/{encoded_name}/memory", response_model=ProjectMemoryResponse)
@cacheable(max_age=30, stale_while_revalidate=60)
async def get_project_memory(encoded_name: str, request: Request):
    """
    Get the MEMORY.md file for a project.

    Returns the markdown content of the project's memory file stored at
    ~/.claude/projects/{encoded_name}/memory/MEMORY.md
    """
    encoded_name = resolve_project_identifier(encoded_name)
    from config import settings

    memory_dir = settings.projects_dir / encoded_name / "memory"
    memory_file = memory_dir / "MEMORY.md"

    if not memory_file.exists():
        return ProjectMemoryResponse(
            content="",
            word_count=0,
            size_bytes=0,
            modified=datetime.now(timezone.utc),
            exists=False,
        )

    try:
        stat = memory_file.stat()
        content = memory_file.read_text(encoding="utf-8")
        word_count = len(content.split())

        return ProjectMemoryResponse(
            content=content,
            word_count=word_count,
            size_bytes=stat.st_size,
            modified=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            exists=True,
        )
    except OSError as e:
        logger.error(f"Error reading memory file for {encoded_name}: {e}")
        raise HTTPException(status_code=500, detail="Failed to read memory file") from e


# ============================================================================
# Remote Sessions (Team sync)
# ============================================================================


@router.get("/{encoded_name}/remote-sessions")
async def project_remote_sessions(encoded_name: str):
    """Get remote sessions for a project, grouped by remote user.

    Returns full SessionSummary data (including cost, duration, models, tools)
    from SQLite for each remote session, grouped by user.
    """
    import json
    import re
    from collections import defaultdict

    ALLOWED_NAME = re.compile(r"^[a-zA-Z0-9_\-]+$")
    if not ALLOWED_NAME.match(encoded_name) or len(encoded_name) > 512:
        raise HTTPException(400, "Invalid project name")

    # Query SQLite for rich remote session data (cost, duration, models, tools).
    try:
        from db.connection import sqlite_read
        from db.queries import _parse_json_list

        with sqlite_read() as conn:
            if conn is None:
                return {"users": []}

            rows = conn.execute(
                """SELECT
                    s.uuid, s.slug, s.message_count, s.start_time, s.end_time,
                    s.duration_seconds, s.models_used, s.subagent_count,
                    s.initial_prompt, s.git_branch, s.session_titles,
                    s.input_tokens, s.output_tokens, s.total_cost,
                    s.session_source,
                    s.source, s.remote_user_id, s.remote_machine_id
                FROM sessions s
                WHERE s.project_encoded_name = :project
                    AND s.source = 'remote'
                    AND s.message_count > 0
                ORDER BY s.start_time DESC""",
                {"project": encoded_name},
            ).fetchall()

            if not rows:
                return {"users": []}

            # Bulk-fetch tools_used for all remote sessions in one query
            uuids = [r["uuid"] for r in rows]
            placeholders = ",".join("?" * len(uuids))
            tool_rows = conn.execute(
                f"SELECT session_uuid, tool_name, count FROM session_tools WHERE session_uuid IN ({placeholders})",
                uuids,
            ).fetchall()
            tools_by_session: dict[str, dict[str, int]] = defaultdict(dict)
            for tr in tool_rows:
                tools_by_session[tr["session_uuid"]][tr["tool_name"]] = tr["count"]

            # Build SessionSummary objects grouped by user
            user_sessions: dict[str, list[SessionSummary]] = defaultdict(list)
            user_machine: dict[str, str | None] = {}

            for row in rows:
                user_id = row["remote_user_id"] or "unknown"
                if user_id not in user_machine:
                    user_machine[user_id] = row["remote_machine_id"]

                uuid = row["uuid"]
                user_sessions[user_id].append(
                    SessionSummary(
                        uuid=uuid,
                        slug=row["slug"],
                        message_count=row["message_count"],
                        start_time=row["start_time"],
                        end_time=row["end_time"],
                        duration_seconds=row["duration_seconds"],
                        models_used=_parse_json_list(row["models_used"]),
                        subagent_count=row["subagent_count"] or 0,
                        has_todos=False,  # Remote sessions don't sync todo data
                        initial_prompt=row["initial_prompt"],
                        git_branches=[row["git_branch"]] if row["git_branch"] else [],
                        session_titles=_parse_json_list(row["session_titles"]),
                        total_input_tokens=row["input_tokens"],
                        total_output_tokens=row["output_tokens"],
                        total_cost=row["total_cost"],
                        tools_used=tools_by_session.get(uuid, {}),
                        session_source=row["session_source"],
                        source="remote",
                        remote_user_id=row["remote_user_id"],
                        remote_machine_id=row["remote_machine_id"],
                    )
                )

    except Exception as e:
        logger.warning("SQLite remote sessions query failed: %s", e)
        return {"users": []}

    # Load manifest data for synced_at timestamps and build response
    remote_base = Path.home() / ".claude_karma" / "remote-sessions"
    users = []
    for user_id, sessions in user_sessions.items():
        synced_at = None
        manifest_path = remote_base / user_id / encoded_name / "manifest.json"
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text())
                synced_at = manifest.get("synced_at")
            except (json.JSONDecodeError, OSError):
                pass

        users.append({
            "user_id": user_id,
            "machine_id": user_machine.get(user_id),
            "synced_at": synced_at,
            "session_count": len(sessions),
            "sessions": sessions,
        })

    return {"users": users}
