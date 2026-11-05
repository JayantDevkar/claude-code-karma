"""The /initial-prompt endpoint returns the real prompt, not a caveat or <wake> line."""

from pathlib import Path

from fastapi.testclient import TestClient

from main import app
from routers import sessions as sessions_router
from tests.test_initial_prompt_clear import PROMPT, _make_session
from tests.test_initial_prompt_relay import NOTE, RELAY, WAKE, _session_from, _user


def test_initial_prompt_endpoint_returns_typed_prompt(tmp_path: Path, monkeypatch):
    session = _make_session(tmp_path)
    monkeypatch.setattr(sessions_router, "find_session", lambda uuid: session)

    response = TestClient(app).get("/sessions/clear-session/initial-prompt")

    assert response.status_code == 200
    body = response.json()
    assert body["content"] == PROMPT
    assert body["timestamp"].startswith("2026-10-21T10:00:05")


def test_initial_prompt_endpoint_returns_spawn_note(tmp_path: Path, monkeypatch):
    session = _session_from(
        tmp_path,
        [
            _user("u1", RELAY, "2026-11-01T20:27:46.949Z", isMeta=True),
            _user("u2", WAKE, "2026-11-01T20:27:47.100Z"),
        ],
    )
    monkeypatch.setattr(sessions_router, "find_session", lambda uuid: session)

    response = TestClient(app).get("/sessions/spawned/initial-prompt")

    assert response.status_code == 200
    body = response.json()
    assert body["content"] == NOTE
    assert body["timestamp"].startswith("2026-11-01T20:27:46")
