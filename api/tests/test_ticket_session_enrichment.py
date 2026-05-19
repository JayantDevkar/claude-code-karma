"""
Tests for api/services/ticket_session_enrichment.py.

Covers:
  - rows with indexed sessions data are returned unchanged (with live=None)
  - rows missing sessions data get filled from live-session state
  - resumed sessions: link UUID found via session_ids[] membership
  - true orphans (no sessions, no live) stay marked as orphan
  - live-sessions read failure doesn't break the pipeline
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

_api_dir = Path(__file__).resolve().parent.parent
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

from models.live_session import LiveSessionState, SessionState
from services.ticket_session_enrichment import (
    _build_uuid_index,
    _find_live_for_uuid,
    enrich_sessions_with_live,
)


def _make_state(
    session_id: str,
    *,
    slug: str = "happy-pioneer",
    state: SessionState = SessionState.LIVE,
    project_encoded: str = "-Users-me-claude-karma",
    session_ids: list[str] | None = None,
    cwd: str = "/Users/me/Documents/GitHub/claude-karma",
) -> LiveSessionState:
    """Build a minimal LiveSessionState for tests.

    The `resolved_project_encoded_name` property derives from
    `transcript_path` via the segment after `/projects/`. We construct a
    transcript_path that yields the desired encoded name so the real
    property logic runs unmodified.
    """
    started = datetime(2026, 5, 13, 14, 36, 0, tzinfo=timezone.utc)
    updated = datetime(2026, 5, 19, 1, 55, 50, tzinfo=timezone.utc)
    transcript_path = f"/Users/me/.claude/projects/{project_encoded}/{session_id}.jsonl"
    return LiveSessionState(
        session_id=session_id,
        session_ids=session_ids or [session_id],
        slug=slug,
        state=state,
        cwd=cwd,
        started_at=started,
        updated_at=updated,
        transcript_path=transcript_path,
        last_hook="SessionStart",
    )


def test_indexed_row_unchanged_live_none():
    """A row that already has sessions_slug stays as-is, gets live=None."""
    rows = [
        {
            "link_id": 1,
            "session_uuid": "uuid-1",
            "sessions_slug": "indexed-slug",
            "project_encoded_name": "-some-project",
            "start_time": "2026-05-10T10:00:00Z",
            "initial_prompt": "build a thing",
        }
    ]

    with patch(
        "services.ticket_session_enrichment.load_all_live_sessions",
        return_value=[],
    ):
        out = enrich_sessions_with_live(rows)

    assert out[0]["sessions_slug"] == "indexed-slug"
    assert out[0]["project_encoded_name"] == "-some-project"
    assert out[0]["initial_prompt"] == "build a thing"
    assert out[0]["live"] is None


def test_orphan_row_gets_live_data():
    """A row with no sessions data + matching live state gets filled in."""
    rows = [
        {
            "link_id": 7,
            "session_uuid": "uuid-live-1",
            "sessions_slug": None,
            "project_encoded_name": None,
            "start_time": None,
            "initial_prompt": None,
        }
    ]
    state = _make_state("uuid-live-1", slug="active-slug")

    with patch(
        "services.ticket_session_enrichment.load_all_live_sessions",
        return_value=[state],
    ):
        out = enrich_sessions_with_live(rows)

    r = out[0]
    assert r["sessions_slug"] == "active-slug"
    assert r["project_encoded_name"] == "-Users-me-claude-karma"
    assert r["start_time"] == "2026-05-13T14:36:00+00:00"
    assert r["initial_prompt"] is None  # intentional — see service docstring
    assert r["live"] is not None
    assert r["live"]["status"] == "LIVE"
    assert r["live"]["cwd"] == "/Users/me/Documents/GitHub/claude-karma"


def test_resumed_session_found_via_session_ids():
    """Link made to an early UUID resolves to the active state via session_ids."""
    rows = [
        {
            "link_id": 9,
            "session_uuid": "uuid-old",
            "sessions_slug": None,
            "project_encoded_name": None,
            "start_time": None,
            "initial_prompt": None,
        }
    ]
    # Current state is under uuid-new, but session_ids tracks the prior resume
    state = _make_state(
        "uuid-new",
        slug="resumed-slug",
        session_ids=["uuid-old", "uuid-new"],
    )

    with patch(
        "services.ticket_session_enrichment.load_all_live_sessions",
        return_value=[state],
    ):
        out = enrich_sessions_with_live(rows)

    assert out[0]["sessions_slug"] == "resumed-slug"
    assert out[0]["live"]["status"] == "LIVE"


def test_true_orphan_stays_orphan():
    """No sessions row, no live state → row left as-is, live=None."""
    rows = [
        {
            "link_id": 5,
            "session_uuid": "uuid-truly-gone",
            "sessions_slug": None,
            "project_encoded_name": None,
            "start_time": None,
            "initial_prompt": None,
        }
    ]

    with patch(
        "services.ticket_session_enrichment.load_all_live_sessions",
        return_value=[],
    ):
        out = enrich_sessions_with_live(rows)

    assert out[0]["sessions_slug"] is None
    assert out[0]["project_encoded_name"] is None
    assert out[0]["live"] is None


def test_live_states_read_failure_does_not_break_enrichment():
    """If load_all_live_sessions raises, the pipeline still returns rows."""
    rows = [
        {
            "link_id": 1,
            "session_uuid": "uuid-x",
            "sessions_slug": None,
            "project_encoded_name": None,
            "start_time": None,
            "initial_prompt": None,
        }
    ]

    with patch(
        "services.ticket_session_enrichment.load_all_live_sessions",
        side_effect=RuntimeError("filesystem broke"),
    ):
        out = enrich_sessions_with_live(rows)

    # Row preserved, live=None, no raise.
    assert out[0]["sessions_slug"] is None
    assert out[0]["live"] is None


def test_fast_path_no_missing_rows_still_scans_zero_times():
    """When all rows are indexed, we skip the directory scan entirely."""
    rows = [
        {"session_uuid": "u1", "sessions_slug": "s1"},
        {"session_uuid": "u2", "sessions_slug": "s2"},
    ]

    with patch(
        "services.ticket_session_enrichment.load_all_live_sessions",
        side_effect=AssertionError("should not be called on the fast path"),
    ):
        out = enrich_sessions_with_live(rows)

    assert all(r["live"] is None for r in out)


def test_indexed_data_not_overwritten():
    """If a row already has start_time, we don't overwrite it with live data."""
    rows = [
        {
            "link_id": 1,
            "session_uuid": "uuid-x",
            "sessions_slug": None,  # triggers enrichment
            "project_encoded_name": None,
            "start_time": "2026-01-01T00:00:00Z",  # already set, must persist
            "initial_prompt": None,
        }
    ]
    state = _make_state("uuid-x", slug="live-slug")

    with patch(
        "services.ticket_session_enrichment.load_all_live_sessions",
        return_value=[state],
    ):
        out = enrich_sessions_with_live(rows)

    assert out[0]["start_time"] == "2026-01-01T00:00:00Z"  # preserved
    assert out[0]["sessions_slug"] == "live-slug"  # was None → filled


def test__find_live_for_uuid_returns_state():
    state = _make_state("uuid-find")
    with patch(
        "services.ticket_session_enrichment.load_all_live_sessions",
        return_value=[state],
    ):
        result = _find_live_for_uuid("uuid-find")

    assert result is state


def test__find_live_for_uuid_missing_returns_none():
    with patch(
        "services.ticket_session_enrichment.load_all_live_sessions",
        return_value=[],
    ):
        assert _find_live_for_uuid("nope") is None


def test_build_uuid_index_current_wins_over_historical():
    """If two states share a UUID — one as current, one as historical —
    the current one wins in the index."""
    current = _make_state("u1", slug="current")
    other = _make_state("u2", slug="other-with-u1-historical", session_ids=["u1", "u2"])
    index = _build_uuid_index([current, other])
    # u1 is the current id of `current`, but also a historical id of `other`.
    # Current must win.
    assert index["u1"].slug == "current"


def test_build_uuid_index_current_wins_regardless_of_input_order():
    """Cross-state collision: u1 is current for state A AND historical for
    state B. The two-pass build must yield A regardless of iteration order.
    Regression test for the ordering-fragility flagged in code review."""
    state_a = _make_state("u1", slug="state-a-current")
    state_b = _make_state("u2", slug="state-b-current", session_ids=["u1", "u2"])

    # Forward order
    forward = _build_uuid_index([state_a, state_b])
    assert forward["u1"].slug == "state-a-current"

    # Reverse order — historical write happens BEFORE the current write
    # for u1. Two-pass guarantees A still wins.
    reverse = _build_uuid_index([state_b, state_a])
    assert reverse["u1"].slug == "state-a-current"
