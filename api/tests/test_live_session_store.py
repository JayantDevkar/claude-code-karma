"""Tests for ``services.live_session_store``.

Cover the write/mark_ended/delete/purge primitives that the hook script,
reconciler, and router cleanup endpoints now all funnel through.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from services import live_session_store


@pytest.fixture
def tmp_live_dir(tmp_path: Path, monkeypatch):
    """Redirect the live-sessions directory to a tmp path."""
    live_dir = tmp_path / "live-sessions"
    live_dir.mkdir()
    monkeypatch.setattr(live_session_store, "get_live_sessions_dir", lambda: live_dir)
    return live_dir


def test_write_state_creates_file(tmp_live_dir: Path):
    result = live_session_store.write_state(
        "sess-1",
        state="LIVE",
        cwd="/tmp",
    )
    path = tmp_live_dir / "sess-1.json"
    assert path.exists()
    written = json.loads(path.read_text())
    assert written["session_id"] == "sess-1"
    assert written["state"] == "LIVE"
    assert "updated_at" in written
    assert result == written


def test_write_state_merges_into_existing(tmp_live_dir: Path):
    live_session_store.write_state("sess-2", state="STARTING", cwd="/tmp", started_at="x")
    live_session_store.write_state("sess-2", state="LIVE")
    data = json.loads((tmp_live_dir / "sess-2.json").read_text())
    assert data["state"] == "LIVE"
    assert data["cwd"] == "/tmp"  # preserved
    assert data["started_at"] == "x"  # preserved


def test_mark_ended_sets_terminal_fields(tmp_live_dir: Path):
    live_session_store.write_state("sess-3", state="LIVE", cwd="/tmp")
    live_session_store.mark_ended("sess-3", end_reason="session_handoff", last_hook="Reconciler")
    data = json.loads((tmp_live_dir / "sess-3.json").read_text())
    assert data["state"] == "ENDED"
    assert data["end_reason"] == "session_handoff"
    assert data["last_hook"] == "Reconciler"


def test_delete_state_returns_true_on_success(tmp_live_dir: Path):
    live_session_store.write_state("sess-4", state="LIVE")
    assert live_session_store.delete_state("sess-4") is True
    assert not (tmp_live_dir / "sess-4.json").exists()


def test_delete_state_returns_false_when_missing(tmp_live_dir: Path):
    assert live_session_store.delete_state("nope") is False


def test_delete_by_identifier_finds_via_slug(tmp_live_dir: Path):
    # Legacy file named by slug
    legacy = tmp_live_dir / "happy-slug.json"
    legacy.write_text(
        json.dumps(
            {
                "session_id": "uuid-xyz",
                "slug": "happy-slug",
                "state": "LIVE",
            }
        )
    )
    # Lookup by session_id should still find it
    assert live_session_store.delete_by_identifier("uuid-xyz") is True
    assert not legacy.exists()


def test_purge_old_files_deletes_old_ended(tmp_live_dir: Path):
    old_ts = (datetime.now(timezone.utc) - timedelta(seconds=1200)).isoformat()
    fresh_ts = datetime.now(timezone.utc).isoformat()

    (tmp_live_dir / "old.json").write_text(
        json.dumps({"session_id": "old", "state": "ENDED", "updated_at": old_ts})
    )
    (tmp_live_dir / "fresh.json").write_text(
        json.dumps({"session_id": "fresh", "state": "ENDED", "updated_at": fresh_ts})
    )
    (tmp_live_dir / "live.json").write_text(
        json.dumps({"session_id": "live", "state": "LIVE", "updated_at": old_ts})
    )

    deleted = live_session_store.purge_old_files(ended_max_age_sec=600)
    assert deleted == 1
    assert not (tmp_live_dir / "old.json").exists()
    assert (tmp_live_dir / "fresh.json").exists()
    assert (tmp_live_dir / "live.json").exists()  # LIVE never purged


def test_purge_old_files_deletes_stuck_starting(tmp_live_dir: Path):
    old_ts = (datetime.now(timezone.utc) - timedelta(seconds=1200)).isoformat()
    (tmp_live_dir / "stuck.json").write_text(
        json.dumps({"session_id": "stuck", "state": "STARTING", "updated_at": old_ts})
    )
    assert live_session_store.purge_old_files(starting_max_age_sec=600) == 1
    assert not (tmp_live_dir / "stuck.json").exists()


def test_purge_old_files_no_dir_returns_zero(tmp_path: Path, monkeypatch):
    missing = tmp_path / "does-not-exist"
    monkeypatch.setattr(live_session_store, "get_live_sessions_dir", lambda: missing)
    assert live_session_store.purge_old_files() == 0


def test_write_state_requires_session_id(tmp_live_dir: Path):
    with pytest.raises(ValueError):
        live_session_store.write_state("", state="LIVE")


def test_reconciler_mark_uses_store(tmp_live_dir: Path):
    """`session_reconciler._mark_session_ended` should route through the store."""
    live_session_store.write_state("sess-r", state="LIVE", cwd="/tmp")

    from services.session_reconciler import _mark_session_ended

    # _mark_session_ended derives the session_id from state_data (or the
    # filename stem) and calls live_session_store.mark_ended.
    state_file = tmp_live_dir / "sess-r.json"
    with patch("services.session_reconciler.live_session_store.mark_ended") as mock_ended:
        _mark_session_ended(state_file, {"session_id": "sess-r"}, end_reason="x")
        mock_ended.assert_called_once_with("sess-r", end_reason="x", last_hook="Reconciler")
