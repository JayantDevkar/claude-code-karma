"""Shared packaging service — used by both watcher and on-demand endpoint."""
from __future__ import annotations

import logging
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_project_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


def _get_project_lock(encoded_name: str) -> threading.Lock:
    with _locks_lock:
        if encoded_name not in _project_locks:
            _project_locks[encoded_name] = threading.Lock()
        return _project_locks[encoded_name]


@dataclass
class PackageResult:
    team_name: str
    git_identity: str
    sessions_packaged: int = 0
    error: Optional[str] = None


class PackagingService:
    def __init__(
        self,
        member_tag: str,
        user_id: str = "unknown",
        machine_id: str = "unknown",
        device_id: str = "",
    ):
        self.member_tag = member_tag
        self.user_id = user_id
        self.machine_id = machine_id
        self.device_id = device_id

    def resolve_packagable_projects(
        self,
        conn: sqlite3.Connection,
        *,
        team_name: Optional[str] = None,
        git_identity: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Return projects that this member should package sessions for.

        Filters:
          - Only ACCEPTED subscriptions with direction send or both
          - Only SHARED projects
          - Optional team_name / git_identity narrowing
          - Dedup key: (encoded_name, team_name)
        """
        from repositories.subscription_repo import SubscriptionRepository
        from repositories.project_repo import ProjectRepository

        subs = SubscriptionRepository().list_for_member(conn, self.member_tag)
        results: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()  # (encoded_name, team_name)

        for s in subs:
            if s.status.value != "accepted" or s.direction.value not in (
                "send",
                "both",
            ):
                continue
            if team_name and s.team_name != team_name:
                continue

            project = ProjectRepository().get(
                conn, s.team_name, s.project_git_identity
            )
            if not project or project.status.value != "shared":
                continue
            if git_identity and project.git_identity != git_identity:
                continue

            enc = project.encoded_name or ""
            key = (enc, s.team_name)
            if key in seen:
                continue
            seen.add(key)

            results.append(
                {
                    "team_name": s.team_name,
                    "git_identity": project.git_identity,
                    "encoded_name": enc,
                    "folder_suffix": project.folder_suffix,
                }
            )

        return results

    def package_project(
        self,
        conn: sqlite3.Connection,
        *,
        team_name: str,
        git_identity: str,
        encoded_name: str,
        folder_suffix: str,
    ) -> PackageResult:
        """Package sessions for a single project into the Syncthing outbox.

        Thread-safe: uses a per-project lock so concurrent calls for the
        same encoded_name are serialized (non-blocking — returns immediately
        if another thread is already packaging).
        """
        from services.sync.session_packager import SessionPackager
        from services.sync.worktree_discovery import find_worktree_dirs
        from models.sync_config import KARMA_BASE
        from services.syncthing.folder_manager import build_outbox_folder_id

        lock = _get_project_lock(encoded_name)
        if not lock.acquire(blocking=False):
            return PackageResult(
                team_name=team_name,
                git_identity=git_identity,
                error="Packaging already in progress",
            )
        try:
            projects_dir = Path.home() / ".claude" / "projects"
            claude_dir = projects_dir / encoded_name
            if not claude_dir.is_dir():
                return PackageResult(
                    team_name=team_name,
                    git_identity=git_identity,
                    error=f"Project dir not found: {encoded_name}",
                )

            folder_id = build_outbox_folder_id(self.member_tag, folder_suffix)
            outbox = KARMA_BASE / folder_id
            outbox.mkdir(parents=True, exist_ok=True)

            wt_dirs = find_worktree_dirs(encoded_name, projects_dir)
            packager = SessionPackager(
                project_dir=claude_dir,
                user_id=self.user_id,
                machine_id=self.machine_id,
                device_id=self.device_id,
                project_path="",
                extra_dirs=wt_dirs,
                member_tag=self.member_tag,
            )
            manifest = packager.package(staging_dir=outbox)
            count = len(manifest.sessions) if manifest else 0
            self._log_events(conn, team_name, git_identity, manifest)
            return PackageResult(
                team_name=team_name,
                git_identity=git_identity,
                sessions_packaged=count,
            )
        except Exception as e:
            logger.warning("Packaging failed for %s: %s", encoded_name, e)
            return PackageResult(
                team_name=team_name,
                git_identity=git_identity,
                error=str(e),
            )
        finally:
            lock.release()

    def _log_events(self, conn, team_name, git_identity, manifest):
        if not manifest or not manifest.sessions:
            return
        try:
            from repositories.event_repo import EventRepository
            from domain.events import SyncEvent, SyncEventType

            repo = EventRepository()
            for session_uuid in manifest.sessions:
                repo.log(
                    conn,
                    SyncEvent(
                        event_type=SyncEventType.session_packaged,
                        team_name=team_name,
                        project_git_identity=git_identity,
                        session_uuid=session_uuid,
                    ),
                )
        except Exception:
            logger.debug(
                "Failed to log session_packaged events", exc_info=True
            )
