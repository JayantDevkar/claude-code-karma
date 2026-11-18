"""
The HTTP answer for a timeline: conditional requests, peer-session links, cache headers.

A timeline is built from the conversation's files, but the links on its session messages
come from the index. So its ETag covers both, and a timeline whose links could not be
looked up is never stored by the browser.
"""

from __future__ import annotations

from datetime import datetime
from typing import Callable, Optional

from fastapi import Request, Response
from fastapi.responses import JSONResponse

from http_caching import build_cache_headers, check_conditional_request
from schemas import TimelineEvent
from services.conversation_endpoints import timeline_etag
from services.session_lookup import sessions_by_name
from services.timeline_links import (
    apply_peer_links,
    links_etag,
    peer_refs,
    recall_refs,
    remember_refs,
    resolve_peer_links,
)


def timeline_response(
    request: Request,
    *,
    file_etag: Optional[str],
    last_modified: Optional[datetime],
    own_uuid: str,
    fresh: bool,
    build: Callable[[], list[TimelineEvent]],
) -> Response:
    """
    Answer a timeline request, building the events only when the client's copy is out of date.

    Args:
        file_etag: ETag over the conversation's files
        own_uuid: The session the timeline belongs to (never linked to itself)
        fresh: Minimal cache lifetime, for live polling
        build: Builds the events
    """
    base_etag = timeline_etag(file_etag)

    # A timeline built before: its links can be re-resolved without rebuilding it
    known = recall_refs(base_etag) if base_etag else None
    if known is not None:
        etag = _current_etag(base_etag, known, own_uuid)
        if etag is not None:
            not_modified = check_conditional_request(request, etag, last_modified)
            if not_modified:
                return not_modified

    events = build()
    refs = peer_refs(events)
    if base_etag:
        remember_refs(base_etag, refs)

    found = sessions_by_name({ref.name for ref in refs}) if refs else {}
    if found is None:
        # Links were wanted but the index could not be asked: do not let this copy be kept
        headers = {"Cache-Control": "no-store"}
    else:
        links = resolve_peer_links(refs, found, own_uuid)
        apply_peer_links(events, links)
        etag = links_etag(base_etag, links) if base_etag else None
        not_modified = check_conditional_request(request, etag, last_modified)
        if not_modified:
            return not_modified
        headers = build_cache_headers(
            etag=etag,
            last_modified=last_modified,
            max_age=1 if fresh else 60,
            stale_while_revalidate=2 if fresh else 300,
            private=True,
        )
    body = [event.model_dump(mode="json") for event in events]
    return JSONResponse(content=body, headers=headers)


def _current_etag(base_etag: str, refs: tuple, own_uuid: str) -> Optional[str]:
    """The ETag this timeline has right now; None when its links cannot be looked up."""
    if not refs:
        return base_etag
    found = sessions_by_name({ref.name for ref in refs})
    if found is None:
        return None
    return links_etag(base_etag, resolve_peer_links(refs, found, own_uuid))
