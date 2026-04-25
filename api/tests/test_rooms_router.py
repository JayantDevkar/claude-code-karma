"""
Tests for routers/rooms.py — agent-coord rooms dashboard endpoints.

Strategy: build a real-shaped v11 DB in tmp, monkeypatch sqlite_read to
yield that DB, exercise the endpoints via FastAPI's TestClient.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parent.parent))

from db.schema import ensure_schema  # noqa: E402
from routers import rooms as rooms_router  # noqa: E402

# --- Test infrastructure ---------------------------------------------------


@pytest.fixture
def db():
    # check_same_thread=False because FastAPI's TestClient runs requests in
    # a worker thread separate from the test setup. The fixture is
    # single-writer in practice (no concurrent SQLite use across threads).
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def app(db):
    """Mount the rooms router with a sqlite_read patched to yield the test DB."""

    @contextmanager
    def fake_sqlite_read():
        yield db

    rooms_router.sqlite_read = fake_sqlite_read

    app = FastAPI()
    app.include_router(rooms_router.router)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


# --- Seed helpers ----------------------------------------------------------


def _seed_room(db, room_id: str, *, title: str = "test room", status: str = "active"):
    db.execute(
        "INSERT INTO room (id, title, status) VALUES (?, ?, ?)",
        (room_id, title, status),
    )


def _seed_message(
    db,
    *,
    msg_id: str,
    room_id: str,
    type: str,
    from_agent_id: str = "airflow:main",
    to: list[str] | None = None,
    in_reply_to: str | None = None,
    body: str = "x",
    confidence: str | None = None,
    created_at: str = "2026-04-25T00:00:00Z",
    citations: list[dict] | None = None,
):
    db.execute(
        """
        INSERT INTO message (id, room_id, in_reply_to, from_agent_id,
            to_agents, type, body, confidence, schema_version, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """,
        (
            msg_id,
            room_id,
            in_reply_to,
            from_agent_id,
            json.dumps(to or []),
            type,
            body,
            confidence,
            created_at,
        ),
    )
    for c in citations or []:
        db.execute(
            "INSERT INTO citation (message_id, urn, node_kind) VALUES (?, ?, ?)",
            (msg_id, c["urn"], c.get("node_kind")),
        )
    db.commit()


def _seed_decision(db, *, decision_id: str, room_id: str, question_id: str, answer_id: str):
    db.execute(
        """
        INSERT INTO decision (id, room_id, question_id, answer_id, body,
                              made_by, confidence)
        VALUES (?, ?, ?, ?, 'pinned', 'airflow:main', 'high')
        """,
        (decision_id, room_id, question_id, answer_id),
    )
    db.commit()


# --- Empty / missing-tables ------------------------------------------------


class TestEmptyAndMissing:
    def test_list_returns_empty_when_no_rooms(self, client):
        r = client.get("/rooms")
        assert r.status_code == 200
        assert r.json() == {"rooms": [], "total": 0}

    def test_get_room_404_when_missing(self, client):
        r = client.get("/rooms/LIN-NOPE")
        assert r.status_code == 404


# --- /rooms list -----------------------------------------------------------


class TestListRooms:
    def test_list_returns_summary_with_counts(self, db, client):
        _seed_room(db, "LIN-1", title="auth")
        _seed_room(db, "LIN-2", title="dag", status="archived")
        _seed_message(
            db,
            msg_id="m1",
            room_id="LIN-1",
            type="question",
            created_at="2026-04-25T01:00:00Z",
        )
        _seed_message(
            db,
            msg_id="m2",
            room_id="LIN-1",
            type="answer",
            in_reply_to="m1",
            created_at="2026-04-25T01:05:00Z",
        )
        # Decision message FIRST so the FK from decision.id → message.id resolves
        _seed_message(
            db,
            msg_id="m3",
            room_id="LIN-1",
            type="decision",
            in_reply_to="m1",
            created_at="2026-04-25T01:10:00Z",
            body=json.dumps({"pins": "m2"}),
        )
        _seed_decision(db, decision_id="m3", room_id="LIN-1", question_id="m1", answer_id="m2")

        r = client.get("/rooms")
        assert r.status_code == 200
        data = r.json()
        assert data["total"] == 2
        # last_activity sort: LIN-1 has messages, LIN-2 doesn't → LIN-1 first
        assert [room["id"] for room in data["rooms"]] == ["LIN-1", "LIN-2"]

        lin1 = data["rooms"][0]
        assert lin1["title"] == "auth"
        assert lin1["status"] == "active"
        assert lin1["message_count"] == 3
        assert lin1["decision_count"] == 1
        # @human roster row inserted by trigger
        assert lin1["agent_count"] == 1
        assert lin1["last_activity"] == "2026-04-25T01:10:00Z"

    def test_status_filter(self, db, client):
        _seed_room(db, "LIN-A", status="active")
        _seed_room(db, "LIN-B", status="archived")

        r = client.get("/rooms", params={"status": "archived"})
        assert {room["id"] for room in r.json()["rooms"]} == {"LIN-B"}

    def test_search_substring(self, db, client):
        _seed_room(db, "LIN-100", title="snowflake migration")
        _seed_room(db, "LIN-200", title="auth refactor")

        # Match on title substring
        r = client.get("/rooms", params={"search": "snow"})
        assert {room["id"] for room in r.json()["rooms"]} == {"LIN-100"}

        # Match on id
        r = client.get("/rooms", params={"search": "200"})
        assert {room["id"] for room in r.json()["rooms"]} == {"LIN-200"}

    def test_sort_created(self, db, client):
        # Same-second CURRENT_TIMESTAMP defaults make ordering undefined,
        # so set created_at explicitly to control the sort.
        db.execute(
            "INSERT INTO room (id, created_at) VALUES (?, ?)",
            ("LIN-A", "2026-01-01T00:00:00Z"),
        )
        db.execute(
            "INSERT INTO room (id, created_at) VALUES (?, ?)",
            ("LIN-B", "2026-02-01T00:00:00Z"),
        )
        db.commit()

        r = client.get("/rooms", params={"sort": "created"})
        ids = [room["id"] for room in r.json()["rooms"]]
        assert ids == ["LIN-B", "LIN-A"]


# --- /rooms/{id} detail ----------------------------------------------------


class TestGetRoom:
    def _seed_walkthrough_lite(self, db):
        _seed_room(db, "LIN-4821", title="metrics")
        _seed_message(
            db,
            msg_id="q1",
            room_id="LIN-4821",
            type="question",
            from_agent_id="airflow:main",
            to=["infra:main"],
            confidence="low",
            created_at="2026-04-25T00:00:00Z",
        )
        _seed_message(
            db,
            msg_id="a1",
            room_id="LIN-4821",
            type="answer",
            from_agent_id="infra:main",
            to=["airflow:main"],
            in_reply_to="q1",
            confidence="high",
            created_at="2026-04-25T00:05:00Z",
            citations=[{"urn": "urn:infra:role:writer", "node_kind": "InfraResource"}],
        )
        _seed_message(
            db,
            msg_id="d1",
            room_id="LIN-4821",
            type="decision",
            from_agent_id="airflow:main",
            in_reply_to="q1",
            confidence="high",
            created_at="2026-04-25T00:10:00Z",
            body=json.dumps({"pins": "a1", "summary": "use writer role"}),
        )
        _seed_decision(
            db,
            decision_id="d1",
            room_id="LIN-4821",
            question_id="q1",
            answer_id="a1",
        )

    def test_returns_room_presence_decisions_inline_messages(self, db, client):
        self._seed_walkthrough_lite(db)
        r = client.get("/rooms/LIN-4821")
        assert r.status_code == 200
        data = r.json()

        # Room
        assert data["room"]["id"] == "LIN-4821"
        assert data["room"]["message_count"] == 3
        assert data["room"]["decision_count"] == 1

        # Presence: only @human (no agent_presence rows seeded)
        assert any(p["agent_id"] == "human" and p["is_human"] is True for p in data["presence"])

        # Decisions
        assert len(data["decisions"]) == 1
        assert data["decisions"][0]["mirror_state"] == "pending"
        assert data["decisions"][0]["external_system"] == "linear"

        # Messages: chronological, citations attached
        msg_types = [m["type"] for m in data["messages"]]
        assert msg_types == ["question", "answer", "decision"]
        answer = data["messages"][1]
        assert len(answer["citations"]) == 1
        assert answer["citations"][0]["node_kind"] == "InfraResource"

        # to_agents parsed back to a list
        assert data["messages"][0]["to_agents"] == ["infra:main"]

    def test_path_room_id_supports_github_style(self, db, client):
        _seed_room(db, "owner/repo#42", title="github example")
        r = client.get("/rooms/owner/repo%2342")  # %23 == #
        assert r.status_code == 200
        assert r.json()["room"]["id"] == "owner/repo#42"


# --- /rooms/{id}/messages pagination --------------------------------------


class TestRoomMessages:
    def _seed_n_messages(self, db, n: int):
        _seed_room(db, "LIN-PAG")
        for i in range(n):
            _seed_message(
                db,
                msg_id=f"m{i:03d}",
                room_id="LIN-PAG",
                type="question",
                created_at=f"2026-04-25T00:{i:02d}:00Z",
            )

    def test_default_page_chronological(self, db, client):
        self._seed_n_messages(db, 5)
        r = client.get("/rooms/LIN-PAG/messages")
        ids = [m["id"] for m in r.json()["messages"]]
        assert ids == ["m000", "m001", "m002", "m003", "m004"]

    def test_order_desc(self, db, client):
        self._seed_n_messages(db, 5)
        r = client.get("/rooms/LIN-PAG/messages", params={"order": "desc"})
        ids = [m["id"] for m in r.json()["messages"]]
        assert ids == ["m004", "m003", "m002", "m001", "m000"]

    def test_pagination(self, db, client):
        self._seed_n_messages(db, 7)
        r = client.get("/rooms/LIN-PAG/messages", params={"per_page": 3, "page": 2})
        data = r.json()
        ids = [m["id"] for m in data["messages"]]
        assert ids == ["m003", "m004", "m005"]
        assert data["total"] == 7
        assert data["page"] == 2
        assert data["per_page"] == 3

    def test_404_when_room_missing(self, client):
        r = client.get("/rooms/LIN-MISSING/messages")
        assert r.status_code == 404
