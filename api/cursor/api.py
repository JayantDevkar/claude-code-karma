"""
Service-layer helpers that surface Cursor data through claude-karma's existing
response schemas.

Each function reads from the indexed `metadata.db` (NOT from Cursor's
state.vscdb directly) — the indexer is the boundary. Routers call these
helpers when `sessions.session_source = 'cursor'` is detected.
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_EPOCH_UTC = datetime.fromtimestamp(0, tz=timezone.utc)

logger = logging.getLogger(__name__)


# =============================================================================
# Detection helpers (routers use these to dispatch)
# =============================================================================


def get_session_source(conn: sqlite3.Connection, uuid: str) -> str | None:
    """Return 'cursor' / 'claude_code' / 'desktop' / None for a session UUID."""
    row = conn.execute(
        "SELECT session_source FROM sessions WHERE uuid = ?", (uuid,)
    ).fetchone()
    return row[0] if row else None


def is_cursor_project_encoded_name(encoded_name: str) -> bool:
    """True if a URL `encoded_name` parameter targets a Cursor workspace."""
    return encoded_name.startswith("cursor:")


# =============================================================================
# Project surface
# =============================================================================


def list_cursor_projects(conn: sqlite3.Connection) -> list[dict]:
    """
    Return raw project dicts for every Cursor workspace with at least one session.

    Each dict has the keys needed by `ProjectSummary`. Router merges these
    with Claude Code projects.
    """
    rows = conn.execute(
        """
        SELECT p.encoded_name, p.project_path, p.slug, p.display_name,
               p.session_count, p.last_activity
        FROM projects p
        WHERE p.encoded_name LIKE 'cursor:%'
        """
    ).fetchall()
    return [
        {
            "path": row[1] or row[0],
            "encoded_name": row[0],
            "slug": row[2],
            "display_name": row[3],
            "session_count": row[4] or 0,
            "agent_count": 0,
            "exists": True,
            "is_git_repository": False,
            "git_root_path": None,
            "is_nested_project": False,
            "latest_session_time": _parse_iso(row[5]),
            "session_source": "cursor",
        }
        for row in rows
    ]


def get_cursor_project_detail(
    conn: sqlite3.Connection, encoded_name: str
) -> dict | None:
    """Build a ProjectDetail-shaped dict for one Cursor workspace, or None."""
    if not is_cursor_project_encoded_name(encoded_name):
        return None
    row = conn.execute(
        "SELECT encoded_name, project_path, slug, display_name, session_count, last_activity "
        "FROM projects WHERE encoded_name = ?",
        (encoded_name,),
    ).fetchone()
    if not row:
        return None

    sessions = list_cursor_sessions_for_project(conn, encoded_name)
    return {
        "path": row[1] or row[0],
        "encoded_name": row[0],
        "slug": row[2],
        "display_name": row[3],
        "session_count": row[4] or 0,
        "agent_count": 0,
        "exists": True,
        "is_git_repository": False,
        "git_root_path": None,
        "is_nested_project": False,
        "latest_session_time": _parse_iso(row[5]),
        "session_source": "cursor",
        "sessions": sessions,
    }


def list_cursor_sessions_for_project(
    conn: sqlite3.Connection, encoded_name: str
) -> list[dict]:
    """Return SessionSummary-shaped dicts for every Cursor session in a workspace."""
    rows = conn.execute(
        """
        SELECT s.uuid, s.slug, s.project_encoded_name, s.project_path,
               s.message_count, s.start_time, s.end_time, s.duration_seconds,
               s.models_used, s.subagent_count, s.initial_prompt,
               s.session_titles, s.session_source
        FROM sessions s
        WHERE s.project_encoded_name = ?
        ORDER BY s.start_time DESC NULLS LAST
        """,
        (encoded_name,),
    ).fetchall()
    return [_row_to_session_summary(r) for r in rows]


# =============================================================================
# Session surface
# =============================================================================


def get_cursor_session_summary(
    conn: sqlite3.Connection, uuid: str
) -> dict | None:
    """Return a SessionSummary-shaped dict for a Cursor session, or None."""
    row = conn.execute(
        """
        SELECT s.uuid, s.slug, s.project_encoded_name, s.project_path,
               s.message_count, s.start_time, s.end_time, s.duration_seconds,
               s.models_used, s.subagent_count, s.initial_prompt,
               s.session_titles, s.session_source
        FROM sessions s
        WHERE s.uuid = ? AND s.session_source = 'cursor'
        """,
        (uuid,),
    ).fetchone()
    if not row:
        return None
    return _row_to_session_summary(row)


def get_cursor_session_detail(
    conn: sqlite3.Connection, uuid: str
) -> dict | None:
    """
    Return a SessionDetail-shaped dict for a Cursor session, or None.

    Populates core fields. Claude-Code-only fields (compaction events,
    file_snapshot_count, chain refs, project_context_summaries) default
    to their schema defaults — Cursor has no equivalent.
    """
    base = get_cursor_session_summary(conn, uuid)
    if base is None:
        return None
    meta_row = conn.execute(
        "SELECT * FROM cursor_session_meta WHERE session_uuid = ?", (uuid,)
    ).fetchone()
    meta = dict(meta_row) if meta_row else {}

    tools_used = _build_tools_used(conn, uuid)

    detail = dict(base)
    detail.update(
        {
            "initial_prompt_images": [],
            "tools_used": tools_used,
            "git_branches": [meta["created_on_branch"]] if meta.get("created_on_branch") else [],
            "working_directories": [base["path"]] if base.get("path") else [],
            "total_input_tokens": meta.get("context_tokens_used") or 0,
            "total_output_tokens": 0,
            "cache_hit_rate": 0.0,
            "total_cost": 0.0,
            "todos": _parse_json_list(meta.get("todos_json")),
            "tasks": [],
            "has_tasks": False,
            "has_chain": False,
            "is_continuation_marker": False,
            "file_snapshot_count": 0,
            "project_context_summaries": [],
            "project_context_leaf_uuids": [],
            "session_titles": base.get("session_titles") or [],
            "was_compacted": False,
            "compaction_summary_count": 0,
            "compaction_summaries": [],
            "message_type_breakdown": _build_message_type_breakdown(conn, uuid),
            "skills_used": [],
            "skills_mentioned": [],
            "commands_used": [],
        }
    )
    return detail


def get_cursor_session_timeline(
    conn: sqlite3.Connection, uuid: str
) -> list[dict]:
    """Return TimelineEvent-shaped dicts in conversation order."""
    rows = conn.execute(
        """
        SELECT bubble_id, seq, bubble_type, capability_type, created_at_ms,
               has_thinking, thinking_duration_ms, has_tool_call,
               text_preview, text_full
        FROM cursor_bubble
        WHERE session_uuid = ?
        ORDER BY seq ASC
        """,
        (uuid,),
    ).fetchall()
    events: list[dict] = []
    for row in rows:
        event_type = _timeline_event_type(row[2], row[3])
        events.append(
            {
                "event_type": event_type,
                "timestamp": _ms_to_dt(row[4]),
                "uuid": row[0],
                "content": (row[9] or row[8] or "") if not row[7] else None,
                "tool_name": None,
                "tool_use_id": None,
                "metadata": {
                    "seq": row[1],
                    "bubble_type": row[2],
                    "capability_type": row[3],
                    "has_thinking": bool(row[5]),
                    "thinking_duration_ms": row[6],
                },
            }
        )
    return events


def get_cursor_session_tools(
    conn: sqlite3.Connection, uuid: str
) -> list[dict]:
    """Return ToolUsageSummary-shaped dicts for tool calls in a Cursor session."""
    rows = conn.execute(
        """
        SELECT tool_name, count FROM session_tools
        WHERE session_uuid = ? AND invocation_source = 'cursor'
        ORDER BY count DESC
        """,
        (uuid,),
    ).fetchall()
    return [
        {
            "tool_name": row[0],
            "call_count": row[1],
            "total_input_tokens": 0,
            "total_output_tokens": 0,
        }
        for row in rows
    ]


def get_cursor_session_file_activity(
    conn: sqlite3.Connection, uuid: str
) -> list[dict]:
    """Return FileActivity-shaped dicts from cursor_tool_call rows."""
    rows = conn.execute(
        """
        SELECT tool_name, file_path, status, created_at_ms
        FROM cursor_tool_call
        WHERE session_uuid = ? AND file_path IS NOT NULL
        ORDER BY created_at_ms ASC NULLS LAST
        """,
        (uuid,),
    ).fetchall()
    return [
        {
            "path": row[1],
            "operation": _classify_file_op(row[0]),
            "tool_name": row[0],
            "timestamp": _ms_to_dt(row[3]),
            "actor": "session",
            "actor_type": "session",
            "status": row[2],
        }
        for row in rows
    ]


def get_cursor_session_initial_prompt(
    conn: sqlite3.Connection, uuid: str
) -> str | None:
    """Return the first user bubble's text as the initial prompt."""
    row = conn.execute(
        "SELECT initial_prompt FROM sessions WHERE uuid = ? AND session_source = 'cursor'",
        (uuid,),
    ).fetchone()
    return row[0] if row else None


# =============================================================================
# Plans surface
# =============================================================================


def list_cursor_plan_summaries(conn: sqlite3.Connection) -> list[dict]:
    """Return PlanSummary-shaped dicts for all Cursor plans in metadata.db."""
    rows = conn.execute(
        """
        SELECT slug, name, overview, body_md, file_mtime_ms
        FROM cursor_plan
        ORDER BY file_mtime_ms DESC
        """
    ).fetchall()
    return [_plan_row_to_summary(r) for r in rows]


def get_cursor_plan_detail(conn: sqlite3.Connection, slug: str) -> dict | None:
    """Return PlanDetail-shaped dict for a single Cursor plan, or None."""
    row = conn.execute(
        """
        SELECT slug, name, overview, body_md, file_mtime_ms
        FROM cursor_plan WHERE slug = ?
        """,
        (slug,),
    ).fetchone()
    if not row:
        return None
    base = _plan_row_to_summary(row)
    body_md = row[3] or ""
    return {**base, "content": body_md}


def _plan_row_to_summary(row) -> dict:
    if isinstance(row, sqlite3.Row):
        row = tuple(row)
    slug, name, overview, body_md, file_mtime_ms = row
    body_md = body_md or ""
    preview = (overview or body_md)[:500] if (overview or body_md) else ""
    word_count = len((body_md or "").split())
    mtime_dt = _ms_to_dt(file_mtime_ms) or _EPOCH_UTC
    return {
        "slug": slug,
        "title": name,
        "preview": preview,
        "word_count": word_count,
        "created": mtime_dt,
        "modified": mtime_dt,
        "size_bytes": len((body_md or "").encode("utf-8")),
    }


# =============================================================================
# MCP overview surface
# =============================================================================


def list_cursor_mcp_servers_with_tools(conn: sqlite3.Connection) -> list[dict]:
    """
    Build MCP server summaries for the /tools overview.

    Aggregates unique server identifiers across workspaces, joining tool
    descriptors and tool call counts from `session_tools`.
    """
    server_rows = conn.execute(
        """
        SELECT server_identifier, MIN(server_name) AS server_name, MIN(source) AS source
        FROM cursor_mcp_server
        GROUP BY server_identifier
        """
    ).fetchall()
    servers: list[dict] = []
    for row in server_rows:
        server_id = row[0]
        server_name = row[1] or server_id
        source = row[2] or "user"
        tool_rows = conn.execute(
            """
            SELECT tool_name, MIN(description) AS description, MIN(arguments_json) AS arguments_json
            FROM cursor_mcp_tool
            WHERE server_identifier = ?
            GROUP BY tool_name
            """,
            (server_id,),
        ).fetchall()
        tools = []
        for tr in tool_rows:
            tool_name = tr[0]
            full_name = f"mcp__{server_id}__{tool_name}"
            call_count_row = conn.execute(
                "SELECT COALESCE(SUM(count), 0), COUNT(DISTINCT session_uuid) "
                "FROM session_tools WHERE tool_name = ? AND invocation_source = 'cursor'",
                (full_name,),
            ).fetchone()
            calls = call_count_row[0] or 0
            session_count = call_count_row[1] or 0
            arguments_schema = None
            if tr[2]:
                try:
                    arguments_schema = json.loads(tr[2])
                except (json.JSONDecodeError, TypeError):
                    arguments_schema = None
            tools.append(
                {
                    "name": tool_name,
                    "full_name": full_name,
                    "server_name": server_id,
                    "server_display_name": server_name,
                    "description": tr[1],
                    "calls": calls,
                    "session_count": session_count,
                    "main_calls": 0,
                    "subagent_calls": 0,
                    "arguments_schema": arguments_schema,
                }
            )
        servers.append(
            {
                "name": server_id,
                "display_name": server_name,
                "source": source,
                "tools": tools,
                "tool_count": len(tools),
                "total_calls": sum(t["calls"] for t in tools),
            }
        )
    return servers


# =============================================================================
# Skills surface (listing only — Cursor has no invocation telemetry)
# =============================================================================


def list_cursor_skill_items() -> list[dict]:
    """Return SkillItem-shaped dicts for every Cursor skill on disk."""
    from cursor.skills import iter_cursor_skills

    out: list[dict] = []
    for skill in iter_cursor_skills():
        out.append(
            {
                "name": skill.name,
                "path": f"cursor:{skill.name}",
                "type": "file",
                "size_bytes": None,
                "modified_at": skill.modified_at,
                "source": "cursor",
                "description": skill.description,
                "tracking_unavailable": True,
            }
        )
    return out


# =============================================================================
# Agents surface (built-in inventory only — Cursor has no custom-agent system)
# =============================================================================


def list_cursor_builtin_agent_summaries() -> list[dict]:
    """Return AgentSummary-shaped dicts for Cursor's built-in agent modes."""
    from cursor.agents import list_cursor_builtin_agents

    now = datetime.now(tz=timezone.utc)
    return [
        {
            "name": a.name,
            "size_bytes": 0,
            "modified_at": now,
        }
        for a in list_cursor_builtin_agents()
    ]


# =============================================================================
# Analytics surface (per-project, basic rollup)
# =============================================================================


def get_cursor_project_analytics(
    conn: sqlite3.Connection, encoded_name: str
) -> dict | None:
    """
    Build a minimal analytics blob for one Cursor workspace.

    Compatible with the existing ProjectAnalytics shape — populates totals
    + sessions_by_date + model_usage + tool_usage. Cost/cache_hit stay 0
    (Cursor doesn't expose per-bubble token costs).
    """
    if not is_cursor_project_encoded_name(encoded_name):
        return None

    totals = conn.execute(
        """
        SELECT
            COUNT(*) AS session_count,
            COALESCE(SUM(message_count), 0) AS total_messages,
            COALESCE(SUM(input_tokens), 0) AS total_input_tokens,
            COALESCE(SUM(output_tokens), 0) AS total_output_tokens,
            COALESCE(SUM(duration_seconds), 0) AS total_duration_seconds,
            COALESCE(SUM(subagent_count), 0) AS subagent_count
        FROM sessions
        WHERE project_encoded_name = ?
        """,
        (encoded_name,),
    ).fetchone()

    sessions_by_date_rows = conn.execute(
        """
        SELECT DATE(start_time) AS day, COUNT(*) AS n
        FROM sessions
        WHERE project_encoded_name = ? AND start_time IS NOT NULL
        GROUP BY day
        ORDER BY day
        """,
        (encoded_name,),
    ).fetchall()

    model_usage_rows = conn.execute(
        """
        SELECT csm.model_name, COUNT(*) AS sessions
        FROM cursor_session_meta csm
        JOIN sessions s ON s.uuid = csm.session_uuid
        WHERE s.project_encoded_name = ? AND csm.model_name IS NOT NULL
        GROUP BY csm.model_name
        """,
        (encoded_name,),
    ).fetchall()

    tool_usage_rows = conn.execute(
        """
        SELECT st.tool_name, COALESCE(SUM(st.count), 0) AS calls
        FROM session_tools st
        JOIN sessions s ON s.uuid = st.session_uuid
        WHERE s.project_encoded_name = ? AND st.invocation_source = 'cursor'
        GROUP BY st.tool_name
        ORDER BY calls DESC
        """,
        (encoded_name,),
    ).fetchall()

    return {
        "encoded_name": encoded_name,
        "session_source": "cursor",
        "totals": {
            "session_count": totals[0] or 0,
            "total_messages": totals[1] or 0,
            "total_input_tokens": totals[2] or 0,
            "total_output_tokens": totals[3] or 0,
            "total_duration_seconds": totals[4] or 0,
            "subagent_count": totals[5] or 0,
            "total_cost": 0.0,
            "cache_hit_rate": 0.0,
        },
        "sessions_by_date": [
            {"date": r[0], "count": r[1]} for r in sessions_by_date_rows
        ],
        "model_usage": [
            {"model": r[0], "sessions": r[1]} for r in model_usage_rows
        ],
        "tool_usage": [
            {"tool_name": r[0], "calls": r[1]} for r in tool_usage_rows
        ],
    }


# =============================================================================
# Internal helpers
# =============================================================================


def _row_to_session_summary(row: sqlite3.Row | tuple) -> dict:
    if isinstance(row, sqlite3.Row):
        row = tuple(row)
    return {
        "uuid": row[0],
        "slug": row[1],
        "project_encoded_name": row[2],
        "project_slug": row[2],
        "project_display_name": Path(row[3]).name if row[3] else None,
        "path": row[3],
        "message_count": row[4] or 0,
        "start_time": _parse_iso(row[5]),
        "end_time": _parse_iso(row[6]),
        "duration_seconds": row[7],
        "models_used": _parse_json_list(row[8]),
        "subagent_count": row[9] or 0,
        "has_todos": False,
        "todo_count": 0,
        "initial_prompt": row[10],
        "summary": None,
        "git_branches": [],
        "chain_info": None,
        "session_titles": _parse_json_list(row[11]),
        "chain_title": None,
        "tool_source": None,
        "subagent_agent_ids": [],
        "invocation_sources": [],
        "session_source": row[12] or "cursor",
    }


def _build_tools_used(conn: sqlite3.Connection, uuid: str) -> dict[str, int]:
    rows = conn.execute(
        "SELECT tool_name, count FROM session_tools "
        "WHERE session_uuid = ? AND invocation_source = 'cursor'",
        (uuid,),
    ).fetchall()
    return {row[0]: row[1] for row in rows}


def _build_message_type_breakdown(
    conn: sqlite3.Connection, uuid: str
) -> dict[str, int]:
    rows = conn.execute(
        "SELECT bubble_type, COUNT(*) FROM cursor_bubble "
        "WHERE session_uuid = ? GROUP BY bubble_type",
        (uuid,),
    ).fetchall()
    out: dict[str, int] = {}
    for row in rows:
        label = "user" if row[0] == 1 else "assistant" if row[0] == 2 else f"type_{row[0]}"
        out[label] = row[1]
    return out


def _timeline_event_type(bubble_type: int, capability_type: int | None) -> str:
    if bubble_type == 1:
        return "user_message"
    if bubble_type == 2:
        if capability_type == 15:
            return "tool_call"
        if capability_type == 30:
            return "thinking"
        return "assistant_message"
    return "unknown"


def _classify_file_op(tool_name: str) -> str:
    n = (tool_name or "").lower()
    if "edit" in n or "write" in n or "create" in n or "replace" in n:
        return "edit"
    if "delete" in n:
        return "delete"
    if "list" in n or "glob" in n or "grep" in n or "search" in n:
        return "search"
    return "read"


def _parse_iso(val: Any) -> datetime | None:
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _ms_to_dt(ms: int | None) -> datetime | None:
    if ms is None or ms <= 0:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def _parse_json_list(val: Any) -> list:
    if not val:
        return []
    if isinstance(val, list):
        return val
    try:
        result = json.loads(val)
        return result if isinstance(result, list) else []
    except (json.JSONDecodeError, TypeError):
        return []
