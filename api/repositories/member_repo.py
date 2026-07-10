"""Member repository — SQLite persistence for Member domain model."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from domain.member import Member, MemberStatus


class MemberRepository:
    def get(self, conn: sqlite3.Connection, team_name: str, member_tag: str) -> Member | None:
        row = conn.execute(
            "SELECT * FROM sync_members WHERE team_name = ? AND member_tag = ?",
            (team_name, member_tag),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_member(row)

    def get_by_device(self, conn: sqlite3.Connection, device_id: str) -> list[Member]:
        rows = conn.execute(
            "SELECT * FROM sync_members WHERE device_id = ?", (device_id,)
        ).fetchall()
        return [self._row_to_member(r) for r in rows]

    def get_all_by_member_tag(
        self, conn: sqlite3.Connection, member_tag: str
    ) -> list[Member]:
        rows = conn.execute(
            "SELECT * FROM sync_members WHERE member_tag = ?", (member_tag,)
        ).fetchall()
        return [self._row_to_member(r) for r in rows]

    def get_by_user_id(
        self, conn: sqlite3.Connection, user_id: str
    ) -> list[Member]:
        rows = conn.execute(
            "SELECT * FROM sync_members WHERE user_id = ?", (user_id,)
        ).fetchall()
        return [self._row_to_member(r) for r in rows]

    def save(self, conn: sqlite3.Connection, member: Member) -> None:
        conn.execute(
            """INSERT INTO sync_members
               (team_name, member_tag, device_id, user_id, machine_tag, status, added_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(team_name, member_tag) DO UPDATE SET
                   device_id = excluded.device_id,
                   user_id = excluded.user_id,
                   machine_tag = excluded.machine_tag,
                   status = excluded.status,
                   updated_at = excluded.updated_at""",
            (member.team_name, member.member_tag, member.device_id,
             member.user_id, member.machine_tag, member.status.value,
             member.added_at.isoformat(), member.updated_at.isoformat()),
        )
        conn.commit()

    def list_for_team(self, conn: sqlite3.Connection, team_name: str) -> list[Member]:
        rows = conn.execute(
            "SELECT * FROM sync_members WHERE team_name = ?", (team_name,)
        ).fetchall()
        return [self._row_to_member(r) for r in rows]

    def was_removed(self, conn: sqlite3.Connection, team_name: str, device_id: str) -> bool:
        row = conn.execute(
            "SELECT 1 FROM sync_removed_members WHERE team_name = ? AND device_id = ?",
            (team_name, device_id),
        ).fetchone()
        return row is not None

    def record_removal(
        self,
        conn: sqlite3.Connection,
        team_name: str,
        device_id: str,
        member_tag: str | None = None,
    ) -> None:
        conn.execute(
            """INSERT INTO sync_removed_members (team_name, device_id, member_tag)
               VALUES (?, ?, ?)
               ON CONFLICT(team_name, device_id) DO UPDATE SET
                   member_tag = excluded.member_tag""",
            (team_name, device_id, member_tag),
        )
        conn.commit()

    @staticmethod
    def _row_to_member(row: sqlite3.Row) -> Member:
        return Member(
            team_name=row["team_name"],
            member_tag=row["member_tag"],
            device_id=row["device_id"],
            user_id=row["user_id"],
            machine_tag=row["machine_tag"],
            status=MemberStatus(row["status"]),
            added_at=datetime.fromisoformat(row["added_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
