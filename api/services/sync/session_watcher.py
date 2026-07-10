"""Filesystem watcher for automatic session packaging."""

import logging
import threading
from pathlib import Path
from typing import Callable, Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)


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
        except Exception:
            logger.exception("Packaging error during watch")

    def start(self):
        """Start watching the directory."""
        self._observer = Observer()
        self._observer.schedule(self, str(self.watch_dir), recursive=True)
        self._observer.daemon = True
        self._observer.start()

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
