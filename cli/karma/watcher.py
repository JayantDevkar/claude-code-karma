"""Filesystem watcher for automatic session packaging."""

import logging
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)

PEER_CHECK_INTERVAL = 300  # 5 minutes


class SessionWatcher(FileSystemEventHandler):
    """Watches Claude project dirs for JSONL changes and triggers packaging."""

    def __init__(
        self,
        watch_dir: Path,
        package_fn: Callable[[], None],
        debounce_seconds: float = 5.0,
    ):
        self.watch_dir = Path(watch_dir)
        self.package_fn = package_fn
        self.debounce_seconds = debounce_seconds
        self._timer: Optional[threading.Timer] = None
        self._observer: Optional[Observer] = None
        self._lock = threading.Lock()
        self._last_peer_check: float = 0.0
        self._peer_timer: Optional[threading.Timer] = None

    @property
    def is_running(self) -> bool:
        return self._observer is not None and self._observer.is_alive()

    def _should_process(self, path: str) -> bool:
        """Only process session JSONL files (not agent files)."""
        p = Path(path)
        return p.suffix == ".jsonl" and not p.name.startswith("agent-")

    def on_modified(self, event):
        if self._should_process(event.src_path):
            self._schedule_package()

    def on_created(self, event):
        if self._should_process(event.src_path):
            self._schedule_package()

    def _schedule_package(self):
        """Debounced packaging — waits for quiet period before running."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self.debounce_seconds, self._do_package)
            self._timer.daemon = True
            self._timer.start()

    def _do_package(self):
        """Execute the packaging function."""
        try:
            self.package_fn()
        except Exception as e:
            print(f"[karma watch] Packaging error: {e}", file=sys.stderr)

    def _maybe_check_peers(self):
        """Check for new team members periodically."""
        now = time.time()
        if now - self._last_peer_check < PEER_CHECK_INTERVAL:
            return 0

        self._last_peer_check = now
        try:
            from karma.main import _accept_pending_folders
            from karma.syncthing import SyncthingClient, read_local_api_key
            from karma.config import SyncConfig

            config = SyncConfig.load()
            if not config:
                return 0
            api_key = config.syncthing.api_key or read_local_api_key()
            st = SyncthingClient(api_key=api_key)
            if not st.is_running():
                return 0

            import sqlite3
            from api.config import settings

            conn = sqlite3.connect(str(settings.sqlite_db_path))
            conn.row_factory = sqlite3.Row
            try:
                accepted = _accept_pending_folders(st, config, conn)
                return accepted or 0
            finally:
                conn.close()
        except Exception as e:
            logger.debug("Peer check failed: %s", e)
            return 0

    def _schedule_peer_check(self):
        """Schedule the next periodic peer check."""
        self._peer_timer = threading.Timer(PEER_CHECK_INTERVAL, self._run_peer_check)
        self._peer_timer.daemon = True
        self._peer_timer.start()

    def _run_peer_check(self):
        """Run peer check and reschedule."""
        self._maybe_check_peers()
        if self._observer is not None and self._observer.is_alive():
            self._schedule_peer_check()

    def start(self):
        """Start watching the directory."""
        self._observer = Observer()
        self._observer.schedule(self, str(self.watch_dir), recursive=True)
        self._observer.daemon = True
        self._observer.start()
        # Start periodic peer discovery
        self._schedule_peer_check()

    def stop(self):
        """Stop watching."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None
        if self._peer_timer is not None:
            self._peer_timer.cancel()
            self._peer_timer = None
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None
