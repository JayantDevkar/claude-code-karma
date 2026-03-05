"""
JSONL-to-SQLite indexer.

Walks project directories, detects changed JSONL files via mtime comparison,
and upserts session metadata into SQLite. Reuses Session model's single-pass
_load_metadata() for data extraction.

The indexer is designed to be:
- Incremental: Only re-indexes files whose mtime has changed
- Idempotent: Safe to run multiple times (uses INSERT OR REPLACE)
- Non-blocking: Runs in a background thread on startup
- Resilient: Skips individual session errors without failing the batch
"""

import json
import logging
import sqlite3
import sys
import threading
import time
from pathlib import Path
from typing import Optional

# Ensure api/ is on the import path (needed when called from background thread)
sys.path.insert(0, str(Path(__file__).parent.parent))

logger = logging.getLogger(__name__)

# Module-level state
_ready = threading.Event()
_indexing_lock = threading.Lock()
_last_health: dict = {}
_last_sync_complete: float = 0.0


def is_db_ready() -> bool:
    """Check if the initial index build has completed."""
    return _ready.is_set()


def wait_for_ready(timeout: float = 30.0) -> bool:
    """Wait for the initial index build to complete."""
    return _ready.wait(timeout=timeout)


def get_last_health() -> dict:
    """Get the most recent DB health metrics."""
    return dict(_last_health)


def get_last_sync_time() -> float:
    """Get the timestamp of the last successful sync completion."""
    return _last_sync_complete


def sync_all_projects(conn: sqlite3.Connection) -> dict:
    """
    Sync all project directories into SQLite.

    Walks ~/.claude/projects/, finds all JSONL session files,
    and indexes any that are new or modified since last index.

    Returns:
        Dict with sync statistics: total, indexed, skipped, errors, elapsed
    """
    if not _indexing_lock.acquire(blocking=False):
        logger.info("Indexing already in progress, skipping")
        return {"status": "already_running"}

    try:
        from config import settings

        start = time.time()
        projects_dir = settings.projects_dir

        if not projects_dir.exists():
            logger.warning("Projects directory does not exist: %s", projects_dir)
            _ready.set()
            return {"status": "no_projects_dir"}

        stats = {"total": 0, "indexed": 0, "skipped": 0, "errors": 0}

        from services.desktop_sessions import (
            get_real_project_encoded_name,
            is_worktree_project,
        )

        # Two-pass indexing: normal projects first, then worktrees
        worktree_dirs = []
        real_project_paths = {}

        # First pass: normal projects
        for encoded_dir in projects_dir.iterdir():
            if not encoded_dir.is_dir() or not encoded_dir.name.startswith("-"):
                continue
            if is_worktree_project(encoded_dir.name):
                worktree_dirs.append(encoded_dir)
                continue

            try:
                project_stats = sync_project(conn, encoded_dir)
                stats["total"] += project_stats["total"]
                stats["indexed"] += project_stats["indexed"]
                stats["skipped"] += project_stats["skipped"]
                stats["errors"] += project_stats["errors"]
            except Exception as e:
                logger.warning("Error syncing project %s: %s", encoded_dir.name, e)
                stats["errors"] += 1

            # Collect project_path for worktree remapping
            row = conn.execute(
                "SELECT project_path FROM sessions WHERE project_encoded_name = ? AND project_path IS NOT NULL LIMIT 1",
                (encoded_dir.name,),
            ).fetchone()
            if row:
                real_project_paths[encoded_dir.name] = row[0]

        # Second pass: worktree dirs -> resolve -> index under real project
        for wt_dir in worktree_dirs:
            try:
                session_uuids = [
                    f.stem for f in wt_dir.glob("*.jsonl") if not f.name.startswith("agent-")
                ]
                real_encoded = get_real_project_encoded_name(wt_dir.name, session_uuids)
                if real_encoded:
                    real_path = real_project_paths.get(real_encoded)
                    # Determine session source: CLI worktrees (per-repo .claude/worktrees/
                    # or .worktrees/) don't come from Desktop — let auto-detect handle it
                    from services.desktop_sessions import (
                        _extract_project_prefix_from_worktree,
                    )

                    wt_source = (
                        None  # auto-detect per session
                        if _extract_project_prefix_from_worktree(wt_dir.name)
                        else "desktop"
                    )
                    project_stats = sync_project(
                        conn,
                        wt_dir,
                        encoded_name_override=real_encoded,
                        project_path_override=real_path,
                        session_source=wt_source,
                    )
                else:
                    # Can't resolve — index as standalone (graceful degradation)
                    logger.warning(
                        "Cannot resolve worktree %s to real project, indexing standalone",
                        wt_dir.name,
                    )
                    project_stats = sync_project(conn, wt_dir)
                stats["total"] += project_stats["total"]
                stats["indexed"] += project_stats["indexed"]
                stats["skipped"] += project_stats["skipped"]
                stats["errors"] += project_stats["errors"]
            except Exception as e:
                logger.warning("Error syncing worktree %s: %s", wt_dir.name, e)
                stats["errors"] += 1

        # Third pass: remote sessions from Syncthing sync
        try:
            remote_stats = index_remote_sessions(conn)
            stats["total"] += remote_stats.get("total", 0)
            stats["indexed"] += remote_stats.get("indexed", 0)
            stats["skipped"] += remote_stats.get("skipped", 0)
            stats["errors"] += remote_stats.get("errors", 0)
        except Exception as e:
            logger.warning("Error indexing remote sessions: %s", e)

        # Clean up stale sessions (files deleted from disk)
        _cleanup_stale_sessions(conn, projects_dir)

        # Update project summary table
        _update_project_summaries(conn)

        elapsed = time.time() - start
        stats["elapsed"] = round(elapsed, 2)

        logger.info(
            "Index sync complete: %d total, %d indexed, %d skipped, %d errors in %.2fs",
            stats["total"],
            stats["indexed"],
            stats["skipped"],
            stats["errors"],
            elapsed,
        )

        # Log DB health metrics
        try:
            health = _log_db_health(conn)
            stats["health"] = health
        except Exception as e:
            logger.warning("Health check failed: %s", e)

        # Update last sync timestamp
        global _last_sync_complete
        _last_sync_complete = time.time()

        _ready.set()
        return stats

    finally:
        _indexing_lock.release()


def sync_project(
    conn: sqlite3.Connection,
    project_dir: Path,
    encoded_name_override: Optional[str] = None,
    project_path_override: Optional[str] = None,
    session_source: Optional[str] = None,
) -> dict:
    """
    Sync a single project directory into SQLite.

    Compares JSONL file mtimes against stored values and only re-indexes
    files that have changed.

    Args:
        conn: SQLite connection
        project_dir: Path to project directory (e.g., ~/.claude/projects/-Users-me-repo)
        encoded_name_override: Store sessions under this project name instead of dir name
                              (used for worktree -> real project remapping)
        project_path_override: Use this project path instead of detecting from session data
        session_source: Tag sessions with this source (e.g., "desktop")

    Returns:
        Dict with per-project sync statistics
    """
    encoded_name = encoded_name_override or project_dir.name
    # Track the actual directory for stale session cleanup
    source_encoded_name = project_dir.name if encoded_name_override else None
    stats = {"total": 0, "indexed": 0, "skipped": 0, "errors": 0}

    # Load current mtimes from DB for this project
    rows = conn.execute(
        "SELECT uuid, jsonl_mtime FROM sessions WHERE project_encoded_name = ?",
        (encoded_name,),
    ).fetchall()
    db_mtimes = {row["uuid"]: row["jsonl_mtime"] for row in rows}

    for jsonl_path in project_dir.glob("*.jsonl"):
        # Skip agent files and non-session files
        if jsonl_path.name.startswith("agent-"):
            continue

        uuid = jsonl_path.stem
        stats["total"] += 1

        try:
            file_stat = jsonl_path.stat()
            current_mtime = file_stat.st_mtime
            current_size = file_stat.st_size

            # Skip if mtime hasn't changed
            if uuid in db_mtimes and abs(db_mtimes[uuid] - current_mtime) < 0.001:
                stats["skipped"] += 1
                continue

            # Index this session
            _index_session(
                conn,
                jsonl_path,
                encoded_name,
                current_mtime,
                current_size,
                project_path_override=project_path_override,
                session_source=session_source,
                source_encoded_name=source_encoded_name,
            )
            stats["indexed"] += 1

        except Exception as e:
            logger.debug("Error indexing %s/%s: %s", encoded_name, uuid, e)
            stats["errors"] += 1

    # Commit after each project
    conn.commit()
    return stats


def index_remote_sessions(conn: sqlite3.Connection) -> dict:
    """
    Index remote sessions from Syncthing-synced directories into SQLite.

    Walks ~/.claude_karma/remote-sessions/{user_id}/{encoded_name}/sessions/
    and upserts session rows with source='remote'. Skips local user's outbox.

    Returns:
        Dict with sync statistics: total, indexed, skipped, errors
    """
    from config import settings
    from services.remote_sessions import get_project_mapping

    stats = {"total": 0, "indexed": 0, "skipped": 0, "errors": 0}

    remote_base = settings.karma_base / "remote-sessions"
    if not remote_base.exists():
        return stats

    mapping = get_project_mapping()

    # Load current mtimes for remote sessions
    rows = conn.execute("SELECT uuid, jsonl_mtime FROM sessions WHERE source = 'remote'").fetchall()
    db_mtimes = {row["uuid"]: row["jsonl_mtime"] for row in rows}

    local_user = None
    config_path = settings.karma_base / "sync-config.json"
    if config_path.exists():
        try:
            import json as _json
            local_user = _json.loads(config_path.read_text()).get("user_id")
        except Exception:
            pass

    for user_dir in remote_base.iterdir():
        if not user_dir.is_dir():
            continue
        user_id = user_dir.name

        # Skip local user's outbox
        if user_id == local_user:
            continue

        for encoded_dir in user_dir.iterdir():
            if not encoded_dir.is_dir():
                continue
            encoded_name = encoded_dir.name
            local_encoded = mapping.get((user_id, encoded_name), encoded_name)

            sessions_dir = encoded_dir / "sessions"
            if not sessions_dir.exists():
                continue

            for jsonl_path in sessions_dir.glob("*.jsonl"):
                if jsonl_path.name.startswith("agent-"):
                    continue

                uuid = jsonl_path.stem
                stats["total"] += 1

                try:
                    file_stat = jsonl_path.stat()
                    current_mtime = file_stat.st_mtime
                    current_size = file_stat.st_size

                    if uuid in db_mtimes and abs(db_mtimes[uuid] - current_mtime) < 0.001:
                        stats["skipped"] += 1
                        continue

                    _index_session(
                        conn,
                        jsonl_path,
                        local_encoded,
                        current_mtime,
                        current_size,
                        source="remote",
                        remote_user_id=user_id,
                        remote_machine_id=user_id,
                    )
                    stats["indexed"] += 1
                except Exception as e:
                    logger.debug("Error indexing remote session %s: %s", uuid, e)
                    stats["errors"] += 1

    conn.commit()
    return stats


def _index_session(
    conn: sqlite3.Connection,
    jsonl_path: Path,
    encoded_name: str,
    mtime: float,
    size: int,
    project_path_override: Optional[str] = None,
    session_source: Optional[str] = None,
    source_encoded_name: Optional[str] = None,
    source: Optional[str] = None,
    remote_user_id: Optional[str] = None,
    remote_machine_id: Optional[str] = None,
) -> None:
    """
    Extract metadata from a session JSONL and upsert into SQLite.

    Uses the Session model's _load_metadata() for single-pass extraction,
    then writes the computed values to the sessions table.

    Args:
        project_path_override: Use this path instead of detecting from session data
        session_source: Tag session with this source (e.g., "desktop")
        source_encoded_name: The actual directory name where the JSONL lives
                            (differs from encoded_name for remapped worktree sessions)
        source: Session source type ("local" or "remote")
        remote_user_id: User ID of remote machine (for remote sessions)
        remote_machine_id: Machine ID of remote machine (for remote sessions)
    """
    from models import Session
    from utils import get_initial_prompt

    uuid = jsonl_path.stem

    # Parse session (triggers _load_metadata via property access)
    session = Session.from_path(jsonl_path)

    # Skip empty sessions
    if session.message_count == 0:
        # Remove from DB if it was previously indexed
        conn.execute("DELETE FROM sessions WHERE uuid = ?", (uuid,))
        conn.execute("DELETE FROM session_tools WHERE session_uuid = ?", (uuid,))
        conn.execute("DELETE FROM session_skills WHERE session_uuid = ?", (uuid,))
        conn.execute("DELETE FROM session_commands WHERE session_uuid = ?", (uuid,))
        conn.execute("DELETE FROM message_uuids WHERE session_uuid = ?", (uuid,))
        conn.execute("DELETE FROM session_leaf_refs WHERE session_uuid = ?", (uuid,))
        conn.execute("DELETE FROM subagent_invocations WHERE session_uuid = ?", (uuid,))
        return

    # Extract all metadata
    usage = session.get_usage_summary()
    tools_used = session.get_tools_used()
    skills_used = session.get_skills_used()
    skills_mentioned = session.get_skills_mentioned()
    commands_used = session.get_commands_used()
    models_used = list(session.get_models_used())
    git_branches = list(session.get_git_branches())
    session_titles = session.session_titles or []
    initial_prompt = get_initial_prompt(session, max_length=500)

    # Count subagents via filesystem (fast, no JSONL parse)
    subagent_count = 0
    subagents_dir = jsonl_path.parent / uuid / "subagents"
    if subagents_dir.exists():
        subagent_count = len(list(subagents_dir.glob("agent-*.jsonl")))

    # Detect project_path from session data (or use override for worktrees)
    project_path = project_path_override or _detect_project_path(session, encoded_name)

    # Auto-detect session source from Desktop metadata if not provided
    if session_source is None:
        from services.desktop_sessions import get_session_source

        session_source = get_session_source(uuid)

    # Upsert session
    conn.execute(
        """
        INSERT OR REPLACE INTO sessions (
            uuid, slug, project_encoded_name, project_path,
            start_time, end_time, message_count, duration_seconds,
            input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens,
            total_cost, initial_prompt, git_branch, models_used,
            session_titles, is_continuation_marker, was_compacted,
            compaction_count, file_snapshot_count, subagent_count,
            jsonl_mtime, jsonl_size, session_source, source_encoded_name,
            source, remote_user_id, remote_machine_id,
            indexed_at
        ) VALUES (
            ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?,
            ?, ?, ?,
            datetime('now')
        )
        """,
        (
            uuid,
            session.slug,
            encoded_name,
            project_path,
            session.start_time.isoformat() if session.start_time else None,
            session.end_time.isoformat() if session.end_time else None,
            session.message_count,
            session.duration_seconds,
            usage.total_input,
            usage.output_tokens,
            usage.cache_creation_input_tokens,
            usage.cache_read_input_tokens,
            session.get_total_cost(),
            initial_prompt,
            git_branches[0] if git_branches else None,
            json.dumps(models_used) if models_used else None,
            json.dumps(session_titles) if session_titles else None,
            1 if session.is_continuation_marker else 0,
            1 if session.was_compacted else 0,
            session.compaction_summary_count,
            session.file_snapshot_count,
            subagent_count,
            mtime,
            size,
            session_source,
            source_encoded_name,
            source or "local",
            remote_user_id,
            remote_machine_id,
        ),
    )

    # Upsert tool usage (INSERT OR REPLACE + cleanup to avoid DELETE gap)
    if tools_used:
        for tool_name, count in tools_used.items():
            conn.execute(
                "INSERT OR REPLACE INTO session_tools VALUES (?, ?, ?)", (uuid, tool_name, count)
            )
        # Remove tools no longer present
        placeholders = ",".join("?" * len(tools_used))
        conn.execute(
            f"DELETE FROM session_tools WHERE session_uuid = ? AND tool_name NOT IN ({placeholders})",
            (uuid, *tools_used.keys()),
        )
    else:
        conn.execute("DELETE FROM session_tools WHERE session_uuid = ?", (uuid,))

    # Upsert skill usage with invocation_source
    # Keys are (skill_name, invocation_source) tuples
    # skills_used = actual invocations (slash_command, skill_tool)
    # skills_mentioned = text_detection only (user referenced but didn't invoke)
    conn.execute("DELETE FROM session_skills WHERE session_uuid = ?", (uuid,))
    all_skills = {**skills_used, **skills_mentioned}
    if all_skills:
        for (skill_name, source), count in all_skills.items():
            conn.execute(
                "INSERT OR REPLACE INTO session_skills (session_uuid, skill_name, invocation_source, count) VALUES (?, ?, ?, ?)",
                (uuid, skill_name, source, count),
            )

    # Upsert command usage with invocation_source
    # Keys are (command_name, invocation_source) tuples
    conn.execute("DELETE FROM session_commands WHERE session_uuid = ?", (uuid,))
    if commands_used:
        for (cmd_name, source), count in commands_used.items():
            conn.execute(
                "INSERT OR REPLACE INTO session_commands (session_uuid, command_name, invocation_source, count) VALUES (?, ?, ?, ?)",
                (uuid, cmd_name, source, count),
            )

    # Upsert message UUIDs (for continuation lookup)
    conn.execute("DELETE FROM message_uuids WHERE session_uuid = ?", (uuid,))
    msg_uuids = []
    for msg in session.iter_messages():
        if hasattr(msg, "uuid") and msg.uuid:
            msg_uuids.append((msg.uuid, uuid))
    if msg_uuids:
        conn.executemany(
            "INSERT OR IGNORE INTO message_uuids (message_uuid, session_uuid) VALUES (?, ?)",
            msg_uuids,
        )

    # Upsert session leaf_uuid references (for chain detection)
    conn.execute("DELETE FROM session_leaf_refs WHERE session_uuid = ?", (uuid,))
    leaf_uuids = session.project_context_leaf_uuids
    if leaf_uuids:
        conn.executemany(
            "INSERT OR IGNORE INTO session_leaf_refs (session_uuid, leaf_uuid) VALUES (?, ?)",
            [(uuid, lu) for lu in leaf_uuids],
        )

    # Upsert subagent invocations
    conn.execute(
        "DELETE FROM subagent_skills WHERE invocation_id IN (SELECT id FROM subagent_invocations WHERE session_uuid = ?)",
        (uuid,),
    )
    conn.execute(
        "DELETE FROM subagent_commands WHERE invocation_id IN (SELECT id FROM subagent_invocations WHERE session_uuid = ?)",
        (uuid,),
    )
    conn.execute(
        "DELETE FROM subagent_tools WHERE invocation_id IN (SELECT id FROM subagent_invocations WHERE session_uuid = ?)",
        (uuid,),
    )
    conn.execute("DELETE FROM subagent_invocations WHERE session_uuid = ?", (uuid,))
    if subagent_count > 0:
        try:
            from services.subagent_types import get_all_subagent_types

            subagent_types = get_all_subagent_types(jsonl_path, subagents_dir)
            for subagent in session.list_subagents():
                subagent_type = subagent_types.get(subagent.agent_id, "_unknown")
                if subagent_type == "_unknown":
                    logger.debug(
                        "Skipping unclassified subagent %s in session %s", subagent.agent_id, uuid
                    )
                    continue
                usage = subagent.get_usage_summary()
                duration = 0.0
                if subagent.start_time and subagent.end_time:
                    duration = (subagent.end_time - subagent.start_time).total_seconds()
                conn.execute(
                    """INSERT INTO subagent_invocations
                       (session_uuid, agent_id, subagent_type, input_tokens,
                        output_tokens, cost_usd, duration_seconds, started_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        uuid,
                        subagent.agent_id,
                        subagent_type,
                        usage.total_input,
                        usage.output_tokens,
                        usage.calculate_cost(),
                        duration,
                        subagent.start_time.isoformat() if subagent.start_time else None,
                    ),
                )

                invocation_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

                # Count tool/skill/command usage from subagent messages
                # skill_counts/command_counts use (name, source) tuple keys
                tool_counts = {}
                skill_counts = {}
                command_counts = {}
                for msg in subagent.iter_messages():
                    # Check if this is an AssistantMessage with tool_names property
                    if hasattr(msg, "tool_names"):
                        for tool_name in msg.tool_names:
                            tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1
                    # Extract skill/command from Skill tool inputs
                    if hasattr(msg, "content_blocks"):
                        for block in msg.content_blocks:
                            if (
                                hasattr(block, "name")
                                and block.name == "Skill"
                                and hasattr(block, "input")
                                and block.input
                            ):
                                skill_name = block.input.get("skill")
                                if skill_name:
                                    from command_helpers import (
                                        classify_invocation,
                                        expand_plugin_short_name,
                                        is_command_category,
                                        is_skill_category,
                                    )

                                    # Normalize short-form plugin names
                                    skill_name = expand_plugin_short_name(skill_name)
                                    kind = classify_invocation(skill_name, source="skill_tool")
                                    source = "skill_tool"
                                    if is_skill_category(kind):
                                        key = (skill_name, source)
                                        skill_counts[key] = skill_counts.get(key, 0) + 1
                                    elif is_command_category(kind):
                                        key = (skill_name, source)
                                        command_counts[key] = command_counts.get(key, 0) + 1

                if tool_counts:
                    conn.executemany(
                        "INSERT INTO subagent_tools (invocation_id, tool_name, count) VALUES (?, ?, ?)",
                        [(invocation_id, name, count) for name, count in tool_counts.items()],
                    )
                if skill_counts:
                    conn.executemany(
                        "INSERT INTO subagent_skills (invocation_id, skill_name, invocation_source, count) VALUES (?, ?, ?, ?)",
                        [
                            (invocation_id, name, source, count)
                            for (name, source), count in skill_counts.items()
                        ],
                    )
                if command_counts:
                    conn.executemany(
                        "INSERT INTO subagent_commands (invocation_id, command_name, invocation_source, count) VALUES (?, ?, ?, ?)",
                        [
                            (invocation_id, name, source, count)
                            for (name, source), count in command_counts.items()
                        ],
                    )
        except Exception as e:
            logger.warning("Error indexing subagent invocations for %s: %s", uuid, e)


def _detect_project_path(session, encoded_name: str) -> Optional[str]:
    """
    Detect the real project path from session data or encoded name.

    Tries working directories first, then decodes the encoded name.
    """
    # Try getting from working directories
    working_dirs = list(session.get_working_directories())
    if working_dirs:
        return working_dirs[0]

    # Fallback: Decode from encoded name (lossy for paths with hyphens).
    # Only use the decoded path if it actually exists on disk, to avoid
    # storing wrong paths (e.g. "claude-karma" → "claude/karma").
    if encoded_name.startswith("-"):
        decoded = "/" + encoded_name[1:].replace("-", "/")
        if Path(decoded).is_dir():
            return decoded

    # Don't store a bad path — let _update_project_summaries resolve it
    # from sibling sessions that have working directory data.
    return None


def _cleanup_stale_sessions(conn: sqlite3.Connection, projects_dir: Path) -> None:
    """
    Remove sessions from DB whose JSONL files no longer exist on disk.

    This handles deleted sessions and renamed/moved project directories.
    Uses source_encoded_name (the actual directory) for worktree-remapped sessions,
    falling back to project_encoded_name for normal sessions.
    """
    import os

    # Get all non-remote sessions grouped by their actual source directory
    # source_encoded_name is set for worktree-remapped sessions;
    # for normal sessions it's NULL and we use project_encoded_name
    # Remote sessions live outside projects_dir, so skip them here.
    session_rows = conn.execute(
        "SELECT uuid, COALESCE(source_encoded_name, project_encoded_name) as source_dir FROM sessions WHERE COALESCE(source, 'local') != 'remote'"
    ).fetchall()

    # Group by source directory
    by_dir: dict[str, list[str]] = {}
    for row in session_rows:
        source_dir = row["source_dir"]
        by_dir.setdefault(source_dir, []).append(row["uuid"])

    stale_uuids = []

    for source_dir, uuids in by_dir.items():
        project_dir = projects_dir / source_dir

        # Build set of existing UUIDs on disk using scandir (single traversal)
        existing_uuids = set()
        if project_dir.exists():
            try:
                for entry in os.scandir(project_dir):
                    if (
                        entry.is_file()
                        and entry.name.endswith(".jsonl")
                        and not entry.name.startswith("agent-")
                    ):
                        existing_uuids.add(entry.name[:-6])  # Remove .jsonl extension
            except OSError as e:
                logger.warning("Error scanning project directory %s: %s", source_dir, e)

        for uuid in uuids:
            if uuid not in existing_uuids:
                stale_uuids.append(uuid)

    if stale_uuids:
        placeholders = ",".join("?" * len(stale_uuids))
        conn.execute(
            f"DELETE FROM sessions WHERE uuid IN ({placeholders})",
            stale_uuids,
        )
        conn.execute(
            f"DELETE FROM session_tools WHERE session_uuid IN ({placeholders})",
            stale_uuids,
        )
        conn.execute(
            f"DELETE FROM session_skills WHERE session_uuid IN ({placeholders})",
            stale_uuids,
        )
        conn.execute(
            f"DELETE FROM session_commands WHERE session_uuid IN ({placeholders})",
            stale_uuids,
        )
        conn.execute(
            f"DELETE FROM message_uuids WHERE session_uuid IN ({placeholders})",
            stale_uuids,
        )
        conn.execute(
            f"DELETE FROM session_leaf_refs WHERE session_uuid IN ({placeholders})",
            stale_uuids,
        )
        conn.execute(
            f"DELETE FROM subagent_skills WHERE invocation_id IN (SELECT id FROM subagent_invocations WHERE session_uuid IN ({placeholders}))",
            stale_uuids,
        )
        conn.execute(
            f"DELETE FROM subagent_commands WHERE invocation_id IN (SELECT id FROM subagent_invocations WHERE session_uuid IN ({placeholders}))",
            stale_uuids,
        )
        conn.execute(
            f"DELETE FROM subagent_tools WHERE invocation_id IN (SELECT id FROM subagent_invocations WHERE session_uuid IN ({placeholders}))",
            stale_uuids,
        )
        conn.execute(
            f"DELETE FROM subagent_invocations WHERE session_uuid IN ({placeholders})",
            stale_uuids,
        )
        conn.commit()
        logger.info("Removed %d stale sessions from index", len(stale_uuids))


def _resolve_project_path(encoded_name: str, candidate_paths: list) -> str:
    """Pick the project_path whose encoding matches the encoded_name.

    When multiple paths encode to the same string (lossy encoding — hyphens
    and slashes both become '-'), prefers the path that exists on disk.
    Falls back to shortest path if no encoding match is found.
    """
    from pathlib import Path

    if not candidate_paths:
        # Last resort: decode from encoded name (lossy for hyphenated paths)
        if encoded_name.startswith("-"):
            return "/" + encoded_name[1:].replace("-", "/")
        return encoded_name

    # Find all paths whose encoding matches the encoded_name
    # (multiple paths can match due to lossy encoding: / and - both become -)
    matches = []
    for path in candidate_paths:
        if not path:
            continue
        if path.startswith("/"):
            encoded = "-" + path[1:].replace("/", "-")
        else:
            encoded = path.replace("/", "-")
        if encoded == encoded_name:
            matches.append(path)

    if matches:
        # Prefer the match that exists on disk
        for path in matches:
            if Path(path).is_dir():
                return path
        return matches[0]

    # Fallback: shortest path (closest to project root)
    return min((p for p in candidate_paths if p), key=len, default=candidate_paths[0] or "")


def _update_project_summaries(conn: sqlite3.Connection) -> None:
    """
    Update the projects summary table from aggregated session data.
    Uses INSERT OR REPLACE to avoid race condition between DELETE and INSERT.
    Computes slug and display_name for URL beautification.
    """
    from pathlib import Path

    from utils import compute_project_slug

    rows = conn.execute(
        """
        SELECT
            project_encoded_name,
            COUNT(*) as session_count,
            MAX(start_time) as last_activity
        FROM sessions
        GROUP BY project_encoded_name
        """
    ).fetchall()

    for row in rows:
        encoded_name = row[0]
        session_count = row[1]
        last_activity = row[2]

        # Find the correct project_path by encoding-match (not arbitrary GROUP BY)
        path_rows = conn.execute(
            "SELECT DISTINCT project_path FROM sessions WHERE project_encoded_name = ? AND project_path IS NOT NULL",
            (encoded_name,),
        ).fetchall()
        project_path = _resolve_project_path(encoded_name, [r[0] for r in path_rows])

        slug = compute_project_slug(encoded_name, project_path)
        display_name = Path(project_path).name if project_path else encoded_name

        conn.execute(
            """
            INSERT OR REPLACE INTO projects
                (encoded_name, project_path, slug, display_name, session_count, last_activity)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (encoded_name, project_path, slug, display_name, session_count, last_activity),
        )

    conn.commit()


def _log_db_health(conn: sqlite3.Connection) -> dict:
    """
    Log database health metrics and auto-vacuum if needed.

    Returns dict with health metrics for use by /health endpoint.
    """
    from db.connection import get_db_path

    metrics = {}

    try:
        db_path = get_db_path()

        # DB file size
        if db_path.exists():
            metrics["db_size_bytes"] = db_path.stat().st_size
            metrics["db_size_kb"] = round(db_path.stat().st_size / 1024, 1)

        # WAL file size
        wal_path = db_path.parent / (db_path.name + "-wal")
        if wal_path.exists():
            metrics["wal_size_bytes"] = wal_path.stat().st_size
            metrics["wal_size_kb"] = round(wal_path.stat().st_size / 1024, 1)

        # Row counts
        metrics["session_count"] = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        metrics["invocation_count"] = conn.execute(
            "SELECT COUNT(*) FROM subagent_invocations"
        ).fetchone()[0]
        metrics["subagent_skills_count"] = conn.execute(
            "SELECT COUNT(*) FROM subagent_skills"
        ).fetchone()[0]
        metrics["subagent_commands_count"] = conn.execute(
            "SELECT COUNT(*) FROM subagent_commands"
        ).fetchone()[0]

        # Fragmentation check
        page_count = conn.execute("PRAGMA page_count").fetchone()[0]
        freelist_count = conn.execute("PRAGMA freelist_count").fetchone()[0]

        if page_count > 0:
            fragmentation = freelist_count / page_count
            metrics["fragmentation_pct"] = round(fragmentation * 100, 1)

            # Auto-vacuum if fragmentation > 10%
            if fragmentation > 0.10:
                logger.info(
                    "DB fragmentation at %.1f%%, running VACUUM",
                    fragmentation * 100,
                )
                conn.execute("VACUUM")
                metrics["vacuumed"] = True

        logger.info(
            "DB health: size=%sKB, sessions=%d, invocations=%d, fragmentation=%.1f%%",
            metrics.get("db_size_kb", "?"),
            metrics.get("session_count", 0),
            metrics.get("invocation_count", 0),
            metrics.get("fragmentation_pct", 0),
        )

    except Exception as e:
        logger.warning("DB health check failed: %s", e)
        metrics["error"] = str(e)

    global _last_health
    _last_health = metrics

    return metrics


async def run_periodic_sync(interval_seconds: int = 300) -> None:
    """
    Periodically re-index changed sessions every N seconds.

    Runs as an asyncio background task in the API lifespan. Uses
    asyncio.to_thread() to avoid blocking the event loop, since
    sync_all_projects() does heavy file I/O + SQLite writes.

    The first run is skipped (startup indexer handles the initial sync).
    Shares _indexing_lock with startup indexer to prevent overlap.
    """
    import asyncio

    # Wait for initial index to complete before starting periodic runs
    while not _ready.is_set():
        await asyncio.sleep(1)

    logger.info("Periodic reindex started (interval=%ds)", interval_seconds)

    while True:
        await asyncio.sleep(interval_seconds)
        try:
            from .connection import get_writer_db

            conn = get_writer_db()
            stats = await asyncio.to_thread(sync_all_projects, conn)
            logger.info("Periodic reindex complete: %s", stats)
        except Exception as e:
            logger.warning("Periodic reindex failed: %s", e)


def run_background_sync() -> None:
    """
    Run a full index sync in a background thread.

    Called during API startup to build/refresh the index without
    blocking request handling.
    """
    from .connection import get_writer_db

    try:
        logger.info("Starting background index sync...")
        conn = get_writer_db()
        stats = sync_all_projects(conn)
        logger.info("Background sync complete: %s", stats)
    except Exception as e:
        logger.error("Background sync failed: %s", e)
        # Still mark as ready so the API falls back to old code path
        _ready.set()
