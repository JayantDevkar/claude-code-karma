"""Session packager — collects project sessions into a staging directory."""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from karma.manifest import SessionEntry, SyncManifest


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
        project_path: str = "",
        last_sync_cid: Optional[str] = None,
        extra_dirs: Optional[list[Path]] = None,
        team_name: Optional[str] = None,
        proj_suffix: Optional[str] = None,
    ):
        self.project_dir = Path(project_dir)
        self.user_id = user_id
        self.machine_id = machine_id
        self.project_path = project_path or str(self.project_dir)
        self.last_sync_cid = last_sync_cid
        self.extra_dirs = [Path(d) for d in (extra_dirs or [])]
        self.team_name = team_name
        self.proj_suffix = proj_suffix
        # ~/.claude/ base directory (parent of projects/{encoded}/)
        self._claude_base = self.project_dir.parent.parent

    def _discover_from_dir(
        self, directory: Path, worktree_name: Optional[str] = None
    ) -> list[SessionEntry]:
        """Find session JSONL files in a single directory."""
        entries = []
        for jsonl_path in sorted(directory.glob("*.jsonl")):
            if jsonl_path.name.startswith("agent-"):
                continue
            stat = jsonl_path.stat()
            if stat.st_size == 0:
                continue
            entries.append(
                SessionEntry(
                    uuid=jsonl_path.stem,
                    mtime=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                    size_bytes=stat.st_size,
                    worktree_name=worktree_name,
                )
            )
        return entries

    def discover_sessions(self) -> list[SessionEntry]:
        """Find all session JSONL files in the project and worktree directories."""
        entries = self._discover_from_dir(self.project_dir)

        for extra_dir in self.extra_dirs:
            if not extra_dir.is_dir():
                continue
            wt_name = _extract_worktree_name(extra_dir.name, self.project_dir.name)
            entries.extend(self._discover_from_dir(extra_dir, worktree_name=wt_name))

        return entries

    def _source_dir_for_session(self, entry: SessionEntry) -> Path:
        """Find the directory containing the session's JSONL file."""
        if (self.project_dir / f"{entry.uuid}.jsonl").exists():
            return self.project_dir
        for extra_dir in self.extra_dirs:
            if (extra_dir / f"{entry.uuid}.jsonl").exists():
                return extra_dir
        return self.project_dir  # fallback

    def package(self, staging_dir: Path) -> SyncManifest:
        """Copy session files into staging directory and create manifest."""
        sessions = self.discover_sessions()

        sessions_dir = staging_dir / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        for entry in sessions:
            source_dir = self._source_dir_for_session(entry)

            # Copy JSONL file (skip if unchanged)
            src_jsonl = source_dir / f"{entry.uuid}.jsonl"
            dst_jsonl = sessions_dir / src_jsonl.name
            if not dst_jsonl.exists() or src_jsonl.stat().st_mtime > dst_jsonl.stat().st_mtime:
                shutil.copy2(src_jsonl, dst_jsonl)

            # Copy associated directories (subagents, tool-results)
            assoc_dir = source_dir / entry.uuid
            if assoc_dir.is_dir():
                shutil.copytree(
                    assoc_dir,
                    sessions_dir / entry.uuid,
                    dirs_exist_ok=True,
                )

        # Copy todos (glob pattern: {uuid}-*.json)
        todos_base = self._claude_base / "todos"
        if todos_base.is_dir():
            todos_staging = staging_dir / "todos"
            for session_entry in sessions:
                for todo_file in todos_base.glob(f"{session_entry.uuid}-*.json"):
                    todos_staging.mkdir(exist_ok=True)
                    shutil.copy2(todo_file, todos_staging / todo_file.name)

        # Copy per-session directories (tasks, file-history)
        for resource_name in ("tasks", "file-history"):
            resource_base = self._claude_base / resource_name
            if resource_base.is_dir():
                resource_staging = staging_dir / resource_name
                for session_entry in sessions:
                    src_dir = resource_base / session_entry.uuid
                    if src_dir.is_dir():
                        resource_staging.mkdir(exist_ok=True)
                        shutil.copytree(
                            src_dir,
                            resource_staging / session_entry.uuid,
                            dirs_exist_ok=True,
                        )

        # Copy debug logs (single file: {uuid}.txt)
        debug_base = self._claude_base / "debug"
        if debug_base.is_dir():
            debug_staging = staging_dir / "debug"
            for session_entry in sessions:
                debug_file = debug_base / f"{session_entry.uuid}.txt"
                if debug_file.is_file():
                    debug_staging.mkdir(exist_ok=True)
                    shutil.copy2(debug_file, debug_staging / debug_file.name)

        # Detect git identity for cross-machine project matching
        from karma.sync import detect_git_identity

        git_id = detect_git_identity(self.project_path)

        # Build manifest
        manifest = SyncManifest(
            user_id=self.user_id,
            machine_id=self.machine_id,
            project_path=self.project_path,
            project_encoded=self.project_dir.name,
            session_count=len(sessions),
            sessions=sessions,
            previous_cid=self.last_sync_cid,
            git_identity=git_id,
            team_name=self.team_name,
            proj_suffix=self.proj_suffix,
        )

        manifest_path = staging_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest.model_dump(), indent=2) + "\n")

        return manifest
