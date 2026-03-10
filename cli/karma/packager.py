"""Session packager — collects project sessions into a staging directory."""

import json
import logging
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from karma.config import KARMA_BASE
from karma.manifest import SessionEntry, SyncManifest

logger = logging.getLogger(__name__)

MIN_FREE_BYTES = 10 * 1024 * 1024 * 1024  # 10 GiB


STALE_LIVE_SESSION_SECONDS = 30 * 60  # 30 minutes


def _get_live_session_uuids() -> set[str]:
    """Return UUIDs of sessions that are currently live (not yet ended).

    Reads ``~/.claude_karma/live-sessions/*.json`` written by Claude Code hooks.
    If hooks aren't configured (directory missing/empty), returns an empty set
    so all sessions pass through — backward compatible.

    Sessions idle for more than 30 minutes are considered stale (likely crashed
    without a SessionEnd hook) and are NOT excluded — their JSONL is stable
    enough to package.
    """
    live_dir = KARMA_BASE / "live-sessions"
    if not live_dir.is_dir():
        return set()

    now = datetime.now(timezone.utc)
    live_uuids: set[str] = set()
    for json_file in live_dir.glob("*.json"):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
            state = data.get("state", "")
            if state == "ENDED":
                continue

            # Skip sessions idle longer than the staleness threshold —
            # likely crashed without SessionEnd, safe to package.
            updated_at_str = data.get("updated_at")
            if updated_at_str:
                updated_at = datetime.fromisoformat(
                    updated_at_str.replace("Z", "+00:00")
                )
                if updated_at.tzinfo is None:
                    updated_at = updated_at.replace(tzinfo=timezone.utc)
                idle_seconds = (now - updated_at).total_seconds()
                if idle_seconds > STALE_LIVE_SESSION_SECONDS:
                    logger.debug(
                        "Live session %s idle %.0fs > %ds, treating as stale",
                        data.get("session_id", "?"),
                        idle_seconds,
                        STALE_LIVE_SESSION_SECONDS,
                    )
                    continue

            # Current active session UUID
            sid = data.get("session_id")
            if sid:
                live_uuids.add(sid)
            # All historical UUIDs for this slug (resumed sessions)
            for sid in data.get("session_ids", []):
                live_uuids.add(sid)
        except (json.JSONDecodeError, OSError):
            continue
    return live_uuids


def get_session_limit(team_session_limit: str, dest_path: Path) -> int | None:
    """Return max sessions to package, or None for unlimited.

    If disk has < 10 GiB free, force recent 100 regardless of setting.
    """
    try:
        free = shutil.disk_usage(dest_path).free
    except OSError:
        return 100  # Can't check disk → be conservative
    if free < MIN_FREE_BYTES:
        return 100  # safety cap

    limits = {"all": None, "recent_100": 100, "recent_10": 10}
    return limits.get(team_session_limit, None)


def _build_skill_classifications_from_db(
    session_uuids: list[str],
) -> dict[str, str]:
    """Query the metadata DB for skill/command classifications of given sessions.

    The DB already has correctly classified invocations (session_skills and
    session_commands tables). We extract all plugin colon-format names and
    their categories so the importing machine can use them as ground truth.

    Returns:
        Dict mapping invocation name → InvocationCategory string.
        E.g. {'feature-dev:feature-dev': 'plugin_command',
              'superpowers:brainstorming': 'plugin_skill'}
    """
    if not session_uuids:
        return {}

    try:
        from karma.db import get_connection

        conn = get_connection()
    except Exception:
        return {}

    classifications: dict[str, str] = {}
    placeholders = ",".join("?" * len(session_uuids))

    try:
        # Import classify_invocation from API (CLI adds API to sys.path via karma.db)
        try:
            from command_helpers import classify_invocation
            _classify = classify_invocation
        except ImportError:
            # Fallback: colon-format → plugin, otherwise unknown (will be reclassified on import)
            def _classify(name, source="skill_tool"):  # type: ignore[misc]
                return "plugin_skill" if ":" in name else "custom_skill"

        # Skills from session_skills table (all names, not just colon-format)
        rows = conn.execute(
            f"SELECT DISTINCT skill_name FROM session_skills WHERE session_uuid IN ({placeholders})",
            session_uuids,
        ).fetchall()
        for row in rows:
            classifications[row[0]] = _classify(row[0], source="skill_tool")

        # Commands from session_commands table (all names, not just colon-format)
        rows = conn.execute(
            f"SELECT DISTINCT command_name FROM session_commands WHERE session_uuid IN ({placeholders})",
            session_uuids,
        ).fetchall()
        for row in rows:
            classifications[row[0]] = _classify(row[0], source="slash_command")

        # Subagent skills
        rows = conn.execute(
            f"""SELECT DISTINCT ss.skill_name FROM subagent_skills ss
                JOIN subagent_invocations si ON ss.invocation_id = si.id
                WHERE si.session_uuid IN ({placeholders})""",
            session_uuids,
        ).fetchall()
        for row in rows:
            if row[0] not in classifications:
                classifications[row[0]] = _classify(row[0], source="skill_tool")

        # Subagent commands
        rows = conn.execute(
            f"""SELECT DISTINCT sc.command_name FROM subagent_commands sc
                JOIN subagent_invocations si ON sc.invocation_id = si.id
                WHERE si.session_uuid IN ({placeholders})""",
            session_uuids,
        ).fetchall()
        for row in rows:
            if row[0] not in classifications:
                classifications[row[0]] = _classify(row[0], source="slash_command")

    except Exception as e:
        logger.warning("Failed to extract skill classifications from DB: %s", e)
    finally:
        conn.close()

    return classifications


def _detect_git_branch(project_path: str) -> Optional[str]:
    """Detect the current git branch for a project/worktree path.

    Tries ``git rev-parse --abbrev-ref HEAD`` in the given directory.
    Returns None if git is not available, the path doesn't exist, or
    the repo is in detached-HEAD state.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return None
        branch = result.stdout.strip()
        if not branch or branch == "HEAD":
            return None
        return branch
    except (subprocess.SubprocessError, OSError):
        return None


def _extract_worktree_name(dir_name: str, main_dir_name: str) -> Optional[str]:
    """Extract human-readable worktree name from encoded dir name.

    Given main="-Users-jay-GitHub-karma" and
    dir="-Users-jay-GitHub-karma--claude-worktrees-feat-a",
    returns "feat-a".
    """
    markers = ["--claude-worktrees-", "-.claude-worktrees-", "--worktrees-", "-.worktrees-"]
    for marker in markers:
        idx = dir_name.find(marker)
        if idx > 0:
            return dir_name[idx + len(marker):]
    return None


class SessionPackager:
    """Discovers and packages Claude Code sessions for a project."""

    def __init__(
        self,
        project_dir: Path,
        user_id: str,
        machine_id: str,
        device_id: Optional[str] = None,
        project_path: str = "",
        extra_dirs: Optional[list[Path]] = None,
        team_name: Optional[str] = None,
        proj_suffix: Optional[str] = None,
    ):
        self.project_dir = Path(project_dir)
        self.user_id = user_id
        self.machine_id = machine_id
        self.device_id = device_id
        self.project_path = project_path or str(self.project_dir)

        self.extra_dirs = [Path(d) for d in (extra_dirs or [])]
        self.team_name = team_name
        self.proj_suffix = proj_suffix
        # ~/.claude/ base directory (parent of projects/{encoded}/)
        self._claude_base = self.project_dir.parent.parent

    def _discover_from_dir(
        self,
        directory: Path,
        worktree_name: Optional[str] = None,
        git_branch: Optional[str] = None,
    ) -> list[SessionEntry]:
        """Find session JSONL files in a single directory."""
        entries = []
        for jsonl_path in sorted(directory.glob("*.jsonl")):
            if jsonl_path.name.startswith("agent-"):
                continue
            try:
                stat = jsonl_path.stat()
            except (PermissionError, OSError) as e:
                logger.debug("Skipping unreadable file %s: %s", jsonl_path, e)
                continue
            if stat.st_size == 0:
                continue
            entries.append(
                SessionEntry(
                    uuid=jsonl_path.stem,
                    mtime=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                    size_bytes=stat.st_size,
                    worktree_name=worktree_name,
                    git_branch=git_branch,
                )
            )
        return entries

    def discover_sessions(self, exclude_live: bool = True) -> list[SessionEntry]:
        """Find all session JSONL files in the project and worktree directories.

        Args:
            exclude_live: If True (default), skip sessions that are currently
                live according to ``~/.claude_karma/live-sessions/``. When hooks
                aren't configured the live-sessions dir won't exist, so no
                sessions are excluded — backward compatible.
        """
        live_uuids = _get_live_session_uuids() if exclude_live else set()

        # Detect git branch for the main project directory
        main_branch = _detect_git_branch(self.project_path)
        entries = self._discover_from_dir(self.project_dir, git_branch=main_branch)

        for extra_dir in self.extra_dirs:
            if not extra_dir.is_dir():
                continue
            wt_name = _extract_worktree_name(extra_dir.name, self.project_dir.name)

            # For worktrees, construct the real worktree path from the project path
            wt_branch: Optional[str] = None
            if wt_name:
                wt_path = Path(self.project_path) / ".claude" / "worktrees" / wt_name
                if wt_path.is_dir():
                    wt_branch = _detect_git_branch(str(wt_path))
                if wt_branch is None:
                    # Fallback: try .worktrees/ (alternate location)
                    wt_path_alt = Path(self.project_path) / ".worktrees" / wt_name
                    if wt_path_alt.is_dir():
                        wt_branch = _detect_git_branch(str(wt_path_alt))

            entries.extend(
                self._discover_from_dir(extra_dir, worktree_name=wt_name, git_branch=wt_branch)
            )

        if live_uuids:
            before = len(entries)
            entries = [e for e in entries if e.uuid not in live_uuids]
            skipped = before - len(entries)
            if skipped:
                logger.info("Excluded %d live session(s) from packaging", skipped)

        return entries

    def _source_dir_for_session(self, entry: SessionEntry) -> Path:
        """Find the directory containing the session's JSONL file."""
        if (self.project_dir / f"{entry.uuid}.jsonl").exists():
            return self.project_dir
        for extra_dir in self.extra_dirs:
            if (extra_dir / f"{entry.uuid}.jsonl").exists():
                return extra_dir
        return self.project_dir  # fallback

    def package(self, staging_dir: Path, session_limit: str = "all") -> SyncManifest:
        """Copy session files into staging directory and create manifest."""
        sessions = self.discover_sessions()

        # Apply session limit (disk space aware)
        limit = get_session_limit(session_limit, staging_dir)
        if limit is not None and len(sessions) > limit:
            # Sort by mtime descending (most recent first), take top N
            sessions.sort(key=lambda s: s.mtime, reverse=True)
            sessions = sessions[:limit]

        sessions_dir = staging_dir / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        for entry in sessions:
            source_dir = self._source_dir_for_session(entry)

            # Copy JSONL file (skip if unchanged)
            src_jsonl = source_dir / f"{entry.uuid}.jsonl"
            dst_jsonl = sessions_dir / src_jsonl.name
            if not dst_jsonl.exists() or src_jsonl.stat().st_mtime > dst_jsonl.stat().st_mtime:
                try:
                    shutil.copy2(src_jsonl, dst_jsonl)
                except (PermissionError, OSError) as e:
                    logger.warning("Failed to copy %s: %s", src_jsonl, e)
                    continue

            # Copy associated directories (subagents, tool-results)
            assoc_dir = source_dir / entry.uuid
            if assoc_dir.is_dir():
                try:
                    shutil.copytree(
                        assoc_dir,
                        sessions_dir / entry.uuid,
                        dirs_exist_ok=True,
                    )
                except (PermissionError, OSError) as e:
                    logger.warning("Failed to copy directory %s: %s", assoc_dir, e)

        # Copy todos (glob pattern: {uuid}-*.json)
        todos_base = self._claude_base / "todos"
        if todos_base.is_dir():
            todos_staging = staging_dir / "todos"
            for session_entry in sessions:
                for todo_file in todos_base.glob(f"{session_entry.uuid}-*.json"):
                    todos_staging.mkdir(exist_ok=True)
                    try:
                        shutil.copy2(todo_file, todos_staging / todo_file.name)
                    except (PermissionError, OSError) as e:
                        logger.warning("Failed to copy %s: %s", todo_file, e)

        # Copy per-session directories (tasks, file-history)
        for resource_name in ("tasks", "file-history"):
            resource_base = self._claude_base / resource_name
            if resource_base.is_dir():
                resource_staging = staging_dir / resource_name
                for session_entry in sessions:
                    src_dir = resource_base / session_entry.uuid
                    if src_dir.is_dir():
                        resource_staging.mkdir(exist_ok=True)
                        try:
                            shutil.copytree(
                                src_dir,
                                resource_staging / session_entry.uuid,
                                dirs_exist_ok=True,
                            )
                        except (PermissionError, OSError) as e:
                            logger.warning("Failed to copy directory %s: %s", src_dir, e)

        # Copy debug logs (single file: {uuid}.txt)
        debug_base = self._claude_base / "debug"
        if debug_base.is_dir():
            debug_staging = staging_dir / "debug"
            for session_entry in sessions:
                debug_file = debug_base / f"{session_entry.uuid}.txt"
                if debug_file.is_file():
                    debug_staging.mkdir(exist_ok=True)
                    try:
                        shutil.copy2(debug_file, debug_staging / debug_file.name)
                    except (PermissionError, OSError) as e:
                        logger.warning("Failed to copy %s: %s", debug_file, e)

        # Detect git identity for cross-machine project matching
        from karma.sync import detect_git_identity

        git_id = detect_git_identity(self.project_path)

        # Build skill classifications from the metadata DB.
        # The exporting machine has already indexed sessions with correct
        # classifications — reuse that instead of re-scanning JSONL files.
        skill_classifications = _build_skill_classifications_from_db(
            [entry.uuid for entry in sessions]
        )

        # Build manifest
        manifest = SyncManifest(
            user_id=self.user_id,
            machine_id=self.machine_id,
            device_id=self.device_id,
            project_path=self.project_path,
            project_encoded=self.project_dir.name,
            session_count=len(sessions),
            sessions=sessions,

            git_identity=git_id,
            team_name=self.team_name,
            proj_suffix=self.proj_suffix,
            skill_classifications=skill_classifications,
        )

        manifest_path = staging_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest.model_dump(), indent=2) + "\n")

        # Ensure titles.json sidecar exists (best-effort)
        try:
            titles_path = staging_dir / "titles.json"
            if not titles_path.exists():
                from karma.titles_io import write_titles_bulk
                write_titles_bulk(titles_path, {})
        except Exception as e:
            logger.debug("titles.json sidecar creation failed (best-effort): %s", e)

        return manifest
