"""Sync CRUD functions for teams, members, projects, and events.

All functions take a raw sqlite3.Connection. The API wraps them with
run_in_executor for async. The CLI calls them directly.
"""

import json
import sqlite3
from typing import Optional


# ── Teams ──────────────────────────────────────────────────────────────


def create_team(conn: sqlite3.Connection, name: str, backend: str = "syncthing") -> dict:
    conn.execute(
        "INSERT INTO sync_teams (name, backend) VALUES (?, ?)",
        (name, backend),
    )
    conn.commit()
    return {"name": name, "backend": backend}


def delete_team(conn: sqlite3.Connection, name: str) -> None:
    conn.execute("DELETE FROM sync_teams WHERE name = ?", (name,))
    conn.commit()


def list_teams(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """SELECT t.name, t.backend, t.created_at,
                  (SELECT COUNT(*) FROM sync_members m WHERE m.team_name = t.name) as member_count,
                  (SELECT COUNT(*) FROM sync_team_projects p WHERE p.team_name = t.name) as project_count
           FROM sync_teams t ORDER BY t.created_at"""
    ).fetchall()
    return [dict(r) for r in rows]


def get_team(conn: sqlite3.Connection, name: str) -> Optional[dict]:
    row = conn.execute(
        """SELECT t.name, t.backend, t.created_at,
                  (SELECT COUNT(*) FROM sync_members m WHERE m.team_name = t.name) as member_count,
                  (SELECT COUNT(*) FROM sync_team_projects p WHERE p.team_name = t.name) as project_count
           FROM sync_teams t WHERE t.name = ?""",
        (name,),
    ).fetchone()
    return dict(row) if row else None


# ── Members ────────────────────────────────────────────────────────────


def add_member(
    conn: sqlite3.Connection,
    team_name: str,
    name: str,
    device_id: Optional[str] = None,
    ipns_key: Optional[str] = None,
) -> dict:
    conn.execute(
        "INSERT INTO sync_members (team_name, name, device_id, ipns_key) VALUES (?, ?, ?, ?)",
        (team_name, name, device_id, ipns_key),
    )
    conn.commit()
    return {"team_name": team_name, "name": name, "device_id": device_id}


def remove_member(conn: sqlite3.Connection, team_name: str, name: str) -> None:
    conn.execute(
        "DELETE FROM sync_members WHERE team_name = ? AND name = ?",
        (team_name, name),
    )
    conn.commit()


def list_members(conn: sqlite3.Connection, team_name: str) -> list[dict]:
    rows = conn.execute(
        "SELECT team_name, name, device_id, ipns_key, added_at FROM sync_members WHERE team_name = ? ORDER BY added_at",
        (team_name,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_member_by_device_id(conn: sqlite3.Connection, device_id: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT team_name, name, device_id, ipns_key, added_at FROM sync_members WHERE device_id = ?",
        (device_id,),
    ).fetchone()
    return dict(row) if row else None


# ── Team Projects ──────────────────────────────────────────────────────


def add_team_project(
    conn: sqlite3.Connection,
    team_name: str,
    project_encoded_name: str,
    path: Optional[str] = None,
) -> dict:
    conn.execute(
        "INSERT INTO sync_team_projects (team_name, project_encoded_name, path) VALUES (?, ?, ?)",
        (team_name, project_encoded_name, path),
    )
    conn.commit()
    return {"team_name": team_name, "project_encoded_name": project_encoded_name}


def remove_team_project(conn: sqlite3.Connection, team_name: str, project_encoded_name: str) -> None:
    conn.execute(
        "DELETE FROM sync_team_projects WHERE team_name = ? AND project_encoded_name = ?",
        (team_name, project_encoded_name),
    )
    conn.commit()


def list_team_projects(conn: sqlite3.Connection, team_name: str) -> list[dict]:
    rows = conn.execute(
        "SELECT team_name, project_encoded_name, path, added_at FROM sync_team_projects WHERE team_name = ? ORDER BY added_at",
        (team_name,),
    ).fetchall()
    return [dict(r) for r in rows]


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

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params["limit"] = limit
    params["offset"] = offset

    rows = conn.execute(
        f"SELECT * FROM sync_events {where} ORDER BY created_at DESC LIMIT :limit OFFSET :offset",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


# ── Helpers ────────────────────────────────────────────────────────────


def get_known_devices(conn: sqlite3.Connection) -> dict[str, tuple[str, str]]:
    """Return {device_id: (member_name, team_name)} for all Syncthing members."""
    rows = conn.execute(
        "SELECT device_id, name, team_name FROM sync_members WHERE device_id IS NOT NULL"
    ).fetchall()
    return {row["device_id"]: (row["name"], row["team_name"]) for row in rows}
