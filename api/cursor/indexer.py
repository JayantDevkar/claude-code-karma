"""
Cursor → metadata.db indexer.

Runs alongside the existing Claude Code indexer (`api/db/indexer.py`).
Writes to the same SQLite database but to source-discriminated rows:
- `sessions.session_source = 'cursor'`
- `session_tools.invocation_source = 'cursor'`

Full scan: walk every composer in every workspace, upsert.
Incremental scan: only re-process composers whose `lastUpdatedAt` advanced
since their `cursor_session_meta.indexed_at` stamp.
"""

import json
import logging
import sqlite3
import threading
import time
from datetime import datetime, timezone

from cursor.bubble import extract_bubble_row, iter_bubbles_for_composer
from cursor.composer import (
    extract_meta,
    get_bubble_headers,
    get_created_at_ms,
    get_last_updated_at_ms,
    iter_all_composer_ids,
    read_composer,
)
from cursor.mcp import iter_mcp_descriptors_for_workspace
from cursor.paths import cursor_global_db_path, detect_cursor_install
from cursor.plans import iter_plans
from cursor.state_db import open_state_db_readonly
from cursor.tools import extract_tool_call_row
from cursor.workspace import (
    CursorWorkspace,
    iter_workspaces,
    list_composer_ids_for_workspace,
)

logger = logging.getLogger(__name__)

_cursor_indexing_lock = threading.Lock()
_cursor_ready = threading.Event()


def is_cursor_index_ready() -> bool:
    return _cursor_ready.is_set()


def run_cursor_full_index(writer_conn: sqlite3.Connection) -> dict:
    """
    Materialize every Cursor composer into metadata.db.

    Safe to run on every startup. Idempotent — re-runs upsert in place.
    Returns sync stats.
    """
    if not detect_cursor_install():
        logger.info("Cursor not detected; skipping indexer")
        _cursor_ready.set()
        return {"status": "cursor_not_installed"}

    if not _cursor_indexing_lock.acquire(blocking=False):
        logger.info("Cursor index already running; skipping")
        return {"status": "already_running"}

    start = time.time()
    stats = {
        "workspaces": 0,
        "composers_total": 0,
        "composers_indexed": 0,
        "composers_skipped": 0,
        "bubbles_written": 0,
        "tool_calls_written": 0,
        "plans_written": 0,
        "mcp_servers_written": 0,
        "mcp_tools_written": 0,
        "errors": 0,
    }

    try:
        global_db_path = cursor_global_db_path()
        try:
            cursor_conn = open_state_db_readonly(global_db_path)
        except (FileNotFoundError, sqlite3.Error) as e:
            logger.warning("Cannot open Cursor global DB: %s", e)
            _cursor_ready.set()
            return {"status": "cursor_db_unreadable", "error": str(e)}

        try:
            # Step 1: Index workspaces and their composers
            for workspace in iter_workspaces():
                stats["workspaces"] += 1
                try:
                    _index_workspace(writer_conn, cursor_conn, workspace, stats)
                except Exception as e:
                    logger.warning(
                        "Error indexing Cursor workspace %s: %s",
                        workspace.workspace_hash,
                        e,
                    )
                    stats["errors"] += 1

            # Step 2: Index plans (independent of workspaces)
            try:
                stats["plans_written"] = _index_plans(writer_conn)
            except Exception as e:
                logger.warning("Cursor plan indexing failed: %s", e)
                stats["errors"] += 1

            writer_conn.commit()

            # Step 3: Update projects summary so Cursor workspaces appear in /projects
            try:
                _update_cursor_projects(writer_conn)
                writer_conn.commit()
            except Exception as e:
                logger.warning("Cursor projects summary update failed: %s", e)
                stats["errors"] += 1

        finally:
            cursor_conn.close()

        stats["elapsed"] = round(time.time() - start, 2)
        logger.info(
            "Cursor index complete: %d composers (%d new), %d bubbles, %d tools, "
            "%d plans, %d MCP servers, %d MCP tools in %.2fs",
            stats["composers_total"],
            stats["composers_indexed"],
            stats["bubbles_written"],
            stats["tool_calls_written"],
            stats["plans_written"],
            stats["mcp_servers_written"],
            stats["mcp_tools_written"],
            stats["elapsed"],
        )
        _cursor_ready.set()
        return stats
    finally:
        _cursor_indexing_lock.release()


def _index_workspace(
    writer_conn: sqlite3.Connection,
    cursor_conn: sqlite3.Connection,
    workspace: CursorWorkspace,
    stats: dict,
) -> None:
    """Index every composer that belongs to one Cursor workspace."""
    composer_ids = list_composer_ids_for_workspace(workspace.workspace_hash)
    if not composer_ids:
        return

    # Bulk-fetch known indexed_at timestamps to short-circuit unchanged composers
    placeholders = ",".join("?" * len(composer_ids))
    indexed_at_map = {
        row[0]: row[1]
        for row in writer_conn.execute(
            f"SELECT session_uuid, indexed_at FROM cursor_session_meta "
            f"WHERE session_uuid IN ({placeholders})",
            composer_ids,
        ).fetchall()
    }

    for composer_id in composer_ids:
        stats["composers_total"] += 1
        try:
            composer = read_composer(cursor_conn, composer_id)
            if composer is None:
                continue
            last_updated = get_last_updated_at_ms(composer) or 0
            prior_indexed = indexed_at_map.get(composer_id, 0) or 0
            if last_updated and prior_indexed and last_updated <= prior_indexed:
                stats["composers_skipped"] += 1
                continue

            _index_composer(
                writer_conn=writer_conn,
                cursor_conn=cursor_conn,
                workspace=workspace,
                composer_id=composer_id,
                composer=composer,
                stats=stats,
            )
            stats["composers_indexed"] += 1
        except Exception as e:
            logger.debug(
                "Skipping composer %s in workspace %s: %s",
                composer_id,
                workspace.workspace_hash,
                e,
            )
            stats["errors"] += 1

    # MCP descriptors for this workspace (one-shot per scan)
    try:
        mcp_servers, mcp_tools = iter_mcp_descriptors_for_workspace(
            workspace.workspace_hash, workspace.real_path
        )
        if mcp_servers:
            _write_mcp_servers(writer_conn, mcp_servers)
            stats["mcp_servers_written"] += len(mcp_servers)
        if mcp_tools:
            _write_mcp_tools(writer_conn, mcp_tools)
            stats["mcp_tools_written"] += len(mcp_tools)
    except Exception as e:
        logger.debug("MCP scan failed for workspace %s: %s", workspace.workspace_hash, e)


def _index_composer(
    writer_conn: sqlite3.Connection,
    cursor_conn: sqlite3.Connection,
    workspace: CursorWorkspace,
    composer_id: str,
    composer: dict,
    stats: dict,
) -> None:
    """Write a single composer + its bubbles + its tool calls + its tool counts."""
    meta = extract_meta(composer_id, composer)
    now_ms = int(time.time() * 1000)
    meta["indexed_at"] = now_ms

    created_at = get_created_at_ms(composer)
    last_updated = get_last_updated_at_ms(composer)

    # Walk bubbles FIRST so we know real counts before writing the session row
    headers = get_bubble_headers(composer)
    sub_composers = composer.get("subComposerIds") or []
    subagent_composers = composer.get("subagentComposerIds") or []
    subagent_count = len(sub_composers) + len(subagent_composers)

    bubble_rows: list[dict] = []
    tool_call_rows: list[dict] = []
    tool_counts: dict[str, int] = {}
    initial_prompt: str | None = None

    for seq, header, bubble in iter_bubbles_for_composer(cursor_conn, composer_id, headers):
        row = extract_bubble_row(composer_id, seq, header, bubble)
        bubble_rows.append(row)
        # Capture the first user bubble's text as the initial prompt
        if initial_prompt is None and row["bubble_type"] == 1 and row["text_full"]:
            initial_prompt = row["text_full"][:500]
        if row["has_tool_call"]:
            call = extract_tool_call_row(composer_id, row["bubble_id"], bubble)
            if call:
                tool_call_rows.append(call)
                tool_counts[call["tool_name"]] = tool_counts.get(call["tool_name"], 0) + 1

    # Write the session row with real counts
    _write_session_row(
        writer_conn,
        composer_id=composer_id,
        workspace=workspace,
        meta=meta,
        created_at_ms=created_at,
        last_updated_at_ms=last_updated,
        message_count=len(bubble_rows),
        subagent_count=subagent_count,
        initial_prompt=initial_prompt,
    )

    _write_session_meta(writer_conn, meta)

    # Replace bubble + tool call rows wholesale for this composer
    writer_conn.execute(
        "DELETE FROM cursor_bubble WHERE session_uuid = ?", (composer_id,)
    )
    writer_conn.execute(
        "DELETE FROM cursor_tool_call WHERE session_uuid = ?", (composer_id,)
    )
    writer_conn.execute(
        "DELETE FROM session_tools WHERE session_uuid = ? AND invocation_source = 'cursor'",
        (composer_id,),
    )

    for row in bubble_rows:
        _write_bubble_row(writer_conn, row)
        stats["bubbles_written"] += 1
    for call in tool_call_rows:
        _write_tool_call_row(writer_conn, call)
        stats["tool_calls_written"] += 1
    for tool_name, count in tool_counts.items():
        writer_conn.execute(
            "INSERT OR REPLACE INTO session_tools "
            "(session_uuid, tool_name, invocation_source, count) "
            "VALUES (?, ?, 'cursor', ?)",
            (composer_id, tool_name, count),
        )


def _write_session_row(
    writer_conn: sqlite3.Connection,
    composer_id: str,
    workspace: CursorWorkspace,
    meta: dict,
    created_at_ms: int | None,
    last_updated_at_ms: int | None,
    message_count: int,
    subagent_count: int,
    initial_prompt: str | None,
) -> None:
    """Write to the canonical `sessions` table with session_source='cursor'."""
    encoded_name = f"cursor:{workspace.workspace_hash}"
    start_iso = _ms_to_iso(created_at_ms)
    end_iso = _ms_to_iso(last_updated_at_ms)
    duration = None
    if created_at_ms and last_updated_at_ms and last_updated_at_ms > created_at_ms:
        duration = (last_updated_at_ms - created_at_ms) / 1000.0
    models_used = json.dumps([meta["model_name"]]) if meta["model_name"] else None
    session_titles = json.dumps([meta["name"]]) if meta["name"] else None
    mtime = (last_updated_at_ms or created_at_ms or 0) / 1000.0

    writer_conn.execute(
        """
        INSERT OR REPLACE INTO sessions (
            uuid, slug, project_encoded_name, project_path,
            start_time, end_time, message_count, duration_seconds,
            input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens,
            total_cost, initial_prompt, git_branch, models_used,
            session_titles, is_continuation_marker, was_compacted,
            compaction_count, file_snapshot_count, subagent_count,
            jsonl_mtime, jsonl_size, session_source, source_encoded_name,
            cursor_workspace_hash, indexed_at
        ) VALUES (
            ?, NULL, ?, ?,
            ?, ?, ?, ?,
            ?, 0, 0, 0,
            0, ?, ?, ?,
            ?, 0, 0,
            0, 0, ?,
            ?, 0, 'cursor', NULL,
            ?, datetime('now')
        )
        """,
        (
            composer_id,
            encoded_name,
            workspace.real_path,
            start_iso,
            end_iso,
            message_count,
            duration,
            meta.get("context_tokens_used") or 0,
            initial_prompt,
            meta.get("created_on_branch"),
            models_used,
            session_titles,
            subagent_count,
            mtime,
            workspace.workspace_hash,
        ),
    )


def _write_session_meta(writer_conn: sqlite3.Connection, meta: dict) -> None:
    writer_conn.execute(
        """
        INSERT OR REPLACE INTO cursor_session_meta (
            session_uuid, unified_mode, force_mode, agent_backend, model_name,
            context_usage_percent, context_tokens_used, context_token_limit,
            is_agentic, is_archived, is_draft,
            parent_composer_id, created_on_branch,
            referenced_plans_json, todos_json, sub_composer_ids_json,
            name, subtitle, status,
            total_lines_added, total_lines_removed, files_changed_count,
            indexed_at
        ) VALUES (
            :session_uuid, :unified_mode, :force_mode, :agent_backend, :model_name,
            :context_usage_percent, :context_tokens_used, :context_token_limit,
            :is_agentic, :is_archived, :is_draft,
            :parent_composer_id, :created_on_branch,
            :referenced_plans_json, :todos_json, :sub_composer_ids_json,
            :name, :subtitle, :status,
            :total_lines_added, :total_lines_removed, :files_changed_count,
            :indexed_at
        )
        """,
        meta,
    )


def _write_bubble_row(writer_conn: sqlite3.Connection, row: dict) -> None:
    writer_conn.execute(
        """
        INSERT OR REPLACE INTO cursor_bubble (
            session_uuid, bubble_id, seq, bubble_type, capability_type,
            created_at_ms, has_thinking, thinking_duration_ms, has_tool_call,
            text_preview, text_full, raw_json
        ) VALUES (
            :session_uuid, :bubble_id, :seq, :bubble_type, :capability_type,
            :created_at_ms, :has_thinking, :thinking_duration_ms, :has_tool_call,
            :text_preview, :text_full, :raw_json
        )
        """,
        row,
    )


def _write_tool_call_row(writer_conn: sqlite3.Connection, row: dict) -> None:
    writer_conn.execute(
        """
        INSERT OR REPLACE INTO cursor_tool_call (
            session_uuid, bubble_id, tool_call_id, tool_name, tool_int, status,
            args_json, result_text, file_path, created_at_ms
        ) VALUES (
            :session_uuid, :bubble_id, :tool_call_id, :tool_name, :tool_int, :status,
            :args_json, :result_text, :file_path, :created_at_ms
        )
        """,
        row,
    )


def _index_plans(writer_conn: sqlite3.Connection) -> int:
    """Refresh cursor_plan from ~/.cursor/plans/. Returns count written."""
    count = 0
    seen: set[str] = set()
    now_ms = int(time.time() * 1000)
    for plan in iter_plans():
        seen.add(plan.slug)
        writer_conn.execute(
            """
            INSERT OR REPLACE INTO cursor_plan (
                slug, plan_id, name, overview, todos_json, body_md,
                file_path, file_mtime_ms, indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                plan.slug,
                plan.plan_id,
                plan.name,
                plan.overview,
                plan.todos_json,
                plan.body_md,
                plan.file_path,
                plan.file_mtime_ms,
                now_ms,
            ),
        )
        count += 1
    # Remove plans whose source file disappeared
    if seen:
        placeholders = ",".join("?" * len(seen))
        writer_conn.execute(
            f"DELETE FROM cursor_plan WHERE slug NOT IN ({placeholders})",
            list(seen),
        )
    else:
        writer_conn.execute("DELETE FROM cursor_plan")
    return count


def _write_mcp_servers(writer_conn: sqlite3.Connection, servers: list) -> None:
    now_ms = int(time.time() * 1000)
    for s in servers:
        writer_conn.execute(
            """
            INSERT OR REPLACE INTO cursor_mcp_server (
                server_identifier, workspace_hash, server_name, source,
                file_path, indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                s.server_identifier,
                s.workspace_hash,
                s.server_name,
                s.source,
                s.file_path,
                now_ms,
            ),
        )


def _write_mcp_tools(writer_conn: sqlite3.Connection, tools: list) -> None:
    now_ms = int(time.time() * 1000)
    for t in tools:
        writer_conn.execute(
            """
            INSERT OR REPLACE INTO cursor_mcp_tool (
                server_identifier, workspace_hash, tool_name,
                description, arguments_json, file_path, indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                t.server_identifier,
                t.workspace_hash,
                t.tool_name,
                t.description,
                t.arguments_json,
                t.file_path,
                now_ms,
            ),
        )


def _update_cursor_projects(writer_conn: sqlite3.Connection) -> None:
    """Roll up Cursor sessions into the `projects` table for /projects listing."""
    from pathlib import Path

    rows = writer_conn.execute(
        """
        SELECT
            project_encoded_name,
            project_path,
            COUNT(*) AS session_count,
            MAX(start_time) AS last_activity
        FROM sessions
        WHERE session_source = 'cursor'
        GROUP BY project_encoded_name
        """
    ).fetchall()
    for row in rows:
        encoded_name = row[0]
        project_path = row[1]
        session_count = row[2]
        last_activity = row[3]
        display_name = Path(project_path).name if project_path else encoded_name
        # Cursor projects use the cursor: prefix as both encoded_name and slug
        # (their workspace hash is unique enough; no need for the md5 slug scheme).
        slug = encoded_name
        writer_conn.execute(
            """
            INSERT OR REPLACE INTO projects (
                encoded_name, project_path, slug, display_name,
                session_count, last_activity
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (encoded_name, project_path, slug, display_name, session_count, last_activity),
        )


def _ms_to_iso(ms: int | None) -> str | None:
    if ms is None or ms <= 0:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()
    except (ValueError, OverflowError, OSError):
        return None
