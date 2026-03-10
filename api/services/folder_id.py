"""Karma folder ID parsing utilities.

Shared by both the API (``api/routers/sync_status.py``) and the CLI
(``cli/karma/pending.py``).  All folder-ID disambiguation logic lives
here so there is exactly one implementation to maintain.

Folder ID formats
-----------------
- ``karma-out-{username}-{suffix}``  — session outbox/inbox
- ``karma-join-{username}-{team}``   — team handshake signal

The core problem: both *username* and *suffix* (or *team*) can contain
hyphens, so a naive ``split("-")`` is ambiguous.  When a set of known
values is provided, all possible splits are tried and the longest
matching known value wins.  Without hints the shortest-first split is
returned (unreliable for hyphenated names — callers should treat this
as a best-effort fallback).
"""

from __future__ import annotations

import sqlite3
from typing import Optional


def parse_karma_folder_id(
    folder_id: str,
    known_names: set[str] | None = None,
) -> Optional[tuple[str, str]]:
    """Parse ``karma-out-{username}-{suffix}`` into ``(username, suffix)``.

    Parameters
    ----------
    folder_id:
        The full Syncthing folder ID, e.g.
        ``"karma-out-my-mac-mini-jayantdevkar-claude-code-karma"``.
    known_names:
        Optional set of known usernames / member IDs.  When provided,
        all possible splits are tried and the *longest* known name that
        matches is returned (greedy match).  This resolves the hyphen
        ambiguity reliably.

    Returns
    -------
    ``(username, suffix)`` on success, ``None`` if the folder ID does
    not start with ``karma-out-`` or cannot be split into two non-empty
    parts.

    Notes
    -----
    When *known_names* is ``None`` (or empty), the function falls back
    to the shortest-username-first split — the first ``i`` where both
    parts are non-empty.  This is unreliable for hyphenated usernames
    but matches the legacy behaviour.  Callers that need accuracy
    should always supply *known_names*.
    """
    prefix = "karma-out-"
    if not folder_id.startswith(prefix):
        return None
    rest = folder_id[len(prefix):]

    # ── With hints: try known names, longest first ──────────────────
    if known_names:
        for name in sorted(known_names, key=len, reverse=True):
            if rest.startswith(name + "-"):
                remainder = rest[len(name) + 1:]
                if remainder:
                    return name, remainder

    # ── Fallback: shortest-username-first ───────────────────────────
    parts = rest.split("-")
    if len(parts) < 2:
        return None
    for i in range(1, len(parts)):
        candidate_name = "-".join(parts[:i])
        candidate_suffix = "-".join(parts[i:])
        if candidate_name and candidate_suffix:
            return candidate_name, candidate_suffix
    return None


def parse_karma_handshake_id(
    folder_id: str,
    known_teams: set[str] | None = None,
) -> Optional[tuple[str, str]]:
    """Parse ``karma-join-{username}-{team}`` into ``(username, team_name)``.

    Parameters
    ----------
    folder_id:
        The full Syncthing folder ID, e.g.
        ``"karma-join-alice-my-cool-team"``.
    known_teams:
        Optional set of known team names.  When provided, all possible
        splits are tried (longest team name first) and the one matching
        a known team is returned.

    Returns
    -------
    ``(username, team_name)`` on success, ``None`` if the folder ID
    does not start with ``karma-join-`` or cannot be split.
    """
    prefix = "karma-join-"
    if not folder_id.startswith(prefix):
        return None
    rest = folder_id[len(prefix):]
    parts = rest.split("-")
    if len(parts) < 2:
        return None

    # ── With hints: match known team names ──────────────────────────
    if known_teams:
        # Try longest team name first (scan from right)
        for i in range(1, len(parts)):
            candidate_name = "-".join(parts[:i])
            candidate_team = "-".join(parts[i:])
            if candidate_name and candidate_team and candidate_team in known_teams:
                return candidate_name, candidate_team

    # ── Fallback: shortest-username-first ───────────────────────────
    for i in range(1, len(parts)):
        candidate_name = "-".join(parts[:i])
        candidate_team = "-".join(parts[i:])
        if candidate_name and candidate_team:
            return candidate_name, candidate_team
    return None


# ── DB convenience helpers ──────────────────────────────────────────
# These avoid coupling the pure parsing functions to the database, but
# let API callers that already have a ``conn`` do a one-liner.


def known_names_from_db(conn: sqlite3.Connection) -> set[str]:
    """Build a set of known member names from the sync_members table.

    This is the canonical way to obtain the *known_names* argument for
    :func:`parse_karma_folder_id` when a DB connection is available.
    """
    from db.sync_queries import get_known_devices

    known_devices = get_known_devices(conn)
    return {name for name, _team in known_devices.values()}


def known_teams_from_db(conn: sqlite3.Connection) -> set[str]:
    """Build a set of known team names from the sync_teams table.

    This is the canonical way to obtain the *known_teams* argument for
    :func:`parse_karma_handshake_id` when a DB connection is available.
    """
    from db.sync_queries import list_teams

    return {t["name"] for t in list_teams(conn)}
