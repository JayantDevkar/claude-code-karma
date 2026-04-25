"""
SQL helpers for the agent-coord room indexer (sync_rooms).

Keeps the indexer module readable. All functions take an open sqlite3
connection and return plain Python values; transactions are managed by
the caller.

Naming convention: helpers are written from the indexer's perspective
("the thing the indexer wants to do") not the schema's perspective
("CRUD on table X").
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Iterable, Optional

logger = logging.getLogger(__name__)

# coderoots URN kinds that count as "stable" (name-based, survive file moves).
# Source: docs/agent-coord/coderoots-integration.md and proposal.md §5 L3.
STABLE_URN_KINDS = frozenset(
    {"Service", "Component", "DataStore", "InfraResource", "Schema", "Endpoint"}
)


# --- Idempotent room lifecycle ---------------------------------------------


def ensure_room(conn: sqlite3.Connection, room_id: str, title: Optional[str] = None) -> None:
    """
    Create a room row if it doesn't exist.

    The schema's AFTER INSERT ON room trigger synthesizes the @human
    presence row automatically. INSERT OR IGNORE makes this safe to call
    on every ingest pass.
    """
    conn.execute(
        "INSERT OR IGNORE INTO room (id, title) VALUES (?, ?)",
        (room_id, title),
    )


# --- High-watermark for O(tail) ingest -------------------------------------


def get_room_max_message_id(conn: sqlite3.Connection, room_id: str) -> Optional[str]:
    """
    Return the lexicographically-largest message id seen for this room.

    UUID v7 is lex-sortable = chronologically-sortable, so this is the
    "last ingested" cursor with no extra table to maintain. The indexer
    skips JSONL lines whose id is <= this watermark.
    """
    row = conn.execute(
        "SELECT MAX(id) FROM message WHERE room_id = ?",
        (room_id,),
    ).fetchone()
    return row[0] if row else None


# --- Idempotent INSERTs ----------------------------------------------------


def insert_message(conn: sqlite3.Connection, msg: dict) -> bool:
    """
    INSERT OR IGNORE a single message row.

    Returns True if a new row was inserted, False if the row already
    existed (idempotent replay).
    """
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO message (
            id, room_id, thread_id, in_reply_to,
            from_agent_id, to_agents, mentions_attempted,
            type, body, confidence, schema_version, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            msg["id"],
            msg["room_id"],
            msg.get("thread_id"),
            msg.get("in_reply_to"),
            msg["from"],
            json.dumps(msg.get("to", [])),
            json.dumps(msg["mentions_attempted"]) if msg.get("mentions_attempted") else None,
            msg["type"],
            _coerce_body_to_text(msg.get("body", "")),
            msg.get("confidence"),
            int(msg.get("schema_version", 1)),
            msg["created_at"],
        ),
    )
    return cur.rowcount > 0


def insert_decision(conn: sqlite3.Connection, msg: dict) -> bool:
    """
    INSERT OR IGNORE a decision row derived from a type=decision message.

    The decision.id == message.id (FK CASCADE). Caller is responsible for
    wrapping insert_message + insert_decision in a single transaction.
    """
    body = msg.get("body") or {}
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            body = {}

    pins = body.get("pins")  # answer_id
    summary = body.get("summary") or ""
    supersedes = body.get("supersedes")

    if not pins:
        logger.warning("decision message %s missing body.pins; skipping decision row", msg["id"])
        return False

    cur = conn.execute(
        """
        INSERT OR IGNORE INTO decision (
            id, room_id, question_id, answer_id, body, made_by,
            confidence, valid_from, superseded_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            msg["id"],
            msg["room_id"],
            msg.get("in_reply_to"),  # the original question
            pins,
            summary,
            msg["from"],
            msg.get("confidence"),
            msg["created_at"],
            supersedes,
        ),
    )
    return cur.rowcount > 0


def insert_citations(conn: sqlite3.Connection, message_id: str, citations: Iterable[dict]) -> int:
    """
    INSERT OR IGNORE the citations for a message.

    UNIQUE(message_id, urn) makes this idempotent. Returns count inserted.
    """
    inserted = 0
    for c in citations:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO citation (
                message_id, urn, node_kind, resolved_at_commit, retrieved_via
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                message_id,
                c["urn"],
                c.get("node_kind"),
                c.get("resolved_at_commit"),
                c.get("retrieved_via"),
            ),
        )
        if cur.rowcount > 0:
            inserted += 1
    return inserted


# --- Citation quality check ------------------------------------------------


def has_stable_citation(citations: Iterable[dict]) -> bool:
    """
    True iff at least one citation has node_kind in STABLE_URN_KINDS.

    Spec: every type=answer message must carry >=1 stable-URN citation
    (proposal.md §5 L3). Enforced by the indexer at ingest time, not
    by the writer.
    """
    return any(c.get("node_kind") in STABLE_URN_KINDS for c in citations)


# --- Escalation rule queries ----------------------------------------------


def find_unanswered_or_unsure_questions(
    conn: sqlite3.Connection, room_id: str
) -> list[sqlite3.Row]:
    """
    Return question rows in this room that are candidates for the
    "all-unsure" escalation rule.

    Filter:
      - type='question'
      - to_agents is non-empty (specific agents addressed)
      - no type='decision' message has in_reply_to == question.id (no decision yet)
      - no prior escalation_status with kind='all_unsure' already exists for this question
    """
    return conn.execute(
        """
        SELECT q.id, q.from_agent_id, q.to_agents, q.created_at
        FROM message q
        WHERE q.room_id = ?
          AND q.type = 'question'
          AND q.to_agents != '[]'
          AND NOT EXISTS (
              SELECT 1 FROM decision d WHERE d.question_id = q.id
          )
          AND NOT EXISTS (
              SELECT 1 FROM message s
              WHERE s.room_id = q.room_id
                AND s.type = 'status'
                AND s.in_reply_to = q.id
                AND json_extract(s.body, '$.kind') = 'all_unsure'
          )
        """,
        (room_id,),
    ).fetchall()


def get_answers_for_question(
    conn: sqlite3.Connection, question_id: str
) -> list[sqlite3.Row]:
    """Return all type='answer' messages whose in_reply_to == question_id."""
    return conn.execute(
        """
        SELECT id, from_agent_id, confidence, created_at
        FROM message
        WHERE in_reply_to = ? AND type = 'answer'
        """,
        (question_id,),
    ).fetchall()


def find_idle_buckets(
    conn: sqlite3.Connection, room_id: str, threshold_minutes: int
) -> list[dict]:
    """
    Return buckets (per thread_id, else per room) where the last message
    is older than threshold_minutes AND no escalation_timeout status
    already exists for the current idle stretch.

    Returns list of dicts: {bucket_kind, thread_id, last_id, last_created_at}.
    """
    # Bucket = thread_id if set, else NULL (= the room's catch-all bucket)
    rows = conn.execute(
        """
        SELECT
            thread_id,
            MAX(id) AS last_id,
            MAX(created_at) AS last_created_at
        FROM message
        WHERE room_id = ?
        GROUP BY thread_id
        HAVING (julianday(datetime('now')) - julianday(last_created_at)) * 24 * 60
               > ?
        """,
        (room_id, threshold_minutes),
    ).fetchall()

    buckets = []
    for row in rows:
        # Skip if a timeout escalation already exists for this idle stretch
        # (i.e. created after the bucket's last real message)
        existing = conn.execute(
            """
            SELECT 1 FROM message
            WHERE room_id = ?
              AND type = 'status'
              AND from_agent_id = '_indexer'
              AND json_extract(body, '$.kind') = 'escalation_timeout'
              AND COALESCE(json_extract(body, '$.thread_id'), '') = COALESCE(?, '')
              AND created_at > ?
            LIMIT 1
            """,
            (room_id, row["thread_id"], row["last_created_at"]),
        ).fetchone()
        if existing:
            continue
        buckets.append(
            {
                "thread_id": row["thread_id"],
                "last_id": row["last_id"],
                "last_created_at": row["last_created_at"],
            }
        )
    return buckets


# --- Helpers ---------------------------------------------------------------


def _coerce_body_to_text(body) -> str:
    """
    message.body is TEXT. Plain prose passes through; objects (decision,
    status) are JSON-encoded for storage. Readers can json_extract().
    """
    if isinstance(body, str):
        return body
    return json.dumps(body, ensure_ascii=False)
