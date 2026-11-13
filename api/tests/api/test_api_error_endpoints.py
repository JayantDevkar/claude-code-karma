"""Endpoint exposure of API-error turns: timeline events, ended-by on sessions and subagents."""

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from main import app
from tests.api_error_fixtures import (
    SESSION_ID,
    limit_line,
    reply_line,
    user_line,
    write_jsonl,
)

ENCODED = "-home-alice-project"
LONG_REPLY = "Here is a thorough answer that is comfortably longer than fifty characters in total."


def _ts(n):
    return f"2026-01-10T10:{n:02d}:00.000Z"


def _u(n):
    return user_line(f"u{n}", None, _ts(n), "go")


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def session_files(mock_claude_base):
    """Main session ending on a limit (one earlier limit healed) plus two subagents."""
    project_dir = mock_claude_base / "projects" / ENCODED
    main = write_jsonl(
        project_dir / f"{SESSION_ID}.jsonl",
        [
            _u(1),
            limit_line("a1", "u1", _ts(2)),
            _u(3),
            reply_line("a3", "u3", _ts(4), LONG_REPLY),
            _u(5),
            limit_line("a5", "u5", _ts(6)),
        ],
    )
    sub_dir = project_dir / SESSION_ID / "subagents"
    write_jsonl(sub_dir / "agent-aaa1.jsonl", [_u(7), limit_line("s1", "u7", _ts(8))])
    write_jsonl(sub_dir / "agent-bbb2.jsonl", [_u(9), reply_line("s2", "u9", _ts(10), "fine")])
    return main


def test_timeline_marks_error_turns(client, session_files):
    ev = client.get(f"/sessions/{SESSION_ID}/timeline").json()

    errs = [e for e in ev if e["event_type"] == "api_error"]
    assert [e["metadata"]["healed"] for e in errs] == [True, False]
    assert errs[1]["metadata"]["kind"] == "limit"
    assert errs[1]["metadata"]["code"] == "usage_limit_reached"
    assert errs[1]["metadata"]["status"] == 429
    assert errs[1]["metadata"]["resets_at"].startswith("2026-01-10T12:00:00")
    assert "hit your session limit" in errs[1]["summary"]
    assert not any(e["event_type"] == "response" and "hit your" in (e["summary"] or "") for e in ev)
    assert any(e["event_type"] == "response" for e in ev)


def test_session_detail_has_ended_by(client, session_files):
    body = client.get(f"/sessions/{SESSION_ID}").json()

    assert body["ended_by"] == "limit"
    assert body["limit_hit_count"] == 2
    assert body["ended_resets_at"].startswith("2026-01-10T12:00:00")
    assert "<synthetic>" not in body["models_used"]


def test_subagent_list_has_ended_by(client, session_files):
    body = client.get(f"/sessions/{SESSION_ID}/subagents").json()

    by_id = {s["agent_id"]: s for s in body}
    assert by_id["aaa1"]["ended_by"] == "limit"
    assert by_id["aaa1"]["limit_hit_count"] == 1
    assert by_id["bbb2"]["ended_by"] is None
    assert by_id["bbb2"]["limit_hit_count"] == 0


def test_parallel_subagent_list_has_ended_by(client, session_files):
    sub_dir = session_files.parent / SESSION_ID / "subagents"
    for i in range(3):
        write_jsonl(
            sub_dir / f"agent-ccc{i}.jsonl",
            [_u(11 + i), reply_line(f"c{i}", f"u{11 + i}", _ts(20), "ok")],
        )

    resp = client.get(f"/sessions/{SESSION_ID}/subagents/parallel")

    assert resp.status_code == 200
    by_id = {s["agent_id"]: s for s in resp.json()}
    assert len(by_id) == 5
    assert by_id["aaa1"]["ended_by"] == "limit"
    assert by_id["bbb2"]["ended_by"] is None


def test_subagent_detail_and_timeline_mark_final_error(client, session_files):
    base = f"/agents/{ENCODED}/{SESSION_ID}/agents/aaa1"

    assert client.get(base).json()["ended_by"] == "limit"
    ev = client.get(f"{base}/timeline").json()

    errs = [e for e in ev if e["event_type"] == "api_error"]
    assert len(errs) == 1 and errs[0]["metadata"]["healed"] is False


def test_session_list_rows_carry_ended_by(client, session_files, monkeypatch):
    import db.connection as connection
    import db.indexer as indexer
    from models.session import Session

    monkeypatch.setattr(indexer, "is_db_ready", lambda: True)
    conn = connection.get_writer_db()
    Session.clear_all_caches()
    stat = session_files.stat()
    indexer._index_session(conn, session_files, ENCODED, stat.st_mtime, stat.st_size)
    conn.commit()

    listed = client.get("/sessions/all").json()["sessions"]
    assert [s["ended_by"] for s in listed] == ["limit"]
    assert listed[0]["limit_hit_count"] == 2
    assert listed[0]["ended_resets_at"].startswith("2026-01-10T12:00:00")

    project = client.get(f"/projects/{ENCODED}").json()
    assert [s["ended_by"] for s in project["sessions"]] == ["limit"]
