"""
Enrich session_tickets rows with live-session fallback data.

Problem
-------
A session UUID linked to a ticket may not yet have a row in the `sessions`
SQLite table — sessions are indexed at `SessionEnd`, but the link could
have been created mid-session (via the link-ticket-to-session skill, or
the branch-detect hook at SessionStart). The naive LEFT JOIN in
get_ticket_sessions therefore returns NULL session fields for active
sessions, making them indistinguishable from real orphans.

We have authoritative data for active sessions: the live-session JSON
files written by `hooks/live_session_tracker.py` under
`~/.claude_karma/live-sessions/`. The `LiveSessionState` model exposes
`session_id`, `session_ids[]` (for resumed sessions), `slug`, `state`,
`cwd`, `started_at`, `updated_at`, and a computed
`resolved_project_encoded_name`.

Strategy
--------
- Batch-load every live-session file ONCE per request via
  `load_all_live_sessions()`.
- Build a `{session_uuid: LiveSessionState}` lookup including both the
  current `session_id` and every historical UUID in `session_ids[]`, so
  resumed sessions (link made to an earlier UUID, current state under a
  newer UUID) still resolve.
- For each session_tickets row whose `sessions_slug` is None (no indexed
  sessions row), look up the live state. If found, fill in
  `sessions_slug`, `project_encoded_name`, `start_time` from the live
  data, and attach a `live` block exposing the active status.
- Rows that have neither a sessions row nor a live state are TRUE
  orphans (frontend renders them as such).

The `live` block is additive — rows with an indexed sessions row are
returned unchanged with `live: None`.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from models.live_session import LiveSessionState, load_all_live_sessions

logger = logging.getLogger(__name__)


def _build_uuid_index(sessions: list[LiveSessionState]) -> dict[str, LiveSessionState]:
    """Map every UUID a live state knows about to that state.

    A `LiveSessionState` tracks both `session_id` (current) and
    `session_ids[]` (historical, for resumed sessions). A ticket linked
    to an earlier UUID must still resolve to the active state.

    Two-pass build to guarantee "current beats historical" regardless of
    input order: pass 1 fills from historical session_ids; pass 2
    overwrites with current session_id. Without the explicit two passes,
    correctness relied on within-iteration ordering of statements — a
    fragile invariant flagged in review.
    """
    index: dict[str, LiveSessionState] = {}
    # Pass 1: historical UUIDs (lower priority). setdefault keeps the
    # first historical reference if two states list the same prior UUID.
    for state in sessions:
        for prior in state.session_ids or []:
            index.setdefault(prior, state)
    # Pass 2: current session_id always wins, even if it appeared as a
    # historical UUID under a different state in pass 1.
    for state in sessions:
        if state.session_id:
            index[state.session_id] = state
    return index


def _live_block(state: LiveSessionState) -> dict[str, Any]:
    """The additive `live` field returned to the frontend.

    Kept narrow on purpose: only fields the UI actually renders.
    `cwd` is included so an unindexed live session can still link out
    to its project.
    """
    return {
        "status": state.state.value if hasattr(state.state, "value") else str(state.state),
        "started_at": state.started_at.isoformat() if state.started_at else None,
        "last_updated": state.updated_at.isoformat() if state.updated_at else None,
        "cwd": state.cwd or None,
    }


def _augment_row(row: dict[str, Any], state: LiveSessionState) -> None:
    """Fill missing sessions-table fields from live state, in place.

    Only fields that the LEFT JOIN would have populated are touched, and
    only when they are currently None — never overwrite indexed data.
    `initial_prompt` is intentionally not derived (would require reading
    an open transcript JSONL). Returns nothing — mutation is the point.
    """
    if not row.get("sessions_slug") and state.slug:
        row["sessions_slug"] = state.slug
    if not row.get("project_encoded_name"):
        # `resolved_project_encoded_name` handles worktree / git-root fallback.
        encoded = state.resolved_project_encoded_name
        if encoded:
            row["project_encoded_name"] = encoded
    if not row.get("start_time") and state.started_at:
        row["start_time"] = state.started_at.isoformat()

    row["live"] = _live_block(state)


def enrich_sessions_with_live(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fall back to live-sessions data for rows missing an indexed session.

    Mutates each row dict in place: every row gets a `live` key (None
    when no live state matches), and rows that lacked sessions-table
    data get those fields backfilled from live state. Returns the same
    list for caller ergonomics. The mutation is intentional — rows are
    locally owned by `list_sessions_for_ticket` and not shared.

    Performance note: makes ONE filesystem scan of the live-sessions
    directory per call, regardless of how many rows are passed. Suitable
    for endpoints that already perform per-request work.
    """
    # Fast path: no rows that need enrichment.
    missing_indices = [i for i, r in enumerate(rows) if not r.get("sessions_slug")]
    if not missing_indices:
        # Still attach `live: None` for response-shape consistency.
        for r in rows:
            r.setdefault("live", None)
        return rows

    try:
        live_states = load_all_live_sessions()
    except Exception as e:
        # Live-session read should never break the ticket endpoint.
        logger.warning("Live-sessions read failed during ticket enrichment: %s", e)
        for r in rows:
            r.setdefault("live", None)
        return rows

    index = _build_uuid_index(live_states)

    for i in missing_indices:
        row = rows[i]
        uuid = row.get("session_uuid")
        if not uuid:
            continue
        state = index.get(uuid)
        if state is None:
            continue  # true orphan — leave row as-is
        _augment_row(row, state)

    # Rows that already had indexed data get `live: None`.
    for r in rows:
        r.setdefault("live", None)

    return rows


def _find_live_for_uuid(uuid: str) -> Optional[LiveSessionState]:
    """Single-row variant — internal convenience for tests only.

    Endpoint code should call `enrich_sessions_with_live` so the
    directory scan amortizes across all rows. The leading underscore
    is the discouragement: don't reach for this in router code.
    """
    if not uuid:
        return None
    try:
        sessions = load_all_live_sessions()
    except Exception:
        return None
    return _build_uuid_index(sessions).get(uuid)
