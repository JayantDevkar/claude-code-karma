"""Session packager — collects project sessions into a staging directory for IPFS upload."""

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from karma.manifest import SessionEntry, SyncManifest


class SessionPackager:
    """Discovers and packages Claude Code sessions for a project."""

    def __init__(
        self,
        project_dir: Path,
        user_id: str,
        machine_id: str,
        last_sync_cid: Optional[str] = None,
    ):
        self.project_dir = Path(project_dir)
        self.user_id = user_id
        self.machine_id = machine_id
        self.last_sync_cid = last_sync_cid

    def discover_sessions(self) -> list[SessionEntry]:
        """Find all session JSONL files in the project directory."""
        entries = []
        for jsonl_path in sorted(self.project_dir.glob("*.jsonl")):
            # Skip standalone agent files
            if jsonl_path.name.startswith("agent-"):
                continue
            stat = jsonl_path.stat()
            entries.append(
                SessionEntry(
                    uuid=jsonl_path.stem,
                    mtime=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                    size_bytes=stat.st_size,
                )
            )
        return entries

    def package(self, staging_dir: Path) -> SyncManifest:
        """Copy session files into staging directory and create manifest."""
        sessions = self.discover_sessions()

        # Create staging structure
        sessions_dir = staging_dir / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)

        for entry in sessions:
            # Copy JSONL file
            src_jsonl = self.project_dir / f"{entry.uuid}.jsonl"
            shutil.copy2(src_jsonl, sessions_dir / src_jsonl.name)

            # Copy associated directories (subagents, tool-results)
            assoc_dir = self.project_dir / entry.uuid
            if assoc_dir.is_dir():
                shutil.copytree(
                    assoc_dir,
                    sessions_dir / entry.uuid,
                    dirs_exist_ok=True,
                )

        # Copy todos if they exist
        todos_base = self.project_dir.parent.parent / "todos"
        if todos_base.is_dir():
            todos_staging = staging_dir / "todos"
            for session_entry in sessions:
                for todo_file in todos_base.glob(f"{session_entry.uuid}-*.json"):
                    todos_staging.mkdir(exist_ok=True)
                    shutil.copy2(todo_file, todos_staging / todo_file.name)

        # Build manifest
        manifest = SyncManifest(
            user_id=self.user_id,
            machine_id=self.machine_id,
            project_path=str(self.project_dir),
            project_encoded=self.project_dir.name,
            session_count=len(sessions),
            sessions=sessions,
            previous_cid=self.last_sync_cid,
        )

        # Write manifest to staging
        manifest_path = staging_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest.model_dump(), indent=2) + "\n")

        return manifest
