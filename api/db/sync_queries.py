"""Sync CRUD functions for teams, members, projects, and events.

All functions take a raw sqlite3.Connection. The API wraps them with
run_in_executor for async. The CLI calls them directly.
"""

import json
import shutil
import sqlite3
from collections import defaultdict
from pathlib import Path
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
    # Clean up orphaned settings (sync_settings has no FK to sync_teams)
    conn.execute(
        "DELETE FROM sync_settings WHERE scope = ? OR scope LIKE ?",
        (f"team:{name}", f"member:{name}:%"),
    )
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


VALID_SESSION_LIMITS = frozenset({"all", "recent_100", "recent_10"})


def update_team_session_limit(
    conn: sqlite3.Connection,
    team_name: str,
    limit: str,
) -> None:
    """Update the sync session limit for a team.

    Valid values: 'all', 'recent_100', 'recent_10'.
    """
    if limit not in VALID_SESSION_LIMITS:
        raise ValueError(f"Invalid session limit: {limit!r}. Must be one of {sorted(VALID_SESSION_LIMITS)}")
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
    # Remove any existing entry with the same name but different device_id
    # (handles the case where a member reinstalled Syncthing and got a new identity)
    conn.execute(
        "DELETE FROM sync_members WHERE team_name = ? AND name = ? AND device_id != ?",
        (team_name, name, device_id),
    )
    conn.execute(
        """INSERT INTO sync_members (team_name, name, device_id)
           VALUES (?, ?, ?)
           ON CONFLICT(team_name, device_id)
           DO UPDATE SET name = excluded.name""",
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
    """Insert a member or update their name if the device already exists.

    Also removes stale rows where the same name maps to a different device_id
    (e.g. member reinstalled Syncthing and got a new identity).
    """
    conn.execute(
        "DELETE FROM sync_members WHERE team_name = ? AND name = ? AND device_id != ?",
        (team_name, name, device_id),
    )
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
    """Remove a member by device_id (the PK) and record the removal.

    The removal record prevents reconcile_pending_handshakes from
    re-adding the member when a stale handshake folder is re-offered.
    """
    conn.execute(
        """INSERT OR REPLACE INTO sync_removed_members (team_name, device_id, removed_at)
           VALUES (?, ?, datetime('now'))""",
        (team_name, device_id),
    )
    conn.execute(
        "DELETE FROM sync_members WHERE team_name = ? AND device_id = ?",
        (team_name, device_id),
    )
    conn.commit()


def was_member_removed(conn: sqlite3.Connection, team_name: str, device_id: str) -> bool:
    """Check if a device was intentionally removed from a team.

    Used by reconcile_pending_handshakes to avoid re-adding members
    whose stale handshake folders are re-offered after removal.
    """
    row = conn.execute(
        "SELECT 1 FROM sync_removed_members WHERE team_name = ? AND device_id = ?",
        (team_name, device_id),
    ).fetchone()
    return row is not None


def clear_member_removal(conn: sqlite3.Connection, team_name: str, device_id: str) -> None:
    """Clear a removal record when a member is intentionally re-added.

    Called when a member joins via join code or is manually added via UI —
    these are explicit user actions that should override a previous removal.
    """
    conn.execute(
        "DELETE FROM sync_removed_members WHERE team_name = ? AND device_id = ?",
        (team_name, device_id),
    )
    conn.commit()


def list_members(conn: sqlite3.Connection, team_name: str) -> list[dict]:
    rows = conn.execute(
        "SELECT team_name, name, device_id, added_at FROM sync_members WHERE team_name = ? ORDER BY added_at",
        (team_name,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_member_by_device_id(
    conn: sqlite3.Connection, device_id: str, team_name: Optional[str] = None,
) -> Optional[dict]:
    """Look up a member by device_id, optionally scoped to a specific team.

    Without team_name, returns the first row found (non-deterministic for
    multi-team devices). With team_name, returns the exact row for that team.
    Always prefer passing team_name when the team context is known.
    """
    if team_name:
        row = conn.execute(
            "SELECT team_name, name, device_id, added_at FROM sync_members "
            "WHERE device_id = ? AND team_name = ?",
            (device_id, team_name),
        ).fetchone()
    else:
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


def log_session_packaged_events(
    conn: sqlite3.Connection,
    team_name: str,
    project_encoded_name: str,
    member_name: str,
    sessions: list,
    *,
    commit: bool = True,
) -> int:
    """Log session_packaged events with dedup. Returns count of new events logged.

    ``sessions`` should be an iterable of objects with a ``.uuid`` attribute.
    """
    already = {
        r[0] for r in conn.execute(
            "SELECT session_uuid FROM sync_events "
            "WHERE event_type = 'session_packaged' AND team_name = ? "
            "AND project_encoded_name = ? AND session_uuid IS NOT NULL",
            (team_name, project_encoded_name),
        ).fetchall()
    }
    logged = 0
    for entry in sessions:
        if entry.uuid not in already:
            conn.execute(
                """INSERT INTO sync_events (event_type, team_name, member_name, project_encoded_name, session_uuid, detail)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                ("session_packaged", team_name, member_name, project_encoded_name, entry.uuid, None),
            )
            logged += 1
    if commit and logged:
        conn.commit()
    return logged


_ALLOWED_EVENT_FILTERS = frozenset({"team_name", "event_type", "member_name"})


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
        # Support comma-separated event types for multi-filter (e.g. "session_packaged,session_received")
        types = [t.strip() for t in event_type.split(",") if t.strip()]
        if len(types) == 1:
            conditions.append("event_type = :event_type")
            params["event_type"] = types[0]
        elif types:
            placeholders = ", ".join(f":evt_{i}" for i in range(len(types)))
            conditions.append(f"event_type IN ({placeholders})")
            for i, t in enumerate(types):
                params[f"evt_{i}"] = t
    if member_name:
        conditions.append("member_name = :member_name")
        params["member_name"] = member_name

    # Safety: verify all filter param keys are in the allowlist before SQL interpolation
    # (belt-and-suspenders — params are built from hardcoded branches above, never from raw user input)
    unknown = set(params.keys()) - _ALLOWED_EVENT_FILTERS - {"limit", "offset"} - {k for k in params if k.startswith("evt_")}
    if unknown:
        raise ValueError(f"Unexpected filter columns: {unknown}")

    # Validate condition column names (not just param keys) to close injection vector
    # for future developers who might add conditions with unsanitized column names.
    for cond in conditions:
        col = cond.split()[0]
        if col not in _ALLOWED_EVENT_FILTERS:
            raise ValueError(f"Disallowed column in condition: {col!r}")

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


def get_known_devices(conn: sqlite3.Connection) -> dict[str, list[tuple[str, str]]]:
    """Return {device_id: [(member_name, team_name), ...]} for all Syncthing members.

    A device in multiple teams will have multiple entries in the list.
    """
    rows = conn.execute(
        "SELECT device_id, name, team_name FROM sync_members ORDER BY added_at"
    ).fetchall()
    result: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for row in rows:
        result[row["device_id"]].append((row["name"], row["team_name"]))
    return dict(result)


def query_session_stats_by_member(
    conn: sqlite3.Connection,
    team_name: str,
    days: int = 30,
    member_name: Optional[str] = None,
) -> list[dict]:
    """Aggregate session activity events per member per day.

    Both ``session_packaged`` and ``session_received`` represent sessions
    contributed by the member (packaged locally or received from them
    remotely).  They are combined into a single ``out`` count.

    When *member_name* is provided the query is scoped to that single member,
    avoiding the cost of aggregating every team member's stats.

    Returns dicts with keys: date, member_name, out, packaged (alias for out),
    received (always 0, kept for backward compat).
    """
    if member_name:
        rows = conn.execute(
            """
            SELECT
                DATE(created_at, 'localtime') AS date,
                member_name,
                COUNT(DISTINCT session_uuid) AS out_count
            FROM sync_events
            WHERE team_name = ?
              AND member_name = ?
              AND event_type IN ('session_packaged', 'session_received')
              AND created_at >= datetime('now', 'localtime', ?)
            GROUP BY date, member_name
            ORDER BY date
            """,
            (team_name, member_name, f"-{days} days"),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT
                DATE(created_at, 'localtime') AS date,
                member_name,
                COUNT(DISTINCT session_uuid) AS out_count
            FROM sync_events
            WHERE team_name = ?
              AND event_type IN ('session_packaged', 'session_received')
              AND member_name IS NOT NULL
              AND created_at >= datetime('now', 'localtime', ?)
            GROUP BY date, member_name
            ORDER BY date
            """,
            (team_name, f"-{days} days"),
        ).fetchall()
    return [
        {
            "date": r[0],
            "member_name": r[1],
            "out": r[2],
            "packaged": r[2],  # backward compat alias
            "received": 0,     # backward compat
        }
        for r in rows
    ]


# ── Settings ──────────────────────────────────────────────────────────

_SETTING_DEFAULTS = {
    "auto_accept_members": "false",
    "sync_direction": "both",
}

VALID_SYNC_DIRECTIONS = frozenset({"both", "send_only", "receive_only", "none"})

VALID_SETTING_KEYS = frozenset(_SETTING_DEFAULTS.keys())


def get_setting(
    conn: sqlite3.Connection,
    scope: str,
    key: str,
) -> Optional[str]:
    """Raw single-scope lookup. Returns None if not set."""
    row = conn.execute(
        "SELECT value FROM sync_settings WHERE scope = ? AND setting_key = ?",
        (scope, key),
    ).fetchone()
    return row[0] if row else None


def set_setting(
    conn: sqlite3.Connection,
    scope: str,
    key: str,
    value: str,
) -> Optional[str]:
    """Set a setting value. Returns the old value (or None if new)."""
    old = get_setting(conn, scope, key)
    conn.execute(
        """INSERT INTO sync_settings (scope, setting_key, value, updated_at)
           VALUES (?, ?, ?, datetime('now'))
           ON CONFLICT(scope, setting_key)
           DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
        (scope, key, value),
    )
    conn.commit()
    return old


def delete_setting(
    conn: sqlite3.Connection,
    scope: str,
    key: str,
) -> None:
    """Remove a setting override (falls back to default)."""
    conn.execute(
        "DELETE FROM sync_settings WHERE scope = ? AND setting_key = ?",
        (scope, key),
    )
    conn.commit()


def list_settings(
    conn: sqlite3.Connection,
    scope_prefix: str,
) -> list[dict]:
    """List all settings matching a scope prefix.

    E.g. ``list_settings(conn, "team:acme")`` returns team-level and
    member-level settings for team "acme".
    """
    escaped = scope_prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    rows = conn.execute(
        "SELECT scope, setting_key, value, updated_at FROM sync_settings"
        " WHERE scope LIKE ? || '%' ESCAPE '\\'",
        (escaped,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_effective_setting(
    conn: sqlite3.Connection,
    key: str,
    *,
    team_name: Optional[str] = None,
    device_id: Optional[str] = None,
) -> tuple[str, str]:
    """Resolve setting with 3-scope cascade. Returns (value, source).

    Resolution order (most specific wins):
        member:{team}:{device} > team:{team} > device:{device} > default
    """
    # 1. Most specific: per-member-per-team
    if team_name and device_id:
        val = get_setting(conn, f"member:{team_name}:{device_id}", key)
        if val is not None:
            return val, "member"
    # 2. Team default
    if team_name:
        val = get_setting(conn, f"team:{team_name}", key)
        if val is not None:
            return val, "team"
    # 3. Global device default (cross-team)
    if device_id:
        val = get_setting(conn, f"device:{device_id}", key)
        if val is not None:
            return val, "device"
    # 4. Hardcoded default
    if key not in _SETTING_DEFAULTS:
        raise ValueError(f"Unknown setting key: {key!r}. Valid keys: {sorted(_SETTING_DEFAULTS)}")
    return _SETTING_DEFAULTS[key], "default"


def get_effective_sync_direction(
    conn: sqlite3.Connection,
    *,
    team_name: Optional[str] = None,
    device_id: Optional[str] = None,
) -> str:
    """Convenience: resolve sync_direction."""
    value, _ = get_effective_setting(conn, "sync_direction", team_name=team_name, device_id=device_id)
    return value


def get_effective_auto_accept(
    conn: sqlite3.Connection,
    team_name: str,
) -> bool:
    """Convenience: resolve auto_accept_members for a team."""
    value, _ = get_effective_setting(conn, "auto_accept_members", team_name=team_name)
    return value == "true"


def cleanup_data_for_member(
    conn: sqlite3.Connection,
    team_name: str,
    member_name: str,
    karma_base: Path,
) -> dict:
    """Delete remote-session files and DB rows for a removed member.

    Scoped to the team's projects so data from other teams is preserved.
    """
    projects = list_team_projects(conn, team_name)
    project_encoded_names = [p["project_encoded_name"] for p in projects]

    # Filesystem: delete per-project dirs under remote-sessions/{member}/
    dirs_removed = 0
    remote_base = karma_base / "remote-sessions" / member_name
    for encoded_name in project_encoded_names:
        target = remote_base / encoded_name
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)
            dirs_removed += 1

    # Remove member dir if now empty
    if remote_base.exists():
        try:
            remote_base.rmdir()  # only succeeds if empty
        except OSError:
            pass

    # DB: delete remote session rows scoped to team projects
    sessions_deleted = 0
    if project_encoded_names:
        placeholders = ",".join("?" * len(project_encoded_names))
        cursor = conn.execute(
            f"DELETE FROM sessions WHERE source = 'remote' AND remote_user_id = ?"
            f" AND project_encoded_name IN ({placeholders})",
            [member_name, *project_encoded_names],
        )
        sessions_deleted = cursor.rowcount
        conn.commit()

    return {"dirs_removed": dirs_removed, "sessions_deleted": sessions_deleted}


def cleanup_data_for_project(
    conn: sqlite3.Connection,
    team_name: str,
    project_encoded_name: str,
    *,
    base_path: Path | None = None,
) -> dict:
    """Remove remote session data for a specific project across all team members.

    Cleans up:
    - Filesystem: remote-sessions/{member}/{encoded}/ directories
    - DB: sessions with source='remote' for this project
    """
    if base_path is None:
        from karma.config import KARMA_BASE
        base_path = KARMA_BASE

    stats = {"sessions_deleted": 0, "dirs_deleted": 0}

    members = list_members(conn, team_name)

    # Filesystem cleanup
    for m in members:
        member_dir = base_path / "remote-sessions" / m["name"] / project_encoded_name
        if member_dir.exists():
            shutil.rmtree(member_dir)
            stats["dirs_deleted"] += 1
            # Remove parent if empty
            parent = member_dir.parent
            if parent.exists() and not any(parent.iterdir()):
                parent.rmdir()

    # DB cleanup: remove remote sessions for this project
    cursor = conn.execute(
        "DELETE FROM sessions WHERE source = 'remote' AND project_encoded_name = ?",
        (project_encoded_name,),
    )
    stats["sessions_deleted"] = cursor.rowcount
    conn.commit()

    return stats
