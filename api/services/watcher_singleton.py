"""Process-wide WatcherManager singleton.

The lifespan startup creates one WatcherManager; routers need to read its
status (reconciliation worker + Syncthing event stream health) without
threading it through every dependency. One instance per API process.
"""
from __future__ import annotations

from services.watcher_manager import WatcherManager

_manager: WatcherManager | None = None


def get_watcher_manager() -> WatcherManager:
    global _manager
    if _manager is None:
        _manager = WatcherManager()
    return _manager
