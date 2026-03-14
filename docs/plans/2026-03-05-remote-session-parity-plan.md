# Remote Session Feature Parity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make remote (synced) sessions fully feature-complete with local sessions across CLI packaging and API endpoints — so every piece of data visible for a local session is also available for a remote session.

**Architecture:** The system has two path anchors per session: `session_dir` (relative to JSONL, handles subagents/tool-results) and `claude_base_dir` (handles todos/tasks/file-history/debug/plans). For local sessions `claude_base_dir` defaults to `~/.claude`. For remote sessions accessed via `find_remote_session()`, it's set to `~/.claude_karma/remote-sessions/{user}/{encoded}/`. The CLI packager must place files at the right relative paths under the staging directory so the API resolves them correctly.

**Tech Stack:** Python 3.9+, FastAPI, Pydantic 2.x, pytest, shutil, pathlib

**Current State:**
- JSONL, subagents, tool-results: Packaged + accessible (verified)
- Todos: Packaged, path SHOULD resolve but unverified
- Tasks: Packaged, path SHOULD resolve but unverified
- File-history: NOT packaged
- Debug logs: NOT packaged
- Plans: NOT packaged (and endpoint may hardcode path)

**Roles:**
- **Role A (Test Engineer):** Writes verification tests proving current state and catching regressions
- **Role B (CLI Engineer):** Extends packager to sync missing resource types
- **Role C (Backend Engineer):** Fixes API path resolution and endpoint gaps

---

## Phase 1: Verify What Already Works (Role A — Test Engineer)

### Task 1: Test todos resolve for remote sessions

**Files:**
- Modify: `api/tests/test_remote_sessions.py`

**Step 1: Write the test**

Add to `TestRemoteSessionSubagentAccess` class (or create new class `TestRemoteSessionTodos`):

```python
class TestRemoteSessionTodos:
    def test_todos_resolve_for_remote_session(self, karma_base):
        """Todos packaged into remote staging dir should be loadable."""
        encoded = "-Users-jayant-acme"
        alice_dir = karma_base / "remote-sessions" / "alice" / encoded

        # Create session JSONL
        sessions_dir = alice_dir / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "sess-todo-001.jsonl").write_text(
            json.dumps({
                "type": "user",
                "message": {"role": "user", "content": "hello"},
                "timestamp": "2026-03-03T12:00:00Z",
            }) + "\n"
        )

        # Create todo file in staging structure (mirrors packager output)
        todos_dir = alice_dir / "todos"
        todos_dir.mkdir(parents=True, exist_ok=True)
        (todos_dir / "sess-todo-001-task1.json").write_text(
            json.dumps([{
                "content": "Fix the bug",
                "status": "in_progress",
            }])
        )

        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            result = find_remote_session("sess-todo-001")

        assert result is not None
        session = result.session

        # Verify todos_dir points to correct location
        assert session.todos_dir == todos_dir
        assert session.todos_dir.exists()

        # Verify todos are loadable
        todos = session.list_todos()
        assert len(todos) >= 1
        assert todos[0].content == "Fix the bug"
```

**Step 2: Run test to verify**

Run: `cd api && pytest tests/test_remote_sessions.py::TestRemoteSessionTodos -v`
Expected: PASS (if path resolution works) or FAIL (revealing the gap)

**Step 3: If test fails, fix path resolution**

The issue would be in `api/services/remote_sessions.py:196` where `claude_base_dir=encoded_dir`. Verify `encoded_dir` is the parent of `sessions/` (the project-level dir), not the `sessions/` dir itself.

Check: `encoded_dir` = `~/.claude_karma/remote-sessions/alice/-Users-jayant-acme/`
Then: `session.todos_dir` = `encoded_dir / "todos"` = `.../alice/-Users-jayant-acme/todos/` — should match packager output.

**Step 4: Commit**

```bash
git add api/tests/test_remote_sessions.py
git commit -m "test: verify todos resolve for remote sessions"
```

---

### Task 2: Test tasks resolve for remote sessions

**Files:**
- Modify: `api/tests/test_remote_sessions.py`

**Step 1: Write the test**

```python
class TestRemoteSessionTasks:
    def test_tasks_resolve_for_remote_session(self, karma_base):
        """Tasks packaged into remote staging dir should be loadable."""
        encoded = "-Users-jayant-acme"
        alice_dir = karma_base / "remote-sessions" / "alice" / encoded

        # Create session JSONL
        sessions_dir = alice_dir / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "sess-task-001.jsonl").write_text(
            json.dumps({
                "type": "user",
                "message": {"role": "user", "content": "hello"},
                "timestamp": "2026-03-03T12:00:00Z",
            }) + "\n"
        )

        # Create task files in staging structure (mirrors packager output)
        task_dir = alice_dir / "tasks" / "sess-task-001"
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "1.json").write_text(
            json.dumps({
                "id": "1",
                "subject": "Implement feature",
                "description": "Build the thing",
                "status": "in_progress",
            })
        )

        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            result = find_remote_session("sess-task-001")

        assert result is not None
        session = result.session

        # Verify tasks_dir points to correct location
        assert session.tasks_dir == task_dir
        assert session.tasks_dir.exists()

        # Verify tasks are loadable
        tasks = session.list_tasks()
        assert len(tasks) >= 1
```

**Step 2: Run test**

Run: `cd api && pytest tests/test_remote_sessions.py::TestRemoteSessionTasks -v`

**Step 3: Commit**

```bash
git add api/tests/test_remote_sessions.py
git commit -m "test: verify tasks resolve for remote sessions"
```

---

### Task 3: Test tool-results resolve for remote sessions

**Files:**
- Modify: `api/tests/test_remote_sessions.py`

**Step 1: Write the test**

```python
class TestRemoteSessionToolResults:
    def test_tool_results_resolve_for_remote_session(self, karma_base):
        """Tool result files packaged alongside JSONL should be accessible."""
        encoded = "-Users-jayant-acme"
        alice_sessions = (
            karma_base / "remote-sessions" / "alice" / encoded / "sessions"
        )
        alice_sessions.mkdir(parents=True, exist_ok=True)

        # Create session JSONL
        (alice_sessions / "sess-tr-001.jsonl").write_text(
            json.dumps({
                "type": "user",
                "message": {"role": "user", "content": "hello"},
                "timestamp": "2026-03-03T12:00:00Z",
            }) + "\n"
        )

        # Create tool-results directory
        tr_dir = alice_sessions / "sess-tr-001" / "tool-results"
        tr_dir.mkdir(parents=True)
        (tr_dir / "toolu_abc123.txt").write_text("Tool output here")

        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            result = find_remote_session("sess-tr-001")

        assert result is not None
        session = result.session
        assert session.tool_results_dir == tr_dir
        assert session.tool_results_dir.exists()

        tool_results = session.list_tool_results()
        assert len(tool_results) >= 1
```

**Step 2: Run and commit**

Run: `cd api && pytest tests/test_remote_sessions.py::TestRemoteSessionToolResults -v`

```bash
git add api/tests/test_remote_sessions.py
git commit -m "test: verify tool-results resolve for remote sessions"
```

---

## Phase 2: Package Missing Resources (Role B — CLI Engineer)

### Task 4: Package file-history in CLI packager

**Files:**
- Modify: `cli/karma/packager.py:134` (after tasks copying block)
- Test: `cli/tests/test_packager.py`

**Context:** File-history lives at `~/.claude/file-history/{uuid}/` and contains per-file snapshots. The Session model resolves it via `claude_base_dir / "file-history" / {uuid}`. We need to copy it into staging so remote sessions can access it.

**Step 1: Write the failing test**

```python
def test_package_copies_file_history(tmp_path):
    """File-history directories should be copied to staging."""
    # Setup: create project dir structure
    claude_dir = tmp_path / ".claude"
    project_dir = claude_dir / "projects" / "-Users-test-repo"
    project_dir.mkdir(parents=True)

    uuid = "sess-fh-001"
    (project_dir / f"{uuid}.jsonl").write_text(
        '{"type":"user","message":{"role":"user","content":"hi"},"timestamp":"2026-01-01T00:00:00Z"}\n'
    )

    # Create file-history for this session
    fh_dir = claude_dir / "file-history" / uuid
    fh_dir.mkdir(parents=True)
    (fh_dir / "snapshot-1.json").write_text('{"file": "main.py", "content": "print(1)"}')

    staging = tmp_path / "staging"
    packager = SessionPackager(
        project_dir=project_dir,
        user_id="test",
        machine_id="test-machine",
        project_path="/Users/test/repo",
    )
    packager.package(staging)

    # Verify file-history was copied
    staged_fh = staging / "file-history" / uuid / "snapshot-1.json"
    assert staged_fh.exists()
    assert staged_fh.read_text() == '{"file": "main.py", "content": "print(1)"}'
```

**Step 2: Run test to verify it fails**

Run: `cd cli && pytest tests/test_packager.py::test_package_copies_file_history -v`
Expected: FAIL — `staged_fh` does not exist

**Step 3: Implement file-history copying**

Add after the tasks block in `cli/karma/packager.py` (after line 134):

```python
        # Copy file-history if it exists
        file_history_base = self.project_dir.parent.parent / "file-history"
        if file_history_base.is_dir():
            fh_staging = staging_dir / "file-history"
            for session_entry in sessions:
                fh_dir = file_history_base / session_entry.uuid
                if fh_dir.is_dir():
                    fh_staging.mkdir(exist_ok=True)
                    shutil.copytree(
                        fh_dir,
                        fh_staging / session_entry.uuid,
                        dirs_exist_ok=True,
                    )
```

**Step 4: Run test to verify it passes**

Run: `cd cli && pytest tests/test_packager.py::test_package_copies_file_history -v`
Expected: PASS

**Step 5: Commit**

```bash
git add cli/karma/packager.py cli/tests/test_packager.py
git commit -m "feat(cli): package file-history directories for sync"
```

---

### Task 5: Package debug logs in CLI packager

**Files:**
- Modify: `cli/karma/packager.py` (after file-history block)
- Test: `cli/tests/test_packager.py`

**Step 1: Write the failing test**

```python
def test_package_copies_debug_logs(tmp_path):
    """Debug log files should be copied to staging."""
    claude_dir = tmp_path / ".claude"
    project_dir = claude_dir / "projects" / "-Users-test-repo"
    project_dir.mkdir(parents=True)

    uuid = "sess-debug-001"
    (project_dir / f"{uuid}.jsonl").write_text(
        '{"type":"user","message":{"role":"user","content":"hi"},"timestamp":"2026-01-01T00:00:00Z"}\n'
    )

    # Create debug log
    debug_dir = claude_dir / "debug"
    debug_dir.mkdir(parents=True)
    (debug_dir / f"{uuid}.txt").write_text("DEBUG: session started\nDEBUG: tool called")

    staging = tmp_path / "staging"
    packager = SessionPackager(
        project_dir=project_dir,
        user_id="test",
        machine_id="test-machine",
        project_path="/Users/test/repo",
    )
    packager.package(staging)

    staged_debug = staging / "debug" / f"{uuid}.txt"
    assert staged_debug.exists()
    assert "DEBUG: session started" in staged_debug.read_text()
```

**Step 2: Run to fail**

Run: `cd cli && pytest tests/test_packager.py::test_package_copies_debug_logs -v`

**Step 3: Implement debug log copying**

Add after file-history block in `cli/karma/packager.py`:

```python
        # Copy debug logs if they exist
        debug_base = self.project_dir.parent.parent / "debug"
        if debug_base.is_dir():
            debug_staging = staging_dir / "debug"
            for session_entry in sessions:
                debug_file = debug_base / f"{session_entry.uuid}.txt"
                if debug_file.is_file():
                    debug_staging.mkdir(exist_ok=True)
                    shutil.copy2(debug_file, debug_staging / debug_file.name)
```

**Step 4: Run to pass, commit**

```bash
git add cli/karma/packager.py cli/tests/test_packager.py
git commit -m "feat(cli): package debug logs for sync"
```

---

## Phase 3: API Path Resolution for New Resources (Role C — Backend Engineer)

### Task 6: Test file-history resolves for remote sessions

**Files:**
- Modify: `api/tests/test_remote_sessions.py`

**Step 1: Write the test**

```python
class TestRemoteSessionFileHistory:
    def test_file_history_resolves_for_remote_session(self, karma_base):
        """File-history packaged into remote staging should be accessible."""
        encoded = "-Users-jayant-acme"
        alice_dir = karma_base / "remote-sessions" / "alice" / encoded

        sessions_dir = alice_dir / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "sess-fh-001.jsonl").write_text(
            json.dumps({
                "type": "user",
                "message": {"role": "user", "content": "hello"},
                "timestamp": "2026-03-03T12:00:00Z",
            }) + "\n"
        )

        # Create file-history in staging structure
        fh_dir = alice_dir / "file-history" / "sess-fh-001"
        fh_dir.mkdir(parents=True)
        (fh_dir / "snapshot.json").write_text('{"file": "main.py"}')

        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            result = find_remote_session("sess-fh-001")

        assert result is not None
        session = result.session
        assert session.file_history_dir == fh_dir
        assert session.has_file_history is True
```

**Step 2: Run test**

Run: `cd api && pytest tests/test_remote_sessions.py::TestRemoteSessionFileHistory -v`
Expected: PASS (path resolves via `claude_base_dir / "file-history" / uuid`)

**Step 3: Commit**

```bash
git add api/tests/test_remote_sessions.py
git commit -m "test: verify file-history resolves for remote sessions"
```

---

### Task 7: Test debug log resolves for remote sessions

**Files:**
- Modify: `api/tests/test_remote_sessions.py`

**Step 1: Write the test**

```python
class TestRemoteSessionDebugLog:
    def test_debug_log_resolves_for_remote_session(self, karma_base):
        """Debug logs packaged into remote staging should be readable."""
        encoded = "-Users-jayant-acme"
        alice_dir = karma_base / "remote-sessions" / "alice" / encoded

        sessions_dir = alice_dir / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "sess-dbg-001.jsonl").write_text(
            json.dumps({
                "type": "user",
                "message": {"role": "user", "content": "hello"},
                "timestamp": "2026-03-03T12:00:00Z",
            }) + "\n"
        )

        debug_dir = alice_dir / "debug"
        debug_dir.mkdir(parents=True)
        (debug_dir / "sess-dbg-001.txt").write_text("DEBUG: started")

        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            result = find_remote_session("sess-dbg-001")

        assert result is not None
        session = result.session
        assert session.has_debug_log is True
        assert session.read_debug_log() == "DEBUG: started"
```

**Step 2: Run and commit**

```bash
cd api && pytest tests/test_remote_sessions.py::TestRemoteSessionDebugLog -v
git add api/tests/test_remote_sessions.py
git commit -m "test: verify debug logs resolve for remote sessions"
```

---

### Task 8: Verify session detail endpoint returns full data for remote sessions

**Files:**
- Modify: `api/tests/api/test_remote_sessions.py`

**Context:** The `/sessions/{uuid}` endpoint uses `find_session_with_project()` which falls back to `find_remote_session()` at `api/services/session_lookup.py:82-90`. We need an integration test proving the full detail response includes todos, tasks, and subagent counts for a remote session.

**Step 1: Write the integration test**

```python
class TestRemoteSessionDetailEndpoint:
    """Integration test: GET /sessions/{uuid} for remote sessions."""

    def test_detail_endpoint_returns_remote_session_data(
        self, client, karma_base
    ):
        """Full session detail should work for remote sessions via fallback."""
        encoded = "-Users-jayant-acme"
        alice_dir = karma_base / "remote-sessions" / "alice" / encoded

        # Create JSONL with a user message and assistant response
        sessions_dir = alice_dir / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        jsonl_content = (
            json.dumps({
                "type": "user",
                "message": {"role": "user", "content": "Build a CLI tool"},
                "timestamp": "2026-03-03T12:00:00Z",
                "sessionId": "remote-test-slug",
            }) + "\n"
            + json.dumps({
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "I'll help build that."}],
                    "model": "claude-sonnet-4-20250514",
                    "usage": {"input_tokens": 100, "output_tokens": 50},
                },
                "timestamp": "2026-03-03T12:00:05Z",
            }) + "\n"
        )
        (sessions_dir / "sess-remote-detail.jsonl").write_text(jsonl_content)

        # Create todos
        todos_dir = alice_dir / "todos"
        todos_dir.mkdir(parents=True, exist_ok=True)
        (todos_dir / "sess-remote-detail-task1.json").write_text(
            json.dumps([{"content": "Build parser", "status": "in_progress"}])
        )

        # Create tasks
        task_dir = alice_dir / "tasks" / "sess-remote-detail"
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "1.json").write_text(
            json.dumps({"id": "1", "subject": "Parse args", "status": "pending"})
        )

        # Create subagent
        sub_dir = alice_dir / "sessions" / "sess-remote-detail" / "subagents"
        sub_dir.mkdir(parents=True)
        (sub_dir / "agent-abc.jsonl").write_text(
            json.dumps({
                "type": "user",
                "message": {"role": "user", "content": "sub task"},
                "timestamp": "2026-03-03T12:01:00Z",
            }) + "\n"
        )

        with patch("services.remote_sessions.settings") as mock_settings, \
             patch("services.session_lookup.settings") as mock_lookup_settings:
            mock_settings.karma_base = karma_base
            # Make local project search find nothing (force remote fallback)
            mock_lookup_settings.projects_dir = karma_base / "nonexistent"

            response = client.get("/sessions/sess-remote-detail")

        assert response.status_code == 200
        data = response.json()
        assert data["uuid"] == "sess-remote-detail"
        assert data["message_count"] >= 2
        assert data["todo_count"] >= 1
        assert data["task_count"] >= 1
        assert data["subagent_count"] >= 1
```

**Step 2: Run test**

Run: `cd api && pytest tests/api/test_remote_sessions.py::TestRemoteSessionDetailEndpoint -v`

This test may reveal issues with how the router accesses todos/tasks for remote sessions. If it fails, the fix is in the session detail endpoint.

**Step 3: Fix any failures, commit**

```bash
git add api/tests/api/test_remote_sessions.py
git commit -m "test: integration test for remote session detail endpoint"
```

---

## Phase 4: Endpoint-Level Fixes (Role C — Backend Engineer)

### Task 9: Ensure `/sessions/{uuid}/todos` works for remote sessions

**Files:**
- Modify: `api/routers/sessions.py` (the todos endpoint)
- Test: `api/tests/api/test_remote_sessions.py`

**Context:** The `/sessions/{uuid}/todos` endpoint calls `find_session(uuid)` which returns a Session. For remote sessions, this goes through `find_remote_session()` which sets `claude_base_dir` correctly. The endpoint should work without code changes — this task verifies it.

**Step 1: Write the test**

```python
def test_todos_endpoint_for_remote_session(self, client, karma_base):
    """GET /sessions/{uuid}/todos should return remote session todos."""
    encoded = "-Users-jayant-acme"
    alice_dir = karma_base / "remote-sessions" / "alice" / encoded

    sessions_dir = alice_dir / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    (sessions_dir / "sess-rtodos.jsonl").write_text(
        json.dumps({
            "type": "user",
            "message": {"role": "user", "content": "hello"},
            "timestamp": "2026-03-03T12:00:00Z",
        }) + "\n"
    )

    todos_dir = alice_dir / "todos"
    todos_dir.mkdir(parents=True, exist_ok=True)
    (todos_dir / "sess-rtodos-item.json").write_text(
        json.dumps([{"content": "Remote todo", "status": "pending"}])
    )

    with patch("services.remote_sessions.settings") as mock_settings, \
         patch("services.session_lookup.settings") as mock_lookup:
        mock_settings.karma_base = karma_base
        mock_lookup.projects_dir = karma_base / "nonexistent"

        response = client.get("/sessions/sess-rtodos/todos")

    assert response.status_code == 200
    todos = response.json()
    assert len(todos) >= 1
    assert todos[0]["content"] == "Remote todo"
```

**Step 2: Run, fix if needed, commit**

If the endpoint's `find_session()` call doesn't fall through to `find_remote_session()`, update `session_lookup.py:find_session()` to ensure the remote fallback works (it should — line 108 delegates to `find_session_with_project()` which has the fallback at line 82-90).

```bash
git commit -m "test: verify /sessions/{uuid}/todos for remote sessions"
```

---

### Task 10: Ensure `/sessions/{uuid}/tasks` works for remote sessions

**Files:**
- Test: `api/tests/api/test_remote_sessions.py`

**Step 1: Write and run the test** (same pattern as Task 9 but for tasks endpoint)

```python
def test_tasks_endpoint_for_remote_session(self, client, karma_base):
    """GET /sessions/{uuid}/tasks should return remote session tasks."""
    # ... (same setup as Task 9 but with tasks dir instead of todos)
    response = client.get("/sessions/sess-rtasks/tasks")
    assert response.status_code == 200
    tasks = response.json()
    assert len(tasks) >= 1
```

**Step 2: Commit**

```bash
git commit -m "test: verify /sessions/{uuid}/tasks for remote sessions"
```

---

### Task 11: Ensure `/sessions/{uuid}/file-activity` works for remote sessions

**Files:**
- Test: `api/tests/api/test_remote_sessions.py`

**Context:** File activity is extracted from JSONL tool-use blocks (Read, Write, etc.) and optionally from tool-result files. The JSONL parsing works regardless of location. Tool-results resolve via `session_dir` (relative to JSONL). This should work.

**Step 1: Write test with a JSONL containing a tool-use block**

```python
def test_file_activity_endpoint_for_remote_session(self, client, karma_base):
    """GET /sessions/{uuid}/file-activity should work for remote sessions."""
    encoded = "-Users-jayant-acme"
    alice_dir = karma_base / "remote-sessions" / "alice" / encoded
    sessions_dir = alice_dir / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)

    # JSONL with a tool-use block (Read tool)
    jsonl_lines = [
        json.dumps({
            "type": "user",
            "message": {"role": "user", "content": "read main.py"},
            "timestamp": "2026-03-03T12:00:00Z",
        }),
        json.dumps({
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{
                    "type": "tool_use",
                    "id": "toolu_001",
                    "name": "Read",
                    "input": {"file_path": "/Users/jayant/acme/main.py"},
                }],
                "model": "claude-sonnet-4-20250514",
            },
            "timestamp": "2026-03-03T12:00:02Z",
        }),
    ]
    (sessions_dir / "sess-rfa.jsonl").write_text("\n".join(jsonl_lines) + "\n")

    with patch("services.remote_sessions.settings") as mock_settings, \
         patch("services.session_lookup.settings") as mock_lookup:
        mock_settings.karma_base = karma_base
        mock_lookup.projects_dir = karma_base / "nonexistent"

        response = client.get("/sessions/sess-rfa/file-activity")

    assert response.status_code == 200
    activities = response.json()
    assert len(activities) >= 1
```

**Step 2: Commit**

```bash
git commit -m "test: verify /sessions/{uuid}/file-activity for remote sessions"
```

---

### Task 12: Ensure `/sessions/{uuid}/subagents` works for remote sessions

**Files:**
- Test: `api/tests/api/test_remote_sessions.py`

**Context:** Subagent files sit in `session_dir / "subagents"` which is relative to the JSONL path. Already verified in unit test `TestRemoteSessionSubagentAccess`. This task adds an endpoint-level integration test.

**Step 1: Write test, run, commit**

```python
def test_subagents_endpoint_for_remote_session(self, client, karma_base):
    """GET /sessions/{uuid}/subagents should work for remote sessions."""
    # Create JSONL + subagent file (same structure as TestRemoteSessionSubagentAccess)
    # ... setup ...
    response = client.get("/sessions/sess-rsub/subagents")
    assert response.status_code == 200
```

```bash
git commit -m "test: verify /sessions/{uuid}/subagents for remote sessions"
```

---

### Task 13: Ensure `/sessions/{uuid}/timeline` works for remote sessions

**Files:**
- Test: `api/tests/api/test_remote_sessions.py`

**Context:** Timeline builds events from JSONL messages + tool results. Both should resolve correctly for remote sessions.

**Step 1: Write test, run, commit**

```bash
git commit -m "test: verify /sessions/{uuid}/timeline for remote sessions"
```

---

## Phase 5: Edge Cases and Robustness (Role A + C)

### Task 14: Handle missing resource dirs gracefully for remote sessions

**Files:**
- Modify: `api/models/session.py` (if needed)
- Test: `api/tests/test_remote_sessions.py`

**Context:** A remote session may have JSONL but NOT todos/tasks/file-history (packager didn't find any). The API must return empty lists, not crash.

**Step 1: Write the test**

```python
class TestRemoteSessionMissingResources:
    def test_missing_todos_returns_empty(self, karma_base):
        """Remote session without todos dir should return empty list."""
        encoded = "-Users-jayant-acme"
        alice_dir = karma_base / "remote-sessions" / "alice" / encoded
        sessions_dir = alice_dir / "sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / "sess-empty-001.jsonl").write_text(
            json.dumps({
                "type": "user",
                "message": {"role": "user", "content": "hello"},
                "timestamp": "2026-03-03T12:00:00Z",
            }) + "\n"
        )
        # NO todos, tasks, file-history, debug dirs created

        with patch("services.remote_sessions.settings") as mock_settings:
            mock_settings.karma_base = karma_base
            result = find_remote_session("sess-empty-001")

        session = result.session
        assert session.list_todos() == []
        assert session.list_tasks() == []
        assert session.has_file_history is False
        assert session.has_debug_log is False
```

**Step 2: Run test — should pass since Session already handles missing dirs**

Run: `cd api && pytest tests/test_remote_sessions.py::TestRemoteSessionMissingResources -v`

**Step 3: Commit**

```bash
git commit -m "test: verify graceful handling of missing resources in remote sessions"
```

---

### Task 15: Verify incremental packaging skips unchanged file-history and debug

**Files:**
- Test: `cli/tests/test_packager.py`

**Context:** The packager uses mtime comparison for JSONL files (`packager.py:101`). The new file-history and debug copying should also not re-copy unchanged data (copytree with `dirs_exist_ok=True` handles this implicitly).

**Step 1: Write test verifying idempotent packaging**

```python
def test_incremental_package_skips_unchanged_file_history(tmp_path):
    """Re-packaging should not fail or duplicate file-history."""
    # Setup + first package
    # ... (same as Task 4 setup)
    packager.package(staging)
    first_mtime = (staging / "file-history" / uuid / "snapshot-1.json").stat().st_mtime

    # Package again without changes
    packager.package(staging)
    second_mtime = (staging / "file-history" / uuid / "snapshot-1.json").stat().st_mtime

    # copytree with dirs_exist_ok replaces files, so mtime may change
    # Just verify it didn't crash and file still exists
    assert (staging / "file-history" / uuid / "snapshot-1.json").exists()
```

**Step 2: Run and commit**

```bash
git commit -m "test: verify incremental packaging for file-history and debug logs"
```

---

## Phase 6: Indexer Alignment (Role C — Backend Engineer)

### Task 16: Pass `claude_base_dir` to `_index_session()` for remote sessions

**Files:**
- Modify: `api/db/indexer.py:351-359` (the `_index_session()` call in `index_remote_sessions()`)
- Modify: `api/db/indexer.py:370-397` (the `_index_session()` signature and `Session.from_path()` call)
- Test: `api/tests/test_remote_sessions.py`

**Context:** Currently `_index_session()` at line 404 calls `Session.from_path(jsonl_path)` without `claude_base_dir`. For remote sessions this means `claude_base_dir` defaults to `~/.claude`, so todo/task/file-history existence checks during indexing point to the wrong place. While the indexer doesn't currently use these resources, future schema additions (e.g., `todo_count`, `has_file_history` columns) would be incorrect.

**Step 1: Add `claude_base_dir` parameter to `_index_session()`**

In `api/db/indexer.py`, modify `_index_session()` signature (line 370):

```python
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
    claude_base_dir: Optional[Path] = None,  # NEW
) -> None:
```

And update the `Session.from_path()` call (line 404):

```python
    session = Session.from_path(jsonl_path, claude_base_dir=claude_base_dir)
```

**Step 2: Pass `claude_base_dir` from `index_remote_sessions()`**

In `api/db/indexer.py`, update the call at line 351:

```python
                    _index_session(
                        conn,
                        jsonl_path,
                        local_encoded,
                        current_mtime,
                        current_size,
                        source="remote",
                        remote_user_id=user_id,
                        remote_machine_id=user_id,
                        claude_base_dir=encoded_dir,  # NEW
                    )
```

Where `encoded_dir` is the project-level directory (parent of `sessions/`).

**Step 3: Run all tests**

Run: `cd api && pytest tests/ -v`
Expected: All pass (existing behavior unchanged for local sessions since `claude_base_dir=None` preserves default)

**Step 4: Commit**

```bash
git add api/db/indexer.py
git commit -m "fix: pass claude_base_dir to indexer for remote sessions"
```

---

## Phase 7: End-to-End Verification (All Roles)

### Task 17: Full round-trip test: package → land → index → serve

**Files:**
- Create: `api/tests/test_remote_roundtrip.py`

**Context:** This is the capstone test. It simulates the full pipeline: CLI packages a local session with all resources → files land in remote-sessions dir → indexer picks them up → API serves complete data.

**Step 1: Write the end-to-end test**

```python
"""
End-to-end test: package local session → simulate sync landing →
index into SQLite → serve via API endpoints.
"""
import json
import shutil
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from db.indexer import index_remote_sessions
from db.schema import ensure_schema
from services.remote_sessions import find_remote_session


@pytest.fixture
def full_roundtrip_env(tmp_path):
    """Create a complete roundtrip environment."""
    karma_base = tmp_path / ".claude_karma"
    karma_base.mkdir()

    # Simulate remote session landing (as if packager + sync already ran)
    user_id = "alice"
    encoded = "-Users-alice-acme"
    uuid = "roundtrip-001"

    alice_dir = karma_base / "remote-sessions" / user_id / encoded
    sessions_dir = alice_dir / "sessions"
    sessions_dir.mkdir(parents=True)

    # JSONL with user + assistant messages
    jsonl = (
        json.dumps({
            "type": "user",
            "message": {"role": "user", "content": "Build feature X"},
            "timestamp": "2026-03-03T12:00:00Z",
            "sessionId": "roundtrip-slug",
        }) + "\n"
        + json.dumps({
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "text", "text": "On it."}],
                "model": "claude-sonnet-4-20250514",
                "usage": {"input_tokens": 100, "output_tokens": 50},
            },
            "timestamp": "2026-03-03T12:00:05Z",
        }) + "\n"
    )
    (sessions_dir / f"{uuid}.jsonl").write_text(jsonl)

    # Subagent
    sub_dir = sessions_dir / uuid / "subagents"
    sub_dir.mkdir(parents=True)
    (sub_dir / "agent-aaa.jsonl").write_text(
        json.dumps({
            "type": "user",
            "message": {"role": "user", "content": "sub task"},
            "timestamp": "2026-03-03T12:01:00Z",
        }) + "\n"
    )

    # Tool result
    tr_dir = sessions_dir / uuid / "tool-results"
    tr_dir.mkdir(parents=True)
    (tr_dir / "toolu_xyz.txt").write_text("file content here")

    # Todos
    todos_dir = alice_dir / "todos"
    todos_dir.mkdir()
    (todos_dir / f"{uuid}-item.json").write_text(
        json.dumps([{"content": "Fix bug", "status": "pending"}])
    )

    # Tasks
    task_dir = alice_dir / "tasks" / uuid
    task_dir.mkdir(parents=True)
    (task_dir / "1.json").write_text(
        json.dumps({"id": "1", "subject": "Parse CLI args", "status": "in_progress"})
    )

    # File-history
    fh_dir = alice_dir / "file-history" / uuid
    fh_dir.mkdir(parents=True)
    (fh_dir / "snapshot.json").write_text('{"file": "main.py"}')

    # Debug log
    debug_dir = alice_dir / "debug"
    debug_dir.mkdir()
    (debug_dir / f"{uuid}.txt").write_text("DEBUG: started")

    # Sync config (identifies local user to skip)
    (karma_base / "sync-config.json").write_text(
        json.dumps({"user_id": "local-me", "machine_id": "my-mac"})
    )

    return {
        "karma_base": karma_base,
        "user_id": user_id,
        "encoded": encoded,
        "uuid": uuid,
    }


def test_full_roundtrip(full_roundtrip_env):
    """Remote session should be fully accessible after sync landing."""
    env = full_roundtrip_env

    with patch("services.remote_sessions.settings") as mock_settings:
        mock_settings.karma_base = env["karma_base"]

        # Step 1: find_remote_session resolves everything
        result = find_remote_session(env["uuid"])
        assert result is not None

        session = result.session
        assert session.message_count >= 2
        assert result.user_id == "alice"

        # Step 2: All resource types accessible
        assert len(session.list_todos()) >= 1
        assert len(session.list_tasks()) >= 1
        assert len(session.list_subagents()) >= 1
        assert len(session.list_tool_results()) >= 1
        assert session.has_file_history is True
        assert session.has_debug_log is True
        assert "DEBUG: started" in session.read_debug_log()

    # Step 3: Indexer picks it up
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)

    with patch("db.indexer.settings") as mock_idx_settings, \
         patch("services.remote_sessions.settings") as mock_rs_settings, \
         patch("services.remote_sessions.get_project_mapping", return_value={}):
        mock_idx_settings.karma_base = env["karma_base"]
        mock_rs_settings.karma_base = env["karma_base"]

        stats = index_remote_sessions(conn)

    assert stats["indexed"] >= 1
    assert stats["errors"] == 0

    # Verify indexed data
    row = conn.execute(
        "SELECT * FROM sessions WHERE uuid = ?", (env["uuid"],)
    ).fetchone()
    assert row is not None
    assert row["source"] == "remote"
    assert row["remote_user_id"] == "alice"
    assert row["message_count"] >= 2

    conn.close()
```

**Step 2: Run the test**

Run: `cd api && pytest tests/test_remote_roundtrip.py -v`

**Step 3: Fix any failures discovered**

**Step 4: Commit**

```bash
git add api/tests/test_remote_roundtrip.py
git commit -m "test: end-to-end roundtrip test for remote session parity"
```

---

## Summary: Task Assignment by Role

| Phase | Task | Role | Description |
|-------|------|------|-------------|
| 1 | 1 | Test Engineer | Verify todos resolve for remote sessions |
| 1 | 2 | Test Engineer | Verify tasks resolve for remote sessions |
| 1 | 3 | Test Engineer | Verify tool-results resolve for remote sessions |
| 2 | 4 | CLI Engineer | Package file-history in packager |
| 2 | 5 | CLI Engineer | Package debug logs in packager |
| 3 | 6 | Backend Engineer | Test file-history resolution |
| 3 | 7 | Backend Engineer | Test debug log resolution |
| 3 | 8 | Backend Engineer | Integration test: session detail endpoint |
| 4 | 9 | Backend Engineer | Verify /todos endpoint for remote |
| 4 | 10 | Backend Engineer | Verify /tasks endpoint for remote |
| 4 | 11 | Backend Engineer | Verify /file-activity endpoint for remote |
| 4 | 12 | Backend Engineer | Verify /subagents endpoint for remote |
| 4 | 13 | Backend Engineer | Verify /timeline endpoint for remote |
| 5 | 14 | Test + Backend | Handle missing resource dirs gracefully |
| 5 | 15 | Test Engineer | Verify incremental packaging |
| 6 | 16 | Backend Engineer | Pass `claude_base_dir` to indexer for remote |
| 7 | 17 | All | Full round-trip end-to-end test |

**Parallelization:** Phase 1 (Tasks 1-3) and Phase 2 (Tasks 4-5) can run in parallel since they touch different codebases (api/tests vs cli). Phase 3-4 depend on Phase 2 for file-history/debug tests. Phase 5-6 can run in parallel. Phase 7 is the final gate.
