"""
Agents router - manage custom agent markdown files.

Provides endpoints for listing, reading, and writing agent configurations
stored in ~/.claude/agents/ directory.

Phase 3: HTTP caching with Cache-Control headers.
"""

import logging
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

# Add models and api to path
api_path = Path(__file__).parent.parent
models_path = api_path.parent.parent
sys.path.insert(0, str(api_path))
sys.path.insert(0, str(models_path))

from config import Settings, settings
from http_caching import cacheable
from models import Project
from parallel import run_in_thread
from routers.agent_analytics import (
    collect_all_agent_usage,
    get_agent_detail,
    get_agent_history,
)
from schemas import (
    AgentCreateRequest,
    AgentDetail,
    AgentInfo,
    AgentInvocationHistoryResponse,
    AgentSessionsResponse,
    AgentSummary,
    AgentUsageDetail,
    AgentUsageListResponse,
    SessionSummary,
    UsageTrendItem,
    UsageTrendResponse,
)
from services.session_title_cache import title_cache

logger = logging.getLogger(__name__)

router = APIRouter()

# Constants
ALLOWED_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


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


def get_agents_dir(
    config: Annotated[Settings, Depends(get_settings)],
    project: Annotated[
        str | None, Query(description="Project encoded name for project-specific agents")
    ] = None,
) -> Path:
    """
    Dependency to get the agents directory.

    Args:
        config: Application settings (injected)
        project: Optional project encoded name for project-specific agents

    Returns:
        Path to agents directory (global or project-specific)
    """
    if project:
        proj = Project.from_encoded_name(project)
        return Path(proj.path) / ".claude" / "agents"
    return config.agents_dir


def validate_agent_name(name: str, max_length: int = 100) -> None:
    """
    Validate agent name for security.

    Args:
        name: Agent filename (without .md extension)
        max_length: Maximum allowed name length (default: 100)

    Raises:
        HTTPException: If name is invalid
    """
    if not name or len(name) > max_length:
        raise HTTPException(
            status_code=400, detail=f"Agent name must be between 1 and {max_length} characters"
        )

    if not ALLOWED_NAME_PATTERN.match(name):
        raise HTTPException(
            status_code=400,
            detail="Agent name must contain only alphanumeric characters, hyphens, and underscores",
        )

    # Prevent directory traversal
    if ".." in name or "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="Invalid agent name")


def discover_agents(agents_dir: Path) -> list[tuple[str, Path]]:
    """
    Discover all agent definitions in a directory.

    Supports two formats:
    - Flat file: {agents_dir}/{name}.md
    - Directory: {agents_dir}/{name}/SKILL.md

    Returns:
        List of (agent_name, file_path) tuples. If both formats exist
        for the same name, the directory format takes precedence.
    """
    agents: dict[str, Path] = {}

    if not agents_dir.exists():
        return []

    # 1. Flat .md files
    for file_path in agents_dir.glob("*.md"):
        if file_path.is_file():
            agents[file_path.stem] = file_path

    # 2. Directory-based agents ({name}/SKILL.md) — override flat files
    for child in agents_dir.iterdir():
        if child.is_dir():
            skill_file = child / "SKILL.md"
            if skill_file.is_file():
                agents[child.name] = skill_file

    return sorted(agents.items(), key=lambda item: item[0].lower())


from utils_io import delete_file_sync, safe_read_file, safe_write_file


@router.get("/agents", response_model=list[AgentSummary])
@cacheable(max_age=30, stale_while_revalidate=60, private=True)
def list_agents(
    request: Request,
    agents_dir: Annotated[Path, Depends(get_agents_dir)],
    config: Annotated[Settings, Depends(get_settings)],
) -> list[AgentSummary]:
    """
    List all custom agent markdown files.

    Returns agent names and metadata without full content for performance.
    Agents are markdown files stored in ~/.claude/agents/

    Phase 3: Short cache (30s) - files may be edited frequently.

    Args:
        request: FastAPI request object (for caching support)
        agents_dir: Agents directory path (injected)
        config: Application settings (injected)

    Returns:
        List of agent summaries sorted alphabetically by name
    """
    agents: list[AgentSummary] = []

    try:
        for name, file_path in discover_agents(agents_dir):
            try:
                stat = file_path.stat()
                agents.append(
                    AgentSummary(
                        name=name,
                        size_bytes=stat.st_size,
                        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                    )
                )
            except OSError as e:
                logger.warning(f"Failed to stat agent file {file_path}: {e}")
                continue
    except OSError as e:
        logger.error(f"Failed to list agents directory: {e}")
        raise HTTPException(status_code=500, detail="Failed to list agents") from e

    return agents


# =============================================================================
# Agent Usage Analytics Endpoints
# NOTE: These MUST be defined BEFORE /agents/{name} to avoid path conflicts
# =============================================================================


@router.get("/agents/usage", response_model=AgentUsageListResponse)
@cacheable(
    max_age=settings.cache_agent_usage,
    stale_while_revalidate=settings.cache_agent_usage_revalidate,
    private=True,
)
async def list_agent_usage(
    request: Request,
    response: Response,
    category: Annotated[
        str | None, Query(description="Filter by category: builtin, plugin, custom, project")
    ] = None,
    search: Annotated[str | None, Query(description="Search by agent name or type")] = None,
    sort: Annotated[str, Query(description="Sort by: runs, cost, last_used, name")] = "runs",
    order: Annotated[str, Query(description="Sort order: asc, desc")] = "desc",
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    per_page: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
) -> AgentUsageListResponse:
    """
    List all agents with usage statistics.

    Scans all sessions across all projects to aggregate agent invocation data.
    Returns summary statistics for each agent type.

    Uses async parallel processing for improved performance.
    Cache TTL configurable via CLAUDE_KARMA_CACHE_AGENT_USAGE env var.

    Args:
        request: FastAPI request object (for caching support)
        category: Optional category filter
        search: Optional search filter by agent name or type
        sort: Sort field (runs, cost, last_used, name)
        order: Sort order (asc, desc)
        page: Page number (1-indexed)
        per_page: Items per page (max 100)

    Returns:
        AgentUsageListResponse with aggregated stats and pagination
    """
    # Pass search to SQL for database-level filtering
    usage_response = await collect_all_agent_usage(search=search)

    # Add X-Index-Age header
    from db.indexer import get_last_sync_time

    last_sync = get_last_sync_time()
    if last_sync > 0:
        index_age = time.time() - last_sync
        response.headers["X-Index-Age"] = str(int(index_age))

    # Work on a copy to avoid mutating the cached response object
    agents = list(usage_response.agents)

    # Filter by category if specified
    # NOTE: Category filtering done in Python because category is derived from
    # subagent_type via determine_agent_category() and not stored in the database.
    # Could be pushed to SQL if we add a category column to subagent_invocations.
    if category:
        agents = [a for a in agents if a.category == category]

    # Sort
    reverse = order == "desc"
    if sort == "runs":
        agents.sort(key=lambda a: a.total_runs, reverse=reverse)
    elif sort == "cost":
        agents.sort(key=lambda a: a.total_cost_usd, reverse=reverse)
    elif sort == "last_used":
        agents.sort(key=lambda a: a.last_used or datetime.min, reverse=reverse)
    elif sort == "name":
        agents.sort(key=lambda a: a.agent_name.lower(), reverse=reverse)

    # Calculate pagination
    total = len(agents)
    total_pages = (total + per_page - 1) // per_page if total > 0 else 0

    # Slice for requested page
    start = (page - 1) * per_page
    end = start + per_page
    paginated_agents = agents[start:end]

    # Create new response with pagination (preserve global stats)
    return AgentUsageListResponse(
        agents=paginated_agents,
        total_runs=usage_response.total_runs,
        total_cost_usd=usage_response.total_cost_usd,
        by_category=usage_response.by_category,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


@router.get("/agents/usage/trend", response_model=UsageTrendResponse)
@cacheable(max_age=60, stale_while_revalidate=120, private=True)
def get_agent_usage_trend(
    request: Request,
    project: Annotated[str | None, Query(description="Filter by project encoded name")] = None,
    period: Annotated[str, Query(description="Time period: week, month, quarter, all")] = "month",
) -> UsageTrendResponse:
    """
    Get agent usage trend data for charts.

    Aggregates subagent invocations into daily counts, with per-agent breakdown.
    Optionally filtered by project.

    Args:
        request: FastAPI request object (for caching support)
        project: Optional project encoded name filter
        period: Time period (week, month, quarter, all)

    Returns:
        UsageTrendResponse with totals, per-agent breakdown, and daily trend
    """
    try:
        from db.connection import sqlite_read
        from db.queries import query_agent_usage_trend

        with sqlite_read() as conn:
            if conn is not None:
                data = query_agent_usage_trend(conn, project=project, period=period)
                return UsageTrendResponse(
                    total=data["total"],
                    by_item=data["by_item"],
                    trend=[UsageTrendItem(date=t["date"], count=t["count"]) for t in data["trend"]],
                    first_used=data.get("first_used"),
                    last_used=data.get("last_used"),
                )
    except Exception as e:
        logger.warning("Failed to query agent usage trend: %s", e)

    return UsageTrendResponse()


@router.get("/agents/usage/{subagent_type:path}/trend", response_model=UsageTrendResponse)
@cacheable(max_age=60, stale_while_revalidate=120, private=True)
def get_single_agent_usage_trend(
    subagent_type: str,
    request: Request,
    period: Annotated[str, Query(description="Time period: week, month, quarter, all")] = "month",
) -> UsageTrendResponse:
    """
    Get usage trend data for a specific agent type.

    Args:
        subagent_type: The subagent_type identifier
        request: FastAPI request object (for caching support)
        period: Time period (week, month, quarter, all)

    Returns:
        UsageTrendResponse with daily trend for this agent
    """
    try:
        from db.connection import sqlite_read
        from db.queries import query_agent_usage_trend

        with sqlite_read() as conn:
            if conn is not None:
                data = query_agent_usage_trend(
                    conn, period=period, subagent_type=subagent_type
                )
                return UsageTrendResponse(
                    total=data["total"],
                    by_item=data["by_item"],
                    trend=[
                        UsageTrendItem(date=t["date"], count=t["count"])
                        for t in data["trend"]
                    ],
                    first_used=data.get("first_used"),
                    last_used=data.get("last_used"),
                )
    except Exception as e:
        logger.warning("Failed to query agent usage trend for %s: %s", subagent_type, e)

    return UsageTrendResponse()


@router.get(
    "/agents/usage/{subagent_type:path}/history", response_model=AgentInvocationHistoryResponse
)
@cacheable(
    max_age=settings.cache_agent_usage,
    stale_while_revalidate=settings.cache_agent_usage_revalidate,
    private=True,
)
async def get_agent_invocation_history(
    subagent_type: str,
    request: Request,
    response: Response,
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    per_page: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
) -> AgentInvocationHistoryResponse:
    """
    Get paginated invocation history for a specific agent type.

    Uses async parallel processing for improved performance.

    Args:
        subagent_type: The subagent_type identifier
        request: FastAPI request object (for caching support)
        page: Page number (1-indexed)
        per_page: Number of items per page (max 100)

    Returns:
        Paginated response with AgentInvocation records, sorted by invoked_at descending
    """
    invocations, total = await get_agent_history(subagent_type, page=page, per_page=per_page)

    # Add X-Index-Age header
    from db.indexer import get_last_sync_time

    last_sync = get_last_sync_time()
    if last_sync > 0:
        index_age = time.time() - last_sync
        response.headers["X-Index-Age"] = str(int(index_age))

    total_pages = (total + per_page - 1) // per_page if total > 0 else 0
    return AgentInvocationHistoryResponse(
        items=invocations,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
    )


@router.get("/agents/usage/{subagent_type:path}/sessions", response_model=AgentSessionsResponse)
@cacheable(
    max_age=settings.cache_agent_usage,
    stale_while_revalidate=settings.cache_agent_usage_revalidate,
    private=True,
)
async def get_agent_sessions(
    subagent_type: str,
    request: Request,
    response: Response,
    limit: Annotated[int, Query(ge=1, le=500, description="Max sessions to return")] = 100,
    offset: Annotated[int, Query(ge=0, description="Number of sessions to skip")] = 0,
) -> AgentSessionsResponse:
    """
    Get sessions that used a specific agent type.

    Returns session summaries (same shape as skill sessions) for display
    as session cards in the agent detail history tab.
    """
    try:
        from db.connection import sqlite_read
        from db.queries import query_sessions_by_agent

        with sqlite_read() as conn:
            if conn is not None:
                data = query_sessions_by_agent(conn, subagent_type, limit=limit, offset=offset)
                sessions = []
                for row in data["sessions"]:
                    sessions.append(
                        SessionSummary(
                            uuid=row["uuid"],
                            slug=row.get("slug"),
                            project_encoded_name=row["project_encoded_name"],
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
                            or title_cache.get_titles(row["project_encoded_name"], row["uuid"])
                            or [],
                        )
                    )

                # Add X-Index-Age header
                from db.indexer import get_last_sync_time

                last_sync = get_last_sync_time()
                if last_sync > 0:
                    index_age = time.time() - last_sync
                    response.headers["X-Index-Age"] = str(int(index_age))

                return AgentSessionsResponse(
                    subagent_type=subagent_type,
                    sessions=sessions,
                    total_count=data["total"],
                )
    except Exception as e:
        logger.warning("SQLite agent sessions query failed: %s", e)

    return AgentSessionsResponse(
        subagent_type=subagent_type,
        sessions=[],
        total_count=0,
    )


@router.get("/agents/usage/{subagent_type:path}", response_model=AgentUsageDetail)
@cacheable(
    max_age=settings.cache_agent_usage,
    stale_while_revalidate=settings.cache_agent_usage_revalidate,
    private=True,
)
async def get_agent_usage_detail(
    subagent_type: str,
    request: Request,
    response: Response,
) -> AgentUsageDetail:
    """
    Get detailed usage statistics for a specific agent type.

    Uses async parallel processing for improved performance.

    Args:
        subagent_type: The subagent_type identifier (e.g., "Explore", "feature-dev:code-reviewer")
        request: FastAPI request object (for caching support)

    Returns:
        AgentUsageDetail with full statistics

    Raises:
        HTTPException: 404 if agent has no usage data
    """
    detail = await get_agent_detail(subagent_type)
    if detail is None:
        raise HTTPException(
            status_code=404, detail=f"No usage data found for agent '{subagent_type}'"
        )

    # Add X-Index-Age header
    from db.indexer import get_last_sync_time

    last_sync = get_last_sync_time()
    if last_sync > 0:
        index_age = time.time() - last_sync
        response.headers["X-Index-Age"] = str(int(index_age))

    return detail


# =============================================================================
# Agent Definition Endpoints (Custom Markdown Files)
# NOTE: These come AFTER /agents/usage to avoid path conflicts
# =============================================================================


_BUILTIN_AGENTS: dict[str, str] = {
    "general-purpose": "A capable agent for complex, multi-step tasks that require both exploration and action. Inherits the parent model and has access to all tools.",
    "Bash": "Running terminal commands in a separate context. Inherits the parent model.",
    "Explore": "A fast, read-only agent optimized for searching and analyzing codebases. Uses Haiku for low-latency file discovery, code search, and codebase exploration.",
    "Plan": "A research agent used during plan mode to gather codebase context before presenting a plan. Read-only tools, inherits the parent model.",
    "claude-code-guide": "Answers questions about Claude Code features, hooks, slash commands, MCP servers, settings, and IDE integrations. Uses Haiku.",
    "statusline-setup": "Configures the Claude Code status line setting. Uses Sonnet.",
}


def _builtin_agent_info(agent_name: str) -> AgentInfo:
    """Return synthetic AgentInfo for built-in Claude Code agent types."""
    desc = _BUILTIN_AGENTS.get(agent_name, "Built-in Claude Code agent type.")
    return AgentInfo(
        name=agent_name,
        description=desc,
        capabilities=None,
        content=None,
        is_plugin=False,
        plugin=None,
        file_path=None,
    )


@router.get("/agents/info/{agent_name}", response_model=AgentInfo)
@cacheable(max_age=60, stale_while_revalidate=120, private=True)
async def get_agent_info(
    agent_name: str,
    request: Request,
    config: Annotated[Settings, Depends(get_settings)],
) -> AgentInfo:
    """
    Get detailed information about an agent.

    Reads agent metadata and content from:
    - Plugin agents: ~/.claude/plugins/cache/{short_name}/{plugin_name}/{version}/agents/{agent}.md
    - Custom agents: ~/.claude/agents/{agent_name}.md

    Parses YAML frontmatter for description and capabilities.

    Args:
        agent_name: Name of the agent (e.g., 'qa-tester' or 'oh-my-claudecode:qa-tester')
        request: FastAPI request object (for caching support)
        config: Application settings (injected)

    Returns:
        AgentInfo with agent metadata and content

    Raises:
        HTTPException: 404 if agent file not found
    """
    import yaml

    # Determine if this is a plugin agent
    is_plugin = ":" in agent_name
    plugin_full_name = agent_name.split(":")[0] if is_plugin else None
    # Extract short name (before @) for directory matching
    # e.g., "oh-my-claudecode@omc" -> "oh-my-claudecode"
    plugin_short_name = (
        plugin_full_name.split("@")[0]
        if plugin_full_name and "@" in plugin_full_name
        else plugin_full_name
    )

    agent_file = None

    if is_plugin:
        actual_agent_name = agent_name.split(":", 1)[1] if ":" in agent_name else agent_name

        # Search in plugins cache directory
        plugins_cache_dir = config.claude_base / "plugins" / "cache"

        if plugins_cache_dir.exists():
            # Structure: cache/{short_name}/{plugin_name}/{version}/agents/{agent}.md
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
                        # Check agents/{agent}.md
                        agents_file = version_dir / "agents" / f"{actual_agent_name}.md"
                        if agents_file.is_file():
                            agent_file = agents_file
                            break
                    if agent_file:
                        break
                if agent_file:
                    break
    else:
        # For agents without plugin prefix, search in:
        # 1. Global user agents: ~/.claude/agents/{agent_name}.md
        # 2. Plugins cache: search all plugins for this agent name

        global_agents_file = config.agents_dir / f"{agent_name}.md"
        # Also check directory-based agents: {agent_name}/SKILL.md
        global_agents_dir_file = config.agents_dir / agent_name / "SKILL.md"

        if global_agents_file.is_file():
            agent_file = global_agents_file
        elif global_agents_dir_file.is_file():
            agent_file = global_agents_dir_file
        else:
            # Search plugins cache for agent without prefix
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
                            # Check agents/{agent}.md
                            agents_file = version_dir / "agents" / f"{agent_name}.md"
                            if agents_file.is_file():
                                agent_file = agents_file
                                # Update plugin info since we found it in plugins
                                is_plugin = True
                                plugin_full_name = plugin_dir.name
                                break
                        if agent_file:
                            break
                    if agent_file:
                        break

            if not agent_file:
                # Built-in agent types have no definition file — return synthetic info
                return _builtin_agent_info(agent_name)

    if not agent_file or not agent_file.exists():
        return _builtin_agent_info(agent_name)

    # Read the file content
    content = await run_in_thread(safe_read_file, agent_file, config.max_agent_size)

    # Parse YAML frontmatter
    description = None
    capabilities = None
    frontmatter_name = agent_name

    if content.startswith("---"):
        # Split frontmatter from content
        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter_str = parts[1].strip()
            try:
                frontmatter = yaml.safe_load(frontmatter_str)
                if isinstance(frontmatter, dict):
                    description = frontmatter.get("description")
                    capabilities = frontmatter.get("capabilities")
                    frontmatter_name = frontmatter.get("name", agent_name)
            except yaml.YAMLError as e:
                logger.warning(f"Failed to parse YAML frontmatter for {agent_name}: {e}")

    return AgentInfo(
        name=frontmatter_name,
        description=description,
        capabilities=capabilities,
        content=content,
        is_plugin=is_plugin,
        plugin=plugin_full_name,
        file_path=str(agent_file),
    )


@router.get("/agents/{name}", response_model=AgentDetail)
@cacheable(max_age=60, stale_while_revalidate=120, private=True)
async def get_agent(
    name: str,
    request: Request,
    agents_dir: Annotated[Path, Depends(get_agents_dir)],
    config: Annotated[Settings, Depends(get_settings)],
) -> AgentDetail:
    """
    Get a specific agent by name.

    Returns the full content and metadata of an agent markdown file.

    Phase 3: Moderate cache (60s) - agent content changes infrequently.
    Phase 4: Async file I/O via run_in_thread() for consistency.

    Args:
        name: Agent name (filename without .md extension)
        request: FastAPI request object (for caching support)
        agents_dir: Agents directory path (injected)
        config: Application settings (injected)

    Returns:
        Agent details including full markdown content

    Raises:
        HTTPException: 400 for invalid name, 404 if agent not found
    """
    validate_agent_name(name)

    # Check both flat file and directory-based agent
    file_path = agents_dir / f"{name}.md"
    dir_path = agents_dir / name / "SKILL.md"

    if dir_path.is_file():
        file_path = dir_path
    elif not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")

    content = await run_in_thread(safe_read_file, file_path, config.max_agent_size)
    stat = file_path.stat()

    return AgentDetail(
        name=name,
        content=content,
        size_bytes=stat.st_size,
        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
    )


@router.post("/agents/{name}", response_model=AgentDetail, status_code=201)
async def create_or_update_agent(
    name: str,
    agent: AgentCreateRequest,
    agents_dir: Annotated[Path, Depends(get_agents_dir)],
    config: Annotated[Settings, Depends(get_settings)],
) -> AgentDetail:
    """
    Create or update an agent markdown file.

    If the agent already exists, it will be overwritten.
    Phase 4: Async file I/O via run_in_thread() for consistency.

    Args:
        name: Agent name (filename without .md extension)
        agent: Request body with markdown content
        agents_dir: Agents directory path (injected)
        config: Application settings (injected)

    Returns:
        Created/updated agent details

    Raises:
        HTTPException: 400 for invalid name/content, 413 if content too large
    """
    validate_agent_name(name)

    # Validate content size
    content_size = len(agent.content.encode("utf-8"))
    if content_size > config.max_agent_size:
        raise HTTPException(
            status_code=413,
            detail=f"Content too large ({content_size} bytes). Maximum is {config.max_agent_size} bytes",
        )

    file_path = agents_dir / f"{name}.md"

    # Write the file (async)
    await run_in_thread(safe_write_file, file_path, agent.content)

    # Return the created agent
    stat = file_path.stat()
    return AgentDetail(
        name=name,
        content=agent.content,
        size_bytes=stat.st_size,
        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
    )


@router.delete("/agents/{name}", status_code=204)
async def delete_agent(
    name: str,
    agents_dir: Annotated[Path, Depends(get_agents_dir)],
) -> None:
    """
    Delete an agent markdown file.

    Phase 4: Async file I/O via run_in_thread() for consistency.

    Args:
        name: Agent name (filename without .md extension)
        agents_dir: Agents directory path (injected)

    Raises:
        HTTPException: 400 for invalid name, 404 if agent not found
    """
    validate_agent_name(name)

    file_path = agents_dir / f"{name}.md"

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Agent '{name}' not found")

    try:
        await run_in_thread(delete_file_sync, file_path)
        logger.info(f"Deleted agent: {name}")
    except OSError as e:
        logger.error(f"Failed to delete agent {name}: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete agent") from e
