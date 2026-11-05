"""Live-session duration must be active time, the same number the session page shows."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

_api_dir = Path(__file__).resolve().parent.parent.parent
if str(_api_dir) not in sys.path:
    sys.path.insert(0, str(_api_dir))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.session import Session

T0 = datetime(2026, 11, 1, 16, 5, tzinfo=timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _message(uuid: str, ts: datetime) -> dict:
    return {
        "type": "assistant",
        "uuid": uuid,
        "sessionId": "s-overnight",
        "timestamp": _iso(ts),
        "message": {
            "id": f"msg_{uuid}",
            "role": "assistant",
            "model": "claude-opus-4-5-20251101",
            "content": [{"type": "text", "text": "ok"}],
            "usage": {"input_tokens": 1, "output_tokens": 1},
        },
    }


def _write_transcript(path: Path, times: list[datetime]) -> None:
    path.write_text("".join(json.dumps(_message(f"m{i}", t)) + "\n" for i, t in enumerate(times)))


@pytest.fixture
def client(tmp_path, monkeypatch):
    import models.live_session as live_model
    from routers import live_sessions

    live_sessions._active_duration_cache.clear()
    live_dir = tmp_path / "live-sessions"
    live_dir.mkdir()
    monkeypatch.setattr(live_model, "get_live_sessions_dir", lambda: live_dir)
    app = FastAPI()
    app.include_router(live_sessions.router, prefix="/live-sessions")
    yield TestClient(app), live_dir
    live_sessions._active_duration_cache.clear()


def _write_state(
    live_dir: Path, transcript: Path, updated_at: datetime, started_at: datetime = T0
) -> None:
    (live_dir / "s-overnight.json").write_text(
        json.dumps(
            {
                "session_id": "s-overnight",
                "state": "ENDED",
                "cwd": str(transcript.parent),
                "transcript_path": str(transcript),
                "permission_mode": "default",
                "last_hook": "SessionEnd",
                "started_at": _iso(started_at),
                "updated_at": _iso(updated_at),
                "session_ids": ["s-overnight"],
            }
        )
    )


def test_ended_session_left_open_overnight_reports_active_time(tmp_path, client):
    # 33 minutes of work, then the window sat open until the session ended 14h later
    http, live_dir = client
    transcript = tmp_path / "s-overnight.jsonl"
    _write_transcript(transcript, [T0, T0 + timedelta(minutes=20), T0 + timedelta(minutes=33)])
    _write_state(live_dir, transcript, T0 + timedelta(hours=13, minutes=57))

    body = http.get("/live-sessions/s-overnight").json()

    assert body["duration_seconds"] == Session.from_path(transcript).duration_seconds == 33 * 60


def test_duration_follows_transcript_growth_between_polls(tmp_path, client):
    http, live_dir = client
    transcript = tmp_path / "s-overnight.jsonl"
    times = [T0, T0 + timedelta(minutes=20), T0 + timedelta(minutes=33)]
    _write_transcript(transcript, times)
    _write_state(live_dir, transcript, T0 + timedelta(hours=10))
    assert http.get("/live-sessions/s-overnight").json()["duration_seconds"] == 33 * 60

    # Work resumes the next morning: 10 more minutes after the overnight gap
    later = T0 + timedelta(hours=10)
    _write_transcript(transcript, times + [later, later + timedelta(minutes=10)])
    _write_state(live_dir, transcript, later + timedelta(minutes=10))

    expected = 33 * 60 + 30 * 60 + 10 * 60
    assert http.get("/live-sessions/s-overnight").json()["duration_seconds"] == expected


def test_missing_transcript_falls_back_to_tracker_span(tmp_path, client):
    http, live_dir = client
    _write_state(live_dir, tmp_path / "gone.jsonl", T0 + timedelta(hours=2))

    assert http.get("/live-sessions/s-overnight").json()["duration_seconds"] == 2 * 3600


@pytest.mark.parametrize("work_minutes", [10, 40])
def test_resumed_session_matches_session_page(tmp_path, client, work_minutes):
    # The transcript keeps 2h40m of earlier history; the tracker restarted its clock on resume
    http, live_dir = client
    transcript = tmp_path / "s-overnight.jsonl"
    history = [T0 - timedelta(hours=5) + timedelta(minutes=20 * i) for i in range(9)]
    resumed = [T0 + timedelta(minutes=m) for m in range(0, work_minutes + 1, 5)]
    _write_transcript(transcript, history + resumed)
    _write_state(live_dir, transcript, resumed[-1])

    expected = Session.from_path(transcript).duration_seconds
    assert http.get("/live-sessions/s-overnight").json()["duration_seconds"] == expected
    # The async list endpoint builds the same summary off the event loop
    assert http.get("/live-sessions").json()["sessions"][0]["duration_seconds"] == expected


@pytest.mark.parametrize("wall_minutes", [25, 45])
def test_wait_before_first_prompt_matches_session_page(tmp_path, client, wall_minutes):
    # The window opened at T0 but the first prompt came 5 minutes before updated_at
    http, live_dir = client
    transcript = tmp_path / "s-overnight.jsonl"
    end = T0 + timedelta(minutes=wall_minutes)
    _write_transcript(transcript, [end - timedelta(minutes=5), end])
    _write_state(live_dir, transcript, end)

    body = http.get("/live-sessions/s-overnight").json()

    assert body["duration_seconds"] == Session.from_path(transcript).duration_seconds == 5 * 60
