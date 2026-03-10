"""Karma folder ID parsing utilities.

Shared by both the API (``api/routers/sync_status.py``) and the CLI
(``cli/karma/pending.py``).  All folder-ID logic lives here so there
is exactly one implementation to maintain.

Folder ID formats (double-dash delimited)
------------------------------------------
- ``karma-out--{username}--{suffix}``  — session outbox/inbox
- ``karma-join--{username}--{team}``   — team handshake signal

The double-dash ``--`` delimiter is unambiguous: usernames and suffixes
may contain single hyphens but never ``--``.  Parsing is a simple
``split("--")`` with a length check — no DB disambiguation needed.
"""

from __future__ import annotations

from typing import Optional


KARMA_PREFIX = "karma-"
OUTBOX_PREFIX = "karma-out--"
HANDSHAKE_PREFIX = "karma-join--"


def _validate_no_double_dash(value: str, label: str) -> None:
    """Raise ValueError if value contains the ``--`` delimiter."""
    if "--" in value:
        raise ValueError(f"{label} must not contain '--': {value!r}")
    if not value:
        raise ValueError(f"{label} must not be empty")


def build_outbox_id(username: str, suffix: str) -> str:
    """Build ``karma-out--{username}--{suffix}``."""
    _validate_no_double_dash(username, "username")
    _validate_no_double_dash(suffix, "suffix")
    return f"{OUTBOX_PREFIX}{username}--{suffix}"


def build_handshake_id(username: str, team_name: str) -> str:
    """Build ``karma-join--{username}--{team_name}``."""
    _validate_no_double_dash(username, "username")
    _validate_no_double_dash(team_name, "team_name")
    return f"{HANDSHAKE_PREFIX}{username}--{team_name}"


def parse_outbox_id(folder_id: str) -> Optional[tuple[str, str]]:
    """Parse ``karma-out--{username}--{suffix}`` into ``(username, suffix)``.

    Returns ``None`` if the folder ID does not match the expected format.
    """
    if not folder_id.startswith(OUTBOX_PREFIX):
        return None
    rest = folder_id[len(OUTBOX_PREFIX):]
    parts = rest.split("--")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return parts[0], parts[1]


def parse_handshake_id(folder_id: str) -> Optional[tuple[str, str]]:
    """Parse ``karma-join--{username}--{team_name}`` into ``(username, team_name)``.

    Returns ``None`` if the folder ID does not match the expected format.
    """
    if not folder_id.startswith(HANDSHAKE_PREFIX):
        return None
    rest = folder_id[len(HANDSHAKE_PREFIX):]
    parts = rest.split("--")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        return None
    return parts[0], parts[1]


def is_karma_folder(folder_id: str) -> bool:
    """Check if a folder ID belongs to karma (any ``karma-`` prefix)."""
    return folder_id.startswith(KARMA_PREFIX)


def is_outbox_folder(folder_id: str) -> bool:
    """Check if a folder ID is an outbox/inbox folder."""
    return folder_id.startswith(OUTBOX_PREFIX)


def is_handshake_folder(folder_id: str) -> bool:
    """Check if a folder ID is a handshake folder."""
    return folder_id.startswith(HANDSHAKE_PREFIX)
