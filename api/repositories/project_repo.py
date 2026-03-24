"""Project repository — SQLite persistence for SharedProject domain model."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from domain.project import SharedProject, SharedProjectStatus


class ProjectRepository:
    def get(
        self, conn: sqlite3.Connection, team_name: str, git_identity: str
    ) -> SharedProject | None:
        row = conn.execute(
            "SELECT * FROM sync_projects WHERE team_name = ? AND git_identity = ?",
            (team_name, git_identity),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_project(row)

    def save(self, conn: sqlite3.Connection, project: SharedProject) -> None:
        conn.execute(
            """INSERT INTO sync_projects
               (team_name, git_identity, encoded_name, folder_suffix, status, shared_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(team_name, git_identity) DO UPDATE SET
                   encoded_name = excluded.encoded_name,
                   folder_suffix = excluded.folder_suffix,
                   status = excluded.status""",
            (project.team_name, project.git_identity, project.encoded_name,
             project.folder_suffix, project.status.value, project.shared_at.isoformat()),
        )
        conn.commit()

    def list_for_team(
        self,
        conn: sqlite3.Connection,
        team_name: str,
        include_removed: bool = False,
    ) -> list[SharedProject]:
        if include_removed:
            rows = conn.execute(
                "SELECT * FROM sync_projects WHERE team_name = ?", (team_name,)
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM sync_projects WHERE team_name = ? AND status != 'removed'",
                (team_name,),
            ).fetchall()
        return [self._row_to_project(r) for r in rows]

    def find_by_suffix(self, conn: sqlite3.Connection, suffix: str) -> list[SharedProject]:
        rows = conn.execute(
            "SELECT * FROM sync_projects WHERE folder_suffix = ?", (suffix,)
        ).fetchall()
        return [self._row_to_project(r) for r in rows]

    def find_by_git_identity(
        self, conn: sqlite3.Connection, git_identity: str
    ) -> list[SharedProject]:
        rows = conn.execute(
            "SELECT * FROM sync_projects WHERE git_identity = ?", (git_identity,)
        ).fetchall()
        return [self._row_to_project(r) for r in rows]

    @staticmethod
    def _row_to_project(row: sqlite3.Row) -> SharedProject:
        return SharedProject(
            team_name=row["team_name"],
            git_identity=row["git_identity"],
            encoded_name=row["encoded_name"],
            folder_suffix=row["folder_suffix"],
            status=SharedProjectStatus(row["status"]),
            shared_at=datetime.fromisoformat(row["shared_at"]),
        )
