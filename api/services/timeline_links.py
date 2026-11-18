"""
Links from a timeline's session messages to the Karma session on the other end.

A message names its peer session; the index knows which sessions carry that name
and when they ran. This module is pure: the caller supplies what the index said.
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping, NamedTuple, Optional, Sequence

from schemas import TimelineEvent


@dataclass(frozen=True)
class NamedSession:
    """A session that carries a given name, and when it ran."""

    uuid: str
    project_encoded_name: str
    start_time: Optional[datetime]
    end_time: Optional[datetime]


class PeerRef(NamedTuple):
    """One timeline message whose peer is a named session."""

    event_id: str
    name: str
    timestamp: datetime


# The sender's last entry and the receiver's entry are written moments apart.
_PEER_CLOCK_SLACK = timedelta(seconds=5)


def peer_refs(events: Sequence[TimelineEvent]) -> tuple[PeerRef, ...]:
    """The messages of a timeline that could link to another session."""
    return tuple(
        PeerRef(e.id, e.metadata["peer_name"], e.timestamp)
        for e in events
        if e.event_type == "message"
        and e.metadata.get("peer_kind") == "session"
        and e.metadata.get("peer_name")
    )


def resolve_peer_links(
    refs: Sequence[PeerRef],
    sessions_by_name: Mapping[str, Sequence[NamedSession]],
    own_uuid: Optional[str] = None,
) -> dict[str, NamedSession]:
    """
    Event id -> the session on the other end, for the messages that have exactly one candidate.

    A candidate is another session with the peer's name that was running at the moment
    of the message. Several candidates are never guessed between.
    """
    links: dict[str, NamedSession] = {}
    for ref in refs:
        running = [
            s
            for s in sessions_by_name.get(ref.name, ())
            if s.uuid != own_uuid and _was_running(s, ref.timestamp)
        ]
        if len(running) == 1:
            links[ref.event_id] = running[0]
    return links


def apply_peer_links(events: Sequence[TimelineEvent], links: Mapping[str, NamedSession]) -> None:
    """Write the resolved links into the events' metadata."""
    for event in events:
        session = links.get(event.id)
        if session is not None:
            event.metadata["peer_session_uuid"] = session.uuid
            event.metadata["peer_project_encoded_name"] = session.project_encoded_name


def link_peer_sessions(
    events: Sequence[TimelineEvent],
    sessions_by_name: Mapping[str, Sequence[NamedSession]],
    own_uuid: Optional[str] = None,
) -> dict[str, NamedSession]:
    """Resolve and apply the links of a timeline in one step; returns what was linked."""
    links = resolve_peer_links(peer_refs(events), sessions_by_name, own_uuid)
    apply_peer_links(events, links)
    return links


def links_etag(base_etag: str, links: Mapping[str, NamedSession]) -> str:
    """The timeline's ETag with its resolved links folded in; the base ETag when there are none."""
    if not links:
        return base_etag
    pairs = "|".join(f"{event_id}={s.uuid}" for event_id, s in sorted(links.items()))
    digest = hashlib.md5(pairs.encode()).hexdigest()[:12]
    return f'"{base_etag.strip(chr(34))}-l{digest}"'


def _was_running(session: NamedSession, moment: datetime) -> bool:
    if session.start_time is None or session.end_time is None:
        return False
    try:
        return session.start_time <= moment <= session.end_time + _PEER_CLOCK_SLACK
    except TypeError:
        # Naive and aware timestamps cannot be compared
        return False


# Peer refs of timelines already built, by their file ETag: lets a revalidation re-resolve
# the links from the index without rebuilding the timeline.
_REFS_KEPT = 512
_refs_by_etag: OrderedDict[str, tuple[PeerRef, ...]] = OrderedDict()
_refs_lock = threading.Lock()


def remember_refs(etag: str, refs: tuple[PeerRef, ...]) -> None:
    with _refs_lock:
        _refs_by_etag[etag] = refs
        _refs_by_etag.move_to_end(etag)
        while len(_refs_by_etag) > _REFS_KEPT:
            _refs_by_etag.popitem(last=False)


def recall_refs(etag: str) -> Optional[tuple[PeerRef, ...]]:
    """The peer refs of the timeline with this file ETag; None if it has not been built here."""
    with _refs_lock:
        return _refs_by_etag.get(etag)
