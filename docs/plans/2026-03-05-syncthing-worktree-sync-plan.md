# Syncthing Worktree-Aware Session Sync — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the CLI packager and watcher discover and sync worktree sessions alongside main project sessions, so remote teammates see the complete picture of all work happening on a project.

**Architecture:** Extract worktree discovery logic from the API's `desktop_sessions.py` into a shared helper in the CLI. The `SessionPackager` accepts multiple source directories. The watcher monitors worktree dirs dynamically. `SessionEntry` gains optional metadata fields (`worktree_name`, `git_branch`) so receivers can understand session context. Incremental packaging avoids redundant copies.

**Tech Stack:** Python 3.9+, click (CLI), watchdog (filesystem events), Pydantic 2.x (models), pytest (testing)

**Prior plan:** `docs/plans/2026-03-03-syncthing-session-sync-plan.md` (implements the base Syncthing sync — this plan extends it)

**Key insight:** The API indexer (`api/db/indexer.py:86-158`) already solves worktree→real project mapping via `api/services/desktop_sessions.py`. The CLI needs a lightweight version of the same logic, without importing the API.

---

## Task 1: Add worktree discovery to the CLI

The CLI needs `is_worktree_project()` and `find_worktree_dirs()` without depending on the API module. This is a pure-function utility — no API imports, no settings object.

**Files:**
- Create: `cli/karma/worktree_discovery.py`
- Create: `cli/tests/test_worktree_discovery.py`

**Step 1: Write failing tests**

```python
# cli/tests/test_worktree_discovery.py
"""Tests for worktree discovery."""

from pathlib import Path
import pytest
from karma.worktree_discovery import is_worktree_dir, find_worktree_dirs


class TestIsWorktreeDir:
    def test_cli_worktree_pattern(self):
        assert is_worktree_dir(
            "-Users-jay-GitHub-karma--claude-worktrees-feature-x"
        ) is True

    def test_superpowers_worktree_pattern(self):
        assert is_worktree_dir(
            "-Users-jay-GitHub-karma--worktrees-feature-y"
        ) is True

    def test_desktop_worktree_pattern(self):
        assert is_worktree_dir(
            "-Users-jay--claude-worktrees-karma-focused-jepsen"
        ) is True

    def test_normal_project_not_worktree(self):
        assert is_worktree_dir(
            "-Users-jay-Documents-GitHub-claude-karma"
        ) is False

    def test_empty_string(self):
        assert is_worktree_dir("") is False


class TestFindWorktreeDirs:
    def test_finds_cli_worktrees(self, tmp_path):
        """CLI worktrees: {project}/.claude/worktrees/{name}"""
        projects_dir = tmp_path / "projects"
        main = projects_dir / "-Users-jay-GitHub-karma"
        wt1 = projects_dir / "-Users-jay-GitHub-karma--claude-worktrees-feat-a"
        wt2 = projects_dir / "-Users-jay-GitHub-karma--claude-worktrees-feat-b"
        for d in (main, wt1, wt2):
            d.mkdir(parents=True)
            (d / "session.jsonl").write_text('{"type":"user"}\n')
        result = find_worktree_dirs(
            "-Users-jay-GitHub-karma", projects_dir
        )
        assert len(result) == 2
        assert wt1 in result
        assert wt2 in result

    def test_finds_superpowers_worktrees(self, tmp_path):
        projects_dir = tmp_path / "projects"
        main = projects_dir / "-Users-jay-GitHub-karma"
        wt = projects_dir / "-Users-jay-GitHub-karma--worktrees-fix-bug"
        for d in (main, wt):
            d.mkdir(parents=True)
        result = find_worktree_dirs(
            "-Users-jay-GitHub-karma", projects_dir
        )
        assert wt in result

    def test_ignores_unrelated_projects(self, tmp_path):
        projects_dir = tmp_path / "projects"
        main = projects_dir / "-Users-jay-GitHub-karma"
        unrelated = projects_dir / "-Users-jay-GitHub-other--claude-worktrees-x"
        for d in (main, unrelated):
            d.mkdir(parents=True)
        result = find_worktree_dirs(
            "-Users-jay-GitHub-karma", projects_dir
        )
        assert len(result) == 0

    def test_returns_empty_when_no_worktrees(self, tmp_path):
        projects_dir = tmp_path / "projects"
        main = projects_dir / "-Users-jay-GitHub-karma"
        main.mkdir(parents=True)
        result = find_worktree_dirs(
            "-Users-jay-GitHub-karma", projects_dir
        )
        assert result == []

    def test_returns_empty_when_projects_dir_missing(self, tmp_path):
        result = find_worktree_dirs(
            "-Users-jay-GitHub-karma", tmp_path / "nonexistent"
        )
        assert result == []
```

**Step 2: Run tests to verify they fail**

Run: `cd cli && pytest tests/test_worktree_discovery.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'karma.worktree_discovery'`

**Step 3: Implement worktree discovery**

```python
# cli/karma/worktree_discovery.py
"""Worktree directory discovery for CLI packager.

Detects worktree project directories that belong to a given main project.
This is a lightweight port of the logic in api/services/desktop_sessions.py,
without any API dependencies.

Worktree patterns (all encoded by Claude Code):
  1. CLI worktrees:    {project}/.claude/worktrees/{name}
     Encoded:          {project_encoded}--claude-worktrees-{name}
  2. Superpowers:      {project}/.worktrees/{name}
     Encoded:          {project_encoded}--worktrees-{name}
  3. Desktop worktrees: ~/.claude-worktrees/{project}/{name}
     Encoded:          -Users-{user}--claude-worktrees-{project}-{name}
     (These DON'T share a prefix with the main project — handled separately)
"""

from pathlib import Path

# Markers in encoded names that separate project prefix from worktree suffix.
_WORKTREE_MARKERS = [
    "--claude-worktrees-",
    "-.claude-worktrees-",
    "--worktrees-",
    "-.worktrees-",
]


def is_worktree_dir(encoded_name: str) -> bool:
    """Check if an encoded project directory name is a worktree."""
    if not encoded_name:
        return False
    if "-claude-worktrees-" in encoded_name:
        return True
    if "--worktrees-" in encoded_name or "-.worktrees-" in encoded_name:
        return True
    return False


def _get_worktree_prefix(encoded_name: str) -> str | None:
    """Extract the main project prefix from a worktree encoded name.

    Returns the prefix before the worktree marker, or None if not a
    prefix-style worktree (e.g., Desktop worktrees don't share a prefix).
    """
    for marker in _WORKTREE_MARKERS:
        idx = encoded_name.find(marker)
        if idx > 0:
            prefix = encoded_name[:idx]
            if prefix.startswith("-") and len(prefix) > 1:
                return prefix
    return None


def find_worktree_dirs(
    main_encoded_name: str, projects_dir: Path
) -> list[Path]:
    """Find all worktree directories that belong to a main project.

    Scans projects_dir for directories whose encoded name starts with
    the main project's encoded name followed by a worktree marker.

    Args:
        main_encoded_name: The main project's encoded directory name
            (e.g., "-Users-jay-GitHub-karma").
        projects_dir: Path to ~/.claude/projects/

    Returns:
        List of Path objects for matching worktree directories.
    """
    if not projects_dir.is_dir():
        return []

    matches = []
    for entry in projects_dir.iterdir():
        if not entry.is_dir():
            continue
        if entry.name == main_encoded_name:
            continue  # skip the main project itself
        if not is_worktree_dir(entry.name):
            continue
        # Check if this worktree's prefix matches the main project
        prefix = _get_worktree_prefix(entry.name)
        if prefix == main_encoded_name:
            matches.append(entry)

    return sorted(matches)
```

**Step 4: Run tests to verify they pass**

Run: `cd cli && pytest tests/test_worktree_discovery.py -v`
Expected: All 9 tests PASS

**Step 5: Commit**

```bash
git add cli/karma/worktree_discovery.py cli/tests/test_worktree_discovery.py
git commit -m "feat(cli): add worktree directory discovery module

Lightweight port of API's worktree detection for CLI packager.
Finds CLI, superpowers, and Desktop worktree dirs by encoded name prefix."
```

---

## Task 2: Extend SessionEntry with worktree metadata

Add `worktree_name` and `git_branch` to `SessionEntry` so receivers know which worktree/branch a session came from.

**Files:**
- Modify: `cli/karma/manifest.py:8-14` (SessionEntry class)
- Modify: `cli/tests/test_packager.py` (add tests)

**Step 1: Write failing tests**

Add to `cli/tests/test_packager.py`:

```python
class TestSessionEntryMetadata:
    def test_session_entry_default_no_worktree(self):
        from karma.manifest import SessionEntry
        entry = SessionEntry(uuid="abc", mtime="2026-01-01T00:00:00Z", size_bytes=100)
        assert entry.worktree_name is None
        assert entry.git_branch is None

    def test_session_entry_with_worktree(self):
        from karma.manifest import SessionEntry
        entry = SessionEntry(
            uuid="abc",
            mtime="2026-01-01T00:00:00Z",
            size_bytes=100,
            worktree_name="syncthing-sync-design",
            git_branch="worktree-syncthing-sync-design",
        )
        assert entry.worktree_name == "syncthing-sync-design"
        assert entry.git_branch == "worktree-syncthing-sync-design"

    def test_session_entry_worktree_in_dump(self):
        from karma.manifest import SessionEntry
        entry = SessionEntry(
            uuid="abc",
            mtime="2026-01-01T00:00:00Z",
            size_bytes=100,
            worktree_name="feat-x",
        )
        data = entry.model_dump()
        assert data["worktree_name"] == "feat-x"
        assert data["git_branch"] is None
```

**Step 2: Run tests to verify they fail**

Run: `cd cli && pytest tests/test_packager.py::TestSessionEntryMetadata -v`
Expected: FAIL — `TypeError: unexpected keyword argument 'worktree_name'`

**Step 3: Add fields to SessionEntry**

In `cli/karma/manifest.py`, modify the `SessionEntry` class:

```python
class SessionEntry(BaseModel):
    """Metadata for a single synced session."""

    model_config = ConfigDict(frozen=True)

    uuid: str
    mtime: str = Field(..., description="ISO timestamp of session file modification time")
    size_bytes: int
    worktree_name: Optional[str] = Field(default=None, description="Worktree name if session is from a worktree")
    git_branch: Optional[str] = Field(default=None, description="Git branch the session was on")
```

Add `Optional` import at the top of the file if not already present:

```python
from typing import Optional
```

**Step 4: Run tests to verify they pass**

Run: `cd cli && pytest tests/test_packager.py -v`
Expected: All tests PASS (existing + new)

**Step 5: Commit**

```bash
git add cli/karma/manifest.py cli/tests/test_packager.py
git commit -m "feat(cli): add worktree_name and git_branch to SessionEntry

Allows manifest to carry per-session metadata about which worktree
and branch a session came from, for richer remote viewing."
```

---

## Task 3: Make SessionPackager accept multiple source directories

The packager currently only globs one `project_dir`. Extend it to accept additional worktree dirs and tag sessions with their origin.

**Files:**
- Modify: `cli/karma/packager.py`
- Modify: `cli/tests/test_packager.py`

**Step 1: Write failing tests**

Add to `cli/tests/test_packager.py`:

```python
@pytest.fixture
def mock_project_with_worktree(tmp_path: Path) -> dict:
    """Create a main project dir + one worktree dir."""
    projects_dir = tmp_path / ".claude" / "projects"

    # Main project
    main_dir = projects_dir / "-Users-jay-GitHub-karma"
    main_dir.mkdir(parents=True)
    (main_dir / "session-main-001.jsonl").write_text(
        '{"type":"user","message":{"role":"user","content":"hello"}}\n'
    )

    # Worktree
    wt_dir = projects_dir / "-Users-jay-GitHub-karma--claude-worktrees-feat-a"
    wt_dir.mkdir(parents=True)
    (wt_dir / "session-wt-001.jsonl").write_text(
        '{"type":"user","message":{"role":"user","content":"worktree work"}}\n'
    )
    # Worktree session with subagent
    (wt_dir / "session-wt-002.jsonl").write_text(
        '{"type":"user","message":{"role":"user","content":"more work"}}\n'
    )
    sub_dir = wt_dir / "session-wt-002" / "subagents"
    sub_dir.mkdir(parents=True)
    (sub_dir / "agent-x.jsonl").write_text('{"type":"agent"}\n')

    return {
        "main_dir": main_dir,
        "wt_dir": wt_dir,
        "projects_dir": projects_dir,
    }


class TestPackagerWithWorktrees:
    def test_discover_includes_worktree_sessions(self, mock_project_with_worktree):
        dirs = mock_project_with_worktree
        packager = SessionPackager(
            project_dir=dirs["main_dir"],
            user_id="jay",
            machine_id="mac",
            extra_dirs=[dirs["wt_dir"]],
        )
        sessions = packager.discover_sessions()
        uuids = {s.uuid for s in sessions}
        assert "session-main-001" in uuids
        assert "session-wt-001" in uuids
        assert "session-wt-002" in uuids
        assert len(sessions) == 3

    def test_worktree_sessions_tagged_with_worktree_name(self, mock_project_with_worktree):
        dirs = mock_project_with_worktree
        packager = SessionPackager(
            project_dir=dirs["main_dir"],
            user_id="jay",
            machine_id="mac",
            extra_dirs=[dirs["wt_dir"]],
        )
        sessions = packager.discover_sessions()
        wt_sessions = [s for s in sessions if s.worktree_name is not None]
        assert len(wt_sessions) == 2
        assert all(s.worktree_name == "feat-a" for s in wt_sessions)

    def test_package_copies_worktree_subagents(self, mock_project_with_worktree, tmp_path):
        dirs = mock_project_with_worktree
        staging = tmp_path / "staging"
        packager = SessionPackager(
            project_dir=dirs["main_dir"],
            user_id="jay",
            machine_id="mac",
            extra_dirs=[dirs["wt_dir"]],
        )
        packager.package(staging_dir=staging)
        assert (staging / "sessions" / "session-wt-002" / "subagents" / "agent-x.jsonl").exists()

    def test_manifest_counts_all_sessions(self, mock_project_with_worktree, tmp_path):
        dirs = mock_project_with_worktree
        staging = tmp_path / "staging"
        packager = SessionPackager(
            project_dir=dirs["main_dir"],
            user_id="jay",
            machine_id="mac",
            extra_dirs=[dirs["wt_dir"]],
        )
        manifest = packager.package(staging_dir=staging)
        assert manifest.session_count == 3

    def test_no_extra_dirs_works_like_before(self, mock_claude_project, tmp_path):
        """Backward compat: no extra_dirs = original behavior."""
        staging = tmp_path / "staging"
        packager = SessionPackager(
            project_dir=mock_claude_project,
            user_id="alice",
            machine_id="test-mac",
        )
        manifest = packager.package(staging_dir=staging)
        assert manifest.session_count == 2
```

**Step 2: Run tests to verify they fail**

Run: `cd cli && pytest tests/test_packager.py::TestPackagerWithWorktrees -v`
Expected: FAIL — `TypeError: unexpected keyword argument 'extra_dirs'`

**Step 3: Modify SessionPackager**

Replace `cli/karma/packager.py` with:

```python
"""Session packager -- collects project sessions into a staging directory."""

import json
import re
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
    ):
        self.project_dir = Path(project_dir)
        self.user_id = user_id
        self.machine_id = machine_id
        self.project_path = project_path or str(self.project_dir)
        self.last_sync_cid = last_sync_cid
        self.extra_dirs = [Path(d) for d in (extra_dirs or [])]

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

            # Copy JSONL file
            src_jsonl = source_dir / f"{entry.uuid}.jsonl"
            shutil.copy2(src_jsonl, sessions_dir / src_jsonl.name)

            # Copy associated directories (subagents, tool-results)
            assoc_dir = source_dir / entry.uuid
            if assoc_dir.is_dir():
                shutil.copytree(
                    assoc_dir,
                    sessions_dir / entry.uuid,
                    dirs_exist_ok=True,
                )

        # Copy todos if they exist (from main project dir's parent)
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
            project_path=self.project_path,
            project_encoded=self.project_dir.name,
            session_count=len(sessions),
            sessions=sessions,
            previous_cid=self.last_sync_cid,
        )

        manifest_path = staging_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest.model_dump(), indent=2) + "\n")

        return manifest
```

**Step 4: Run ALL packager tests**

Run: `cd cli && pytest tests/test_packager.py -v`
Expected: All tests PASS (existing + new)

**Step 5: Commit**

```bash
git add cli/karma/packager.py cli/tests/test_packager.py
git commit -m "feat(cli): packager discovers sessions from worktree dirs

SessionPackager accepts extra_dirs for worktree directories.
Sessions from worktrees are tagged with worktree_name in the manifest."
```

---

## Task 4: Wire worktree discovery into `karma watch`

The `watch` command needs to auto-discover worktree dirs for each project and pass them to the packager. New worktree dirs appearing mid-watch should be picked up.

**Files:**
- Modify: `cli/karma/main.py` (watch command, ~lines 465-547)
- Modify: `cli/tests/test_cli_syncthing.py` (add watch worktree test)

**Step 1: Write failing test**

Add to `cli/tests/test_cli_syncthing.py`:

```python
from unittest.mock import patch, MagicMock
from pathlib import Path

def test_watch_discovers_worktree_dirs(tmp_path):
    """karma watch should find worktree dirs and pass them to packager."""
    from karma.worktree_discovery import find_worktree_dirs

    projects_dir = tmp_path / ".claude" / "projects"
    main = projects_dir / "-Users-jay-GitHub-karma"
    wt = projects_dir / "-Users-jay-GitHub-karma--claude-worktrees-feat-a"
    main.mkdir(parents=True)
    wt.mkdir(parents=True)
    (main / "s1.jsonl").write_text('{"type":"user"}\n')
    (wt / "s2.jsonl").write_text('{"type":"user"}\n')

    dirs = find_worktree_dirs("-Users-jay-GitHub-karma", projects_dir)
    assert len(dirs) == 1
    assert dirs[0] == wt
```

**Step 2: Run test to verify it passes** (this tests the discovery itself, which we built in Task 1)

Run: `cd cli && pytest tests/test_cli_syncthing.py::test_watch_discovers_worktree_dirs -v`
Expected: PASS

**Step 3: Modify the watch command in `cli/karma/main.py`**

Replace the watch command's inner loop (lines ~506-536) with worktree-aware logic:

```python
# In the watch command, replace the watcher setup loop with:

    watchers = []
    for proj_name, proj in team_cfg.projects.items():
        claude_dir = Path.home() / ".claude" / "projects" / proj.encoded_name
        if not claude_dir.is_dir():
            click.echo(f"  Skipping '{proj_name}': Claude dir not found ({claude_dir})")
            continue

        # Discover worktree dirs for this project
        from karma.worktree_discovery import find_worktree_dirs
        projects_dir = Path.home() / ".claude" / "projects"
        wt_dirs = find_worktree_dirs(proj.encoded_name, projects_dir)
        if wt_dirs:
            click.echo(f"  Found {len(wt_dirs)} worktree dir(s) for '{proj_name}'")

        outbox = KARMA_BASE / "remote-sessions" / config.user_id / proj.encoded_name

        def make_package_fn(cd=claude_dir, ob=outbox, pn=proj_name, wd=wt_dirs):
            def package():
                # Re-discover worktrees each time (new ones may appear)
                current_wt_dirs = find_worktree_dirs(proj.encoded_name, projects_dir)
                packager = SessionPackager(
                    project_dir=cd,
                    user_id=config.user_id,
                    machine_id=config.machine_id,
                    project_path=proj.path,
                    extra_dirs=current_wt_dirs,
                )
                ob.mkdir(parents=True, exist_ok=True)
                packager.package(staging_dir=ob)
                click.echo(f"  Packaged '{pn}' -> {ob} ({len(current_wt_dirs)} worktrees)")
            return package

        package_fn = make_package_fn()

        # Watch main project dir
        watcher = SessionWatcher(
            watch_dir=claude_dir,
            package_fn=package_fn,
        )
        watcher.start()
        watchers.append(watcher)
        click.echo(f"  Watching: {proj_name} ({claude_dir})")

        # Also watch each worktree dir
        for wt_dir in wt_dirs:
            wt_watcher = SessionWatcher(
                watch_dir=wt_dir,
                package_fn=package_fn,
            )
            wt_watcher.start()
            watchers.append(wt_watcher)
            wt_name = wt_dir.name.split("--claude-worktrees-")[-1] if "--claude-worktrees-" in wt_dir.name else wt_dir.name
            click.echo(f"  Watching worktree: {wt_name} ({wt_dir})")
```

**Step 4: Run existing CLI tests to verify no regressions**

Run: `cd cli && pytest tests/test_cli_syncthing.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add cli/karma/main.py cli/tests/test_cli_syncthing.py
git commit -m "feat(cli): karma watch discovers and monitors worktree dirs

Watch command auto-discovers worktree directories for each project
and starts watchers for them. Re-discovers on each package cycle
so new worktrees are picked up dynamically."
```

---

## Task 5: Add `karma status` sync gap visibility

Show local vs packaged vs worktree session counts so users can see if they're out of sync.

**Files:**
- Modify: `cli/karma/main.py` (status command, ~lines 550-580)
- Modify: `cli/tests/test_cli_syncthing.py`

**Step 1: Write failing test**

```python
# Add to cli/tests/test_cli_syncthing.py
from click.testing import CliRunner
from karma.main import cli


def test_status_shows_worktree_counts(tmp_path, monkeypatch):
    """karma status should show worktree session counts."""
    # Create config
    config_data = {
        "user_id": "jay",
        "machine_id": "test-mac",
        "projects": {},
        "team": {},
        "ipfs_api": "http://127.0.0.1:5001",
        "teams": {
            "my-team": {
                "backend": "syncthing",
                "projects": {
                    "karma": {
                        "path": "/Users/jay/karma",
                        "encoded_name": "-Users-jay-karma",
                        "last_sync_cid": None,
                        "last_sync_at": None,
                    }
                },
                "ipfs_members": {},
                "syncthing_members": {"bob": {"syncthing_device_id": "TESTID"}},
                "owner_device_id": None,
                "owner_ipns_key": None,
            }
        },
        "syncthing": {"api_url": "http://127.0.0.1:8384", "api_key": None, "device_id": None},
    }

    import json
    config_path = tmp_path / "sync-config.json"
    config_path.write_text(json.dumps(config_data))
    monkeypatch.setattr("karma.config.SYNC_CONFIG_PATH", config_path)

    # Create fake project dir with sessions
    projects_dir = tmp_path / ".claude" / "projects"
    main_dir = projects_dir / "-Users-jay-karma"
    main_dir.mkdir(parents=True)
    (main_dir / "s1.jsonl").write_text('{"type":"user"}\n')
    (main_dir / "s2.jsonl").write_text('{"type":"user"}\n')

    # Create worktree dir
    wt_dir = projects_dir / "-Users-jay-karma--claude-worktrees-feat-x"
    wt_dir.mkdir(parents=True)
    (wt_dir / "s3.jsonl").write_text('{"type":"user"}\n')

    monkeypatch.setattr("karma.main.Path.home", lambda: tmp_path)

    runner = CliRunner()
    result = runner.invoke(cli, ["status"])
    assert result.exit_code == 0
    # Should mention worktree count
    assert "worktree" in result.output.lower() or "2" in result.output
```

**Step 2: Run to verify it fails**

Run: `cd cli && pytest tests/test_cli_syncthing.py::test_status_shows_worktree_counts -v`
Expected: FAIL (status command doesn't show worktree info yet)

**Step 3: Enhance the status command**

In `cli/karma/main.py`, replace the `status` command body with:

```python
@cli.command()
def status():
    """Show sync status for all teams."""
    from karma.worktree_discovery import find_worktree_dirs

    config = require_config()

    click.echo(f"User: {config.user_id} ({config.machine_id})")

    if not config.teams and not config.projects:
        click.echo("No teams or projects configured.")
        return

    # Legacy flat projects
    if config.projects:
        click.echo(f"\nLegacy projects (IPFS):")
        for name, proj in config.projects.items():
            sync_info = f"last sync: {proj.last_sync_at}" if proj.last_sync_at else "never synced"
            click.echo(f"  {name}: {proj.path} ({sync_info})")

    projects_dir = Path.home() / ".claude" / "projects"

    # Per-team
    for team_name, team_cfg in config.teams.items():
        click.echo(f"\n{team_name} ({team_cfg.backend}):")
        if not team_cfg.projects:
            click.echo("  No projects")
        for proj_name, proj in team_cfg.projects.items():
            last = proj.last_sync_at or "never"
            claude_dir = projects_dir / proj.encoded_name

            # Count local sessions
            local_count = 0
            if claude_dir.is_dir():
                local_count = sum(
                    1 for f in claude_dir.glob("*.jsonl")
                    if not f.name.startswith("agent-") and f.stat().st_size > 0
                )

            # Count worktree sessions
            wt_dirs = find_worktree_dirs(proj.encoded_name, projects_dir)
            wt_count = 0
            for wd in wt_dirs:
                wt_count += sum(
                    1 for f in wd.glob("*.jsonl")
                    if not f.name.startswith("agent-") and f.stat().st_size > 0
                )

            # Count packaged sessions
            outbox = KARMA_BASE / "remote-sessions" / config.user_id / proj.encoded_name / "sessions"
            packaged_count = 0
            if outbox.is_dir():
                packaged_count = sum(1 for f in outbox.glob("*.jsonl") if not f.name.startswith("agent-"))

            total_local = local_count + wt_count
            gap = total_local - packaged_count

            click.echo(f"  {proj_name}: {proj.path} (last: {last})")
            click.echo(f"    Local: {local_count} sessions + {wt_count} worktree ({len(wt_dirs)} dirs) = {total_local}")
            click.echo(f"    Packaged: {packaged_count}  {'(up to date)' if gap <= 0 else f'({gap} behind)'}")

        if team_cfg.members:
            click.echo(f"  Members: {', '.join(team_cfg.members.keys())}")
```

**Step 4: Run tests**

Run: `cd cli && pytest tests/test_cli_syncthing.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add cli/karma/main.py cli/tests/test_cli_syncthing.py
git commit -m "feat(cli): karma status shows worktree counts and sync gap

Status command now shows local, worktree, and packaged session counts
per project, making it easy to see if the outbox is stale."
```

---

## Task 6: Incremental packaging (avoid full re-copy)

Currently `package()` copies all sessions every time. Add mtime tracking to skip unchanged files.

**Files:**
- Modify: `cli/karma/packager.py`
- Modify: `cli/tests/test_packager.py`

**Step 1: Write failing test**

```python
# Add to cli/tests/test_packager.py

class TestIncrementalPackaging:
    def test_skip_unchanged_sessions(self, mock_claude_project, tmp_path):
        """Second package should skip files that haven't changed."""
        staging = tmp_path / "staging"
        packager = SessionPackager(
            project_dir=mock_claude_project,
            user_id="alice",
            machine_id="test-mac",
        )

        # First package
        manifest1 = packager.package(staging_dir=staging)
        assert manifest1.session_count == 2

        # Record mtime of a copied file
        copied = staging / "sessions" / "session-uuid-001.jsonl"
        mtime_after_first = copied.stat().st_mtime

        import time
        time.sleep(0.05)  # ensure mtime difference is detectable

        # Second package (no source changes)
        manifest2 = packager.package(staging_dir=staging)
        assert manifest2.session_count == 2

        # File should NOT have been re-copied (mtime unchanged)
        mtime_after_second = copied.stat().st_mtime
        assert mtime_after_first == mtime_after_second

    def test_repackage_modified_session(self, mock_claude_project, tmp_path):
        """Modified source file should be re-copied."""
        staging = tmp_path / "staging"
        packager = SessionPackager(
            project_dir=mock_claude_project,
            user_id="alice",
            machine_id="test-mac",
        )

        packager.package(staging_dir=staging)
        copied = staging / "sessions" / "session-uuid-001.jsonl"
        mtime_before = copied.stat().st_mtime

        import time
        time.sleep(0.05)

        # Modify source
        src = mock_claude_project / "session-uuid-001.jsonl"
        src.write_text('{"type":"user","message":{"role":"user","content":"updated"}}\n')

        packager.package(staging_dir=staging)
        mtime_after = copied.stat().st_mtime
        assert mtime_after > mtime_before
```

**Step 2: Run to verify they fail**

Run: `cd cli && pytest tests/test_packager.py::TestIncrementalPackaging -v`
Expected: FAIL (first test fails because files are always re-copied)

**Step 3: Add incremental logic to `package()`**

In `cli/karma/packager.py`, modify the `package()` method's session copy loop:

```python
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
                dst_assoc = sessions_dir / entry.uuid
                # For associated dirs, always sync (copytree with dirs_exist_ok handles updates)
                shutil.copytree(
                    assoc_dir,
                    dst_assoc,
                    dirs_exist_ok=True,
                )

        # ... rest unchanged (todos, manifest)
```

**Step 4: Run all tests**

Run: `cd cli && pytest tests/test_packager.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add cli/karma/packager.py cli/tests/test_packager.py
git commit -m "feat(cli): incremental packaging skips unchanged JSONL files

Compares source and destination mtimes before copying. Only re-copies
sessions whose source JSONL has been modified since last package."
```

---

## Task 7: Integration test — end-to-end worktree sync

Verify the full pipeline: discover worktrees → package → manifest has worktree sessions.

**Files:**
- Modify: `cli/tests/test_cli_syncthing.py`

**Step 1: Write integration test**

```python
# Add to cli/tests/test_cli_syncthing.py

def test_full_worktree_package_pipeline(tmp_path):
    """End-to-end: discover worktrees, package, verify manifest."""
    from karma.packager import SessionPackager
    from karma.worktree_discovery import find_worktree_dirs
    import json

    projects_dir = tmp_path / "projects"

    # Main project
    main = projects_dir / "-Users-jay-karma"
    main.mkdir(parents=True)
    (main / "main-session.jsonl").write_text(
        '{"type":"user","message":{"role":"user","content":"main work"}}\n'
    )

    # Worktree 1
    wt1 = projects_dir / "-Users-jay-karma--claude-worktrees-feat-auth"
    wt1.mkdir(parents=True)
    (wt1 / "auth-session.jsonl").write_text(
        '{"type":"user","message":{"role":"user","content":"auth feature"}}\n'
    )
    # With subagent
    (wt1 / "auth-session" / "subagents").mkdir(parents=True)
    (wt1 / "auth-session" / "subagents" / "agent-a1.jsonl").write_text('{"type":"agent"}\n')

    # Worktree 2
    wt2 = projects_dir / "-Users-jay-karma--claude-worktrees-fix-bug"
    wt2.mkdir(parents=True)
    (wt2 / "bug-session.jsonl").write_text(
        '{"type":"user","message":{"role":"user","content":"bug fix"}}\n'
    )

    # Discover
    wt_dirs = find_worktree_dirs("-Users-jay-karma", projects_dir)
    assert len(wt_dirs) == 2

    # Package
    staging = tmp_path / "outbox"
    packager = SessionPackager(
        project_dir=main,
        user_id="jay",
        machine_id="mac",
        extra_dirs=wt_dirs,
    )
    manifest = packager.package(staging_dir=staging)

    # Verify manifest
    assert manifest.session_count == 3
    uuids = {s.uuid for s in manifest.sessions}
    assert uuids == {"main-session", "auth-session", "bug-session"}

    # Verify worktree tagging
    by_uuid = {s.uuid: s for s in manifest.sessions}
    assert by_uuid["main-session"].worktree_name is None
    assert by_uuid["auth-session"].worktree_name == "feat-auth"
    assert by_uuid["bug-session"].worktree_name == "fix-bug"

    # Verify files on disk
    assert (staging / "sessions" / "auth-session.jsonl").exists()
    assert (staging / "sessions" / "auth-session" / "subagents" / "agent-a1.jsonl").exists()
    assert (staging / "sessions" / "bug-session.jsonl").exists()

    # Verify manifest JSON
    manifest_json = json.loads((staging / "manifest.json").read_text())
    wt_entries = [s for s in manifest_json["sessions"] if s["worktree_name"]]
    assert len(wt_entries) == 2
```

**Step 2: Run test**

Run: `cd cli && pytest tests/test_cli_syncthing.py::test_full_worktree_package_pipeline -v`
Expected: PASS (all prior tasks should make this work)

**Step 3: Commit**

```bash
git add cli/tests/test_cli_syncthing.py
git commit -m "test(cli): add end-to-end worktree sync integration test

Verifies full pipeline: discovery -> packaging -> manifest with
worktree metadata and subagent file copying."
```

---

## Task 8: Run full test suite and verify

**Step 1: Run all CLI tests**

Run: `cd cli && pytest -v`
Expected: All tests PASS

**Step 2: Run API tests to check no regressions**

Run: `cd api && pytest tests/ -v --timeout=30`
Expected: All pass (no API changes in this plan)

**Step 3: Final commit (if any fixups needed)**

---

## Summary

| Task | What | Files Changed | Tests |
|------|------|---------------|-------|
| 1 | Worktree discovery module | +`worktree_discovery.py`, +`test_worktree_discovery.py` | 9 |
| 2 | SessionEntry metadata fields | `manifest.py`, `test_packager.py` | 3 |
| 3 | Multi-dir SessionPackager | `packager.py`, `test_packager.py` | 5 |
| 4 | Wire into `karma watch` | `main.py`, `test_cli_syncthing.py` | 1 |
| 5 | Status with sync gap | `main.py`, `test_cli_syncthing.py` | 1 |
| 6 | Incremental packaging | `packager.py`, `test_packager.py` | 2 |
| 7 | Integration test | `test_cli_syncthing.py` | 1 |
| 8 | Full suite verification | — | all |

**Not in scope (future work):**
- Hook-based packaging trigger (SessionEnd hook → `karma watch --once`)
- launchd/systemd for persistent `karma watch`
- Stable project identity (GitHub remote URL)
- Debug log syncing
- Desktop worktree discovery (requires Desktop metadata which the CLI doesn't have)
