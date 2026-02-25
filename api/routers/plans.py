"""
Plans router - view Claude Code plan markdown files.

Provides endpoints for listing and reading plan files stored in
~/.claude/plans/ directory. Plans are created during Claude Code's
"plan mode" and contain implementation strategies.

Phase 3: HTTP caching with Cache-Control headers.
Plans change infrequently, so longer cache times are appropriate.
"""

import logging
import math
import sqlite3
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request

# Add models and api to path
api_path = Path(__file__).parent.parent
models_path = api_path.parent.parent
sys.path.insert(0, str(api_path))
sys.path.insert(0, str(models_path))

from http_caching import cacheable
from models import Plan, get_plans_dir, load_all_plans, load_plan
from schemas import (
    PlanDetail,
    PlanListResponse,
    PlanRelatedSession,
    PlanSessionContext,
    PlanSummary,
    PlanWithContext,
)
from utils import list_all_projects

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Converter Functions
# =============================================================================


def plan_to_summary(plan: Plan) -> PlanSummary:
    """
    Convert a Plan model to PlanSummary for API responses.

    Args:
        plan: Plan instance

    Returns:
        PlanSummary schema for API response
    """
    return PlanSummary(
        slug=plan.slug,
        title=plan.extract_title(),
        preview=plan.content[:500] if plan.content else "",
        word_count=plan.word_count,
        created=plan.created,
        modified=plan.modified,
        size_bytes=plan.size_bytes,
    )


def plan_to_detail(plan: Plan) -> PlanDetail:
    """
    Convert a Plan model to PlanDetail for API responses.

    Args:
        plan: Plan instance

    Returns:
        PlanDetail schema with full content
    """
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


def find_session_context_for_slug(slug: str) -> PlanSessionContext | None:
    """
    Find session context for a given slug by scanning all projects.

    Args:
        slug: Session slug to match against plan slug

    Returns:
        PlanSessionContext if a matching session is found, None otherwise
    """
    for project in list_all_projects():
        if not project.exists:
            continue

        for session in project.list_sessions():
            try:
                session_slug = session.slug
                if session_slug == slug:
                    # Get git branches for this session
                    git_branches = list(session.get_git_branches())
                    return PlanSessionContext(
                        session_uuid=session.uuid,
                        session_slug=session_slug,
                        project_encoded_name=project.encoded_name,
                        project_path=project.path,
                        git_branches=git_branches,
                    )
            except Exception:
                # Skip sessions that fail to load
                continue

    return None


def _row_to_context(row: dict) -> PlanSessionContext:
    """Convert a SQLite session row dict to PlanSessionContext."""
    return PlanSessionContext(
        session_uuid=row["uuid"],
        session_slug=row["slug"],
        project_encoded_name=row["project_encoded_name"],
        project_path=row["project_path"] or "",
        git_branches=[row["git_branch"]] if row.get("git_branch") else [],
    )


def _get_plan_context_sqlite(slug: str) -> PlanSessionContext | None:
    """O(1) slug lookup via SQLite. Lazy imports db module."""
    from db.connection import sqlite_read
    from db.queries import query_session_by_slug

    with sqlite_read() as conn:
        if conn is None:
            return None
        row = query_session_by_slug(conn, slug)
        return _row_to_context(row) if row else None


def _build_slug_index_sqlite(slugs: list[str]) -> dict[str, PlanSessionContext]:
    """Batch slug lookup via SQLite. Single query for all plan slugs."""
    from db.connection import sqlite_read
    from db.queries import query_sessions_by_slugs

    with sqlite_read() as conn:
        if conn is None:
            return {}
        rows = query_sessions_by_slugs(conn, slugs)
        return {slug: _row_to_context(row) for slug, row in rows.items()}


def build_slug_session_index() -> dict[str, PlanSessionContext]:
    """
    Scan ALL sessions once and build a slug-to-context dict.

    JSONL fallback: replaces N calls to find_session_context_for_slug()
    with a single pass over all sessions.
    """
    slug_index: dict[str, PlanSessionContext] = {}
    for project in list_all_projects():
        if not project.exists:
            continue
        for session in project.list_sessions():
            try:
                session_slug = session.slug
                if session_slug and session_slug not in slug_index:
                    git_branches = list(session.get_git_branches())
                    slug_index[session_slug] = PlanSessionContext(
                        session_uuid=session.uuid,
                        session_slug=session_slug,
                        project_encoded_name=project.encoded_name,
                        project_path=project.path,
                        git_branches=git_branches,
                    )
            except Exception:
                continue
    return slug_index


# =============================================================================
# Endpoints
# =============================================================================


@router.get("", response_model=list[PlanSummary])
@cacheable(max_age=300, stale_while_revalidate=600, private=True)
def list_plans(request: Request) -> list[PlanSummary]:
    """
    List all plans from ~/.claude/plans directory.

    Plans are sorted by modification time (newest first).
    Each plan summary includes:
    - slug: Plan identifier
    - title: First h1 header from markdown
    - preview: First 500 characters
    - word_count: Total words in plan
    - created/modified: File timestamps
    - size_bytes: File size

    Cache: 5 minutes (plans change infrequently)
    """
    plans_dir = get_plans_dir()

    if not plans_dir.exists():
        logger.debug(f"Plans directory does not exist: {plans_dir}")
        return []

    plans = load_all_plans()
    return [plan_to_summary(p) for p in plans]


@router.get("/stats")
@cacheable(max_age=300, stale_while_revalidate=600, private=True)
def get_plans_stats(request: Request) -> dict:
    """
    Get aggregate statistics about plans.

    Returns:
        - total_plans: Number of plan files
        - total_words: Sum of all plan word counts
        - total_size_bytes: Sum of all plan sizes
        - oldest_plan: Slug of oldest plan
        - newest_plan: Slug of newest plan
    """
    plans = load_all_plans()

    if not plans:
        return {
            "total_plans": 0,
            "total_words": 0,
            "total_size_bytes": 0,
            "oldest_plan": None,
            "newest_plan": None,
        }

    # Plans are sorted by modified (newest first)
    newest = plans[0] if plans else None
    oldest = plans[-1] if plans else None

    return {
        "total_plans": len(plans),
        "total_words": sum(p.word_count for p in plans),
        "total_size_bytes": sum(p.size_bytes for p in plans),
        "oldest_plan": oldest.slug if oldest else None,
        "newest_plan": newest.slug if newest else None,
    }


@router.get("/with-context", response_model=PlanListResponse)
@cacheable(max_age=300, stale_while_revalidate=600, private=True)
def list_plans_with_context(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(24, ge=1, le=100, description="Plans per page"),
    search: str = Query("", description="Search query for slug, title, preview, project path"),
    project: str = Query("", description="Filter by project encoded name"),
    branch: str = Query("", description="Filter by git branch"),
) -> PlanListResponse:
    """
    List all plans with their associated session and project context.

    For each plan, tries to find a session with matching slug by scanning
    all projects. Returns enriched plan data with session_context populated
    when a matching session is found.

    Supports server-side pagination, search, and filtering:
    - search: Case-insensitive search across slug, title, preview, and project path
    - project: Filter by project encoded name
    - branch: Filter by git branch name
    - page/per_page: Pagination controls

    Plans are sorted by modification time (newest first).

    Cache: 5 minutes (plans and session relationships change infrequently)
    """
    plans_dir = get_plans_dir()

    if not plans_dir.exists():
        logger.debug(f"Plans directory does not exist: {plans_dir}")
        return PlanListResponse(plans=[], total=0, page=page, per_page=per_page, total_pages=0)

    plans = load_all_plans()
    if not plans:
        return PlanListResponse(plans=[], total=0, page=page, per_page=per_page, total_pages=0)

    slugs = [p.slug for p in plans]

    # Build slug index: SQLite first, then JSONL single-pass fallback
    slug_index: dict[str, PlanSessionContext] = {}
    try:
        slug_index = _build_slug_index_sqlite(slugs)
    except sqlite3.Error as e:
        logger.warning("SQLite batch slug lookup failed, falling back: %s", e)

    if not slug_index:
        slug_index = build_slug_session_index()

    # Build full list with context
    all_plans: list[PlanWithContext] = []
    for plan in plans:
        all_plans.append(
            PlanWithContext(
                slug=plan.slug,
                title=plan.extract_title(),
                preview=plan.content[:500] if plan.content else "",
                word_count=plan.word_count,
                created=plan.created,
                modified=plan.modified,
                size_bytes=plan.size_bytes,
                session_context=slug_index.get(plan.slug),
            )
        )

    # Apply search filter (supports comma-separated tokens with AND logic)
    if search:
        # Split comma-separated tokens and decode
        from urllib.parse import unquote

        tokens = [unquote(t.strip()).lower() for t in search.split(",") if t.strip()]

        if tokens:
            filtered_plans = []
            for plan in all_plans:
                # Build searchable text for this plan
                searchable = plan.slug.lower()
                if plan.title:
                    searchable += " " + plan.title.lower()
                if plan.preview:
                    searchable += " " + plan.preview.lower()
                if plan.session_context and plan.session_context.project_path:
                    searchable += " " + plan.session_context.project_path.lower()

                # ALL tokens must match (AND logic)
                if all(token in searchable for token in tokens):
                    filtered_plans.append(plan)
            all_plans = filtered_plans

    # Apply project filter
    if project:
        all_plans = [
            p
            for p in all_plans
            if p.session_context and p.session_context.project_encoded_name == project
        ]

    # Apply branch filter
    if branch:
        all_plans = [
            p
            for p in all_plans
            if p.session_context
            and p.session_context.git_branches
            and branch in p.session_context.git_branches
        ]

    # Paginate
    total = len(all_plans)
    total_pages = math.ceil(total / per_page) if total > 0 else 0
    # Clamp page to valid range (prevents empty page on stale bookmarks)
    page = min(page, max(total_pages, 1))
    start = (page - 1) * per_page
    end = start + per_page
    paginated = all_plans[start:end]

    return PlanListResponse(
        plans=paginated,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


@router.get("/{slug}", response_model=PlanDetail)
@cacheable(max_age=300, stale_while_revalidate=600, private=True)
def get_plan(slug: str, request: Request) -> PlanDetail:
    """
    Get a specific plan by slug.

    Args:
        slug: Plan identifier (filename without .md)

    Returns:
        Full plan content and metadata

    Raises:
        404: Plan not found
    """
    plan = load_plan(slug)

    if not plan:
        raise HTTPException(
            status_code=404,
            detail=f"Plan '{slug}' not found in ~/.claude/plans/",
        )

    return plan_to_detail(plan)


@router.get("/{slug}/context", response_model=PlanSessionContext | None)
@cacheable(max_age=300, stale_while_revalidate=600, private=True)
def get_plan_context(slug: str, request: Request) -> PlanSessionContext | None:
    """
    Get session context for a single plan by slug.

    O(1) via SQLite index lookup. Falls back to JSONL scan.
    """
    try:
        result = _get_plan_context_sqlite(slug)
        if result is not None:
            return result
    except sqlite3.Error as e:
        logger.warning("SQLite slug lookup failed, falling back: %s", e)

    return find_session_context_for_slug(slug)


@router.get("/{slug}/sessions", response_model=list[PlanRelatedSession])
@cacheable(max_age=300, stale_while_revalidate=600, private=True)
def get_plan_sessions(slug: str, request: Request) -> list[PlanRelatedSession]:
    """
    Find all sessions that interacted with a plan file.

    Searches all sessions across all projects for file operations
    (Read, Write, Edit) on the plan file at ~/.claude/plans/{slug}.md.

    This helps users understand which sessions have read or modified
    a plan, enabling navigation to those sessions.

    Args:
        slug: Plan identifier (filename without .md)

    Returns:
        List of PlanRelatedSession with sessions that interacted with the plan,
        sorted by timestamp (most recent first). Excludes the session that
        created the plan (available via /plans/with-context).
    """
    # Verify the plan exists
    plan = load_plan(slug)
    if not plan:
        raise HTTPException(
            status_code=404,
            detail=f"Plan '{slug}' not found in ~/.claude/plans/",
        )

    # The plan file path pattern to search for
    plans_dir = get_plans_dir()
    plan_file_path = str(plans_dir / f"{slug}.md")

    # Find the session that created the plan (to exclude from results)
    creator_context = None
    try:
        creator_context = _get_plan_context_sqlite(slug)
    except Exception as e:
        logger.warning("SQLite creator lookup failed, falling back: %s", e)
    if creator_context is None:
        creator_context = find_session_context_for_slug(slug)
    creator_uuid = creator_context.session_uuid if creator_context else None

    related_sessions: list[PlanRelatedSession] = []
    seen_sessions: set[str] = set()

    # Pre-compute the byte pattern for fast JSONL pre-filtering.
    # If the slug doesn't appear in the raw file, skip expensive parsing.
    slug_needle = f"plans/{slug}.md".encode()
    max_results = 20

    # Scan all projects and sessions for file operations on this plan
    for project in list_all_projects():
        if not project.exists:
            continue

        for session in project.list_sessions():
            if len(related_sessions) >= max_results:
                break

            # Skip the creator session
            if creator_uuid and session.uuid == creator_uuid:
                continue

            # Skip if we've already processed this session
            if session.uuid in seen_sessions:
                continue

            try:
                # Fast pre-filter: check if the plan slug appears in raw JSONL bytes.
                # This eliminates >99% of sessions without parsing any messages.
                jsonl_file = session.jsonl_path
                if jsonl_file.exists():
                    raw = jsonl_file.read_bytes()
                    if slug_needle not in raw:
                        continue

                # Slug found in raw bytes — parse messages to confirm and extract details
                for msg in session.iter_messages():
                    if not hasattr(msg, "content_blocks"):
                        continue

                    for block in msg.content_blocks:
                        if not hasattr(block, "name") or not hasattr(block, "input"):
                            continue

                        tool_name = block.name
                        tool_input = block.input or {}

                        # Check for file operations on the plan file
                        if tool_name in ("Read", "Write", "StrReplace", "Edit"):
                            file_path = tool_input.get("file_path") or tool_input.get("path", "")

                            # Check if this operation is on our plan file
                            if file_path and (
                                file_path == plan_file_path
                                or file_path.endswith(f"/plans/{slug}.md")
                                or file_path.endswith(f"/.claude/plans/{slug}.md")
                            ):
                                # Map tool name to operation type
                                op_map = {
                                    "Read": "read",
                                    "Write": "write",
                                    "StrReplace": "edit",
                                    "Edit": "edit",
                                }
                                operation = op_map.get(tool_name, "read")

                                related_sessions.append(
                                    PlanRelatedSession(
                                        session_uuid=session.uuid,
                                        session_slug=session.slug or session.uuid[:8],
                                        project_encoded_name=project.encoded_name,
                                        operation=operation,
                                        timestamp=msg.timestamp,
                                    )
                                )
                                seen_sessions.add(session.uuid)
                                break  # Found a match, move to next session

                    if session.uuid in seen_sessions:
                        break  # Already found, stop checking messages

            except Exception as e:
                logger.debug(f"Error scanning session {session.uuid}: {e}")
                continue

        if len(related_sessions) >= max_results:
            break

    # Sort by timestamp (most recent first)
    related_sessions.sort(key=lambda s: s.timestamp, reverse=True)

    return related_sessions
