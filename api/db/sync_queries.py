"""Sync CRUD functions for teams, members, projects, and events.

All functions take a raw sqlite3.Connection. The API wraps them with
run_in_executor for async. The CLI calls them directly.
"""

import json
import sqlite3
from typing import Optional


# ── Teams ──────────────────────────────────────────────────────────────


def create_team(
    conn: sqlite3.Connection,
    name: str,
    backend: str = "syncthing",
    join_code: Optional[str] = None,
) -> dict:
    conn.execute(
        "INSERT INTO sync_teams (name, backend, join_code) VALUES (?, ?, ?)",
        (name, backend, join_code),
    )
    conn.commit()
    return {"name": name, "backend": backend, "join_code": join_code}


def delete_team(conn: sqlite3.Connection, name: str) -> None:
    conn.execute("DELETE FROM sync_teams WHERE name = ?", (name,))
    conn.commit()


def list_teams(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT t.name, t.backend, t.join_code, t.created_at, t.sync_session_limit,
                  (SELECT COUNT(*) FROM sync_members m WHERE m.team_name = t.name) as member_count,
                  (SELECT COUNT(*) FROM sync_team_projects p WHERE p.team_name = t.name) as project_count
           FROM sync_teams t ORDER BY t.created_at"""
    ).fetchall()
    return [dict(r) for r in rows]


def get_team(conn: sqlite3.Connection, name: str) -> Optional[dict]:
    row = conn.execute(
        """SELECT t.name, t.backend, t.join_code, t.created_at, t.sync_session_limit,
                  (SELECT COUNT(*) FROM sync_members m WHERE m.team_name = t.name) as member_count,
                  (SELECT COUNT(*) FROM sync_team_projects p WHERE p.team_name = t.name) as project_count
           FROM sync_teams t WHERE t.name = ?""",
        (name,),
    ).fetchone()
    return dict(row) if row else None


def update_team_session_limit(
    conn: sqlite3.Connection,
    team_name: str,
    limit: str,
) -> None:
    """Update the sync session limit for a team.

    Valid values: 'all', 'recent_100', 'recent_10'.
    """
    conn.execute(
        "UPDATE sync_teams SET sync_session_limit = ? WHERE name = ?",
        (limit, team_name),
    )
    conn.commit()


# ── Members ────────────────────────────────────────────────────────────


def add_member(
    conn: sqlite3.Connection,
    team_name: str,
    name: str,
    device_id: str,
) -> dict:
    conn.execute(
        "INSERT INTO sync_members (team_name, name, device_id) VALUES (?, ?, ?)",
        (team_name, name, device_id),
    )
    conn.commit()
    return {"team_name": team_name, "name": name, "device_id": device_id}


def upsert_member(
    conn: sqlite3.Connection,
    team_name: str,
    name: str,
    device_id: str,
) -> dict:
    """Insert a member or update their name if the device already exists."""
    conn.execute(
        """INSERT INTO sync_members (team_name, name, device_id)
           VALUES (?, ?, ?)
           ON CONFLICT(team_name, device_id)
           DO UPDATE SET name = excluded.name""",
        (team_name, name, device_id),
    )
    conn.commit()
    return {"team_name": team_name, "name": name, "device_id": device_id}


def remove_member(conn: sqlite3.Connection, team_name: str, device_id: str) -> None:
    """Remove a member by device_id (the PK)."""
    conn.execute(
        "DELETE FROM sync_members WHERE team_name = ? AND device_id = ?",
        (team_name, device_id),
    )
    conn.commit()


def list_members(conn: sqlite3.Connection, team_name: str) -> list[dict]:
    rows = conn.execute(
        "SELECT team_name, name, device_id, added_at FROM sync_members WHERE team_name = ? ORDER BY added_at",
        (team_name,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_member_by_device_id(conn: sqlite3.Connection, device_id: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT team_name, name, device_id, added_at FROM sync_members WHERE device_id = ?",
        (device_id,),
    ).fetchone()
    return dict(row) if row else None


# ── Team Projects ──────────────────────────────────────────────────────


def add_team_project(
    conn: sqlite3.Connection,
    team_name: str,
    project_encoded_name: str,
    path: Optional[str] = None,
    git_identity: Optional[str] = None,
) -> dict:
    conn.execute(
        "INSERT INTO sync_team_projects (team_name, project_encoded_name, path, git_identity) VALUES (?, ?, ?, ?)",
        (team_name, project_encoded_name, path, git_identity),
    )
    conn.commit()
    return {"team_name": team_name, "project_encoded_name": project_encoded_name, "git_identity": git_identity}


def remove_team_project(conn: sqlite3.Connection, team_name: str, project_encoded_name: str) -> None:
    conn.execute(
        "DELETE FROM sync_team_projects WHERE team_name = ? AND project_encoded_name = ?",
        (team_name, project_encoded_name),
    )
    conn.commit()


def list_team_projects(conn: sqlite3.Connection, team_name: str) -> list[dict]:
    rows = conn.execute(
        "SELECT team_name, project_encoded_name, path, git_identity, added_at FROM sync_team_projects WHERE team_name = ? ORDER BY added_at",
        (team_name,),
    ).fetchall()
    return [dict(r) for r in rows]


def upsert_team_project(
    conn: sqlite3.Connection,
    team_name: str,
    project_encoded_name: str,
    path: Optional[str] = None,
    git_identity: Optional[str] = None,
) -> dict:
    """Create or update a sync_team_projects record.

    Also ensures the parent ``projects`` row exists (FK requirement).
    Uses INSERT ... ON CONFLICT ... DO UPDATE for idempotent upsert
    (updates in-place without triggering FK cascade deletes).
    """
    # Ensure FK parent row exists in projects table
    conn.execute(
        "INSERT OR IGNORE INTO projects (encoded_name, project_path, git_identity) VALUES (?, ?, ?)",
        (project_encoded_name, path, git_identity),
    )
    # Update git_identity on the projects row if it was previously NULL
    if git_identity:
        conn.execute(
            "UPDATE projects SET git_identity = ? WHERE encoded_name = ? AND git_identity IS NULL",
            (git_identity, project_encoded_name),
        )

    # Upsert into sync_team_projects
    conn.execute(
        """INSERT INTO sync_team_projects (team_name, project_encoded_name, path, git_identity)
           VALUES (?, ?, ?, ?)
           ON CONFLICT (team_name, project_encoded_name)
           DO UPDATE SET path = COALESCE(excluded.path, path),
                         git_identity = COALESCE(excluded.git_identity, git_identity)""",
        (team_name, project_encoded_name, path, git_identity),
    )
    conn.commit()
    return {
        "team_name": team_name,
        "project_encoded_name": project_encoded_name,
        "path": path,
        "git_identity": git_identity,
    }


# ── Events ─────────────────────────────────────────────────────────────


def log_event(
    conn: sqlite3.Connection,
    event_type: str,
    team_name: Optional[str] = None,
    member_name: Optional[str] = None,
    project_encoded_name: Optional[str] = None,
    session_uuid: Optional[str] = None,
    detail: Optional[dict] = None,
) -> int:
    cursor = conn.execute(
        """INSERT INTO sync_events (event_type, team_name, member_name, project_encoded_name, session_uuid, detail)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (event_type, team_name, member_name, project_encoded_name, session_uuid,
         json.dumps(detail) if detail else None),
    )
    conn.commit()
    return cursor.lastrowid


def query_events(
    conn: sqlite3.Connection,
    team_name: Optional[str] = None,
    event_type: Optional[str] = None,
    member_name: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    conditions = []
    params: dict = {}
    if team_name:
        conditions.append("team_name = :team_name")
        params["team_name"] = team_name
    if event_type:
        conditions.append("event_type = :event_type")
        params["event_type"] = event_type
    if member_name:
        conditions.append("member_name = :member_name")
        params["member_name"] = member_name

    # Safety: conditions list is built from hardcoded column names only — never from user input
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params["limit"] = limit
    params["offset"] = offset

    rows = conn.execute(
        f"SELECT * FROM sync_events {where} ORDER BY created_at DESC LIMIT :limit OFFSET :offset",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


# ── Helpers ────────────────────────────────────────────────────────────


def find_project_by_git_identity(conn: sqlite3.Connection, git_identity: str) -> Optional[dict]:
    """Find a local project row matching this git identity."""
    row = conn.execute(
        "SELECT encoded_name, project_path, git_identity FROM projects WHERE git_identity = ?",
        (git_identity,),
    ).fetchone()
    return dict(row) if row else None


def find_project_by_git_suffix(conn: sqlite3.Connection, suffix: str) -> Optional[dict]:
    """Find a local project whose git_identity matches a Syncthing folder suffix.

    Syncthing folder IDs use ``git_identity.replace('/', '-')`` as the suffix.
    This reverses that by querying ``REPLACE(git_identity, '/', '-') = suffix``.
    """
    row = conn.execute(
        "SELECT encoded_name, project_path, git_identity FROM projects"
        " WHERE REPLACE(git_identity, '/', '-') = ?",
        (suffix,),
    ).fetchone()
    return dict(row) if row else None


def count_sessions_for_project(conn: sqlite3.Connection, encoded_name: str) -> int:
    """Count sessions for a project by encoded name."""
    row = conn.execute(
        "SELECT COUNT(*) FROM sessions WHERE project_encoded_name = ?",
        (encoded_name,),
    ).fetchone()
    return row[0] if row else 0


def get_known_devices(conn: sqlite3.Connection) -> dict[str, tuple[str, str]]:
    """Return {device_id: (member_name, team_name)} for all Syncthing members."""
    rows = conn.execute(
        "SELECT device_id, name, team_name FROM sync_members"
    ).fetchall()
    return {row["device_id"]: (row["name"], row["team_name"]) for row in rows}
