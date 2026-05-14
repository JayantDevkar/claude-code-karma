"""
Parse Cursor `bubbleId:<composer>:<bubble>` blobs — the per-message records.

Each composer has N bubbles, ordered by `composer.fullConversationHeadersOnly`.
A bubble is either a user message (type=1), an assistant message (type=2),
a tool call (type=2, capability_type=15), or a thinking block (type=2,
capability_type=30).

Critical correction validated by POC: tool call data lives at
`bubble.toolFormerData` (top-level), NOT nested in `bubble.capabilities[]`.
"""

import json
import logging
import sqlite3
from typing import Iterator

from cursor.state_db import read_kv_value

logger = logging.getLogger(__name__)

# Bubble type constants
BUBBLE_TYPE_USER = 1
BUBBLE_TYPE_ASSISTANT = 2

# Capability type discriminators on assistant bubbles
CAPABILITY_TOOL_CALL = 15
CAPABILITY_THINKING = 30

# How much text to preview in indexed bubble rows. Full text stays in text_full.
TEXT_PREVIEW_CHARS = 200


def read_bubble(
    conn: sqlite3.Connection, composer_id: str, bubble_id: str
) -> dict | None:
    """Return the parsed bubble JSON or None if missing/malformed."""
    raw = read_kv_value(conn, f"bubbleId:{composer_id}:{bubble_id}")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.debug(
            "Malformed bubbleId:%s:%s skipped: %s", composer_id, bubble_id, e
        )
        return None


def iter_bubbles_for_composer(
    conn: sqlite3.Connection, composer_id: str, headers: list[dict]
) -> Iterator[tuple[int, dict, dict]]:
    """
    Yield `(seq, header, bubble_json)` in the authoritative order from headers.

    Skips bubbles that are listed in headers but missing from cursorDiskKV
    (rare on healthy data; happens on partial Cursor crashes).
    """
    for seq, header in enumerate(headers):
        bubble_id = header.get("bubbleId")
        if not bubble_id:
            continue
        bubble = read_bubble(conn, composer_id, bubble_id)
        if bubble is None:
            continue
        yield seq, header, bubble


def extract_bubble_row(
    composer_id: str, seq: int, header: dict, bubble: dict
) -> dict:
    """Map a parsed bubble dict to a cursor_bubble row."""
    bubble_id = header.get("bubbleId")
    bubble_type = header.get("type") or bubble.get("type") or 0
    capability_type = bubble.get("capabilityType")
    text = bubble.get("text") or ""
    thinking = bubble.get("thinking") or {}
    thinking_text = thinking.get("text") if isinstance(thinking, dict) else None
    has_thinking = 1 if thinking_text else 0
    thinking_duration_ms = (
        bubble.get("thinkingDurationMs") if isinstance(bubble.get("thinkingDurationMs"), int) else None
    )
    tfd = bubble.get("toolFormerData")
    has_tool_call = 1 if tfd else 0

    return {
        "session_uuid": composer_id,
        "bubble_id": bubble_id,
        "seq": seq,
        "bubble_type": bubble_type,
        "capability_type": capability_type,
        "created_at_ms": _parse_created_at(bubble.get("createdAt")),
        "has_thinking": has_thinking,
        "thinking_duration_ms": thinking_duration_ms,
        "has_tool_call": has_tool_call,
        "text_preview": (text[:TEXT_PREVIEW_CHARS] or None) if text else None,
        "text_full": text or None,
        # Strip the bulky toolFormerData.result before storing raw_json — we
        # already capture it in cursor_tool_call. Keeps cursor_bubble lean.
        "raw_json": _compact_raw_json(bubble),
    }


def _parse_created_at(val) -> int | None:
    """
    Cursor stores createdAt on bubbles as an ISO 8601 STRING (e.g., "2026-03-12T..."),
    distinct from composerData.createdAt which is unix ms. Handle both shapes.
    """
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    if isinstance(val, str):
        try:
            from datetime import datetime

            # Normalize Z to +00:00 for fromisoformat compat
            normalized = val.replace("Z", "+00:00")
            dt = datetime.fromisoformat(normalized)
            return int(dt.timestamp() * 1000)
        except (ValueError, TypeError):
            return None
    return None


def _compact_raw_json(bubble: dict) -> str:
    """Strip bulky fields we won't read back from raw_json (saves DB size)."""
    if not isinstance(bubble, dict):
        return ""
    out = dict(bubble)
    tfd = out.get("toolFormerData")
    if isinstance(tfd, dict):
        compact_tfd = {
            k: v for k, v in tfd.items()
            if k not in ("result", "rawArgs", "params", "toolCallBinary")
        }
        out["toolFormerData"] = compact_tfd
    try:
        return json.dumps(out, ensure_ascii=False)
    except (TypeError, ValueError):
        return ""
