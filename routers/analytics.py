"""
Analytics router - project-level analytics and aggregations.

Phase 3: HTTP caching with Cache-Control headers.
"""

import logging
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

# Add models and api to path
api_path = Path(__file__).parent.parent
models_path = api_path.parent.parent
sys.path.insert(0, str(api_path))
sys.path.insert(0, str(models_path))

# Phase 3: HTTP caching
from http_caching import cacheable
from models import AssistantMessage, Project, ToolUseBlock
from schemas import DashboardStats, ProjectAnalytics, WorkModeDistribution
from utils import list_all_projects, parse_timestamp_range

router = APIRouter()
logger = logging.getLogger(__name__)


from models.usage import TokenUsage


def _get_analytics_sqlite(
    project: Optional[str],
    start_dt: Optional[datetime],
    end_dt: Optional[datetime],
    tz_offset_minutes: int,
) -> ProjectAnalytics | None:
    """SQLite fast path for analytics aggregation."""
    try:
        from db.connection import sqlite_read
        from db.queries import query_analytics

        with sqlite_read() as conn:
            if conn is None:
                return None
            data = query_analytics(conn, project=project, start_dt=start_dt, end_dt=end_dt)
        totals = data["totals"]

        # Models already parsed by SQLite's json_each()
        models_used_counter: Counter[str] = Counter()
        models_categorized_counter: Counter[str] = Counter()
        for model in data["models_used_list"]:
            models_used_counter[model] += 1
            models_categorized_counter[_categorize_model(model)] += 1

        # Build temporal heatmap from start_times
        local_tz = timezone(timedelta(minutes=-tz_offset_minutes))
        sessions_by_date: Counter[str] = Counter()
        temporal_heatmap = [[0 for _ in range(24)] for _ in range(7)]
        for ts_str in data["start_times"]:
            try:
                ts = datetime.fromisoformat(ts_str)
                local_time = ts.astimezone(local_tz)
                sessions_by_date[local_time.strftime("%Y-%m-%d")] += 1
                temporal_heatmap[local_time.weekday()][local_time.hour] += 1
            except (ValueError, TypeError):
                continue

        # Peak hours
        hour_totals = [(sum(temporal_heatmap[d][h] for d in range(7)), h) for h in range(24)]
        hour_totals.sort(reverse=True)
        peak_hours = [h for _, h in hour_totals[:3] if hour_totals[0][0] > 0]

        # Cache hit rate
        total_cacheable = (
            totals["total_input"] + totals["total_cache_creation"] + totals["total_cache_read"]
        )
        cache_hit_rate = (
            totals["total_cache_read"] / total_cacheable if total_cacheable > 0 else 0.0
        )

        # Time distribution
        time_distribution = _calculate_time_distribution(temporal_heatmap)
        work_mode_distribution = _calculate_work_mode_distribution(dict(data["tools"]))

        return ProjectAnalytics(
            total_sessions=totals["total_sessions"],
            total_tokens=totals["total_input"] + totals["total_output"],
            total_input_tokens=totals["total_input"],
            total_output_tokens=totals["total_output"],
            total_duration_seconds=totals["total_duration"],
            estimated_cost_usd=round(totals["total_cost"], 4),
            models_used=dict(models_used_counter),
            cache_hit_rate=round(cache_hit_rate, 4),
            tools_used=dict(data["tools"]),
            sessions_by_date=dict(sessions_by_date),
            temporal_heatmap=temporal_heatmap,
            peak_hours=peak_hours,
            models_categorized=dict(models_categorized_counter),
            time_distribution=time_distribution,
            work_mode_distribution=work_mode_distribution,
            projects_active=totals.get("projects_active", 0),
        )
    except sqlite3.Error as e:
        logger.warning("SQLite analytics query failed, falling back: %s", e)
        return None


@router.get("")
@cacheable(max_age=120, stale_while_revalidate=300, private=True)
def get_global_analytics(
    request: Request,
    start_ts: Optional[int] = Query(None, description="Start timestamp (Unix milliseconds)"),
    end_ts: Optional[int] = Query(None, description="End timestamp (Unix milliseconds)"),
    tz_offset: Optional[int] = Query(
        0,
        description="Timezone offset in minutes from UTC (e.g., 480 for PST). "
        "Matches JavaScript's getTimezoneOffset() convention.",
    ),
    use_index: bool = Query(
        True,
        description="Use sessions-index.json for fast lightweight analytics. "
        "Set to false for full token/tool metrics.",
    ),
):
    """
    Get aggregated analytics for all projects, optionally filtered by time range.

    Phase 3: Moderate cache (2min) - aggregated computed data.
    Phase 4: Uses early date filtering when date range specified.
    Phase 6: Simplified timestamp-based filtering (no timezone math needed).
    Phase 7: Timezone-aware date grouping for sessions_by_date and temporal_heatmap.
    Phase 8: Session index optimization - avoids JSONL parsing when use_index=true.
    """
    # Parse timestamp parameters to UTC datetimes
    start_dt, end_dt = parse_timestamp_range(start_ts, end_ts)

    # SQLite fast path
    sqlite_result = _get_analytics_sqlite(None, start_dt, end_dt, tz_offset or 0)
    if sqlite_result is not None:
        return sqlite_result

    # Get all projects with valid directories
    projects = [p for p in list_all_projects() if p.exists]

    all_sessions = []
    projects_active = 0
    for project in projects:
        try:
            if use_index:
                # Try index-based fast path first
                try:
                    index_entries = project.list_session_index_entries()

                    # Apply date filtering to index entries
                    if start_dt or end_dt:
                        filtered_entries = []
                        for entry in index_entries:
                            if start_dt and entry.start_time and entry.start_time < start_dt:
                                continue
                            if end_dt and entry.start_time and entry.start_time > end_dt:
                                continue
                            filtered_entries.append(entry)
                        index_entries = filtered_entries

                    if index_entries:
                        projects_active += 1
                        all_sessions.extend(index_entries)
                        continue
                except Exception:
                    # Fall through to full session loading
                    pass

            # Fallback: Full session loading with JSONL parsing
            # Phase 4: Use early date filtering when date range specified
            if start_dt or end_dt:
                project_sessions = project.list_sessions_filtered(
                    start_date=start_dt, end_date=end_dt
                )
            else:
                project_sessions = project.list_sessions()

            if project_sessions:
                projects_active += 1
                all_sessions.extend(project_sessions)
        except Exception:
            continue

    analytics = _calculate_analytics_from_sessions(
        all_sessions, tz_offset or 0, use_index=use_index
    )
    analytics.projects_active = projects_active
    return analytics


@router.get("/projects/{encoded_name}")
@cacheable(max_age=120, stale_while_revalidate=300, private=True)
def get_project_analytics(
    encoded_name: str,
    request: Request,
    start_ts: Optional[int] = Query(None, description="Start timestamp (Unix milliseconds)"),
    end_ts: Optional[int] = Query(None, description="End timestamp (Unix milliseconds)"),
    tz_offset: Optional[int] = Query(
        0,
        description="Timezone offset in minutes from UTC (e.g., 480 for PST). "
        "Matches JavaScript's getTimezoneOffset() convention.",
    ),
    use_index: bool = Query(
        True,
        description="Use sessions-index.json for fast lightweight analytics. "
        "Set to false for full token/tool metrics.",
    ),
):
    """
    Get comprehensive analytics for a project, optionally filtered by time range.

    Phase 3: Moderate cache (2min) - aggregated computed data.
    Phase 4: Uses early date filtering when date range specified.
    Phase 6: Simplified timestamp-based filtering (no timezone math needed).
    Phase 7: Timezone-aware date grouping for sessions_by_date and temporal_heatmap.
    Phase 8: Session index optimization - avoids JSONL parsing when use_index=true.
    """
    from routers.projects import resolve_project_identifier

    encoded_name = resolve_project_identifier(encoded_name)
    try:
        project = Project.from_encoded_name(encoded_name)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Project not found: {e}") from e

    if not project.exists:
        raise HTTPException(status_code=404, detail="Project directory not found")

    # Parse timestamp parameters to UTC datetimes
    start_dt, end_dt = parse_timestamp_range(start_ts, end_ts)

    # SQLite fast path
    sqlite_result = _get_analytics_sqlite(encoded_name, start_dt, end_dt, tz_offset or 0)
    if sqlite_result is not None:
        return sqlite_result

    # Try index-based fast path first if requested
    if use_index:
        try:
            index_entries = project.list_session_index_entries()

            # Apply date filtering to index entries
            if start_dt or end_dt:
                filtered_entries = []
                for entry in index_entries:
                    if start_dt and entry.start_time and entry.start_time < start_dt:
                        continue
                    if end_dt and entry.start_time and entry.start_time > end_dt:
                        continue
                    filtered_entries.append(entry)
                index_entries = filtered_entries

            if index_entries:
                return _calculate_analytics_from_sessions(
                    index_entries, tz_offset or 0, use_index=True
                )
        except Exception:
            # Fall through to full session loading on any index error
            pass

    # Fallback: Full session loading with JSONL parsing
    try:
        if start_dt or end_dt:
            # Early filtering: skips loading sessions whose mtime is out of range
            sessions = project.list_sessions_filtered(start_date=start_dt, end_date=end_dt)
        else:
            sessions = project.list_sessions()
    except Exception as e:
        import traceback

        tb = traceback.format_exc()
        raise HTTPException(
            status_code=500, detail=f"CRASH in list_sessions: {str(e)} TB: {tb[:200]}"
        ) from e

    return _calculate_analytics_from_sessions(sessions, tz_offset or 0, use_index=False)


def _categorize_model(model_name: str) -> str:
    """Categorize model into simplified name."""
    model_lower = model_name.lower()
    if "opus" in model_lower:
        return "Opus"
    elif "sonnet" in model_lower:
        return "Sonnet"
    elif "haiku" in model_lower:
        return "Haiku"
    else:
        return "Other"


def _calculate_time_distribution(temporal_heatmap: list) -> dict:
    """Calculate simplified time-of-day distribution percentages."""
    # Sum across all 7 days for each time period
    morning = sum(temporal_heatmap[d][h] for d in range(7) for h in range(6, 12))  # 6am-12pm
    afternoon = sum(temporal_heatmap[d][h] for d in range(7) for h in range(12, 18))  # 12pm-6pm
    evening = sum(temporal_heatmap[d][h] for d in range(7) for h in range(18, 24))  # 6pm-12am
    night = sum(temporal_heatmap[d][h] for d in range(7) for h in range(0, 6))  # 12am-6am

    total = morning + afternoon + evening + night

    if total == 0:
        return {
            "morning_pct": 0.0,
            "afternoon_pct": 0.0,
            "evening_pct": 0.0,
            "night_pct": 0.0,
            "dominant_period": "Unknown",
        }

    morning_pct = (morning / total) * 100
    afternoon_pct = (afternoon / total) * 100
    evening_pct = (evening / total) * 100
    night_pct = (night / total) * 100

    periods = [
        (morning_pct, "Morning"),
        (afternoon_pct, "Afternoon"),
        (evening_pct, "Evening"),
        (night_pct, "Night"),
    ]
    dominant_period = max(periods, key=lambda x: x[0])[1]

    return {
        "morning_pct": round(morning_pct, 1),
        "afternoon_pct": round(afternoon_pct, 1),
        "evening_pct": round(evening_pct, 1),
        "night_pct": round(night_pct, 1),
        "dominant_period": dominant_period,
    }


# Tool categorization for work mode distribution
EXPLORATION_TOOLS = {
    "Read",
    "Grep",
    "Glob",
    "LS",
    "WebFetch",
    "WebSearch",
    "ListMcpResourcesTool",
    "ReadMcpResourceTool",
}
BUILDING_TOOLS = {"Write", "Edit", "NotebookEdit", "MultiEdit"}
TESTING_TOOLS = {"Bash", "Task", "KillShell"}


def _calculate_work_mode_distribution(tools_used: dict) -> WorkModeDistribution:
    """Calculate work mode distribution from tool usage counts."""
    exploration_count = sum(tools_used.get(tool, 0) for tool in EXPLORATION_TOOLS)
    building_count = sum(tools_used.get(tool, 0) for tool in BUILDING_TOOLS)
    testing_count = sum(tools_used.get(tool, 0) for tool in TESTING_TOOLS)

    total = exploration_count + building_count + testing_count

    if total == 0:
        return WorkModeDistribution(
            exploration_pct=0.0,
            building_pct=0.0,
            testing_pct=0.0,
            primary_mode="Unknown",
        )

    exploration_pct = round((exploration_count / total) * 100, 1)
    building_pct = round((building_count / total) * 100, 1)
    testing_pct = round((testing_count / total) * 100, 1)

    modes = [
        (exploration_pct, "Exploration"),
        (building_pct, "Building"),
        (testing_pct, "Testing"),
    ]
    primary_mode = max(modes, key=lambda x: x[0])[1]

    return WorkModeDistribution(
        exploration_pct=exploration_pct,
        building_pct=building_pct,
        testing_pct=testing_pct,
        primary_mode=primary_mode,
    )


def _calculate_analytics_from_index(
    index_entries: list, tz_offset_minutes: int = 0
) -> ProjectAnalytics:
    """
    Calculate lightweight analytics from SessionIndexEntry objects.

    This is a FAST PATH that avoids parsing JSONL files entirely. It provides
    basic metrics (session counts, durations, temporal patterns) but cannot
    provide token/model/tool data since SessionIndexEntry doesn't contain them.

    When use_index=True is passed to the analytics endpoint, this function is
    used for FAST responses (typically <50ms vs 1.3-4.8s for full JSONL parsing).

    Use this for:
    - Session counts
    - Duration aggregation
    - Temporal patterns (sessions by date, heatmap)
    - Quick project overviews

    NOT available from index (returns zeros/empty):
    - Token usage (input/output/cache)
    - Model usage
    - Tool usage
    - Cost estimates

    Args:
        index_entries: List of SessionIndexEntry objects
        tz_offset_minutes: Timezone offset in minutes from UTC

    Returns:
        ProjectAnalytics with basic metrics (token/tool/model fields are zero/empty)
    """
    total_duration = 0.0
    sessions_by_date: Counter[str] = Counter()
    temporal_heatmap = [[0 for _ in range(24)] for _ in range(7)]

    # Create timezone object for local time conversion
    local_tz = timezone(timedelta(minutes=-tz_offset_minutes))

    for entry in index_entries:
        # Aggregate duration
        if entry.duration_seconds:
            total_duration += entry.duration_seconds

        # Track sessions by date and temporal pattern (in user's local time)
        if entry.start_time:
            # Convert UTC to local time for date grouping
            local_time = entry.start_time.astimezone(local_tz)
            date_str = local_time.strftime("%Y-%m-%d")
            sessions_by_date[date_str] += 1

            # Temporal heatmap - use local time for accurate time-of-day analysis
            day_of_week = local_time.weekday()  # 0=Monday
            hour = local_time.hour
            temporal_heatmap[day_of_week][hour] += 1

    # Calculate peak hours (top 3)
    hour_totals = [(sum(temporal_heatmap[d][h] for d in range(7)), h) for h in range(24)]
    hour_totals.sort(reverse=True)
    peak_hours = [h for _, h in hour_totals[:3] if hour_totals[0][0] > 0]

    total_sessions = len(index_entries)

    # Calculate time distribution (simplified view)
    time_distribution = _calculate_time_distribution(temporal_heatmap)

    # Work mode distribution unavailable without tool data
    work_mode_distribution = WorkModeDistribution(
        exploration_pct=0.0,
        building_pct=0.0,
        testing_pct=0.0,
        primary_mode="Unknown",
    )

    return ProjectAnalytics(
        total_sessions=total_sessions,
        total_tokens=0,  # Not available in index
        total_input_tokens=0,
        total_output_tokens=0,
        total_duration_seconds=total_duration,
        estimated_cost_usd=0.0,  # Cannot calculate without token data
        models_used={},  # Not available in index
        cache_hit_rate=0.0,  # Not available in index
        tools_used={},  # Not available in index
        sessions_by_date=dict(sessions_by_date),
        temporal_heatmap=temporal_heatmap,
        peak_hours=peak_hours,
        models_categorized={},  # Not available in index
        time_distribution=time_distribution,
        work_mode_distribution=work_mode_distribution,
    )


def _calculate_analytics_from_sessions(
    sessions: list, tz_offset_minutes: int = 0, use_index: bool = True
) -> ProjectAnalytics:
    """
    Calculate analytics from a list of sessions.

    Args:
        sessions: List of Session objects
        tz_offset_minutes: Timezone offset in minutes from UTC (e.g., -480 for PST/UTC-8).
                          Positive values are west of UTC, negative are east.
                          This matches JavaScript's getTimezoneOffset() convention.
        use_index: If True, attempt to use SessionIndexEntry data for lightweight metrics
                   (session count, durations, temporal patterns) without parsing JSONL.
                   Falls back to full parsing for token/tool counts.
    """
    # Try fast path using SessionIndexEntry if available
    # Check if all sessions are actually SessionIndexEntry objects
    from models.session_index import SessionIndexEntry

    if use_index and sessions and all(isinstance(s, SessionIndexEntry) for s in sessions):
        return _calculate_analytics_from_index(sessions, tz_offset_minutes)

    total_input_tokens = 0
    total_output_tokens = 0
    total_cache_read = 0
    total_cacheable = 0
    total_duration = 0.0
    total_cost = 0.0
    models_used: Counter[str] = Counter()
    models_categorized: Counter[str] = Counter()
    tools_used: Counter[str] = Counter()
    sessions_by_date: Counter[str] = Counter()

    # Temporal heatmap: 7 days (Mon=0) x 24 hours
    # Uses local time when tz_offset is provided
    temporal_heatmap = [[0 for _ in range(24)] for _ in range(7)]

    # Create timezone object for local time conversion
    # Note: JS getTimezoneOffset() returns positive for west of UTC, but Python's
    # timedelta uses the opposite convention, so we negate the offset
    local_tz = timezone(timedelta(minutes=-tz_offset_minutes))

    for session in sessions:
        usage = session.get_usage_summary()
        total_input_tokens += usage.total_input
        total_output_tokens += usage.output_tokens
        total_cache_read += usage.cache_read_input_tokens
        total_cacheable += (
            usage.input_tokens + usage.cache_creation_input_tokens + usage.cache_read_input_tokens
        )

        if session.duration_seconds:
            total_duration += session.duration_seconds

        # Track models used
        session_models = session.get_models_used()
        model_count = len(session_models)

        for model in session_models:
            models_used[model] += 1
            models_categorized[_categorize_model(model)] += 1
            # Calculate cost per model (split tokens evenly across models)
            split_usage = TokenUsage(
                input_tokens=usage.input_tokens // max(1, model_count),
                output_tokens=usage.output_tokens // max(1, model_count),
                cache_creation_input_tokens=usage.cache_creation_input_tokens
                // max(1, model_count),
                cache_read_input_tokens=usage.cache_read_input_tokens // max(1, model_count),
            )
            total_cost += split_usage.calculate_cost(model)

        # Track tools used
        session_tools = session.get_tools_used()
        for tool, count in session_tools.items():
            tools_used[tool] += count

        # Track sessions by date and temporal pattern (in user's local time)
        if session.start_time:
            # Convert UTC to local time for date grouping
            local_time = session.start_time.astimezone(local_tz)
            date_str = local_time.strftime("%Y-%m-%d")
            sessions_by_date[date_str] += 1

            # Temporal heatmap - use local time for accurate time-of-day analysis
            day_of_week = local_time.weekday()  # 0=Monday
            hour = local_time.hour
            temporal_heatmap[day_of_week][hour] += 1

        # Also count subagent tool usage
        for subagent in session.list_subagents():
            for msg in subagent.iter_messages():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content_blocks:
                        if isinstance(block, ToolUseBlock):
                            tools_used[block.name] += 1

    # Calculate cache hit rate
    cache_hit_rate = total_cache_read / total_cacheable if total_cacheable > 0 else 0.0

    # Calculate peak hours (top 3)
    hour_totals = [(sum(temporal_heatmap[d][h] for d in range(7)), h) for h in range(24)]
    hour_totals.sort(reverse=True)
    peak_hours = [h for _, h in hour_totals[:3] if hour_totals[0][0] > 0]

    total_sessions = len(sessions)

    # Calculate time distribution (simplified view)
    time_distribution = _calculate_time_distribution(temporal_heatmap)

    # Calculate work mode distribution from tool usage
    work_mode_distribution = _calculate_work_mode_distribution(dict(tools_used))

    return ProjectAnalytics(
        total_sessions=total_sessions,
        total_tokens=total_input_tokens + total_output_tokens,
        total_input_tokens=total_input_tokens,
        total_output_tokens=total_output_tokens,
        total_duration_seconds=total_duration,
        estimated_cost_usd=round(total_cost, 4),
        models_used=dict(models_used),
        cache_hit_rate=round(cache_hit_rate, 4),
        tools_used=dict(tools_used),
        sessions_by_date=dict(sessions_by_date),
        temporal_heatmap=temporal_heatmap,
        peak_hours=peak_hours,
        models_categorized=dict(models_categorized),
        time_distribution=time_distribution,
        work_mode_distribution=work_mode_distribution,
    )


def _get_stats_for_period(start_dt: datetime, end_dt: datetime) -> tuple:
    """Helper to calculate stats for a date range."""
    sessions_count = 0
    projects_active = 0
    duration_seconds = 0.0

    for project in list_all_projects():
        if not project.exists:
            continue

        try:
            period_sessions = project.list_sessions_filtered(start_date=start_dt, end_date=end_dt)

            if period_sessions:
                projects_active += 1
                sessions_count += len(period_sessions)

                for session in period_sessions:
                    if session.duration_seconds:
                        duration_seconds += session.duration_seconds
        except Exception:
            continue

    return sessions_count, projects_active, duration_seconds


def _get_dashboard_stats_sqlite() -> DashboardStats | None:
    """SQLite fast path for dashboard stats."""
    try:
        from db.connection import sqlite_read
        from db.queries import query_dashboard_stats

        with sqlite_read() as conn:
            if conn is None:
                return None

            now_utc = datetime.now(timezone.utc)
            today = now_utc.date()
            yesterday = today - timedelta(days=1)
            days_since_monday = today.weekday()
            week_start = today - timedelta(days=days_since_monday)

            today_start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
            today_end = datetime.combine(today, datetime.max.time(), tzinfo=timezone.utc)
            yesterday_start = datetime.combine(yesterday, datetime.min.time(), tzinfo=timezone.utc)
            yesterday_end = datetime.combine(yesterday, datetime.max.time(), tzinfo=timezone.utc)
            week_start_dt = datetime.combine(week_start, datetime.min.time(), tzinfo=timezone.utc)
            week_end_dt = datetime.combine(today, datetime.max.time(), tzinfo=timezone.utc)

            # Priority cascade: today → yesterday → this week
            for period, start, end, start_str, end_str in [
                ("today", today_start, today_end, today.isoformat(), today.isoformat()),
                (
                    "yesterday",
                    yesterday_start,
                    yesterday_end,
                    yesterday.isoformat(),
                    yesterday.isoformat(),
                ),
                (
                    "this_week",
                    week_start_dt,
                    week_end_dt,
                    week_start.isoformat(),
                    today.isoformat(),
                ),
            ]:
                result = query_dashboard_stats(conn, start, end)
                if result and result["session_count"] > 0:
                    return DashboardStats(
                        period=period,
                        start_date=start_str,
                        end_date=end_str,
                        sessions_count=result["session_count"],
                        projects_active=result["projects_active"],
                        duration_seconds=round(result["total_duration"], 1),
                    )
            return None
    except sqlite3.Error as e:
        logger.warning("SQLite dashboard query failed, falling back: %s", e)
        return None


@router.get("/dashboard")
@cacheable(max_age=60, stale_while_revalidate=120, private=True)
def get_dashboard_stats(request: Request):
    """
    Lightweight endpoint for homepage terminal display.

    Priority cascade:
    1. Today's sessions (if any)
    2. Yesterday's sessions (if no today)
    3. This week's sessions (if no yesterday)
    4. Empty stats with period="none" (if no activity this week)

    Cache: 60s - frequent refresh expected for live feel.
    """
    # SQLite fast path
    sqlite_result = _get_dashboard_stats_sqlite()
    if sqlite_result is not None:
        return sqlite_result

    now_utc = datetime.now(timezone.utc)
    today = now_utc.date()
    yesterday = today - timedelta(days=1)

    # Calculate start of week (Monday)
    days_since_monday = today.weekday()
    week_start = today - timedelta(days=days_since_monday)

    # Make timezone-aware to match session timestamps
    today_start = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)
    today_end = datetime.combine(today, datetime.max.time(), tzinfo=timezone.utc)

    yesterday_start = datetime.combine(yesterday, datetime.min.time(), tzinfo=timezone.utc)
    yesterday_end = datetime.combine(yesterday, datetime.max.time(), tzinfo=timezone.utc)

    week_start_dt = datetime.combine(week_start, datetime.min.time(), tzinfo=timezone.utc)
    week_end_dt = datetime.combine(today, datetime.max.time(), tzinfo=timezone.utc)

    # Priority 1: Today
    sessions_count, projects_active, duration_seconds = _get_stats_for_period(
        today_start, today_end
    )

    if sessions_count > 0:
        return DashboardStats(
            period="today",
            start_date=today.isoformat(),
            end_date=today.isoformat(),
            sessions_count=sessions_count,
            projects_active=projects_active,
            duration_seconds=round(duration_seconds, 1),
        )

    # Priority 2: Yesterday
    sessions_count, projects_active, duration_seconds = _get_stats_for_period(
        yesterday_start, yesterday_end
    )

    if sessions_count > 0:
        return DashboardStats(
            period="yesterday",
            start_date=yesterday.isoformat(),
            end_date=yesterday.isoformat(),
            sessions_count=sessions_count,
            projects_active=projects_active,
            duration_seconds=round(duration_seconds, 1),
        )

    # Priority 3: This week
    sessions_count, projects_active, duration_seconds = _get_stats_for_period(
        week_start_dt, week_end_dt
    )

    if sessions_count > 0:
        return DashboardStats(
            period="this_week",
            start_date=week_start.isoformat(),
            end_date=today.isoformat(),
            sessions_count=sessions_count,
            projects_active=projects_active,
            duration_seconds=round(duration_seconds, 1),
        )

    # No activity - return empty stats
    return DashboardStats(
        period="none",
        start_date=today.isoformat(),
        end_date=today.isoformat(),
        sessions_count=0,
        projects_active=0,
        duration_seconds=0.0,
    )


@router.get("/debug/verify")
def verify_analytics(
    start_ts: Optional[int] = Query(None, description="Start timestamp (Unix milliseconds)"),
    end_ts: Optional[int] = Query(None, description="End timestamp (Unix milliseconds)"),
):
    """
    Debug endpoint to verify timestamp filtering accuracy.

    Returns raw session timestamps for manual verification.

    Example:
        GET /analytics/debug/verify?start_ts=1736899200000&end_ts=1736985600000
    """
    start_dt, end_dt = parse_timestamp_range(start_ts, end_ts)

    # Get all projects with valid directories
    projects = [p for p in list_all_projects() if p.exists]

    # Collect raw session data for verification
    sessions_debug = []
    for project in projects:
        try:
            if start_dt or end_dt:
                sessions = project.list_sessions_filtered(start_date=start_dt, end_date=end_dt)
            else:
                sessions = project.list_sessions()

            for session in sessions:
                if session.start_time:
                    sessions_debug.append(
                        {
                            "uuid": session.uuid[:8],
                            "project": project.path.split("/")[-1],
                            "start_time_utc": session.start_time.isoformat(),
                            "start_time_ts": int(session.start_time.timestamp() * 1000),
                            "duration_seconds": session.duration_seconds,
                        }
                    )
        except Exception:
            continue

    # Sort by start time descending
    sessions_debug.sort(key=lambda s: s["start_time_utc"], reverse=True)

    return {
        "query": {
            "start_ts": start_ts,
            "end_ts": end_ts,
            "start_dt_utc": start_dt.isoformat() if start_dt else None,
            "end_dt_utc": end_dt.isoformat() if end_dt else None,
        },
        "sessions_found": len(sessions_debug),
        "sessions": sessions_debug[:20],  # Limit for readability
    }
