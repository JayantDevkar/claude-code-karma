"""
Plugins router - view Claude Code installed plugins.

Provides endpoints for listing and viewing plugins installed via Claude Code's
plugin system. Plugin data is stored at ~/.claude/plugins/installed_plugins.json.

Phase 4: Plugins are optional/low priority but useful for plugin usage analytics.
"""

import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Annotated, Optional
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Query, Request

from command_helpers import is_plugin_skill
from http_caching import cacheable
from models import (
    PluginInstallation,
    get_plugins_file,
    load_installed_plugins,
)
from models.plugin import (
    get_plugin_description,
    read_command_contents,
    read_plugin_manifest,
    resolve_manifest_dirs,
    scan_plugin_capabilities,
)
from schemas import (
    DailyUsage,
    PluginCapabilities,
    PluginCommandDetail,
    PluginCommandsResponse,
    PluginDetail,
    PluginInstallationSchema,
    PluginsOverview,
    PluginSummary,
    PluginUsageStats,
    SkillContent,
    SkillItem,
)
from utils import utc_to_local_date

logger = logging.getLogger(__name__)


def _validate_plugin_name(name: str) -> str:
    """
    Validate and sanitize plugin name.

    Args:
        name: URL-decoded plugin name

    Returns:
        Validated plugin name

    Raises:
        HTTPException: If name is invalid
    """
    # Max length check
    if len(name) > 255:
        raise HTTPException(status_code=400, detail="Plugin name too long (max 255 chars)")

    # Empty check
    if not name or not name.strip():
        raise HTTPException(status_code=400, detail="Plugin name cannot be empty")

    # Character validation - allow alphanumeric, @, -, _, .
    if not re.match(r"^[a-zA-Z0-9@._-]+$", name):
        raise HTTPException(status_code=400, detail="Plugin name contains invalid characters")

    return name


# =============================================================================
# Plugin Usage Aggregation
# =============================================================================


def _get_plugin_short_name(plugin_full_name: str) -> str:
    """
    Extract short name from full plugin name.

    Examples:
        "oh-my-claudecode@anthropics/oh-my-claudecode" -> "oh-my-claudecode"
        "github@claude-plugins-official" -> "github"
    """
    return plugin_full_name.split("@")[0]


def _extract_mcp_tool_short_name(full_tool_name: str) -> str:
    """
    Extract short tool name from full MCP tool name.

    Examples:
        "mcp__plugin_playwright_playwright__browser_click" -> "browser_click"
        "mcp__plugin_github_github__add_issue_comment" -> "add_issue_comment"
    """
    parts = full_tool_name.split("__")
    return "__".join(parts[2:]) if len(parts) > 2 else full_tool_name


def _query_plugin_mcp_usage_sqlite(
    conn: sqlite3.Connection,
    plugin_short_name: str,
    period: str = "all",
) -> dict:
    """
    Query MCP tool usage from session_tools for a plugin.

    Args:
        conn: SQLite connection
        plugin_short_name: Plugin short name (e.g., "playwright")
        period: Time period filter - "day", "week", "month", or "all"

    Returns:
        Dict with total_mcp_tool_calls, by_mcp_tool, and daily_usage
    """
    from collections import Counter, defaultdict
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    cutoff = None
    if period == "day":
        cutoff = now - timedelta(days=1)
    elif period == "week":
        cutoff = now - timedelta(weeks=1)
    elif period == "month":
        cutoff = now - timedelta(days=30)

    time_filter = ""
    params: dict = {"pattern": f"mcp__plugin_{plugin_short_name}_%"}
    if cutoff:
        time_filter = "AND s.start_time >= :cutoff"
        params["cutoff"] = cutoff.isoformat()

    rows = conn.execute(
        f"""
        SELECT tool_name, count, start_time FROM (
            SELECT st.tool_name, st.count, s.start_time
            FROM session_tools st
            JOIN sessions s ON s.uuid = st.session_uuid
            WHERE st.tool_name LIKE :pattern {time_filter}
            UNION ALL
            SELECT sat.tool_name, sat.count, s.start_time
            FROM subagent_tools sat
            JOIN subagent_invocations si ON si.id = sat.invocation_id
            JOIN sessions s ON s.uuid = si.session_uuid
            WHERE sat.tool_name LIKE :pattern {time_filter}
        )
        ORDER BY start_time
        """,
        params,
    ).fetchall()

    if not rows:
        return {"total_mcp_tool_calls": 0, "by_mcp_tool": {}, "daily_usage": {}}

    by_mcp_tool: Counter = Counter()
    daily_usage: dict[str, int] = defaultdict(int)
    by_mcp_tool_daily: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    total = 0

    for row in rows:
        tool_name = row["tool_name"]
        count = row["count"]
        start_time = row["start_time"]

        short = _extract_mcp_tool_short_name(tool_name)
        by_mcp_tool[short] += count
        total += count

        if start_time:
            try:
                date_key = utc_to_local_date(datetime.fromisoformat(start_time))
                daily_usage[date_key] += count
                by_mcp_tool_daily[short][date_key] += count
            except (ValueError, TypeError):
                pass

    return {
        "total_mcp_tool_calls": total,
        "by_mcp_tool": dict(by_mcp_tool),
        "daily_usage": dict(daily_usage),
        "by_mcp_tool_daily": {k: dict(v) for k, v in by_mcp_tool_daily.items()},
    }


def _query_plugin_usage_sqlite(
    conn: sqlite3.Connection,
    plugin_short_name: str,
    period: str = "all",
) -> Optional[dict]:
    """
    Query plugin usage from SQLite session_skills and subagent_invocations tables.

    Args:
        conn: SQLite connection
        plugin_short_name: Plugin short name (e.g., "oh-my-claudecode")
        period: Time period filter - "day", "week", "month", or "all"

    Returns:
        Dict with plugin usage stats, or None if no data found
    """
    from datetime import timedelta

    # Calculate cutoff time based on period
    now = datetime.now(timezone.utc)
    cutoff = None
    if period == "day":
        cutoff = now - timedelta(days=1)
    elif period == "week":
        cutoff = now - timedelta(weeks=1)
    elif period == "month":
        cutoff = now - timedelta(days=30)

    # Build WHERE clause for time filtering
    time_filter = ""
    params = {"plugin": plugin_short_name}
    if cutoff:
        time_filter = "AND s.start_time >= :cutoff"
        params["cutoff"] = cutoff.isoformat()

    # Query skill invocations (exclude mentions, match both full and short form)
    skill_rows = conn.execute(
        f"""
        SELECT
            sk.skill_name,
            sk.count,
            s.start_time,
            s.total_cost
        FROM session_skills sk
        JOIN sessions s ON s.uuid = sk.session_uuid
        WHERE (sk.skill_name LIKE :plugin || ':%' OR sk.skill_name = :plugin)
            AND sk.invocation_source != 'text_detection'
            {time_filter}
        ORDER BY s.start_time
        """,
        params,
    ).fetchall()

    # Query agent runs
    agent_rows = conn.execute(
        f"""
        SELECT
            si.subagent_type,
            s.start_time,
            si.cost_usd
        FROM subagent_invocations si
        JOIN sessions s ON s.uuid = si.session_uuid
        WHERE si.subagent_type LIKE :plugin || ':%' {time_filter}
        ORDER BY s.start_time
        """,
        params,
    ).fetchall()

    # Query command invocations
    command_rows = conn.execute(
        f"""
        SELECT
            sc.command_name,
            sc.count,
            s.start_time,
            s.total_cost
        FROM session_commands sc
        JOIN sessions s ON s.uuid = sc.session_uuid
        WHERE (sc.command_name LIKE :plugin || ':%' OR sc.command_name = :plugin)
            AND sc.invocation_source != 'text_detection'
            {time_filter}
        ORDER BY s.start_time
        """,
        params,
    ).fetchall()

    # If no data found, return None
    if not skill_rows and not agent_rows and not command_rows:
        return None

    # Aggregate results
    from collections import Counter, defaultdict

    by_skill = Counter()
    by_agent = Counter()
    by_command = Counter()
    daily_usage = defaultdict(
        lambda: {"agent_runs": 0, "skill_invocations": 0, "command_invocations": 0, "cost_usd": 0.0}
    )
    by_agent_daily: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_skill_daily: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_command_daily: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    total_skill_invocations = 0
    total_agent_runs = 0
    total_command_invocations = 0
    total_cost = 0.0
    first_used = None
    last_used = None

    # Process skill invocations
    for row in skill_rows:
        skill_full_name = row["skill_name"]
        skill_short = (
            skill_full_name.split(":", 1)[1] if ":" in skill_full_name else skill_full_name
        )
        count = row["count"]
        start_time = datetime.fromisoformat(row["start_time"]) if row["start_time"] else None

        by_skill[skill_short] += count
        total_skill_invocations += count

        if start_time:
            date_key = utc_to_local_date(start_time)
            daily_usage[date_key]["skill_invocations"] += count
            by_skill_daily[skill_short][date_key] += count

            if first_used is None or start_time < first_used:
                first_used = start_time
            if last_used is None or start_time > last_used:
                last_used = start_time

    # Process agent runs
    for row in agent_rows:
        agent_full_type = row["subagent_type"]
        agent_short = (
            agent_full_type.split(":", 1)[1] if ":" in agent_full_type else agent_full_type
        )
        # Note: agent_rows has s.start_time not si.started_at
        start_time = datetime.fromisoformat(row["start_time"]) if row["start_time"] else None
        cost = row["cost_usd"] or 0.0

        by_agent[agent_short] += 1
        total_agent_runs += 1
        total_cost += cost

        if start_time:
            date_key = utc_to_local_date(start_time)
            daily_usage[date_key]["agent_runs"] += 1
            daily_usage[date_key]["cost_usd"] += cost
            by_agent_daily[agent_short][date_key] += 1

            if first_used is None or start_time < first_used:
                first_used = start_time
            if last_used is None or start_time > last_used:
                last_used = start_time

    # Process command invocations
    for row in command_rows:
        cmd_full_name = row["command_name"]
        cmd_short = cmd_full_name.split(":", 1)[1] if ":" in cmd_full_name else cmd_full_name
        count = row["count"]
        start_time = datetime.fromisoformat(row["start_time"]) if row["start_time"] else None

        by_command[cmd_short] += count
        total_command_invocations += count

        if start_time:
            date_key = utc_to_local_date(start_time)
            daily_usage[date_key]["command_invocations"] += count
            by_command_daily[cmd_short][date_key] += count

            if first_used is None or start_time < first_used:
                first_used = start_time
            if last_used is None or start_time > last_used:
                last_used = start_time

    return {
        "agent_runs": total_agent_runs,
        "skill_invocations": total_skill_invocations,
        "command_invocations": total_command_invocations,
        "cost_usd": total_cost,
        "by_agent": dict(by_agent),
        "by_skill": dict(by_skill),
        "by_command": dict(by_command),
        "by_agent_daily": {k: dict(v) for k, v in by_agent_daily.items()},
        "by_skill_daily": {k: dict(v) for k, v in by_skill_daily.items()},
        "by_command_daily": {k: dict(v) for k, v in by_command_daily.items()},
        "daily_usage": dict(daily_usage),
        "first_used": first_used,
        "last_used": last_used,
    }


def _collect_plugin_usage_sync(period: str = "all") -> dict[str, dict]:
    """
    Collect plugin usage statistics from sessions.

    Args:
        period: Time period filter - "day", "week", "month", or "all"

    Returns:
        Dict mapping plugin short name to usage stats with timestamps and trends
    """
    from collections import Counter, defaultdict
    from datetime import timedelta

    from models.content import ToolUseBlock
    from models.message import AssistantMessage
    from utils import list_all_projects

    # Calculate cutoff time based on period
    now = datetime.now(timezone.utc)
    cutoff = None
    if period == "day":
        cutoff = now - timedelta(days=1)
    elif period == "week":
        cutoff = now - timedelta(weeks=1)
    elif period == "month":
        cutoff = now - timedelta(days=30)
    # "all" means no cutoff

    plugin_stats: dict[str, dict] = defaultdict(
        lambda: {
            "agent_runs": 0,
            "skill_invocations": 0,
            "command_invocations": 0,
            "mcp_tool_calls": 0,
            "cost_usd": 0.0,
            "by_agent": Counter(),
            "by_skill": Counter(),
            "by_command": Counter(),
            "by_mcp_tool": Counter(),
            "by_agent_daily": defaultdict(lambda: defaultdict(int)),
            "by_skill_daily": defaultdict(lambda: defaultdict(int)),
            "by_command_daily": defaultdict(lambda: defaultdict(int)),
            "by_mcp_tool_daily": defaultdict(lambda: defaultdict(int)),
            "first_used": None,
            "last_used": None,
            "daily_usage": defaultdict(
                lambda: {
                    "agent_runs": 0,
                    "skill_invocations": 0,
                    "command_invocations": 0,
                    "mcp_tool_calls": 0,
                    "cost_usd": 0.0,
                }
            ),
        }
    )

    # Get known plugin short names for MCP tool matching
    known_plugin_shorts: set[str] = set()
    try:
        installed = load_installed_plugins()
        if installed:
            for name in installed.plugins:
                known_plugin_shorts.add(_get_plugin_short_name(name))
    except Exception:
        pass

    for project in list_all_projects():
        try:
            for session in project.list_sessions():
                # Get session timestamp for filtering and tracking
                session_time = getattr(session, "start_time", None) or getattr(
                    session, "created_at", None
                )

                # Ensure timezone-aware comparison
                if session_time and session_time.tzinfo is None:
                    session_time = session_time.replace(tzinfo=timezone.utc)

                # Skip sessions outside the period
                if cutoff and session_time and session_time < cutoff:
                    continue

                # Get date key for daily tracking
                date_key = utc_to_local_date(session_time) if session_time else "unknown"

                # Track which plugins are used in this session
                plugins_in_session = set()

                # Track skill invocations (keys are (name, source) tuples)
                skills_used = session.get_skills_used()
                for (skill_name, _inv_source), count in skills_used.items():
                    if is_plugin_skill(skill_name):
                        if ":" in skill_name:
                            plugin_name = skill_name.split(":")[0]
                            skill_short = skill_name.split(":", 1)[1]
                        else:
                            # Short-form: plugin name is the skill name
                            plugin_name = skill_name
                            skill_short = skill_name
                        plugins_in_session.add(plugin_name)
                        plugin_stats[plugin_name]["skill_invocations"] += count
                        plugin_stats[plugin_name]["by_skill"][skill_short] += count
                        plugin_stats[plugin_name]["by_skill_daily"][skill_short][date_key] += count
                        plugin_stats[plugin_name]["daily_usage"][date_key]["skill_invocations"] += (
                            count
                        )

                        # Track timestamps
                        if session_time:
                            if (
                                plugin_stats[plugin_name]["first_used"] is None
                                or session_time < plugin_stats[plugin_name]["first_used"]
                            ):
                                plugin_stats[plugin_name]["first_used"] = session_time
                            if (
                                plugin_stats[plugin_name]["last_used"] is None
                                or session_time > plugin_stats[plugin_name]["last_used"]
                            ):
                                plugin_stats[plugin_name]["last_used"] = session_time

                # Track command invocations
                commands_used = session.get_commands_used()
                for (cmd_name, _inv_source), count in commands_used.items():
                    if ":" in cmd_name:
                        plugin_name_cmd = cmd_name.split(":")[0]
                        cmd_short = cmd_name.split(":", 1)[1]
                    else:
                        continue  # Skip commands without plugin prefix
                    plugins_in_session.add(plugin_name_cmd)
                    plugin_stats[plugin_name_cmd]["command_invocations"] += count
                    plugin_stats[plugin_name_cmd]["by_command"][cmd_short] += count
                    plugin_stats[plugin_name_cmd]["by_command_daily"][cmd_short][date_key] += count
                    plugin_stats[plugin_name_cmd]["daily_usage"][date_key][
                        "command_invocations"
                    ] += count

                    # Track timestamps
                    if session_time:
                        if (
                            plugin_stats[plugin_name_cmd]["first_used"] is None
                            or session_time < plugin_stats[plugin_name_cmd]["first_used"]
                        ):
                            plugin_stats[plugin_name_cmd]["first_used"] = session_time
                        if (
                            plugin_stats[plugin_name_cmd]["last_used"] is None
                            or session_time > plugin_stats[plugin_name_cmd]["last_used"]
                        ):
                            plugin_stats[plugin_name_cmd]["last_used"] = session_time

                # Track agent runs and MCP tool calls by analyzing tool use blocks
                for msg in session.iter_messages():
                    if isinstance(msg, AssistantMessage):
                        for block in msg.content_blocks:
                            if not isinstance(block, ToolUseBlock):
                                continue

                            if block.name in ("Task", "Agent"):
                                subagent_type = block.input.get("subagent_type", "")
                                if ":" in subagent_type:
                                    plugin_name = subagent_type.split(":")[0]
                                    plugins_in_session.add(plugin_name)
                                    agent_short = subagent_type.split(":", 1)[1]
                                    plugin_stats[plugin_name]["agent_runs"] += 1
                                    plugin_stats[plugin_name]["by_agent"][agent_short] += 1
                                    plugin_stats[plugin_name]["by_agent_daily"][agent_short][
                                        date_key
                                    ] += 1
                                    plugin_stats[plugin_name]["daily_usage"][date_key][
                                        "agent_runs"
                                    ] += 1

                                    # Track timestamps
                                    if session_time:
                                        if (
                                            plugin_stats[plugin_name]["first_used"] is None
                                            or session_time
                                            < plugin_stats[plugin_name]["first_used"]
                                        ):
                                            plugin_stats[plugin_name]["first_used"] = session_time
                                        if (
                                            plugin_stats[plugin_name]["last_used"] is None
                                            or session_time > plugin_stats[plugin_name]["last_used"]
                                        ):
                                            plugin_stats[plugin_name]["last_used"] = session_time

                            elif block.name.startswith("mcp__plugin_") and known_plugin_shorts:
                                stripped = block.name[len("mcp__plugin_") :]
                                for short in known_plugin_shorts:
                                    if stripped.startswith(short + "_"):
                                        plugins_in_session.add(short)
                                        tool_short = _extract_mcp_tool_short_name(block.name)
                                        plugin_stats[short]["mcp_tool_calls"] += 1
                                        plugin_stats[short]["by_mcp_tool"][tool_short] += 1
                                        plugin_stats[short]["by_mcp_tool_daily"][tool_short][
                                            date_key
                                        ] += 1
                                        plugin_stats[short]["daily_usage"][date_key][
                                            "mcp_tool_calls"
                                        ] += 1

                                        if session_time:
                                            if (
                                                plugin_stats[short]["first_used"] is None
                                                or session_time < plugin_stats[short]["first_used"]
                                            ):
                                                plugin_stats[short]["first_used"] = session_time
                                            if (
                                                plugin_stats[short]["last_used"] is None
                                                or session_time > plugin_stats[short]["last_used"]
                                            ):
                                                plugin_stats[short]["last_used"] = session_time
                                        break

                # Calculate cost from session token usage
                if hasattr(session, "total_usage") and session.total_usage:
                    usage = session.total_usage
                    # Claude pricing estimates: $3/M input, $15/M output
                    input_cost = (usage.input_tokens / 1_000_000) * 3.0
                    output_cost = (usage.output_tokens / 1_000_000) * 15.0
                    session_cost = input_cost + output_cost

                    # Distribute cost equally among all plugins used in this session
                    if plugins_in_session:
                        cost_per_plugin = session_cost / len(plugins_in_session)
                        for plugin_name in plugins_in_session:
                            plugin_stats[plugin_name]["cost_usd"] += cost_per_plugin
                            plugin_stats[plugin_name]["daily_usage"][date_key]["cost_usd"] += (
                                cost_per_plugin
                            )
        except Exception as e:
            logger.debug(f"Error processing project {project.encoded_name}: {e}")
            continue

    # Convert to serializable format
    for plugin_name in plugin_stats:
        plugin_stats[plugin_name]["by_agent"] = dict(plugin_stats[plugin_name]["by_agent"])
        plugin_stats[plugin_name]["by_skill"] = dict(plugin_stats[plugin_name]["by_skill"])
        plugin_stats[plugin_name]["by_command"] = dict(plugin_stats[plugin_name]["by_command"])
        plugin_stats[plugin_name]["by_mcp_tool"] = dict(plugin_stats[plugin_name]["by_mcp_tool"])
        plugin_stats[plugin_name]["by_agent_daily"] = {
            k: dict(v) for k, v in plugin_stats[plugin_name]["by_agent_daily"].items()
        }
        plugin_stats[plugin_name]["by_skill_daily"] = {
            k: dict(v) for k, v in plugin_stats[plugin_name]["by_skill_daily"].items()
        }
        plugin_stats[plugin_name]["by_command_daily"] = {
            k: dict(v) for k, v in plugin_stats[plugin_name]["by_command_daily"].items()
        }
        plugin_stats[plugin_name]["by_mcp_tool_daily"] = {
            k: dict(v) for k, v in plugin_stats[plugin_name]["by_mcp_tool_daily"].items()
        }
        plugin_stats[plugin_name]["daily_usage"] = dict(plugin_stats[plugin_name]["daily_usage"])

    return dict(plugin_stats)


# Module-level cache for plugin usage (refreshed every 5 minutes)
# Cache is keyed by period for period-specific results
_plugin_usage_cache: dict[str, dict[str, dict]] = {}  # {period: stats}
_plugin_usage_cache_time: dict[str, datetime] = {}  # {period: timestamp}
_plugin_usage_cache_lock = Lock()


def get_plugin_usage_stats(period: str = "all") -> dict[str, dict]:
    """
    Get cached plugin usage statistics.

    Returns cached stats if available and fresh (<5 minutes old),
    otherwise recollects from session data.

    Thread-safe with double-checked locking to avoid blocking during heavy I/O.
    """
    global _plugin_usage_cache, _plugin_usage_cache_time

    now = datetime.now(timezone.utc)
    cache_ttl_seconds = 300  # 5 minutes

    # First check (without lock for fast path)
    cached_time = _plugin_usage_cache_time.get(period)
    if (
        period in _plugin_usage_cache
        and cached_time is not None
        and (now - cached_time).total_seconds() < cache_ttl_seconds
    ):
        return _plugin_usage_cache[period]

    # Cache miss - compute outside the lock
    new_stats = _collect_plugin_usage_sync(period)

    # Acquire lock only for the update
    with _plugin_usage_cache_lock:
        # Double-check: another thread may have updated while we computed
        cached_time = _plugin_usage_cache_time.get(period)
        if (
            period in _plugin_usage_cache
            and cached_time is not None
            and (now - cached_time).total_seconds() < cache_ttl_seconds
        ):
            # Another thread beat us, use their result
            return _plugin_usage_cache[period]

        # Update cache with our result
        _plugin_usage_cache[period] = new_stats
        _plugin_usage_cache_time[period] = now

    return new_stats


router = APIRouter()


# =============================================================================
# Converter Functions
# =============================================================================


def installation_to_schema(
    plugin_name: str, installation: PluginInstallation
) -> PluginInstallationSchema:
    """
    Convert a PluginInstallation model to schema for API responses.

    Args:
        plugin_name: Name of the plugin (e.g., "github@claude-plugins-official")
        installation: PluginInstallation instance

    Returns:
        PluginInstallationSchema for API response
    """
    return PluginInstallationSchema(
        plugin_name=plugin_name,
        scope=installation.scope,
        install_path=installation.install_path,
        version=installation.version,
        installed_at=installation.installed_at,
        last_updated=installation.last_updated,
    )


def plugin_to_summary(
    plugin_name: str,
    installations: list[PluginInstallation],
    usage_stats: dict[str, dict] | None = None,
) -> PluginSummary:
    """
    Convert plugin installations to a summary for API responses.

    Args:
        plugin_name: Name of the plugin
        installations: List of all installations for this plugin
        usage_stats: Optional pre-fetched usage stats dict

    Returns:
        PluginSummary schema for API response
    """
    # Find latest update across all installations
    latest_installation = (
        max(installations, key=lambda i: i.last_updated) if installations else None
    )

    # Get capabilities count
    capabilities = scan_plugin_capabilities(plugin_name)
    agent_count = len(capabilities.get("agents", []))
    skill_count = len(capabilities.get("skills", []))
    command_count = len(capabilities.get("commands", []))

    # Calculate days since update
    days_since_update = 0
    if latest_installation:
        now = datetime.now(timezone.utc)
        if latest_installation.last_updated.tzinfo:
            days_since_update = (now - latest_installation.last_updated).days
        else:
            days_since_update = (datetime.now(timezone.utc) - latest_installation.last_updated).days

    # Get description
    description = get_plugin_description(plugin_name)

    # Check if official (contains "claude-plugins-official" in name)
    is_official = "claude-plugins-official" in plugin_name

    # Get usage from cached stats
    short_name = _get_plugin_short_name(plugin_name)
    plugin_usage = (usage_stats or {}).get(short_name, {})
    total_runs = (
        plugin_usage.get("agent_runs", 0)
        + plugin_usage.get("skill_invocations", 0)
        + plugin_usage.get("command_invocations", 0)
        + plugin_usage.get("mcp_tool_calls", 0)
    )
    estimated_cost = plugin_usage.get("cost_usd", 0.0)

    return PluginSummary(
        name=plugin_name,
        installation_count=len(installations),
        scopes=list(set(i.scope for i in installations)),
        latest_version=latest_installation.version if latest_installation else "",
        latest_update=latest_installation.last_updated if latest_installation else None,
        agent_count=agent_count,
        skill_count=skill_count,
        command_count=command_count,
        total_runs=total_runs,
        estimated_cost_usd=estimated_cost,
        days_since_update=days_since_update,
        description=description,
        is_official=is_official,
    )


def plugin_to_detail(plugin_name: str, installations: list[PluginInstallation]) -> PluginDetail:
    """
    Convert plugin installations to detail for API responses.

    Args:
        plugin_name: Name of the plugin
        installations: List of all installations for this plugin

    Returns:
        PluginDetail schema with all installations
    """
    capabilities_data = scan_plugin_capabilities(plugin_name)
    description = get_plugin_description(plugin_name)

    # Augment/validate MCP tools from SQLite usage data
    # SQLite is the source of truth for which servers actually exist and are used
    short_name = _get_plugin_short_name(plugin_name)
    try:
        from db.connection import sqlite_read

        with sqlite_read() as conn:
            if conn is not None:
                pattern = f"mcp__plugin_{short_name}_%"
                rows = conn.execute(
                    """
                    SELECT DISTINCT tool_name FROM session_tools WHERE tool_name LIKE ?
                    UNION
                    SELECT DISTINCT tool_name FROM subagent_tools WHERE tool_name LIKE ?
                    """,
                    (pattern, pattern),
                ).fetchall()
                # Collect servers that have actual usage
                used_servers: set[str] = set()
                for row in rows:
                    parts = row[0].split("__")  # mcp__{server}__{tool}
                    if len(parts) >= 3:
                        used_servers.add(parts[1])
                # Keep filesystem-discovered servers only if they have usage,
                # plus add any servers found in usage but not on filesystem
                fs_servers = set(capabilities_data.get("mcp_tools", []))
                validated = [s for s in fs_servers if s in used_servers]
                for s in used_servers:
                    if s not in fs_servers:
                        validated.append(s)
                capabilities_data["mcp_tools"] = validated
    except Exception:
        pass  # SQLite unavailable, use filesystem-only results

    capabilities = PluginCapabilities(
        plugin_name=plugin_name,
        agents=capabilities_data.get("agents", []),
        skills=capabilities_data.get("skills", []),
        commands=capabilities_data.get("commands", []),
        mcp_tools=capabilities_data.get("mcp_tools", []),
        hooks=capabilities_data.get("hooks", []),
    )

    return PluginDetail(
        name=plugin_name,
        description=description,
        installations=[installation_to_schema(plugin_name, i) for i in installations],
        capabilities=capabilities,
        usage=None,  # Populated separately via /usage endpoint
    )


# =============================================================================
# Endpoints
# =============================================================================


@router.get("", response_model=PluginsOverview)
@cacheable(max_age=300, stale_while_revalidate=600, private=True)
def list_plugins(
    request: Request,
    include_usage: Annotated[bool, Query(description="Include usage stats (slow)")] = True,
) -> PluginsOverview:
    """
    List all installed plugins from ~/.claude/plugins/installed_plugins.json.

    Plugins are sorted alphabetically by name.
    Each plugin summary includes:
    - name: Plugin identifier (e.g., "github@claude-plugins-official")
    - installation_count: Number of installations
    - scopes: All scopes this plugin is installed in
    - latest_version: Most recent version
    - latest_update: Most recent update timestamp

    Cache: 5 minutes (plugins change infrequently)
    """
    plugins_file = get_plugins_file()

    if not plugins_file.exists():
        logger.debug(f"Plugins file does not exist: {plugins_file}")
        return PluginsOverview(
            version=0,
            total_plugins=0,
            total_installations=0,
            plugins=[],
        )

    installed = load_installed_plugins()

    if not installed:
        return PluginsOverview(
            version=0,
            total_plugins=0,
            total_installations=0,
            plugins=[],
        )

    # Fetch usage stats once for all plugins (skip when include_usage=False for fast response)
    usage_stats = get_plugin_usage_stats() if include_usage else None

    summaries = [
        plugin_to_summary(name, installations, usage_stats)
        for name, installations in sorted(installed.plugins.items())
    ]

    return PluginsOverview(
        version=installed.version,
        total_plugins=installed.plugin_count,
        total_installations=installed.total_installations,
        plugins=summaries,
    )


@router.get("/stats")
@cacheable(max_age=300, stale_while_revalidate=600, private=True)
def get_plugins_stats(request: Request) -> dict:
    """
    Get aggregate statistics about installed plugins.

    Returns:
        - total_plugins: Number of unique plugins
        - total_installations: Total installation count
        - version: Plugin file schema version
        - by_scope: Count of installations by scope
        - oldest_install: Timestamp of oldest installation
        - newest_install: Timestamp of newest installation
    """
    installed = load_installed_plugins()

    if not installed:
        return {
            "total_plugins": 0,
            "total_installations": 0,
            "version": 0,
            "by_scope": {},
            "oldest_install": None,
            "newest_install": None,
        }

    # Collect all installations for stats
    all_installations = installed.list_all_installations()

    # Count by scope
    scope_counts: dict[str, int] = {}
    oldest = None
    newest = None

    for _, installation in all_installations:
        scope_counts[installation.scope] = scope_counts.get(installation.scope, 0) + 1

        if oldest is None or installation.installed_at < oldest:
            oldest = installation.installed_at
        if newest is None or installation.last_updated > newest:
            newest = installation.last_updated

    return {
        "total_plugins": installed.plugin_count,
        "total_installations": installed.total_installations,
        "version": installed.version,
        "by_scope": scope_counts,
        "oldest_install": oldest.isoformat() if oldest else None,
        "newest_install": newest.isoformat() if newest else None,
    }


@router.get("/{plugin_name}/capabilities", response_model=PluginCapabilities)
@cacheable(max_age=300, stale_while_revalidate=600, private=True)
def get_plugin_capabilities(plugin_name: str, request: Request) -> PluginCapabilities:
    """
    Get capabilities (agents, skills, commands, hooks) for a specific plugin.

    Args:
        plugin_name: Plugin identifier (URL-decoded automatically)

    Returns:
        Plugin capabilities breakdown

    Raises:
        404: Plugin not found
    """
    decoded_name = _validate_plugin_name(unquote(plugin_name))

    installed = load_installed_plugins()
    if not installed or not installed.has_plugin(decoded_name):
        raise HTTPException(status_code=404, detail=f"Plugin '{decoded_name}' not found")

    capabilities = scan_plugin_capabilities(decoded_name)

    return PluginCapabilities(
        plugin_name=decoded_name,
        agents=capabilities.get("agents", []),
        skills=capabilities.get("skills", []),
        commands=capabilities.get("commands", []),
        mcp_tools=capabilities.get("mcp_tools", []),
        hooks=capabilities.get("hooks", []),
    )


@router.get("/{plugin_name}/usage", response_model=PluginUsageStats)
@cacheable(max_age=60, stale_while_revalidate=120, private=True)
def get_plugin_usage(
    plugin_name: str,
    request: Request,
    period: Annotated[str, Query(description="Time period: day, week, month, all")] = "month",
) -> PluginUsageStats:
    """
    Get usage analytics for a specific plugin.

    Aggregates agent runs and skill invocations from session data.

    Args:
        plugin_name: Plugin identifier (URL-decoded automatically)
        period: Time period for analytics (day, week, month, all)

    Returns:
        Plugin usage statistics

    Raises:
        404: Plugin not found
    """
    decoded_name = _validate_plugin_name(unquote(plugin_name))

    installed = load_installed_plugins()
    if not installed or not installed.has_plugin(decoded_name):
        raise HTTPException(status_code=404, detail=f"Plugin '{decoded_name}' not found")

    short_name = _get_plugin_short_name(decoded_name)

    # SQLite fast path
    try:
        from db.connection import sqlite_read

        with sqlite_read() as conn:
            if conn is not None:
                plugin_usage = _query_plugin_usage_sqlite(conn, short_name, period)
                mcp_usage = _query_plugin_mcp_usage_sqlite(conn, short_name, period)

                if plugin_usage is not None or mcp_usage.get("total_mcp_tool_calls", 0) > 0:
                    if plugin_usage is None:
                        plugin_usage = {
                            "agent_runs": 0,
                            "skill_invocations": 0,
                            "command_invocations": 0,
                            "cost_usd": 0.0,
                            "by_agent": {},
                            "by_skill": {},
                            "by_agent_daily": {},
                            "by_skill_daily": {},
                            "by_command": {},
                            "by_command_daily": {},
                            "daily_usage": {},
                            "first_used": None,
                            "last_used": None,
                        }

                    # Merge MCP daily data into trend
                    daily_usage = plugin_usage.get("daily_usage", {})
                    mcp_daily = mcp_usage.get("daily_usage", {})
                    all_dates = set(daily_usage.keys()) | set(mcp_daily.keys())

                    trend = [
                        DailyUsage(
                            date=date,
                            agent_runs=daily_usage.get(date, {}).get("agent_runs", 0)
                            if isinstance(daily_usage.get(date), dict)
                            else 0,
                            skill_invocations=daily_usage.get(date, {}).get("skill_invocations", 0)
                            if isinstance(daily_usage.get(date), dict)
                            else 0,
                            command_invocations=daily_usage.get(date, {}).get(
                                "command_invocations", 0
                            )
                            if isinstance(daily_usage.get(date), dict)
                            else 0,
                            mcp_tool_calls=mcp_daily.get(date, 0),
                            cost_usd=daily_usage.get(date, {}).get("cost_usd", 0.0)
                            if isinstance(daily_usage.get(date), dict)
                            else 0.0,
                        )
                        for date in sorted(all_dates)
                        if date != "unknown"
                    ]

                    return PluginUsageStats(
                        plugin_name=decoded_name,
                        total_agent_runs=plugin_usage.get("agent_runs", 0),
                        total_skill_invocations=plugin_usage.get("skill_invocations", 0),
                        total_command_invocations=plugin_usage.get("command_invocations", 0),
                        total_mcp_tool_calls=mcp_usage.get("total_mcp_tool_calls", 0),
                        estimated_cost_usd=plugin_usage.get("cost_usd", 0.0),
                        by_agent=plugin_usage.get("by_agent", {}),
                        by_skill=plugin_usage.get("by_skill", {}),
                        by_command=plugin_usage.get("by_command", {}),
                        by_mcp_tool=mcp_usage.get("by_mcp_tool", {}),
                        by_agent_daily=plugin_usage.get("by_agent_daily", {}),
                        by_skill_daily=plugin_usage.get("by_skill_daily", {}),
                        by_command_daily=plugin_usage.get("by_command_daily", {}),
                        by_mcp_tool_daily=mcp_usage.get("by_mcp_tool_daily", {}),
                        trend=trend,
                        first_used=plugin_usage.get("first_used"),
                        last_used=plugin_usage.get("last_used"),
                    )
    except sqlite3.Error as e:
        logger.warning("SQLite plugin usage query failed, falling back: %s", e)

    # JSONL fallback: Get usage from cached stats with period filtering
    usage_stats = get_plugin_usage_stats(period)
    plugin_usage = usage_stats.get(short_name, {})

    # Convert daily_usage to trend list sorted by date
    daily_usage = plugin_usage.get("daily_usage", {})
    trend = [
        DailyUsage(
            date=date,
            agent_runs=data.get("agent_runs", 0),
            skill_invocations=data.get("skill_invocations", 0),
            command_invocations=data.get("command_invocations", 0),
            mcp_tool_calls=data.get("mcp_tool_calls", 0),
            cost_usd=data.get("cost_usd", 0.0),
        )
        for date, data in sorted(daily_usage.items())
        if date != "unknown"
    ]

    return PluginUsageStats(
        plugin_name=decoded_name,
        total_agent_runs=plugin_usage.get("agent_runs", 0),
        total_skill_invocations=plugin_usage.get("skill_invocations", 0),
        total_command_invocations=plugin_usage.get("command_invocations", 0),
        total_mcp_tool_calls=plugin_usage.get("mcp_tool_calls", 0),
        estimated_cost_usd=plugin_usage.get("cost_usd", 0.0),
        by_agent=plugin_usage.get("by_agent", {}),
        by_skill=plugin_usage.get("by_skill", {}),
        by_command=plugin_usage.get("by_command", {}),
        by_mcp_tool=plugin_usage.get("by_mcp_tool", {}),
        by_agent_daily=plugin_usage.get("by_agent_daily", {}),
        by_skill_daily=plugin_usage.get("by_skill_daily", {}),
        by_command_daily=plugin_usage.get("by_command_daily", {}),
        by_mcp_tool_daily=plugin_usage.get("by_mcp_tool_daily", {}),
        trend=trend,
        first_used=plugin_usage.get("first_used"),
        last_used=plugin_usage.get("last_used"),
    )


@router.get("/{plugin_name}/commands", response_model=PluginCommandsResponse)
@cacheable(max_age=300, stale_while_revalidate=600, private=True)
def get_plugin_commands(plugin_name: str, request: Request) -> PluginCommandsResponse:
    """
    Get commands for a specific plugin with their .md file contents.

    Args:
        plugin_name: Plugin identifier (URL-decoded automatically)

    Returns:
        Plugin commands with markdown content

    Raises:
        404: Plugin not found
    """
    decoded_name = _validate_plugin_name(unquote(plugin_name))

    installed = load_installed_plugins()
    if not installed or not installed.has_plugin(decoded_name):
        raise HTTPException(status_code=404, detail=f"Plugin '{decoded_name}' not found")

    command_data = read_command_contents(decoded_name)

    return PluginCommandsResponse(
        plugin_name=decoded_name,
        commands=[
            PluginCommandDetail(name=cmd["name"], content=cmd["content"]) for cmd in command_data
        ],
    )


@router.get("/{plugin_name:path}/skills", response_model=list[SkillItem])
@cacheable(max_age=300, stale_while_revalidate=600, private=True)
def list_plugin_skills(plugin_name: str, request: Request) -> list[SkillItem]:
    """
    List skills in a plugin's skills and commands directories.

    Plugin skills are SKILL.md files in {install_path}/skills/**/SKILL.md and
    markdown files in {install_path}/commands/*.md. Also checks manifest custom paths.
    Returns empty list if the plugin has no skills/commands or if they are empty.

    Args:
        plugin_name: Plugin identifier (URL-decoded automatically)

    Returns:
        List of skill items (files) sorted by name

    Raises:
        404: Plugin not found

    Cache: 5 minutes (plugin skills change infrequently)
    """
    # URL decode the plugin name
    decoded_name = unquote(plugin_name)

    installed = load_installed_plugins()

    if not installed:
        raise HTTPException(
            status_code=404,
            detail=f"No plugins installed. Plugin '{decoded_name}' not found.",
        )

    installations = installed.get_plugin(decoded_name)

    if not installations:
        raise HTTPException(
            status_code=404,
            detail=f"Plugin '{decoded_name}' not found in installed plugins.",
        )

    install_path = Path(installations[0].install_path)
    manifest = read_plugin_manifest(install_path)

    items: list[SkillItem] = []
    seen_names: set[str] = set()

    # Scan skills directories for SKILL.md files
    for skills_dir in resolve_manifest_dirs(install_path, manifest, "skills", ["skills"]):
        try:
            for skill_md in sorted(
                skills_dir.rglob("SKILL.md"), key=lambda p: p.parent.name.lower()
            ):
                name = skill_md.parent.name
                if name in seen_names:
                    continue
                seen_names.add(name)
                try:
                    stat = skill_md.stat()
                    items.append(
                        SkillItem(
                            name=name,
                            path=name,
                            type="file",
                            size_bytes=stat.st_size,
                            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                        )
                    )
                except OSError as e:
                    logger.warning(f"Failed to stat skill file {skill_md}: {e}")
        except OSError as e:
            logger.error(f"Failed to scan skills directory {skills_dir}: {e}")

    # Scan commands directories for .md files
    for commands_dir in resolve_manifest_dirs(install_path, manifest, "commands", ["commands"]):
        try:
            for entry in sorted(commands_dir.iterdir(), key=lambda p: p.name.lower()):
                if entry.name.startswith(".") or not entry.is_file():
                    continue
                if entry.name in seen_names or entry.stem in seen_names:
                    continue
                seen_names.add(entry.name)
                seen_names.add(entry.stem)
                try:
                    stat = entry.stat()
                    items.append(
                        SkillItem(
                            name=entry.name,
                            path=entry.name,
                            type="file",
                            size_bytes=stat.st_size,
                            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                        )
                    )
                except OSError as e:
                    logger.warning(f"Failed to process skill entry {entry}: {e}")
        except OSError as e:
            logger.error(f"Failed to list commands directory {commands_dir}: {e}")
            raise HTTPException(
                status_code=500, detail="Failed to list plugin skills directory"
            ) from e

    # Sort alphabetically by name
    return sorted(items, key=lambda x: x.name.lower())


@router.get("/{plugin_name:path}/skills/content", response_model=SkillContent)
@cacheable(max_age=300, stale_while_revalidate=600, private=True)
def get_plugin_skill_content(
    plugin_name: str,
    path: str = Query(..., description="Relative path within skills/commands directory"),
    request: Request = None,
) -> SkillContent:
    """
    Get content of a specific plugin skill file.

    Searches manifest custom paths in addition to default skills/ and commands/ dirs.

    Args:
        plugin_name: Plugin identifier (URL-decoded automatically)
        path: Relative path to the skill file (name only or subdirectory/name)

    Returns:
        Skill file content and metadata

    Raises:
        400: Invalid path (directory traversal attempt)
        404: Plugin not found or file not found

    Cache: 5 minutes (plugin skills change infrequently)
    """
    # URL decode the plugin name
    decoded_name = unquote(plugin_name)

    installed = load_installed_plugins()

    if not installed:
        raise HTTPException(
            status_code=404,
            detail=f"No plugins installed. Plugin '{decoded_name}' not found.",
        )

    installations = installed.get_plugin(decoded_name)

    if not installations:
        raise HTTPException(
            status_code=404,
            detail=f"Plugin '{decoded_name}' not found in installed plugins.",
        )

    # Validate path for security (prevent directory traversal)
    clean_path = path.strip("/").strip()

    if not clean_path:
        raise HTTPException(status_code=400, detail="Invalid path")

    # Prevent directory traversal
    if ".." in clean_path:
        raise HTTPException(status_code=400, detail="Path traversal not allowed")

    install_path = Path(installations[0].install_path)
    manifest = read_plugin_manifest(install_path)

    target_file = None

    # Search skills directories for SKILL.md (path is skill name)
    for skills_dir in resolve_manifest_dirs(install_path, manifest, "skills", ["skills"]):
        candidate = (skills_dir / clean_path / "SKILL.md").resolve()
        try:
            candidate.relative_to(skills_dir.resolve())
        except ValueError:
            continue
        if candidate.is_file():
            target_file = candidate
            break

    # Search commands directories for .md file
    if target_file is None:
        for commands_dir in resolve_manifest_dirs(install_path, manifest, "commands", ["commands"]):
            candidate = (commands_dir / clean_path).resolve()
            try:
                candidate.relative_to(commands_dir.resolve())
            except ValueError:
                continue
            if candidate.is_file():
                target_file = candidate
                break

    if target_file is None:
        raise HTTPException(status_code=404, detail="File not found")

    if not target_file.is_file():
        raise HTTPException(status_code=400, detail="Path is not a file")

    # Read the file content
    try:
        content = target_file.read_text(encoding="utf-8")
        stat = target_file.stat()

        return SkillContent(
            name=target_file.name,
            path=clean_path,
            content=content,
            size_bytes=stat.st_size,
            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        )
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File is not valid UTF-8 text") from None
    except OSError as e:
        logger.error(f"Failed to read skill file {target_file}: {e}")
        raise HTTPException(status_code=500, detail="Failed to read skill file") from e


@router.get("/installed-skills")
@cacheable(max_age=120, stale_while_revalidate=300, private=True)
def list_installed_skills(request: Request) -> list[dict]:
    """
    List all skills across all installed plugins.

    Returns a flat list of skill entries with prefixed names (e.g. "superpowers:brainstorming"),
    suitable for merging with usage data to show 0-use plugin skills on the skills page.

    Cache: 2 minutes
    """
    installed = load_installed_plugins()

    if not installed:
        return []

    seen: set[str] = set()
    result: list[dict] = []

    for plugin_name in installed.plugins:
        full_name = installed.get_plugin_full_name(plugin_name) or plugin_name
        short_name = _get_plugin_short_name(full_name)
        capabilities = scan_plugin_capabilities(plugin_name)
        for skill_name in capabilities.get("skills", []):
            prefixed = f"{short_name}:{skill_name}"
            if prefixed in seen:
                continue
            seen.add(prefixed)
            result.append(
                {
                    "name": prefixed,
                    "plugin": full_name,
                    "category": "plugin_skill",
                }
            )

    return result


@router.get("/{plugin_name:path}", response_model=PluginDetail)
@cacheable(max_age=300, stale_while_revalidate=600, private=True)
def get_plugin(plugin_name: str, request: Request) -> PluginDetail:
    """
    Get details for a specific plugin by name.

    Plugin names often contain special characters (e.g., "github@claude-plugins-official"),
    so the path parameter accepts any string.

    Args:
        plugin_name: Plugin identifier (URL-decoded automatically)

    Returns:
        Full plugin details with all installations

    Raises:
        404: Plugin not found
    """
    # URL decode the plugin name (handles @ and other special chars)
    decoded_name = _validate_plugin_name(unquote(plugin_name))

    installed = load_installed_plugins()

    if not installed:
        raise HTTPException(
            status_code=404,
            detail=f"No plugins installed. Plugin '{decoded_name}' not found.",
        )

    installations = installed.get_plugin(decoded_name)

    if not installations:
        raise HTTPException(
            status_code=404,
            detail=f"Plugin '{decoded_name}' not found in installed plugins.",
        )

    # Resolve to full name (handles short name lookups like "feature-dev")
    resolved_name = installed.get_plugin_full_name(decoded_name) or decoded_name

    return plugin_to_detail(resolved_name, installations)
