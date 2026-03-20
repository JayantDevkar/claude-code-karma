"""karma sessions — get session details and content."""
import subprocess
import sys
from pathlib import Path

import click

from . import db as _db
from .formatters import format_for_claude, format_table


CLEAN_SCRIPT = Path.home() / ".claude" / "skills" / "session-summary" / "add" / "scripts" / "clean-session.py"


def _find_session(conn, uuid_prefix: str) -> dict | None:
    """Find a session by exact or prefix UUID match."""
    row = conn.execute(
        "SELECT * FROM sessions WHERE uuid = ?", (uuid_prefix,)
    ).fetchone()

    if not row:
        row = conn.execute(
            "SELECT * FROM sessions WHERE uuid LIKE ?", (f"{uuid_prefix}%",)
        ).fetchone()

    if not row:
        return None

    session = dict(row)

    skills = conn.execute(
        "SELECT skill_name FROM session_skills WHERE session_uuid = ?",
        (session["uuid"],),
    ).fetchall()
    session["skills"] = ", ".join(r["skill_name"] for r in skills)

    tools = conn.execute(
        "SELECT tool_name, count FROM session_tools WHERE session_uuid = ?",
        (session["uuid"],),
    ).fetchall()
    session["tools"] = ", ".join(f"{r['tool_name']}({r['count']})" for r in tools)

    return session


def _get_clean_content(session: dict) -> str | None:
    """Get cleaned session content using clean-session.py."""
    if not CLEAN_SCRIPT.exists():
        return None

    projects_dir = Path.home() / ".claude" / "projects" / session["project_encoded_name"]
    if not projects_dir.exists():
        return None

    try:
        result = subprocess.run(
            [
                sys.executable,
                str(CLEAN_SCRIPT),
                "--session", session["uuid"],
                "--projects-dir", str(projects_dir),
                "--format", "md",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        pass

    return None


@click.group()
def sessions():
    """Session details and content retrieval."""
    pass


@sessions.command()
@click.argument("uuid")
@click.option("--content", is_flag=True, help="Include cleaned conversation content")
@click.option("--for-claude", is_flag=True, help="Output structured markdown for Claude Code")
def get(uuid, content, for_claude):
    """Get details of a specific session by UUID (or prefix)."""
    conn = _db.get_read_connection()
    try:
        session = _find_session(conn, uuid)
        if not session:
            click.echo(f"Session not found for UUID: {uuid}")
            return

        if for_claude:
            output = format_for_claude([session])
        else:
            output = format_table([session])

        click.echo(output)

        if content:
            click.echo("\n---\n")
            clean = _get_clean_content(session)
            if clean:
                click.echo(clean)
            else:
                click.echo(
                    "Could not retrieve session content. "
                    "Make sure clean-session.py is available."
                )
    finally:
        conn.close()
