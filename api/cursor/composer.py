"""
Parse Cursor `composerData:<id>` blobs from the master cursorDiskKV store.

A composer is Cursor's term for a single chat/agent conversation. This
module exposes one function — `read_composer(conn, composer_id)` — that
returns a normalized dict ready for DB insertion. Missing or malformed
fields default to None / [] / 0 to keep callers simple.
"""

import json
import logging
import sqlite3
from typing import Iterator

from cursor.state_db import iter_kv_keys, read_kv_value

logger = logging.getLogger(__name__)


def iter_all_composer_ids(conn: sqlite3.Connection) -> Iterator[str]:
    """Yield every composerId that has a `composerData:<id>` row in the global DB."""
    prefix = "composerData:"
    for key in iter_kv_keys(conn, prefix):
        yield key[len(prefix):]


def read_composer(conn: sqlite3.Connection, composer_id: str) -> dict | None:
    """
    Return the parsed composerData JSON or None if missing/malformed.

    Lenient — unknown fields are preserved; missing required fields are
    backfilled with safe defaults so the indexer doesn't crash on edge cases.
    """
    raw = read_kv_value(conn, f"composerData:{composer_id}")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.warning("Malformed composerData:%s skipped: %s", composer_id, e)
        return None


def extract_meta(composer_id: str, composer: dict) -> dict:
    """
    Pull the fields we materialize into the cursor_session_meta table.

    All keys map directly to columns. Missing fields → None/0.
    """
    model_config = composer.get("modelConfig") or {}
    return {
        "session_uuid": composer_id,
        "unified_mode": composer.get("unifiedMode"),
        "force_mode": composer.get("forceMode"),
        "agent_backend": composer.get("agentBackend") or None,
        "model_name": model_config.get("modelName") if isinstance(model_config, dict) else None,
        "context_usage_percent": composer.get("contextUsagePercent"),
        "context_tokens_used": composer.get("contextTokensUsed"),
        "context_token_limit": composer.get("contextTokenLimit"),
        "is_agentic": 1 if composer.get("isAgentic") else 0,
        "is_archived": 1 if composer.get("isArchived") else 0,
        "is_draft": 1 if composer.get("isDraft") else 0,
        "parent_composer_id": _detect_parent_composer(composer),
        "created_on_branch": composer.get("createdOnBranch") or None,
        "referenced_plans_json": _json_or_none(composer.get("referencedPlans")),
        "todos_json": _json_or_none(composer.get("todos")),
        "sub_composer_ids_json": _json_or_none(
            (composer.get("subComposerIds") or [])
            + (composer.get("subagentComposerIds") or [])
        ),
        "name": composer.get("name") or None,
        "subtitle": composer.get("subtitle") or None,
        "status": composer.get("status") or None,
        "total_lines_added": int(composer.get("totalLinesAdded") or 0),
        "total_lines_removed": int(composer.get("totalLinesRemoved") or 0),
        "files_changed_count": int(composer.get("filesChangedCount") or 0),
    }


def get_bubble_headers(composer: dict) -> list[dict]:
    """Return the ordered list of (bubbleId, type) entries — authoritative order."""
    return composer.get("fullConversationHeadersOnly") or []


def get_created_at_ms(composer: dict) -> int | None:
    """createdAt is unix milliseconds in Cursor's schema."""
    val = composer.get("createdAt")
    if isinstance(val, (int, float)):
        return int(val)
    return None


def get_last_updated_at_ms(composer: dict) -> int | None:
    val = composer.get("lastUpdatedAt")
    if isinstance(val, (int, float)):
        return int(val)
    return None


def _detect_parent_composer(composer: dict) -> str | None:
    """A sub-composer can identify its parent via isBestOfNSubcomposer + lineage."""
    # No explicit parent field; parent linkage is via the parent's subComposerIds
    # array. We resolve this at indexer time by walking the parent list, so this
    # function just preserves the explicit fields if any future Cursor version
    # adds them. For now, return None.
    return composer.get("parentComposerId")


def _json_or_none(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        if not value:
            return None
        try:
            return json.dumps(value)
        except (TypeError, ValueError):
            return None
    return None
