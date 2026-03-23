"""Team repository — SQLite persistence for Team domain model."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from domain.team import Team, TeamStatus


class TeamRepository:
    def get(self, conn: sqlite3.Connection, name: str) -> Team | None:
        row = conn.execute(
            "SELECT * FROM sync_teams WHERE name = ?", (name,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_team(row)

    def get_by_leader(self, conn: sqlite3.Connection, device_id: str) -> list[Team]:
        rows = conn.execute(
            "SELECT * FROM sync_teams WHERE leader_device_id = ?", (device_id,)
        ).fetchall()
        return [self._row_to_team(r) for r in rows]

    def save(self, conn: sqlite3.Connection, team: Team) -> None:
        conn.execute(
            """INSERT INTO sync_teams (name, leader_device_id, leader_member_tag, team_id, status, created_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                   leader_device_id = excluded.leader_device_id,
                   leader_member_tag = excluded.leader_member_tag,
                   team_id = excluded.team_id,
                   status = excluded.status""",
            (team.name, team.leader_device_id, team.leader_member_tag,
             team.team_id, team.status.value, team.created_at.isoformat()),
        )
        conn.commit()

    def delete(self, conn: sqlite3.Connection, name: str) -> None:
        conn.execute("DELETE FROM sync_teams WHERE name = ?", (name,))
        conn.commit()

    def list_all(self, conn: sqlite3.Connection) -> list[Team]:
        rows = conn.execute("SELECT * FROM sync_teams").fetchall()
        return [self._row_to_team(r) for r in rows]

    def list_active(self, conn: sqlite3.Connection) -> list[Team]:
        rows = conn.execute(
            "SELECT * FROM sync_teams WHERE status = ?", (TeamStatus.ACTIVE.value,)
        ).fetchall()
        return [self._row_to_team(r) for r in rows]

    @staticmethod
    def _row_to_team(row: sqlite3.Row) -> Team:
        # Deterministic fallback: uuid5 from team name so reads are stable
        team_id = row["team_id"]
        if not team_id:
            import uuid
            team_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"karma-team:{row['name']}"))
        return Team(
            name=row["name"],
            leader_device_id=row["leader_device_id"],
            leader_member_tag=row["leader_member_tag"],
            team_id=team_id,
            status=TeamStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
        )
