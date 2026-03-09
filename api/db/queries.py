"""
SQLite query functions for session listing and filtering.

These functions provide SQLite-backed alternatives to the JSONL-based
loading in routers/sessions.py. They return the same schema types
so the router can swap implementations transparently.
"""

import json
import logging
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from services.session_filter import ACTIVE_THRESHOLD_SECONDS

logger = logging.getLogger(__name__)


def _local_tz_modifier() -> str:
    """Return SQLite time modifier for the machine's local timezone.

    E.g. '-480 minutes' for UTC-8 (PST), '+330 minutes' for UTC+5:30 (IST).
    Used in DATE()/TIME() functions to group by local calendar date.
    Correctly handles DST transitions via datetime.astimezone().
    """
    from utils import local_timezone

    offset = local_timezone().utcoffset(None)
    offset_min = int(offset.total_seconds() // 60)
    return f"{offset_min:+d} minutes"


def _tz_date(col: str = "s.start_time") -> str:
    """Return SQL expression for DATE in local timezone.

    >>> _tz_date()  # on a UTC-7 machine
    "DATE(s.start_time, '-420 minutes')"
    """
    return f"DATE({col}, '{_local_tz_modifier()}')"


# Allowlist for SQL fragments interpolated into _query_per_item_trend.
# Prevents future callers from accidentally passing user input.
_ALLOWED_ITEM_COLS = frozenset({"sc.command_name", "sk.skill_name", "st.tool_name", "si.subagent_type"})


def _query_per_item_trend(
    conn: sqlite3.Connection,
    item_col: str,
    from_clause: str,
    where: str,
    params: dict,
    count_expr: str = "COUNT(*)",
) -> dict[str, list[dict]]:
    """Query per-item daily trend. Returns {item_name: [{date, count}, ...]}.

    SECURITY: item_col, from_clause, where, and count_expr are interpolated
    directly into the SQL string. They MUST be hardcoded SQL fragments,
    never user input. All user-supplied values must go through ``params``.
    """
    if item_col not in _ALLOWED_ITEM_COLS:
        raise ValueError(f"Disallowed item_col: {item_col!r}")
    rows = conn.execute(
        f"""SELECT {item_col} as item, {_tz_date()} as date, {count_expr} as count
        {from_clause}
        {where}
        {"AND" if where else "WHERE"} s.start_time IS NOT NULL
        GROUP BY {item_col}, {_tz_date()}
        ORDER BY item, date""",
        params,
    ).fetchall()
    result: dict[str, list[dict]] = {}
    for row in rows:
        result.setdefault(row["item"], []).append({"date": row["date"], "count": row["count"]})
    return result


def _resolve_user_names(conn: sqlite3.Connection, user_ids: list[str]) -> dict[str, str]:
    """Resolve user_ids to display names from sync_members table."""
    if not user_ids:
        return {}
    placeholders = ",".join("?" * len(user_ids))
    rows = conn.execute(
        f"SELECT DISTINCT device_id, name FROM sync_members WHERE device_id IN ({placeholders})",
        user_ids,
    ).fetchall()
    return {row["device_id"]: row["name"] for row in rows}


def _query_per_user_trend(
    conn: sqlite3.Connection,
    from_clause: str,
    where: str,
    params: dict,
    count_expr: str = "COUNT(*)",
) -> dict[str, list[dict]]:
    """Per-user daily trend. Returns {user_id: [{date, count}, ...]}."""
    and_or_where = "AND" if where else "WHERE"
    rows = conn.execute(
        f"""SELECT COALESCE(s.remote_user_id, '_local') as user_id,
            {_tz_date()} as date, {count_expr} as count
        {from_clause}
        {where}
        {and_or_where} s.start_time IS NOT NULL
        GROUP BY user_id, {_tz_date()}
        ORDER BY user_id, date""",
        params,
    ).fetchall()
    result: dict[str, list[dict]] = {}
    for row in rows:
        result.setdefault(row["user_id"], []).append(
            {"date": row["date"], "count": row["count"]}
        )
    return result


def query_all_sessions(
    conn: sqlite3.Connection,
    search: Optional[str] = None,
    project: Optional[str] = None,
    branch: Optional[str] = None,
    scope: str = "both",
    status: str = "all",
    source: str = "all",
    start_dt: Optional[datetime] = None,
    end_dt: Optional[datetime] = None,
    limit: int = 200,
    offset: int = 0,
) -> dict:
    """
    Query sessions from SQLite with filtering, sorting, and pagination.

    Returns a dict with keys matching what the router needs:
    - sessions: list of row dicts (paginated, sorted by start_time DESC)
    - total: total matching count (before pagination)
    - status_counts: {"active": N, "completed": N, "error": N}
    - project_options: list of {"encoded_name", "path", "name", "session_count"}
    """
    # Build WHERE clauses
    conditions = []
    params = {}

    if project:
        conditions.append("s.project_encoded_name = :project")
        params["project"] = project

    if branch:
        conditions.append("s.git_branch = :branch")
        params["branch"] = branch

    if start_dt:
        conditions.append("s.start_time >= :start_dt")
        params["start_dt"] = start_dt.isoformat()

    if end_dt:
        conditions.append("s.end_time <= :end_dt")
        params["end_dt"] = end_dt.isoformat()

    if source and source != "all":
        conditions.append("s.source = :source")
        params["source"] = source

    # Search via FTS5
    fts_join = ""
    if search:
        # Sanitize FTS5 tokens: strip special characters that cause OperationalError
        raw_tokens = [t.strip() for t in search.split(",") if t.strip()][:7]
        tokens = [_sanitize_fts_token(t) for t in raw_tokens]
        tokens = [t for t in tokens if t]  # Remove empty after sanitization
        if tokens:
            if scope == "titles":
                fts_terms = " AND ".join(f"session_titles:{t}" for t in tokens)
            elif scope == "prompts":
                fts_terms = " AND ".join(
                    f"(slug:{t} OR initial_prompt:{t} OR project_path:{t})" for t in tokens
                )
            else:
                fts_terms = " AND ".join(t for t in tokens)

            fts_join = "JOIN sessions_fts ON sessions_fts.rowid = s.rowid"
            conditions.append("sessions_fts MATCH :fts_query")
            params["fts_query"] = fts_terms

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    # Snapshot base conditions before adding status filter
    base_conditions = list(conditions)
    base_where = "WHERE " + " AND ".join(base_conditions) if base_conditions else ""

    # Status filtering — compute in SQL using end_time recency
    now_iso = datetime.now(timezone.utc).isoformat()
    threshold_days = ACTIVE_THRESHOLD_SECONDS / 86400.0

    # Step 1: Get status counts (across all matching sessions, no status filter)
    count_sql = f"""
        SELECT
            SUM(CASE WHEN julianday(:now) - julianday(s.end_time) < :threshold_days THEN 1 ELSE 0 END) as active_count,
            SUM(CASE WHEN s.end_time IS NULL OR julianday(:now) - julianday(s.end_time) >= :threshold_days THEN 1 ELSE 0 END) as completed_count
        FROM sessions s
        {fts_join}
        {base_where}
    """
    params["now"] = now_iso
    params["threshold_days"] = threshold_days
    try:
        count_row = conn.execute(count_sql, params).fetchone()
    except sqlite3.OperationalError as e:
        logger.warning("FTS5 query error (status counts): %s", e)
        return {
            "sessions": [],
            "total": 0,
            "status_counts": {"active": 0, "completed": 0, "error": 0},
            "project_options": _query_project_options(conn),
        }
    status_counts = {
        "active": count_row["active_count"] or 0,
        "completed": count_row["completed_count"] or 0,
        "error": 0,  # Error detection requires JSONL parsing (future enhancement)
    }

    # Step 2: Add status filter to a separate filtered list
    filtered_conditions = list(base_conditions)
    if status == "active":
        filtered_conditions.append("julianday(:now) - julianday(s.end_time) < :threshold_days")
    elif status == "completed":
        filtered_conditions.append(
            "(s.end_time IS NULL OR julianday(:now) - julianday(s.end_time) >= :threshold_days)"
        )

    where = "WHERE " + " AND ".join(filtered_conditions) if filtered_conditions else ""

    # Step 3: Get total count (with status filter applied)
    total_sql = f"SELECT COUNT(*) FROM sessions s {fts_join} {where}"
    try:
        total = conn.execute(total_sql, params).fetchone()[0]
    except sqlite3.OperationalError as e:
        logger.warning("FTS5 query error (total count): %s", e)
        return {
            "sessions": [],
            "total": 0,
            "status_counts": status_counts,
            "project_options": _query_project_options(conn),
        }

    # Step 4: Get paginated results
    query_sql = f"""
        SELECT
            s.uuid, s.slug, s.project_encoded_name, s.project_path,
            s.message_count, s.start_time, s.end_time, s.duration_seconds,
            s.input_tokens, s.output_tokens, s.total_cost,
            s.initial_prompt, s.git_branch, s.models_used,
            s.session_titles, s.is_continuation_marker, s.was_compacted,
            s.subagent_count, s.session_source,
            s.source, s.remote_user_id, s.remote_machine_id
        FROM sessions s
        {fts_join}
        {where}
        ORDER BY s.start_time DESC
        LIMIT :limit OFFSET :offset
    """
    params["limit"] = limit
    params["offset"] = offset

    try:
        rows = conn.execute(query_sql, params).fetchall()
    except sqlite3.OperationalError as e:
        logger.warning("FTS5 query error (paginated results): %s", e)
        return {
            "sessions": [],
            "total": 0,
            "status_counts": status_counts,
            "project_options": _query_project_options(conn),
        }

    # Convert rows to dicts with parsed JSON fields
    sessions = []
    for row in rows:
        session = dict(row)
        # Parse JSON fields
        session["models_used"] = _parse_json_list(session.get("models_used"))
        session["session_titles"] = _parse_json_list(session.get("session_titles"))
        session["git_branches"] = [session["git_branch"]] if session.get("git_branch") else []
        sessions.append(session)

    # Step 5: Get project options (from precomputed projects table)
    project_options = _query_project_options(conn)

    return {
        "sessions": sessions,
        "total": total,
        "status_counts": status_counts,
        "project_options": project_options,
    }


def _sanitize_fts_token(token: str) -> str:
    """
    Sanitize a search token for FTS5 MATCH queries.

    Strips special characters that cause sqlite3.OperationalError:
    parentheses, asterisks, unbalanced quotes, and standalone colons.
    """
    # Strip FTS5 special characters (quotes, parens, asterisks)
    sanitized = re.sub(r'[()"\*]', "", token)
    # Remove standalone colons (but keep column-prefixed like "title:foo")
    if ":" in sanitized and not re.match(r"^[a-zA-Z_]+:", sanitized):
        sanitized = sanitized.replace(":", "")
    sanitized = sanitized.strip()
    if not sanitized:
        return sanitized
    # Wrap in double quotes and append * for prefix matching
    # e.g. "ecomode" -> '"ecomode"*'
    # This prevents FTS5 interpreting hyphens as operators and enables "search as you type"
    return f'"{sanitized}"*'


def _query_project_options(conn: sqlite3.Connection) -> list[dict]:
    """Get project filter options from the projects summary table."""
    rows = conn.execute(
        """
        SELECT encoded_name, project_path, slug, display_name, session_count
        FROM projects
        ORDER BY session_count DESC
        """
    ).fetchall()

    options = []
    for row in rows:
        path = row["project_path"] or ""
        options.append(
            {
                "encoded_name": row["encoded_name"],
                "path": path,
                "name": Path(path).name if path else row["encoded_name"],
                "slug": row["slug"],
                "display_name": row["display_name"],
                "session_count": row["session_count"],
            }
        )
    return options


def query_all_projects(conn: sqlite3.Connection) -> list[dict]:
    """
    Get all projects from the precomputed projects table.

    Returns list of dicts with keys matching ProjectSummary needs:
    encoded_name, project_path, slug, display_name, session_count, last_activity.
    """
    rows = conn.execute(
        """SELECT encoded_name, project_path, slug, display_name,
                  session_count, last_activity
           FROM projects
           ORDER BY last_activity DESC NULLS LAST"""
    ).fetchall()
    return [dict(row) for row in rows]


def query_project_by_slug(conn: sqlite3.Connection, slug: str) -> dict | None:
    """
    Look up a project by its slug.

    Returns the project row as a dict, or None if not found.
    """
    row = conn.execute(
        """SELECT encoded_name, project_path, slug, display_name, session_count, last_activity
           FROM projects
           WHERE slug = ?
           LIMIT 1""",
        (slug,),
    ).fetchone()
    return dict(row) if row else None


def query_session_by_slug(conn: sqlite3.Connection, slug: str) -> dict | None:
    """
    Single slug lookup using idx_sessions_slug index.

    Returns the most recent session row matching the slug, or None.
    """
    row = conn.execute(
        """SELECT uuid, slug, project_encoded_name, project_path, git_branch
           FROM sessions
           WHERE slug = ?
           ORDER BY start_time DESC
           LIMIT 1""",
        (slug,),
    ).fetchone()
    return dict(row) if row else None


def query_sessions_by_slugs(conn: sqlite3.Connection, slugs: list[str]) -> dict[str, dict]:
    """
    Batch slug lookup. Returns {slug: session_row} picking the latest per slug.
    """
    if not slugs:
        return {}

    # Safe: placeholders are parameter markers, not user input
    placeholders = ",".join("?" * len(slugs))
    rows = conn.execute(
        f"""SELECT uuid, slug, project_encoded_name, project_path, git_branch
            FROM (
                SELECT *,
                       ROW_NUMBER() OVER (PARTITION BY slug ORDER BY start_time DESC) AS rn
                FROM sessions
                WHERE slug IN ({placeholders})
            )
            WHERE rn = 1""",
        slugs,
    ).fetchall()
    return {row["slug"]: dict(row) for row in rows}


def _parse_json_list(value: Optional[str]) -> list:
    """Parse a JSON array string, returning empty list on None or error."""
    if not value:
        return []
    try:
        result = json.loads(value)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


# ---------------------------------------------------------------------------
# Dashboard & Analytics queries
# ---------------------------------------------------------------------------


def query_dashboard_stats(
    conn: sqlite3.Connection,
    start_dt: datetime,
    end_dt: datetime,
) -> dict | None:
    """Dashboard stats for a date range. Returns None if no sessions found."""
    row = conn.execute(
        """SELECT
            COUNT(*) as session_count,
            COUNT(DISTINCT project_encoded_name) as projects_active,
            COALESCE(SUM(duration_seconds), 0) as total_duration
        FROM sessions
        WHERE start_time >= :start AND start_time <= :end""",
        {"start": start_dt.isoformat(), "end": end_dt.isoformat()},
    ).fetchone()
    if not row or row["session_count"] == 0:
        return None
    return dict(row)


def query_analytics(
    conn: sqlite3.Connection,
    project: Optional[str] = None,
    start_dt: Optional[datetime] = None,
    end_dt: Optional[datetime] = None,
) -> dict:
    """
    Aggregated analytics from SQLite. Returns dict with keys:
    - totals: {sessions, input_tokens, output_tokens, cache_read, cache_creation, cost, duration}
    - tools: {tool_name: count}
    - models_used_raw: list of JSON-encoded model arrays (parse in caller)
    - start_times: list of ISO start_time strings (for temporal heatmap)
    """
    conditions: list[str] = []
    params: dict = {}
    if project:
        conditions.append("s.project_encoded_name = :project")
        params["project"] = project
    if start_dt:
        conditions.append("s.start_time >= :start_dt")
        params["start_dt"] = start_dt.isoformat()
    if end_dt:
        conditions.append("s.start_time <= :end_dt")
        params["end_dt"] = end_dt.isoformat()
    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    # 1. Session totals
    totals_row = conn.execute(
        f"""SELECT
            COUNT(*) as total_sessions,
            COALESCE(SUM(input_tokens), 0) as total_input,
            COALESCE(SUM(output_tokens), 0) as total_output,
            COALESCE(SUM(cache_read_tokens), 0) as total_cache_read,
            COALESCE(SUM(cache_creation_tokens), 0) as total_cache_creation,
            COALESCE(SUM(total_cost), 0) as total_cost,
            COALESCE(SUM(duration_seconds), 0) as total_duration,
            COUNT(DISTINCT project_encoded_name) as projects_active
        FROM sessions s
        {where}""",
        params,
    ).fetchone()
    totals = dict(totals_row)

    # 2. Tool aggregates
    tool_rows = conn.execute(
        f"""SELECT st.tool_name, SUM(st.count) as total
        FROM session_tools st
        JOIN sessions s ON st.session_uuid = s.uuid
        {where}
        GROUP BY st.tool_name""",
        params,
    ).fetchall()
    tools = {row["tool_name"]: row["total"] for row in tool_rows}

    # 3. Models used (use json_each for efficient parsing)
    model_conditions = list(conditions) + ["models_used IS NOT NULL"]
    model_where = "WHERE " + " AND ".join(model_conditions)
    # Use SQLite's json_each() to parse JSON arrays directly in SQL
    model_rows = conn.execute(
        f"""SELECT DISTINCT je.value as model_name
        FROM sessions s, json_each(s.models_used) AS je
        {model_where}""",
        params,
    ).fetchall()
    # Return as list of model names (already parsed by SQLite)
    models_used_list = [row["model_name"] for row in model_rows]

    # 4. Start times for temporal heatmap
    time_conditions = list(conditions) + ["start_time IS NOT NULL"]
    time_where = "WHERE " + " AND ".join(time_conditions)
    time_rows = conn.execute(f"SELECT start_time FROM sessions s {time_where}", params).fetchall()
    start_times = [row["start_time"] for row in time_rows]

    # 4b. Start times with user_id for per-user breakdowns
    time_user_rows = conn.execute(
        f"""SELECT COALESCE(s.remote_user_id, '_local') as user_id, s.start_time
        FROM sessions s
        {time_where}""",
        params,
    ).fetchall()
    start_times_with_user = [
        {"user_id": row["user_id"], "start_time": row["start_time"]}
        for row in time_user_rows
    ]

    # 5. Resolve user display names from sync_members
    user_ids = list({e["user_id"] for e in start_times_with_user if e["user_id"] != "_local"})
    user_names = _resolve_user_names(conn, user_ids) if user_ids else {}

    return {
        "totals": totals,
        "tools": tools,
        "models_used_list": models_used_list,
        "start_times": start_times,
        "start_times_with_user": start_times_with_user,
        "user_names": user_names,
    }


# ---------------------------------------------------------------------------
# Skill queries
# ---------------------------------------------------------------------------


def _query_item_usage(
    conn: sqlite3.Connection,
    *,
    table: str,
    item_col: str,
    project: Optional[str],
    limit: int,
    track_mentions: bool = False,
) -> list[dict]:
    """Shared helper for skill/command aggregate usage queries.

    Args:
        conn: SQLite connection.
        table: Source table name (e.g. 'session_skills', 'session_commands').
        item_col: Column holding the item name (e.g. 'skill_name', 'command_name').
        project: Optional project encoded name filter.
        limit: Maximum rows to return.
        track_mentions: When True, adds a mentioned_count column using the
            text_detection invocation_source (skills only).
    """
    alias = "t"
    _where = f"WHERE s.project_encoded_name = :project" if project else ""
    _params: dict = {"limit": limit}
    if project:
        _params["project"] = project

    if track_mentions:
        count_expr = (
            f"SUM(CASE WHEN {alias}.invocation_source != 'text_detection' THEN {alias}.count ELSE 0 END) as total_count,\n"
            f"            SUM(CASE WHEN {alias}.invocation_source = 'text_detection' THEN {alias}.count ELSE 0 END) as mentioned_count,"
        )
    else:
        count_expr = f"SUM({alias}.count) as total_count,"

    rows = conn.execute(
        f"""SELECT {alias}.{item_col},
            {count_expr}
            COUNT(DISTINCT {alias}.session_uuid) as session_count,
            MAX(s.end_time) as last_used,
            GROUP_CONCAT(DISTINCT {alias}.invocation_source) as invocation_sources,
            SUM(CASE WHEN s.source = 'remote' THEN {alias}.count ELSE 0 END) as remote_count,
            SUM(CASE WHEN s.source != 'remote' THEN {alias}.count ELSE 0 END) as local_count,
            GROUP_CONCAT(DISTINCT CASE WHEN s.source = 'remote' THEN s.remote_user_id END) as remote_user_ids
        FROM {table} {alias}
        JOIN sessions s ON {alias}.session_uuid = s.uuid
        {_where}
        GROUP BY {alias}.{item_col}
        ORDER BY total_count DESC
        LIMIT :limit""",
        _params,
    ).fetchall()
    return [dict(row) for row in rows]


def query_skill_usage(
    conn: sqlite3.Connection,
    project: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Aggregate skill usage counts, optionally filtered by project.

    Includes invocation_sources field showing which sources contributed
    (e.g., 'slash_command,skill_tool').
    """
    return _query_item_usage(
        conn,
        table="session_skills",
        item_col="skill_name",
        project=project,
        limit=limit,
        track_mentions=True,
    )


def query_sessions_by_skill(
    conn: sqlite3.Connection,
    skill_name: str,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """Find sessions that used a specific skill. Returns {sessions, total}.

    Excludes sessions where the skill was only mentioned (text_detection)
    but never actually invoked.
    """
    # Total count (exclude mention-only sessions)
    total = conn.execute(
        """SELECT COUNT(DISTINCT session_uuid) FROM session_skills
        WHERE skill_name = :skill AND invocation_source != 'text_detection'""",
        {"skill": skill_name},
    ).fetchone()[0]

    # Paginated results (exclude mention-only sessions)
    rows = conn.execute(
        """SELECT
            s.uuid, s.slug, s.project_encoded_name, s.project_path,
            s.message_count, s.start_time, s.end_time, s.duration_seconds,
            s.models_used, s.subagent_count, s.initial_prompt,
            s.git_branch, s.session_titles,
            s.session_source, s.source, s.remote_user_id, s.remote_machine_id
        FROM sessions s
        JOIN session_skills sk ON s.uuid = sk.session_uuid
        WHERE sk.skill_name = :skill AND sk.invocation_source != 'text_detection'
        ORDER BY s.start_time DESC
        LIMIT :limit OFFSET :offset""",
        {"skill": skill_name, "limit": limit, "offset": offset},
    ).fetchall()

    sessions = []
    for row in rows:
        session = dict(row)
        session["models_used"] = _parse_json_list(session.get("models_used"))
        session["session_titles"] = _parse_json_list(session.get("session_titles"))
        session["git_branches"] = [session["git_branch"]] if session.get("git_branch") else []
        sessions.append(session)

    return {"sessions": sessions, "total": total}


def _query_item_detail(
    conn: sqlite3.Connection,
    *,
    table: str,
    sub_table: str,
    item_col: str,
    item_value: str,
    limit: int,
    offset: int,
    track_mentions: bool = False,
) -> dict | None:
    """Shared helper for skill/command detail queries.

    Args:
        conn: SQLite connection.
        table: Main session table (e.g. 'session_skills', 'session_commands').
        sub_table: Subagent table (e.g. 'subagent_skills', 'subagent_commands').
        item_col: Column holding the item name (e.g. 'skill_name', 'command_name').
        item_value: The specific item name to look up.
        limit: Page size for session list.
        offset: Page offset for session list.
        track_mentions: When True, applies text_detection exclusion logic in main
            stats and trend, and includes mentioned_calls / command_triggered_calls /
            mention_session_count fields in the result (skills only).
    """
    # Alias and parameter name differ by entity to stay readable in SQL.
    # Skills use :skill / sk alias; commands use :cmd / sc alias.
    # We normalise to a single alias 't' and a single param ':item' here.
    alias = "t"
    param_name = "item"
    item_param = {param_name: item_value}

    mention_exclusion = (
        f"AND {alias}.invocation_source != 'text_detection'" if track_mentions else ""
    )

    # Main session stats
    main_row = conn.execute(
        f"""SELECT COALESCE(SUM({alias}.count), 0) as total_count,
            COUNT(DISTINCT {alias}.session_uuid) as session_count,
            MIN(s.start_time) as first_used,
            MAX(s.start_time) as last_used,
            GROUP_CONCAT(DISTINCT {alias}.invocation_source) as invocation_sources
        FROM {table} {alias}
        JOIN sessions s ON {alias}.session_uuid = s.uuid
        WHERE {alias}.{item_col} = :{param_name} {mention_exclusion}""",
        item_param,
    ).fetchone()

    # Subagent stats
    sub_alias = "sa"
    sub_row = conn.execute(
        f"""SELECT COALESCE(SUM({sub_alias}.count), 0) as total_count
        FROM {sub_table} {sub_alias}
        JOIN subagent_invocations si ON {sub_alias}.invocation_id = si.id
        WHERE {sub_alias}.{item_col} = :{param_name}""",
        item_param,
    ).fetchone()

    main_calls = main_row["total_count"] or 0 if main_row else 0
    sub_calls = sub_row["total_count"] or 0 if sub_row else 0

    # Calls by invocation source — run BEFORE early-exit (skills: mention-only must not be hidden)
    source_rows = conn.execute(
        f"""SELECT {alias}.invocation_source, COALESCE(SUM({alias}.count), 0) as total
        FROM {table} {alias}
        WHERE {alias}.{item_col} = :{param_name}
        GROUP BY {alias}.invocation_source""",
        item_param,
    ).fetchall()
    source_counts = {r["invocation_source"]: r["total"] for r in source_rows}
    manual_calls = source_counts.get("slash_command", 0)
    auto_calls = source_counts.get("skill_tool", 0)

    if track_mentions:
        mentioned_calls = source_counts.get("text_detection", 0)
        command_triggered_calls = source_counts.get("command_triggered", 0)

        # Sessions where item was ONLY mentioned, never actually invoked
        mention_session_count = conn.execute(
            f"""SELECT COUNT(DISTINCT {alias}.session_uuid)
            FROM {table} {alias}
            WHERE {alias}.{item_col} = :{param_name} AND {alias}.invocation_source = 'text_detection'
                AND {alias}.session_uuid NOT IN (
                    SELECT session_uuid FROM {table}
                    WHERE {item_col} = :{param_name} AND invocation_source != 'text_detection'
                )""",
            item_param,
        ).fetchone()[0]

        if (
            main_calls == 0
            and sub_calls == 0
            and mentioned_calls == 0
            and command_triggered_calls == 0
        ):
            return None
    else:
        if main_calls == 0 and sub_calls == 0:
            return None

    # Daily trend
    trend_rows = conn.execute(
        f"""SELECT {_tz_date()} as date,
            SUM({alias}.count) as calls,
            COUNT(DISTINCT {alias}.session_uuid) as sessions
        FROM {table} {alias}
        JOIN sessions s ON {alias}.session_uuid = s.uuid
        WHERE {alias}.{item_col} = :{param_name} AND s.start_time IS NOT NULL
            {mention_exclusion}
        GROUP BY {_tz_date()}
        ORDER BY date""",
        item_param,
    ).fetchall()

    # Sessions with source tagging (main vs subagent)
    params: dict = {param_name: item_value, "limit": limit, "offset": offset}

    cte_sql = f"""
    WITH target_sessions AS (
        -- Main session usage
        SELECT {alias}.session_uuid, 1 as has_main, 0 as has_sub, NULL as agent_id
        FROM {table} {alias}
        JOIN sessions s ON {alias}.session_uuid = s.uuid
        WHERE {alias}.{item_col} = :{param_name}

        UNION ALL

        -- Subagent usage
        SELECT si.session_uuid, 0 as has_main, 1 as has_sub, si.agent_id
        FROM {sub_table} {sub_alias}
        JOIN subagent_invocations si ON {sub_alias}.invocation_id = si.id
        JOIN sessions s ON si.session_uuid = s.uuid
        WHERE {sub_alias}.{item_col} = :{param_name}
    ),
    aggregated_sessions AS (
        SELECT session_uuid,
               MAX(has_main) as has_main,
               MAX(has_sub) as has_sub,
               GROUP_CONCAT(DISTINCT agent_id) as agent_ids
        FROM target_sessions
        GROUP BY session_uuid
    ),
    session_sources AS (
        SELECT {alias}.session_uuid,
               GROUP_CONCAT(DISTINCT {alias}.invocation_source) as invocation_sources
        FROM {table} {alias}
        WHERE {alias}.{item_col} = :{param_name}
        GROUP BY {alias}.session_uuid
    )
    """

    total_sessions = conn.execute(
        f"{cte_sql} SELECT COUNT(*) FROM aggregated_sessions",
        params,
    ).fetchone()[0]

    rows = conn.execute(
        f"""{cte_sql}
        SELECT
            s.uuid, s.slug, s.project_encoded_name, s.project_path,
            s.message_count, s.start_time, s.end_time, s.duration_seconds,
            s.models_used, s.subagent_count, s.initial_prompt,
            s.git_branch, s.session_titles,
            s.session_source, s.source, s.remote_user_id, s.remote_machine_id,
            agg.has_main, agg.has_sub, agg.agent_ids,
            ss.invocation_sources
        FROM sessions s
        JOIN aggregated_sessions agg ON s.uuid = agg.session_uuid
        LEFT JOIN session_sources ss ON s.uuid = ss.session_uuid
        ORDER BY s.start_time DESC
        LIMIT :limit OFFSET :offset""",
        params,
    ).fetchall()

    sessions = []
    for row in rows:
        session = dict(row)

        has_main = session.pop("has_main")
        has_sub = session.pop("has_sub")
        if has_main and has_sub:
            session["tool_source"] = "both"
        elif has_sub:
            session["tool_source"] = "subagent"
        else:
            session["tool_source"] = "main"

        agent_ids_str = session.pop("agent_ids")
        session["subagent_agent_ids"] = agent_ids_str.split(",") if agent_ids_str else []

        sources_str = session.pop("invocation_sources", None)
        session["invocation_sources"] = sources_str.split(",") if sources_str else []

        session["models_used"] = _parse_json_list(session.get("models_used"))
        session["session_titles"] = _parse_json_list(session.get("session_titles"))
        session["git_branches"] = [session["git_branch"]] if session.get("git_branch") else []
        sessions.append(session)

    sources_str = main_row["invocation_sources"] if main_row else None
    invocation_sources = sources_str.split(",") if sources_str else []

    result: dict = {
        "main_calls": main_calls,
        "subagent_calls": sub_calls,
        "total_calls": main_calls + sub_calls,
        "manual_calls": manual_calls,
        "auto_calls": auto_calls,
        "session_count": main_row["session_count"] or 0 if main_row else 0,
        "first_used": main_row["first_used"] if main_row else None,
        "last_used": main_row["last_used"] if main_row else None,
        "invocation_sources": invocation_sources,
        "trend": [
            {"date": r["date"], "calls": r["calls"], "sessions": r["sessions"]} for r in trend_rows
        ],
        "sessions": sessions,
        "total": total_sessions,
    }

    if track_mentions:
        result["mentioned_calls"] = mentioned_calls
        result["command_triggered_calls"] = command_triggered_calls
        result["mention_session_count"] = mention_session_count

    return result


def query_skill_detail(
    conn: sqlite3.Connection,
    skill_name: str,
    limit: int = 100,
    offset: int = 0,
) -> dict | None:
    """Detailed stats for a single skill with trend and session list."""
    result = _query_item_detail(
        conn,
        table="session_skills",
        sub_table="subagent_skills",
        item_col="skill_name",
        item_value=skill_name,
        limit=limit,
        offset=offset,
        track_mentions=True,
    )
    if result is None:
        return None
    result["name"] = skill_name
    return result


# ---------------------------------------------------------------------------
# Command queries (mirrors skill query pattern)
# ---------------------------------------------------------------------------


def query_command_usage(
    conn: sqlite3.Connection,
    project: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Aggregate command usage counts, optionally filtered by project.

    Includes invocation_sources field showing which sources contributed
    (e.g., 'slash_command,skill_tool').
    """
    return _query_item_usage(
        conn,
        table="session_commands",
        item_col="command_name",
        project=project,
        limit=limit,
        track_mentions=False,
    )


def query_command_detail(
    conn: sqlite3.Connection,
    command_name: str,
    limit: int = 100,
    offset: int = 0,
) -> dict | None:
    """Detailed stats for a single command with trend and session list."""
    result = _query_item_detail(
        conn,
        table="session_commands",
        sub_table="subagent_commands",
        item_col="command_name",
        item_value=command_name,
        limit=limit,
        offset=offset,
        track_mentions=False,
    )
    if result is None:
        return None
    result["name"] = command_name
    return result


def query_command_sessions(
    conn: sqlite3.Connection,
    command_name: str,
    limit: int = 50,
) -> dict:
    """Get sessions that used a specific command. Returns {name, total_uses, sessions}."""
    rows = conn.execute(
        """SELECT
            sc.session_uuid,
            sc.count,
            s.slug,
            s.project_encoded_name,
            s.start_time
        FROM session_commands sc
        JOIN sessions s ON sc.session_uuid = s.uuid
        WHERE sc.command_name = :cmd
        ORDER BY s.start_time DESC
        LIMIT :limit""",
        {"cmd": command_name, "limit": limit},
    ).fetchall()

    return {
        "name": command_name,
        "total_uses": sum(r["count"] for r in rows),
        "sessions": [
            {
                "uuid": row["session_uuid"],
                "count": row["count"],
                "slug": row["slug"],
                "project_encoded_name": row["project_encoded_name"],
                "start_time": row["start_time"],
            }
            for row in rows
        ],
    }


def _query_item_usage_trend(
    conn: sqlite3.Connection,
    *,
    table: str,
    item_col: str,
    item_col_qualified: str,
    from_clause: str,
    project: Optional[str],
    period: str,
    track_mentions: bool = False,
) -> dict:
    """Shared helper for skill/command aggregate usage-trend queries.

    Args:
        conn: SQLite connection.
        table: Source table alias prefix used in qualified column names.
        item_col: Unqualified item name column (e.g. 'skill_name').
        item_col_qualified: Table-qualified item name column (e.g. 'sk.skill_name').
        from_clause: Full FROM … JOIN clause for all queries.
        project: Optional project encoded name filter.
        period: Time period - "week", "month", "quarter", or "all".
        track_mentions: When True, adds a WHERE … != 'text_detection' filter so
            mention-only rows are excluded from counts (skills only).

    Returns:
        Dict with total, by_item, trend, trend_by_item, first_used, last_used.
    """
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    cutoff = None
    if period == "week":
        cutoff = now - timedelta(days=7)
    elif period == "month":
        cutoff = now - timedelta(days=30)
    elif period == "quarter":
        cutoff = now - timedelta(days=90)

    conditions = []
    params: dict = {}
    if project:
        conditions.append("s.project_encoded_name = :project")
        params["project"] = project
    if cutoff:
        conditions.append("s.start_time >= :cutoff")
        params["cutoff"] = cutoff.isoformat()

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    # For skills, build a tighter where clause that excludes text_detection rows.
    if track_mentions:
        mention_filter = f"{table}.invocation_source != 'text_detection'"
        where_items = (f"{where} AND {mention_filter}") if where else f"WHERE {mention_filter}"
    else:
        where_items = where

    # Totals by item
    rows = conn.execute(
        f"""SELECT {item_col_qualified}, SUM({table}.count) as total_count
        {from_clause}
        {where_items}
        GROUP BY {item_col_qualified}
        ORDER BY total_count DESC""",
        params,
    ).fetchall()

    by_item = {row[item_col]: row["total_count"] for row in rows}
    total = sum(by_item.values())

    # Daily trend
    and_or_where = "AND" if where_items else "WHERE"
    trend_rows = conn.execute(
        f"""SELECT {_tz_date()} as date, SUM({table}.count) as count
        {from_clause}
        {where_items}
        {and_or_where} s.start_time IS NOT NULL
        GROUP BY {_tz_date()}
        ORDER BY date""",
        params,
    ).fetchall()

    trend = [{"date": row["date"], "count": row["count"]} for row in trend_rows]

    trend_by_item = _query_per_item_trend(
        conn,
        item_col=item_col_qualified,
        from_clause=from_clause,
        where=where_items,
        params=params,
        count_expr=f"SUM({table}.count)",
    )

    # First/last used
    time_row = conn.execute(
        f"""SELECT MIN(s.start_time) as first_used, MAX(s.start_time) as last_used
        {from_clause}
        {where_items}""",
        params,
    ).fetchone()

    first_used = time_row["first_used"] if time_row else None
    last_used = time_row["last_used"] if time_row else None

    # Per-user trend
    trend_by_user = _query_per_user_trend(
        conn,
        from_clause=from_clause,
        where=where_items,
        params=params,
        count_expr=f"SUM({table}.count)",
    )
    # Resolve user names
    trend_user_ids = [uid for uid in trend_by_user if uid != "_local"]
    user_names = _resolve_user_names(conn, trend_user_ids) if trend_user_ids else {}

    return {
        "total": total,
        "by_item": by_item,
        "trend": trend,
        "trend_by_item": trend_by_item,
        "trend_by_user": trend_by_user,
        "user_names": user_names,
        "first_used": first_used,
        "last_used": last_used,
    }


def query_command_usage_trend(
    conn: sqlite3.Connection,
    project: Optional[str] = None,
    period: str = "month",
) -> dict:
    """
    Aggregate command usage with daily trend data.

    Args:
        conn: SQLite connection
        project: Optional project encoded name filter
        period: Time period - "week", "month", "quarter", or "all"

    Returns:
        Dict with total, by_item, trend, trend_by_item, first_used, last_used
    """
    return _query_item_usage_trend(
        conn,
        table="sc",
        item_col="command_name",
        item_col_qualified="sc.command_name",
        from_clause="FROM session_commands sc JOIN sessions s ON sc.session_uuid = s.uuid",
        project=project,
        period=period,
        track_mentions=False,
    )


# ---------------------------------------------------------------------------
# Project queries
# ---------------------------------------------------------------------------


def query_project_sessions(
    conn: sqlite3.Connection,
    project: str,
    limit: Optional[int] = None,
    offset: int = 0,
    search: Optional[str] = None,
) -> dict:
    """Paginated session list for a project with optional search. Returns {sessions, total}."""
    # Build WHERE clause
    where = "s.project_encoded_name = :project AND s.message_count > 0"
    params: dict = {"project": project, "offset": offset}

    fts_join = ""
    if search:
        raw_tokens = [t.strip() for t in search.split() if t.strip()][:7]
        tokens = [_sanitize_fts_token(t) for t in raw_tokens]
        tokens = [t for t in tokens if t]
        if tokens:
            fts_terms = " AND ".join(t for t in tokens)
            fts_join = "JOIN sessions_fts ON sessions_fts.rowid = s.rowid"
            where += " AND sessions_fts MATCH :fts_query"
            params["fts_query"] = fts_terms

    # Total count (with search filter applied)
    try:
        total = conn.execute(
            f"SELECT COUNT(*) FROM sessions s {fts_join} WHERE {where}",
            params,
        ).fetchone()[0]
    except sqlite3.OperationalError as e:
        logger.warning("FTS5 query error in project sessions: %s", e)
        return {"sessions": [], "total": 0}

    # Paginated results
    if limit is not None:
        params["limit"] = limit
    else:
        params["limit"] = -1  # SQLite: LIMIT -1 means no limit

    rows = conn.execute(
        f"""SELECT
            s.uuid, s.slug, s.message_count, s.start_time, s.end_time,
            s.duration_seconds, s.models_used, s.subagent_count,
            s.initial_prompt, s.git_branch, s.session_titles,
            s.is_continuation_marker, s.was_compacted, s.input_tokens,
            s.output_tokens, s.total_cost, s.compaction_count,
            s.session_source,
            s.source, s.remote_user_id, s.remote_machine_id
        FROM sessions s
        {fts_join}
        WHERE {where}
        ORDER BY s.start_time DESC
        LIMIT :limit OFFSET :offset""",
        params,
    ).fetchall()

    sessions = []
    for row in rows:
        session = dict(row)
        session["models_used"] = _parse_json_list(session.get("models_used"))
        session["session_titles"] = _parse_json_list(session.get("session_titles"))
        session["git_branches"] = [session["git_branch"]] if session.get("git_branch") else []
        sessions.append(session)

    return {"sessions": sessions, "total": total}


def query_project_branches(
    conn: sqlite3.Connection,
    project: str,
) -> dict:
    """Branch aggregation for a project. Returns {branches, active_branch}."""
    rows = conn.execute(
        """SELECT
            git_branch as name,
            COUNT(*) as session_count,
            MAX(COALESCE(end_time, start_time)) as last_active
        FROM sessions
        WHERE project_encoded_name = :project
          AND git_branch IS NOT NULL
        GROUP BY git_branch
        ORDER BY last_active DESC""",
        {"project": project},
    ).fetchall()

    # Active branch = branch from the most recent session
    active_row = conn.execute(
        """SELECT git_branch FROM sessions
        WHERE project_encoded_name = :project AND git_branch IS NOT NULL
        ORDER BY start_time DESC
        LIMIT 1""",
        {"project": project},
    ).fetchone()
    active_branch = active_row["git_branch"] if active_row else None

    branches = [dict(row) for row in rows]
    return {"branches": branches, "active_branch": active_branch}


def query_project_chains(
    conn: sqlite3.Connection,
    project: str,
) -> dict:
    """Session chains (slug groups with >1 session). Returns {chains: {slug: [session_dicts]}, singles_count}."""
    # Get slugs with multiple sessions
    chain_slugs = conn.execute(
        """SELECT slug FROM sessions
        WHERE project_encoded_name = :project AND slug IS NOT NULL AND message_count > 0
        GROUP BY slug HAVING COUNT(*) > 1""",
        {"project": project},
    ).fetchall()

    if not chain_slugs:
        total = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE project_encoded_name = :project AND message_count > 0",
            {"project": project},
        ).fetchone()[0]
        return {"chains": {}, "total_sessions": total, "chained_sessions": 0}

    slug_list = [row["slug"] for row in chain_slugs]
    slug_params = {f"slug_{i}": s for i, s in enumerate(slug_list)}
    # Safe: placeholders are named parameter markers, not user input
    placeholders = ",".join(f":slug_{i}" for i in range(len(slug_list)))
    params = {"project": project, **slug_params}

    rows = conn.execute(
        f"""SELECT
            uuid, slug, start_time, end_time,
            was_compacted, is_continuation_marker,
            message_count, initial_prompt, compaction_count
        FROM sessions
        WHERE project_encoded_name = :project AND slug IN ({placeholders}) AND message_count > 0
        ORDER BY slug, start_time ASC""",
        params,
    ).fetchall()

    # Group by slug
    chains: dict[str, list[dict]] = {}
    for row in rows:
        d = dict(row)
        slug = d["slug"]
        if slug not in chains:
            chains[slug] = []
        chains[slug].append(d)

    chained_sessions = sum(len(v) for v in chains.values())
    total = conn.execute(
        "SELECT COUNT(*) FROM sessions WHERE project_encoded_name = :project AND message_count > 0",
        {"project": project},
    ).fetchone()[0]

    return {"chains": chains, "total_sessions": total, "chained_sessions": chained_sessions}


# ---------------------------------------------------------------------------
# Session lookup
# ---------------------------------------------------------------------------


def query_session_lookup(
    conn: sqlite3.Connection,
    project: str,
    identifier: str,
) -> dict | None:
    """
    Fast session lookup by slug or UUID prefix.
    Returns session dict with matched_by field, or None.
    """
    # Fix 1: Guard against empty string
    if not identifier or not identifier.strip():
        return None

    is_uuid_like = all(c in "0123456789abcdef-" for c in identifier.lower())

    if is_uuid_like:
        # Try exact UUID match
        row = conn.execute(
            """SELECT uuid, slug, project_encoded_name, project_path,
                   message_count, start_time, end_time, initial_prompt
            FROM sessions
            WHERE uuid = :id AND project_encoded_name = :project AND message_count > 0""",
            {"id": identifier, "project": project},
        ).fetchone()
        if row:
            result = dict(row)
            result["matched_by"] = "uuid"
            return result

        # Try UUID prefix match
        row = conn.execute(
            """SELECT uuid, slug, project_encoded_name, project_path,
                   message_count, start_time, end_time, initial_prompt
            FROM sessions
            WHERE uuid LIKE :prefix AND project_encoded_name = :project AND message_count > 0
            LIMIT 1""",
            {"prefix": f"{identifier}%", "project": project},
        ).fetchone()
        if row:
            result = dict(row)
            result["matched_by"] = "uuid_prefix"
            return result

    # Fix 3: Always try slug match as fallback (slugs like "abc-def" look UUID-like)
    row = conn.execute(
        """SELECT uuid, slug, project_encoded_name, project_path,
               message_count, start_time, end_time, initial_prompt
        FROM sessions
        WHERE slug = :slug AND project_encoded_name = :project AND message_count > 0
        ORDER BY start_time DESC
        LIMIT 1""",
        {"slug": identifier, "project": project},
    ).fetchone()
    if row:
        result = dict(row)
        result["matched_by"] = "slug"
        return result

    return None


# ---------------------------------------------------------------------------
# Agent usage queries
# ---------------------------------------------------------------------------


def query_source_session(conn: sqlite3.Connection, uuid: str) -> dict | None:
    """Look up a session by UUID for continuation resolution."""
    row = conn.execute(
        """SELECT uuid, slug, project_encoded_name, end_time, is_continuation_marker
        FROM sessions WHERE uuid = :uuid""",
        {"uuid": uuid},
    ).fetchone()
    return dict(row) if row else None


def query_continuation_session(
    conn: sqlite3.Connection,
    project: str,
    source_uuid: str,
    slug: Optional[str],
    source_end_time: Optional[str],
) -> dict | None:
    """
    Find a continuation session by slug match or time-proximity fallback.

    Returns session dict with uuid, slug, project_encoded_name, or None.
    """
    # Step 1: Slug match (primary)
    if slug:
        row = conn.execute(
            """SELECT uuid, slug, project_encoded_name
            FROM sessions
            WHERE project_encoded_name = :project
              AND slug = :slug
              AND uuid != :source_uuid
              AND is_continuation_marker = 0
              AND message_count > 0
            ORDER BY start_time DESC
            LIMIT 1""",
            {"project": project, "slug": slug, "source_uuid": source_uuid},
        ).fetchone()
        if row:
            return dict(row)

    # Step 2: Time-proximity fallback (within 60 seconds)
    if source_end_time:
        row = conn.execute(
            """SELECT uuid, slug, project_encoded_name
            FROM sessions
            WHERE project_encoded_name = :project
              AND uuid != :source_uuid
              AND is_continuation_marker = 0
              AND message_count > 0
              AND ABS(julianday(start_time) - julianday(:source_end_time)) < (60.0 / 86400.0)
            ORDER BY start_time DESC
            LIMIT 1""",
            {"project": project, "source_uuid": source_uuid, "source_end_time": source_end_time},
        ).fetchone()
        if row:
            return dict(row)

    return None


def query_session_by_message_uuid(conn: sqlite3.Connection, message_uuid: str) -> dict | None:
    """Look up a session by a message UUID it contains."""
    row = conn.execute(
        """SELECT mu.session_uuid, s.slug, s.project_encoded_name, s.source_encoded_name
        FROM message_uuids mu
        JOIN sessions s ON mu.session_uuid = s.uuid
        WHERE mu.message_uuid = :msg_uuid""",
        {"msg_uuid": message_uuid},
    ).fetchone()
    return dict(row) if row else None


def query_chain_parents(conn: sqlite3.Connection, child_uuid: str) -> list[dict]:
    """Find parent sessions for a child session via leaf_uuid references."""
    rows = conn.execute(
        """SELECT DISTINCT mu.session_uuid AS parent_uuid, s.slug, s.start_time, s.end_time
        FROM session_leaf_refs slr
        JOIN message_uuids mu ON slr.leaf_uuid = mu.message_uuid
        JOIN sessions s ON mu.session_uuid = s.uuid
        WHERE slr.session_uuid = :child_uuid
          AND mu.session_uuid != :child_uuid""",
        {"child_uuid": child_uuid},
    ).fetchall()
    return [dict(r) for r in rows]


def query_chain_children(conn: sqlite3.Connection, parent_uuid: str) -> list[dict]:
    """Find child sessions that loaded context from a parent session via leaf_uuid."""
    rows = conn.execute(
        """SELECT DISTINCT slr.session_uuid AS child_uuid, s.slug, s.start_time, s.end_time
        FROM session_leaf_refs slr
        JOIN message_uuids mu ON slr.leaf_uuid = mu.message_uuid
        JOIN sessions s ON slr.session_uuid = s.uuid
        WHERE mu.session_uuid = :parent_uuid
          AND slr.session_uuid != :parent_uuid""",
        {"parent_uuid": parent_uuid},
    ).fetchall()
    return [dict(r) for r in rows]


def query_chain_info_for_project(conn: sqlite3.Connection, project: str) -> dict[str, dict]:
    """
    Build chain info for all sessions in a project using both leaf_uuid and slug matching.

    Returns dict mapping session_uuid -> {chain_id, position, total, is_root, is_latest}.

    Uses leaf_uuid links (high confidence) first, then augments with slug matching
    for sequential (non-overlapping) sessions only.
    """
    # Step 1: Get leaf_uuid-based parent→child links
    leaf_links = conn.execute(
        """SELECT DISTINCT slr.session_uuid AS child_uuid, mu.session_uuid AS parent_uuid
        FROM session_leaf_refs slr
        JOIN message_uuids mu ON slr.leaf_uuid = mu.message_uuid
        JOIN sessions s ON slr.session_uuid = s.uuid
        WHERE s.project_encoded_name = :project
          AND mu.session_uuid != slr.session_uuid""",
        {"project": project},
    ).fetchall()

    # Build parent→child graph from leaf_uuid links
    leaf_parent_of: dict[str, str] = {}  # child -> parent
    for row in leaf_links:
        leaf_parent_of[row["child_uuid"]] = row["parent_uuid"]

    # Step 2: Get slug groups with >1 session, ordered by start_time
    slug_groups = conn.execute(
        """SELECT uuid, slug, start_time, end_time
        FROM sessions
        WHERE project_encoded_name = :project
          AND slug IS NOT NULL
          AND message_count > 0
        ORDER BY slug, start_time""",
        {"project": project},
    ).fetchall()

    # Group by slug
    from collections import defaultdict

    slugs: dict[str, list[dict]] = defaultdict(list)
    for row in slug_groups:
        slugs[row["slug"]].append(dict(row))

    # Step 3: Build chain info combining both methods
    chain_info: dict[str, dict] = {}

    for slug, sessions in slugs.items():
        if len(sessions) < 2:
            continue

        # Filter out concurrent sessions: only chain if sequential
        # (start_time[n] >= end_time[n-1])
        sequential = [sessions[0]]
        for i in range(1, len(sessions)):
            prev_end = sequential[-1].get("end_time")
            curr_start = sessions[i].get("start_time")
            # If previous has no end_time or times overlap, skip (concurrent)
            if prev_end and curr_start and curr_start >= prev_end:
                sequential.append(sessions[i])
            elif sessions[i]["uuid"] in leaf_parent_of:
                # Keep if linked by leaf_uuid even if times overlap
                sequential.append(sessions[i])

        if len(sequential) < 2:
            continue

        chain_length = len(sequential)
        for idx, sess in enumerate(sequential):
            chain_info[sess["uuid"]] = {
                "chain_id": slug,
                "position": idx,
                "total": chain_length,
                "is_root": idx == 0,
                "is_latest": idx == chain_length - 1,
            }

    return chain_info


def query_session_chain(conn: sqlite3.Connection, session_uuid: str) -> dict | None:
    """
    Build a full session chain for a single session using DB only (no JSONL scanning).

    Returns dict with: current_session_uuid, nodes, root_uuid, total_sessions,
    max_depth, total_compactions — matching the SessionChain schema.
    Returns None if session not found.
    """
    from collections import defaultdict

    # Get the target session's project
    target = conn.execute(
        "SELECT project_encoded_name, slug FROM sessions WHERE uuid = :uuid",
        {"uuid": session_uuid},
    ).fetchone()
    if not target:
        return None

    project = target["project_encoded_name"]
    target_slug = target["slug"]

    # Step 1: Find all chain members via leaf_uuid links (recursive CTE)
    parent_of: dict[str, str] = {}  # child -> parent

    # Single recursive CTE replaces the BFS loop — one query instead of 2*N
    cte_rows = conn.execute(
        """WITH RECURSIVE chain_down(child_uuid, parent_uuid) AS (
            -- Children of seed: sessions whose leaf_refs point into seed's messages
            SELECT slr.session_uuid, mu.session_uuid
            FROM session_leaf_refs slr
            JOIN message_uuids mu ON slr.leaf_uuid = mu.message_uuid
            WHERE mu.session_uuid = :uuid AND slr.session_uuid != mu.session_uuid
            UNION
            -- Recurse: children of children
            SELECT slr.session_uuid, mu.session_uuid
            FROM session_leaf_refs slr
            JOIN message_uuids mu ON slr.leaf_uuid = mu.message_uuid
            JOIN chain_down cd ON mu.session_uuid = cd.child_uuid
            WHERE slr.session_uuid != mu.session_uuid
        ),
        chain_up(child_uuid, parent_uuid) AS (
            -- Parents of seed: sessions containing messages referenced by seed's leaf_refs
            SELECT slr.session_uuid, mu.session_uuid
            FROM session_leaf_refs slr
            JOIN message_uuids mu ON slr.leaf_uuid = mu.message_uuid
            WHERE slr.session_uuid = :uuid AND mu.session_uuid != slr.session_uuid
            UNION
            -- Recurse: parents of parents
            SELECT slr.session_uuid, mu.session_uuid
            FROM session_leaf_refs slr
            JOIN message_uuids mu ON slr.leaf_uuid = mu.message_uuid
            JOIN chain_up cu ON slr.session_uuid = cu.parent_uuid
            WHERE mu.session_uuid != slr.session_uuid
        )
        SELECT DISTINCT child_uuid, parent_uuid FROM chain_down
        UNION
        SELECT DISTINCT child_uuid, parent_uuid FROM chain_up""",
        {"uuid": session_uuid},
    ).fetchall()

    linked: set[str] = {session_uuid}
    for row in cte_rows:
        parent_of[row["child_uuid"]] = row["parent_uuid"]
        linked.add(row["child_uuid"])
        linked.add(row["parent_uuid"])

    # Step 2: Add slug siblings (sequential only, no concurrent)
    if target_slug:
        slug_sessions = conn.execute(
            """SELECT uuid, start_time, end_time FROM sessions
            WHERE project_encoded_name = :project AND slug = :slug
              AND message_count > 0
            ORDER BY start_time""",
            {"project": project, "slug": target_slug},
        ).fetchall()

        if len(slug_sessions) > 1:
            sequential = [slug_sessions[0]]
            for i in range(1, len(slug_sessions)):
                prev_end = sequential[-1]["end_time"]
                curr_start = slug_sessions[i]["start_time"]
                if prev_end and curr_start and curr_start >= prev_end:
                    sequential.append(slug_sessions[i])
                elif slug_sessions[i]["uuid"] in parent_of:
                    sequential.append(slug_sessions[i])

            if len(sequential) >= 2:
                for i, s in enumerate(sequential):
                    linked.add(s["uuid"])
                    if i > 0 and s["uuid"] not in parent_of:
                        parent_of[s["uuid"]] = sequential[i - 1]["uuid"]

    if len(linked) < 2:
        return None  # No chain

    # Step 3: Fetch full session data for all linked sessions
    placeholders = ",".join("?" * len(linked))
    rows = conn.execute(
        f"""SELECT uuid, slug, start_time, end_time, message_count,
               was_compacted, compaction_count, is_continuation_marker, initial_prompt
        FROM sessions WHERE uuid IN ({placeholders})
        ORDER BY start_time""",
        list(linked),
    ).fetchall()

    if not rows:
        return None

    session_data = {r["uuid"]: dict(r) for r in rows}

    # Step 4: Find root (no parent among linked set)
    children_of: dict[str, list[str]] = defaultdict(list)
    for child, parent in parent_of.items():
        if parent in session_data and child in session_data:
            children_of[parent].append(child)

    root_uuid = None
    for uuid in session_data:
        if uuid not in parent_of or parent_of[uuid] not in session_data:
            root_uuid = uuid
            break
    if not root_uuid:
        root_uuid = rows[0]["uuid"]

    # Step 5: BFS to build nodes with depth
    nodes = []
    total_compactions = 0
    max_depth = 0
    visited: set[str] = set()
    queue = [(root_uuid, 0, None)]  # (uuid, depth, parent_uuid)

    while queue:
        uuid, depth, par = queue.pop(0)
        if uuid in visited or uuid not in session_data:
            continue
        visited.add(uuid)
        s = session_data[uuid]
        max_depth = max(max_depth, depth)
        if s["was_compacted"]:
            total_compactions += s["compaction_count"] or 1

        child_uuids = [c for c in children_of.get(uuid, []) if c in session_data]
        nodes.append(
            {
                "uuid": uuid,
                "slug": s["slug"],
                "start_time": s["start_time"],
                "end_time": s["end_time"],
                "is_current": uuid == session_uuid,
                "chain_depth": depth,
                "parent_uuid": par,
                "children_uuids": child_uuids,
                "was_compacted": bool(s["was_compacted"]),
                "is_continuation_marker": bool(s["is_continuation_marker"]),
                "message_count": s["message_count"] or 0,
                "initial_prompt": s["initial_prompt"],
            }
        )

        for child in child_uuids:
            queue.append((child, depth + 1, uuid))

    # Add any unvisited sessions (disconnected but same slug)
    for uuid, s in session_data.items():
        if uuid not in visited:
            nodes.append(
                {
                    "uuid": uuid,
                    "slug": s["slug"],
                    "start_time": s["start_time"],
                    "end_time": s["end_time"],
                    "is_current": uuid == session_uuid,
                    "chain_depth": max_depth + 1,
                    "parent_uuid": None,
                    "children_uuids": [],
                    "was_compacted": bool(s["was_compacted"]),
                    "is_continuation_marker": bool(s["is_continuation_marker"]),
                    "message_count": s["message_count"] or 0,
                    "initial_prompt": s["initial_prompt"],
                }
            )

    return {
        "current_session_uuid": session_uuid,
        "nodes": nodes,
        "root_uuid": root_uuid,
        "total_sessions": len(nodes),
        "max_depth": max_depth,
        "total_compactions": total_compactions,
    }


def query_session_has_chain(conn: sqlite3.Connection, session_uuid: str) -> bool:
    """
    Lightweight check: does this session belong to a chain (>= 2 linked sessions)?

    Checks leaf_uuid links and slug siblings without building the full chain.
    """
    # Check leaf_uuid links (either direction)
    row = conn.execute(
        """SELECT EXISTS(
            SELECT 1 FROM session_leaf_refs slr
            JOIN message_uuids mu ON slr.leaf_uuid = mu.message_uuid
            WHERE (mu.session_uuid = :uuid AND slr.session_uuid != :uuid)
               OR (slr.session_uuid = :uuid AND mu.session_uuid != :uuid)
        ) AS has_link""",
        {"uuid": session_uuid},
    ).fetchone()
    if row and row["has_link"]:
        return True

    # Check slug siblings
    slug_row = conn.execute(
        "SELECT slug FROM sessions WHERE uuid = :uuid", {"uuid": session_uuid}
    ).fetchone()
    if slug_row and slug_row["slug"]:
        count = conn.execute(
            """SELECT COUNT(*) AS cnt FROM sessions
            WHERE slug = :slug AND message_count > 0
              AND project_encoded_name = (
                SELECT project_encoded_name FROM sessions WHERE uuid = :uuid
              )""",
            {"slug": slug_row["slug"], "uuid": session_uuid},
        ).fetchone()
        if count and count["cnt"] >= 2:
            return True

    return False


def query_skill_usage_trend(
    conn: sqlite3.Connection,
    project: Optional[str] = None,
    period: str = "month",
) -> dict:
    """
    Aggregate skill usage with daily trend data.

    Args:
        conn: SQLite connection
        project: Optional project encoded name filter
        period: Time period - "week", "month", "quarter", or "all"

    Returns:
        Dict with total, by_item, trend, trend_by_item, first_used, last_used
    """
    return _query_item_usage_trend(
        conn,
        table="sk",
        item_col="skill_name",
        item_col_qualified="sk.skill_name",
        from_clause="FROM session_skills sk JOIN sessions s ON sk.session_uuid = s.uuid",
        project=project,
        period=period,
        track_mentions=True,
    )


def query_agent_usage_trend(
    conn: sqlite3.Connection,
    project: Optional[str] = None,
    period: str = "month",
    subagent_type: Optional[str] = None,
) -> dict:
    """
    Aggregate agent (subagent) usage with daily trend data.

    Args:
        conn: SQLite connection
        project: Optional project encoded name filter
        period: Time period - "week", "month", "quarter", or "all"
        subagent_type: Optional specific agent type filter

    Returns:
        Dict with total, by_item, trend, first_used, last_used
    """
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    cutoff = None
    if period == "week":
        cutoff = now - timedelta(days=7)
    elif period == "month":
        cutoff = now - timedelta(days=30)
    elif period == "quarter":
        cutoff = now - timedelta(days=90)

    conditions = ["si.subagent_type IS NOT NULL"]
    params: dict = {}
    if project:
        conditions.append("s.project_encoded_name = :project")
        params["project"] = project
    if subagent_type:
        conditions.append("si.subagent_type = :subagent_type")
        params["subagent_type"] = subagent_type
    if cutoff:
        conditions.append("s.start_time >= :cutoff")
        params["cutoff"] = cutoff.isoformat()

    where = "WHERE " + " AND ".join(conditions)

    # Totals by agent type
    rows = conn.execute(
        f"""SELECT si.subagent_type, COUNT(*) as total_count
        FROM subagent_invocations si
        JOIN sessions s ON si.session_uuid = s.uuid
        {where}
        GROUP BY si.subagent_type
        ORDER BY total_count DESC""",
        params,
    ).fetchall()

    by_item = {row["subagent_type"]: row["total_count"] for row in rows}
    total = sum(by_item.values())

    # Daily trend
    trend_rows = conn.execute(
        f"""SELECT {_tz_date()} as date, COUNT(*) as count
        FROM subagent_invocations si
        JOIN sessions s ON si.session_uuid = s.uuid
        {where}
        AND s.start_time IS NOT NULL
        GROUP BY {_tz_date()}
        ORDER BY date""",
        params,
    ).fetchall()

    trend = [{"date": row["date"], "count": row["count"]} for row in trend_rows]

    trend_by_item = _query_per_item_trend(
        conn,
        item_col="si.subagent_type",
        from_clause="FROM subagent_invocations si JOIN sessions s ON si.session_uuid = s.uuid",
        where=where,
        params=params,
        count_expr="COUNT(*)",
    )

    trend_by_user = _query_per_user_trend(
        conn,
        from_clause="FROM subagent_invocations si JOIN sessions s ON si.session_uuid = s.uuid",
        where=where,
        params=params,
        count_expr="COUNT(*)",
    )
    user_names = _resolve_user_names(conn, [u for u in trend_by_user if u != "_local"])

    # First/last used
    time_row = conn.execute(
        f"""SELECT MIN(s.start_time) as first_used, MAX(s.start_time) as last_used
        FROM subagent_invocations si
        JOIN sessions s ON si.session_uuid = s.uuid
        {where}""",
        params,
    ).fetchone()

    first_used = time_row["first_used"] if time_row else None
    last_used = time_row["last_used"] if time_row else None

    return {
        "total": total,
        "by_item": by_item,
        "trend": trend,
        "trend_by_item": trend_by_item,
        "trend_by_user": trend_by_user,
        "user_names": user_names,
        "first_used": first_used,
        "last_used": last_used,
    }


def query_agent_usage(conn: sqlite3.Connection, search: Optional[str] = None) -> dict:
    """
    Aggregate agent usage from subagent_invocations table.

    Returns dict with:
    - agents: list of dicts with per-type aggregates
    - total_runs: int
    - total_cost: float

    Args:
        conn: SQLite connection
        search: Optional search filter for subagent_type (case-insensitive LIKE)
    """
    conditions = ["si.subagent_type IS NOT NULL"]
    params = {}

    if search:
        conditions.append("si.subagent_type LIKE '%' || :search || '%'")
        params["search"] = search

    where = " AND ".join(conditions)

    rows = conn.execute(
        f"""SELECT
            si.subagent_type,
            COUNT(*) as total_runs,
            COALESCE(SUM(si.cost_usd), 0) as total_cost_usd,
            COALESCE(SUM(si.input_tokens), 0) as total_input_tokens,
            COALESCE(SUM(si.output_tokens), 0) as total_output_tokens,
            COALESCE(AVG(si.duration_seconds), 0) as avg_duration_seconds,
            MIN(si.started_at) as first_used,
            MAX(si.started_at) as last_used,
            GROUP_CONCAT(DISTINCT s.project_encoded_name) as projects
        FROM subagent_invocations si
        JOIN sessions s ON si.session_uuid = s.uuid
        WHERE {where}
        GROUP BY si.subagent_type
        ORDER BY total_runs DESC""",
        params,
    ).fetchall()

    agents = []
    total_runs = 0
    total_cost = 0.0

    for row in rows:
        agent_data = dict(row)
        # Split comma-separated projects into list
        projects_str = agent_data.pop("projects", "")
        agent_data["projects"] = projects_str.split(",") if projects_str else []
        agents.append(agent_data)
        total_runs += row["total_runs"]
        total_cost += row["total_cost_usd"]

    return {
        "agents": agents,
        "total_runs": total_runs,
        "total_cost": total_cost,
    }


def query_agent_detail(
    conn: sqlite3.Connection,
    subagent_type: str,
) -> dict | None:
    """
    Single agent type detail with per-project breakdown.

    Returns dict with aggregated stats and usage_by_project, or None if not found.
    """
    row = conn.execute(
        """SELECT
            si.subagent_type,
            COUNT(*) as total_runs,
            COALESCE(SUM(si.cost_usd), 0) as total_cost_usd,
            COALESCE(SUM(si.input_tokens), 0) as total_input_tokens,
            COALESCE(SUM(si.output_tokens), 0) as total_output_tokens,
            COALESCE(AVG(si.duration_seconds), 0) as avg_duration_seconds,
            MIN(si.started_at) as first_used,
            MAX(si.started_at) as last_used,
            GROUP_CONCAT(DISTINCT s.project_encoded_name) as projects
        FROM subagent_invocations si
        JOIN sessions s ON si.session_uuid = s.uuid
        WHERE si.subagent_type = :type
        GROUP BY si.subagent_type""",
        {"type": subagent_type},
    ).fetchone()

    if not row or row["total_runs"] == 0:
        return None

    result = dict(row)
    projects_str = result.pop("projects", "")
    result["projects"] = projects_str.split(",") if projects_str else []

    # Per-project breakdown
    project_rows = conn.execute(
        """SELECT s.project_encoded_name, COUNT(*) as run_count
        FROM subagent_invocations si
        JOIN sessions s ON si.session_uuid = s.uuid
        WHERE si.subagent_type = :type
        GROUP BY s.project_encoded_name
        ORDER BY run_count DESC""",
        {"type": subagent_type},
    ).fetchall()
    result["usage_by_project"] = {
        pr["project_encoded_name"]: pr["run_count"] for pr in project_rows
    }

    # Top tools used by this agent type
    tool_rows = conn.execute(
        """SELECT st.tool_name, SUM(st.count) as total_count
        FROM subagent_tools st
        JOIN subagent_invocations si ON st.invocation_id = si.id
        WHERE si.subagent_type = :type
        GROUP BY st.tool_name
        ORDER BY total_count DESC
        LIMIT 20""",
        {"type": subagent_type},
    ).fetchall()
    result["top_tools"] = {row["tool_name"]: row["total_count"] for row in tool_rows}

    # Top skills used by this agent type
    skill_rows = conn.execute(
        """SELECT ssk.skill_name, SUM(ssk.count) as total_count
        FROM subagent_skills ssk
        JOIN subagent_invocations si ON ssk.invocation_id = si.id
        WHERE si.subagent_type = :type
        GROUP BY ssk.skill_name
        ORDER BY total_count DESC
        LIMIT 20""",
        {"type": subagent_type},
    ).fetchall()
    result["top_skills"] = {row["skill_name"]: row["total_count"] for row in skill_rows}

    # Top commands used by this agent type
    command_rows = conn.execute(
        """SELECT sc.command_name, SUM(sc.count) as total_count
        FROM subagent_commands sc
        JOIN subagent_invocations si ON sc.invocation_id = si.id
        WHERE si.subagent_type = :type
        GROUP BY sc.command_name
        ORDER BY total_count DESC
        LIMIT 20""",
        {"type": subagent_type},
    ).fetchall()
    result["top_commands"] = {row["command_name"]: row["total_count"] for row in command_rows}

    return result


def query_agent_history(
    conn: sqlite3.Connection,
    subagent_type: str,
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """
    Paginated invocation history for a specific agent type.

    Returns dict with:
    - invocations: list of dicts
    - total: int
    """
    total = conn.execute(
        "SELECT COUNT(*) FROM subagent_invocations WHERE subagent_type = :type",
        {"type": subagent_type},
    ).fetchone()[0]

    rows = conn.execute(
        """SELECT
            si.agent_id,
            si.session_uuid,
            s.project_encoded_name,
            s.project_path,
            si.started_at,
            si.duration_seconds,
            si.input_tokens,
            si.output_tokens,
            si.cost_usd,
            si.agent_display_name
        FROM subagent_invocations si
        JOIN sessions s ON si.session_uuid = s.uuid
        WHERE si.subagent_type = :type
        ORDER BY si.started_at DESC
        LIMIT :limit OFFSET :offset""",
        {"type": subagent_type, "limit": limit, "offset": offset},
    ).fetchall()

    return {
        "invocations": [dict(row) for row in rows],
        "total": total,
    }


def query_sessions_by_agent(
    conn: sqlite3.Connection,
    subagent_type: str,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """Find sessions that used a specific agent type. Returns {sessions, total}."""
    # Total count (distinct sessions)
    total = conn.execute(
        "SELECT COUNT(DISTINCT session_uuid) FROM subagent_invocations WHERE subagent_type = :type",
        {"type": subagent_type},
    ).fetchone()[0]

    # Paginated results - join sessions for full session data
    rows = conn.execute(
        """SELECT
            s.uuid, s.slug, s.project_encoded_name, s.project_path,
            s.message_count, s.start_time, s.end_time, s.duration_seconds,
            s.models_used, s.subagent_count, s.initial_prompt,
            s.git_branch, s.session_titles,
            s.session_source, s.source, s.remote_user_id, s.remote_machine_id
        FROM sessions s
        JOIN (SELECT DISTINCT session_uuid FROM subagent_invocations WHERE subagent_type = :type) si
            ON s.uuid = si.session_uuid
        ORDER BY s.start_time DESC
        LIMIT :limit OFFSET :offset""",
        {"type": subagent_type, "limit": limit, "offset": offset},
    ).fetchall()

    sessions = []
    for row in rows:
        session = dict(row)
        session["models_used"] = _parse_json_list(session.get("models_used"))
        session["session_titles"] = _parse_json_list(session.get("session_titles"))
        session["git_branches"] = [session["git_branch"]] if session.get("git_branch") else []
        sessions.append(session)

    return {"sessions": sessions, "total": total}


# ---------------------------------------------------------------------------
# MCP tools queries
# ---------------------------------------------------------------------------


def _mcp_time_filter(period: str) -> tuple[str, dict]:
    """Build time filter clause and params for MCP queries."""
    from datetime import timedelta

    params: dict = {}
    if period == "day":
        cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    elif period == "week":
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    elif period == "month":
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    elif period == "quarter":
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    else:
        return "", params

    params["cutoff"] = cutoff.isoformat()
    return "s.start_time >= :cutoff", params


# ---------------------------------------------------------------------------
# Built-in tool categories (virtual "servers" for non-MCP tools)
# ---------------------------------------------------------------------------

BUILTIN_TOOL_CATEGORIES: dict[str, list[str]] = {
    "builtin-file-ops": ["Read", "Write", "Edit", "Glob", "Grep", "NotebookEdit"],
    "builtin-execution": ["Bash", "KillShell"],
    "builtin-agents": [
        "Task",
        "Agent",
        "TaskCreate",
        "TaskUpdate",
        "TaskOutput",
        "TaskList",
        "TaskGet",
        "TaskStop",
        "SendMessage",
        "TeamCreate",
        "TeamDelete",
    ],
    "builtin-planning": [
        "TodoWrite",
        "EnterPlanMode",
        "ExitPlanMode",
        "Skill",
        "AskUserQuestion",
        "EnterWorktree",
    ],
    "builtin-web": ["WebFetch", "WebSearch"],
    "builtin-tools": ["ToolSearch", "ReadMcpResourceTool", "ListMcpResourcesTool"],
}

BUILTIN_CATEGORY_DISPLAY: dict[str, str] = {
    "builtin-file-ops": "File Operations",
    "builtin-execution": "Execution",
    "builtin-agents": "Agent Coordination",
    "builtin-planning": "Planning & Workflow",
    "builtin-web": "Web Access",
    "builtin-tools": "Tool Discovery",
}

# Reverse lookup: tool_name -> category
_BUILTIN_TOOL_TO_CATEGORY: dict[str, str] = {
    tool: cat for cat, tools in BUILTIN_TOOL_CATEGORIES.items() for tool in tools
}


def query_builtin_tools_overview(
    conn: sqlite3.Connection,
    project: Optional[str] = None,
    period: str = "all",
) -> dict:
    """
    Aggregate built-in tool usage across virtual server categories.

    Returns dict with same shape as query_mcp_tools_overview:
    {total_servers, total_tools, total_calls, total_sessions, servers: [...]}
    """
    from collections import defaultdict

    all_builtin_names = list(_BUILTIN_TOOL_TO_CATEGORY.keys())
    placeholders = ",".join(f":t{i}" for i in range(len(all_builtin_names)))
    params: dict = {f"t{i}": name for i, name in enumerate(all_builtin_names)}

    conditions = [f"st.tool_name IN ({placeholders})"]

    if project:
        conditions.append("s.project_encoded_name = :project")
        params["project"] = project

    time_clause, time_params = _mcp_time_filter(period)
    if time_clause:
        conditions.append(time_clause)
        params.update(time_params)

    where = "WHERE " + " AND ".join(conditions)

    # 1. Main session tool usage
    main_rows = conn.execute(
        f"""SELECT
            st.tool_name,
            SUM(st.count) as total_count,
            COUNT(DISTINCT st.session_uuid) as session_count
        FROM session_tools st
        JOIN sessions s ON st.session_uuid = s.uuid
        {where}
        GROUP BY st.tool_name""",
        params,
    ).fetchall()

    # 2. Subagent tool usage
    sub_conditions = [f"sat.tool_name IN ({placeholders})"]
    sub_params: dict = {f"t{i}": name for i, name in enumerate(all_builtin_names)}
    if project:
        sub_conditions.append("s.project_encoded_name = :project")
        sub_params["project"] = project
    sub_time_clause, sub_time_params = _mcp_time_filter(period)
    if sub_time_clause:
        sub_conditions.append(sub_time_clause)
        sub_params.update(sub_time_params)
    sub_where = "WHERE " + " AND ".join(sub_conditions)

    sub_rows = conn.execute(
        f"""SELECT
            sat.tool_name,
            SUM(sat.count) as total_count,
            COUNT(DISTINCT si.session_uuid) as session_count
        FROM subagent_tools sat
        JOIN subagent_invocations si ON sat.invocation_id = si.id
        JOIN sessions s ON si.session_uuid = s.uuid
        {sub_where}
        GROUP BY sat.tool_name""",
        sub_params,
    ).fetchall()

    # Combine into tool_data
    tool_data: dict[str, dict] = defaultdict(
        lambda: {"main_count": 0, "sub_count": 0, "main_sessions": 0, "sub_sessions": 0}
    )
    for row in main_rows:
        tool_data[row["tool_name"]]["main_count"] = row["total_count"]
        tool_data[row["tool_name"]]["main_sessions"] = row["session_count"]
    for row in sub_rows:
        tool_data[row["tool_name"]]["sub_count"] = row["total_count"]
        tool_data[row["tool_name"]]["sub_sessions"] = row["session_count"]

    # 3. Time bounds per category
    time_rows = conn.execute(
        f"""SELECT
            st.tool_name,
            MIN(s.start_time) as first_used,
            MAX(s.start_time) as last_used
        FROM session_tools st
        JOIN sessions s ON st.session_uuid = s.uuid
        {where}
        GROUP BY st.tool_name""",
        params,
    ).fetchall()
    tool_time_bounds = {
        row["tool_name"]: (row["first_used"], row["last_used"]) for row in time_rows
    }

    # Group by category
    servers: dict[str, dict] = defaultdict(
        lambda: {
            "tools": [],
            "total_calls": 0,
            "main_calls": 0,
            "subagent_calls": 0,
            "first_used": None,
            "last_used": None,
        }
    )

    for tool_name, data in tool_data.items():
        category = _BUILTIN_TOOL_TO_CATEGORY.get(tool_name)
        if not category:
            continue

        total = data["main_count"] + data["sub_count"]
        servers[category]["tools"].append(
            {
                "name": tool_name,
                "full_name": tool_name,
                "calls": total,
                "session_count": data["main_sessions"],
                "main_calls": data["main_count"],
                "subagent_calls": data["sub_count"],
            }
        )
        servers[category]["total_calls"] += total
        servers[category]["main_calls"] += data["main_count"]
        servers[category]["subagent_calls"] += data["sub_count"]

        # Update time bounds for category
        bounds = tool_time_bounds.get(tool_name, (None, None))
        if bounds[0]:
            cur_first = servers[category]["first_used"]
            if cur_first is None or bounds[0] < cur_first:
                servers[category]["first_used"] = bounds[0]
        if bounds[1]:
            cur_last = servers[category]["last_used"]
            if cur_last is None or bounds[1] > cur_last:
                servers[category]["last_used"] = bounds[1]

    # Session counts per category
    for cat_name, cat_tools in BUILTIN_TOOL_CATEGORIES.items():
        if cat_name not in servers:
            continue
        cat_placeholders = ",".join(f":ct{i}" for i in range(len(cat_tools)))
        cat_params: dict = {f"ct{i}": t for i, t in enumerate(cat_tools)}
        cat_conditions = [f"st.tool_name IN ({cat_placeholders})"]
        if project:
            cat_conditions.append("s.project_encoded_name = :project")
            cat_params["project"] = project
        if time_clause:
            cat_conditions.append(time_clause)
            cat_params.update(time_params)
        cat_where = "WHERE " + " AND ".join(cat_conditions)

        sc_row = conn.execute(
            f"""SELECT COUNT(DISTINCT st.session_uuid) as cnt
            FROM session_tools st
            JOIN sessions s ON st.session_uuid = s.uuid
            {cat_where}""",
            cat_params,
        ).fetchone()
        servers[cat_name]["session_count"] = sc_row["cnt"] if sc_row else 0

    # Build result
    server_list = []
    total_tools = 0
    total_calls = 0

    for cat_name, sdata in sorted(servers.items(), key=lambda x: x[1]["total_calls"], reverse=True):
        tools_sorted = sorted(sdata["tools"], key=lambda t: t["calls"], reverse=True)
        total_tools += len(tools_sorted)
        total_calls += sdata["total_calls"]

        server_list.append(
            {
                "name": cat_name,
                "tool_count": len(tools_sorted),
                "total_calls": sdata["total_calls"],
                "session_count": sdata.get("session_count", 0),
                "main_calls": sdata["main_calls"],
                "subagent_calls": sdata["subagent_calls"],
                "first_used": sdata["first_used"],
                "last_used": sdata["last_used"],
                "tools": tools_sorted,
            }
        )

    # Total distinct sessions across all builtin tools
    total_session_row = conn.execute(
        f"""SELECT COUNT(DISTINCT st.session_uuid) as cnt
        FROM session_tools st
        JOIN sessions s ON st.session_uuid = s.uuid
        {where}""",
        params,
    ).fetchone()
    total_sessions = total_session_row["cnt"] if total_session_row else 0

    return {
        "total_servers": len(server_list),
        "total_tools": total_tools,
        "total_calls": total_calls,
        "total_sessions": total_sessions,
        "servers": server_list,
    }


def query_mcp_tools_overview(
    conn: sqlite3.Connection,
    project: Optional[str] = None,
    period: str = "all",
) -> dict:
    """
    Aggregate MCP tool usage across all servers.

    Returns dict with: servers (list of server dicts with nested tools),
    total_servers, total_tools, total_calls, total_sessions.
    """
    from collections import defaultdict

    conditions = ["st.tool_name LIKE 'mcp\\_\\_%' ESCAPE '\\'"]
    params: dict = {}

    if project:
        conditions.append("s.project_encoded_name = :project")
        params["project"] = project

    time_clause, time_params = _mcp_time_filter(period)
    if time_clause:
        conditions.append(time_clause)
        params.update(time_params)

    where = "WHERE " + " AND ".join(conditions)

    # 1. Main session tool usage
    main_rows = conn.execute(
        f"""SELECT
            st.tool_name,
            SUM(st.count) as total_count,
            COUNT(DISTINCT st.session_uuid) as session_count
        FROM session_tools st
        JOIN sessions s ON st.session_uuid = s.uuid
        {where}
        GROUP BY st.tool_name""",
        params,
    ).fetchall()

    # 2. Subagent tool usage
    sub_conditions = ["sat.tool_name LIKE 'mcp\\_\\_%' ESCAPE '\\'"]
    sub_params: dict = {}
    if project:
        sub_conditions.append("s.project_encoded_name = :project")
        sub_params["project"] = project
    sub_time_clause, sub_time_params = _mcp_time_filter(period)
    if sub_time_clause:
        sub_conditions.append(sub_time_clause)
        sub_params.update(sub_time_params)
    sub_where = "WHERE " + " AND ".join(sub_conditions)

    sub_rows = conn.execute(
        f"""SELECT
            sat.tool_name,
            SUM(sat.count) as total_count,
            COUNT(DISTINCT si.session_uuid) as session_count
        FROM subagent_tools sat
        JOIN subagent_invocations si ON sat.invocation_id = si.id
        JOIN sessions s ON si.session_uuid = s.uuid
        {sub_where}
        GROUP BY sat.tool_name""",
        sub_params,
    ).fetchall()

    # 3. Time bounds per server
    time_rows = conn.execute(
        f"""SELECT
            SUBSTR(st.tool_name, 6, INSTR(SUBSTR(st.tool_name, 6), '__') - 1) as server_name,
            MIN(s.start_time) as first_used,
            MAX(s.start_time) as last_used
        FROM session_tools st
        JOIN sessions s ON st.session_uuid = s.uuid
        {where}
        GROUP BY server_name""",
        params,
    ).fetchall()
    time_bounds = {row["server_name"]: (row["first_used"], row["last_used"]) for row in time_rows}

    # Combine into server->tool structure
    tool_data: dict[str, dict] = defaultdict(
        lambda: {
            "main_count": 0,
            "sub_count": 0,
            "main_sessions": 0,
            "sub_sessions": 0,
        }
    )

    for row in main_rows:
        tool_data[row["tool_name"]]["main_count"] = row["total_count"]
        tool_data[row["tool_name"]]["main_sessions"] = row["session_count"]

    for row in sub_rows:
        tool_data[row["tool_name"]]["sub_count"] = row["total_count"]
        tool_data[row["tool_name"]]["sub_sessions"] = row["session_count"]

    # Group by server
    servers: dict[str, dict] = defaultdict(
        lambda: {
            "tools": [],
            "total_calls": 0,
            "main_calls": 0,
            "subagent_calls": 0,
        }
    )

    for full_name, data in tool_data.items():
        parts = full_name.split("__")
        if len(parts) < 3:
            continue
        server_name = parts[1]
        short_name = "__".join(parts[2:])

        total = data["main_count"] + data["sub_count"]
        servers[server_name]["tools"].append(
            {
                "name": short_name,
                "full_name": full_name,
                "calls": total,
                "session_count": data["main_sessions"],
                "main_calls": data["main_count"],
                "subagent_calls": data["sub_count"],
            }
        )
        servers[server_name]["total_calls"] += total
        servers[server_name]["main_calls"] += data["main_count"]
        servers[server_name]["subagent_calls"] += data["sub_count"]

    # Get distinct session count per server
    session_count_rows = conn.execute(
        f"""SELECT
            SUBSTR(st.tool_name, 6, INSTR(SUBSTR(st.tool_name, 6), '__') - 1) as server_name,
            COUNT(DISTINCT st.session_uuid) as session_count
        FROM session_tools st
        JOIN sessions s ON st.session_uuid = s.uuid
        {where}
        GROUP BY server_name""",
        params,
    ).fetchall()
    server_session_counts = {row["server_name"]: row["session_count"] for row in session_count_rows}

    # Build result
    server_list = []
    total_tools = 0
    total_calls = 0

    for server_name, sdata in sorted(
        servers.items(), key=lambda x: x[1]["total_calls"], reverse=True
    ):
        bounds = time_bounds.get(server_name, (None, None))
        tools_sorted = sorted(sdata["tools"], key=lambda t: t["calls"], reverse=True)
        total_tools += len(tools_sorted)
        total_calls += sdata["total_calls"]

        server_list.append(
            {
                "name": server_name,
                "tool_count": len(tools_sorted),
                "total_calls": sdata["total_calls"],
                "session_count": server_session_counts.get(server_name, 0),
                "main_calls": sdata["main_calls"],
                "subagent_calls": sdata["subagent_calls"],
                "first_used": bounds[0],
                "last_used": bounds[1],
                "tools": tools_sorted,
            }
        )

    # Total distinct sessions across all MCP tools
    total_session_row = conn.execute(
        f"""SELECT COUNT(DISTINCT st.session_uuid) as cnt
        FROM session_tools st
        JOIN sessions s ON st.session_uuid = s.uuid
        {where}""",
        params,
    ).fetchone()
    total_sessions = total_session_row["cnt"] if total_session_row else 0

    return {
        "total_servers": len(server_list),
        "total_tools": total_tools,
        "total_calls": total_calls,
        "total_sessions": total_sessions,
        "servers": server_list,
    }


def query_mcp_server_detail(
    conn: sqlite3.Connection,
    server_name: str,
    project: Optional[str] = None,
    period: str = "all",
) -> dict | None:
    """
    Aggregate tool usage for a single MCP server.

    Returns dict with server-level stats and tools list, or None if not found.
    """
    from collections import defaultdict

    like_pattern = f"mcp__{server_name}__%"
    conditions = ["st.tool_name LIKE :pattern"]
    params: dict = {"pattern": like_pattern}

    if project:
        conditions.append("s.project_encoded_name = :project")
        params["project"] = project

    time_clause, time_params = _mcp_time_filter(period)
    if time_clause:
        conditions.append(time_clause)
        params.update(time_params)

    where = "WHERE " + " AND ".join(conditions)

    # Main session tools
    main_rows = conn.execute(
        f"""SELECT st.tool_name, SUM(st.count) as total_count,
            COUNT(DISTINCT st.session_uuid) as session_count
        FROM session_tools st
        JOIN sessions s ON st.session_uuid = s.uuid
        {where}
        GROUP BY st.tool_name""",
        params,
    ).fetchall()

    # Subagent tools
    sub_conditions = ["sat.tool_name LIKE :pattern"]
    sub_params: dict = {"pattern": like_pattern}
    if project:
        sub_conditions.append("s.project_encoded_name = :project")
        sub_params["project"] = project
    sub_time_clause, sub_time_params = _mcp_time_filter(period)
    if sub_time_clause:
        sub_conditions.append(sub_time_clause)
        sub_params.update(sub_time_params)
    sub_where = "WHERE " + " AND ".join(sub_conditions)

    sub_rows = conn.execute(
        f"""SELECT sat.tool_name, SUM(sat.count) as total_count
        FROM subagent_tools sat
        JOIN subagent_invocations si ON sat.invocation_id = si.id
        JOIN sessions s ON si.session_uuid = s.uuid
        {sub_where}
        GROUP BY sat.tool_name""",
        sub_params,
    ).fetchall()

    if not main_rows and not sub_rows:
        return None

    # Combine
    tool_data: dict[str, dict] = defaultdict(lambda: {"main": 0, "sub": 0, "sessions": 0})
    for row in main_rows:
        tool_data[row["tool_name"]]["main"] = row["total_count"]
        tool_data[row["tool_name"]]["sessions"] = row["session_count"]
    for row in sub_rows:
        tool_data[row["tool_name"]]["sub"] = row["total_count"]

    tools = []
    total_calls = 0
    main_calls = 0
    subagent_calls = 0
    for full_name, data in tool_data.items():
        parts = full_name.split("__")
        short_name = "__".join(parts[2:]) if len(parts) > 2 else full_name
        mc = data["main"]
        sc = data["sub"]
        tools.append(
            {
                "name": short_name,
                "full_name": full_name,
                "calls": mc + sc,
                "session_count": data["sessions"],
                "main_calls": mc,
                "subagent_calls": sc,
            }
        )
        total_calls += mc + sc
        main_calls += mc
        subagent_calls += sc

    tools.sort(key=lambda t: t["calls"], reverse=True)

    # Session count and time bounds
    meta_row = conn.execute(
        f"""SELECT COUNT(DISTINCT st.session_uuid) as session_count,
            MIN(s.start_time) as first_used, MAX(s.start_time) as last_used
        FROM session_tools st
        JOIN sessions s ON st.session_uuid = s.uuid
        {where}""",
        params,
    ).fetchone()

    return {
        "name": server_name,
        "tool_count": len(tools),
        "total_calls": total_calls,
        "session_count": meta_row["session_count"] if meta_row else 0,
        "main_calls": main_calls,
        "subagent_calls": subagent_calls,
        "first_used": meta_row["first_used"] if meta_row else None,
        "last_used": meta_row["last_used"] if meta_row else None,
        "tools": tools,
    }


def query_mcp_server_trend(
    conn: sqlite3.Connection,
    server_name: str,
    project: Optional[str] = None,
    period: str = "all",
) -> list[dict]:
    """Daily usage trend for an MCP server. Returns list of {date, calls, sessions}."""
    like_pattern = f"mcp__{server_name}__%"
    conditions = ["st.tool_name LIKE :pattern", "s.start_time IS NOT NULL"]
    params: dict = {"pattern": like_pattern}

    if project:
        conditions.append("s.project_encoded_name = :project")
        params["project"] = project

    time_clause, time_params = _mcp_time_filter(period)
    if time_clause:
        conditions.append(time_clause)
        params.update(time_params)

    where = "WHERE " + " AND ".join(conditions)

    # Main session calls per day
    main_rows = conn.execute(
        f"""SELECT {_tz_date()} as date,
            SUM(st.count) as calls,
            COUNT(DISTINCT st.session_uuid) as sessions
        FROM session_tools st
        JOIN sessions s ON st.session_uuid = s.uuid
        {where}
        GROUP BY {_tz_date()}""",
        params,
    ).fetchall()

    # Subagent calls per day
    sub_conditions = ["sat.tool_name LIKE :pattern"]
    sub_params: dict = {"pattern": like_pattern}
    if project:
        sub_conditions.append("s.project_encoded_name = :project")
        sub_params["project"] = project
    sub_time_clause, sub_time_params = _mcp_time_filter(period)
    if sub_time_clause:
        sub_conditions.append(sub_time_clause)
        sub_params.update(sub_time_params)
    sub_conditions.append("s.start_time IS NOT NULL")
    sub_where = "WHERE " + " AND ".join(sub_conditions)

    sub_rows = conn.execute(
        f"""SELECT {_tz_date()} as date,
            SUM(sat.count) as calls,
            COUNT(DISTINCT si.session_uuid) as sessions
        FROM subagent_tools sat
        JOIN subagent_invocations si ON sat.invocation_id = si.id
        JOIN sessions s ON si.session_uuid = s.uuid
        {sub_where}
        GROUP BY {_tz_date()}""",
        sub_params,
    ).fetchall()

    # Merge main + subagent by date
    date_map: dict = {}
    for row in main_rows:
        d = row["date"]
        date_map[d] = {"main_calls": row["calls"], "sub_calls": 0, "sessions": row["sessions"]}

    for row in sub_rows:
        d = row["date"]
        if d not in date_map:
            date_map[d] = {"main_calls": 0, "sub_calls": 0, "sessions": 0}
        date_map[d]["sub_calls"] = row["calls"]
        # Use max of main/sub session counts (can't union without raw UUIDs)
        date_map[d]["sessions"] = max(date_map[d]["sessions"], row["sessions"])

    return [
        {
            "date": d,
            "calls": date_map[d]["main_calls"] + date_map[d]["sub_calls"],
            "sessions": date_map[d]["sessions"],
            "main_calls": date_map[d]["main_calls"],
            "subagent_calls": date_map[d]["sub_calls"],
        }
        for d in sorted(date_map)
    ]


def query_sessions_by_mcp_server(
    conn: sqlite3.Connection,
    server_name: str,
    project: Optional[str] = None,
    period: str = "all",
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Paginated session list for an MCP server. Returns {sessions, total}."""
    like_pattern = f"mcp__{server_name}__%"
    params: dict = {"pattern": like_pattern}

    # Build conditions for main and subagent queries
    main_conditions = ["st.tool_name LIKE :pattern"]
    sub_conditions = ["sat.tool_name LIKE :pattern"]

    if project:
        main_conditions.append("s.project_encoded_name = :project")
        sub_conditions.append("s.project_encoded_name = :project")
        params["project"] = project

    time_clause, time_params = _mcp_time_filter(period)
    if time_clause:
        main_conditions.append(time_clause)
        sub_conditions.append(time_clause)
        params.update(time_params)

    main_where = "WHERE " + " AND ".join(main_conditions)
    sub_where = "WHERE " + " AND ".join(sub_conditions)

    # CTE: union main + subagent tool usage, then aggregate per session
    cte_sql = f"""
    WITH target_sessions AS (
        -- Main usage
        SELECT
            st.session_uuid,
            1 as has_main,
            0 as has_sub,
            NULL as agent_id
        FROM session_tools st
        JOIN sessions s ON st.session_uuid = s.uuid
        {main_where}

        UNION ALL

        -- Subagent usage
        SELECT
            si.session_uuid,
            0 as has_main,
            1 as has_sub,
            si.agent_id
        FROM subagent_tools sat
        JOIN subagent_invocations si ON sat.invocation_id = si.id
        JOIN sessions s ON si.session_uuid = s.uuid
        {sub_where}
    ),
    aggregated_sessions AS (
        SELECT
            session_uuid,
            MAX(has_main) as has_main,
            MAX(has_sub) as has_sub,
            GROUP_CONCAT(DISTINCT agent_id) as agent_ids
        FROM target_sessions
        GROUP BY session_uuid
    )
    """

    # Total count
    total = conn.execute(
        f"""{cte_sql}
        SELECT COUNT(*) FROM aggregated_sessions""",
        params,
    ).fetchone()[0]

    # Paginated results
    params["limit"] = limit
    params["offset"] = offset

    rows = conn.execute(
        f"""{cte_sql}
        SELECT
            s.uuid, s.slug, s.project_encoded_name, s.project_path,
            s.message_count, s.start_time, s.end_time, s.duration_seconds,
            s.models_used, s.subagent_count, s.initial_prompt,
            s.git_branch, s.session_titles,
            s.session_source, s.source, s.remote_user_id, s.remote_machine_id,
            agg.has_main, agg.has_sub, agg.agent_ids
        FROM sessions s
        JOIN aggregated_sessions agg ON s.uuid = agg.session_uuid
        ORDER BY s.start_time DESC
        LIMIT :limit OFFSET :offset""",
        params,
    ).fetchall()

    sessions = []
    for row in rows:
        session = dict(row)

        # Calculate tool_source
        has_main = session.pop("has_main")
        has_sub = session.pop("has_sub")
        if has_main and has_sub:
            session["tool_source"] = "both"
        elif has_sub:
            session["tool_source"] = "subagent"
        else:
            session["tool_source"] = "main"

        # Parse agent IDs
        agent_ids_str = session.pop("agent_ids")
        session["subagent_agent_ids"] = agent_ids_str.split(",") if agent_ids_str else []

        # Parse JSON fields
        session["models_used"] = _parse_json_list(session.get("models_used"))
        session["session_titles"] = _parse_json_list(session.get("session_titles"))
        session["git_branches"] = [session["git_branch"]] if session.get("git_branch") else []
        sessions.append(session)

    return {"sessions": sessions, "total": total}


def query_mcp_tool_usage_trend(
    conn: sqlite3.Connection,
    project: Optional[str] = None,
    period: str = "month",
) -> dict:
    """
    Aggregate MCP tool usage with daily trend data.

    Returns dict with total, by_item, trend, first_used, last_used
    matching UsageTrendResponse schema.
    """
    from collections import defaultdict
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    cutoff = None
    if period == "week":
        cutoff = now - timedelta(days=7)
    elif period == "month":
        cutoff = now - timedelta(days=30)
    elif period == "quarter":
        cutoff = now - timedelta(days=90)

    conditions = ["st.tool_name LIKE 'mcp\\_\\_%' ESCAPE '\\'"]
    params: dict = {}
    if project:
        conditions.append("s.project_encoded_name = :project")
        params["project"] = project
    if cutoff:
        conditions.append("s.start_time >= :cutoff")
        params["cutoff"] = cutoff.isoformat()

    where = "WHERE " + " AND ".join(conditions)

    # Main session tool counts
    main_rows = conn.execute(
        f"""SELECT st.tool_name, SUM(st.count) as total_count
        FROM session_tools st
        JOIN sessions s ON st.session_uuid = s.uuid
        {where}
        GROUP BY st.tool_name
        ORDER BY total_count DESC""",
        params,
    ).fetchall()

    # Subagent tool counts
    sub_conditions = ["sat.tool_name LIKE 'mcp\\_\\_%' ESCAPE '\\'"]
    sub_params: dict = {}
    if project:
        sub_conditions.append("s.project_encoded_name = :project")
        sub_params["project"] = project
    if cutoff:
        sub_conditions.append("s.start_time >= :cutoff")
        sub_params["cutoff"] = cutoff.isoformat()
    sub_where = "WHERE " + " AND ".join(sub_conditions)

    sub_rows = conn.execute(
        f"""SELECT sat.tool_name, SUM(sat.count) as total_count
        FROM subagent_tools sat
        JOIN subagent_invocations si ON sat.invocation_id = si.id
        JOIN sessions s ON si.session_uuid = s.uuid
        {sub_where}
        GROUP BY sat.tool_name""",
        sub_params,
    ).fetchall()

    # Combine main + sub counts per tool
    tool_counts: dict[str, int] = defaultdict(int)
    for row in main_rows:
        tool_counts[row["tool_name"]] += row["total_count"]
    for row in sub_rows:
        tool_counts[row["tool_name"]] += row["total_count"]

    by_item = dict(sorted(tool_counts.items(), key=lambda x: x[1], reverse=True))
    total = sum(by_item.values())

    # Daily trend
    trend_rows = conn.execute(
        f"""SELECT {_tz_date()} as date, SUM(st.count) as count
        FROM session_tools st
        JOIN sessions s ON st.session_uuid = s.uuid
        {where}
        AND s.start_time IS NOT NULL
        GROUP BY {_tz_date()}
        ORDER BY date""",
        params,
    ).fetchall()

    trend = [{"date": row["date"], "count": row["count"]} for row in trend_rows]

    trend_by_item = _query_per_item_trend(
        conn,
        item_col="st.tool_name",
        from_clause="FROM session_tools st JOIN sessions s ON st.session_uuid = s.uuid",
        where=where,
        params=params,
        count_expr="SUM(st.count)",
    )

    trend_by_user = _query_per_user_trend(
        conn,
        from_clause="FROM session_tools st JOIN sessions s ON st.session_uuid = s.uuid",
        where=where,
        params=params,
        count_expr="SUM(st.count)",
    )
    user_names = _resolve_user_names(conn, [u for u in trend_by_user if u != "_local"])

    # First/last used
    time_row = conn.execute(
        f"""SELECT MIN(s.start_time) as first_used, MAX(s.start_time) as last_used
        FROM session_tools st
        JOIN sessions s ON st.session_uuid = s.uuid
        {where}""",
        params,
    ).fetchone()

    first_used = time_row["first_used"] if time_row else None
    last_used = time_row["last_used"] if time_row else None

    return {
        "total": total,
        "by_item": by_item,
        "trend": trend,
        "trend_by_item": trend_by_item,
        "trend_by_user": trend_by_user,
        "user_names": user_names,
        "first_used": first_used,
        "last_used": last_used,
    }


def query_builtin_tool_usage_trend(
    conn: sqlite3.Connection,
    project: Optional[str] = None,
    period: str = "month",
) -> dict:
    """
    Aggregate built-in tool usage with daily trend data.

    Returns dict with total, by_item, trend, first_used, last_used
    matching UsageTrendResponse schema.
    """
    from collections import defaultdict

    all_builtin_names = list(_BUILTIN_TOOL_TO_CATEGORY.keys())
    placeholders, params = _builtin_tool_placeholders(all_builtin_names, "t")

    conditions = [f"st.tool_name IN ({placeholders})"]
    if project:
        conditions.append("s.project_encoded_name = :project")
        params["project"] = project
    time_clause, time_params = _mcp_time_filter(period)
    if time_clause:
        conditions.append(time_clause)
        params.update(time_params)

    where = "WHERE " + " AND ".join(conditions)

    # Main session tool counts
    main_rows = conn.execute(
        f"""SELECT st.tool_name, SUM(st.count) as total_count
        FROM session_tools st
        JOIN sessions s ON st.session_uuid = s.uuid
        {where}
        GROUP BY st.tool_name
        ORDER BY total_count DESC""",
        params,
    ).fetchall()

    # Subagent tool counts
    sub_placeholders, sub_params = _builtin_tool_placeholders(all_builtin_names, "st")
    sub_conditions = [f"sat.tool_name IN ({sub_placeholders})"]
    if project:
        sub_conditions.append("s.project_encoded_name = :project")
        sub_params["project"] = project
    sub_time_clause, sub_time_params = _mcp_time_filter(period)
    if sub_time_clause:
        sub_conditions.append(sub_time_clause)
        sub_params.update(sub_time_params)
    sub_where = "WHERE " + " AND ".join(sub_conditions)

    sub_rows = conn.execute(
        f"""SELECT sat.tool_name, SUM(sat.count) as total_count
        FROM subagent_tools sat
        JOIN subagent_invocations si ON sat.invocation_id = si.id
        JOIN sessions s ON si.session_uuid = s.uuid
        {sub_where}
        GROUP BY sat.tool_name""",
        sub_params,
    ).fetchall()

    # Combine main + sub counts per tool
    tool_counts: dict[str, int] = defaultdict(int)
    for row in main_rows:
        tool_counts[row["tool_name"]] += row["total_count"]
    for row in sub_rows:
        tool_counts[row["tool_name"]] += row["total_count"]

    by_item = dict(sorted(tool_counts.items(), key=lambda x: x[1], reverse=True))
    total = sum(by_item.values())

    # Daily trend
    trend_rows = conn.execute(
        f"""SELECT {_tz_date()} as date, SUM(st.count) as count
        FROM session_tools st
        JOIN sessions s ON st.session_uuid = s.uuid
        {where}
        AND s.start_time IS NOT NULL
        GROUP BY {_tz_date()}
        ORDER BY date""",
        params,
    ).fetchall()

    trend = [{"date": row["date"], "count": row["count"]} for row in trend_rows]

    trend_by_item = _query_per_item_trend(
        conn,
        item_col="st.tool_name",
        from_clause="FROM session_tools st JOIN sessions s ON st.session_uuid = s.uuid",
        where=where,
        params=params,
        count_expr="SUM(st.count)",
    )

    trend_by_user = _query_per_user_trend(
        conn,
        from_clause="FROM session_tools st JOIN sessions s ON st.session_uuid = s.uuid",
        where=where,
        params=params,
        count_expr="SUM(st.count)",
    )
    user_names = _resolve_user_names(conn, [u for u in trend_by_user if u != "_local"])

    # First/last used
    time_row = conn.execute(
        f"""SELECT MIN(s.start_time) as first_used, MAX(s.start_time) as last_used
        FROM session_tools st
        JOIN sessions s ON st.session_uuid = s.uuid
        {where}""",
        params,
    ).fetchone()

    return {
        "total": total,
        "by_item": by_item,
        "trend": trend,
        "trend_by_item": trend_by_item,
        "trend_by_user": trend_by_user,
        "user_names": user_names,
        "first_used": time_row["first_used"] if time_row else None,
        "last_used": time_row["last_used"] if time_row else None,
    }


def query_mcp_tool_detail(
    conn: sqlite3.Connection,
    server_name: str,
    tool_name: str,
    project: Optional[str] = None,
    period: str = "all",
) -> dict | None:
    """
    Detailed stats for a single MCP tool.

    Returns dict with tool stats and daily trend, or None if not found.
    """
    # Build full tool name: mcp__{server}__{tool}
    full_name = f"mcp__{server_name}__{tool_name}"

    conditions = ["st.tool_name = :full_name"]
    params: dict = {"full_name": full_name}

    if project:
        conditions.append("s.project_encoded_name = :project")
        params["project"] = project

    time_clause, time_params = _mcp_time_filter(period)
    if time_clause:
        conditions.append(time_clause)
        params.update(time_params)

    where = "WHERE " + " AND ".join(conditions)

    # Main session stats
    main_row = conn.execute(
        f"""SELECT COALESCE(SUM(st.count), 0) as total_count,
            COUNT(DISTINCT st.session_uuid) as session_count,
            MIN(s.start_time) as first_used,
            MAX(s.start_time) as last_used
        FROM session_tools st
        JOIN sessions s ON st.session_uuid = s.uuid
        {where}""",
        params,
    ).fetchone()

    # Subagent stats
    sub_conditions = ["sat.tool_name = :full_name"]
    sub_params: dict = {"full_name": full_name}
    if project:
        sub_conditions.append("s.project_encoded_name = :project")
        sub_params["project"] = project
    sub_time_clause, sub_time_params = _mcp_time_filter(period)
    if sub_time_clause:
        sub_conditions.append(sub_time_clause)
        sub_params.update(sub_time_params)
    sub_where = "WHERE " + " AND ".join(sub_conditions)

    sub_row = conn.execute(
        f"""SELECT COALESCE(SUM(sat.count), 0) as total_count
        FROM subagent_tools sat
        JOIN subagent_invocations si ON sat.invocation_id = si.id
        JOIN sessions s ON si.session_uuid = s.uuid
        {sub_where}""",
        sub_params,
    ).fetchone()

    main_calls = main_row["total_count"] or 0 if main_row else 0
    sub_calls = sub_row["total_count"] or 0 if sub_row else 0

    if main_calls == 0 and sub_calls == 0:
        return None

    # Daily trend — main calls
    trend_conditions = list(conditions) + ["s.start_time IS NOT NULL"]
    trend_where = "WHERE " + " AND ".join(trend_conditions)

    trend_rows = conn.execute(
        f"""SELECT {_tz_date()} as date,
            SUM(st.count) as calls,
            COUNT(DISTINCT st.session_uuid) as sessions
        FROM session_tools st
        JOIN sessions s ON st.session_uuid = s.uuid
        {trend_where}
        GROUP BY {_tz_date()}""",
        params,
    ).fetchall()

    # Daily trend — subagent calls
    sub_trend_conditions = list(sub_conditions) + ["s.start_time IS NOT NULL"]
    sub_trend_where = "WHERE " + " AND ".join(sub_trend_conditions)

    sub_trend_rows = conn.execute(
        f"""SELECT {_tz_date()} as date,
            SUM(sat.count) as calls
        FROM subagent_tools sat
        JOIN subagent_invocations si ON sat.invocation_id = si.id
        JOIN sessions s ON si.session_uuid = s.uuid
        {sub_trend_where}
        GROUP BY {_tz_date()}""",
        sub_params,
    ).fetchall()

    # Merge main + subagent trend by date
    trend_map: dict = {}
    for r in trend_rows:
        trend_map[r["date"]] = {"main_calls": r["calls"], "sub_calls": 0, "sessions": r["sessions"]}
    for r in sub_trend_rows:
        d = r["date"]
        if d not in trend_map:
            trend_map[d] = {"main_calls": 0, "sub_calls": 0, "sessions": 0}
        trend_map[d]["sub_calls"] = r["calls"]

    trend = []
    for d in sorted(trend_map):
        m = trend_map[d]
        trend.append(
            {
                "date": d,
                "calls": m["main_calls"] + m["sub_calls"],
                "sessions": m["sessions"],
                "main_calls": m["main_calls"],
                "subagent_calls": m["sub_calls"],
            }
        )

    return {
        "name": tool_name,
        "full_name": full_name,
        "server_name": server_name,
        "main_calls": main_calls,
        "subagent_calls": sub_calls,
        "total_calls": main_calls + sub_calls,
        "session_count": main_row["session_count"] or 0 if main_row else 0,
        "first_used": main_row["first_used"] if main_row else None,
        "last_used": main_row["last_used"] if main_row else None,
        "trend": trend,
    }


def query_sessions_by_mcp_tool(
    conn: sqlite3.Connection,
    full_tool_name: str,
    project: Optional[str] = None,
    period: str = "all",
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Paginated session list for a specific MCP tool. Returns {sessions, total}."""

    # Base WHERE clause components
    conditions = []
    params: dict = {"full_name": full_tool_name}

    if project:
        conditions.append("s.project_encoded_name = :project")
        params["project"] = project

    time_clause, time_params = _mcp_time_filter(period)
    if time_clause:
        conditions.append(time_clause)
        params.update(time_params)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    # Common CTE for main + subagent tool usage union
    # We want sessions that have EITHER main usage OR subagent usage of the tool
    # And we want to know WHICH source(s) apply
    cte_sql = f"""
    WITH target_sessions AS (
        -- Main usage
        SELECT
            st.session_uuid,
            1 as has_main,
            0 as has_sub,
            NULL as agent_id
        FROM session_tools st
        JOIN sessions s ON st.session_uuid = s.uuid
        {where} AND st.tool_name = :full_name

        UNION ALL

        -- Subagent usage
        SELECT
            si.session_uuid,
            0 as has_main,
            1 as has_sub,
            si.agent_id
        FROM subagent_tools sat
        JOIN subagent_invocations si ON sat.invocation_id = si.id
        JOIN sessions s ON si.session_uuid = s.uuid
        {where} AND sat.tool_name = :full_name
    ),
    aggregated_sessions AS (
        SELECT
            session_uuid,
            MAX(has_main) as has_main,
            MAX(has_sub) as has_sub,
            GROUP_CONCAT(DISTINCT agent_id) as agent_ids
        FROM target_sessions
        GROUP BY session_uuid
    )
    """

    # Total count
    total = conn.execute(
        f"""{cte_sql}
        SELECT COUNT(*) FROM aggregated_sessions""",
        params,
    ).fetchone()[0]

    # Paginated results
    params["limit"] = limit
    params["offset"] = offset

    rows = conn.execute(
        f"""{cte_sql}
        SELECT
            s.uuid, s.slug, s.project_encoded_name, s.project_path,
            s.message_count, s.start_time, s.end_time, s.duration_seconds,
            s.models_used, s.subagent_count, s.initial_prompt,
            s.git_branch, s.session_titles,
            s.session_source, s.source, s.remote_user_id, s.remote_machine_id,
            agg.has_main, agg.has_sub, agg.agent_ids
        FROM sessions s
        JOIN aggregated_sessions agg ON s.uuid = agg.session_uuid
        ORDER BY s.start_time DESC
        LIMIT :limit OFFSET :offset""",
        params,
    ).fetchall()

    sessions = []
    for row in rows:
        session = dict(row)

        # Calculate tool_source
        has_main = session.pop("has_main")
        has_sub = session.pop("has_sub")
        if has_main and has_sub:
            session["tool_source"] = "both"
        elif has_sub:
            session["tool_source"] = "subagent"
        else:
            session["tool_source"] = "main"

        # Parse agent IDs
        agent_ids_str = session.pop("agent_ids")
        session["subagent_agent_ids"] = agent_ids_str.split(",") if agent_ids_str else []

        # Parse JSON fields
        session["models_used"] = _parse_json_list(session.get("models_used"))
        session["session_titles"] = _parse_json_list(session.get("session_titles"))
        session["git_branches"] = [session["git_branch"]] if session.get("git_branch") else []
        sessions.append(session)

    return {"sessions": sessions, "total": total}


# ---------------------------------------------------------------------------
# Built-in tool queries
# ---------------------------------------------------------------------------


def _builtin_tool_placeholders(tool_names: list[str], prefix: str = "bt") -> tuple[str, dict]:
    """Build IN-clause placeholders and params for a list of tool names."""
    placeholders = ",".join(f":{prefix}{i}" for i in range(len(tool_names)))
    params = {f"{prefix}{i}": name for i, name in enumerate(tool_names)}
    return placeholders, params


def _builtin_session_rows_to_list(rows: list) -> list[dict]:
    """Convert session rows with has_main/has_sub/agent_ids to session dicts."""
    sessions = []
    for row in rows:
        session = dict(row)
        has_main = session.pop("has_main")
        has_sub = session.pop("has_sub")
        if has_main and has_sub:
            session["tool_source"] = "both"
        elif has_sub:
            session["tool_source"] = "subagent"
        else:
            session["tool_source"] = "main"
        agent_ids_str = session.pop("agent_ids")
        session["subagent_agent_ids"] = agent_ids_str.split(",") if agent_ids_str else []
        session["models_used"] = _parse_json_list(session.get("models_used"))
        session["session_titles"] = _parse_json_list(session.get("session_titles"))
        session["git_branches"] = [session["git_branch"]] if session.get("git_branch") else []
        sessions.append(session)
    return sessions


def query_builtin_server_detail(
    conn: sqlite3.Connection,
    category_name: str,
    project: Optional[str] = None,
    period: str = "all",
) -> dict | None:
    """Aggregate tool usage for a builtin category. Returns same shape as query_mcp_server_detail."""
    from collections import defaultdict

    tool_names = BUILTIN_TOOL_CATEGORIES.get(category_name)
    if not tool_names:
        return None

    placeholders, params = _builtin_tool_placeholders(tool_names)
    conditions = [f"st.tool_name IN ({placeholders})"]

    if project:
        conditions.append("s.project_encoded_name = :project")
        params["project"] = project

    time_clause, time_params = _mcp_time_filter(period)
    if time_clause:
        conditions.append(time_clause)
        params.update(time_params)

    where = "WHERE " + " AND ".join(conditions)

    # Main session tools
    main_rows = conn.execute(
        f"""SELECT st.tool_name, SUM(st.count) as total_count,
            COUNT(DISTINCT st.session_uuid) as session_count
        FROM session_tools st
        JOIN sessions s ON st.session_uuid = s.uuid
        {where}
        GROUP BY st.tool_name""",
        params,
    ).fetchall()

    # Subagent tools
    sub_placeholders, sub_params = _builtin_tool_placeholders(tool_names, "sbt")
    sub_conditions = [f"sat.tool_name IN ({sub_placeholders})"]
    if project:
        sub_conditions.append("s.project_encoded_name = :project")
        sub_params["project"] = project
    sub_time_clause, sub_time_params = _mcp_time_filter(period)
    if sub_time_clause:
        sub_conditions.append(sub_time_clause)
        sub_params.update(sub_time_params)
    sub_where = "WHERE " + " AND ".join(sub_conditions)

    sub_rows = conn.execute(
        f"""SELECT sat.tool_name, SUM(sat.count) as total_count
        FROM subagent_tools sat
        JOIN subagent_invocations si ON sat.invocation_id = si.id
        JOIN sessions s ON si.session_uuid = s.uuid
        {sub_where}
        GROUP BY sat.tool_name""",
        sub_params,
    ).fetchall()

    if not main_rows and not sub_rows:
        return None

    # Combine
    tool_data: dict[str, dict] = defaultdict(lambda: {"main": 0, "sub": 0, "sessions": 0})
    for row in main_rows:
        tool_data[row["tool_name"]]["main"] = row["total_count"]
        tool_data[row["tool_name"]]["sessions"] = row["session_count"]
    for row in sub_rows:
        tool_data[row["tool_name"]]["sub"] = row["total_count"]

    tools = []
    total_calls = 0
    main_calls = 0
    subagent_calls = 0
    for tool_name, data in tool_data.items():
        mc = data["main"]
        sc = data["sub"]
        tools.append(
            {
                "name": tool_name,
                "full_name": tool_name,
                "calls": mc + sc,
                "session_count": data["sessions"],
                "main_calls": mc,
                "subagent_calls": sc,
            }
        )
        total_calls += mc + sc
        main_calls += mc
        subagent_calls += sc

    tools.sort(key=lambda t: t["calls"], reverse=True)

    # Session count and time bounds
    meta_row = conn.execute(
        f"""SELECT COUNT(DISTINCT st.session_uuid) as session_count,
            MIN(s.start_time) as first_used, MAX(s.start_time) as last_used
        FROM session_tools st
        JOIN sessions s ON st.session_uuid = s.uuid
        {where}""",
        params,
    ).fetchone()

    return {
        "name": category_name,
        "tool_count": len(tools),
        "total_calls": total_calls,
        "session_count": meta_row["session_count"] if meta_row else 0,
        "main_calls": main_calls,
        "subagent_calls": subagent_calls,
        "first_used": meta_row["first_used"] if meta_row else None,
        "last_used": meta_row["last_used"] if meta_row else None,
        "tools": tools,
    }


def query_builtin_server_trend(
    conn: sqlite3.Connection,
    category_name: str,
    project: Optional[str] = None,
    period: str = "all",
) -> list[dict]:
    """Daily usage trend for a builtin category. Returns list of {date, calls, sessions, ...}."""
    tool_names = BUILTIN_TOOL_CATEGORIES.get(category_name)
    if not tool_names:
        return []

    placeholders, params = _builtin_tool_placeholders(tool_names)
    conditions = [f"st.tool_name IN ({placeholders})", "s.start_time IS NOT NULL"]

    if project:
        conditions.append("s.project_encoded_name = :project")
        params["project"] = project

    time_clause, time_params = _mcp_time_filter(period)
    if time_clause:
        conditions.append(time_clause)
        params.update(time_params)

    where = "WHERE " + " AND ".join(conditions)

    main_rows = conn.execute(
        f"""SELECT {_tz_date()} as date,
            SUM(st.count) as calls,
            COUNT(DISTINCT st.session_uuid) as sessions
        FROM session_tools st
        JOIN sessions s ON st.session_uuid = s.uuid
        {where}
        GROUP BY {_tz_date()}""",
        params,
    ).fetchall()

    # Subagent calls per day
    sub_placeholders, sub_params = _builtin_tool_placeholders(tool_names, "sbt")
    sub_conditions = [f"sat.tool_name IN ({sub_placeholders})", "s.start_time IS NOT NULL"]
    if project:
        sub_conditions.append("s.project_encoded_name = :project")
        sub_params["project"] = project
    sub_time_clause, sub_time_params = _mcp_time_filter(period)
    if sub_time_clause:
        sub_conditions.append(sub_time_clause)
        sub_params.update(sub_time_params)
    sub_where = "WHERE " + " AND ".join(sub_conditions)

    sub_rows = conn.execute(
        f"""SELECT {_tz_date()} as date,
            SUM(sat.count) as calls,
            COUNT(DISTINCT si.session_uuid) as sessions
        FROM subagent_tools sat
        JOIN subagent_invocations si ON sat.invocation_id = si.id
        JOIN sessions s ON si.session_uuid = s.uuid
        {sub_where}
        GROUP BY {_tz_date()}""",
        sub_params,
    ).fetchall()

    # Merge by date
    date_map: dict = {}
    for row in main_rows:
        d = row["date"]
        date_map[d] = {"main_calls": row["calls"], "sub_calls": 0, "sessions": row["sessions"]}
    for row in sub_rows:
        d = row["date"]
        if d not in date_map:
            date_map[d] = {"main_calls": 0, "sub_calls": 0, "sessions": 0}
        date_map[d]["sub_calls"] = row["calls"]
        date_map[d]["sessions"] = max(date_map[d]["sessions"], row["sessions"])

    return [
        {
            "date": d,
            "calls": date_map[d]["main_calls"] + date_map[d]["sub_calls"],
            "sessions": date_map[d]["sessions"],
            "main_calls": date_map[d]["main_calls"],
            "subagent_calls": date_map[d]["sub_calls"],
        }
        for d in sorted(date_map)
    ]


def query_builtin_tool_detail(
    conn: sqlite3.Connection,
    category_name: str,
    tool_name: str,
    project: Optional[str] = None,
    period: str = "all",
) -> dict | None:
    """Detailed stats for a single builtin tool. Returns same shape as query_mcp_tool_detail."""
    # Verify tool belongs to category
    cat_tools = BUILTIN_TOOL_CATEGORIES.get(category_name, [])
    if tool_name not in cat_tools:
        return None

    conditions = ["st.tool_name = :tool_name"]
    params: dict = {"tool_name": tool_name}

    if project:
        conditions.append("s.project_encoded_name = :project")
        params["project"] = project

    time_clause, time_params = _mcp_time_filter(period)
    if time_clause:
        conditions.append(time_clause)
        params.update(time_params)

    where = "WHERE " + " AND ".join(conditions)

    # Main session stats
    main_row = conn.execute(
        f"""SELECT COALESCE(SUM(st.count), 0) as total_count,
            COUNT(DISTINCT st.session_uuid) as session_count,
            MIN(s.start_time) as first_used,
            MAX(s.start_time) as last_used
        FROM session_tools st
        JOIN sessions s ON st.session_uuid = s.uuid
        {where}""",
        params,
    ).fetchone()

    # Subagent stats
    sub_conditions = ["sat.tool_name = :tool_name"]
    sub_params: dict = {"tool_name": tool_name}
    if project:
        sub_conditions.append("s.project_encoded_name = :project")
        sub_params["project"] = project
    sub_time_clause, sub_time_params = _mcp_time_filter(period)
    if sub_time_clause:
        sub_conditions.append(sub_time_clause)
        sub_params.update(sub_time_params)
    sub_where = "WHERE " + " AND ".join(sub_conditions)

    sub_row = conn.execute(
        f"""SELECT COALESCE(SUM(sat.count), 0) as total_count
        FROM subagent_tools sat
        JOIN subagent_invocations si ON sat.invocation_id = si.id
        JOIN sessions s ON si.session_uuid = s.uuid
        {sub_where}""",
        sub_params,
    ).fetchone()

    main_calls = main_row["total_count"] or 0 if main_row else 0
    sub_calls = sub_row["total_count"] or 0 if sub_row else 0

    if main_calls == 0 and sub_calls == 0:
        return None

    # Daily trend — main
    trend_conditions = list(conditions) + ["s.start_time IS NOT NULL"]
    trend_where = "WHERE " + " AND ".join(trend_conditions)

    trend_rows = conn.execute(
        f"""SELECT {_tz_date()} as date,
            SUM(st.count) as calls,
            COUNT(DISTINCT st.session_uuid) as sessions
        FROM session_tools st
        JOIN sessions s ON st.session_uuid = s.uuid
        {trend_where}
        GROUP BY {_tz_date()}""",
        params,
    ).fetchall()

    # Daily trend — subagent
    sub_trend_conditions = list(sub_conditions) + ["s.start_time IS NOT NULL"]
    sub_trend_where = "WHERE " + " AND ".join(sub_trend_conditions)

    sub_trend_rows = conn.execute(
        f"""SELECT {_tz_date()} as date,
            SUM(sat.count) as calls
        FROM subagent_tools sat
        JOIN subagent_invocations si ON sat.invocation_id = si.id
        JOIN sessions s ON si.session_uuid = s.uuid
        {sub_trend_where}
        GROUP BY {_tz_date()}""",
        sub_params,
    ).fetchall()

    # Merge trend
    trend_map: dict = {}
    for r in trend_rows:
        trend_map[r["date"]] = {"main_calls": r["calls"], "sub_calls": 0, "sessions": r["sessions"]}
    for r in sub_trend_rows:
        d = r["date"]
        if d not in trend_map:
            trend_map[d] = {"main_calls": 0, "sub_calls": 0, "sessions": 0}
        trend_map[d]["sub_calls"] = r["calls"]

    trend = [
        {
            "date": d,
            "calls": trend_map[d]["main_calls"] + trend_map[d]["sub_calls"],
            "sessions": trend_map[d]["sessions"],
            "main_calls": trend_map[d]["main_calls"],
            "subagent_calls": trend_map[d]["sub_calls"],
        }
        for d in sorted(trend_map)
    ]

    return {
        "name": tool_name,
        "full_name": tool_name,
        "server_name": category_name,
        "main_calls": main_calls,
        "subagent_calls": sub_calls,
        "total_calls": main_calls + sub_calls,
        "session_count": main_row["session_count"] or 0 if main_row else 0,
        "first_used": main_row["first_used"] if main_row else None,
        "last_used": main_row["last_used"] if main_row else None,
        "trend": trend,
    }


def query_sessions_by_builtin_server(
    conn: sqlite3.Connection,
    category_name: str,
    project: Optional[str] = None,
    period: str = "all",
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Paginated session list for a builtin category. Returns {sessions, total}."""
    tool_names = BUILTIN_TOOL_CATEGORIES.get(category_name)
    if not tool_names:
        return {"sessions": [], "total": 0}

    placeholders, params = _builtin_tool_placeholders(tool_names)

    main_conditions = [f"st.tool_name IN ({placeholders})"]
    sub_placeholders, sub_extra = _builtin_tool_placeholders(tool_names, "sbt")
    sub_conditions = [f"sat.tool_name IN ({sub_placeholders})"]

    # Merge sub_extra into params (different prefix, no collision)
    params.update(sub_extra)

    if project:
        main_conditions.append("s.project_encoded_name = :project")
        sub_conditions.append("s.project_encoded_name = :project")
        params["project"] = project

    time_clause, time_params = _mcp_time_filter(period)
    if time_clause:
        main_conditions.append(time_clause)
        sub_conditions.append(time_clause)
        params.update(time_params)

    main_where = "WHERE " + " AND ".join(main_conditions)
    sub_where = "WHERE " + " AND ".join(sub_conditions)

    cte_sql = f"""
    WITH target_sessions AS (
        SELECT st.session_uuid, 1 as has_main, 0 as has_sub, NULL as agent_id
        FROM session_tools st
        JOIN sessions s ON st.session_uuid = s.uuid
        {main_where}

        UNION ALL

        SELECT si.session_uuid, 0 as has_main, 1 as has_sub, si.agent_id
        FROM subagent_tools sat
        JOIN subagent_invocations si ON sat.invocation_id = si.id
        JOIN sessions s ON si.session_uuid = s.uuid
        {sub_where}
    ),
    aggregated_sessions AS (
        SELECT session_uuid,
            MAX(has_main) as has_main,
            MAX(has_sub) as has_sub,
            GROUP_CONCAT(DISTINCT agent_id) as agent_ids
        FROM target_sessions
        GROUP BY session_uuid
    )
    """

    total = conn.execute(
        f"""{cte_sql}
        SELECT COUNT(*) FROM aggregated_sessions""",
        params,
    ).fetchone()[0]

    params["limit"] = limit
    params["offset"] = offset

    rows = conn.execute(
        f"""{cte_sql}
        SELECT
            s.uuid, s.slug, s.project_encoded_name, s.project_path,
            s.message_count, s.start_time, s.end_time, s.duration_seconds,
            s.models_used, s.subagent_count, s.initial_prompt,
            s.git_branch, s.session_titles,
            s.session_source, s.source, s.remote_user_id, s.remote_machine_id,
            agg.has_main, agg.has_sub, agg.agent_ids
        FROM sessions s
        JOIN aggregated_sessions agg ON s.uuid = agg.session_uuid
        ORDER BY s.start_time DESC
        LIMIT :limit OFFSET :offset""",
        params,
    ).fetchall()

    return {"sessions": _builtin_session_rows_to_list(rows), "total": total}


def query_sessions_by_builtin_tool(
    conn: sqlite3.Connection,
    tool_name: str,
    project: Optional[str] = None,
    period: str = "all",
    limit: int = 20,
    offset: int = 0,
) -> dict:
    """Paginated session list for a specific builtin tool. Returns {sessions, total}."""
    conditions = []
    params: dict = {"full_name": tool_name}

    if project:
        conditions.append("s.project_encoded_name = :project")
        params["project"] = project

    time_clause, time_params = _mcp_time_filter(period)
    if time_clause:
        conditions.append(time_clause)
        params.update(time_params)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    cte_sql = f"""
    WITH target_sessions AS (
        SELECT st.session_uuid, 1 as has_main, 0 as has_sub, NULL as agent_id
        FROM session_tools st
        JOIN sessions s ON st.session_uuid = s.uuid
        {where} {"AND" if where else "WHERE"} st.tool_name = :full_name

        UNION ALL

        SELECT si.session_uuid, 0 as has_main, 1 as has_sub, si.agent_id
        FROM subagent_tools sat
        JOIN subagent_invocations si ON sat.invocation_id = si.id
        JOIN sessions s ON si.session_uuid = s.uuid
        {where} {"AND" if where else "WHERE"} sat.tool_name = :full_name
    ),
    aggregated_sessions AS (
        SELECT session_uuid,
            MAX(has_main) as has_main,
            MAX(has_sub) as has_sub,
            GROUP_CONCAT(DISTINCT agent_id) as agent_ids
        FROM target_sessions
        GROUP BY session_uuid
    )
    """

    total = conn.execute(
        f"""{cte_sql}
        SELECT COUNT(*) FROM aggregated_sessions""",
        params,
    ).fetchone()[0]

    params["limit"] = limit
    params["offset"] = offset

    rows = conn.execute(
        f"""{cte_sql}
        SELECT
            s.uuid, s.slug, s.project_encoded_name, s.project_path,
            s.message_count, s.start_time, s.end_time, s.duration_seconds,
            s.models_used, s.subagent_count, s.initial_prompt,
            s.git_branch, s.session_titles,
            s.session_source, s.source, s.remote_user_id, s.remote_machine_id,
            agg.has_main, agg.has_sub, agg.agent_ids
        FROM sessions s
        JOIN aggregated_sessions agg ON s.uuid = agg.session_uuid
        ORDER BY s.start_time DESC
        LIMIT :limit OFFSET :offset""",
        params,
    ).fetchall()

    return {"sessions": _builtin_session_rows_to_list(rows), "total": total}


# ---------------------------------------------------------------------------
# Subagent skill/command queries
# ---------------------------------------------------------------------------


def query_subagent_skill_usage(
    conn: sqlite3.Connection,
    project: Optional[str] = None,
    subagent_type: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Aggregate skill usage across subagent invocations."""
    conditions: list[str] = []
    params: dict = {}

    if project:
        conditions.append("s.project_encoded_name = :project")
        params["project"] = project
    if subagent_type:
        conditions.append("si.subagent_type = :subagent_type")
        params["subagent_type"] = subagent_type

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    params["limit"] = limit

    rows = conn.execute(
        f"""SELECT sk.skill_name,
                   SUM(sk.count) as total_count,
                   COUNT(DISTINCT sk.invocation_id) as invocation_count
        FROM subagent_skills sk
        JOIN subagent_invocations si ON sk.invocation_id = si.id
        JOIN sessions s ON si.session_uuid = s.uuid
        {where}
        GROUP BY sk.skill_name
        ORDER BY total_count DESC
        LIMIT :limit""",
        params,
    ).fetchall()
    return [dict(row) for row in rows]


def query_subagent_command_usage(
    conn: sqlite3.Connection,
    project: Optional[str] = None,
    subagent_type: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """Aggregate command usage across subagent invocations."""
    conditions: list[str] = []
    params: dict = {}

    if project:
        conditions.append("s.project_encoded_name = :project")
        params["project"] = project
    if subagent_type:
        conditions.append("si.subagent_type = :subagent_type")
        params["subagent_type"] = subagent_type

    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    params["limit"] = limit

    rows = conn.execute(
        f"""SELECT cmd.command_name,
                   SUM(cmd.count) as total_count,
                   COUNT(DISTINCT cmd.invocation_id) as invocation_count
        FROM subagent_commands cmd
        JOIN subagent_invocations si ON cmd.invocation_id = si.id
        JOIN sessions s ON si.session_uuid = s.uuid
        {where}
        GROUP BY cmd.command_name
        ORDER BY total_count DESC
        LIMIT :limit""",
        params,
    ).fetchall()
    return [dict(row) for row in rows]


# ---------------------------------------------------------------------------
# Parse-once: Session detail & tool breakdown queries
# ---------------------------------------------------------------------------


def query_session_detail(conn: sqlite3.Connection, uuid: str) -> dict | None:
    """
    Fetch all SessionDetail fields available in the DB for a single session.

    Returns a dict ready to be mapped to the SessionDetail schema, or None
    if the session is not in the DB.
    """
    # 1. Core session row
    row = conn.execute(
        """SELECT uuid, slug, project_encoded_name, project_path,
                  message_count, start_time, end_time, duration_seconds,
                  input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens,
                  total_cost, initial_prompt, git_branch, models_used,
                  session_titles, is_continuation_marker, was_compacted,
                  compaction_count, file_snapshot_count, subagent_count,
                  session_source, source, remote_user_id, remote_machine_id,
                  jsonl_mtime
        FROM sessions WHERE uuid = ?""",
        (uuid,),
    ).fetchone()
    if not row:
        return None

    session = dict(row)

    # Parse JSON columns
    session["models_used"] = _parse_json_list(session.get("models_used"))
    session["session_titles"] = _parse_json_list(session.get("session_titles"))

    # Compute derived fields
    input_tokens = session.get("input_tokens") or 0
    cache_read = session.get("cache_read_tokens") or 0
    denom = input_tokens + cache_read
    session["cache_hit_rate"] = cache_read / denom if denom > 0 else 0.0

    git_branch = session.get("git_branch")
    session["git_branches"] = [git_branch] if git_branch else []

    project_path = session.get("project_path") or ""
    session["working_directories"] = [project_path] if project_path else []
    session["project_display_name"] = Path(project_path).name if project_path else None

    # 2. Tool counts
    tool_rows = conn.execute(
        "SELECT tool_name, count FROM session_tools WHERE session_uuid = ?",
        (uuid,),
    ).fetchall()
    session["tools_used"] = {r["tool_name"]: r["count"] for r in tool_rows}

    # 3. Skill usage (with invocation_source)
    skill_rows = conn.execute(
        "SELECT skill_name, invocation_source, count FROM session_skills WHERE session_uuid = ?",
        (uuid,),
    ).fetchall()
    session["skills_used_raw"] = [
        (r["skill_name"], r["invocation_source"], r["count"]) for r in skill_rows
    ]

    # 4. Command usage (with invocation_source)
    cmd_rows = conn.execute(
        "SELECT command_name, invocation_source, count FROM session_commands WHERE session_uuid = ?",
        (uuid,),
    ).fetchall()
    session["commands_used_raw"] = [
        (r["command_name"], r["invocation_source"], r["count"]) for r in cmd_rows
    ]

    # 5. Leaf UUIDs (for project_context_leaf_uuids display)
    leaf_rows = conn.execute(
        "SELECT leaf_uuid FROM session_leaf_refs WHERE session_uuid = ?",
        (uuid,),
    ).fetchall()
    session["project_context_leaf_uuids"] = [r["leaf_uuid"] for r in leaf_rows]

    # 6. Chain detection
    session["has_chain"] = query_session_has_chain(conn, uuid)

    return session


def query_session_tool_breakdown(
    conn: sqlite3.Connection, uuid: str
) -> tuple[dict[str, int] | None, dict[str, int]]:
    """
    Fetch session + subagent tool counts from DB.

    Returns (session_tool_counts, subagent_tool_counts).
    Returns (None, {}) if session not found.
    """
    # Session tools
    session_rows = conn.execute(
        "SELECT tool_name, count FROM session_tools WHERE session_uuid = ?",
        (uuid,),
    ).fetchall()
    session_counts = {r["tool_name"]: r["count"] for r in session_rows}

    # Subagent tools (aggregated across all invocations)
    subagent_rows = conn.execute(
        """SELECT sat.tool_name, SUM(sat.count) as count
        FROM subagent_tools sat
        JOIN subagent_invocations si ON sat.invocation_id = si.id
        WHERE si.session_uuid = ?
        GROUP BY sat.tool_name""",
        (uuid,),
    ).fetchall()
    subagent_counts = {r["tool_name"]: r["count"] for r in subagent_rows}

    # Only check existence when both are empty (distinguish "no tools" from "no session")
    if not session_counts and not subagent_counts:
        exists = conn.execute(
            "SELECT 1 FROM sessions WHERE uuid = ?", (uuid,)
        ).fetchone()
        if not exists:
            return None, {}

    return session_counts, subagent_counts
