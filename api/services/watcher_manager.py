"""In-process session watcher manager.

Runs the same SessionWatcher + SessionPackager logic as `karma watch`,
but as a background service managed by the API process.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Add CLI to path
_CLI_PATH = Path(__file__).parent.parent.parent / "cli"
if str(_CLI_PATH) not in sys.path:
    sys.path.insert(0, str(_CLI_PATH))


class WatcherManager:
    """Manages SessionWatcher instances for a single team."""

    def __init__(self) -> None:
        self._running = False
        self._team: Optional[str] = None
        self._watchers: list = []
        self._started_at: Optional[str] = None
        self._last_packaged_at: Optional[str] = None
        self._projects_watched: list[str] = []

    @property
    def is_running(self) -> bool:
        return self._running

    def status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "team": self._team,
            "started_at": self._started_at,
            "last_packaged_at": self._last_packaged_at,
            "projects_watched": self._projects_watched,
        }

    def start(self, team_name: str, config_data: dict) -> dict[str, Any]:
        """Start watchers for all projects in the given team."""
        if self._running:
            raise ValueError(f"Watcher already running for team '{self._team}'")

        from karma.watcher import SessionWatcher
        from karma.packager import SessionPackager
        from karma.worktree_discovery import find_worktree_dirs
        from karma.config import KARMA_BASE

        team_cfg = config_data.get("teams", {}).get(team_name, {})
        projects = team_cfg.get("projects", {})
        user_id = config_data.get("user_id", "unknown")
        machine_id = config_data.get("machine_id", "unknown")

        projects_dir = Path.home() / ".claude" / "projects"
        watchers = []
        watched = []

        for proj_name, proj in projects.items():
            encoded = proj.get("encoded_name", proj_name)
            claude_dir = projects_dir / encoded
            if not claude_dir.is_dir():
                logger.warning("Skipping %s: dir not found %s", proj_name, claude_dir)
                continue

            outbox = KARMA_BASE / "remote-sessions" / user_id / encoded

            def make_package_fn(
                cd=claude_dir, ob=outbox, en=encoded, pp=proj.get("path", ""),
                tn=team_name,
            ):
                def package():
                    wt_dirs = find_worktree_dirs(en, projects_dir)
                    packager = SessionPackager(
                        project_dir=cd,
                        user_id=user_id,
                        machine_id=machine_id,
                        project_path=pp,
                        extra_dirs=wt_dirs,
                    )
                    ob.mkdir(parents=True, exist_ok=True)
                    packager.package(staging_dir=ob)
                    self._last_packaged_at = (
                        datetime.now(timezone.utc).isoformat()
                    )
                    # Log session_packaged event
                    try:
                        from db.connection import get_writer_db
                        from db.sync_queries import log_event
                        log_event(
                            get_writer_db(), "session_packaged",
                            team_name=tn, project_encoded_name=en,
                        )
                    except Exception:
                        pass  # Best-effort logging
                return package

            watcher = SessionWatcher(
                watch_dir=claude_dir,
                package_fn=make_package_fn(),
            )
            watcher.start()
            watchers.append(watcher)
            watched.append(proj_name)

            # Also watch worktree dirs
            wt_dirs = find_worktree_dirs(encoded, projects_dir)
            for wt_dir in wt_dirs:
                wt_watcher = SessionWatcher(
                    watch_dir=wt_dir,
                    package_fn=make_package_fn(),
                )
                wt_watcher.start()
                watchers.append(wt_watcher)

        self._watchers = watchers
        self._running = True
        self._team = team_name
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._projects_watched = watched

        logger.info(
            "Watcher started: team=%s, projects=%d, watchers=%d",
            team_name, len(watched), len(watchers),
        )
        return self.status()

    def stop(self) -> dict[str, Any]:
        """Stop all watchers."""
        for w in self._watchers:
            try:
                w.stop()
            except Exception as e:
                logger.warning("Error stopping watcher: %s", e)

        self._watchers = []
        self._running = False
        team = self._team
        self._team = None
        self._started_at = None
        self._projects_watched = []

        logger.info("Watcher stopped (was team=%s)", team)
        return self.status()
