"""Tests for event-driven reconciliation (SyncthingEventListener + trigger)."""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from unittest.mock import patch

_api_dir = Path(__file__).resolve().parent.parent
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

from services.watcher_manager import ReconciliationTimer, SyncthingEventListener


# ---------------------------------------------------------------------------
# SyncthingEventListener._reason_for — event filtering
# ---------------------------------------------------------------------------


class TestReasonFor:
    def _listener(self):
        return SyncthingEventListener(
            api_url="http://localhost:8384", api_key="k", on_trigger=lambda r: None
        )

    def test_pending_devices_triggers(self):
        assert (
            self._listener()._reason_for({"type": "PendingDevicesChanged", "data": {}})
            == "PendingDevicesChanged"
        )

    def test_pending_folders_triggers(self):
        assert (
            self._listener()._reason_for({"type": "PendingFoldersChanged", "data": {}})
            == "PendingFoldersChanged"
        )

    def test_device_connected_triggers(self):
        assert (
            self._listener()._reason_for({"type": "DeviceConnected", "data": {}})
            == "DeviceConnected"
        )

    def test_config_saved_triggers(self):
        assert (
            self._listener()._reason_for({"type": "ConfigSaved", "data": {}})
            == "ConfigSaved"
        )

    def test_item_finished_metadata_folder_triggers(self):
        reason = self._listener()._reason_for(
            {"type": "ItemFinished", "data": {"folder": "karma-meta--team1"}}
        )
        assert reason == "ItemFinished:karma-meta--team1"

    def test_item_finished_outbox_folder_ignored(self):
        assert (
            self._listener()._reason_for(
                {"type": "ItemFinished", "data": {"folder": "karma-out--a.b--repo"}}
            )
            is None
        )

    def test_folder_completion_metadata_triggers(self):
        reason = self._listener()._reason_for(
            {"type": "FolderCompletion", "data": {"folder": "karma-meta--t"}}
        )
        assert reason == "FolderCompletion:karma-meta--t"

    def test_folder_completion_non_karma_ignored(self):
        assert (
            self._listener()._reason_for(
                {"type": "FolderCompletion", "data": {"folder": "photos"}}
            )
            is None
        )

    def test_unknown_event_ignored(self):
        assert self._listener()._reason_for({"type": "LocalIndexUpdated"}) is None


# ---------------------------------------------------------------------------
# SyncthingEventListener._loop — long-poll behaviour (mocked requests)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


class TestListenerLoop:
    def test_positions_then_triggers_on_new_events(self):
        """First poll (limit=1) only positions; later events fire the callback."""
        triggered = []
        listener = SyncthingEventListener(
            api_url="http://localhost:8384",
            api_key="k",
            on_trigger=triggered.append,
        )

        polls = []

        def fake_get(url, params=None, headers=None, timeout=None):
            polls.append(dict(params))
            if len(polls) == 1:
                # positioning poll
                return _FakeResponse([{"id": 41, "type": "ConfigSaved", "data": {}}])
            if len(polls) == 2:
                return _FakeResponse(
                    [{"id": 42, "type": "PendingFoldersChanged", "data": {}}]
                )
            listener._running = False
            return _FakeResponse([])

        with patch.dict(sys.modules, {}):
            with patch("requests.get", side_effect=fake_get):
                listener._running = True
                listener._loop()

        assert polls[0].get("limit") == 1  # positioning
        assert polls[1]["since"] == 41  # resumed after latest buffered event
        assert triggered == ["PendingFoldersChanged"]
        assert listener.events_seen == 1

    def test_burst_collapses_to_single_trigger(self):
        triggered = []
        listener = SyncthingEventListener(
            api_url="http://localhost:8384",
            api_key="k",
            on_trigger=triggered.append,
        )
        polls = []

        def fake_get(url, params=None, headers=None, timeout=None):
            polls.append(1)
            if len(polls) == 1:
                return _FakeResponse([])
            if len(polls) == 2:
                return _FakeResponse(
                    [
                        {"id": 1, "type": "DeviceConnected", "data": {}},
                        {"id": 2, "type": "ConfigSaved", "data": {}},
                    ]
                )
            listener._running = False
            return _FakeResponse([])

        with patch("requests.get", side_effect=fake_get):
            listener._running = True
            listener._loop()

        assert triggered == ["burst"]

    def test_connection_error_sets_disconnected_and_repositions(self):
        listener = SyncthingEventListener(
            api_url="http://localhost:8384",
            api_key="k",
            on_trigger=lambda r: None,
        )
        listener.ERROR_BACKOFF_SECS = 0.01
        polls = []

        def fake_get(url, params=None, headers=None, timeout=None):
            polls.append(dict(params))
            if len(polls) == 1:
                return _FakeResponse([{"id": 7, "type": "ConfigSaved", "data": {}}])
            if len(polls) == 2:
                raise ConnectionError("syncthing down")
            # Third poll: still down; stop the loop so we can observe the
            # disconnected state.
            listener._running = False
            raise ConnectionError("still down")

        with patch("requests.get", side_effect=fake_get):
            listener._running = True
            listener._loop()

        assert listener.connected is False
        # After the error, polling re-positions (limit=1 again)
        assert polls[2].get("limit") == 1


# ---------------------------------------------------------------------------
# ReconciliationTimer.trigger — debounced immediate reconcile
# ---------------------------------------------------------------------------


class TestTimerTrigger:
    def _make_timer(self, reconcile_calls):
        timer = ReconciliationTimer(config_data={}, interval=999)
        timer.DEBOUNCE_SECS = 0.05

        def fake_reconcile():
            reconcile_calls.append(time.monotonic())

        timer._reconcile = fake_reconcile
        return timer

    def test_trigger_runs_reconcile_promptly(self):
        calls: list[float] = []
        timer = self._make_timer(calls)
        timer.start()
        try:
            t0 = time.monotonic()
            timer.trigger("PendingFoldersChanged")
            deadline = time.monotonic() + 2
            while not calls and time.monotonic() < deadline:
                time.sleep(0.01)
            assert calls, "reconcile did not run after trigger"
            assert calls[0] - t0 < 1.5  # far below the 999s fallback interval
            assert timer.last_run_reason == "PendingFoldersChanged"
            assert timer.last_run_ok is True
            assert timer.runs_total == 1
        finally:
            timer.stop()

    def test_burst_of_triggers_coalesces(self):
        calls: list[float] = []
        timer = self._make_timer(calls)
        timer.start()
        try:
            for _ in range(5):
                timer.trigger("ConfigSaved")
                time.sleep(0.005)
            deadline = time.monotonic() + 2
            while not calls and time.monotonic() < deadline:
                time.sleep(0.01)
            time.sleep(0.2)  # allow any (incorrect) extra runs to surface
            assert len(calls) == 1
        finally:
            timer.stop()

    def test_failed_reconcile_records_not_ok(self):
        timer = ReconciliationTimer(config_data={}, interval=999)
        timer.DEBOUNCE_SECS = 0.01

        def boom():
            raise RuntimeError("nope")

        timer._reconcile = boom
        timer.start()
        try:
            timer.trigger("x")
            deadline = time.monotonic() + 2
            while timer.runs_total == 0 and time.monotonic() < deadline:
                time.sleep(0.01)
            assert timer.runs_total == 1
            assert timer.last_run_ok is False
        finally:
            timer.stop()

    def test_stop_unblocks_worker(self):
        timer = ReconciliationTimer(config_data={}, interval=999)
        timer._reconcile = lambda: None
        timer.start()
        thread = timer._thread
        timer.stop()
        assert thread is not None
        thread.join(timeout=2)
        assert not thread.is_alive()
