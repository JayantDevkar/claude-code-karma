"""Live sessions stopped by an API error or usage limit (StopFailure hook)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_tests_dir = Path(__file__).resolve().parent.parent
_api_dir = _tests_dir.parent
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

from models.live_session import LiveSessionState, SessionStatus  # noqa: E402
from routers.live_sessions import (  # noqa: E402
    STARTING_TIMEOUT,
    determine_status,
    state_to_summary,
)

LIMIT_ERROR = {
    "kind": "limit",
    "code": "rate_limit",
    "details": "429 Too Many Requests",
    "message": "You've hit your limit",
    "at": "2026-01-01T10:00:00+00:00",
}


def _iso_ago(seconds: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds)).isoformat()


def _subagent(agent_id: str, status: str, **extra) -> dict:
    return {
        "agent_id": agent_id,
        "agent_type": "Explore",
        "status": status,
        "started_at": _iso_ago(600),
        **extra,
    }


def _load(tmp_path: Path, state: str, idle_seconds: int = 5, **fields) -> LiveSessionState:
    data = {
        "session_id": "s-int-api",
        "state": state,
        "cwd": "/home/alice/project",
        "transcript_path": "/home/alice/.claude/projects/-home-alice-project/s-int-api.jsonl",
        "last_hook": "StopFailure",
        "updated_at": _iso_ago(idle_seconds),
        "started_at": _iso_ago(idle_seconds + 60),
        "session_ids": ["s-int-api"],
        **fields,
    }
    path = tmp_path / "s-int-api.json"
    path.write_text(json.dumps(data))
    return LiveSessionState.from_file(path)


def test_interrupted_never_decays_to_stale(tmp_path):
    state = _load(tmp_path, "INTERRUPTED", idle_seconds=600, stop_error=LIMIT_ERROR)
    assert determine_status(state) == SessionStatus.INTERRUPTED


def test_summary_carries_stop_error(tmp_path):
    summary = state_to_summary(_load(tmp_path, "INTERRUPTED", stop_error=LIMIT_ERROR))
    assert summary.state == "INTERRUPTED"
    assert summary.status == "interrupted"
    assert summary.stop_error["kind"] == "limit"
    assert summary.stop_error["message"] == "You've hit your limit"


def test_running_subagents_of_ended_session_read_interrupted(tmp_path):
    state = _load(
        tmp_path,
        "ENDED",
        subagents={
            "a1": _subagent("a1", "running"),
            "a2": _subagent("a2", "completed", completed_at=_iso_ago(300)),
            "a3": _subagent("a3", "error", completed_at=_iso_ago(300), stop_error=LIMIT_ERROR),
        },
    )
    summary = state_to_summary(state)
    assert summary.subagents["a1"]["status"] == "interrupted"
    assert summary.subagents["a2"]["status"] == "completed"
    assert summary.subagents["a3"]["status"] == "error"
    assert summary.subagents["a3"]["stop_error"]["kind"] == "limit"
    assert summary.active_subagent_count == 0


def test_running_subagent_of_live_session_stays_running(tmp_path):
    state = _load(tmp_path, "LIVE", subagents={"a1": _subagent("a1", "running")})
    summary = state_to_summary(state)
    assert summary.subagents["a1"]["status"] == "running"
    assert summary.active_subagent_count == 1


def test_stuck_starting_counts_as_ended_for_subagents(tmp_path):
    state = _load(
        tmp_path,
        "STARTING",
        idle_seconds=STARTING_TIMEOUT + 60,
        subagents={"a1": _subagent("a1", "running")},
    )
    summary = state_to_summary(state)
    assert summary.status == "ended"
    assert summary.subagents["a1"]["status"] == "interrupted"


def test_old_file_without_stop_error_parses(tmp_path):
    summary = state_to_summary(_load(tmp_path, "ENDED"))
    assert summary.stop_error is None
