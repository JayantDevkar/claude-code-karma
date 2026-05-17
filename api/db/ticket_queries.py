"""
SQLite queries for ticket linking.

Reads use a read-only connection (`sqlite_read()` / `create_read_connection()`).
Writes use the writer singleton (`get_writer_db()`), which serializes
mutations via SQLite's WAL writer lock. All write functions wrap their
multi-statement work in an explicit transaction.

See: docs/superpowers/specs/2026-05-13-session-ticket-linking-design.md
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


def upsert_ticket(
    conn: sqlite3.Connection,
    *,
    provider: str,
    external_key: str,
    url: str,
) -> int:
    """Insert-or-update the tickets row keyed on (provider, external_key).

    Returns the row's id. URL is refreshed on conflict so a later link with
    a canonical URL replaces an earlier search-fallback URL.
    """
    row = conn.execute(
        """
        INSERT INTO tickets (provider, external_key, url, first_seen_at)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT (provider, external_key) DO UPDATE
            SET url = excluded.url
        RETURNING id
        """,
        (provider, external_key, url),
    ).fetchone()
    return row["id"]


# Numeric precedence for link_source. Higher = more trustworthy.
# slash_command > dashboard > branch.
_SOURCE_PRECEDENCE = {"branch": 1, "dashboard": 2, "slash_command": 3}


def upsert_session_ticket(
    conn: sqlite3.Connection,
    *,
    session_uuid: str,
    session_slug: Optional[str],
    ticket_id: int,
    link_source: str,
) -> tuple[int, str]:
    """Insert-or-find-and-upgrade a session_tickets row.

    Two unique constraints can match an existing row:
      1. UNIQUE(session_uuid, ticket_id) — same session re-linking same ticket.
      2. Partial UNIQUE(session_slug, ticket_id) WHERE slug NOT NULL —
         a different UUID resuming the SAME logical session (same slug).

    When either match exists, we reuse that row and possibly upgrade
    link_source per precedence (slash_command > dashboard > branch).
    Slug is filled in if previously NULL.

    Returns (link_id, effective_link_source).
    """
    if link_source not in _SOURCE_PRECEDENCE:
        raise ValueError(f"invalid link_source: {link_source!r}")

    existing = _find_existing_link(
        conn,
        session_uuid=session_uuid,
        session_slug=session_slug,
        ticket_id=ticket_id,
    )

    if existing is not None:
        new_source = (
            link_source
            if _SOURCE_PRECEDENCE[link_source] > _SOURCE_PRECEDENCE[existing["link_source"]]
            else existing["link_source"]
        )
        new_slug = existing["session_slug"] or session_slug

        if new_source != existing["link_source"] or new_slug != existing["session_slug"]:
            conn.execute(
                """
                UPDATE session_tickets
                   SET link_source  = ?,
                       session_slug = ?
                 WHERE id = ?
                """,
                (new_source, new_slug, existing["id"]),
            )

        return existing["id"], new_source

    # No matching row — insert a fresh one.
    inserted = conn.execute(
        """
        INSERT INTO session_tickets
            (session_uuid, session_slug, ticket_id, link_source, linked_at)
        VALUES (?, ?, ?, ?, datetime('now'))
        RETURNING id
        """,
        (session_uuid, session_slug, ticket_id, link_source),
    ).fetchone()
    return inserted["id"], link_source


def _find_existing_link(
    conn: sqlite3.Connection,
    *,
    session_uuid: str,
    session_slug: Optional[str],
    ticket_id: int,
) -> Optional[dict]:
    """Look up an existing session_tickets row matching either unique
    constraint. (session_uuid, ticket_id) takes precedence; falls back
    to the (session_slug, ticket_id) partial index when slug is present.
    """
    row = conn.execute(
        """
        SELECT id, session_uuid, session_slug, link_source
          FROM session_tickets
         WHERE session_uuid = ? AND ticket_id = ?
        """,
        (session_uuid, ticket_id),
    ).fetchone()
    if row is not None:
        return dict(row)

    if session_slug:
        row = conn.execute(
            """
            SELECT id, session_uuid, session_slug, link_source
              FROM session_tickets
             WHERE session_slug = ? AND ticket_id = ?
            """,
            (session_slug, ticket_id),
        ).fetchone()
        if row is not None:
            return dict(row)

    return None


def update_ticket_metadata(
    conn: sqlite3.Connection,
    *,
    provider: str,
    external_key: str,
    title: Optional[str] = None,
    status: Optional[str] = None,
    metadata_json: Optional[str] = None,
) -> bool:
    """Refresh cached metadata for a ticket.

    `COALESCE` preserves existing non-null values when the caller passes
    None — so a degraded slash-command call (MCP unavailable) never wipes
    previously cached data.

    Returns True if the row was found, False otherwise.
    """
    cur = conn.execute(
        """
        UPDATE tickets
           SET title               = COALESCE(?, title),
               status              = COALESCE(?, status),
               metadata_json       = COALESCE(?, metadata_json),
               metadata_updated_at = datetime('now')
         WHERE provider = ? AND external_key = ?
        """,
        (title, status, metadata_json, provider, external_key),
    )
    return cur.rowcount > 0


def delete_session_ticket(
    conn: sqlite3.Connection,
    *,
    session_uuid: str,
    ticket_id: int,
) -> bool:
    """Unlink one ticket from one session. Returns True if a row was removed."""
    cur = conn.execute(
        "DELETE FROM session_tickets WHERE session_uuid = ? AND ticket_id = ?",
        (session_uuid, ticket_id),
    )
    return cur.rowcount > 0


def cleanup_orphan_session_tickets(
    conn: sqlite3.Connection,
    *,
    ttl_days: int = 7,
) -> int:
    """Delete session_tickets rows whose session_uuid never materialized.

    Run periodically from the FastAPI lifespan task. Returns count removed.
    """
    cur = conn.execute(
        f"""
        DELETE FROM session_tickets
         WHERE session_uuid NOT IN (SELECT uuid FROM sessions)
           AND linked_at < datetime('now', '-{int(ttl_days)} days')
        """,
    )
    return cur.rowcount


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


def get_ticket_by_key(
    conn: sqlite3.Connection,
    *,
    provider: str,
    external_key: str,
) -> Optional[dict]:
    """Fetch one ticket row by (provider, external_key)."""
    row = conn.execute(
        """
        SELECT id, provider, external_key, url, title, status,
               metadata_json, metadata_updated_at, first_seen_at
          FROM tickets
         WHERE provider = ? AND external_key = ?
        """,
        (provider, external_key),
    ).fetchone()
    return dict(row) if row else None


def get_ticket_by_id(conn: sqlite3.Connection, ticket_id: int) -> Optional[dict]:
    """Fetch one ticket row by id."""
    row = conn.execute(
        """
        SELECT id, provider, external_key, url, title, status,
               metadata_json, metadata_updated_at, first_seen_at
          FROM tickets
         WHERE id = ?
        """,
        (ticket_id,),
    ).fetchone()
    return dict(row) if row else None


def get_session_tickets(conn: sqlite3.Connection, session_uuid: str) -> list[dict]:
    """All tickets linked to one session, with link metadata inline."""
    rows = conn.execute(
        """
        SELECT t.id, t.provider, t.external_key, t.url, t.title, t.status,
               t.metadata_json, t.metadata_updated_at, t.first_seen_at,
               st.id           AS link_id,
               st.link_source  AS link_source,
               st.linked_at    AS linked_at,
               st.session_slug AS session_slug
          FROM session_tickets st
          JOIN tickets t ON t.id = st.ticket_id
         WHERE st.session_uuid = ?
         ORDER BY st.linked_at DESC
        """,
        (session_uuid,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_ticket_sessions(
    conn: sqlite3.Connection,
    *,
    provider: str,
    external_key: str,
) -> list[dict]:
    """Sessions linked to one ticket. LEFT JOIN to sessions so orphan
    links (session_uuid present in session_tickets but not yet in the
    sessions index) still appear with NULL session fields."""
    rows = conn.execute(
        """
        SELECT st.id                    AS link_id,
               st.session_uuid          AS session_uuid,
               st.session_slug          AS session_slug,
               st.link_source           AS link_source,
               st.linked_at             AS linked_at,
               s.slug                   AS sessions_slug,
               s.project_encoded_name   AS project_encoded_name,
               s.start_time             AS start_time,
               s.end_time               AS end_time,
               s.initial_prompt         AS initial_prompt
          FROM session_tickets st
          JOIN tickets t      ON t.id  = st.ticket_id
          LEFT JOIN sessions s ON s.uuid = st.session_uuid
         WHERE t.provider = ? AND t.external_key = ?
         ORDER BY st.linked_at DESC
        """,
        (provider, external_key),
    ).fetchall()
    return [dict(r) for r in rows]


def list_tickets(
    conn: sqlite3.Connection,
    *,
    provider: Optional[str] = None,
    q: Optional[str] = None,
) -> list[dict]:
    """List tickets with session counts. Supports provider filter and
    case-insensitive substring search across key and title."""
    where = []
    params: list = []
    if provider:
        where.append("t.provider = ?")
        params.append(provider)
    if q:
        where.append("(t.external_key LIKE ? OR LOWER(COALESCE(t.title,'')) LIKE LOWER(?))")
        like = f"%{q}%"
        params.extend([like, like])

    where_clause = ("WHERE " + " AND ".join(where)) if where else ""

    rows = conn.execute(
        f"""
        SELECT t.id, t.provider, t.external_key, t.url, t.title, t.status,
               t.first_seen_at, t.metadata_updated_at,
               COUNT(st.id)        AS session_count,
               MAX(st.linked_at)   AS last_linked_at
          FROM tickets t
          LEFT JOIN session_tickets st ON st.ticket_id = t.id
          {where_clause}
         GROUP BY t.id
         ORDER BY COALESCE(MAX(st.linked_at), t.first_seen_at) DESC
        """,
        params,
    ).fetchall()
    return [dict(r) for r in rows]


def get_link_row(
    conn: sqlite3.Connection,
    link_id: int,
) -> Optional[dict]:
    """Fetch one session_tickets row by id."""
    row = conn.execute(
        """
        SELECT id, session_uuid, session_slug, ticket_id, link_source, linked_at
          FROM session_tickets
         WHERE id = ?
        """,
        (link_id,),
    ).fetchone()
    return dict(row) if row else None
