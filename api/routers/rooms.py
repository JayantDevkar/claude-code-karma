"""
Rooms router — agent-coord coordination rooms.

Three endpoints, all read-only over the v11 schema (#67):

- GET /rooms                       list view (id, title, status, counts, last_activity)
- GET /rooms/{room_id}             detail view (room + presence + decisions + first 50 messages)
- GET /rooms/{room_id}/messages    paginated timeline

The dashboard frontend (Piece 3) reads exclusively from these endpoints.
sync_rooms() (Piece 2, on a separate branch) writes the underlying tables.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

api_path = Path(__file__).parent.parent
sys.path.insert(0, str(api_path))

from db.connection import sqlite_read  # noqa: E402

logger = logging.getLogger(__name__)
router = APIRouter()


# --- Response schemas ------------------------------------------------------


class RoomSummary(BaseModel):
    id: str
    title: Optional[str] = None
    status: str
    created_at: str
    closed_at: Optional[str] = None
    last_activity: str = Field(
        description=(
            "MAX(message.created_at) for this room, or room.created_at if no "
            "messages yet. Used as the default sort key."
        )
    )
    agent_count: int
    message_count: int
    decision_count: int


class RoomListResponse(BaseModel):
    rooms: list[RoomSummary]
    total: int


class AgentPresence(BaseModel):
    agent_id: str
    repo: Optional[str] = None
    branch: Optional[str] = None
    session_uuid: Optional[str] = None
    is_human: bool
    joined_at: str
    joined_at_commit: Optional[str] = None
    last_seen_at_commit: Optional[str] = None
    left_at: Optional[str] = None


class Citation(BaseModel):
    urn: str
    node_kind: Optional[str] = None
    resolved_at_commit: Optional[str] = None
    retrieved_via: Optional[str] = None


class RoomMessage(BaseModel):
    id: str
    room_id: str
    thread_id: Optional[str] = None
    in_reply_to: Optional[str] = None
    from_agent_id: str
    to_agents: list[str]
    mentions_attempted: Optional[list[str]] = None
    type: str
    body: str  # JSON-encoded for type IN ('decision','status'); prose otherwise
    confidence: Optional[str] = None
    schema_version: int
    created_at: str
    citations: list[Citation] = Field(default_factory=list)


class Decision(BaseModel):
    id: str
    room_id: str
    question_id: str
    answer_id: str
    body: Optional[str] = None
    made_by: Optional[str] = None
    confidence: Optional[str] = None
    valid_from: str
    valid_until: Optional[str] = None
    superseded_by: Optional[str] = None
    status: str
    mirror_state: str
    mirror_attempts: int
    mirror_last_error: Optional[str] = None
    external_system: str
    external_ref_id: Optional[str] = None
    external_ref_url: Optional[str] = None


class RoomDetail(BaseModel):
    room: RoomSummary
    presence: list[AgentPresence]
    decisions: list[Decision]
    messages: list[RoomMessage]  # first N inline for fast initial render
    messages_total: int
    messages_inlined: int


class RoomMessagesResponse(BaseModel):
    messages: list[RoomMessage]
    total: int
    page: int
    per_page: int
    order: str


# --- Helpers ---------------------------------------------------------------

DEFAULT_INLINE_MESSAGES = 50
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 500


def _parse_to_agents(value: Optional[str]) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return []
    return parsed if isinstance(parsed, list) else []


def _parse_mentions(value: Optional[str]) -> Optional[list[str]]:
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return None
    return parsed if isinstance(parsed, list) else None


def _row_to_message(row, citations: list[Citation]) -> RoomMessage:
    return RoomMessage(
        id=row["id"],
        room_id=row["room_id"],
        thread_id=row["thread_id"],
        in_reply_to=row["in_reply_to"],
        from_agent_id=row["from_agent_id"],
        to_agents=_parse_to_agents(row["to_agents"]),
        mentions_attempted=_parse_mentions(row["mentions_attempted"]),
        type=row["type"],
        body=row["body"],
        confidence=row["confidence"],
        schema_version=row["schema_version"],
        created_at=row["created_at"],
        citations=citations,
    )


def _fetch_citations_for(conn, message_ids: list[str]) -> dict[str, list[Citation]]:
    if not message_ids:
        return {}
    placeholders = ",".join("?" * len(message_ids))
    rows = conn.execute(
        f"SELECT message_id, urn, node_kind, resolved_at_commit, retrieved_via "
        f"FROM citation WHERE message_id IN ({placeholders})",
        message_ids,
    ).fetchall()
    grouped: dict[str, list[Citation]] = {}
    for r in rows:
        grouped.setdefault(r["message_id"], []).append(
            Citation(
                urn=r["urn"],
                node_kind=r["node_kind"],
                resolved_at_commit=r["resolved_at_commit"],
                retrieved_via=r["retrieved_via"],
            )
        )
    return grouped


def _row_to_decision(row) -> Decision:
    return Decision(
        id=row["id"],
        room_id=row["room_id"],
        question_id=row["question_id"],
        answer_id=row["answer_id"],
        body=row["body"],
        made_by=row["made_by"],
        confidence=row["confidence"],
        valid_from=row["valid_from"],
        valid_until=row["valid_until"],
        superseded_by=row["superseded_by"],
        status=row["status"],
        mirror_state=row["mirror_state"],
        mirror_attempts=row["mirror_attempts"],
        mirror_last_error=row["mirror_last_error"],
        external_system=row["external_system"],
        external_ref_id=row["external_ref_id"],
        external_ref_url=row["external_ref_url"],
    )


def _v11_tables_present(conn) -> bool:
    """
    True iff the v11 substrate (room/message/decision/...) is present.

    The dashboard runs on installs that haven't yet applied v11 (e.g. the
    sync-branch v22 collision documented in #67). When tables are missing
    we return empty lists instead of 500-ing.
    """
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='room' LIMIT 1"
    ).fetchone()
    return row is not None


# --- Endpoints -------------------------------------------------------------


@router.get("/rooms", response_model=RoomListResponse)
def list_rooms(
    status: Optional[Literal["active", "archived"]] = None,
    search: Optional[str] = Query(default=None, description="Substring on id or title"),
    sort: Literal["activity", "created"] = "activity",
):
    """
    List all coordination rooms with summary counts.

    Sort key:
      - activity (default): MAX(message.created_at) per room, falling back to
        room.created_at when there are no messages. Uses idx_message_room_time.
      - created: room.created_at DESC.
    """
    with sqlite_read() as conn:
        if conn is None or not _v11_tables_present(conn):
            return RoomListResponse(rooms=[], total=0)

        where = []
        params: list = []
        if status:
            where.append("r.status = ?")
            params.append(status)
        if search:
            where.append("(r.id LIKE ? OR COALESCE(r.title, '') LIKE ?)")
            like = f"%{search}%"
            params.extend([like, like])
        where_sql = ("WHERE " + " AND ".join(where)) if where else ""

        if sort == "created":
            order_sql = "ORDER BY r.created_at DESC"
        else:
            order_sql = "ORDER BY last_activity DESC"

        sql = f"""
            SELECT
                r.id,
                r.title,
                r.status,
                r.created_at,
                r.closed_at,
                COALESCE((
                    SELECT MAX(m.created_at) FROM message m WHERE m.room_id = r.id
                ), r.created_at) AS last_activity,
                (SELECT COUNT(*) FROM agent_presence p
                    WHERE p.room_id = r.id AND p.left_at IS NULL) AS agent_count,
                (SELECT COUNT(*) FROM message m WHERE m.room_id = r.id) AS message_count,
                (SELECT COUNT(*) FROM decision d WHERE d.room_id = r.id) AS decision_count
            FROM room r
            {where_sql}
            {order_sql}
        """
        rows = conn.execute(sql, params).fetchall()
        rooms = [
            RoomSummary(
                id=r["id"],
                title=r["title"],
                status=r["status"],
                created_at=r["created_at"],
                closed_at=r["closed_at"],
                last_activity=r["last_activity"],
                agent_count=r["agent_count"],
                message_count=r["message_count"],
                decision_count=r["decision_count"],
            )
            for r in rows
        ]
        return RoomListResponse(rooms=rooms, total=len(rooms))



# NOTE: list_room_messages is registered BEFORE get_room because Starlette's
# matcher iterates in registration order. With `:path` on room_id, get_room
# would otherwise capture "LIN-X/messages" as a room_id and the messages
# endpoint would never fire.
@router.get("/rooms/{room_id:path}/messages", response_model=RoomMessagesResponse)
def list_room_messages(
    room_id: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    order: Literal["asc", "desc"] = "asc",
):
    """
    Paginated timeline. Default ordering is chronological (oldest first) to
    match how the timeline reads top-to-bottom; `order=desc` gives a
    "what just happened" view.
    """
    with sqlite_read() as conn:
        if conn is None or not _v11_tables_present(conn):
            raise HTTPException(status_code=404, detail="rooms feature not enabled")

        exists = conn.execute(
            "SELECT 1 FROM room WHERE id = ? LIMIT 1", (room_id,)
        ).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail=f"room not found: {room_id}")

        total = conn.execute(
            "SELECT COUNT(*) FROM message WHERE room_id = ?", (room_id,)
        ).fetchone()[0]

        order_sql = "DESC" if order == "desc" else "ASC"
        offset = (page - 1) * per_page

        rows = conn.execute(
            f"""
            SELECT id, room_id, thread_id, in_reply_to, from_agent_id,
                   to_agents, mentions_attempted, type, body, confidence,
                   schema_version, created_at
            FROM message
            WHERE room_id = ?
            ORDER BY created_at {order_sql}, id {order_sql}
            LIMIT ? OFFSET ?
            """,
            (room_id, per_page, offset),
        ).fetchall()
        citations_by_msg = _fetch_citations_for(conn, [m["id"] for m in rows])
        messages = [_row_to_message(m, citations_by_msg.get(m["id"], [])) for m in rows]

        return RoomMessagesResponse(
            messages=messages,
            total=total,
            page=page,
            per_page=per_page,
            order=order,
        )


@router.get("/rooms/{room_id:path}", response_model=RoomDetail)
def get_room(room_id: str):
    """
    Single room detail: room summary + presence roster + decisions + first
    DEFAULT_INLINE_MESSAGES inline so the timeline can render immediately.
    Fetch additional pages via /rooms/{id}/messages.

    `:path` converter on room_id supports GitHub-style ids (e.g. owner/repo#N).
    """
    with sqlite_read() as conn:
        if conn is None or not _v11_tables_present(conn):
            raise HTTPException(status_code=404, detail="rooms feature not enabled")

        room_row = conn.execute(
            "SELECT id, title, status, created_at, closed_at FROM room WHERE id = ?",
            (room_id,),
        ).fetchone()
        if room_row is None:
            raise HTTPException(status_code=404, detail=f"room not found: {room_id}")

        last_activity_row = conn.execute(
            "SELECT MAX(created_at) AS la FROM message WHERE room_id = ?",
            (room_id,),
        ).fetchone()
        last_activity = (last_activity_row["la"] if last_activity_row else None) or room_row[
            "created_at"
        ]

        message_count = conn.execute(
            "SELECT COUNT(*) FROM message WHERE room_id = ?", (room_id,)
        ).fetchone()[0]
        decision_count = conn.execute(
            "SELECT COUNT(*) FROM decision WHERE room_id = ?", (room_id,)
        ).fetchone()[0]

        presence_rows = conn.execute(
            """
            SELECT agent_id, repo, branch, session_uuid, is_human, joined_at,
                   joined_at_commit, last_seen_at_commit, left_at
            FROM agent_presence
            WHERE room_id = ?
            ORDER BY is_human DESC, joined_at ASC
            """,
            (room_id,),
        ).fetchall()
        presence = [
            AgentPresence(
                agent_id=p["agent_id"],
                repo=p["repo"],
                branch=p["branch"],
                session_uuid=p["session_uuid"],
                is_human=bool(p["is_human"]),
                joined_at=p["joined_at"],
                joined_at_commit=p["joined_at_commit"],
                last_seen_at_commit=p["last_seen_at_commit"],
                left_at=p["left_at"],
            )
            for p in presence_rows
        ]
        agent_count = sum(1 for p in presence if p.left_at is None)

        decision_rows = conn.execute(
            """
            SELECT * FROM decision WHERE room_id = ?
            ORDER BY valid_from ASC
            """,
            (room_id,),
        ).fetchall()
        decisions = [_row_to_decision(d) for d in decision_rows]

        message_rows = conn.execute(
            """
            SELECT id, room_id, thread_id, in_reply_to, from_agent_id,
                   to_agents, mentions_attempted, type, body, confidence,
                   schema_version, created_at
            FROM message
            WHERE room_id = ?
            ORDER BY created_at ASC, id ASC
            LIMIT ?
            """,
            (room_id, DEFAULT_INLINE_MESSAGES),
        ).fetchall()
        citations_by_msg = _fetch_citations_for(conn, [m["id"] for m in message_rows])
        messages = [
            _row_to_message(m, citations_by_msg.get(m["id"], [])) for m in message_rows
        ]

        room = RoomSummary(
            id=room_row["id"],
            title=room_row["title"],
            status=room_row["status"],
            created_at=room_row["created_at"],
            closed_at=room_row["closed_at"],
            last_activity=last_activity,
            agent_count=agent_count,
            message_count=message_count,
            decision_count=decision_count,
        )

        return RoomDetail(
            room=room,
            presence=presence,
            decisions=decisions,
            messages=messages,
            messages_total=message_count,
            messages_inlined=len(messages),
        )


