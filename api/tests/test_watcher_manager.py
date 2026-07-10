"""Tests for the in-process watcher manager."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.watcher_manager import WatcherManager


class TestWatcherManager:
    def test_status_when_not_running(self):
        mgr = WatcherManager()
        status = mgr.status()
        assert status["running"] is False
        assert status["teams"] == []
        assert status["started_at"] is None
        assert status["last_packaged_at"] is None
        assert status["projects_watched"] == []

    def test_is_running_default_false(self):
        mgr = WatcherManager()
        assert mgr.is_running is False

    def test_cannot_start_twice(self):
        mgr = WatcherManager()
        mgr._running = True
        mgr._teams = ["existing"]

        with pytest.raises(ValueError, match="already running"):
            mgr.start("another", {"teams": {"another": {"projects": {}}}})

    def test_stop_cleans_up(self):
        mgr = WatcherManager()
        mock_w1 = MagicMock()
        mock_w2 = MagicMock()
        mgr._running = True
        mgr._teams = ["test"]
        mgr._watchers = [mock_w1, mock_w2]
        mgr._projects_watched = ["proj1"]
        mgr._started_at = "2026-03-06T00:00:00Z"

        result = mgr.stop()

        assert result["running"] is False
        assert result["teams"] == []
        assert not mgr.is_running
        mock_w1.stop.assert_called_once()
        mock_w2.stop.assert_called_once()

    def test_stop_handles_watcher_errors(self):
        mgr = WatcherManager()
        mock_w = MagicMock()
        mock_w.stop.side_effect = RuntimeError("boom")
        mgr._running = True
        mgr._teams = ["test"]
        mgr._watchers = [mock_w]

        # Should not raise
        result = mgr.stop()
        assert result["running"] is False

    def test_stop_when_not_running(self):
        mgr = WatcherManager()
        result = mgr.stop()
        assert result["running"] is False
