# Syncthing Worktree Session Sync — Verification & Fix Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix three bugs preventing worktree sessions from syncing between teammates: stale `karma watch` process, missing Desktop worktree discovery in CLI packager, and consolidate the fragmented session→project mapping logic so all session sources (local, worktree, desktop-worktree, remote) are handled consistently.

**Architecture:** The CLI packager already supports CLI worktrees via `find_worktree_dirs()` prefix matching. We add Desktop worktree discovery (Strategy A: filesystem scan of `~/.claude-worktrees/`), fix the stale watch process, and add a verification test suite that catches these mapping gaps. On the API side, `list_remote_sessions_for_project()` already works correctly — the fix is entirely on the CLI packaging/sending side.

**Tech Stack:** Python 3.9+, click (CLI), watchdog (filesystem events), Pydantic 2.x (models), pytest (testing)

**Root Cause Analysis (from deep search):**

| Issue | Root Cause | Impact |
|-------|-----------|--------|
| `karma watch --team beta` is zombie | Team `beta` was renamed to `Ayush-stealing-prompts` in config | Watch does nothing; outbox stale since Mar 4 |
| Outbox has 0 worktree sessions | Manifest created before `worktree_name`/`extra_dirs` were added | Friend can't see your worktree work |
| Desktop worktrees not discovered | `find_worktree_dirs()` uses prefix matching; Desktop worktrees have different encoded name pattern | 2 sessions from focused-jepsen/lucid-villani missing |
| 3 separate mapping systems | `utils.py`, `desktop_sessions.py`, `remote_sessions.py` each handle one case independently | No unified view; easy to miss a source |

**Current session counts NOT in outbox:**
- CLI worktrees: 40 sessions (syncthing-sync-design: 23, ipfs-sync-design: 11, opencode-integration-design: 4, fix-command-skill-tracking: 1, syncthing-sync-design-api: 1)
- Desktop worktrees: 2 sessions (focused-jepsen: 1, lucid-villani: 1)

---

## Task 1: Verify current state with diagnostic script

Before changing anything, verify the exact state of the system so we can confirm fixes work.

**Files:**
- Create: `cli/tests/test_sync_diagnostics.py`

**Step 1: Write diagnostic tests**

```python
# cli/tests/test_sync_diagnostics.py
"""Diagnostic tests that verify the sync pipeline state.

These tests use the REAL filesystem (not mocks) to verify the actual
state of the sync pipeline on this machine. They document what IS,
not what SHOULD BE, so they serve as regression tests after fixes.
"""

import json
from pathlib import Path

import pytest


PROJECTS_DIR = Path.home() / ".claude" / "projects"
KARMA_BASE = Path.home() / ".claude_karma"
MAIN_ENCODED = "-Users-jayantdevkar-Documents-GitHub-claude-karma"


@pytest.mark.skipif(
    not PROJECTS_DIR.exists(), reason="No ~/.claude/projects/ on this machine"
)
class TestSyncDiagnostics:
    def test_cli_worktree_dirs_exist(self):
        """CLI worktree dirs should exist in ~/.claude/projects/."""
        from karma.worktree_discovery import find_worktree_dirs

        wt_dirs = find_worktree_dirs(MAIN_ENCODED, PROJECTS_DIR)
        # We know there are at least 5 CLI worktree dirs
        assert len(wt_dirs) >= 5, (
            f"Expected >=5 CLI worktree dirs, found {len(wt_dirs)}: "
            f"{[d.name for d in wt_dirs]}"
        )

    def test_desktop_worktree_dirs_exist(self):
        """Desktop worktree project dirs exist but aren't found by find_worktree_dirs."""
        from karma.worktree_discovery import find_worktree_dirs

        # These exist on disk
        desktop_wt_dirs = list(PROJECTS_DIR.glob(
            "-Users-jayantdevkar--claude-worktrees-claude-karma-*"
        ))
        assert len(desktop_wt_dirs) >= 2, "Desktop worktree dirs should exist"

        # But find_worktree_dirs doesn't find them (prefix doesn't match)
        found = find_worktree_dirs(MAIN_ENCODED, PROJECTS_DIR)
        found_names = {d.name for d in found}
        for dw in desktop_wt_dirs:
            assert dw.name not in found_names, (
                f"Desktop worktree {dw.name} should NOT be found by prefix match"
            )

    def test_outbox_manifest_is_stale(self):
        """Outbox manifest should exist but lack worktree_name fields."""
        manifest_path = (
            KARMA_BASE / "remote-sessions" / "jay" / MAIN_ENCODED / "manifest.json"
        )
        if not manifest_path.exists():
            pytest.skip("No outbox manifest")

        manifest = json.loads(manifest_path.read_text())
        # Check that sessions don't have worktree_name
        sessions_with_wt = [
            s for s in manifest["sessions"] if s.get("worktree_name")
        ]
        # This documents the CURRENT bug — after fix, this test should be updated
        assert len(sessions_with_wt) == 0, (
            "Outbox currently has no worktree sessions (this is the bug)"
        )

    def test_config_team_name_vs_watch_process(self):
        """Config should have a team; watch may be running with wrong name."""
        config_path = KARMA_BASE / "sync-config.json"
        if not config_path.exists():
            pytest.skip("No sync config")

        config = json.loads(config_path.read_text())
        teams = list(config.get("teams", {}).keys())
        assert len(teams) >= 1, "Should have at least one team"
        # Document: the team is NOT called 'beta'
        assert "beta" not in teams, (
            "Team 'beta' should not exist (was renamed)"
        )
```

**Step 2: Run diagnostic tests**

Run: `cd cli && pytest tests/test_sync_diagnostics.py -v`
Expected: All PASS (they document current bugs as assertions)

**Step 3: Commit**

```bash
git add cli/tests/test_sync_diagnostics.py
git commit -m "test(cli): add sync pipeline diagnostic tests

Documents current state: stale outbox, missing worktree sessions,
Desktop worktrees not discovered by prefix matching."
```

---

## Task 2: Add Desktop worktree discovery to CLI

The CLI's `find_worktree_dirs()` only finds CLI/superpowers worktrees via prefix matching. Desktop worktrees (`~/.claude-worktrees/{project}/{name}`) use a completely different encoded name pattern. Add a new function that scans the worktree base dir and matches by project name suffix.

**Files:**
- Modify: `cli/karma/worktree_discovery.py`
- Modify: `cli/tests/test_worktree_discovery.py`

**Step 1: Write failing tests**

Add to `cli/tests/test_worktree_discovery.py`:

```python
# Add these imports at the top if not present
from karma.worktree_discovery import find_desktop_worktree_dirs


class TestFindDesktopWorktreeDirs:
    """Desktop worktrees live in ~/.claude-worktrees/{project}/{name}.

    Their encoded names in ~/.claude/projects/ look like:
      -Users-{user}--claude-worktrees-{project}-{name}

    These DON'T share a prefix with the main project, so they need
    a different discovery strategy: scan the worktree base dir.
    """

    def test_finds_desktop_worktrees_by_project_name(self, tmp_path):
        """Desktop worktrees are found by matching project name in encoded dir."""
        projects_dir = tmp_path / "projects"
        worktree_base = tmp_path / ".claude-worktrees"

        # Main project
        main = projects_dir / "-Users-jay-GitHub-claude-karma"
        main.mkdir(parents=True)

        # Desktop worktree base — the actual worktree dirs
        wt_actual = worktree_base / "claude-karma" / "focused-jepsen"
        wt_actual.mkdir(parents=True)

        # The corresponding ~/.claude/projects/ dir (with encoded name)
        wt_encoded = projects_dir / "-Users-jay--claude-worktrees-claude-karma-focused-jepsen"
        wt_encoded.mkdir(parents=True)
        (wt_encoded / "session.jsonl").write_text('{"type":"user"}\n')

        result = find_desktop_worktree_dirs(
            project_name="claude-karma",
            projects_dir=projects_dir,
            worktree_base=worktree_base,
        )
        assert len(result) == 1
        assert result[0] == wt_encoded

    def test_finds_multiple_desktop_worktrees(self, tmp_path):
        projects_dir = tmp_path / "projects"
        worktree_base = tmp_path / ".claude-worktrees"

        # Main project
        (projects_dir / "-Users-jay-GitHub-karma").mkdir(parents=True)

        # Two desktop worktrees
        for name in ("focused-jepsen", "lucid-villani"):
            (worktree_base / "karma" / name).mkdir(parents=True)
            wt_enc = projects_dir / f"-Users-jay--claude-worktrees-karma-{name}"
            wt_enc.mkdir(parents=True)
            (wt_enc / "session.jsonl").write_text('{"type":"user"}\n')

        result = find_desktop_worktree_dirs(
            project_name="karma",
            projects_dir=projects_dir,
            worktree_base=worktree_base,
        )
        assert len(result) == 2

    def test_ignores_other_project_worktrees(self, tmp_path):
        projects_dir = tmp_path / "projects"
        worktree_base = tmp_path / ".claude-worktrees"

        (projects_dir / "-Users-jay-GitHub-karma").mkdir(parents=True)

        # Worktree for a DIFFERENT project
        (worktree_base / "hubdata" / "feat-x").mkdir(parents=True)
        wt_enc = projects_dir / "-Users-jay--claude-worktrees-hubdata-feat-x"
        wt_enc.mkdir(parents=True)

        result = find_desktop_worktree_dirs(
            project_name="karma",
            projects_dir=projects_dir,
            worktree_base=worktree_base,
        )
        assert len(result) == 0

    def test_returns_empty_when_no_worktree_base(self, tmp_path):
        projects_dir = tmp_path / "projects"
        (projects_dir / "-Users-jay-GitHub-karma").mkdir(parents=True)

        result = find_desktop_worktree_dirs(
            project_name="karma",
            projects_dir=projects_dir,
            worktree_base=tmp_path / "nonexistent",
        )
        assert result == []

    def test_returns_empty_when_project_has_no_desktop_worktrees(self, tmp_path):
        projects_dir = tmp_path / "projects"
        worktree_base = tmp_path / ".claude-worktrees"
        worktree_base.mkdir()

        (projects_dir / "-Users-jay-GitHub-karma").mkdir(parents=True)

        result = find_desktop_worktree_dirs(
            project_name="karma",
            projects_dir=projects_dir,
            worktree_base=worktree_base,
        )
        assert result == []

    def test_handles_cleaned_up_worktree_dirs(self, tmp_path):
        """Worktree dirs may be cleaned up but ~/.claude/projects/ dirs remain."""
        projects_dir = tmp_path / "projects"
        worktree_base = tmp_path / ".claude-worktrees"

        (projects_dir / "-Users-jay-GitHub-karma").mkdir(parents=True)

        # Worktree base exists but is empty (worktrees were cleaned up)
        (worktree_base / "karma").mkdir(parents=True)

        # But the projects dir still has the encoded dir with session data
        wt_enc = projects_dir / "-Users-jay--claude-worktrees-karma-old-branch"
        wt_enc.mkdir(parents=True)
        (wt_enc / "session.jsonl").write_text('{"type":"user"}\n')

        # Can still find it by scanning projects_dir for the pattern
        result = find_desktop_worktree_dirs(
            project_name="karma",
            projects_dir=projects_dir,
            worktree_base=worktree_base,
        )
        # Should find it even though the actual worktree dir is gone
        assert len(result) == 1
```

**Step 2: Run tests to verify they fail**

Run: `cd cli && pytest tests/test_worktree_discovery.py::TestFindDesktopWorktreeDirs -v`
Expected: FAIL — `ImportError: cannot import name 'find_desktop_worktree_dirs'`

**Step 3: Implement `find_desktop_worktree_dirs`**

Add to `cli/karma/worktree_discovery.py` (after existing code):

```python
def _extract_project_name_from_encoded(encoded_name: str) -> str | None:
    """Extract project name (last path segment) from encoded name.

    "-Users-jay-Documents-GitHub-claude-karma" -> "claude-karma"

    This is inherently lossy (dashes in the project name are ambiguous),
    so we use it only as a hint and verify against known worktree dirs.
    """
    if not encoded_name or not encoded_name.startswith("-"):
        return None
    # The last segment after the final path separator
    # But since all separators are dashes, we can't split reliably.
    # Instead, we return the full encoded name for prefix/suffix matching.
    return encoded_name


def find_desktop_worktree_dirs(
    project_name: str,
    projects_dir: Path,
    worktree_base: Path | None = None,
) -> list[Path]:
    """Find Desktop worktree directories for a project.

    Desktop worktrees (created by Claude Desktop's "Claude Code" mode)
    live in ~/.claude-worktrees/{project_name}/{random_name}/ and get
    encoded as: -Users-{user}--claude-worktrees-{project}-{name}

    These DON'T share an encoded name prefix with the main project,
    so we can't use prefix matching. Instead we:
    1. Scan projects_dir for dirs containing '-claude-worktrees-{project_name}-'
    2. Optionally verify against actual worktree base dir

    This also finds "orphaned" worktree project dirs where the actual
    worktree has been cleaned up but sessions remain.

    Args:
        project_name: The project's directory name (e.g., "claude-karma").
        projects_dir: Path to ~/.claude/projects/
        worktree_base: Path to ~/.claude-worktrees/ (default: ~/.claude-worktrees)

    Returns:
        List of Path objects for matching worktree project directories.
    """
    if worktree_base is None:
        worktree_base = Path.home() / ".claude-worktrees"

    if not projects_dir.is_dir():
        return []

    # Pattern: encoded dirs containing -claude-worktrees-{project_name}-
    # This catches both --claude-worktrees- and -.claude-worktrees- variants
    marker = f"-claude-worktrees-{project_name}-"

    matches = []
    for entry in projects_dir.iterdir():
        if not entry.is_dir():
            continue
        if marker not in entry.name:
            continue
        # Ensure this is actually a Desktop worktree pattern:
        # The marker should NOT be preceded by the main project prefix
        # (those are CLI worktrees, already handled by find_worktree_dirs)
        prefix = _get_worktree_prefix(entry.name)
        if prefix is not None:
            # This is a CLI/superpowers worktree (prefix-style), skip it
            # It would already be found by find_worktree_dirs()
            continue
        matches.append(entry)

    return sorted(matches)
```

**Step 4: Run tests to verify they pass**

Run: `cd cli && pytest tests/test_worktree_discovery.py -v`
Expected: All tests PASS (existing + new)

**Step 5: Commit**

```bash
git add cli/karma/worktree_discovery.py cli/tests/test_worktree_discovery.py
git commit -m "feat(cli): add Desktop worktree discovery

find_desktop_worktree_dirs() scans ~/.claude/projects/ for dirs
matching the -claude-worktrees-{project}- pattern that aren't
prefix-style CLI worktrees. Handles orphaned worktree dirs
where the actual worktree was cleaned up but sessions remain."
```

---

## Task 3: Extract project name from config for Desktop discovery

The `find_desktop_worktree_dirs()` needs a `project_name` (e.g., "claude-karma"), but the config only stores `path` (e.g., "/Users/jayantdevkar/Documents/GitHub/claude-karma") and `encoded_name`. We need a helper to extract the project dir name from the path.

**Files:**
- Modify: `cli/karma/worktree_discovery.py`
- Modify: `cli/tests/test_worktree_discovery.py`

**Step 1: Write failing tests**

Add to `cli/tests/test_worktree_discovery.py`:

```python
from karma.worktree_discovery import project_name_from_path


class TestProjectNameFromPath:
    def test_unix_path(self):
        assert project_name_from_path("/Users/jay/GitHub/claude-karma") == "claude-karma"

    def test_nested_path(self):
        assert project_name_from_path("/Users/jay/Documents/GitHub/my-project") == "my-project"

    def test_trailing_slash(self):
        assert project_name_from_path("/Users/jay/repo/") == "repo"

    def test_windows_path(self):
        assert project_name_from_path("C:\\Users\\jay\\repos\\karma") == "karma"

    def test_single_segment(self):
        assert project_name_from_path("myproject") == "myproject"
```

**Step 2: Run to verify they fail**

Run: `cd cli && pytest tests/test_worktree_discovery.py::TestProjectNameFromPath -v`
Expected: FAIL — `ImportError`

**Step 3: Implement**

Add to `cli/karma/worktree_discovery.py`:

```python
def project_name_from_path(project_path: str) -> str:
    """Extract the project directory name from a full path.

    "/Users/jay/GitHub/claude-karma" -> "claude-karma"
    "C:\\Users\\jay\\repos\\karma" -> "karma"
    """
    # Normalize separators
    p = project_path.replace("\\", "/").rstrip("/")
    return p.rsplit("/", 1)[-1] if "/" in p else p
```

**Step 4: Run tests**

Run: `cd cli && pytest tests/test_worktree_discovery.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add cli/karma/worktree_discovery.py cli/tests/test_worktree_discovery.py
git commit -m "feat(cli): add project_name_from_path helper

Extracts directory name from full project path for Desktop
worktree discovery matching."
```

---

## Task 4: Wire Desktop worktree discovery into packager and watch

Connect `find_desktop_worktree_dirs()` into the `sync_project()` and `watch` command so Desktop worktree sessions are included in the outbox.

**Files:**
- Modify: `cli/karma/sync.py:60-70` (sync_project function)
- Modify: `cli/karma/main.py:506-561` (watch command)
- Modify: `cli/tests/test_packager.py`

**Step 1: Write failing test for packager with desktop worktrees**

Add to `cli/tests/test_packager.py`:

```python
@pytest.fixture
def mock_project_with_desktop_worktree(tmp_path: Path) -> dict:
    """Create a main project dir + one Desktop-style worktree dir."""
    projects_dir = tmp_path / ".claude" / "projects"
    worktree_base = tmp_path / ".claude-worktrees"

    # Main project
    main_dir = projects_dir / "-Users-jay-GitHub-karma"
    main_dir.mkdir(parents=True)
    (main_dir / "session-main.jsonl").write_text(
        '{"type":"user","message":{"role":"user","content":"main"}}\n'
    )

    # Desktop worktree (different encoded name pattern)
    wt_dir = projects_dir / "-Users-jay--claude-worktrees-karma-focused-jepsen"
    wt_dir.mkdir(parents=True)
    (wt_dir / "session-desktop-wt.jsonl").write_text(
        '{"type":"user","message":{"role":"user","content":"desktop wt"}}\n'
    )

    # Actual worktree base dir
    (worktree_base / "karma" / "focused-jepsen").mkdir(parents=True)

    return {
        "main_dir": main_dir,
        "wt_dir": wt_dir,
        "projects_dir": projects_dir,
        "worktree_base": worktree_base,
    }


class TestPackagerWithDesktopWorktrees:
    def test_discover_includes_desktop_worktree_sessions(
        self, mock_project_with_desktop_worktree
    ):
        dirs = mock_project_with_desktop_worktree
        packager = SessionPackager(
            project_dir=dirs["main_dir"],
            user_id="jay",
            machine_id="mac",
            extra_dirs=[dirs["wt_dir"]],
        )
        sessions = packager.discover_sessions()
        uuids = {s.uuid for s in sessions}
        assert "session-main" in uuids
        assert "session-desktop-wt" in uuids

    def test_desktop_worktree_sessions_have_worktree_name(
        self, mock_project_with_desktop_worktree
    ):
        dirs = mock_project_with_desktop_worktree
        packager = SessionPackager(
            project_dir=dirs["main_dir"],
            user_id="jay",
            machine_id="mac",
            extra_dirs=[dirs["wt_dir"]],
        )
        sessions = packager.discover_sessions()
        wt_session = [s for s in sessions if s.uuid == "session-desktop-wt"][0]
        # The worktree name is extracted from the encoded dir name
        assert wt_session.worktree_name is not None
```

**Step 2: Run to verify they pass**

Run: `cd cli && pytest tests/test_packager.py::TestPackagerWithDesktopWorktrees -v`
Expected: PASS (the packager already handles `extra_dirs` — this just verifies it works for Desktop-style dirs too)

**Step 3: Modify `sync_project()` to include Desktop worktrees**

In `cli/karma/sync.py`, modify lines 60-70:

```python
# Replace the existing import and extra_dirs construction:

    from karma.worktree_discovery import (
        find_worktree_dirs,
        find_desktop_worktree_dirs,
        project_name_from_path,
    )

    # CLI/superpowers worktrees (prefix match)
    extra_dirs = find_worktree_dirs(project.encoded_name, projects_dir)

    # Desktop worktrees (project name match)
    proj_name = project_name_from_path(project.path)
    extra_dirs.extend(
        find_desktop_worktree_dirs(proj_name, projects_dir)
    )

    packager = SessionPackager(
        project_dir=claude_dir,
        user_id=config.user_id,
        machine_id=config.machine_id,
        project_path=project.path,
        last_sync_cid=project.last_sync_cid,
        extra_dirs=extra_dirs,
    )
```

**Step 4: Modify `watch` command to include Desktop worktrees**

In `cli/karma/main.py`, modify the watch command's inner loop (around lines 506-539):

```python
    from karma.worktree_discovery import (
        find_worktree_dirs,
        find_desktop_worktree_dirs,
        project_name_from_path,
    )

    watchers = []
    projects_dir = Path.home() / ".claude" / "projects"

    for proj_name, proj in team_cfg.projects.items():
        claude_dir = Path.home() / ".claude" / "projects" / proj.encoded_name
        if not claude_dir.is_dir():
            click.echo(f"  Skipping '{proj_name}': Claude dir not found ({claude_dir})")
            continue

        # Discover worktree dirs for this project (CLI + Desktop)
        wt_dirs = find_worktree_dirs(proj.encoded_name, projects_dir)
        desktop_proj_name = project_name_from_path(proj.path)
        desktop_wt_dirs = find_desktop_worktree_dirs(desktop_proj_name, projects_dir)
        all_wt_dirs = wt_dirs + desktop_wt_dirs
        if all_wt_dirs:
            click.echo(
                f"  Found {len(wt_dirs)} CLI + {len(desktop_wt_dirs)} Desktop "
                f"worktree dir(s) for '{proj_name}'"
            )

        outbox = KARMA_BASE / "remote-sessions" / config.user_id / proj.encoded_name

        def make_package_fn(cd=claude_dir, ob=outbox, pn=proj_name, en=proj.encoded_name, pp=proj.path):
            def package():
                # Re-discover worktrees each time (new ones may appear)
                current_wt_dirs = find_worktree_dirs(en, projects_dir)
                current_desktop = find_desktop_worktree_dirs(
                    project_name_from_path(pp), projects_dir
                )
                all_extra = current_wt_dirs + current_desktop
                packager = SessionPackager(
                    project_dir=cd,
                    user_id=config.user_id,
                    machine_id=config.machine_id,
                    project_path=pp,
                    extra_dirs=all_extra,
                )
                ob.mkdir(parents=True, exist_ok=True)
                packager.package(staging_dir=ob)
                click.echo(
                    f"  Packaged '{pn}' -> {ob} "
                    f"({len(current_wt_dirs)} CLI + {len(current_desktop)} Desktop worktrees)"
                )
            return package

        package_fn = make_package_fn()

        watcher = SessionWatcher(
            watch_dir=claude_dir,
            package_fn=package_fn,
        )
        watcher.start()
        watchers.append(watcher)
        click.echo(f"  Watching: {proj_name} ({claude_dir})")

        # Also watch each worktree dir (both CLI and Desktop)
        for wt_dir in all_wt_dirs:
            wt_watcher = SessionWatcher(
                watch_dir=wt_dir,
                package_fn=package_fn,
            )
            wt_watcher.start()
            watchers.append(wt_watcher)
            # Extract a human-readable name
            if "--claude-worktrees-" in wt_dir.name:
                wt_name = wt_dir.name.split("--claude-worktrees-")[-1]
            elif "-claude-worktrees-" in wt_dir.name:
                # Desktop pattern: -Users-jay--claude-worktrees-karma-focused-jepsen
                parts = wt_dir.name.split("-claude-worktrees-")
                wt_name = parts[-1] if parts else wt_dir.name
            else:
                wt_name = wt_dir.name
            click.echo(f"  Watching worktree: {wt_name} ({wt_dir})")
```

**Step 5: Run tests**

Run: `cd cli && pytest tests/test_packager.py tests/test_worktree_discovery.py -v`
Expected: All PASS

**Step 6: Commit**

```bash
git add cli/karma/sync.py cli/karma/main.py cli/tests/test_packager.py
git commit -m "feat(cli): wire Desktop worktree discovery into sync and watch

Both sync_project() and karma watch now discover Desktop worktrees
(~/.claude-worktrees/) in addition to CLI worktrees. Desktop worktree
sessions are included in the outbox for Syncthing sync."
```

---

## Task 5: Add `find_all_worktree_dirs()` unified helper

Create a single function that combines CLI + Desktop worktree discovery, reducing duplication in `sync.py` and `main.py`.

**Files:**
- Modify: `cli/karma/worktree_discovery.py`
- Modify: `cli/tests/test_worktree_discovery.py`

**Step 1: Write failing test**

Add to `cli/tests/test_worktree_discovery.py`:

```python
from karma.worktree_discovery import find_all_worktree_dirs


class TestFindAllWorktreeDirs:
    def test_combines_cli_and_desktop_worktrees(self, tmp_path):
        projects_dir = tmp_path / "projects"
        worktree_base = tmp_path / ".claude-worktrees"

        # Main project
        main = projects_dir / "-Users-jay-GitHub-karma"
        main.mkdir(parents=True)

        # CLI worktree
        cli_wt = projects_dir / "-Users-jay-GitHub-karma--claude-worktrees-feat-x"
        cli_wt.mkdir(parents=True)

        # Desktop worktree
        (worktree_base / "karma" / "focused-jepsen").mkdir(parents=True)
        desktop_wt = projects_dir / "-Users-jay--claude-worktrees-karma-focused-jepsen"
        desktop_wt.mkdir(parents=True)

        result = find_all_worktree_dirs(
            main_encoded_name="-Users-jay-GitHub-karma",
            project_path="/Users/jay/GitHub/karma",
            projects_dir=projects_dir,
            worktree_base=worktree_base,
        )
        assert len(result) == 2
        assert cli_wt in result
        assert desktop_wt in result

    def test_deduplicates_overlapping_results(self, tmp_path):
        """If a dir matches both strategies, it should appear only once."""
        projects_dir = tmp_path / "projects"

        main = projects_dir / "-Users-jay-GitHub-karma"
        main.mkdir(parents=True)

        wt = projects_dir / "-Users-jay-GitHub-karma--claude-worktrees-feat-x"
        wt.mkdir(parents=True)

        result = find_all_worktree_dirs(
            main_encoded_name="-Users-jay-GitHub-karma",
            project_path="/Users/jay/GitHub/karma",
            projects_dir=projects_dir,
        )
        # CLI worktree found once, no duplicates
        assert result.count(wt) == 1
```

**Step 2: Run to verify they fail**

Run: `cd cli && pytest tests/test_worktree_discovery.py::TestFindAllWorktreeDirs -v`
Expected: FAIL — `ImportError`

**Step 3: Implement**

Add to `cli/karma/worktree_discovery.py`:

```python
def find_all_worktree_dirs(
    main_encoded_name: str,
    project_path: str,
    projects_dir: Path,
    worktree_base: Path | None = None,
) -> list[Path]:
    """Find ALL worktree directories for a project (CLI + Desktop).

    Combines:
    - find_worktree_dirs(): CLI/superpowers worktrees (prefix match)
    - find_desktop_worktree_dirs(): Desktop worktrees (project name match)

    Args:
        main_encoded_name: Main project's encoded dir name.
        project_path: Original project path (e.g., "/Users/jay/GitHub/karma").
        projects_dir: Path to ~/.claude/projects/
        worktree_base: Path to ~/.claude-worktrees/ (default: auto-detect)

    Returns:
        Deduplicated sorted list of worktree directory Paths.
    """
    cli_dirs = find_worktree_dirs(main_encoded_name, projects_dir)
    proj_name = project_name_from_path(project_path)
    desktop_dirs = find_desktop_worktree_dirs(proj_name, projects_dir, worktree_base)

    # Deduplicate by resolved path
    seen: set[Path] = set()
    result: list[Path] = []
    for d in cli_dirs + desktop_dirs:
        resolved = d.resolve()
        if resolved not in seen:
            seen.add(resolved)
            result.append(d)

    return sorted(result)
```

**Step 4: Run tests**

Run: `cd cli && pytest tests/test_worktree_discovery.py -v`
Expected: All PASS

**Step 5: Simplify sync.py and main.py to use `find_all_worktree_dirs`**

In `cli/karma/sync.py`, replace lines 60-70:

```python
    from karma.worktree_discovery import find_all_worktree_dirs

    packager = SessionPackager(
        project_dir=claude_dir,
        user_id=config.user_id,
        machine_id=config.machine_id,
        project_path=project.path,
        last_sync_cid=project.last_sync_cid,
        extra_dirs=find_all_worktree_dirs(
            project.encoded_name, project.path, projects_dir
        ),
    )
```

In `cli/karma/main.py` watch command, replace the discovery block:

```python
    from karma.worktree_discovery import find_all_worktree_dirs

    # ... inside the loop:
        all_wt_dirs = find_all_worktree_dirs(
            proj.encoded_name, proj.path, projects_dir
        )
        if all_wt_dirs:
            click.echo(f"  Found {len(all_wt_dirs)} worktree dir(s) for '{proj_name}'")

        # ... inside make_package_fn:
            def package():
                current_wt_dirs = find_all_worktree_dirs(en, pp, projects_dir)
                # ... rest unchanged
```

**Step 6: Run all tests**

Run: `cd cli && pytest -v`
Expected: All PASS

**Step 7: Commit**

```bash
git add cli/karma/worktree_discovery.py cli/tests/test_worktree_discovery.py cli/karma/sync.py cli/karma/main.py
git commit -m "refactor(cli): unified find_all_worktree_dirs helper

Single function that combines CLI prefix-match and Desktop project-name
discovery, deduplicates results. Simplifies sync.py and main.py."
```

---

## Task 6: Update `karma status` to show Desktop worktree counts

The `status` command should show Desktop worktree sessions alongside CLI worktrees.

**Files:**
- Modify: `cli/karma/main.py` (status command)

**Step 1: Modify status command**

In `cli/karma/main.py`, in the `status` command, replace the worktree counting block to use `find_all_worktree_dirs`:

```python
    from karma.worktree_discovery import find_all_worktree_dirs

    # ... inside the per-project loop:

            # Count worktree sessions (CLI + Desktop)
            wt_dirs = find_all_worktree_dirs(
                proj.encoded_name, proj.path, projects_dir
            )
            wt_count = 0
            for wd in wt_dirs:
                wt_count += sum(
                    1 for f in wd.glob("*.jsonl")
                    if not f.name.startswith("agent-") and f.stat().st_size > 0
                )
```

**Step 2: Run status manually to verify**

Run: `cd cli && karma status`
Expected: Should show worktree counts including Desktop worktrees

**Step 3: Run tests**

Run: `cd cli && pytest tests/test_cli_syncthing.py -v`
Expected: All PASS

**Step 4: Commit**

```bash
git add cli/karma/main.py
git commit -m "fix(cli): karma status includes Desktop worktree counts

Status now uses find_all_worktree_dirs() to count sessions from
both CLI and Desktop worktrees."
```

---

## Task 7: Manual verification — restart watch and verify outbox

This is an operational task, not code. Kill the stale watch, restart with the correct team, verify the outbox gets populated.

**Step 1: Kill stale watch process**

Run: `kill 3994`  (PID of `karma watch --team beta`)

Verify: `ps aux | grep '[k]arma watch'` should show nothing.

**Step 2: Run one-shot package to verify content**

We need a way to manually trigger a single package run. Use Python directly:

```bash
cd cli && python3 -c "
from pathlib import Path
from karma.config import SyncConfig, KARMA_BASE
from karma.packager import SessionPackager
from karma.worktree_discovery import find_all_worktree_dirs

config = SyncConfig.load()
team = config.teams['Ayush-stealing-prompts']
proj = team.projects['claude-code-karma']
projects_dir = Path.home() / '.claude' / 'projects'
claude_dir = projects_dir / proj.encoded_name

wt_dirs = find_all_worktree_dirs(proj.encoded_name, proj.path, projects_dir)
print(f'Found {len(wt_dirs)} worktree dirs')
for d in wt_dirs:
    print(f'  {d.name}')

outbox = KARMA_BASE / 'remote-sessions' / config.user_id / proj.encoded_name
outbox.mkdir(parents=True, exist_ok=True)

packager = SessionPackager(
    project_dir=claude_dir,
    user_id=config.user_id,
    machine_id=config.machine_id,
    project_path=proj.path,
    extra_dirs=wt_dirs,
)
manifest = packager.package(staging_dir=outbox)
wt_sessions = [s for s in manifest.sessions if s.worktree_name]
print(f'Total sessions: {manifest.session_count}')
print(f'Worktree sessions: {len(wt_sessions)}')
for s in wt_sessions[:10]:
    print(f'  {s.uuid[:12]}... wt={s.worktree_name}')
"
```

Expected: Should show >826 sessions total, with 40+ worktree sessions.

**Step 3: Verify manifest has worktree_name fields**

```bash
python3 -c "
import json
m = json.load(open('$HOME/.claude_karma/remote-sessions/jay/-Users-jayantdevkar-Documents-GitHub-claude-karma/manifest.json'))
wt = [s for s in m['sessions'] if s.get('worktree_name')]
print(f'Total: {m[\"session_count\"]}')
print(f'With worktree_name: {len(wt)}')
print(f'Session keys: {list(m[\"sessions\"][0].keys())}')
"
```

Expected: `worktree_name` should now appear in session entries.

**Step 4: Restart watch with correct team**

Run: `karma watch --team Ayush-stealing-prompts &`

Verify output includes:
```
Found N CLI + M Desktop worktree dir(s) for 'claude-code-karma'
Watching: claude-code-karma (...)
Watching worktree: syncthing-sync-design (...)
...
```

**Step 5: Verify Syncthing picks up changes**

Check Syncthing web UI or:
```bash
curl -s -H "X-API-Key:$(python3 -c "import json; print(json.load(open('$HOME/.claude_karma/sync-config.json'))['syncthing']['api_key'])")" \
  http://127.0.0.1:8384/rest/db/status?folder=karma-out-jay-claude-code-karma | python3 -m json.tool | grep -E '"globalFiles|localFiles|needFiles'
```

Expected: `globalFiles` should increase to reflect worktree sessions.

---

## Task 8: Update diagnostic tests to reflect fixed state

Now that the fixes are in place, update the diagnostic tests to verify the FIXED state.

**Files:**
- Modify: `cli/tests/test_sync_diagnostics.py`

**Step 1: Update assertions**

```python
# In TestSyncDiagnostics, update test_outbox_manifest_is_stale:

    def test_outbox_manifest_includes_worktree_sessions(self):
        """After fix: outbox manifest should include worktree sessions."""
        manifest_path = (
            KARMA_BASE / "remote-sessions" / "jay" / MAIN_ENCODED / "manifest.json"
        )
        if not manifest_path.exists():
            pytest.skip("No outbox manifest")

        manifest = json.loads(manifest_path.read_text())
        sessions_with_wt = [
            s for s in manifest["sessions"] if s.get("worktree_name")
        ]
        assert len(sessions_with_wt) > 0, (
            "Outbox should now include worktree sessions after fix"
        )
        # Verify the worktree_name field exists in session entries
        assert "worktree_name" in manifest["sessions"][0], (
            "Session entries should have worktree_name field"
        )

    def test_desktop_worktrees_now_discoverable(self):
        """After fix: Desktop worktrees should be found by find_desktop_worktree_dirs."""
        from karma.worktree_discovery import find_desktop_worktree_dirs

        desktop_dirs = find_desktop_worktree_dirs(
            project_name="claude-karma",
            projects_dir=PROJECTS_DIR,
        )
        # Should find focused-jepsen and lucid-villani
        assert len(desktop_dirs) >= 2, (
            f"Expected >=2 Desktop worktree dirs, found {len(desktop_dirs)}"
        )
```

**Step 2: Run updated diagnostics**

Run: `cd cli && pytest tests/test_sync_diagnostics.py -v`
Expected: All PASS (reflecting the fixed state)

**Step 3: Commit**

```bash
git add cli/tests/test_sync_diagnostics.py
git commit -m "test(cli): update diagnostic tests for fixed sync pipeline

Tests now verify that worktree sessions are included in the outbox
and Desktop worktrees are discoverable."
```

---

## Task 9: Run full test suite and verify no regressions

**Step 1: Run all CLI tests**

Run: `cd cli && pytest -v`
Expected: All tests PASS

**Step 2: Run API tests**

Run: `cd api && pytest tests/ -v --timeout=30`
Expected: All pass (no API changes in this plan)

**Step 3: Verify sync status**

Run: `karma status`
Expected: Shows local + worktree + packaged counts with "up to date" or small gap.

---

## Summary

| Task | What | Files Changed | Tests |
|------|------|---------------|-------|
| 1 | Diagnostic tests (document current bugs) | +`test_sync_diagnostics.py` | 4 |
| 2 | Desktop worktree discovery | `worktree_discovery.py`, `test_worktree_discovery.py` | 6 |
| 3 | `project_name_from_path` helper | `worktree_discovery.py`, `test_worktree_discovery.py` | 5 |
| 4 | Wire Desktop discovery into sync/watch | `sync.py`, `main.py`, `test_packager.py` | 2 |
| 5 | Unified `find_all_worktree_dirs` | `worktree_discovery.py`, `sync.py`, `main.py` | 2 |
| 6 | Status shows Desktop worktree counts | `main.py` | 0 |
| 7 | Manual verification (kill/restart watch) | — (operational) | 0 |
| 8 | Update diagnostic tests for fixed state | `test_sync_diagnostics.py` | 2 |
| 9 | Full suite verification | — | all |

**What this fixes:**
- Worktree sessions (CLI + Desktop) are now packaged into the outbox
- `karma watch` discovers and monitors worktree dirs dynamically
- `karma status` shows accurate session counts across all sources
- Stale watch process is killed and restarted with correct team

**What this does NOT change (already works):**
- `api/services/remote_sessions.py` — inbox→project mapping is correct
- `api/services/desktop_sessions.py` — API-side worktree→project mapping is correct
- `api/routers/projects.py` — merges local + worktree + remote sessions correctly
- Syncthing folder setup — inbox/outbox paths use receiver's local encoded name

**Future work (out of scope):**
- Unify the 3 mapping systems (API utils, desktop_sessions, remote_sessions) into a single service
- Hook-based packaging trigger (SessionEnd → auto-package)
- launchd/systemd for persistent `karma watch`
