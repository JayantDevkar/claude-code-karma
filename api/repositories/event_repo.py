"""Event repository — SQLite persistence for SyncEvent domain model."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Optional

from domain.events import SyncEvent, SyncEventType


class EventRepository:
    def log(self, conn: sqlite3.Connection, event: SyncEvent) -> int:
        """Persist a SyncEvent and return its auto-generated id."""
        cur = conn.execute(
            """INSERT INTO sync_events
               (event_type, team_name, member_tag, project_git_identity,
                session_uuid, detail, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                event.event_type.value,
                event.team_name,
                event.member_tag,
                event.project_git_identity,
                event.session_uuid,
                json.dumps(event.detail) if event.detail is not None else None,
                event.created_at.isoformat(),
            ),
        )
        conn.commit()
        return cur.lastrowid

    def query(
        self,
        conn: sqlite3.Connection,
        *,
        team: Optional[str] = None,
        member_tag: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 50,
    ) -> list[SyncEvent]:
        parts = []
        params: list = []

        if team is not None:
            parts.append("team_name = ?")
            params.append(team)
        if member_tag is not None:
            parts.append("member_tag = ?")
            params.append(member_tag)
        if event_type is not None:
            parts.append("event_type = ?")
            params.append(event_type)

        where = f"WHERE {' AND '.join(parts)}" if parts else ""
        params.append(limit)

        rows = conn.execute(
            f"SELECT * FROM sync_events {where} ORDER BY created_at DESC LIMIT ?",
            params,
        ).fetchall()
        return [self._row_to_event(r) for r in rows]

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> SyncEvent:
        detail = json.loads(row["detail"]) if row["detail"] is not None else None
        return SyncEvent(
            event_type=SyncEventType(row["event_type"]),
            team_name=row["team_name"],
            member_tag=row["member_tag"],
            project_git_identity=row["project_git_identity"],
            session_uuid=row["session_uuid"],
            detail=detail,
            created_at=datetime.fromisoformat(row["created_at"]),
        )
