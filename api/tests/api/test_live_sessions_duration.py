"""Live-session duration must be active time, the same number the session page shows."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

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


def test_ended_session_left_open_overnight_reports_active_time(tmp_path, monkeypatch):
    # 33 minutes of work, then the window sat open until the session ended 14h later
    transcript = tmp_path / "s-overnight.jsonl"
    times = [T0, T0 + timedelta(minutes=20), T0 + timedelta(minutes=33)]
    transcript.write_text(
        "".join(json.dumps(_message(f"m{i}", t)) + "\n" for i, t in enumerate(times))
    )

    live_dir = tmp_path / "live-sessions"
    live_dir.mkdir()
    (live_dir / "s-overnight.json").write_text(
        json.dumps(
            {
                "session_id": "s-overnight",
                "state": "ENDED",
                "cwd": str(tmp_path),
                "transcript_path": str(transcript),
                "permission_mode": "default",
                "last_hook": "SessionEnd",
                "started_at": _iso(T0),
                "updated_at": _iso(T0 + timedelta(hours=13, minutes=57)),
                "session_ids": ["s-overnight"],
            }
        )
    )

    import models.live_session as live_model
    from routers import live_sessions

    monkeypatch.setattr(live_model, "get_live_sessions_dir", lambda: live_dir)
    app = FastAPI()
    app.include_router(live_sessions.router, prefix="/live-sessions")

    body = TestClient(app).get("/live-sessions/s-overnight").json()

    assert body["duration_seconds"] == Session.from_path(transcript).duration_seconds == 33 * 60
