# Complete Sync Pipeline — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make remote sessions fully viewable by syncing all data sources (tasks, deep metadata) and indexing them at the same depth as local sessions.

**Architecture:** Three layers — (1) sync task files alongside sessions/todos in the CLI packager, (2) deep-index remote sessions with full `Session._load_metadata()` instead of lazy first/last-line parsing, (3) route `/sessions/{uuid}` to find remote sessions transparently so the frontend works without changes.

**Tech Stack:** Python 3.9+, FastAPI, Pydantic 2.x, SQLite, pytest

**Prior plan:** `docs/plans/2026-03-05-syncthing-worktree-sync-plan.md` (worktree sync — completed)

**Key insight:** Remote sessions already land on disk via Syncthing at `~/.claude_karma/remote-sessions/{user_id}/{encoded_name}/sessions/{uuid}.jsonl`. The API can serve them through the same `Session.from_path()` used for local sessions — the gap is (a) missing task files, (b) shallow indexing, and (c) no path resolution from `/sessions/{uuid}`.

---

## Task 1: Sync task directories in the CLI packager

Tasks live in `~/.claude/tasks/{uuid}/` as individual JSON files (`1.json`, `2.json`, etc.). The packager already copies todos — mirror that pattern for tasks.

**Files:**
- Modify: `cli/karma/packager.py:99-115` (package method)
- Modify: `cli/tests/test_packager.py`

**Step 1: Write failing tests**

Add to `cli/tests/test_packager.py`:

```python
class TestTaskSyncing:
    def test_package_copies_task_files(self, tmp_path):
        """Tasks from ~/.claude/tasks/{uuid}/ should be copied."""
        # Create project dir structure: .claude/projects/-My-project/
        claude_dir = tmp_path / ".claude"
        project_dir = claude_dir / "projects" / "-My-project"
        project_dir.mkdir(parents=True)
        (project_dir / "session-abc.jsonl").write_text(
            '{"type":"user","message":{"role":"user","content":"hello"}}\n'
        )

        # Create task dir: .claude/tasks/session-abc/
        tasks_dir = claude_dir / "tasks" / "session-abc"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "1.json").write_text(
            '{"id":"1","subject":"Fix bug","status":"completed"}\n'
        )
        (tasks_dir / "2.json").write_text(
            '{"id":"2","subject":"Add test","status":"pending"}\n'
        )

        staging = tmp_path / "staging"
        packager = SessionPackager(
            project_dir=project_dir,
            user_id="alice",
            machine_id="mac",
        )
        packager.package(staging_dir=staging)

        assert (staging / "tasks" / "session-abc" / "1.json").exists()
        assert (staging / "tasks" / "session-abc" / "2.json").exists()

    def test_package_skips_missing_task_dir(self, mock_claude_project, tmp_path):
        """Sessions without task dirs should not cause errors."""
        staging = tmp_path / "staging"
        packager = SessionPackager(
            project_dir=mock_claude_project,
            user_id="alice",
            machine_id="mac",
        )
        manifest = packager.package(staging_dir=staging)
        assert manifest.session_count == 2
        # tasks dir should not exist if no tasks
        assert not (staging / "tasks").exists()

    def test_package_copies_worktree_tasks(self, tmp_path):
        """Tasks for worktree sessions should also be copied."""
        claude_dir = tmp_path / ".claude"
        main_dir = claude_dir / "projects" / "-Users-jay-karma"
        main_dir.mkdir(parents=True)
        (main_dir / "main-s.jsonl").write_text('{"type":"user"}\n')

        wt_dir = claude_dir / "projects" / "-Users-jay-karma--claude-worktrees-feat"
        wt_dir.mkdir(parents=True)
        (wt_dir / "wt-s.jsonl").write_text('{"type":"user"}\n')

        # Task for worktree session
        tasks_dir = claude_dir / "tasks" / "wt-s"
        tasks_dir.mkdir(parents=True)
        (tasks_dir / "1.json").write_text('{"id":"1","subject":"WT task","status":"pending"}\n')

        staging = tmp_path / "staging"
        packager = SessionPackager(
            project_dir=main_dir,
            user_id="jay",
            machine_id="mac",
            extra_dirs=[wt_dir],
        )
        packager.package(staging_dir=staging)

        assert (staging / "tasks" / "wt-s" / "1.json").exists()
```

**Step 2: Run tests to verify they fail**

Run: `cd cli && pytest tests/test_packager.py::TestTaskSyncing -v`
Expected: FAIL — task files not copied (no `tasks/` dir in staging)

**Step 3: Add task copying to `package()` method**

In `cli/karma/packager.py`, add after the todos block (around line 115):

```python
        # Copy tasks if they exist
        tasks_base = self.project_dir.parent.parent / "tasks"
        if tasks_base.is_dir():
            tasks_staging = staging_dir / "tasks"
            for session_entry in sessions:
                task_dir = tasks_base / session_entry.uuid
                if task_dir.is_dir():
                    tasks_staging.mkdir(exist_ok=True)
                    shutil.copytree(
                        task_dir,
                        tasks_staging / session_entry.uuid,
                        dirs_exist_ok=True,
                    )
```

**Step 4: Run tests to verify they pass**

Run: `cd cli && pytest tests/test_packager.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add cli/karma/packager.py cli/tests/test_packager.py
git commit -m "feat(cli): sync task directories alongside sessions and todos

Copies ~/.claude/tasks/{uuid}/ into staging/tasks/{uuid}/ for each
session, including worktree sessions. Mirrors the existing todo pattern."
```

---

## Task 2: Deep-index remote sessions

Currently `index_remote_sessions()` (indexer.py:232-315) only reads first/last JSONL lines. Local sessions go through `_index_session()` (indexer.py:318-543) which calls `Session._load_metadata()` and populates session_tools, session_skills, session_commands, subagent_invocations, etc.

The fix: call `_index_session()` for remote sessions instead of the shallow parsing.

**Files:**
- Modify: `api/db/indexer.py:232-315` (index_remote_sessions function)
- Modify: `api/tests/test_indexer.py` (or create if missing)

**Step 1: Write failing test**

Create `api/tests/test_remote_indexing.py`:

```python
"""Tests for deep remote session indexing."""

import json
import sqlite3
from pathlib import Path

import pytest

from db.indexer import index_remote_sessions, _index_session
from db.schema import init_db


@pytest.fixture
def db_conn(tmp_path):
    """Create an in-memory SQLite DB with schema."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    init_db(conn)
    return conn


@pytest.fixture
def remote_sessions_dir(tmp_path):
    """Create fake remote session files with tool usage."""
    remote_base = tmp_path / "remote-sessions"

    # Bob's session with tool usage
    bob_sessions = remote_base / "bob" / "-Users-bob-myapp" / "sessions"
    bob_sessions.mkdir(parents=True)

    # JSONL with actual tool usage for deep indexing
    lines = [
        json.dumps({
            "type": "user",
            "message": {
                "role": "user",
                "content": "fix the bug",
            },
            "timestamp": "2026-03-05T10:00:00Z",
            "uuid": "msg-001",
        }),
        json.dumps({
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "toolu_1", "name": "Read", "input": {"file_path": "/foo.py"}},
                    {"type": "text", "text": "Let me read the file."},
                ],
            },
            "timestamp": "2026-03-05T10:00:05Z",
        }),
        json.dumps({
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_1", "content": "file contents here"},
                ],
            },
            "timestamp": "2026-03-05T10:00:06Z",
        }),
        json.dumps({
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": "toolu_2", "name": "Edit", "input": {"file_path": "/foo.py"}},
                ],
            },
            "timestamp": "2026-03-05T10:00:10Z",
        }),
    ]
    (bob_sessions / "remote-session-001.jsonl").write_text("\n".join(lines) + "\n")

    # Manifest (needed by some code paths)
    manifest = {
        "user_id": "bob",
        "machine_id": "bob-mac",
        "project_path": "/Users/bob/myapp",
        "project_encoded": "-Users-bob-myapp",
        "session_count": 1,
        "sessions": [{"uuid": "remote-session-001", "mtime": "2026-03-05T10:00:00Z", "size_bytes": 500}],
    }
    manifest_dir = remote_base / "bob" / "-Users-bob-myapp"
    (manifest_dir / "manifest.json").write_text(json.dumps(manifest))

    return remote_base


class TestDeepRemoteIndexing:
    def test_remote_session_has_tools_indexed(self, db_conn, remote_sessions_dir, tmp_path, monkeypatch):
        """Remote sessions should have session_tools populated."""
        monkeypatch.setattr("db.indexer.settings.karma_base", tmp_path)
        monkeypatch.setattr("db.indexer._get_local_user_id", lambda: "alice")

        index_remote_sessions(db_conn)

        # Check session was indexed
        cursor = db_conn.execute(
            "SELECT uuid, source, remote_user_id FROM sessions WHERE uuid = ?",
            ("remote-session-001",),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[1] == "remote"
        assert row[2] == "bob"

        # Check tools were deep-indexed
        cursor = db_conn.execute(
            "SELECT tool_name, count FROM session_tools WHERE session_uuid = ?",
            ("remote-session-001",),
        )
        tools = {name: count for name, count in cursor.fetchall()}
        assert "Read" in tools
        assert "Edit" in tools

    def test_remote_session_has_message_count(self, db_conn, remote_sessions_dir, tmp_path, monkeypatch):
        """Remote sessions should have accurate message_count from deep indexing."""
        monkeypatch.setattr("db.indexer.settings.karma_base", tmp_path)
        monkeypatch.setattr("db.indexer._get_local_user_id", lambda: "alice")

        index_remote_sessions(db_conn)

        cursor = db_conn.execute(
            "SELECT message_count FROM sessions WHERE uuid = ?",
            ("remote-session-001",),
        )
        row = cursor.fetchone()
        assert row is not None
        assert row[0] >= 2  # At least user + assistant messages
```

**Step 2: Run tests to verify they fail**

Run: `cd api && pytest tests/test_remote_indexing.py -v`
Expected: FAIL — session_tools empty for remote sessions (shallow indexing)

**Step 3: Modify `index_remote_sessions()` to use `_index_session()`**

In `api/db/indexer.py`, replace the lazy parsing in `index_remote_sessions()` with a call to `_index_session()`. Find the section that does the shallow first/last line parsing and replace it:

```python
# Replace the shallow parsing block with:
_index_session(
    conn=conn,
    jsonl_path=jsonl_path,
    encoded_name=local_encoded or encoded_name,
    mtime=jsonl_path.stat().st_mtime,
    size=jsonl_path.stat().st_size,
    source="remote",
    remote_user_id=user_id,
    remote_machine_id=user_id,
    source_encoded_name=encoded_name,
)
stats["indexed"] += 1
```

**Step 4: Run tests**

Run: `cd api && pytest tests/test_remote_indexing.py -v`
Expected: All PASS

**Step 5: Verify no regressions**

Run: `cd api && pytest tests/ -v --timeout=30`
Expected: All PASS

**Step 6: Commit**

```bash
git add api/db/indexer.py api/tests/test_remote_indexing.py
git commit -m "feat(api): deep-index remote sessions with full metadata

Remote sessions now go through _index_session() instead of lazy
first/last-line parsing. This populates session_tools, session_skills,
session_commands, and subagent_invocations — matching local sessions."
```

---

## Task 3: Route `/sessions/{uuid}` to find remote sessions

The main session endpoint currently only looks in `~/.claude/projects/`. It needs to fall back to `find_remote_session()` when a UUID isn't found locally.

**Files:**
- Modify: `api/routers/sessions.py` (get_session endpoint)
- Modify: `api/tests/` (add test)

**Step 1: Identify the current session resolution**

The endpoint at `GET /sessions/{uuid}` resolves sessions via the SQLite index. Check how `get_session()` finds the JSONL path. It likely queries the `sessions` table for the UUID, gets the `project_encoded_name`, then constructs the path.

Read `api/routers/sessions.py` to find the `get_session` function and understand the path resolution logic. The key change: when local lookup fails, try `find_remote_session(uuid)`.

**Step 2: Write failing test**

```python
# Add to api/tests/test_remote_session_endpoint.py

def test_session_endpoint_finds_remote_session(client, tmp_path, monkeypatch):
    """GET /sessions/{uuid} should find remote sessions."""
    import json

    # Create remote session file
    remote_base = tmp_path / "remote-sessions" / "bob" / "-Users-bob-app" / "sessions"
    remote_base.mkdir(parents=True)
    lines = [
        json.dumps({"type": "user", "message": {"role": "user", "content": "hello"}, "timestamp": "2026-03-05T10:00:00Z"}),
        json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": "hi"}]}, "timestamp": "2026-03-05T10:00:05Z"}),
    ]
    (remote_base / "remote-uuid-001.jsonl").write_text("\n".join(lines) + "\n")

    monkeypatch.setattr("config.settings.karma_base", tmp_path)

    response = client.get("/sessions/remote-uuid-001")
    # Should find it via remote session fallback
    assert response.status_code == 200
```

**Step 3: Add remote fallback to session endpoint**

In the `get_session()` function, after the local session lookup fails (404), add:

```python
from services.remote_sessions import find_remote_session

# ... existing local lookup ...
if session is None:
    remote_result = find_remote_session(uuid)
    if remote_result:
        session = remote_result.session
```

**Step 4: Run tests**

Run: `cd api && pytest tests/test_remote_session_endpoint.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add api/routers/sessions.py api/tests/test_remote_session_endpoint.py
git commit -m "feat(api): /sessions/{uuid} falls back to remote sessions

When a session UUID is not found locally, the endpoint now searches
remote-sessions/ directories. This makes remote sessions accessible
through the same endpoints as local sessions — no frontend changes needed."
```

---

## Task 4: Serve remote session subagents and tool results

Remote session subagent and tool-result files live alongside the JSONL in the Syncthing outbox. The session detail endpoints (`/sessions/{uuid}/subagents`, `/sessions/{uuid}/tools`, `/sessions/{uuid}/file-activity`, `/sessions/{uuid}/timeline`) need the correct base directory to find associated files.

**Files:**
- Modify: `api/routers/sessions.py` (subagent/timeline/file-activity endpoints)
- Test: Extend the remote session test

**Step 1: Verify the problem**

When `Session.from_path(jsonl_path)` is called with a remote JSONL, the session's `project_dir` points to the remote outbox directory. Subagent files are at `{outbox}/sessions/{uuid}/subagents/`. Check if `session.list_subagents()` uses `session.project_dir / uuid / "subagents"` — if so, it should already work since the packager copies the directory structure.

Read the relevant code in `api/models/session.py` to verify. If it works already, this task becomes a verification-only task.

**Step 2: Write test to verify**

```python
def test_remote_session_subagents_accessible(tmp_path, monkeypatch):
    """Subagent files should be loadable from remote session directories."""
    import json
    from models.session import Session

    # Create remote session with subagent
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir()
    (sessions_dir / "remote-s.jsonl").write_text('{"type":"user"}\n')
    sub_dir = sessions_dir / "remote-s" / "subagents"
    sub_dir.mkdir(parents=True)
    (sub_dir / "agent-a1.jsonl").write_text(
        json.dumps({"type": "user", "message": {"role": "user", "content": "sub task"}}) + "\n"
    )

    session = Session.from_path(sessions_dir / "remote-s.jsonl")
    agents = session.list_subagents()
    assert len(agents) >= 1
```

**Step 3: Run test**

Run: `cd api && pytest tests/test_remote_session_endpoint.py::test_remote_session_subagents_accessible -v`
Expected: PASS (if packager directory structure matches what Session expects)

If it fails, the fix will be adjusting `Session.list_subagents()` to look in the right directory relative to the JSONL path.

**Step 4: Commit (if changes needed)**

```bash
git add api/
git commit -m "feat(api): remote session subagents and tool results accessible

Verified that Session.from_path() with remote JSONL paths correctly
resolves subagent and tool-result directories."
```

---

## Task 5: Add project mapping for remote sessions

Remote sessions arrive with their original machine's encoded name (e.g., `-Users-bob-myapp`). The indexer needs to map this to the local project so remote sessions appear in the right project view.

**Files:**
- Check: `api/db/indexer.py` — `get_project_mapping()` function
- Modify if needed: The mapping logic

**Step 1: Understand current mapping**

Read `api/db/indexer.py` to find `get_project_mapping()`. It likely uses the sync-config.json to map `(user_id, encoded_name)` to a local project. Check if this already works correctly.

**Step 2: Write test**

```python
def test_remote_sessions_appear_in_local_project(db_conn, remote_sessions_dir, tmp_path, monkeypatch):
    """Remote sessions should be indexed under the local project name."""
    monkeypatch.setattr("db.indexer.settings.karma_base", tmp_path)
    monkeypatch.setattr("db.indexer._get_local_user_id", lambda: "alice")

    # Create project mapping in sync config
    sync_config = {
        "user_id": "alice",
        "machine_id": "alice-mac",
        "teams": {
            "team1": {
                "backend": "syncthing",
                "projects": {
                    "myapp": {
                        "path": "/Users/alice/myapp",
                        "encoded_name": "-Users-alice-myapp",
                    }
                },
                "syncthing_members": {
                    "bob": {"syncthing_device_id": "BOB-DEVICE"}
                },
            }
        },
    }
    import json
    (tmp_path / "sync-config.json").write_text(json.dumps(sync_config))

    index_remote_sessions(db_conn)

    # Session should be indexed under local project name
    cursor = db_conn.execute(
        "SELECT project_encoded_name, source_encoded_name FROM sessions WHERE uuid = ?",
        ("remote-session-001",),
    )
    row = cursor.fetchone()
    assert row is not None
    # project_encoded_name should be the LOCAL project's encoded name
    # source_encoded_name should be the REMOTE machine's encoded name
    assert row[1] == "-Users-bob-myapp"  # original source
```

**Step 3: Verify or fix mapping**

If the test passes, the mapping already works. If not, update `get_project_mapping()` to use sync-config.json team projects to build the mapping.

**Step 4: Commit**

```bash
git add api/db/indexer.py api/tests/test_remote_indexing.py
git commit -m "test(api): verify remote session project mapping

Confirmed that remote sessions are indexed under the correct local
project name via sync-config.json project mapping."
```

---

## Task 6: Full test suite verification

**Step 1: Run all CLI tests**

Run: `cd cli && pytest -v`
Expected: All PASS

**Step 2: Run all API tests**

Run: `cd api && pytest tests/ -v --timeout=30`
Expected: All PASS

**Step 3: Manual smoke test**

1. Start the API: `cd api && uvicorn main:app --reload --port 8000`
2. Start the frontend: `cd frontend && npm run dev`
3. If you have remote sessions synced, navigate to a remote session and verify:
   - Timeline shows events
   - File activity shows operations
   - Subagents are listed
   - Tasks/todos appear

---

## Summary

| Task | What | Files Changed | Priority |
|------|------|---------------|----------|
| 1 | Sync task directories | `packager.py`, `test_packager.py` | High |
| 2 | Deep-index remote sessions | `indexer.py`, `test_remote_indexing.py` | High |
| 3 | `/sessions/{uuid}` remote fallback | `sessions.py` router | High |
| 4 | Verify subagent/tool-result access | Tests only (likely) | Medium |
| 5 | Project mapping for remote sessions | `indexer.py` (verify/fix) | Medium |
| 6 | Full suite verification | — | Required |

**Not in scope (future work):**
- Frontend changes for remote session indicators (badges, user labels)
- Conflict resolution for duplicate session UUIDs across users
- Bandwidth optimization (delta sync, compression)
- `history.jsonl` syncing (global file, privacy concerns)
- Live session state syncing (ephemeral, local-only by design)
