"""Tests for filesystem session watcher."""

import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from karma.watcher import SessionWatcher


class TestSessionWatcher:
    def test_init(self):
        packager_fn = MagicMock()
        watcher = SessionWatcher(
            watch_dir=Path("/tmp/test"),
            package_fn=packager_fn,
            debounce_seconds=2,
        )
        assert watcher.debounce_seconds == 2
        assert watcher.watch_dir == Path("/tmp/test")

    def test_should_process_jsonl(self):
        watcher = SessionWatcher(
            watch_dir=Path("/tmp"),
            package_fn=MagicMock(),
        )
        assert watcher._should_process("/tmp/abc123.jsonl") is True
        assert watcher._should_process("/tmp/agent-xyz.jsonl") is False
        assert watcher._should_process("/tmp/readme.txt") is False
        assert watcher._should_process("/tmp/subdir/file.jsonl") is True

    def test_debounce_calls_package_fn_once(self):
        packager_fn = MagicMock()
        watcher = SessionWatcher(
            watch_dir=Path("/tmp"),
            package_fn=packager_fn,
            debounce_seconds=0.1,
        )
        # Simulate rapid file changes
        watcher._schedule_package()
        watcher._schedule_package()
        watcher._schedule_package()
        time.sleep(0.3)
        # Should only call once despite 3 triggers
        assert packager_fn.call_count == 1

    def test_is_running_property(self):
        watcher = SessionWatcher(
            watch_dir=Path("/tmp"),
            package_fn=MagicMock(),
        )
        assert watcher.is_running is False
