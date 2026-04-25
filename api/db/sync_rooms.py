"""
Agent-coord rooms indexer (Piece 2 of #65 / agent-coord MVP).

Reads append-only JSONL files at
    ~/.claude/rooms/<ticket>/messages.<agent_id>.jsonl
and ingests them into the v11 schema (room, agent_presence, message,
citation, decision).

Design contract (from proposal.md and locked answers on #65):

- **Hook-triggered primary**, 300s polling timer is the safety net.
  The full UserPromptSubmit hook lives in claude-communicate; karma
  exposes `sync_rooms()` as the synchronous entry point.

- **UUID v7 PK + INSERT OR IGNORE = idempotent replay.** No cursor
  table; high-watermark via `MAX(id)` per room. Per-file mtime cache
  in-memory short-circuits unchanged files.

- **Citation enforcement at ingest** (not at agent speak-time):
  type='answer' messages without >=1 stable-URN citation get a
  type='status' rejection emitted via the indexer JSONL (so the
  author's hook delivers the rejection on their next prompt).

- **Status messages JSONL round-trip.** Indexer writes its own status
  messages (rejections, escalations) to
  `~/.claude/rooms/<room>/messages._indexer.jsonl` so they flow
  through the same delivery path as agent messages. Also INSERT into
  DB immediately for low-latency dashboard rendering; next sweep's
  INSERT OR IGNORE no-ops on the DB side.

- **Atomic message+decision INSERT** for type='decision' messages.

- **Escalation rules** evaluated in the same ingest pass:
  - explicit @human in `to`: route via @human presence (no extra work)
  - all-addressed-unsure: emit status with kind='all_unsure'
  - time-based (default 30 min idle per thread/room): emit status
    with kind='escalation_timeout'

- **Directory name authoritative** for room_id. Validated against
  Linear / GitHub patterns. JSONL lines with mismatching room_id are
  logged to <room_dir>/.indexer.warnings and skipped.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import uuid_utils

from db import room_queries as rq

logger = logging.getLogger(__name__)

# Reserved agent_id for indexer-emitted status messages. Underscore prefix
# reserves the namespace; agents won't claim "_indexer" as their own id.
INDEXER_AGENT_ID = "_indexer"
INDEXER_JSONL_NAME = "messages._indexer.jsonl"
ROOM_WARNINGS_FILENAME = ".indexer.warnings"

# Linear "LIN-4821" or GitHub "owner/repo#N"
ROOM_ID_PATTERN = re.compile(r"^([A-Z]+-\d+|[\w.-]+/[\w.-]+#\d+)$")

# Per-process mtime cache. Ephemeral (no crash-resume needed; high-watermark
# via MAX(id) covers correctness).
_MTIME_CACHE: dict[str, float] = {}
_MTIME_CACHE_LOCK = threading.Lock()

# Indexing serialization (one sync per DB at a time)
_indexing_lock = threading.Lock()


def _now_iso() -> str:
    """ISO-8601 UTC timestamp; matches what writers append in JSONL."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _new_uuid7() -> str:
    """Mint a UUID v7 string for indexer-emitted messages."""
    return str(uuid_utils.uuid7())


def _is_valid_room_id(name: str) -> bool:
    return bool(ROOM_ID_PATTERN.match(name))


def _warn_to_room(room_dir: Path, line: str) -> None:
    """Append a warning line to <room_dir>/.indexer.warnings."""
    try:
        with (room_dir / ROOM_WARNINGS_FILENAME).open("a", encoding="utf-8") as f:
            f.write(f"{_now_iso()} {line}\n")
    except OSError:
        # If we can't even write the warning, surface to logger and move on
        logger.warning("indexer warning (no warnings file): %s", line)


# --- Indexer-emitted status messages ---------------------------------------


def _emit_status(
    conn: sqlite3.Connection,
    room_dir: Path,
    room_id: str,
    *,
    kind: str,
    body_extra: dict,
    in_reply_to: Optional[str] = None,
    to_agents: Optional[list[str]] = None,
) -> dict:
    """
    Emit an indexer status message via JSONL round-trip.

    Writes to messages._indexer.jsonl AND inserts into SQLite immediately
    (low-latency for dashboard; next sweep's INSERT OR IGNORE no-ops).

    Returns the emitted message dict.
    """
    msg = {
        "id": _new_uuid7(),
        "schema_version": 1,
        "room_id": room_id,
        "in_reply_to": in_reply_to,
        "from": INDEXER_AGENT_ID,
        "to": to_agents or ["human"],
        "type": "status",
        "body": {"kind": kind, **body_extra},
        "created_at": _now_iso(),
    }

    # Append to indexer JSONL first; if this fails, we don't insert
    # (so the agent's hook stays the canonical delivery surface).
    indexer_path = room_dir / INDEXER_JSONL_NAME
    try:
        with indexer_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(msg, ensure_ascii=False) + "\n")
    except OSError as e:
        logger.warning("could not append to %s: %s", indexer_path, e)
        return msg

    # Mirror to DB so the dashboard sees it now (without waiting for the
    # next sweep). INSERT OR IGNORE makes the round-trip safe.
    rq.insert_message(conn, msg)
    conn.commit()
    return msg


def _emit_rejection(
    conn: sqlite3.Connection,
    room_dir: Path,
    rejected_msg: dict,
    reason: str,
) -> None:
    """
    Emit a type=status message rejecting an answer that lacks stable-URN
    citations. Routed back to the answer's author so their next prompt
    surfaces the rejection.
    """
    _emit_status(
        conn,
        room_dir,
        rejected_msg["room_id"],
        kind="rejection",
        body_extra={
            "rejected_message_id": rejected_msg["id"],
            "reason": reason,
        },
        in_reply_to=rejected_msg["id"],
        to_agents=[rejected_msg["from"]],
    )


# --- Per-line ingest -------------------------------------------------------


def _ingest_line(
    conn: sqlite3.Connection,
    room_dir: Path,
    room_id: str,
    msg: dict,
    stats: dict,
) -> None:
    """
    Validate and ingest one JSONL message dict.

    Insertion order matters because of FK constraints:
    1. Validate fields and room_id consistency.
    2. INSERT message (so any subsequent rejection can FK-reference it).
    3. INSERT citations on this message.
    4. For type='decision': INSERT decision row (atomic with step 2 via
       a single transaction).
    5. For type='answer': enforce ≥1 stable-URN citation; on miss, emit a
       rejection status. Done AFTER insert so the rejection's in_reply_to
       FK resolves.
    """
    # Validate required fields
    for required in ("id", "from", "type", "created_at"):
        if not msg.get(required):
            stats["skipped_lines"] += 1
            _warn_to_room(room_dir, f"missing required field {required!r}: {msg.get('id', '?')}")
            return

    # room_id reconciliation: dir name authoritative
    if msg.get("room_id") and msg["room_id"] != room_id:
        stats["skipped_lines"] += 1
        _warn_to_room(
            room_dir,
            f"room_id mismatch (dir={room_id} line={msg['room_id']} id={msg['id']})",
        )
        return
    msg["room_id"] = room_id  # normalize for downstream inserts

    # schema_version validation
    sv = msg.get("schema_version", 1)
    if sv != 1:
        stats["skipped_lines"] += 1
        _warn_to_room(room_dir, f"unsupported schema_version {sv}: {msg['id']}")
        return

    # Atomic message + decision insert
    if msg["type"] == "decision":
        try:
            conn.execute("BEGIN")
            inserted = rq.insert_message(conn, msg)
            decision_inserted = rq.insert_decision(conn, msg)
            if inserted:
                stats["messages_inserted"] += 1
            if decision_inserted:
                stats["decisions_inserted"] += 1
            stats["citations_inserted"] += rq.insert_citations(
                conn, msg["id"], msg.get("citations") or []
            )
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            stats["errors"] += 1
            logger.exception("decision tx failed for %s", msg["id"])
        return

    # Non-decision path: message first, then citations, then enforcement
    try:
        if rq.insert_message(conn, msg):
            stats["messages_inserted"] += 1
        stats["citations_inserted"] += rq.insert_citations(
            conn, msg["id"], msg.get("citations") or []
        )
        conn.commit()
    except sqlite3.Error:
        conn.rollback()
        stats["errors"] += 1
        logger.exception("insert failed for %s", msg["id"])
        return

    # Citation enforcement (post-insert so the rejection can FK back)
    if msg["type"] == "answer":
        citations = msg.get("citations") or []
        if not rq.has_stable_citation(citations):
            _emit_rejection(
                conn,
                room_dir,
                msg,
                reason=(
                    "type=answer requires >=1 stable-URN citation "
                    "(node_kind in {Service, Component, DataStore, "
                    "InfraResource, Schema, Endpoint})"
                ),
            )
            stats["rejections_emitted"] += 1


# --- Per-room ingest -------------------------------------------------------


def _ingest_room(
    conn: sqlite3.Connection,
    room_id: str,
    room_dir: Path,
    stats: dict,
) -> None:
    """
    Read all messages.*.jsonl files in the room, sort merged stream by
    (created_at, id) per spec §5 L5, then ingest in order.

    Global sort matters because per-file ingest can violate FKs (a
    decision in agent A's file references an answer in agent I's file
    that hasn't been read yet). Sorting by created_at means parents
    always precede their children.
    """
    rq.ensure_room(conn, room_id)
    conn.commit()

    max_id = rq.get_room_max_message_id(conn, room_id)

    # Phase 1: collect all messages from all changed files
    pending: list[tuple[dict, str, int]] = []  # (msg, file_name, line_no)
    files_visited: list[tuple[Path, float]] = []

    for jsonl_path in sorted(room_dir.glob("messages.*.jsonl")):
        try:
            mtime = jsonl_path.stat().st_mtime
        except OSError:
            stats["errors"] += 1
            continue

        # Per-file mtime short-circuit (perf, not correctness)
        with _MTIME_CACHE_LOCK:
            cached = _MTIME_CACHE.get(str(jsonl_path))
        if cached is not None and abs(cached - mtime) < 0.001:
            stats["files_skipped_unchanged"] += 1
            continue

        try:
            with jsonl_path.open(encoding="utf-8") as f:
                for line_no, raw in enumerate(f, 1):
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        msg = json.loads(raw)
                    except json.JSONDecodeError as e:
                        stats["skipped_lines"] += 1
                        _warn_to_room(
                            room_dir,
                            f"{jsonl_path.name}:{line_no}: invalid JSON: {e}",
                        )
                        continue
                    pending.append((msg, jsonl_path.name, line_no))
        except OSError as e:
            stats["errors"] += 1
            logger.warning("could not read %s: %s", jsonl_path, e)
            continue

        files_visited.append((jsonl_path, mtime))

    # Phase 2: sort merged stream by (created_at, id) — proposal §5 L5
    pending.sort(key=lambda t: (t[0].get("created_at", ""), t[0].get("id", "")))

    # Phase 3: ingest in chronological order; high-watermark skips already-seen
    for msg, _file_name, _line_no in pending:
        if max_id is not None and msg.get("id", "") <= max_id:
            continue
        _ingest_line(conn, room_dir, room_id, msg, stats)

    # Phase 4: update mtime cache only after successful ingest of all files
    for jsonl_path, mtime in files_visited:
        with _MTIME_CACHE_LOCK:
            _MTIME_CACHE[str(jsonl_path)] = mtime


# --- Escalation rules ------------------------------------------------------


def _evaluate_all_unsure(
    conn: sqlite3.Connection,
    room_dir: Path,
    room_id: str,
    stats: dict,
) -> None:
    """
    For each question without a decision and without a prior 'all_unsure'
    status: if every agent_id in `to` has answered AND every one of those
    answers is confidence='unsure', emit a kind='all_unsure' status.
    """
    for question in rq.find_unanswered_or_unsure_questions(conn, room_id):
        try:
            addressed = json.loads(question["to_agents"] or "[]")
        except json.JSONDecodeError:
            continue
        # Filter out the human; humans don't have confidence
        addressed = [a for a in addressed if a != "human"]
        if not addressed:
            continue

        answers = rq.get_answers_for_question(conn, question["id"])
        # Group answers by from_agent_id, keep the latest
        latest_by_agent: dict[str, sqlite3.Row] = {}
        for a in answers:
            prev = latest_by_agent.get(a["from_agent_id"])
            if prev is None or a["created_at"] > prev["created_at"]:
                latest_by_agent[a["from_agent_id"]] = a

        # Every addressed agent must have answered
        if not all(a in latest_by_agent for a in addressed):
            continue

        # And every answer must be unsure
        if not all(latest_by_agent[a]["confidence"] == "unsure" for a in addressed):
            continue

        _emit_status(
            conn,
            room_dir,
            room_id,
            kind="all_unsure",
            body_extra={
                "question_id": question["id"],
                "addressed": addressed,
            },
            in_reply_to=question["id"],
            to_agents=["human"],
        )
        stats["escalations_emitted"] += 1


def _evaluate_time_based(
    conn: sqlite3.Connection,
    room_dir: Path,
    room_id: str,
    threshold_minutes: int,
    stats: dict,
) -> None:
    """
    Emit kind='escalation_timeout' for each idle bucket (per thread_id,
    else per room) where no prior timeout escalation exists for the
    current idle stretch.
    """
    for bucket in rq.find_idle_buckets(conn, room_id, threshold_minutes):
        _emit_status(
            conn,
            room_dir,
            room_id,
            kind="escalation_timeout",
            body_extra={
                "thread_id": bucket["thread_id"],
                "room_id": room_id,
                "idle_since": bucket["last_created_at"],
                "threshold_minutes": threshold_minutes,
            },
            in_reply_to=bucket["last_id"],
            to_agents=["human"],
        )
        stats["escalations_emitted"] += 1


# --- Public entry points ---------------------------------------------------


def sync_rooms(
    conn: sqlite3.Connection,
    rooms_dir: Optional[Path] = None,
    *,
    timeout_minutes: int = 30,
) -> dict:
    """
    Index all rooms under rooms_dir into the v11 schema.

    Idempotent. Designed to be called from both the periodic safety-net
    timer and (synchronously) from claude-communicate's UserPromptSubmit
    hook.

    Args:
        conn: open SQLite connection (writer; will commit per message)
        rooms_dir: Path to the rooms directory; defaults to
            ~/.claude/rooms (resolved via settings if available)
        timeout_minutes: idle threshold for time-based escalation
            (default 30; tuneable per call)

    Returns:
        Stats dict with counts: rooms, messages_inserted,
        decisions_inserted, citations_inserted, rejections_emitted,
        escalations_emitted, skipped_lines, files_skipped_unchanged,
        errors, elapsed_ms.
    """
    if rooms_dir is None:
        rooms_dir = _default_rooms_dir()

    stats = {
        "rooms": 0,
        "messages_inserted": 0,
        "decisions_inserted": 0,
        "citations_inserted": 0,
        "rejections_emitted": 0,
        "escalations_emitted": 0,
        "skipped_lines": 0,
        "files_skipped_unchanged": 0,
        "errors": 0,
        "elapsed_ms": 0,
    }

    if not _indexing_lock.acquire(blocking=False):
        logger.info("sync_rooms: already running, skipping")
        stats["status"] = "already_running"
        return stats

    start = time.time()
    try:
        if not rooms_dir.exists():
            stats["status"] = "no_rooms_dir"
            return stats

        for entry in sorted(rooms_dir.iterdir()):
            if not entry.is_dir():
                continue
            if not _is_valid_room_id(entry.name):
                # Quietly skip non-room dirs (e.g. ., _hidden)
                continue
            try:
                _ingest_room(conn, entry.name, entry, stats)
                _evaluate_all_unsure(conn, entry, entry.name, stats)
                _evaluate_time_based(conn, entry, entry.name, timeout_minutes, stats)
                stats["rooms"] += 1
            except sqlite3.Error:
                stats["errors"] += 1
                logger.exception("room ingest failed: %s", entry.name)
    finally:
        _indexing_lock.release()
        stats["elapsed_ms"] = int((time.time() - start) * 1000)

    return stats


def _default_rooms_dir() -> Path:
    """Resolve ~/.claude/rooms via settings if available, else env-default."""
    try:
        from config import settings

        return settings.claude_base / "rooms"
    except Exception:
        return Path.home() / ".claude" / "rooms"


# --- Periodic safety-net runner -------------------------------------------


async def run_periodic_room_sync(interval_seconds: int) -> None:
    """
    Safety-net periodic loop. Real-time delivery is the hook's job;
    this catches anything that fell through (hook failed, indexer race,
    cold start with no recent prompt).

    Designed to be wired into FastAPI's lifespan alongside
    run_periodic_sync (the existing session indexer).
    """
    from db.connection import get_writer_db

    while True:
        try:
            await asyncio.sleep(interval_seconds)
            conn = get_writer_db()
            stats = await asyncio.to_thread(sync_rooms, conn)
            if stats["messages_inserted"] or stats["escalations_emitted"]:
                logger.info("sync_rooms periodic: %s", stats)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("sync_rooms periodic loop error (continuing)")


# --- CLI entry point for hook --------------------------------------------


def main() -> int:
    """
    Entry point for `python -m db.sync_rooms`. Used by the karma-side
    hook stub that claude-communicate's UserPromptSubmit hook calls.

    Fail-open: any error returns 0 with a logged warning (the spec's
    contract — never block the agent's prompt on indexer failure).
    """
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent))
    logging.basicConfig(level=logging.INFO)
    try:
        from db.connection import get_writer_db

        conn = get_writer_db()
        stats = sync_rooms(conn)
        if stats["messages_inserted"] or stats["escalations_emitted"]:
            logger.info("sync_rooms hook: %s", stats)
    except Exception as e:
        logger.warning("sync_rooms failed (non-blocking): %s", e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
