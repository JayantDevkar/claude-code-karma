"""The /initial-prompt endpoint returns the typed prompt, not the /clear caveat."""

from pathlib import Path

from fastapi.testclient import TestClient

from main import app
from routers import sessions as sessions_router
from tests.test_initial_prompt_clear import PROMPT, _make_session


def test_initial_prompt_endpoint_returns_typed_prompt(tmp_path: Path, monkeypatch):
    session = _make_session(tmp_path)
    monkeypatch.setattr(sessions_router, "find_session", lambda uuid: session)

    response = TestClient(app).get("/sessions/clear-session/initial-prompt")

    assert response.status_code == 200
    body = response.json()
    assert body["content"] == PROMPT
    assert body["timestamp"].startswith("2026-10-21T10:00:05")
