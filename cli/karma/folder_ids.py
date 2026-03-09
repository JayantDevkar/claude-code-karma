"""Shared folder ID parsing utilities for karma Syncthing folder IDs.

Karma uses two folder ID schemes:

- ``karma-out-{user_id}-{proj_suffix}``  — session outbox/inbox folders
- ``karma-join-{user_id}-{team_name}``   — lightweight handshake folders

Because both *user_id* and the trailing component can contain hyphens, all
parsers implement an ambiguity-resolution strategy (shortest-first or
longest-known-name-first).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

# ── Folder ID prefixes ─────────────────────────────────────────────────────
OUTBOX_PREFIX = "karma-out-"
HANDSHAKE_PREFIX = "karma-join-"


def parse_folder_id(folder_id: str) -> Optional[tuple[str, str]]:
    """Parse a karma outbox folder ID into (member_name, suffix).

    Expected format: ``karma-out-{member_name}-{suffix}``
    where *suffix* may itself contain hyphens.

    Returns ``None`` if the folder ID does not match the expected pattern.

    Because both member_name and suffix can contain hyphens, this uses a
    shortest-member-name heuristic (first non-empty split).  For accurate
    splitting when usernames are known, use :func:`parse_folder_id_with_hints`.
    """
    if not folder_id.startswith(OUTBOX_PREFIX):
        return None
    rest = folder_id[len(OUTBOX_PREFIX):]  # "alice-acme-app"
    parts = rest.split("-")
    if len(parts) < 2:
        return None
    # Try progressively longer prefixes as the member name.
    # The first non-empty remainder wins (shortest member name).
    for i in range(1, len(parts)):
        candidate_name = "-".join(parts[:i])
        candidate_suffix = "-".join(parts[i:])
        if candidate_name and candidate_suffix:
            return candidate_name, candidate_suffix
    return None


def parse_folder_id_with_hints(
    folder_id: str, known_user_ids: set[str]
) -> Optional[tuple[str, str]]:
    """Parse a karma outbox folder ID using known user IDs for accurate splitting.

    The ambiguity in ``karma-out-{user}-{suffix}`` is that both user and
    suffix can contain hyphens.  By checking against known user IDs, we can
    split correctly.

    Falls back to :func:`parse_folder_id` if no known user matches.
    """
    if not folder_id.startswith(OUTBOX_PREFIX):
        return None
    rest = folder_id[len(OUTBOX_PREFIX):]

    # Try known user IDs (longest first to match most specific)
    for uid in sorted(known_user_ids, key=len, reverse=True):
        if rest.startswith(uid + "-"):
            suffix = rest[len(uid) + 1:]
            if suffix:
                return uid, suffix

    # Fallback to greedy parse
    return parse_folder_id(folder_id)


def extract_username_from_karma_folder(
    folder_id: str, prefix: str, known_names: set[str]
) -> Optional[tuple[str, str]]:
    """Extract (username, remainder) from a karma folder ID.

    Uses ``known_names`` (own user_id + real usernames discovered from
    handshake folders) to correctly disambiguate multi-dash usernames.
    Falls back to shortest-split when no known name matches.
    """
    rest = folder_id[len(prefix):]
    # Try known names longest-first for greedy match
    for name in sorted(known_names, key=len, reverse=True):
        if rest.startswith(name + "-"):
            remainder = rest[len(name) + 1:]
            if remainder:
                return name, remainder
    # Fallback: shortest split
    parts = rest.split("-", 1)
    if len(parts) == 2 and parts[0] and parts[1]:
        return parts[0], parts[1]
    return None


def parse_handshake_folder(folder_id: str) -> Optional[tuple[str, str]]:
    """Parse a karma-join handshake folder ID into (username, team_name).

    Expected format: ``karma-join-{username}-{team_name}``
    Returns ``None`` if the folder ID does not match.
    """
    if not folder_id.startswith(HANDSHAKE_PREFIX):
        return None
    rest = folder_id[len(HANDSHAKE_PREFIX):]
    parts = rest.split("-")
    if len(parts) < 2:
        return None
    # Same ambiguity as parse_folder_id — try shortest username first
    for i in range(1, len(parts)):
        candidate_name = "-".join(parts[:i])
        candidate_team = "-".join(parts[i:])
        if candidate_name and candidate_team:
            return candidate_name, candidate_team
    return None


def compute_proj_suffix(
    git_identity: Optional[str], path: Optional[str], encoded: str
) -> str:
    """Compute the project suffix used in Syncthing folder IDs.

    Priority:
    1. ``git_identity`` (e.g. ``jayantdevkar/my-repo``) with ``/`` → ``-``
    2. Last component of ``path`` (e.g. ``my-repo`` from ``/Users/me/my-repo``)
    3. ``encoded`` project name as fallback
    """
    if git_identity:
        return git_identity.replace("/", "-")
    return Path(path).name if path else encoded
