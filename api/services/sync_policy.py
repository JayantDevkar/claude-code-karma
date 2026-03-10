"""Centralized sync policy evaluation.

All sync permission checks go through this module. Decision points in
sync_status.py, pending.py, and the packager call these helpers instead
of making inline policy decisions.
"""

import sqlite3
from typing import Optional

from db.sync_queries import (
    get_effective_auto_accept,
    get_effective_sync_direction,
)


def _can_direction(direction: str, action: str) -> bool:
    """Check if a direction setting allows an action.

    Args:
        direction: One of 'both', 'send_only', 'receive_only', 'none'.
        action: Either 'send' or 'receive'.
    """
    if direction == "both":
        return True
    if direction == "none":
        return False
    if direction == "send_only":
        return action == "send"
    if direction == "receive_only":
        return action == "receive"
    return True  # unknown → permissive default


def should_auto_accept_device(conn: sqlite3.Connection, team_name: str) -> bool:
    """Should pending devices be auto-accepted for this team?"""
    return get_effective_auto_accept(conn, team_name)


def should_send_to(
    conn: sqlite3.Connection,
    team_name: str,
    device_id: Optional[str] = None,
) -> bool:
    """Should we send sessions to this team/member?"""
    direction = get_effective_sync_direction(
        conn, team_name=team_name, device_id=device_id
    )
    return _can_direction(direction, "send")


def should_receive_from(
    conn: sqlite3.Connection,
    team_name: str,
    device_id: Optional[str] = None,
) -> bool:
    """Should we receive sessions from this team/member?"""
    direction = get_effective_sync_direction(
        conn, team_name=team_name, device_id=device_id
    )
    return _can_direction(direction, "receive")
