"""
MCP Tools router - aggregate MCP tool usage across servers.

Provides endpoints for viewing MCP server and tool usage analytics,
powered by SQLite session_tools and subagent_tools tables.
"""

import logging
import sqlite3
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from db.queries import (
    query_mcp_server_detail,
    query_mcp_server_trend,
    query_mcp_tool_detail,
    query_mcp_tool_usage_trend,
    query_mcp_tools_overview,
    query_sessions_by_mcp_server,
    query_sessions_by_mcp_tool,
)
from http_caching import cacheable
from schemas import (
    McpServer,
    McpServerDetail,
    McpServerTrend,
    McpToolDetail,
    McpToolsOverview,
    McpToolSummary,
    SessionSummary,
    UsageTrendItem,
    UsageTrendResponse,
    paginate,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# Helpers
# =============================================================================


def _server_display_name(server_name: str) -> str:
    """
    Generate a human-readable display name from an MCP server identifier.

    Examples:
        "coderoots" -> "Coderoots"
        "plugin_playwright_playwright" -> "Playwright"
        "plugin_github_github" -> "Github"
        "plane-project-task-manager" -> "Plane Project Task Manager"
        "context7" -> "Context7"
        "filesystem" -> "Filesystem"
    """
    name = server_name
    # Strip plugin_ prefix and deduplicate (plugin_github_github -> github)
    if name.startswith("plugin_"):
        parts = name[len("plugin_") :].split("_")
        # Deduplicate: plugin_playwright_playwright -> playwright
        if len(parts) >= 2 and parts[0] == parts[1]:
            name = parts[0]
        else:
            name = "_".join(parts)

    # Split on _ and - then title-case
    segments = []
    for part in name.replace("-", "_").split("_"):
        if part:
            segments.append(part.capitalize())

    return " ".join(segments) if segments else server_name


def _detect_source(server_name: str) -> tuple[str, Optional[str]]:
    """
    Detect whether an MCP server comes from a plugin or is standalone.

    Returns (source, plugin_name) tuple.
    """
    if server_name.startswith("plugin_"):
        # Extract plugin name: plugin_github_github -> github
        parts = server_name[len("plugin_") :].split("_")
        plugin_name = parts[0] if parts else server_name
        return "plugin", plugin_name
    return "standalone", None


def _build_server_schema(server_data: dict) -> McpServer:
    """Convert a server dict from query results into an McpServer schema."""
    name = server_data["name"]
    source, plugin_name = _detect_source(name)

    tools = [McpToolSummary(**t) for t in server_data.get("tools", [])]

    return McpServer(
        name=name,
        display_name=_server_display_name(name),
        source=source,
        plugin_name=plugin_name,
        tool_count=server_data.get("tool_count", len(tools)),
        total_calls=server_data.get("total_calls", 0),
        session_count=server_data.get("session_count", 0),
        main_calls=server_data.get("main_calls", 0),
        subagent_calls=server_data.get("subagent_calls", 0),
        first_used=server_data.get("first_used"),
        last_used=server_data.get("last_used"),
        tools=tools,
    )


def _build_session_summary(session_data: dict) -> SessionSummary:
    """Convert a session dict from query results into a SessionSummary schema."""
    return SessionSummary(
        uuid=session_data["uuid"],
        slug=session_data.get("slug"),
        project_encoded_name=session_data.get("project_encoded_name"),
        message_count=session_data.get("message_count", 0),
        start_time=session_data.get("start_time"),
        end_time=session_data.get("end_time"),
        duration_seconds=session_data.get("duration_seconds"),
        models_used=session_data.get("models_used", []),
        subagent_count=session_data.get("subagent_count", 0),
        initial_prompt=session_data.get("initial_prompt"),
        git_branches=session_data.get("git_branches", []),
        session_titles=session_data.get("session_titles", []),
        tool_source=session_data.get("tool_source"),
        subagent_agent_ids=session_data.get("subagent_agent_ids", []),
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.get("", response_model=McpToolsOverview)
@cacheable(max_age=60, stale_while_revalidate=300, private=True)
def get_mcp_tools_overview(
    request: Request,
    project: Optional[str] = Query(None, description="Filter by project encoded name"),
    period: str = Query("all", description="Time period: day, week, month, quarter, all"),
) -> McpToolsOverview:
    """
    List all MCP servers and their tools with aggregated usage stats.

    Returns overview of all MCP tool servers discovered from session data,
    with per-server and per-tool breakdowns of call counts, session counts,
    and main vs subagent usage split.

    Cache: 60s fresh, 5min stale-while-revalidate.
    """
    try:
        from db.connection import sqlite_read

        with sqlite_read() as conn:
            if conn is not None:
                data = query_mcp_tools_overview(conn, project=project, period=period)

                servers = [_build_server_schema(s) for s in data["servers"]]

                return McpToolsOverview(
                    total_servers=data["total_servers"],
                    total_tools=data["total_tools"],
                    total_calls=data["total_calls"],
                    total_sessions=data["total_sessions"],
                    servers=servers,
                )
    except sqlite3.Error as e:
        logger.warning("SQLite MCP tools overview query failed: %s", e)

    # No SQLite available — return empty
    return McpToolsOverview(
        total_servers=0,
        total_tools=0,
        total_calls=0,
        total_sessions=0,
        servers=[],
    )


@router.get("/usage/trend", response_model=UsageTrendResponse)
@cacheable(max_age=60, stale_while_revalidate=300, private=True)
def get_mcp_tool_usage_trend(
    request: Request,
    project: Optional[str] = Query(None, description="Filter by project encoded name"),
    period: str = Query("month", description="Time period: week, month, quarter, all"),
) -> UsageTrendResponse:
    """
    Aggregate MCP tool usage trend with daily breakdown.

    Returns total usage, per-tool breakdown, and daily trend data.
    Matches the same schema as agents/skills usage trend endpoints.
    """
    try:
        from db.connection import sqlite_read

        with sqlite_read() as conn:
            if conn is not None:
                data = query_mcp_tool_usage_trend(conn, project=project, period=period)
                return UsageTrendResponse(
                    total=data["total"],
                    by_item=data["by_item"],
                    trend=[UsageTrendItem(**t) for t in data["trend"]],
                    first_used=data.get("first_used"),
                    last_used=data.get("last_used"),
                )
    except sqlite3.Error as e:
        logger.warning("SQLite MCP tool usage trend query failed: %s", e)

    return UsageTrendResponse(total=0, by_item={}, trend=[])


@router.get("/{server_name}/{tool_name}", response_model=McpToolDetail)
@cacheable(max_age=60, stale_while_revalidate=300, private=True)
def get_mcp_tool_detail(
    request: Request,
    server_name: str,
    tool_name: str,
    project: Optional[str] = Query(None, description="Filter by project encoded name"),
    period: str = Query("all", description="Time period: day, week, month, quarter, all"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
) -> McpToolDetail:
    """
    Get detailed stats for a specific MCP tool including daily trend and sessions.

    Cache: 60s fresh, 5min stale-while-revalidate.
    """
    try:
        from db.connection import sqlite_read

        with sqlite_read() as conn:
            if conn is not None:
                detail = query_mcp_tool_detail(
                    conn, server_name, tool_name, project=project, period=period
                )
                if detail is None:
                    raise HTTPException(
                        status_code=404,
                        detail=f"MCP tool '{server_name}/{tool_name}' not found",
                    )

                full_name = detail["full_name"]

                # Paginated sessions
                p = paginate(detail["session_count"], page, per_page)
                sessions_data = query_sessions_by_mcp_tool(
                    conn,
                    full_name,
                    project=project,
                    period=period,
                    limit=p["per_page"],
                    offset=p["offset"],
                )

                trend = [McpServerTrend(**t) for t in detail["trend"]]
                sessions = [_build_session_summary(s) for s in sessions_data["sessions"]]

                return McpToolDetail(
                    name=detail["name"],
                    full_name=full_name,
                    server_name=server_name,
                    server_display_name=_server_display_name(server_name),
                    calls=detail["total_calls"],
                    main_calls=detail["main_calls"],
                    subagent_calls=detail["subagent_calls"],
                    session_count=detail["session_count"],
                    first_used=detail.get("first_used"),
                    last_used=detail.get("last_used"),
                    trend=trend,
                    sessions=sessions,
                    sessions_total=sessions_data["total"],
                )
    except HTTPException:
        raise
    except sqlite3.Error as e:
        logger.warning("SQLite MCP tool detail query failed: %s", e)

    raise HTTPException(
        status_code=404,
        detail=f"MCP tool '{server_name}/{tool_name}' not found (SQLite unavailable)",
    )


@router.get("/{server_name}", response_model=McpServerDetail)
@cacheable(max_age=60, stale_while_revalidate=300, private=True)
def get_mcp_server_detail(
    request: Request,
    server_name: str,
    project: Optional[str] = Query(None, description="Filter by project encoded name"),
    period: str = Query("all", description="Time period: day, week, month, quarter, all"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page"),
) -> McpServerDetail:
    """
    Get detailed stats for a specific MCP server including daily trend and sessions.

    Returns per-tool breakdowns, daily usage trend, and paginated session list.

    Cache: 60s fresh, 5min stale-while-revalidate.
    """
    try:
        from db.connection import sqlite_read

        with sqlite_read() as conn:
            if conn is not None:
                # Server detail (tools + aggregates)
                detail = query_mcp_server_detail(conn, server_name, project=project, period=period)
                if detail is None:
                    raise HTTPException(
                        status_code=404,
                        detail=f"MCP server '{server_name}' not found",
                    )

                # Daily trend
                trend_data = query_mcp_server_trend(
                    conn, server_name, project=project, period=period
                )

                # Paginated sessions
                p = paginate(detail["session_count"], page, per_page)
                sessions_data = query_sessions_by_mcp_server(
                    conn,
                    server_name,
                    project=project,
                    period=period,
                    limit=p["per_page"],
                    offset=p["offset"],
                )

                # Build response
                source, plugin_name = _detect_source(server_name)
                tools = [McpToolSummary(**t) for t in detail.get("tools", [])]
                trend = [McpServerTrend(**t) for t in trend_data]
                sessions = [_build_session_summary(s) for s in sessions_data["sessions"]]

                return McpServerDetail(
                    name=detail["name"],
                    display_name=_server_display_name(server_name),
                    source=source,
                    plugin_name=plugin_name,
                    tool_count=detail["tool_count"],
                    total_calls=detail["total_calls"],
                    session_count=detail["session_count"],
                    main_calls=detail["main_calls"],
                    subagent_calls=detail["subagent_calls"],
                    first_used=detail.get("first_used"),
                    last_used=detail.get("last_used"),
                    tools=tools,
                    trend=trend,
                    sessions=sessions,
                    sessions_total=sessions_data["total"],
                )
    except HTTPException:
        raise
    except sqlite3.Error as e:
        logger.warning("SQLite MCP server detail query failed: %s", e)

    raise HTTPException(
        status_code=404,
        detail=f"MCP server '{server_name}' not found (SQLite unavailable)",
    )
