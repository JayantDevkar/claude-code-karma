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

from utils import is_encoded_project_dir

# Ensure api/ is on the import path (needed when called from background thread)
sys.path.insert(0, str(Path(__file__).parent.parent))

from command_helpers import category_from_base_directory

logger = logging.getLogger(__name__)

# Module-level state
_ready = threading.Event()
_indexing_lock = threading.Lock()
_last_health: dict = {}
_last_sync_complete: float = 0.0
_reindex_lock = threading.Lock()  # Separate lock for on-demand remote reindex


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
            if not encoded_dir.is_dir() or not is_encoded_project_dir(encoded_dir.name):
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


def _load_manifest_classifications(encoded_dir: Path) -> dict[str, str]:
    """Load skill_classifications from a remote project's manifest.json.

    Returns a mapping of invocation name → InvocationCategory string
    (e.g. {'feature-dev:feature-dev': 'plugin_command'}).
    Returns empty dict if manifest doesn't exist or lacks the field.

    Uses validate_manifest() to ensure the manifest is safe before reading.
    """
    manifest_path = encoded_dir / "manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        from services.file_validator import validate_manifest
        manifest, reason = validate_manifest(manifest_path)
        if manifest is None:
            logger.warning("Invalid manifest at %s: %s", manifest_path, reason)
            return {}
        return manifest.skill_classifications
    except Exception as e:
        logger.warning("Error loading manifest at %s: %s", manifest_path, e)
        return {}


def _load_manifest_skill_definitions(encoded_dir: Path) -> dict:
    """Load skill_definitions from a remote project's manifest.json.

    Returns a dict of skill_name → {content, description, category, base_directory}.
    Returns empty dict if manifest doesn't exist or lacks the field.
    """
    manifest_path = encoded_dir / "manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        from services.file_validator import validate_manifest

        manifest, reason = validate_manifest(manifest_path)
        if manifest is None:
            logger.warning("Invalid manifest at %s: %s", manifest_path, reason)
            return {}
        # Convert SkillDefinitionEntry models to plain dicts
        return {
            name: entry.model_dump() if hasattr(entry, "model_dump") else entry
            for name, entry in manifest.skill_definitions.items()
        }
    except Exception as e:
        logger.warning("Error loading manifest skill definitions at %s: %s", manifest_path, e)
        return {}


def _apply_manifest_skill_definitions(
    conn: sqlite3.Connection,
    skill_definitions: dict,
    source_user_id: str,
    source_machine_id: str,
) -> None:
    """Write manifest-provided skill definitions to the skill_definitions table.

    Called once per manifest (not per session). Manifest content takes precedence
    over heuristic JSONL extraction because it was read directly from the
    exporting machine's filesystem.

    Hard-overrides content and category (manifest is authoritative).
    Uses COALESCE for description and base_directory (preserves existing
    values when the manifest entry has nulls, e.g. no YAML frontmatter).
    Sets extracted_from_session to NULL since this content is from the filesystem.
    """
    for skill_name, entry in skill_definitions.items():
        content = entry.get("content") if isinstance(entry, dict) else None
        if not content:
            continue  # Skip entries without content

        category = entry.get("category", "plugin_skill")
        description = entry.get("description")
        base_directory = entry.get("base_directory")

        try:
            conn.execute(
                """
                INSERT INTO skill_definitions
                    (skill_name, source_user_id, source_machine_id, category,
                     content, base_directory, description, extracted_from_session,
                     updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, NULL, datetime('now'))
                ON CONFLICT(skill_name, source_user_id) DO UPDATE SET
                    content      = excluded.content,
                    category     = excluded.category,
                    base_directory = COALESCE(excluded.base_directory, skill_definitions.base_directory),
                    description  = COALESCE(excluded.description, skill_definitions.description),
                    updated_at   = datetime('now')
                """,
                (
                    skill_name,
                    source_user_id,
                    source_machine_id,
                    category,
                    content,
                    base_directory,
                    description,
                ),
            )
        except Exception as e:
            logger.debug(
                "Error writing manifest skill definition for %s: %s", skill_name, e
            )


def index_remote_sessions(conn: sqlite3.Connection) -> dict:
    """
    Index remote sessions from Syncthing-synced directories into SQLite.

    Walks ~/.claude_karma/remote-sessions/{user_id}/{encoded_name}/sessions/
    and upserts session rows with source='remote'. Skips local user's outbox.

    Reads skill_classifications from each project's manifest.json to correctly
    classify remote skills vs commands (instead of relying on local plugin cache).

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

    from services.remote_sessions import _load_remote_titles, _resolve_user_id

    for user_dir in remote_base.iterdir():
        if not user_dir.is_dir():
            continue
        dir_name = user_dir.name
        resolved_uid = _resolve_user_id(user_dir, conn=conn)

        # If resolved_uid still looks like a hostname (contains '.'), try to
        # find the canonical member name from sync_members by matching device_id.
        # This handles the case where no manifest.json exists yet (member hasn't
        # packaged sessions, only received them from us).
        if "." in resolved_uid:
            try:
                from repositories.member_repo import MemberRepository
                # Look up member by member_tag pattern in v4 schema
                row = conn.execute(
                    "SELECT member_tag FROM sync_members WHERE member_tag = ?",
                    (resolved_uid,),
                ).fetchone()
                if row:
                    resolved_uid = row[0]
            except Exception:
                pass  # DB lookup failed — keep resolved_uid as-is

        # Fixup stale remote_user_id values (e.g. hostname → clean user_id)
        if dir_name != resolved_uid:
            updated = conn.execute(
                "UPDATE sessions SET remote_user_id = ? WHERE remote_user_id = ? AND source = 'remote'",
                (resolved_uid, dir_name),
            ).rowcount
            if updated:
                logger.info("Corrected remote_user_id '%s' → '%s' for %d sessions", dir_name, resolved_uid, updated)

        # Skip local user's outbox (check both dir name and resolved id)
        if dir_name == local_user or resolved_uid == local_user:
            continue

        for encoded_dir in user_dir.iterdir():
            if not encoded_dir.is_dir():
                continue
            encoded_name = encoded_dir.name
            # Mapping keys use dir_name (filesystem identity)
            local_encoded = mapping.get((dir_name, encoded_name), encoded_name)

            sessions_dir = encoded_dir / "sessions"
            if not sessions_dir.exists():
                continue

            # Load manifest classifications once per (dir_name, project)
            classification_overrides = _load_manifest_classifications(encoded_dir)

            # Load titles once per (dir_name, project) for remote session title display
            titles_map = _load_remote_titles(dir_name, encoded_name)

            # Force re-index when manifest/titles have been updated since last index.
            # Without this, the mtime-based skip would prevent reclassification of
            # sessions already indexed (their JSONL files haven't changed).
            force_reindex = False
            # Check both manifest.json (classifications) and titles.json (session titles)
            metadata_files = []
            if classification_overrides:
                manifest_path = encoded_dir / "manifest.json"
                if manifest_path.exists():
                    metadata_files.append(manifest_path)
            if titles_map:
                titles_path = encoded_dir / "titles.json"
                if titles_path.exists():
                    metadata_files.append(titles_path)

            if metadata_files:
                oldest_indexed = conn.execute(
                    "SELECT MIN(indexed_at) FROM sessions WHERE remote_user_id IN (?, ?) AND project_encoded_name = ? AND source = 'remote'",
                    (resolved_uid, dir_name, local_encoded),
                ).fetchone()
                if oldest_indexed and oldest_indexed[0]:
                    from datetime import datetime, timezone
                    try:
                        indexed_dt = datetime.fromisoformat(oldest_indexed[0])
                        for meta_file in metadata_files:
                            meta_mtime = meta_file.stat().st_mtime
                            meta_dt = datetime.fromtimestamp(meta_mtime, tz=timezone.utc).replace(tzinfo=None)
                            if meta_dt > indexed_dt:
                                force_reindex = True
                                break
                    except (ValueError, OSError):
                        pass

            # Apply manifest skill definitions once per project (before per-session loop).
            # Manifest content is authoritative — takes precedence over JSONL heuristics.
            manifest_skill_defs = _load_manifest_skill_definitions(encoded_dir)
            if manifest_skill_defs:
                _apply_manifest_skill_definitions(
                    conn, manifest_skill_defs,
                    source_user_id=resolved_uid,
                    source_machine_id=dir_name,
                )

            for jsonl_path in sessions_dir.glob("*.jsonl"):
                if jsonl_path.name.startswith("agent-"):
                    continue

                uuid = jsonl_path.stem
                stats["total"] += 1

                try:
                    file_stat = jsonl_path.stat()
                    current_mtime = file_stat.st_mtime
                    current_size = file_stat.st_size

                    if not force_reindex and uuid in db_mtimes and abs(db_mtimes[uuid] - current_mtime) < 0.001:
                        stats["skipped"] += 1
                        continue

                    # Validate file before indexing
                    from services.file_validator import quarantine_file, validate_received_file
                    valid, reason = validate_received_file(jsonl_path)
                    if not valid:
                        quarantine_file(jsonl_path, reason, member_name=resolved_uid)
                        logger.warning(
                            "Rejected remote file %s from %s: %s", jsonl_path.name, resolved_uid, reason
                        )
                        try:
                            from repositories.event_repo import EventRepository
                            from domain.events import SyncEvent, SyncEventType
                            EventRepository().log(conn, SyncEvent(
                                event_type=SyncEventType.session_received,
                                member_tag=resolved_uid,
                                project_git_identity=local_encoded,
                                session_uuid=uuid,
                                detail={"reason": reason, "file": jsonl_path.name, "rejected": True},
                            ))
                        except Exception:
                            pass  # Best-effort logging
                        stats["errors"] += 1
                        continue

                    _index_session(
                        conn,
                        jsonl_path,
                        local_encoded,
                        current_mtime,
                        current_size,
                        source="remote",
                        remote_user_id=resolved_uid,
                        remote_machine_id=dir_name,
                        claude_base_dir=encoded_dir,
                        classification_overrides=classification_overrides,
                        session_titles_override=[titles_map[uuid]] if uuid in titles_map else None,
                    )
                    stats["indexed"] += 1

                    # Extract skill definitions from this remote session (best-effort).
                    # Runs for every indexed session; ON CONFLICT DO NOTHING makes it idempotent.
                    _extract_skill_definitions_from_session(
                        conn,
                        jsonl_path,
                        source_user_id=resolved_uid,
                        source_machine_id=dir_name,
                        session_uuid=uuid,
                        claude_base_dir=encoded_dir,
                        classification_overrides=classification_overrides,
                    )

                    # Log session_received for truly new sessions (not re-index).
                    # Dedup against sync_events to prevent duplicates from concurrent
                    # indexer runs (reindex_all + trigger_remote_reindex use separate locks).
                    if uuid not in db_mtimes:
                        try:
                            from repositories.event_repo import EventRepository
                            from domain.events import SyncEvent, SyncEventType
                            already_logged = conn.execute(
                                "SELECT 1 FROM sync_events WHERE event_type = 'session_received' AND session_uuid = ? LIMIT 1",
                                (uuid,),
                            ).fetchone()
                            if not already_logged:
                                team_names = conn.execute(
                                    "SELECT team_name FROM sync_projects WHERE encoded_name = ?",
                                    (local_encoded,),
                                ).fetchall()
                                event_repo = EventRepository()
                                if team_names:
                                    for (tn,) in team_names:
                                        event_repo.log(conn, SyncEvent(
                                            event_type=SyncEventType.session_received,
                                            team_name=tn,
                                            member_tag=resolved_uid,
                                            project_git_identity=local_encoded,
                                            session_uuid=uuid,
                                        ))
                                else:
                                    event_repo.log(conn, SyncEvent(
                                        event_type=SyncEventType.session_received,
                                        member_tag=resolved_uid,
                                        project_git_identity=local_encoded,
                                        session_uuid=uuid,
                                    ))
                        except Exception:
                            pass  # Best-effort logging
                except Exception as e:
                    logger.debug("Error indexing remote session %s: %s", uuid, e)
                    stats["errors"] += 1

    # ---------------------------------------------------------------
    # v4 inbox scan: karma-out--{member_tag}--{suffix}/ directories
    # ---------------------------------------------------------------
    karma_base = settings.karma_base
    local_member_tag = None
    try:
        import json as _json
        cfg_path = karma_base / "sync-config.json"
        if cfg_path.exists():
            cfg = _json.loads(cfg_path.read_text())
            uid = cfg.get("user_id", "")
            mtag = cfg.get("machine_tag", "")
            if uid and mtag:
                local_member_tag = f"{uid}.{mtag}"
    except Exception:
        pass

    for inbox_dir in karma_base.iterdir():
        if not inbox_dir.is_dir():
            continue
        dname = inbox_dir.name
        if not dname.startswith("karma-out--"):
            continue
        # Parse: karma-out--{member_tag}--{folder_suffix}
        rest = dname[len("karma-out--"):]
        parts = rest.split("--", 1)
        if len(parts) != 2:
            continue
        inbox_member_tag, inbox_suffix = parts

        # Skip our own outbox (we only want inboxes from teammates)
        if local_member_tag and inbox_member_tag == local_member_tag:
            continue

        sessions_dir = inbox_dir / "sessions"
        if not sessions_dir.exists():
            continue

        # Resolve local project encoded_name via git_identity.
        # Step 1: Look up the real git_identity from sync_projects using folder_suffix
        # Step 2: Match that git_identity against local projects table
        local_encoded = inbox_suffix  # fallback
        try:
            # Get git_identity from sync_projects (the source of truth)
            sp_row = conn.execute(
                "SELECT git_identity FROM sync_projects "
                "WHERE folder_suffix = ? AND status = 'shared' LIMIT 1",
                (inbox_suffix,),
            ).fetchone()
            if sp_row and sp_row[0]:
                sync_git_id = sp_row[0].rstrip("/").lower()
                if sync_git_id.endswith(".git"):
                    sync_git_id = sync_git_id[:-4]

                # Match against local projects by git_identity
                local_rows = conn.execute(
                    "SELECT encoded_name, git_identity FROM projects "
                    "WHERE git_identity IS NOT NULL"
                ).fetchall()
                for (enc, local_git) in local_rows:
                    lg = (local_git or "").rstrip("/").lower()
                    if lg.endswith(".git"):
                        lg = lg[:-4]
                    # Match: one contains the other (handles short vs full URLs)
                    if lg and (lg in sync_git_id or sync_git_id in lg
                               or lg.endswith(sync_git_id)
                               or sync_git_id.endswith(lg)):
                        local_encoded = enc
                        break
        except Exception:
            pass

        # Fallback: try get_project_mapping()
        if local_encoded == inbox_suffix:
            local_encoded = mapping.get(
                (inbox_member_tag, inbox_suffix), inbox_suffix
            )

        classification_overrides = _load_manifest_classifications(inbox_dir)
        titles_map = _load_remote_titles(inbox_member_tag, local_encoded)

        force_reindex = False
        metadata_files = []
        if classification_overrides:
            mf = inbox_dir / "manifest.json"
            if mf.exists():
                metadata_files.append(mf)
        if titles_map:
            tf = inbox_dir / "titles.json"
            if tf.exists():
                metadata_files.append(tf)
        if metadata_files:
            oldest_indexed = conn.execute(
                "SELECT MIN(indexed_at) FROM sessions WHERE remote_user_id = ? AND project_encoded_name = ? AND source = 'remote'",
                (inbox_member_tag, local_encoded),
            ).fetchone()
            if oldest_indexed and oldest_indexed[0]:
                from datetime import datetime as _dt2, timezone as _tz2
                try:
                    indexed_dt = _dt2.fromisoformat(oldest_indexed[0])
                    for mf2 in metadata_files:
                        mtime2 = mf2.stat().st_mtime
                        mdt2 = _dt2.fromtimestamp(mtime2, tz=_tz2.utc).replace(tzinfo=None)
                        if mdt2 > indexed_dt:
                            force_reindex = True
                            break
                except (ValueError, OSError):
                    pass

        manifest_skill_defs = _load_manifest_skill_definitions(inbox_dir)
        if manifest_skill_defs:
            _apply_manifest_skill_definitions(
                conn, manifest_skill_defs,
                source_user_id=inbox_member_tag,
                source_machine_id=inbox_member_tag,
            )

        for jsonl_path in sessions_dir.glob("*.jsonl"):
            if jsonl_path.name.startswith("agent-"):
                continue
            uuid = jsonl_path.stem
            stats["total"] += 1
            try:
                file_stat = jsonl_path.stat()
                current_mtime = file_stat.st_mtime

                if not force_reindex and uuid in db_mtimes and abs(db_mtimes[uuid] - current_mtime) < 0.001:
                    stats["skipped"] += 1
                    continue

                from services.file_validator import quarantine_file, validate_received_file
                valid, reason = validate_received_file(jsonl_path)
                if not valid:
                    quarantine_file(jsonl_path, reason, member_name=inbox_member_tag)
                    stats["errors"] += 1
                    continue

                _index_session(
                    conn,
                    jsonl_path,
                    local_encoded,
                    current_mtime,
                    file_stat.st_size,
                    source="remote",
                    remote_user_id=inbox_member_tag,
                    remote_machine_id=inbox_member_tag,
                    claude_base_dir=inbox_dir,
                    classification_overrides=classification_overrides,
                    session_titles_override=[titles_map[uuid]] if uuid in titles_map else None,
                )
                stats["indexed"] += 1

                if uuid not in db_mtimes:
                    try:
                        from repositories.event_repo import EventRepository
                        from domain.events import SyncEvent, SyncEventType
                        already_logged = conn.execute(
                            "SELECT 1 FROM sync_events WHERE event_type = 'session_received' AND session_uuid = ? LIMIT 1",
                            (uuid,),
                        ).fetchone()
                        if not already_logged:
                            team_names = conn.execute(
                                "SELECT team_name FROM sync_projects WHERE folder_suffix = ?",
                                (inbox_suffix,),
                            ).fetchall()
                            event_repo = EventRepository()
                            for (tn,) in team_names:
                                event_repo.log(conn, SyncEvent(
                                    event_type=SyncEventType.session_received,
                                    team_name=tn,
                                    member_tag=inbox_member_tag,
                                    project_git_identity=local_encoded,
                                    session_uuid=uuid,
                                ))
                    except Exception:
                        pass
            except Exception as e:
                logger.debug("Error indexing v4 inbox session %s: %s", uuid, e)
                stats["errors"] += 1

    conn.commit()
    return stats


def trigger_remote_reindex() -> dict:
    """Trigger an immediate remote session reindex.

    Called after sync actions (folder acceptance, device pairing) so that
    newly arrived remote sessions appear in the dashboard without waiting
    for the periodic 5-minute reindex cycle.

    Uses a separate lock to avoid blocking the full periodic indexer.
    Skips silently if a reindex is already in progress.

    Returns:
        Dict with sync statistics, or {"status": "skipped"} if already running.
    """
    if not _reindex_lock.acquire(blocking=False):
        return {"status": "skipped"}
    try:
        from .connection import create_writer_connection

        conn = create_writer_connection()
        try:
            stats = index_remote_sessions(conn)
            logger.info("On-demand remote reindex complete: %s", stats)
            return stats
        finally:
            conn.close()
    except Exception as e:
        logger.warning("On-demand remote reindex failed: %s", e)
        return {"status": "error", "error": str(e)}
    finally:
        _reindex_lock.release()


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
    claude_base_dir: Optional[Path] = None,
    classification_overrides: Optional[dict[str, str]] = None,
    session_titles_override: Optional[list[str]] = None,
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
        classification_overrides: Manifest-provided name→category map for remote sessions.
            When present, overrides local classify_invocation() results to fix
            misclassification of remote skills/commands.
        session_titles_override: Titles from external source (e.g., titles.json) to use
            when the JSONL doesn't contain title data (remote sessions).
    """
    from models import Session
    from utils import get_initial_prompt

    uuid = jsonl_path.stem

    # Parse session (triggers _load_metadata via property access)
    session = Session.from_path(jsonl_path, claude_base_dir=claude_base_dir)

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

    # Build JSONL-extracted category map by scanning messages for
    # "Base directory for this skill:" lines (secondary override source).
    # Priority: manifest override > JSONL-path category > local classify_invocation()
    jsonl_categories: dict[str, str] = {}
    try:
        from models.message import AssistantMessage as _AM, UserMessage as _UM
        from models.content import ToolUseBlock as _TUB

        _msgs = list(session.iter_messages())
        for _i, _msg in enumerate(_msgs):
            if not isinstance(_msg, _AM):
                continue
            for _blk in _msg.content_blocks:
                if not (isinstance(_blk, _TUB) and _blk.name == "Skill" and _blk.input):
                    continue
                _sn = _blk.input.get("skill")
                if not _sn:
                    continue
                for _j in range(_i + 1, min(_i + 8, len(_msgs))):
                    _nm = _msgs[_j]
                    if not isinstance(_nm, _UM):
                        continue
                    _nc = _nm.content or ""
                    if "Base directory for this skill:" not in _nc:
                        continue
                    try:
                        _marker = "Base directory for this skill:"
                        _idx = _nc.index(_marker)
                        _after = _nc[_idx + len(_marker):]
                        _lines = _after.strip().splitlines()
                        if _lines:
                            _bd = _lines[0].strip()
                            _cat = category_from_base_directory(_bd)
                            if _cat:
                                jsonl_categories[_sn] = _cat
                    except (ValueError, IndexError):
                        pass
                    break
    except Exception as _e:
        logger.debug("Error extracting JSONL categories for %s: %s", uuid, _e)

    # Reclassify skills/commands using manifest overrides (remote sessions only).
    # The local classify_invocation() may get colon-format names wrong when the
    # plugin isn't installed locally (defaults to "plugin_skill"). The manifest
    # carries the correct classification from the exporting machine.
    # Apply JSONL-extracted categories first (lower priority than manifest).
    if jsonl_categories and not classification_overrides:
        # No manifest — use JSONL-path categories alone
        classification_overrides = jsonl_categories
    elif jsonl_categories and classification_overrides:
        # Merge: manifest takes precedence, JSONL fills gaps
        merged = dict(jsonl_categories)
        merged.update(classification_overrides)
        classification_overrides = merged

    if classification_overrides:
        from command_helpers import is_command_category, is_skill_category

        # Make mutable copies
        skills_used = dict(skills_used)
        skills_mentioned = dict(skills_mentioned)
        commands_used = dict(commands_used)

        # Check skills that should be commands (both invoked and mentioned)
        for skill_dict in (skills_used, skills_mentioned):
            for key in list(skill_dict.keys()):
                name, inv_source = key
                override = classification_overrides.get(name)
                if override and is_command_category(override):
                    # Move from skills → commands
                    count = skill_dict.pop(key)
                    commands_used[(name, inv_source)] = commands_used.get((name, inv_source), 0) + count

        # Check commands that should be skills
        for key in list(commands_used.keys()):
            name, inv_source = key
            override = classification_overrides.get(name)
            if override and is_skill_category(override):
                # Move from commands → skills
                count = commands_used.pop(key)
                skills_used[(name, inv_source)] = skills_used.get((name, inv_source), 0) + count

    models_used = list(session.get_models_used())
    git_branches = list(session.get_git_branches())
    session_titles = session.session_titles or session_titles_override or []
    initial_prompt = get_initial_prompt(session)

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
            from services.subagent_types import get_all_subagent_metadata

            subagent_types, subagent_names = get_all_subagent_metadata(jsonl_path, subagents_dir)
            for subagent in session.list_subagents():
                subagent_type = subagent_types.get(subagent.agent_id, "_unknown")
                display_name = subagent_names.get(subagent.agent_id)
                usage = subagent.get_usage_summary()
                duration = 0.0
                if subagent.start_time and subagent.end_time:
                    duration = (subagent.end_time - subagent.start_time).total_seconds()
                conn.execute(
                    """INSERT INTO subagent_invocations
                       (session_uuid, agent_id, subagent_type, agent_display_name,
                        input_tokens, output_tokens, cost_usd, duration_seconds, started_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        uuid,
                        subagent.agent_id,
                        subagent_type,
                        display_name,
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
                                    # Override with manifest classification for remote sessions
                                    if classification_overrides and skill_name in classification_overrides:
                                        kind = classification_overrides[skill_name]
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



def _parse_yaml_description(content: str) -> Optional[str]:
    """Extract description field from YAML frontmatter (between --- markers)."""
    try:
        if not content.startswith("---"):
            return None
        end = content.index("---", 3)
        frontmatter = content[3:end].strip()
        for line in frontmatter.splitlines():
            if line.startswith("description:"):
                return line[len("description:"):].strip().strip('"').strip("'")
    except (ValueError, IndexError):
        pass
    return None


def _extract_skill_definitions_from_session(
    conn: sqlite3.Connection,
    jsonl_path: Path,
    source_user_id: Optional[str],
    source_machine_id: Optional[str],
    session_uuid: str,
    claude_base_dir: Optional[Path] = None,
    classification_overrides: Optional[dict[str, str]] = None,
) -> None:
    """Extract skill definitions (content + metadata) from a session's JSONL messages.

    Two-pass extraction:
      Pass 1: Look for 'Base directory for this skill:' marker in the next
              UserMessage (injected by Claude Code). Derives category from path.
      Pass 2: If no category from marker, fall back to manifest classification_overrides.
              Uses the raw UserMessage content as skill body when it looks like markdown.

    Persists custom_skill, user_command, and remote plugin_skill definitions.
    Skips local plugin_skill and bundled categories.
    Upserts new definitions into skill_definitions; skips if already present.

    Best-effort: all errors are logged as warnings, never raised.
    """
    try:
        from models import Session
        from models.message import AssistantMessage, UserMessage
        from models.content import ToolUseBlock

        session = Session.from_path(jsonl_path, claude_base_dir=claude_base_dir)

        # Collect messages into a list for adjacent-message lookahead
        messages = list(session.iter_messages())

        for i, msg in enumerate(messages):
            if not isinstance(msg, AssistantMessage):
                continue

            for block in msg.content_blocks:
                if not (isinstance(block, ToolUseBlock) and block.name == "Skill" and block.input):
                    continue

                skill_name = block.input.get("skill")
                if not skill_name:
                    continue

                # Skip if definition already exists WITH content
                existing_content = conn.execute(
                    "SELECT content FROM skill_definitions WHERE skill_name = ? AND source_user_id = ?",
                    (skill_name, source_user_id or "__local__"),
                ).fetchone()
                if existing_content and existing_content[0]:
                    continue  # Already have content, no need to re-extract

                # Pass 1: Look ahead for the "Base directory for this skill:" marker
                base_dir: Optional[str] = None
                content_text: Optional[str] = None
                description: Optional[str] = None
                category: Optional[str] = None
                next_user_content: Optional[str] = None

                # Lookahead window: ProgressMessages can sit between
                # the Skill tool_use and the injected UserMessage content,
                # so scan up to 8 messages ahead.
                for j in range(i + 1, min(i + 8, len(messages))):
                    next_msg = messages[j]
                    if not isinstance(next_msg, UserMessage):
                        continue
                    next_content = next_msg.content or ""

                    if "Base directory for this skill:" in next_content:
                        try:
                            marker = "Base directory for this skill:"
                            idx = next_content.index(marker)
                            after = next_content[idx + len(marker):]
                            lines = after.strip().splitlines()
                            if lines:
                                base_dir = lines[0].strip()
                                if len(lines) > 1:
                                    content_text = "\n".join(lines[1:]).strip() or None
                        except (ValueError, IndexError):
                            pass

                        if base_dir:
                            category = category_from_base_directory(base_dir)
                            if content_text:
                                description = _parse_yaml_description(content_text)
                        break  # Found the marker message

                    # Save the latest non-marker UserMessage for pass 2 fallback
                    next_user_content = next_content

                # Pass 2: If no category from marker, try manifest classification_overrides
                if category is None and classification_overrides and skill_name in classification_overrides:
                    category = classification_overrides[skill_name]
                    # Content is the full UserMessage text (Claude Code injects the raw
                    # SKILL.md contents when the "Base directory" marker is absent)
                    if next_user_content and next_user_content.strip():
                        # Skip tool result wrapper text (e.g. "Launching skill: pdf")
                        raw = next_user_content.strip()
                        # Only use content if it looks like skill markdown (has heading or frontmatter)
                        if raw.startswith("---") or raw.startswith("#") or len(raw) > 200:
                            content_text = raw
                            description = _parse_yaml_description(content_text)

                # Pass 3: Fallback for unclassified plugin-style skills (name contains ":")
                if category is None and ":" in skill_name:
                    category = "plugin_skill"
                    # Try to grab content from next UserMessage (skill body injected by Claude Code)
                    if not content_text and next_user_content and next_user_content.strip():
                        raw = next_user_content.strip()
                        if raw.startswith("---") or raw.startswith("#") or len(raw) > 200:
                            content_text = raw
                            description = _parse_yaml_description(content_text)

                # Persist custom_skill, user_command, and remote plugin_skill definitions.
                # Remote plugin skills need definitions for the "Inherit Skill" feature.
                is_remote = source_user_id and source_user_id != "__local__"
                if category not in ("custom_skill", "user_command"):
                    if not (category == "plugin_skill" and is_remote):
                        continue

                conn.execute(
                    """
                    INSERT INTO skill_definitions
                        (skill_name, source_user_id, source_machine_id, category,
                         content, base_directory, description, extracted_from_session,
                         updated_at)
                    VALUES (?, COALESCE(?, '__local__'), ?, ?, ?, ?, ?, ?, datetime('now'))
                    ON CONFLICT(skill_name, source_user_id) DO UPDATE SET
                        content = COALESCE(NULLIF(excluded.content, ''), skill_definitions.content),
                        base_directory = COALESCE(excluded.base_directory, skill_definitions.base_directory),
                        description = COALESCE(excluded.description, skill_definitions.description),
                        extracted_from_session = CASE
                            WHEN excluded.content IS NOT NULL AND excluded.content != ''
                                 AND (skill_definitions.content IS NULL OR skill_definitions.content = '')
                            THEN excluded.extracted_from_session
                            ELSE skill_definitions.extracted_from_session
                        END,
                        updated_at = CASE
                            WHEN excluded.content IS NOT NULL AND excluded.content != ''
                                 AND (skill_definitions.content IS NULL OR skill_definitions.content = '')
                            THEN datetime('now')
                            ELSE skill_definitions.updated_at
                        END
                    """,
                    (
                        skill_name,
                        source_user_id,
                        source_machine_id,
                        category,
                        content_text,
                        base_dir,
                        description,
                        session_uuid,
                    ),
                )

    except Exception as e:
        logger.warning(
            "Error extracting skill definitions from session %s: %s", session_uuid, e
        )


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
    from models.project import Project

    decoded = Project.decode_path(encoded_name)
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

    from models.project import Project

    if not candidate_paths:
        # Last resort: decode from encoded name (lossy for hyphenated paths)
        return Project.decode_path(encoded_name)

    # Find all paths whose encoding matches the encoded_name
    # (multiple paths can match due to lossy encoding: / and - both become -)
    matches = []
    for path in candidate_paths:
        if not path:
            continue
        if Project.encode_path(path) == encoded_name:
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

    # Pre-fetch already-known git identities to avoid redundant subprocess calls
    known_git_ids = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT encoded_name, git_identity FROM projects WHERE git_identity IS NOT NULL"
        ).fetchall()
    }

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
        display_name = Path(project_path).name if project_path else None

        # Detect git identity for cross-machine project matching (skip if already known)
        git_identity = known_git_ids.get(encoded_name)
        if git_identity is None and project_path:
            try:
                from utils.git import detect_git_identity
                git_identity = detect_git_identity(project_path)
            except Exception:
                pass

        # For remote-only projects (no project_path), derive display_name
        # from git_identity so it reads nicely (e.g. "claude-code-karma"
        # instead of the raw encoded_name).
        if display_name is None and git_identity:
            display_name = git_identity.split("/")[-1]
        if display_name is None:
            display_name = encoded_name

        conn.execute(
            """
            INSERT OR REPLACE INTO projects
                (encoded_name, project_path, slug, display_name, git_identity, session_count, last_activity)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (encoded_name, project_path, slug, display_name, git_identity, session_count, last_activity),
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
            from .connection import create_writer_connection

            conn = create_writer_connection()
            try:
                stats = await asyncio.to_thread(sync_all_projects, conn)
                logger.info("Periodic reindex complete: %s", stats)
            finally:
                conn.close()
        except Exception as e:
            logger.warning("Periodic reindex failed: %s", e)


def run_background_sync() -> None:
    """
    Run a full index sync in a background thread.

    Called during API startup to build/refresh the index without
    blocking request handling.
    """
    from .connection import create_writer_connection

    try:
        logger.info("Starting background index sync...")
        conn = create_writer_connection()
        try:
            stats = sync_all_projects(conn)
            logger.info("Background sync complete: %s", stats)
        finally:
            conn.close()
    except Exception as e:
        logger.error("Background sync failed: %s", e)
        # Still mark as ready so the API falls back to old code path
        _ready.set()
