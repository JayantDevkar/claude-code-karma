"""In-process session watcher manager.

Runs the same SessionWatcher + SessionPackager logic as `karma watch`,
but as a background service managed by the API process.

Also provides RemoteSessionWatcher for monitoring incoming Syncthing files
in ~/.claude_karma/remote-sessions/ and triggering remote reindex.
"""
from __future__ import annotations

import asyncio
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)



class RemoteSessionWatcher(FileSystemEventHandler):
    """Watches ~/.claude_karma/remote-sessions/ for incoming Syncthing files.

    When JSONL session files are created or modified (by Syncthing syncing from
    a teammate's outbox), debounces and then calls trigger_remote_reindex() to
    import the new sessions into the local SQLite database.

    Uses the same debounce pattern as cli/karma/watcher.py SessionWatcher.
    """

    def __init__(self, watch_dir: Path, debounce_seconds: float = 5.0):
        self.watch_dir = Path(watch_dir)
        self.debounce_seconds = debounce_seconds
        self._timer: Optional[threading.Timer] = None
        self._observer: Optional[Observer] = None
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._observer is not None and self._observer.is_alive()

    def _should_process(self, path: str) -> bool:
        """Only process session JSONL files in remote-sessions/ or karma-out-- inbox dirs.

        Skips agent files, Syncthing temp files, and our own sendonly outbox
        files (those are outgoing, not incoming).
        """
        p = Path(path)
        if ".stversions" in p.parts or ".stfolder" in p.parts:
            return False
        if p.name.startswith(".syncthing."):
            return False
        if ".sync-conflict-" in p.name:
            return False
        if p.suffix != ".jsonl" or p.name.startswith("agent-"):
            return False
        # Only trigger on files inside remote-sessions/ or karma-out-- dirs
        parts_str = str(p)
        if "remote-sessions" in parts_str:
            return True
        if "karma-out--" in parts_str:
            return True
        return False

    def on_created(self, event):
        if self._should_process(event.src_path):
            self._schedule_reindex()

    def on_modified(self, event):
        if self._should_process(event.src_path):
            self._schedule_reindex()

    def _schedule_reindex(self):
        """Debounced reindex -- waits for quiet period before running."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(
                self.debounce_seconds, self._do_reindex
            )
            self._timer.daemon = True
            self._timer.start()

    def _do_reindex(self):
        """Execute trigger_remote_reindex()."""
        try:
            from db.indexer import trigger_remote_reindex

            result = trigger_remote_reindex()
            logger.info("Remote session watcher triggered reindex: %s", result)
        except Exception as e:
            logger.warning("Remote session watcher reindex error: %s", e)

    def start(self):
        """Start watching the remote-sessions directory.

        Creates the watch directory if it doesn't exist yet (it may be
        created later when Syncthing sync is first configured).
        """
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self._observer = Observer()
        self._observer.schedule(self, str(self.watch_dir), recursive=True)
        self._observer.daemon = True
        self._observer.start()
        logger.info(
            "Remote session watcher started: %s", self.watch_dir
        )

    def stop(self):
        """Stop watching."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
        logger.info("Remote session watcher stopped")


class ReconciliationTimer:
    """Periodic timer that runs v4 3-phase reconciliation every N seconds.

    Uses ReconciliationService.run_cycle() which handles:
      Phase 1 (metadata): member/project discovery, removal signals, auto-leave
      Phase 2 (mesh pair): ensure Syncthing devices are paired
      Phase 3 (device lists): declarative folder device-list sync

    H1 fix preserved: dedicated SQLite connection per timer thread.
    """

    def __init__(self, config_data: dict, interval: float = 60.0):
        self._config_data = config_data
        self._interval = interval
        self._timer: Optional[threading.Timer] = None
        self._running = False

    def start(self):
        self._running = True
        self._schedule()
        logger.info("Reconciliation timer started (interval=%ds)", self._interval)

    def _schedule(self):
        if not self._running:
            return
        self._timer = threading.Timer(self._interval, self._run)
        self._timer.daemon = True
        self._timer.start()

    def _run(self):
        try:
            self._reconcile()
        except Exception as e:
            logger.warning("Reconciliation cycle failed: %s", e)
        finally:
            self._schedule()

    def _reconcile(self):
        """Run ReconciliationService.run_cycle() with a dedicated connection."""
        from models.sync_config import SyncConfig

        config = SyncConfig.load()
        if config is None:
            logger.debug("Reconciliation skipped: not initialized")
            return

        # H1 fix: dedicated connection per timer thread
        from db.connection import get_db_path, _apply_pragmas

        db_path = get_db_path()
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        _apply_pragmas(conn, readonly=False)

        try:
            # Build v4 service stack
            from config import settings as app_settings
            from repositories.team_repo import TeamRepository
            from repositories.member_repo import MemberRepository
            from repositories.project_repo import ProjectRepository
            from repositories.subscription_repo import SubscriptionRepository
            from repositories.event_repo import EventRepository
            from services.syncthing.client import SyncthingClient
            from services.syncthing.device_manager import DeviceManager
            from services.syncthing.folder_manager import FolderManager
            from services.sync.metadata_service import MetadataService
            from services.sync.reconciliation_service import ReconciliationService

            api_key = config.syncthing.api_key if config.syncthing else ""
            client = SyncthingClient(
                api_url="http://localhost:8384", api_key=api_key,
            )
            devices = DeviceManager(client)
            folders = FolderManager(client, karma_base=app_settings.karma_base)
            metadata = MetadataService(
                meta_base=app_settings.karma_base / "metadata-folders",
            )
            repos = dict(
                teams=TeamRepository(),
                members=MemberRepository(),
                projects=ProjectRepository(),
                subs=SubscriptionRepository(),
                events=EventRepository(),
            )
            recon = ReconciliationService(
                **repos,
                devices=devices,
                folders=folders,
                metadata=metadata,
                my_member_tag=config.member_tag,
                my_device_id=config.syncthing.device_id if config.syncthing else "",
            )

            # Run the async 3-phase pipeline with 120s timeout
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(
                    asyncio.wait_for(recon.run_cycle(conn), timeout=120)
                )
            except asyncio.TimeoutError:
                logger.warning("Reconciliation timed out after 120s")
            finally:
                loop.close()
        finally:
            conn.close()

    def stop(self):
        self._running = False
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        logger.info("Reconciliation timer stopped")


class WatcherManager:
    """Manages SessionWatcher instances across one or more teams."""

    def __init__(self) -> None:
        self._running = False
        self._teams: list[str] = []
        self._watchers: list = []
        self._started_at: Optional[str] = None
        self._last_packaged_at: Optional[str] = None
        self._projects_watched: list[str] = []
        self._remote_watcher: Optional[RemoteSessionWatcher] = None
        self._metadata_timer: Optional[ReconciliationTimer] = None

    @property
    def is_running(self) -> bool:
        return self._running

    def status(self) -> dict[str, Any]:
        return {
            "running": self._running,
            "teams": self._teams,
            "started_at": self._started_at,
            "last_packaged_at": self._last_packaged_at,
            "projects_watched": self._projects_watched,
            "remote_watcher_running": (
                self._remote_watcher is not None
                and self._remote_watcher.is_running
            ),
        }

    def start_all(self, config_data: dict) -> dict[str, Any]:
        """Start watchers for all projects across all teams.

        Deduplicates projects by encoded_name so each directory is watched
        only once, even if the same project appears in multiple teams.

        Args:
            config_data: Full config dict with "teams", "user_id", "machine_id".

        Returns:
            Current status dict.
        """
        if self._running:
            raise ValueError(
                f"Watcher already running for team(s) {self._teams!r}"
            )

        from services.sync.session_watcher import SessionWatcher
        from services.sync.worktree_discovery import find_worktree_dirs

        all_teams = config_data.get("teams", {})
        user_id = config_data.get("user_id", "unknown")
        machine_id = config_data.get("machine_id", "unknown")
        device_id = config_data.get("device_id")
        member_tag = config_data.get("member_tag")
        projects_dir = Path.home() / ".claude" / "projects"

        # Collect unique projects across all teams, tracking which teams each belongs to
        # Key: encoded_name -> {"proj": proj_dict, "teams": [team_names]}
        unique_projects: dict[str, dict[str, Any]] = {}
        team_names: list[str] = []

        for team_name, team_cfg in all_teams.items():
            team_names.append(team_name)
            projects = team_cfg.get("projects", {})
            for proj_name, proj in projects.items():
                encoded = proj.get("encoded_name", proj_name)
                if encoded not in unique_projects:
                    unique_projects[encoded] = {
                        "proj": proj,
                        "proj_name": proj_name,
                        "teams": [team_name],
                    }
                else:
                    if team_name not in unique_projects[encoded]["teams"]:
                        unique_projects[encoded]["teams"].append(team_name)

        watchers = []
        watched = []
        initial_package_fns = []

        for encoded, info in unique_projects.items():
            proj = info["proj"]
            proj_name = info["proj_name"]
            proj_teams = info["teams"]
            claude_dir = projects_dir / encoded

            if not claude_dir.is_dir():
                logger.warning("Skipping %s: dir not found %s", proj_name, claude_dir)
                continue

            def make_package_fn(
                en=encoded, pt=proj_teams,
                ps=proj.get("folder_suffix", encoded),
                gi=proj.get("git_identity", encoded),
            ):
                def package():
                    from db.connection import get_writer_db
                    from services.sync.packaging_service import PackagingService

                    db = get_writer_db()
                    svc = PackagingService(
                        member_tag=member_tag or user_id,
                        user_id=user_id,
                        machine_id=machine_id,
                        device_id=device_id,
                    )
                    for tn in pt:
                        svc.package_project(
                            db,
                            team_name=tn,
                            git_identity=gi,
                            encoded_name=en,
                            folder_suffix=ps,
                        )
                    self._last_packaged_at = (
                        datetime.now(timezone.utc).isoformat()
                    )
                return package

            pkg_fn = make_package_fn()
            watcher = SessionWatcher(
                watch_dir=claude_dir,
                package_fn=pkg_fn,
            )
            watcher.start()
            watchers.append(watcher)
            watched.append(proj_name)
            initial_package_fns.append((proj_name, pkg_fn))

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
        self._teams = team_names
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._projects_watched = watched

        # Initial sync: package all existing sessions in a background thread
        # so pre-existing and missed sessions are staged for sending immediately.
        if initial_package_fns:
            def _initial_sync():
                for proj_name, pkg_fn in initial_package_fns:
                    try:
                        pkg_fn()
                    except Exception as e:
                        logger.warning("Initial package failed for %s: %s", proj_name, e)
                logger.info("Initial sync complete: packaged %d project(s)", len(initial_package_fns))

            t = threading.Thread(target=_initial_sync, daemon=True, name="initial-sync")
            t.start()

        # Start metadata reconciliation timer (~60s periodic)
        if self._metadata_timer is None:
            try:
                self._metadata_timer = ReconciliationTimer(config_data)
                self._metadata_timer.start()
            except Exception as e:
                logger.warning("Failed to start metadata reconciliation timer: %s", e)

        # Start remote session watcher (for incoming Syncthing files)
        if self._remote_watcher is None or not self._remote_watcher.is_running:
            try:
                from config import settings

                remote_dir = settings.karma_base / "remote-sessions"
                self._remote_watcher = RemoteSessionWatcher(
                    watch_dir=remote_dir
                )
                self._remote_watcher.start()
            except Exception as e:
                logger.warning(
                    "Failed to start remote session watcher: %s", e
                )

        logger.info(
            "Watcher started: teams=%s, projects=%d, watchers=%d",
            team_names, len(watched), len(watchers),
        )
        return self.status()

    def start(self, team_name: str, config_data: dict) -> dict[str, Any]:
        """Start watchers for all projects in the given team.

        Backward-compatible wrapper around start_all(). Filters config_data
        to only the specified team, then delegates to start_all().
        """
        # Filter config_data to only the specified team
        all_teams = config_data.get("teams", {})
        if team_name not in all_teams:
            raise ValueError(f"Team '{team_name}' not found in config_data")

        filtered_config = {
            **config_data,
            "teams": {team_name: all_teams[team_name]},
        }
        return self.start_all(filtered_config)

    def stop(self) -> dict[str, Any]:
        """Stop all watchers (including remote session watcher)."""
        for w in self._watchers:
            try:
                w.stop()
            except Exception as e:
                logger.warning("Error stopping watcher: %s", e)

        if self._metadata_timer is not None:
            try:
                self._metadata_timer.stop()
            except Exception as e:
                logger.warning("Error stopping metadata timer: %s", e)
            self._metadata_timer = None

        if self._remote_watcher is not None:
            try:
                self._remote_watcher.stop()
            except Exception as e:
                logger.warning("Error stopping remote watcher: %s", e)
            self._remote_watcher = None

        self._watchers = []
        self._running = False
        teams = self._teams
        self._teams = []
        self._started_at = None
        self._projects_watched = []

        logger.info("Watcher stopped (was teams=%s)", teams)
        return self.status()
