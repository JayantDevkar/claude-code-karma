"""
MCP Tools router - aggregate MCP tool usage across servers.

Provides endpoints for viewing MCP server and tool usage analytics,
powered by SQLite session_tools and subagent_tools tables.
"""

import logging
import sqlite3
from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from db.queries import (
    BUILTIN_CATEGORY_DISPLAY,
    query_builtin_server_detail,
    query_builtin_server_trend,
    query_builtin_tool_detail,
    query_builtin_tool_usage_trend,
    query_builtin_tools_overview,
    query_mcp_server_detail,
    query_mcp_server_trend,
    query_mcp_tool_detail,
    query_mcp_tool_usage_trend,
    query_mcp_tools_overview,
    query_sessions_by_builtin_server,
    query_sessions_by_builtin_tool,
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
    # Built-in category display names
    if server_name in BUILTIN_CATEGORY_DISPLAY:
        return BUILTIN_CATEGORY_DISPLAY[server_name]

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
    if server_name.startswith("builtin-"):
        return "builtin", None
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
    project_path = session_data.get("project_path") or ""
    project_display_name = project_path.rstrip("/").split("/")[-1] if project_path else None

    return SessionSummary(
        uuid=session_data["uuid"],
        slug=session_data.get("slug"),
        project_encoded_name=session_data.get("project_encoded_name"),
        project_display_name=project_display_name,
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
        session_source=session_data.get("session_source"),
        source=session_data.get("source"),
        remote_user_id=session_data.get("remote_user_id"),
        remote_machine_id=session_data.get("remote_machine_id"),
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
                mcp_data = query_mcp_tools_overview(conn, project=project, period=period)
                builtin_data = query_builtin_tools_overview(conn, project=project, period=period)

                mcp_servers = [_build_server_schema(s) for s in mcp_data["servers"]]
                builtin_servers = [_build_server_schema(s) for s in builtin_data["servers"]]

                all_servers = builtin_servers + mcp_servers

                # Combined distinct session count across both builtin and MCP
                from db.queries import _mcp_time_filter

                cs_conditions: list[str] = []
                cs_params: dict = {}
                if project:
                    cs_conditions.append("s.project_encoded_name = :project")
                    cs_params["project"] = project
                time_clause, time_params = _mcp_time_filter(period)
                if time_clause:
                    cs_conditions.append(time_clause)
                    cs_params.update(time_params)
                cs_where = ("WHERE " + " AND ".join(cs_conditions)) if cs_conditions else ""

                combined_sessions_row = conn.execute(
                    f"""SELECT COUNT(DISTINCT st.session_uuid) as cnt
                    FROM session_tools st
                    JOIN sessions s ON st.session_uuid = s.uuid
                    {cs_where}""",
                    cs_params,
                ).fetchone()
                combined_sessions = combined_sessions_row["cnt"] if combined_sessions_row else 0

                return McpToolsOverview(
                    total_servers=mcp_data["total_servers"] + builtin_data["total_servers"],
                    total_tools=mcp_data["total_tools"] + builtin_data["total_tools"],
                    total_calls=mcp_data["total_calls"] + builtin_data["total_calls"],
                    total_sessions=combined_sessions,
                    servers=all_servers,
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
                mcp_data = query_mcp_tool_usage_trend(conn, project=project, period=period)
                builtin_data = query_builtin_tool_usage_trend(conn, project=project, period=period)

                # Merge by_item (no key collisions: mcp__ vs bare names)
                merged_by_item = {**mcp_data["by_item"], **builtin_data["by_item"]}
                merged_by_item = dict(
                    sorted(merged_by_item.items(), key=lambda x: x[1], reverse=True)
                )

                # Merge daily trends by date
                trend_map: dict[str, int] = {}
                for t in mcp_data["trend"]:
                    trend_map[t["date"]] = trend_map.get(t["date"], 0) + t["count"]
                for t in builtin_data["trend"]:
                    trend_map[t["date"]] = trend_map.get(t["date"], 0) + t["count"]
                merged_trend = [{"date": d, "count": c} for d, c in sorted(trend_map.items())]

                # Earliest first_used, latest last_used
                firsts = [
                    d.get("first_used") for d in (mcp_data, builtin_data) if d.get("first_used")
                ]
                lasts = [d.get("last_used") for d in (mcp_data, builtin_data) if d.get("last_used")]

                # Merge trend_by_item from both sources
                merged_trend_by_item: dict[str, list] = {}
                for item, points in mcp_data.get("trend_by_item", {}).items():
                    merged_trend_by_item[item] = [
                        UsageTrendItem(date=t["date"], count=t["count"]) for t in points
                    ]
                for item, points in builtin_data.get("trend_by_item", {}).items():
                    merged_trend_by_item[item] = [
                        UsageTrendItem(date=t["date"], count=t["count"]) for t in points
                    ]
                # No limit — frontend handles top-N display

                # Merge trend_by_user: sum counts per date across both sources
                merged_by_user: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
                for source in (mcp_data, builtin_data):
                    for user_id, points in source.get("trend_by_user", {}).items():
                        for pt in points:
                            merged_by_user[user_id][pt["date"]] += pt["count"]
                merged_trend_by_user = {
                    uid: [{"date": d, "count": c} for d, c in sorted(date_counts.items())]
                    for uid, date_counts in merged_by_user.items()
                }
                merged_user_names = {
                    **mcp_data.get("user_names", {}),
                    **builtin_data.get("user_names", {}),
                }

                return UsageTrendResponse(
                    total=mcp_data["total"] + builtin_data["total"],
                    by_item=merged_by_item,
                    trend=[UsageTrendItem(**t) for t in merged_trend],
                    trend_by_item=merged_trend_by_item,
                    trend_by_user=merged_trend_by_user,
                    user_names=merged_user_names,
                    first_used=min(firsts) if firsts else None,
                    last_used=max(lasts) if lasts else None,
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
                is_builtin = server_name.startswith("builtin-")

                if is_builtin:
                    detail = query_builtin_tool_detail(
                        conn, server_name, tool_name, project=project, period=period
                    )
                else:
                    detail = query_mcp_tool_detail(
                        conn, server_name, tool_name, project=project, period=period
                    )

                if detail is None:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Tool '{server_name}/{tool_name}' not found",
                    )

                full_name = detail["full_name"]

                # Paginated sessions
                p = paginate(detail["session_count"], page, per_page)
                if is_builtin:
                    sessions_data = query_sessions_by_builtin_tool(
                        conn,
                        tool_name,
                        project=project,
                        period=period,
                        limit=p["per_page"],
                        offset=p["offset"],
                    )
                else:
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
                is_builtin = server_name.startswith("builtin-")

                # Server detail (tools + aggregates)
                if is_builtin:
                    detail = query_builtin_server_detail(
                        conn, server_name, project=project, period=period
                    )
                else:
                    detail = query_mcp_server_detail(
                        conn, server_name, project=project, period=period
                    )

                if detail is None:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Server '{server_name}' not found",
                    )

                # Daily trend
                if is_builtin:
                    trend_data = query_builtin_server_trend(
                        conn, server_name, project=project, period=period
                    )
                else:
                    trend_data = query_mcp_server_trend(
                        conn, server_name, project=project, period=period
                    )

                # Paginated sessions
                p = paginate(detail["session_count"], page, per_page)
                if is_builtin:
                    sessions_data = query_sessions_by_builtin_server(
                        conn,
                        server_name,
                        project=project,
                        period=period,
                        limit=p["per_page"],
                        offset=p["offset"],
                    )
                else:
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
