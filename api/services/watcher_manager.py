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
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)

# Add CLI to path
_CLI_PATH = Path(__file__).parent.parent.parent / "cli"
if str(_CLI_PATH) not in sys.path:
    sys.path.insert(0, str(_CLI_PATH))


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
        """Only process session JSONL files (not agent files or Syncthing temp files)."""
        p = Path(path)
        if ".stversions" in p.parts:
            return False
        if p.name.startswith(".syncthing."):
            return False
        if ".sync-conflict-" in p.name:
            return False
        return p.suffix == ".jsonl" and not p.name.startswith("agent-")

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


class MetadataReconciliationTimer:
    """Periodic timer that runs metadata folder reconciliation every N seconds.

    Discovers new members, updates identity columns, and triggers auto-leave
    when removal signals are detected.
    """

    def __init__(self, config_data: dict, interval: float = 60.0):
        self._config_data = config_data
        self._interval = interval
        self._timer: Optional[threading.Timer] = None
        self._running = False
        self._first_cycle = True

    def start(self):
        self._running = True
        self._schedule()
        logger.info("Metadata reconciliation timer started (interval=%ds)", self._interval)

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
            logger.warning("Metadata reconciliation failed: %s", e)
        finally:
            self._schedule()

    def _reconcile(self):
        from db.connection import get_db_path, _apply_pragmas
        from services.sync_metadata_reconciler import reconcile_all_teams_metadata

        # Build a minimal config object from config_data
        config = _ConfigProxy(self._config_data)

        # H1 fix: Create a dedicated connection for the timer thread.
        # Avoids sharing the writer singleton across threads without a mutex,
        # which can cause interleaved transactions and data corruption.
        db_path = get_db_path()
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        _apply_pragmas(conn, readonly=False)

        try:
            # RC-2: On first cycle, resume any interrupted auto-leave cleanup
            if self._first_cycle:
                self._first_cycle = False
                self._resume_pending_leaves(config, conn)

            # Phase 0: Metadata folder reconciliation (member discovery, auto-leave)
            result = reconcile_all_teams_metadata(config, conn, auto_leave=True)
            if result["members_added"] or result["self_removed_teams"]:
                logger.info(
                    "Metadata reconciliation: added=%d, auto-left=%s",
                    result["members_added"], result["self_removed_teams"],
                )

            # Phases 1-4: Async reconciliation pipeline (each phase independent)
            self._run_async_phases(config, conn)

            # Phase 5: Accept pending folders (auto_only=True — skip peer outboxes)
            self._auto_accept_pending_folders(config, conn)
        finally:
            conn.close()

    def _resume_pending_leaves(self, config, conn):
        """RC-2: Resume interrupted auto-leave cleanup on startup."""
        try:
            from db.sync_queries import get_teams_with_pending_leave
            from services.sync_metadata_reconciler import _auto_leave_team

            pending = get_teams_with_pending_leave(conn)
            for team in pending:
                team_name = team["name"]
                logger.info("RC-2: Resuming pending_leave cleanup for team %s", team_name)
                try:
                    _auto_leave_team(config, conn, team_name)
                except Exception as e:
                    logger.warning("RC-2: Failed to resume auto-leave for %s: %s", team_name, e)
        except Exception as e:
            logger.debug("RC-2: pending_leave check failed: %s", e)

    def _run_async_phases(self, config, conn):
        """Run phases 1-4 of the async reconciliation pipeline.

        Each phase is independent — failure in one does not block others.
        Uses asyncio.new_event_loop() pattern (same as _auto_share_with_new_members
        in sync_metadata_reconciler.py).

        H2 fix: All phases run inside a single async function with a 120s overall
        timeout, preventing indefinite blocking if a Syncthing API call hangs.
        """
        try:
            from services.sync_identity import get_proxy
            proxy = get_proxy()
        except Exception as e:
            logger.debug("Async reconciliation phases skipped (no proxy): %s", e)
            return

        async def _all_phases():
            # Phase 1: Mesh pair from metadata (discover undiscovered devices)
            try:
                from services.sync_reconciliation import mesh_pair_from_metadata
                paired = await mesh_pair_from_metadata(proxy, config, conn)
                if paired:
                    logger.info("Phase 1 mesh_pair: paired with %d new device(s)", paired)
            except Exception as e:
                logger.debug("Phase 1 mesh_pair failed: %s", e)

            # Phase 2: Reconcile pending handshakes (process handshake signals)
            try:
                from services.sync_reconciliation import reconcile_pending_handshakes
                reconciled = await reconcile_pending_handshakes(proxy, config, conn)
                if reconciled:
                    logger.info("Phase 2 handshakes: reconciled %d membership(s)", reconciled)
            except Exception as e:
                logger.debug("Phase 2 handshakes failed: %s", e)

            # Phase 3: Auto-accept pending peers (policy-gated)
            try:
                from services.sync_reconciliation import auto_accept_pending_peers
                accepted, _ = await auto_accept_pending_peers(proxy, config, conn)
                if accepted:
                    logger.info("Phase 3 auto_accept: accepted %d pending peer(s)", accepted)
            except Exception as e:
                logger.debug("Phase 3 auto_accept failed: %s", e)

            # Phase 4: Compute and apply device lists (declarative sync)
            try:
                from services.sync_folders import compute_and_apply_device_lists
                result = await compute_and_apply_device_lists(proxy, config, conn)
                updated = result.get("folders_updated", 0)
                deleted = result.get("folders_deleted", 0)
                if updated or deleted:
                    logger.info(
                        "Phase 4 device_lists: updated=%d, deleted=%d",
                        updated, deleted,
                    )
            except Exception as e:
                logger.debug("Phase 4 device_lists failed: %s", e)

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(asyncio.wait_for(_all_phases(), timeout=120))
        except asyncio.TimeoutError:
            logger.warning("Async reconciliation phases timed out after 120s")
        except Exception as e:
            logger.debug("Async reconciliation phases failed: %s", e)
        finally:
            loop.close()

    def _auto_accept_pending_folders(self, config, conn):
        """Phase 5: Accept pending Syncthing folder offers from known team members.

        Uses auto_only=True to skip peer outboxes (those require explicit user
        acceptance via the UI). Only processes handshake folders and own outbox
        offers automatically.
        """
        try:
            from services.sync_identity import get_proxy

            proxy = get_proxy()
            accepted = proxy.accept_pending_folders(config, conn, auto_only=True)
            if accepted:
                logger.info("Phase 5 accept_folders: auto-accepted %d folder(s)", accepted)
        except Exception as e:
            logger.debug("Phase 5 accept_folders skipped: %s", e)

    def stop(self):
        self._running = False
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        logger.info("Metadata reconciliation timer stopped")


class _ConfigProxy:
    """Minimal config proxy for reconciliation (avoids async _load_identity)."""

    def __init__(self, config_data: dict):
        self.user_id = config_data.get("user_id", "")
        self.machine_id = config_data.get("machine_id", "")
        self.member_tag = config_data.get("member_tag", "")
        self.machine_tag = self.member_tag.split(".", 1)[1] if "." in self.member_tag else ""
        self.syncthing = _SyncthingProxy(config_data.get("device_id"))


class _SyncthingProxy:
    def __init__(self, device_id: Optional[str]):
        self.device_id = device_id


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
        self._metadata_timer: Optional[MetadataReconciliationTimer] = None

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

        from karma.watcher import SessionWatcher
        from karma.packager import SessionPackager
        from karma.worktree_discovery import find_worktree_dirs
        from karma.config import KARMA_BASE

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

            outbox = KARMA_BASE / "remote-sessions" / (member_tag or user_id) / encoded

            def make_package_fn(
                cd=claude_dir, ob=outbox, en=encoded, pp=proj.get("path", ""),
                pt=proj_teams,
            ):
                def package():
                    # Policy gate: skip packaging if send is disabled for ALL teams
                    try:
                        from db.connection import get_writer_db
                        from services.sync_policy import should_send_to
                        db = get_writer_db()
                        if not any(should_send_to(db, tn) for tn in pt):
                            logger.debug("Send disabled for all teams of %s — skipping package", en)
                            return
                    except Exception as exc:
                        logger.warning("Policy check failed for %s, proceeding: %s", en, exc)

                    wt_dirs = find_worktree_dirs(en, projects_dir)
                    packager = SessionPackager(
                        project_dir=cd,
                        user_id=user_id,
                        machine_id=machine_id,
                        device_id=device_id,
                        project_path=pp,
                        extra_dirs=wt_dirs,
                        member_tag=member_tag,
                    )
                    ob.mkdir(parents=True, exist_ok=True)
                    manifest = packager.package(staging_dir=ob)
                    self._last_packaged_at = (
                        datetime.now(timezone.utc).isoformat()
                    )
                    # Log session_packaged per session (dedup against already-logged)
                    try:
                        from db.connection import get_writer_db
                        from db.sync_queries import log_session_packaged_events
                        db = get_writer_db()
                        for tn in pt:
                            log_session_packaged_events(
                                db, tn, en, user_id, manifest.sessions
                            )
                    except Exception:
                        logger.debug("Failed to log session_packaged events", exc_info=True)
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
                self._metadata_timer = MetadataReconciliationTimer(config_data)
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
