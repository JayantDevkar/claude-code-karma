"""karma search — find sessions by branch, date, keyword, skill."""
import sqlite3

import click

from . import db as _db
from .formatters import format_for_claude, format_table


def _query_sessions(
    conn: sqlite3.Connection,
    branch: str | None = None,
    date: str | None = None,
    keyword: str | None = None,
    skill: str | None = None,
    limit: int = 50,
) -> list[dict]:
    """Query sessions from SQLite with optional filters."""
    conditions = []
    params = {}

    if branch:
        conditions.append("s.git_branch LIKE :branch")
        params["branch"] = f"%{branch}%"

    if date:
        conditions.append("s.start_time LIKE :date")
        params["date"] = f"{date}%"

    if keyword:
        conditions.append(
            "s.uuid IN ("
            "SELECT uuid FROM sessions_fts WHERE sessions_fts MATCH :keyword"
            ")"
        )
        params["keyword"] = keyword

    if skill:
        conditions.append(
            "s.uuid IN ("
            "SELECT session_uuid FROM session_skills WHERE skill_name LIKE :skill"
            ")"
        )
        params["skill"] = f"%{skill}%"

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    query = f"""
        SELECT s.uuid, s.slug, s.git_branch, s.project_encoded_name,
               s.project_path, s.start_time, s.end_time,
               s.duration_seconds, s.message_count, s.total_cost,
               s.initial_prompt, s.session_titles, s.input_tokens,
               s.output_tokens
        FROM sessions s
        {where}
        ORDER BY s.start_time DESC
        LIMIT :limit
    """
    params["limit"] = limit

    rows = conn.execute(query, params).fetchall()
    sessions = [dict(row) for row in rows]

    uuids = [s["uuid"] for s in sessions]
    if uuids:
        _enrich_skills(conn, sessions)
        _enrich_tools(conn, sessions)

    return sessions


def _enrich_skills(conn: sqlite3.Connection, sessions: list[dict]) -> None:
    """Add aggregated skill names to each session dict."""
    uuid_map = {s["uuid"]: s for s in sessions}
    placeholders = ",".join("?" for _ in uuid_map)
    rows = conn.execute(
        f"SELECT session_uuid, skill_name, count FROM session_skills "
        f"WHERE session_uuid IN ({placeholders})",
        list(uuid_map.keys()),
    ).fetchall()

    skills_by_uuid: dict[str, list[str]] = {}
    for row in rows:
        skills_by_uuid.setdefault(row["session_uuid"], []).append(row["skill_name"])

    for s in sessions:
        s["skills"] = ", ".join(skills_by_uuid.get(s["uuid"], []))


def _enrich_tools(conn: sqlite3.Connection, sessions: list[dict]) -> None:
    """Add aggregated tool usage to each session dict."""
    uuid_map = {s["uuid"]: s for s in sessions}
    placeholders = ",".join("?" for _ in uuid_map)
    rows = conn.execute(
        f"SELECT session_uuid, tool_name, count FROM session_tools "
        f"WHERE session_uuid IN ({placeholders})",
        list(uuid_map.keys()),
    ).fetchall()

    tools_by_uuid: dict[str, list[str]] = {}
    for row in rows:
        tools_by_uuid.setdefault(row["session_uuid"], []).append(
            f"{row['tool_name']}({row['count']})"
        )

    for s in sessions:
        s["tools"] = ", ".join(tools_by_uuid.get(s["uuid"], []))


@click.command()
@click.option("--branch", "-b", help="Filter by git branch (partial match)")
@click.option("--date", "-d", help="Filter by date (YYYY-MM-DD)")
@click.option("--keyword", "-k", help="Full-text search in prompts and titles")
@click.option("--skill", "-s", help="Filter by skill name (partial match)")
@click.option("--limit", "-l", default=50, help="Max results (default: 50)")
@click.option("--for-claude", is_flag=True, help="Output structured markdown for Claude Code")
def search(branch, date, keyword, skill, limit, for_claude):
    """Search Claude Code sessions by branch, date, keyword, or skill."""
    conn = _db.get_read_connection(_db.DB_PATH)
    try:
        sessions = _query_sessions(conn, branch, date, keyword, skill, limit)
        if for_claude:
            click.echo(format_for_claude(sessions))
        else:
            click.echo(format_table(sessions))
    finally:
        conn.close()
