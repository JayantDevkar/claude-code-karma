"""
Ticket linking router.

Endpoints:
  POST   /sessions/{uuid}/tickets            create link (idempotent)
  GET    /sessions/{uuid}/tickets            list linked tickets
  DELETE /sessions/{uuid}/tickets/{ticket_id} unlink
  PUT    /tickets/{provider}/{external_key}  refresh cached metadata
  PATCH  /tickets/{provider}/{external_key}  dashboard manual metadata edit
  GET    /tickets                            list all tickets w/ session_count
  GET    /tickets/{provider}/{external_key}            ticket detail
  GET    /tickets/{provider}/{external_key}/sessions   sessions linked to ticket

Writes go through the writer singleton (get_writer_db); reads use a
short-lived read connection (create_read_connection). The router is
mounted in main.py with no prefix because it spans two URL roots.

See: docs/superpowers/specs/2026-05-13-session-ticket-linking-design.md
"""

from __future__ import annotations

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, HTTPException, Query

from db.connection import create_read_connection, get_writer_db
from db.ticket_queries import (
    delete_session_ticket,
    get_link_row,
    get_session_tickets,
    get_ticket_by_id,
    get_ticket_by_key,
    get_ticket_sessions,
    list_tickets,
    update_ticket_metadata,
    upsert_session_ticket,
    upsert_ticket,
)
from models.ticket import (
    LinkCreateRequest,
    LinkResponse,
    MetadataUpdate,
    Provider,
    SessionTicketLink,
    Ticket,
    TicketListItem,
)
from routers.projects import safely_resolve_project
from services.ticket_parser import parse_ticket_ref
from services.ticket_session_enrichment import enrich_sessions_with_live

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tickets"])


def _bad_ref(ref: str) -> HTTPException:
    return HTTPException(
        status_code=400,
        detail={
            "error": "could not parse ticket ref",
            "ref": ref,
            "hint": (
                "Pass a recognized URL (Linear/Jira/GitHub) or a fully-qualified "
                "ref like 'LINEAR-123' (with provider='linear') or 'owner/repo#42'. "
                "Bare '#N' is not supported — qualify with owner/repo."
            ),
        },
    )


# ---------------------------------------------------------------------------
# Session-scoped: link/list/unlink
# ---------------------------------------------------------------------------


@router.post("/sessions/{uuid}/tickets", response_model=LinkResponse)
def create_link(uuid: str, body: LinkCreateRequest) -> LinkResponse:
    """Link a ticket to a session.

    Idempotent on (session_uuid, ticket_id). `link_source` upgrades on
    re-POST per precedence (slash_command > dashboard > branch); never
    downgrades. Metadata is NOT touched here — use PUT /tickets/... after
    an MCP fetch.
    """
    ref = parse_ticket_ref(body.ref, hint_provider=body.provider)
    if ref is None:
        raise _bad_ref(body.ref)

    # Caller-supplied URL wins over the parser's best-effort URL
    # (e.g., dashboard pastes a full URL; parser may have generated a
    # search-page fallback for a bare key).
    canonical_url = body.url or ref.url

    conn = get_writer_db()
    try:
        conn.execute("BEGIN IMMEDIATE")

        ticket_id = upsert_ticket(
            conn,
            provider=ref.provider,
            external_key=ref.external_key,
            url=canonical_url,
        )

        link_id, effective_source = upsert_session_ticket(
            conn,
            session_uuid=uuid,
            session_slug=body.session_slug,
            ticket_id=ticket_id,
            link_source=body.source,
        )

        conn.commit()
    except Exception:
        conn.rollback()
        raise

    ticket_row = get_ticket_by_id(conn, ticket_id)
    link_row = get_link_row(conn, link_id)
    if ticket_row is None or link_row is None:
        # Defensive — both rows just got created in the same transaction.
        raise HTTPException(status_code=500, detail="link created but row not found")

    return LinkResponse(
        ticket=Ticket(**ticket_row),
        link=SessionTicketLink(**link_row),
    )


@router.get("/sessions/{uuid}/tickets")
def list_session_tickets(uuid: str) -> list[dict]:
    """All tickets linked to one session, with the link metadata inline."""
    conn = create_read_connection()
    try:
        return get_session_tickets(conn, uuid)
    finally:
        conn.close()


@router.delete("/sessions/{uuid}/tickets/{ticket_id}")
def unlink_session_ticket(uuid: str, ticket_id: int) -> dict:
    """Unlink one ticket from one session. The ticket row stays in the
    registry — another session may still be linked."""
    conn = get_writer_db()
    try:
        removed = delete_session_ticket(conn, session_uuid=uuid, ticket_id=ticket_id)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    if not removed:
        raise HTTPException(status_code=404, detail="link not found")
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Ticket-centric: list/detail/refresh
# ---------------------------------------------------------------------------


@router.get("/tickets", response_model=list[TicketListItem])
def list_all_tickets(
    provider: Annotated[Optional[Provider], Query()] = None,
    q: Annotated[Optional[str], Query(description="Substring of key or title")] = None,
    project: Annotated[
        Optional[str],
        Query(
            description=(
                "Project identifier — accepts either the URL slug "
                "(e.g. 'myrepo-1044') or the raw encoded_name "
                "(e.g. '-Users-me-myrepo'). Restricts to tickets that "
                "touch this project, with cross-encoded aggregation when "
                "the project has a populated git_identity."
            )
        ),
    ] = None,
) -> list[TicketListItem]:
    """List tickets with session counts. Filterable by provider, project,
    and substring search across key/title.

    The `project` param accepts either form (slug or encoded_name) via
    `safely_resolve_project`, which is essential because the user-facing
    URL carries the slug while internal session APIs use encoded_names.
    """
    conn = create_read_connection()
    try:
        rows = list_tickets(
            conn,
            provider=provider,
            q=q,
            project=safely_resolve_project(project),
        )
    finally:
        conn.close()
    return [TicketListItem(**r) for r in rows]


# Declare /sessions route BEFORE the bare ticket detail so Starlette's
# non-greedy {:path} match prefers the more specific suffix when present.
@router.get("/tickets/{provider}/{external_key:path}/sessions")
def list_sessions_for_ticket(provider: Provider, external_key: str) -> list[dict]:
    """All sessions linked to one ticket.

    Rows for sessions that haven't been indexed yet (active sessions whose
    JSONL is still being written) are enriched from the live-sessions
    filesystem via `enrich_sessions_with_live`. True orphans (no indexed
    row AND no live state) keep NULL session fields and `live: None` so the
    frontend can render them distinctly.
    """
    conn = create_read_connection()
    try:
        rows = get_ticket_sessions(conn, provider=provider, external_key=external_key)
    finally:
        conn.close()
    return enrich_sessions_with_live(rows)


@router.get("/tickets/{provider}/{external_key:path}", response_model=Ticket)
def get_ticket(provider: Provider, external_key: str) -> Ticket:
    """One ticket by (provider, external_key). external_key uses :path so
    GitHub-style 'owner/repo#42' (which contains a slash) routes correctly."""
    conn = create_read_connection()
    try:
        row = get_ticket_by_key(conn, provider=provider, external_key=external_key)
    finally:
        conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="ticket not found")
    return Ticket(**row)


def _refresh_metadata(provider: Provider, external_key: str, body: MetadataUpdate) -> Ticket:
    conn = get_writer_db()
    try:
        found = update_ticket_metadata(
            conn,
            provider=provider,
            external_key=external_key,
            title=body.title,
            status=body.status,
            metadata_json=body.metadata_json,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    if not found:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "ticket not found",
                "hint": "create the link first via POST /sessions/{uuid}/tickets",
            },
        )
    row = get_ticket_by_key(conn, provider=provider, external_key=external_key)
    assert row is not None  # just updated successfully
    return Ticket(**row)


@router.put("/tickets/{provider}/{external_key:path}", response_model=Ticket)
def refresh_ticket_metadata(provider: Provider, external_key: str, body: MetadataUpdate) -> Ticket:
    """Agent-driven refresh: replace title/status/metadata with MCP-fetched
    values. COALESCE preserves existing non-null fields when caller passes
    None, so a degraded MCP fetch never wipes prior data."""
    return _refresh_metadata(provider, external_key, body)


@router.patch("/tickets/{provider}/{external_key:path}", response_model=Ticket)
def patch_ticket_metadata(provider: Provider, external_key: str, body: MetadataUpdate) -> Ticket:
    """Dashboard manual metadata edit. Same DB semantics as PUT; distinct
    endpoint kept for auditability (future: emit different log events)."""
    return _refresh_metadata(provider, external_key, body)
