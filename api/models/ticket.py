"""
Ticket models for session ↔ ticket linking.

Karma is a read-only observer. The agent (via MCP) supplies metadata at link
time; karma stores the link record and caches title/status for display.

See: docs/superpowers/specs/2026-05-13-session-ticket-linking-design.md
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Provider = Literal["linear", "jira", "github"]
LinkSource = Literal["branch", "slash_command", "dashboard"]


class TicketRef(BaseModel):
    """Output of the URL/ref parser. Immutable."""

    model_config = ConfigDict(frozen=True)

    provider: Provider
    external_key: str = Field(min_length=1)
    url: str = Field(min_length=1)


class Ticket(BaseModel):
    """A ticket row from the registry."""

    model_config = ConfigDict(frozen=True)

    id: int
    provider: Provider
    external_key: str
    url: str
    title: Optional[str] = None
    status: Optional[str] = None
    metadata_json: Optional[str] = None
    metadata_updated_at: Optional[str] = None
    first_seen_at: str


class SessionTicketLink(BaseModel):
    """A link row from session_tickets."""

    model_config = ConfigDict(frozen=True)

    id: int
    session_uuid: str
    session_slug: Optional[str] = None
    ticket_id: int
    link_source: LinkSource
    linked_at: str


class LinkCreateRequest(BaseModel):
    """Body of POST /sessions/{uuid}/tickets."""

    model_config = ConfigDict(frozen=True)

    ref: str = Field(min_length=1, description="Ticket key or URL (e.g., LINEAR-123 or full URL)")
    provider: Optional[Provider] = Field(
        default=None,
        description="Hint when ref is a bare alphanumeric key like ABC-123. Required for bare keys.",
    )
    url: Optional[str] = Field(default=None, description="Optional override URL")
    session_slug: Optional[str] = Field(
        default=None,
        description="Session slug for dedup across resumes. Populate when known.",
    )
    source: LinkSource


class MetadataUpdate(BaseModel):
    """Body of PUT /tickets/{provider}/{external_key} and PATCH variant."""

    model_config = ConfigDict(frozen=True)

    title: Optional[str] = None
    status: Optional[str] = None
    metadata_json: Optional[str] = Field(
        default=None,
        max_length=65536,
        description="Raw MCP payload (capped at 64 KB to match the DB CHECK constraint).",
    )


class LinkResponse(BaseModel):
    """Response from POST /sessions/{uuid}/tickets — full link + ticket."""

    model_config = ConfigDict(frozen=True)

    link: SessionTicketLink
    ticket: Ticket


class TicketListItem(BaseModel):
    """Row for GET /tickets — ticket plus session count."""

    model_config = ConfigDict(frozen=True)

    id: int
    provider: Provider
    external_key: str
    url: str
    title: Optional[str] = None
    status: Optional[str] = None
    first_seen_at: str
    metadata_updated_at: Optional[str] = None
    session_count: int
    last_linked_at: Optional[str] = None
