"""Subscription repository — SQLite persistence for Subscription domain model."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from domain.subscription import Subscription, SubscriptionStatus, SyncDirection


class SubscriptionRepository:
    def get(
        self,
        conn: sqlite3.Connection,
        member_tag: str,
        team_name: str,
        git_identity: str,
    ) -> Subscription | None:
        row = conn.execute(
            """SELECT * FROM sync_subscriptions
               WHERE member_tag = ? AND team_name = ? AND project_git_identity = ?""",
            (member_tag, team_name, git_identity),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_sub(row)

    def save(self, conn: sqlite3.Connection, sub: Subscription) -> None:
        conn.execute(
            """INSERT INTO sync_subscriptions
               (member_tag, team_name, project_git_identity, status, direction, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(member_tag, team_name, project_git_identity) DO UPDATE SET
                   status = excluded.status,
                   direction = excluded.direction,
                   updated_at = excluded.updated_at""",
            (sub.member_tag, sub.team_name, sub.project_git_identity,
             sub.status.value, sub.direction.value, sub.updated_at.isoformat()),
        )
        conn.commit()

    def list_for_member(self, conn: sqlite3.Connection, member_tag: str) -> list[Subscription]:
        rows = conn.execute(
            "SELECT * FROM sync_subscriptions WHERE member_tag = ?", (member_tag,)
        ).fetchall()
        return [self._row_to_sub(r) for r in rows]

    def list_for_project(
        self, conn: sqlite3.Connection, team_name: str, git_identity: str
    ) -> list[Subscription]:
        rows = conn.execute(
            """SELECT * FROM sync_subscriptions
               WHERE team_name = ? AND project_git_identity = ?""",
            (team_name, git_identity),
        ).fetchall()
        return [self._row_to_sub(r) for r in rows]

    def list_accepted_for_suffix(
        self, conn: sqlite3.Connection, suffix: str
    ) -> list[Subscription]:
        rows = conn.execute(
            """SELECT ss.* FROM sync_subscriptions ss
               JOIN sync_projects sp
                 ON ss.team_name = sp.team_name
                 AND ss.project_git_identity = sp.git_identity
               WHERE sp.folder_suffix = ? AND ss.status = 'accepted'""",
            (suffix,),
        ).fetchall()
        return [self._row_to_sub(r) for r in rows]

    @staticmethod
    def _row_to_sub(row: sqlite3.Row) -> Subscription:
        return Subscription(
            member_tag=row["member_tag"],
            team_name=row["team_name"],
            project_git_identity=row["project_git_identity"],
            status=SubscriptionStatus(row["status"]),
            direction=SyncDirection(row["direction"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
