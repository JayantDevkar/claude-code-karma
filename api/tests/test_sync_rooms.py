"""
Tests for the agent-coord rooms indexer (db/sync_rooms.py).

Exercises:
- §8-walkthrough end-to-end (3 agents, 1 question, 2 answers, 2 decisions, 8 citations)
- Idempotent replay (running the same fixtures twice = no-op)
- Atomic decision INSERT (message + decision in one tx)
- Citation enforcement at ingest (rejection emitted; answer still ingested)
- All 3 escalation rules (explicit @human, all-unsure, time-based)
- Directory-name validation (non-room dirs skipped silently)
- room_id mismatch (warning written, line skipped)
- Status round-trip via messages._indexer.jsonl
- Per-file mtime cache short-circuits unchanged files
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from db import sync_rooms as sr  # noqa: E402
from db.schema import ensure_schema  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "sync_rooms"

# Suppresses the time-based escalation rule for tests that focus on other
# behaviors. Real callers pass the spec's 30-min default; passing a huge
# value here keeps tests independent of wall-clock vs fixture-date drift.
NO_TIMEOUT = 10**9


# --- Fixtures ---------------------------------------------------------------


@pytest.fixture
def db():
    """In-memory v11 schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    ensure_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def rooms_dir(tmp_path):
    """Empty rooms dir (each test stages what it needs)."""
    d = tmp_path / "rooms"
    d.mkdir()
    return d


@pytest.fixture(autouse=True)
def _clear_mtime_cache():
    """Mtime cache is process-global; clear between tests."""
    sr._MTIME_CACHE.clear()
    yield
    sr._MTIME_CACHE.clear()


def _stage_walkthrough(rooms_dir: Path) -> Path:
    """Copy the §8-walkthrough fixture under tmp_rooms/LIN-4821/."""
    dest = rooms_dir / "LIN-4821"
    shutil.copytree(FIXTURES / "LIN-4821", dest)
    return dest


# --- §8 walkthrough ---------------------------------------------------------


class TestWalkthrough:
    def test_full_ingest_matches_proposal_section_8(self, db, rooms_dir):
        room_dir = _stage_walkthrough(rooms_dir)
        stats = sr.sync_rooms(db, rooms_dir, timeout_minutes=NO_TIMEOUT)

        assert stats["rooms"] == 1
        assert stats["errors"] == 0

        # 5 messages: 1 question, 2 answers, 2 decisions
        rows = db.execute(
            "SELECT type, COUNT(*) AS n FROM message WHERE room_id='LIN-4821' GROUP BY type"
        ).fetchall()
        by_type = {r["type"]: r["n"] for r in rows}
        assert by_type == {"question": 1, "answer": 2, "decision": 2}

        # 8 citations: 2 on infra answer + 3 on codebase answer + 0 on others = 5
        # (the inherited-citation note in §8 is for the Linear post; the JSONL
        # of decision messages doesn't carry citations in the fixture.)
        cit_count = db.execute(
            "SELECT COUNT(*) FROM citation c "
            "JOIN message m ON m.id = c.message_id WHERE m.room_id='LIN-4821'"
        ).fetchone()[0]
        assert cit_count == 5

        # 2 decisions, each pinning a different answer
        decisions = db.execute(
            "SELECT question_id, answer_id, mirror_state FROM decision "
            "WHERE room_id='LIN-4821' ORDER BY id"
        ).fetchall()
        assert len(decisions) == 2
        assert all(d["mirror_state"] == "pending" for d in decisions)
        pinned_answers = {d["answer_id"] for d in decisions}
        assert pinned_answers == {
            "01912a00-0002-7000-a000-000000000002",
            "01912a00-0003-7000-a000-000000000003",
        }

        # Room exists + @human roster row (from v11 trigger)
        roster = db.execute(
            "SELECT agent_id, is_human FROM agent_presence WHERE room_id='LIN-4821'"
        ).fetchall()
        assert any(r["agent_id"] == "human" and r["is_human"] == 1 for r in roster)

        # No rejections (every answer has a stable-URN citation)
        assert stats["rejections_emitted"] == 0

        # Indexer JSONL was NOT created (nothing to round-trip)
        assert not (room_dir / sr.INDEXER_JSONL_NAME).exists()

    def test_replay_is_idempotent(self, db, rooms_dir):
        _stage_walkthrough(rooms_dir)
        first = sr.sync_rooms(db, rooms_dir, timeout_minutes=NO_TIMEOUT)
        # Second pass: clear mtime cache so files are re-read; INSERT OR IGNORE
        # + per-room MAX(id) high-watermark should produce zero new rows.
        sr._MTIME_CACHE.clear()
        second = sr.sync_rooms(db, rooms_dir, timeout_minutes=NO_TIMEOUT)

        assert first["messages_inserted"] == 5
        assert first["decisions_inserted"] == 2
        assert second["messages_inserted"] == 0
        assert second["decisions_inserted"] == 0

        # And the row counts are stable
        assert db.execute("SELECT COUNT(*) FROM message").fetchone()[0] == 5
        assert db.execute("SELECT COUNT(*) FROM decision").fetchone()[0] == 2


# --- Atomic decision insert ------------------------------------------------


class TestAtomicDecision:
    def test_decision_tx_inserts_both_message_and_decision(self, db, rooms_dir):
        _stage_walkthrough(rooms_dir)
        sr.sync_rooms(db, rooms_dir, timeout_minutes=NO_TIMEOUT)

        # Every type=decision message has a matching decision row
        rows = db.execute(
            """
            SELECT m.id AS mid, d.id AS did
            FROM message m LEFT JOIN decision d ON m.id = d.id
            WHERE m.type = 'decision' AND m.room_id = 'LIN-4821'
            """
        ).fetchall()
        assert len(rows) == 2
        assert all(r["did"] is not None for r in rows)


# --- Citation enforcement --------------------------------------------------


class TestCitationEnforcement:
    def _stage_uncited_answer(self, rooms_dir: Path) -> Path:
        room_dir = rooms_dir / "LIN-9999"
        room_dir.mkdir()
        # Question
        q = {
            "id": "01912a00-0001-7000-a000-aaaaaaaaaaaa",
            "schema_version": 1,
            "room_id": "LIN-9999",
            "from": "airflow:main",
            "to": ["infra:main"],
            "type": "question",
            "body": "?",
            "confidence": "low",
            "citations": [],
            "created_at": "2026-04-25T00:00:00Z",
        }
        # Answer with NO stable-URN citation (only a path-based File)
        a_bad = {
            "id": "01912a00-0002-7000-a000-aaaaaaaaaaaa",
            "schema_version": 1,
            "room_id": "LIN-9999",
            "in_reply_to": q["id"],
            "from": "infra:main",
            "to": ["airflow:main"],
            "type": "answer",
            "body": "see this file",
            "confidence": "high",
            "citations": [
                {"urn": "urn:file:infra:terraform/x.tf", "node_kind": "File"}
            ],
            "created_at": "2026-04-25T00:01:00Z",
        }
        with (room_dir / "messages.airflow:main.jsonl").open("w") as f:
            f.write(json.dumps(q) + "\n")
        with (room_dir / "messages.infra:main.jsonl").open("w") as f:
            f.write(json.dumps(a_bad) + "\n")
        return room_dir

    def test_uncited_answer_emits_rejection(self, db, rooms_dir):
        room_dir = self._stage_uncited_answer(rooms_dir)
        stats = sr.sync_rooms(db, rooms_dir, timeout_minutes=NO_TIMEOUT)

        assert stats["rejections_emitted"] == 1

        # Rejection landed in DB as a status message
        rejections = db.execute(
            "SELECT id, from_agent_id, in_reply_to, body, to_agents "
            "FROM message WHERE type='status' AND room_id='LIN-9999'"
        ).fetchall()
        assert len(rejections) == 1
        r = rejections[0]
        assert r["from_agent_id"] == sr.INDEXER_AGENT_ID
        assert r["in_reply_to"] == "01912a00-0002-7000-a000-aaaaaaaaaaaa"
        assert json.loads(r["to_agents"]) == ["infra:main"]
        body = json.loads(r["body"])
        assert body["kind"] == "rejection"

        # And it was round-tripped to the indexer JSONL
        assert (room_dir / sr.INDEXER_JSONL_NAME).exists()
        with (room_dir / sr.INDEXER_JSONL_NAME).open() as f:
            line = json.loads(f.readline())
        assert line["from"] == sr.INDEXER_AGENT_ID
        assert line["body"]["kind"] == "rejection"

        # The answer itself was still ingested (rejection is informational)
        a = db.execute(
            "SELECT id FROM message WHERE id='01912a00-0002-7000-a000-aaaaaaaaaaaa'"
        ).fetchone()
        assert a is not None

    def test_stable_urn_passes(self, db, rooms_dir):
        _stage_walkthrough(rooms_dir)
        stats = sr.sync_rooms(db, rooms_dir, timeout_minutes=NO_TIMEOUT)
        # Both walkthrough answers carry InfraResource / Component (stable)
        assert stats["rejections_emitted"] == 0


# --- Escalation rules ------------------------------------------------------


def _stage_question_only(rooms_dir: Path, *, addressed: list[str]) -> Path:
    room_dir = rooms_dir / "LIN-7777"
    room_dir.mkdir()
    q = {
        "id": "01912a00-0001-7000-a000-bbbbbbbbbbbb",
        "schema_version": 1,
        "room_id": "LIN-7777",
        "from": "airflow:main",
        "to": addressed,
        "type": "question",
        "body": "?",
        "confidence": "low",
        "citations": [],
        "created_at": "2026-04-25T00:00:00Z",
    }
    with (room_dir / "messages.airflow:main.jsonl").open("w") as f:
        f.write(json.dumps(q) + "\n")
    return room_dir


def _append_answer(
    room_dir: Path, *, msg_id: str, agent_id: str, confidence: str, in_reply_to: str
) -> dict:
    msg = {
        "id": msg_id,
        "schema_version": 1,
        "room_id": room_dir.name,
        "in_reply_to": in_reply_to,
        "from": agent_id,
        "to": ["airflow:main"],
        "type": "answer",
        "body": "answer",
        "confidence": confidence,
        "citations": [
            {"urn": f"urn:service:foo:{agent_id}", "node_kind": "Service"}
        ],
        "created_at": "2026-04-25T00:05:00Z",
    }
    safe_name = agent_id.replace("/", "-")
    with (room_dir / f"messages.{safe_name}.jsonl").open("a") as f:
        f.write(json.dumps(msg) + "\n")
    return msg


class TestEscalationAllUnsure:
    def test_emits_when_all_addressed_agents_answer_unsure(self, db, rooms_dir):
        room_dir = _stage_question_only(rooms_dir, addressed=["infra:main", "codebase:main"])
        q_id = "01912a00-0001-7000-a000-bbbbbbbbbbbb"

        # Both addressed agents answer with confidence=unsure
        _append_answer(
            room_dir,
            msg_id="01912a00-0002-7000-a000-bbbbbbbbbbbb",
            agent_id="infra:main",
            confidence="unsure",
            in_reply_to=q_id,
        )
        _append_answer(
            room_dir,
            msg_id="01912a00-0003-7000-a000-bbbbbbbbbbbb",
            agent_id="codebase:main",
            confidence="unsure",
            in_reply_to=q_id,
        )

        stats = sr.sync_rooms(db, rooms_dir, timeout_minutes=NO_TIMEOUT)
        assert stats["escalations_emitted"] >= 1

        statuses = db.execute(
            "SELECT body FROM message WHERE type='status' AND from_agent_id='_indexer' "
            "AND room_id='LIN-7777'"
        ).fetchall()
        kinds = [json.loads(s["body"])["kind"] for s in statuses]
        assert "all_unsure" in kinds

    def test_does_not_emit_when_one_agent_is_high_confidence(self, db, rooms_dir):
        room_dir = _stage_question_only(rooms_dir, addressed=["infra:main", "codebase:main"])
        q_id = "01912a00-0001-7000-a000-bbbbbbbbbbbb"
        _append_answer(
            room_dir,
            msg_id="01912a00-0002-7000-a000-bbbbbbbbbbbb",
            agent_id="infra:main",
            confidence="unsure",
            in_reply_to=q_id,
        )
        _append_answer(
            room_dir,
            msg_id="01912a00-0003-7000-a000-bbbbbbbbbbbb",
            agent_id="codebase:main",
            confidence="high",
            in_reply_to=q_id,
        )

        stats = sr.sync_rooms(db, rooms_dir, timeout_minutes=NO_TIMEOUT)
        statuses = db.execute(
            "SELECT body FROM message WHERE type='status' AND from_agent_id='_indexer' "
            "AND room_id='LIN-7777'"
        ).fetchall()
        kinds = [json.loads(s["body"])["kind"] for s in statuses]
        assert "all_unsure" not in kinds
        # No escalation; rejections also zero (Service is a stable URN kind)
        assert stats["escalations_emitted"] == 0

    def test_does_not_emit_when_only_some_have_answered(self, db, rooms_dir):
        room_dir = _stage_question_only(rooms_dir, addressed=["infra:main", "codebase:main"])
        q_id = "01912a00-0001-7000-a000-bbbbbbbbbbbb"
        # Only infra answers
        _append_answer(
            room_dir,
            msg_id="01912a00-0002-7000-a000-bbbbbbbbbbbb",
            agent_id="infra:main",
            confidence="unsure",
            in_reply_to=q_id,
        )

        stats = sr.sync_rooms(db, rooms_dir, timeout_minutes=NO_TIMEOUT)
        statuses = db.execute(
            "SELECT body FROM message WHERE type='status' AND from_agent_id='_indexer' "
            "AND room_id='LIN-7777'"
        ).fetchall()
        assert "all_unsure" not in [json.loads(s["body"])["kind"] for s in statuses]
        assert stats["escalations_emitted"] == 0


class TestEscalationTimeout:
    def test_emits_when_room_idle_past_threshold(self, db, rooms_dir):
        # Stage a room with one ancient message
        room_dir = rooms_dir / "LIN-3333"
        room_dir.mkdir()
        msg = {
            "id": "01912a00-0001-7000-a000-cccccccccccc",
            "schema_version": 1,
            "room_id": "LIN-3333",
            "from": "airflow:main",
            "to": ["infra:main"],
            "type": "question",
            "body": "?",
            "confidence": "low",
            "citations": [],
            "created_at": "2026-01-01T00:00:00Z",  # very old
        }
        with (room_dir / "messages.airflow:main.jsonl").open("w") as f:
            f.write(json.dumps(msg) + "\n")

        stats = sr.sync_rooms(db, rooms_dir, timeout_minutes=30)
        assert stats["escalations_emitted"] >= 1

        statuses = db.execute(
            "SELECT body FROM message WHERE type='status' AND from_agent_id='_indexer' "
            "AND room_id='LIN-3333'"
        ).fetchall()
        kinds = {json.loads(s["body"])["kind"] for s in statuses}
        assert "escalation_timeout" in kinds

        # Body carries the spec-required keys
        body = next(
            json.loads(s["body"])
            for s in statuses
            if json.loads(s["body"])["kind"] == "escalation_timeout"
        )
        assert body["room_id"] == "LIN-3333"
        assert body["threshold_minutes"] == 30
        assert "idle_since" in body

    def test_does_not_re_emit_for_same_idle_stretch(self, db, rooms_dir):
        room_dir = rooms_dir / "LIN-3333"
        room_dir.mkdir()
        msg = {
            "id": "01912a00-0001-7000-a000-cccccccccccc",
            "schema_version": 1,
            "room_id": "LIN-3333",
            "from": "airflow:main",
            "to": ["infra:main"],
            "type": "question",
            "body": "?",
            "confidence": "low",
            "citations": [],
            "created_at": "2026-01-01T00:00:00Z",
        }
        with (room_dir / "messages.airflow:main.jsonl").open("w") as f:
            f.write(json.dumps(msg) + "\n")

        sr.sync_rooms(db, rooms_dir, timeout_minutes=30)
        sr._MTIME_CACHE.clear()
        sr.sync_rooms(db, rooms_dir, timeout_minutes=30)

        timeout_count = db.execute(
            "SELECT COUNT(*) FROM message WHERE type='status' "
            "AND from_agent_id='_indexer' "
            "AND room_id='LIN-3333' "
            "AND json_extract(body, '$.kind') = 'escalation_timeout'"
        ).fetchone()[0]
        assert timeout_count == 1

    def test_does_not_emit_for_recent_room(self, db, rooms_dir):
        # Use the §8 walkthrough but pretend the threshold is way past current time
        _stage_walkthrough(rooms_dir)
        # Messages are dated 2026-04-24; threshold of 525600 minutes (~1 year)
        # is large enough that they may or may not be inside it depending on
        # current date. To keep the test deterministic, use a *very* short
        # threshold and a *future* dated message:
        future_dir = rooms_dir / "LIN-FUTURE"
        future_dir.mkdir()
        with (future_dir / "messages.airflow:main.jsonl").open("w") as f:
            f.write(
                json.dumps(
                    {
                        "id": "01912a00-0001-7000-a000-dddddddddddd",
                        "schema_version": 1,
                        "room_id": "LIN-FUTURE",
                        "from": "airflow:main",
                        "to": [],
                        "type": "question",
                        "body": "?",
                        "confidence": "low",
                        "citations": [],
                        # Datetime that won't be > threshold-old in any reasonable run
                        "created_at": "9999-12-31T23:59:59Z",
                    }
                )
                + "\n"
            )

        sr.sync_rooms(db, rooms_dir, timeout_minutes=30)
        # No timeout escalation for the future-dated room
        timeout_count = db.execute(
            "SELECT COUNT(*) FROM message WHERE type='status' "
            "AND from_agent_id='_indexer' "
            "AND room_id='LIN-FUTURE' "
            "AND json_extract(body, '$.kind') = 'escalation_timeout'"
        ).fetchone()[0]
        assert timeout_count == 0


# --- Directory + line validation -----------------------------------------


class TestRoomIdValidation:
    def test_skips_dirs_that_dont_match_room_id_pattern(self, db, rooms_dir):
        (rooms_dir / "_indexer").mkdir()
        (rooms_dir / "garbage").mkdir()
        (rooms_dir / ".hidden").mkdir()
        # Stage one valid room alongside
        _stage_walkthrough(rooms_dir)

        stats = sr.sync_rooms(db, rooms_dir, timeout_minutes=NO_TIMEOUT)
        # Only LIN-4821 is a valid room
        assert stats["rooms"] == 1
        rooms = {r[0] for r in db.execute("SELECT id FROM room").fetchall()}
        assert rooms == {"LIN-4821"}

    def test_room_id_mismatch_warning_and_skip(self, db, rooms_dir):
        room_dir = rooms_dir / "LIN-4821"
        room_dir.mkdir()
        msg = {
            "id": "01912a00-0001-7000-a000-eeeeeeeeeeee",
            "schema_version": 1,
            "room_id": "LIN-OTHER",  # mismatch
            "from": "airflow:main",
            "to": [],
            "type": "question",
            "body": "?",
            "confidence": "low",
            "citations": [],
            "created_at": "2026-04-25T00:00:00Z",
        }
        with (room_dir / "messages.airflow:main.jsonl").open("w") as f:
            f.write(json.dumps(msg) + "\n")

        stats = sr.sync_rooms(db, rooms_dir, timeout_minutes=NO_TIMEOUT)
        assert stats["skipped_lines"] >= 1
        # Message NOT inserted
        assert (
            db.execute(
                "SELECT COUNT(*) FROM message WHERE id=?", (msg["id"],)
            ).fetchone()[0]
            == 0
        )
        # Warning written to .indexer.warnings
        warnings_path = room_dir / sr.ROOM_WARNINGS_FILENAME
        assert warnings_path.exists()
        assert "room_id mismatch" in warnings_path.read_text()


# --- Mtime cache ----------------------------------------------------------


class TestMtimeCache:
    def test_unchanged_file_skipped_on_second_pass(self, db, rooms_dir):
        _stage_walkthrough(rooms_dir)
        sr.sync_rooms(db, rooms_dir, timeout_minutes=NO_TIMEOUT)
        stats = sr.sync_rooms(db, rooms_dir, timeout_minutes=NO_TIMEOUT)  # cache hot
        assert stats["files_skipped_unchanged"] >= 3  # 3 fixture files

    def test_cleared_cache_re_reads_files(self, db, rooms_dir):
        _stage_walkthrough(rooms_dir)
        sr.sync_rooms(db, rooms_dir, timeout_minutes=NO_TIMEOUT)
        sr._MTIME_CACHE.clear()
        stats = sr.sync_rooms(db, rooms_dir, timeout_minutes=NO_TIMEOUT)
        # Re-read but INSERT OR IGNORE means no new rows
        assert stats["files_skipped_unchanged"] == 0
        assert stats["messages_inserted"] == 0
