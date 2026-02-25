"""
Skills router - manage skill files and directories.

Provides endpoints for browsing, reading, and writing skill files
stored in ~/.claude/skills/ directory.

Phase 3: HTTP caching with Cache-Control headers.
"""

import logging
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

# Add models and api to path
api_path = Path(__file__).parent.parent
models_path = api_path.parent.parent
sys.path.insert(0, str(api_path))
sys.path.insert(0, str(models_path))

from config import Settings, settings
from http_caching import cacheable
from models import Project
from parallel import run_in_thread
from schemas import (
    SessionSummary,
    SessionWithContext,
    SkillContent,
    SkillDetailResponse,
    SkillInfo,
    SkillItem,
    SkillSessionsResponse,
    SkillTrendItem,
    SkillUpdateRequest,
    UsageTrendItem,
    UsageTrendResponse,
)
from services.session_title_cache import title_cache

logger = logging.getLogger(__name__)

router = APIRouter()

# Constants
# Allow alphanumeric, hyphens, underscores, dots, and forward slashes for paths
ALLOWED_PATH_PATTERN = re.compile(r"^[a-zA-Z0-9_.\-/]+$")


# =============================================================================
# Dependencies
# =============================================================================


def get_settings() -> Settings:
    """
    Dependency to get application settings.

    Returns:
        Settings instance
    """
    return settings


def get_skills_dir(
    config: Annotated[Settings, Depends(get_settings)],
    project: Annotated[
        str | None, Query(description="Project encoded name for project-specific skills")
    ] = None,
) -> Path:
    """
    Dependency to get the skills directory.

    Args:
        config: Application settings (injected)
        project: Optional project encoded name for project-specific skills

    Returns:
        Path to skills directory (global or project-specific)
    """
    if project:
        proj = Project.from_encoded_name(project)
        return Path(proj.path) / ".claude" / "skills"
    return config.skills_dir


def validate_skill_path(path: str, skills_dir: Path, max_length: int = 500) -> Path:
    """
    Validate and sanitize skill path for security.

    Args:
        path: Relative path from skills directory
        skills_dir: Base skills directory
        max_length: Maximum path length (default: 500)

    Returns:
        Resolved absolute path within skills directory

    Raises:
        HTTPException: If path is invalid or attempts directory traversal
    """
    if not path or len(path) > max_length:
        raise HTTPException(
            status_code=400, detail=f"Path must be between 1 and {max_length} characters"
        )

    # Remove leading/trailing slashes and normalize
    clean_path = path.strip("/").strip()

    if not clean_path:
        raise HTTPException(status_code=400, detail="Invalid path")

    # Basic pattern check
    if not ALLOWED_PATH_PATTERN.match(clean_path):
        raise HTTPException(
            status_code=400,
            detail="Path must contain only alphanumeric characters, hyphens, underscores, dots, and forward slashes",
        )

    # Prevent directory traversal
    if ".." in clean_path:
        raise HTTPException(status_code=400, detail="Path traversal not allowed")

    # Resolve to absolute path
    target_path = (skills_dir / clean_path).resolve()

    # Ensure the resolved path is still within skills directory
    # We must resolve skills_dir too, in case it contains symlinks (common on macOS)
    try:
        resolved_skills_dir = skills_dir.resolve()
        target_path.relative_to(resolved_skills_dir)
    except ValueError as e:
        logger.warning(f"Path traversal attempt detected: {path}")
        raise HTTPException(status_code=400, detail="Invalid path: outside skills directory") from e

    return target_path


from utils_io import (
    delete_file_sync,
    safe_write_file,
)
from utils_io import (
    safe_read_file as _safe_read_file,
)


def safe_read_file(file_path: Path, max_size: int) -> str:
    """Read file with binary-content fallback for skills (may contain non-UTF-8)."""
    return _safe_read_file(
        file_path, max_size, binary_placeholder="(Binary content - cannot display)"
    )


@router.get("/skills", response_model=list[SkillItem])
@cacheable(max_age=30, stale_while_revalidate=60, private=True)
def list_skills(
    path: str = "",
    request: Request = None,
    skills_dir: Annotated[Path, Depends(get_skills_dir)] = None,
    config: Annotated[Settings, Depends(get_settings)] = None,
) -> list[SkillItem]:
    """
    List skills in a directory.

    If path is provided, list contents of that subdirectory.
    Otherwise, list root skills directory.

    Phase 3: Short cache (30s) - files may be edited frequently.

    Args:
        path: Optional subdirectory path relative to skills directory
        request: FastAPI request object (for caching support)
        skills_dir: Skills directory path (injected)
        config: Application settings (injected)

    Returns:
        List of skill items (files and directories) sorted by name

    Raises:
        HTTPException: 400 if path is invalid, 404 if path not found
    """
    if not path:
        # List root directory
        target_dir = skills_dir
    else:
        target_dir = validate_skill_path(path, skills_dir)

    if not target_dir.exists():
        # If root skills directory is missing, return empty list instead of 404
        if not path:
            return []
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
                # Use the entry's name directly for the relative path, not resolved path
                # This handles symlinks that point outside the skills directory
                # We only care about the location within skills_dir, not where symlinks point
                if path:
                    rel_path = f"{path.strip('/')}/{entry.name}"
                else:
                    rel_path = entry.name

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
            except OSError as e:
                logger.warning(f"Failed to process skill entry {entry}: {e}")
                continue
    except OSError as e:
        logger.error(f"Failed to list skills directory {target_dir}: {e}")
        raise HTTPException(status_code=500, detail="Failed to list skills directory") from e

    # Sort: directories first, then files, alphabetically within each group
    return sorted(items, key=lambda x: (x.type == "file", x.name.lower()))


@router.get("/skills/content", response_model=SkillContent)
@cacheable(max_age=60, stale_while_revalidate=120, private=True)
async def get_skill_content(
    path: str,
    request: Request,
    skills_dir: Annotated[Path, Depends(get_skills_dir)],
    config: Annotated[Settings, Depends(get_settings)],
) -> SkillContent:
    """
    Get content of a specific skill file.

    Phase 3: Moderate cache (60s) - skill content changes infrequently.
    Phase 4: Async file I/O via run_in_thread() for consistency.

    Args:
        path: Relative path to the skill file from skills directory
        request: FastAPI request object (for caching support)
        skills_dir: Skills directory path (injected)
        config: Application settings (injected)

    Returns:
        Skill file content and metadata

    Raises:
        HTTPException: 400 if path is invalid, 404 if file not found
    """
    target_file = validate_skill_path(path, skills_dir)

    if not target_file.exists():
        raise HTTPException(status_code=404, detail="File not found")

    if not target_file.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file")

    content = await run_in_thread(safe_read_file, target_file, config.max_skill_size)
    stat = target_file.stat()

    return SkillContent(
        name=target_file.name,
        path=path,
        content=content,
        size_bytes=stat.st_size,
        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
    )


@router.post("/skills/content", status_code=200)
async def update_skill_content(
    request_body: SkillUpdateRequest,
    skills_dir: Annotated[Path, Depends(get_skills_dir)],
    config: Annotated[Settings, Depends(get_settings)],
) -> dict:
    """
    Create or update a skill file.

    If the file already exists, it will be overwritten.
    Parent directories will be created as needed.
    Phase 4: Async file I/O via run_in_thread() for consistency.

    Args:
        request_body: Request with path and content
        skills_dir: Skills directory path (injected)
        config: Application settings (injected)

    Returns:
        Success message with file info

    Raises:
        HTTPException: 400 if path is invalid, 413 if content too large
    """
    target_file = validate_skill_path(request_body.path, skills_dir)

    # Validate content size
    content_size = len(request_body.content.encode("utf-8"))
    if content_size > config.max_skill_size:
        raise HTTPException(
            status_code=413,
            detail=f"Content too large ({content_size} bytes). Maximum is {config.max_skill_size} bytes",
        )

    # If file exists and is a directory, reject
    if target_file.exists() and target_file.is_dir():
        raise HTTPException(status_code=400, detail="Cannot write to a directory")

    # Write the file (async)
    await run_in_thread(safe_write_file, target_file, request_body.content)

    return {
        "status": "success",
        "message": "File updated successfully",
        "path": request_body.path,
        "size_bytes": content_size,
    }


@router.delete("/skills/content", status_code=204)
async def delete_skill_file(
    path: str,
    skills_dir: Annotated[Path, Depends(get_skills_dir)],
) -> None:
    """
    Delete a skill file.

    Phase 4: Async file I/O via run_in_thread() for consistency.

    Args:
        path: Relative path to the skill file from skills directory
        skills_dir: Skills directory path (injected)

    Raises:
        HTTPException: 400 if path is invalid, 404 if file not found
    """
    target_file = validate_skill_path(path, skills_dir)

    if not target_file.exists():
        raise HTTPException(status_code=404, detail="File not found")

    if not target_file.is_file():
        raise HTTPException(status_code=400, detail="Can only delete files, not directories")

    try:
        await run_in_thread(delete_file_sync, target_file)
        logger.info(f"Deleted skill file: {path}")
    except OSError as e:
        logger.error(f"Failed to delete skill file {path}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete skill file") from e


@router.get("/skills/usage")
@cacheable(max_age=60, stale_while_revalidate=120, private=True)
def get_skill_usage(
    request: Request,
    project: Annotated[
        str | None, Query(description="Project encoded name for project-specific usage")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="Max skills to return")] = 50,
) -> list[dict]:
    """
    Get skill usage statistics aggregated from session data.

    Tracks skills invoked via the Skill tool, including both file-based skills
    and plugin skills (e.g., 'oh-my-claudecode:security-review').

    Args:
        request: FastAPI request object (for caching support)
        project: Optional project encoded name for project-specific stats
        limit: Maximum number of skills to return (default: 50)

    Returns:
        List of skill usage stats sorted by usage count (descending)
    """
    # SQLite fast path
    try:
        from db.connection import sqlite_read
        from db.queries import query_skill_usage

        with sqlite_read() as conn:
            if conn is not None:
                rows = query_skill_usage(conn, project=project, limit=limit)
                results = []
                for row in rows:
                    skill_name = row["skill_name"]
                    is_plugin = ":" in skill_name
                    plugin_name = skill_name.split(":")[0] if is_plugin else None
                    results.append(
                        {
                            "name": skill_name,
                            "count": row["total_count"],
                            "is_plugin": is_plugin,
                            "plugin": plugin_name,
                        }
                    )
                return results
    except sqlite3.Error as e:
        logger.warning("SQLite skill usage query failed, falling back: %s", e)

    from collections import Counter

    from parallel import process_items_parallel
    from utils import list_all_projects

    def process_session_skills(session) -> dict[str, int]:
        """Extract skill usage from a single session."""
        try:
            return session.get_skills_used()
        except Exception:
            return {}

    # Collect all sessions to process
    sessions_to_process = []
    if project:
        # Get skill usage for a specific project
        proj = Project.from_encoded_name(project)
        sessions_to_process = list(proj.list_sessions())
    else:
        # Get skill usage across all projects
        for proj in list_all_projects():
            sessions_to_process.extend(proj.list_sessions())

    # Process sessions in parallel (16 workers like agent_analytics)
    import asyncio

    skill_dicts = asyncio.run(
        process_items_parallel(sessions_to_process, process_session_skills, max_concurrent=16)
    )

    # Aggregate results
    skills_counter: Counter[str] = Counter()
    for skill_dict in skill_dicts:
        skills_counter.update(skill_dict)

    # Format results
    results = []
    for skill_name, count in skills_counter.most_common(limit):
        # Determine if this is a plugin skill
        is_plugin = ":" in skill_name
        plugin_name = skill_name.split(":")[0] if is_plugin else None

        results.append(
            {
                "name": skill_name,
                "count": count,
                "is_plugin": is_plugin,
                "plugin": plugin_name,
            }
        )

    return results


@router.get("/skills/usage/trend", response_model=UsageTrendResponse)
@cacheable(max_age=60, stale_while_revalidate=120, private=True)
def get_skill_usage_trend(
    request: Request,
    project: Annotated[
        str | None, Query(description="Project encoded name for project-specific usage")
    ] = None,
    period: Annotated[str, Query(description="Time period: week, month, quarter, all")] = "month",
) -> UsageTrendResponse:
    """
    Get skill usage trend data with daily breakdown.

    Returns aggregated skill usage with daily trend for charting.

    Args:
        request: FastAPI request object (for caching support)
        project: Optional project encoded name for project-specific stats
        period: Time period filter (week, month, quarter, all)

    Returns:
        UsageTrendResponse with totals, per-skill breakdown, and daily trend
    """
    try:
        from db.connection import sqlite_read
        from db.queries import query_skill_usage_trend

        with sqlite_read() as conn:
            if conn is not None:
                data = query_skill_usage_trend(conn, project=project, period=period)
                return UsageTrendResponse(
                    total=data["total"],
                    by_item=data["by_item"],
                    trend=[UsageTrendItem(date=t["date"], count=t["count"]) for t in data["trend"]],
                    first_used=data["first_used"],
                    last_used=data["last_used"],
                )
    except sqlite3.Error as e:
        logger.warning("SQLite skill usage trend query failed: %s", e)

    return UsageTrendResponse()


@router.get("/skills/{skill_name}/detail", response_model=SkillDetailResponse)
@cacheable(max_age=60, stale_while_revalidate=120, private=True)
async def get_skill_detail(
    skill_name: str,
    request: Request,
    config: Annotated[Settings, Depends(get_settings)],
    per_page: Annotated[int, Query(ge=1, le=500)] = 100,
    page: Annotated[int, Query(ge=1)] = 1,
) -> SkillDetailResponse:
    """
    Get comprehensive detail for a skill: info + usage stats + trend + sessions.

    Combines skill file metadata (from get_skill_info) with SQLite usage data
    (stats, daily trend, paginated session list with subagent source tagging).

    Args:
        skill_name: Name of the skill (e.g., 'commit' or 'oh-my-claudecode:security-review')
        request: FastAPI request object (for caching support)
        config: Application settings (injected)
        per_page: Sessions per page (default: 100, max: 500)
        page: Page number (default: 1)

    Returns:
        SkillDetailResponse with all skill data combined
    """
    # 1. Get skill file info (description, content, plugin status)
    skill_info = None
    try:
        skill_info = await _resolve_skill_info(skill_name, config)
    except HTTPException:
        pass  # Skill file may not exist, but usage data might

    # 2. Get usage stats from SQLite
    usage_data = None
    try:
        from db.connection import sqlite_read
        from db.queries import query_skill_detail

        with sqlite_read() as conn:
            if conn is not None:
                usage_data = query_skill_detail(
                    conn,
                    skill_name,
                    limit=per_page,
                    offset=(page - 1) * per_page,
                )
    except Exception as e:
        logger.warning("SQLite skill detail query failed: %s", e)

    # If neither file info nor usage data found, 404
    if skill_info is None and usage_data is None:
        raise HTTPException(
            status_code=404,
            detail=f"Skill '{skill_name}' not found",
        )

    # 3. Build sessions list with title enrichment
    sessions = []
    if usage_data:
        for row in usage_data["sessions"]:
            project_encoded_name = row.get("project_encoded_name")
            project_path = row.get("project_path") or ""
            if not project_path and project_encoded_name:
                project_path = "/" + project_encoded_name.lstrip("-").replace("-", "/")
            project_name = project_path.rstrip("/").split("/")[-1] if project_path else ""

            sessions.append(
                SessionSummary(
                    uuid=row["uuid"],
                    slug=row.get("slug"),
                    project_encoded_name=project_encoded_name,
                    project_slug=project_encoded_name,
                    project_display_name=project_name,
                    message_count=row["message_count"],
                    start_time=row.get("start_time"),
                    end_time=row.get("end_time"),
                    duration_seconds=row.get("duration_seconds"),
                    models_used=row.get("models_used", []),
                    subagent_count=row.get("subagent_count", 0),
                    has_todos=False,
                    initial_prompt=row.get("initial_prompt"),
                    git_branches=row.get("git_branches", []),
                    session_titles=row.get("session_titles", [])
                    or title_cache.get_titles(project_encoded_name, row["uuid"])
                    or [],
                    tool_source=row.get("tool_source"),
                    subagent_agent_ids=row.get("subagent_agent_ids", []),
                )
            )

    # 4. Build response combining both sources
    return SkillDetailResponse(
        name=skill_info.name if skill_info else skill_name,
        description=skill_info.description if skill_info else None,
        content=skill_info.content if skill_info else None,
        is_plugin=skill_info.is_plugin if skill_info else (":" in skill_name),
        plugin=skill_info.plugin if skill_info else None,
        file_path=skill_info.file_path if skill_info else None,
        calls=usage_data["total_calls"] if usage_data else 0,
        main_calls=usage_data["main_calls"] if usage_data else 0,
        subagent_calls=usage_data["subagent_calls"] if usage_data else 0,
        session_count=usage_data["session_count"] if usage_data else 0,
        first_used=usage_data["first_used"] if usage_data else None,
        last_used=usage_data["last_used"] if usage_data else None,
        trend=[
            SkillTrendItem(date=t["date"], calls=t["calls"], sessions=t["sessions"])
            for t in (usage_data["trend"] if usage_data else [])
        ],
        sessions=sessions,
        sessions_total=usage_data["total"] if usage_data else 0,
    )


@router.get("/skills/{skill_name}/sessions", response_model=SkillSessionsResponse)
@cacheable(max_age=60, stale_while_revalidate=120, private=True)
def get_skill_sessions(
    skill_name: str,
    request: Request,
    limit: Annotated[int, Query(ge=1, le=500, description="Max sessions to return")] = 100,
    offset: Annotated[int, Query(ge=0, description="Number of sessions to skip")] = 0,
) -> SkillSessionsResponse:
    """
    Get sessions that used a specific skill.

    Iterates all projects and sessions to find those that invoked the given skill.
    Uses cached skill usage data from session.get_skills_used().

    Args:
        skill_name: Name of the skill (e.g., 'commit' or 'oh-my-claudecode:security-review')
        request: FastAPI request object (for caching support)
        limit: Maximum number of sessions to return (default: 100, max: 500)
        offset: Number of sessions to skip for pagination (default: 0)

    Returns:
        SkillSessionsResponse with matching sessions and total count
    """
    # SQLite fast path
    try:
        from db.connection import sqlite_read
        from db.queries import query_sessions_by_skill

        with sqlite_read() as conn:
            if conn is not None:
                data = query_sessions_by_skill(conn, skill_name, limit=limit, offset=offset)
                sessions = []
                for row in data["sessions"]:
                    project_encoded_name = row["project_encoded_name"]
                    # Use real project_path from DB if available, fallback to lossy decode
                    project_path = row.get("project_path") or ""
                    if not project_path and project_encoded_name:
                        project_path = "/" + project_encoded_name.lstrip("-").replace("-", "/")
                    project_name = project_path.rstrip("/").split("/")[-1] if project_path else ""

                    sessions.append(
                        SessionWithContext(
                            uuid=row["uuid"],
                            slug=row.get("slug"),
                            project_encoded_name=project_encoded_name,
                            project_path=project_path,
                            project_name=project_name,
                            message_count=row["message_count"],
                            start_time=row.get("start_time"),
                            end_time=row.get("end_time"),
                            duration_seconds=row.get("duration_seconds"),
                            models_used=row.get("models_used", []),
                            subagent_count=row.get("subagent_count", 0),
                            has_todos=False,
                            initial_prompt=row.get("initial_prompt"),
                            git_branches=row.get("git_branches", []),
                            session_titles=row.get("session_titles", [])
                            or title_cache.get_titles(project_encoded_name, row["uuid"])
                            or [],
                        )
                    )
                return SkillSessionsResponse(
                    skill_name=skill_name,
                    sessions=sessions,
                    total_count=data["total"],
                )
    except Exception as e:
        logger.warning("SQLite skill sessions query failed, falling back: %s", e)

    from parallel import process_items_parallel
    from utils import get_initial_prompt, list_all_projects, normalize_timezone

    def process_session_for_skill(session_tuple) -> SessionWithContext | None:
        """Check if session uses skill and return summary if it does."""
        try:
            project, session = session_tuple
            skills_used = session.get_skills_used()
            if skill_name not in skills_used:
                return None

            initial_prompt = get_initial_prompt(session, max_length=500)
            return SessionWithContext(
                uuid=session.uuid,
                slug=session.slug,
                project_encoded_name=project.encoded_name,
                project_path=project.path,
                project_name=project.path.rstrip("/").split("/")[-1],
                message_count=session.message_count,
                start_time=session.start_time,
                end_time=session.end_time,
                duration_seconds=session.duration_seconds,
                models_used=list(session.get_models_used()),
                subagent_count=len(session.list_subagents()),
                has_todos=session.has_todos,
                initial_prompt=initial_prompt,
                git_branches=list(session.get_git_branches()),
                session_titles=list(session.session_titles or []),
            )
        except Exception:
            return None

    # Collect all (project, session) pairs
    session_tuples = []
    for project in list_all_projects():
        for session in project.list_sessions():
            session_tuples.append((project, session))

    # Process sessions in parallel (16 workers like agent_analytics)
    import asyncio

    loop = asyncio.get_event_loop()
    results = loop.run_until_complete(
        process_items_parallel(session_tuples, process_session_for_skill, max_concurrent=16)
    )

    # Filter out None results
    matching_sessions = [r for r in results if r is not None]

    # Sort by start time descending (most recent first)
    matching_sessions.sort(
        key=lambda s: normalize_timezone(s.start_time),
        reverse=True,
    )

    # Store total count before pagination
    total_count = len(matching_sessions)

    # Apply pagination
    paginated_sessions = matching_sessions[offset : offset + limit]

    return SkillSessionsResponse(
        skill_name=skill_name,
        sessions=paginated_sessions,
        total_count=total_count,
    )


async def _resolve_skill_info(skill_name: str, config: Settings) -> SkillInfo:
    """
    Core skill info resolution logic (shared by get_skill_info and get_skill_detail).

    Reads skill metadata and content from:
    - Plugin skills: ~/.claude/plugins/cache/{plugin}/**/skills/{skill_name}/SKILL.md
    - File-based skills: {project}/.claude/commands/{skill_name}.md

    Parses YAML frontmatter for name and description.

    Args:
        skill_name: Name of the skill
        config: Application settings

    Returns:
        SkillInfo with skill metadata and content

    Raises:
        HTTPException: 404 if skill file not found
    """
    import yaml

    # Determine if this is a plugin skill
    is_plugin = ":" in skill_name
    plugin_full_name = skill_name.split(":")[0] if is_plugin else None
    # Extract short name (before @) for directory matching
    # e.g., "oh-my-claudecode@omc" -> "oh-my-claudecode"
    plugin_short_name = (
        plugin_full_name.split("@")[0]
        if plugin_full_name and "@" in plugin_full_name
        else plugin_full_name
    )

    skill_file = None

    if is_plugin:
        actual_skill_name = skill_name.split(":", 1)[1] if ":" in skill_name else skill_name

        # Search in plugins cache directory
        plugins_cache_dir = config.claude_base / "plugins" / "cache"

        if plugins_cache_dir.exists():
            # Structure: cache/{short_name}/{plugin_name}/{version}/commands/{skill}.md
            # Or: cache/{short_name}/{plugin_name}/{version}/skills/{skill}/SKILL.md
            for short_name_dir in plugins_cache_dir.iterdir():
                if not short_name_dir.is_dir():
                    continue
                for plugin_dir in short_name_dir.iterdir():
                    if not plugin_dir.is_dir() or plugin_dir.name != plugin_short_name:
                        continue
                    # Found plugin directory, check all version subdirs
                    for version_dir in plugin_dir.iterdir():
                        if not version_dir.is_dir():
                            continue
                        # Check commands/{skill}.md
                        commands_file = version_dir / "commands" / f"{actual_skill_name}.md"
                        if commands_file.is_file():
                            skill_file = commands_file
                            break
                        # Check skills/{skill}/SKILL.md
                        skills_file = version_dir / "skills" / actual_skill_name / "SKILL.md"
                        if skills_file.is_file():
                            skill_file = skills_file
                            break
                    if skill_file:
                        break
                if skill_file:
                    break
    else:
        # For skills without plugin prefix (e.g., "commit" instead of "commit-commands:commit"),
        # search in multiple locations:
        # 1. Global user commands: ~/.claude/commands/{skill_name}.md
        # 2. Global user skills: ~/.claude/skills/{skill_name}/SKILL.md
        # 3. Plugins cache: search all plugins for this skill name

        global_commands_file = config.claude_base / "commands" / f"{skill_name}.md"
        global_skills_file = config.claude_base / "skills" / skill_name / "SKILL.md"

        if global_commands_file.is_file():
            skill_file = global_commands_file
        elif global_skills_file.is_file():
            skill_file = global_skills_file
        else:
            # Search plugins cache for skill without prefix
            # Structure: cache/{short_name}/{plugin_name}/{version}/commands/{skill}.md
            plugins_cache_dir = config.claude_base / "plugins" / "cache"

            if plugins_cache_dir.exists():
                for short_name_dir in plugins_cache_dir.iterdir():
                    if not short_name_dir.is_dir():
                        continue
                    for plugin_dir in short_name_dir.iterdir():
                        if not plugin_dir.is_dir():
                            continue
                        # Check all version subdirs
                        for version_dir in plugin_dir.iterdir():
                            if not version_dir.is_dir():
                                continue
                            # Check commands/{skill}.md
                            commands_file = version_dir / "commands" / f"{skill_name}.md"
                            if commands_file.is_file():
                                skill_file = commands_file
                                # Update plugin info since we found it in plugins
                                is_plugin = True
                                plugin_full_name = plugin_dir.name
                                break
                            # Check skills/{skill}/SKILL.md
                            skills_file = version_dir / "skills" / skill_name / "SKILL.md"
                            if skills_file.is_file():
                                skill_file = skills_file
                                is_plugin = True
                                plugin_full_name = plugin_dir.name
                                break
                        if skill_file:
                            break
                    if skill_file:
                        break

            if not skill_file:
                raise HTTPException(
                    status_code=404,
                    detail=f"Skill '{skill_name}' not found in ~/.claude/commands/, ~/.claude/skills/, or plugins cache",
                )

    if not skill_file or not skill_file.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Skill file not found for '{skill_name}'",
        )

    # Read the file content
    content = await run_in_thread(safe_read_file, skill_file, config.max_skill_size)

    # Parse YAML frontmatter
    description = None
    frontmatter_name = skill_name

    if content.startswith("---"):
        # Split frontmatter from content
        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter_str = parts[1].strip()
            try:
                frontmatter = yaml.safe_load(frontmatter_str)
                if isinstance(frontmatter, dict):
                    description = frontmatter.get("description")
                    frontmatter_name = frontmatter.get("name", skill_name)
            except yaml.YAMLError as e:
                logger.warning(f"Failed to parse YAML frontmatter for {skill_name}: {e}")

    return SkillInfo(
        name=frontmatter_name,
        description=description,
        content=content,
        is_plugin=is_plugin,
        plugin=plugin_full_name,
        file_path=str(skill_file),
    )


@router.get("/skills/info/{skill_name}", response_model=SkillInfo)
@cacheable(max_age=60, stale_while_revalidate=120, private=True)
async def get_skill_info(
    skill_name: str,
    request: Request,
    config: Annotated[Settings, Depends(get_settings)],
) -> SkillInfo:
    """Get detailed information about a skill (cached endpoint wrapper)."""
    return await _resolve_skill_info(skill_name, config)
