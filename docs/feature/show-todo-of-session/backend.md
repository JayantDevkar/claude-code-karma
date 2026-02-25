# Backend Implementation Plan: Session Todos in Timeline

**Feature**: Show Todo Items in Session Timeline
**Role**: Backend Engineer
**Estimated Effort**: 3-4 hours
**Dependencies**: None (can start immediately)

---

## ✅ Implementation Status: COMPLETE

**Completed**: 2026-01-10
**Tests**: All 202 API tests passing, 479 model tests passing

### Summary of Changes

| File | Changes |
|------|---------|
| `apps/api/schemas.py` | Added `TodoItemSchema`, extended `SessionSummary` with `todo_count`, extended `SessionDetail` with `todos`, added `todo_update` to `TimelineEvent.event_type` |
| `apps/api/routers/sessions.py` | Added `GET /sessions/{uuid}/todos` endpoint, updated `get_session` to return todos, enhanced TodoWrite handling in timeline to emit `todo_update` events with parsed todos, added subagent context |
| `apps/api/tests/test_sessions.py` | Added 7 new tests for todos endpoint and session detail todos |

---

## Overview

You will expose session todo data through the API and integrate it into the timeline event stream. The Python models already support loading todos - your job is to wire this into the API layer.

---

## Phase 1: Add Todo Schema

**Duration**: 15 minutes
**File**: `apps/api/schemas.py`

### Task 1.1: Create TodoItemSchema

Add after line ~70 (after other schema definitions):

```python
class TodoItemSchema(BaseModel):
    """Schema for a single todo item."""
    content: str
    status: Literal["pending", "in_progress", "completed"]
    active_form: Optional[str] = Field(None, alias="activeForm")

    model_config = ConfigDict(populate_by_name=True)
```

### Task 1.2: Extend SessionDetail

Modify the `SessionDetail` class to include todo information:

```python
class SessionDetail(SessionSummary):
    # ... existing fields ...
    tools_used: dict[str, int]
    git_branches: list[str]
    working_directories: list[str]
    total_input_tokens: int
    total_output_tokens: int
    cache_hit_rate: float

    # ADD THESE NEW FIELDS:
    todo_count: int = 0
    todos: list[TodoItemSchema] = Field(default_factory=list)
```

### Task 1.3: Extend SessionSummary (optional enhancement)

Add todo count to the summary for list views:

```python
class SessionSummary(BaseModel):
    # ... existing fields ...
    has_todos: bool = False
    todo_count: int = 0  # ADD THIS
```

### Acceptance Criteria
- [x] `TodoItemSchema` validates todo items correctly
- [x] `SessionDetail` includes `todo_count` and `todos` fields
- [x] Schema serializes `active_form` as `activeForm` in JSON output

---

## Phase 2: Add Dedicated Todos Endpoint

**Duration**: 30 minutes
**File**: `apps/api/routers/sessions.py`

### Task 2.1: Add GET /sessions/{uuid}/todos endpoint

Add this new endpoint (after the existing session endpoints, around line ~300):

```python
@router.get("/{uuid}/todos", response_model=list[TodoItemSchema])
def get_session_todos(uuid: str) -> list[TodoItemSchema]:
    """
    Get all todo items for a session.

    Returns the current state of todos from ~/.claude/todos/{uuid}-*.json
    """
    session = find_session_by_uuid(uuid)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {uuid} not found")

    try:
        todos = session.list_todos()
        return [
            TodoItemSchema(
                content=todo.content,
                status=todo.status,
                active_form=todo.active_form
            )
            for todo in todos
        ]
    except Exception as e:
        # Log error but return empty list (todos are optional)
        logger.warning(f"Failed to load todos for session {uuid}: {e}")
        return []
```

### Task 2.2: Add import for TodoItemSchema

At the top of `routers/sessions.py`, add to imports:

```python
from schemas import (
    SessionSummary,
    SessionDetail,
    # ... existing imports ...
    TodoItemSchema,  # ADD THIS
)
```

### Task 2.3: Update get_session endpoint

Modify the existing `get_session` endpoint to include todos in the response. Find the `get_session` function and update the return statement:

```python
@router.get("/{uuid}", response_model=SessionDetail)
def get_session(uuid: str) -> SessionDetail:
    session = find_session_by_uuid(uuid)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Session {uuid} not found")

    # ... existing code to build response ...

    # ADD: Load todos
    todos = []
    try:
        todo_items = session.list_todos()
        todos = [
            TodoItemSchema(
                content=t.content,
                status=t.status,
                active_form=t.active_form
            )
            for t in todo_items
        ]
    except Exception:
        pass  # Todos are optional, don't fail the request

    return SessionDetail(
        # ... existing fields ...
        has_todos=session.has_todos,
        todo_count=len(todos),  # ADD THIS
        todos=todos,            # ADD THIS
    )
```

### Acceptance Criteria
- [x] `GET /sessions/{uuid}/todos` returns list of todo items
- [x] `GET /sessions/{uuid}` includes `todos` array and `todo_count`
- [x] 404 returned for non-existent session UUID
- [x] Empty list returned if todos file is missing or corrupted

---

## Phase 3: Enhance Timeline with Todo Events

**Duration**: 1-2 hours
**File**: `apps/api/routers/sessions.py`

### Task 3.1: Add todo_update to TimelineEvent schema

In `apps/api/schemas.py`, update the `TimelineEvent` schema:

```python
class TimelineEvent(BaseModel):
    id: str
    event_type: Literal[
        "prompt",
        "tool_call",
        "subagent_spawn",
        "thinking",
        "response",
        "todo_update"  # ADD THIS
    ]
    timestamp: datetime
    actor: str
    actor_type: Literal["user", "session", "subagent"]
    title: str
    summary: Optional[str]
    metadata: dict
```

### Task 3.2: Create TodoUpdateMetadata schema (optional but recommended)

```python
class TodoUpdateMetadata(BaseModel):
    """Metadata for todo_update timeline events."""
    action: Literal["set", "merge"]
    count: int
    todos: list[TodoItemSchema]
    tool_id: Optional[str] = None
```

### Task 3.3: Modify timeline generation for TodoWrite

In the `get_timeline` endpoint (around line 738), find the section that processes `ToolUseBlock`. Modify the TodoWrite handling:

**Current code** (around line 566-572):
```python
elif tool_name == "TodoWrite":
    todos = tool_input.get("todos", [])
    count = len(todos) if isinstance(todos, list) else 0
    merge = tool_input.get("merge", False)
    action = "Merge" if merge else "Set"
    summary = f"{action} {count} todo{'s' if count != 1 else ''}"
    return "Update todos", summary, {"action": action, "count": count}
```

**Replace with**:
```python
elif tool_name == "TodoWrite":
    todos_input = tool_input.get("todos", [])
    count = len(todos_input) if isinstance(todos_input, list) else 0
    merge = tool_input.get("merge", False)
    action = "merge" if merge else "set"
    summary = f"{'Merge' if merge else 'Set'} {count} todo{'s' if count != 1 else ''}"

    # Parse todo items for richer metadata
    parsed_todos = []
    if isinstance(todos_input, list):
        for todo in todos_input:
            if isinstance(todo, dict):
                parsed_todos.append({
                    "content": todo.get("content", ""),
                    "status": todo.get("status", "pending"),
                    "activeForm": todo.get("activeForm", todo.get("active_form"))
                })

    return "Update todos", summary, {
        "action": action,
        "count": count,
        "todos": parsed_todos
    }
```

### Task 3.4: Create dedicated todo_update events (alternative approach)

If you want TodoWrite to appear as `todo_update` instead of `tool_call`, modify the event creation logic:

In the timeline generation loop, after processing tool use blocks:

```python
# When processing ToolUseBlock
if block.name == "TodoWrite":
    # Create as todo_update event instead of tool_call
    todos_input = block.input.get("todos", [])
    merge = block.input.get("merge", False)

    parsed_todos = []
    for todo in todos_input if isinstance(todos_input, list) else []:
        if isinstance(todo, dict):
            parsed_todos.append({
                "content": todo.get("content", ""),
                "status": todo.get("status", "pending"),
                "activeForm": todo.get("activeForm", todo.get("active_form"))
            })

    events.append(TimelineEvent(
        id=f"evt-{event_counter}",
        event_type="todo_update",  # Dedicated type
        timestamp=msg.timestamp,
        actor=actor,
        actor_type=actor_type,
        title="Update todos",
        summary=f"{'Merge' if merge else 'Set'} {len(parsed_todos)} todo{'s' if len(parsed_todos) != 1 else ''}",
        metadata={
            "action": "merge" if merge else "set",
            "count": len(parsed_todos),
            "todos": parsed_todos,
            "tool_id": block.id
        }
    ))
    event_counter += 1
    continue  # Skip normal tool_call processing for TodoWrite
```

### Acceptance Criteria
- [x] TodoWrite tool calls include `todos` array in metadata
- [x] Each todo has `content`, `status`, `activeForm` fields
- [x] Timeline events correctly show todo count in summary
- [x] TodoWrite appears as `todo_update` event type

---

## Phase 4: Add Subagent Todo Support

**Duration**: 30 minutes
**File**: `apps/api/routers/sessions.py`

### Task 4.1: Load todos for subagents

Subagents may also have todos. Update the subagent timeline processing to include their todos:

```python
def get_subagent_todos(session: Session, agent_id: str) -> list[dict]:
    """Load todos for a specific subagent."""
    todos_dir = session.todos_dir
    pattern = f"{session.uuid}-agent-{agent_id}*.json"

    todos = []
    for todo_file in todos_dir.glob(pattern):
        try:
            with open(todo_file) as f:
                data = json.load(f)
                if isinstance(data, list):
                    todos.extend(data)
        except (json.JSONDecodeError, FileNotFoundError):
            continue

    return todos
```

### Task 4.2: Include agent context in todo events

When creating todo_update events, include which agent created them:

```python
metadata={
    "action": action,
    "count": len(parsed_todos),
    "todos": parsed_todos,
    "tool_id": block.id,
    "agent_id": agent_id if is_subagent else None,  # ADD THIS
    "agent_slug": agent_slug if is_subagent else None  # ADD THIS
}
```

### Acceptance Criteria
- [x] Subagent TodoWrite events include `agent_id` and `agent_slug`
- [x] Subagent todos can be loaded separately if needed

---

## Phase 5: Testing

**Duration**: 45 minutes
**File**: `tests/test_sessions_api.py` (create or extend)

### Task 5.1: Create test fixtures

In `tests/conftest.py`, ensure the todo fixture exists:

```python
@pytest.fixture
def session_with_todos(tmp_path, mock_claude_dir):
    """Create a session with todo items."""
    # Create session JSONL
    session_uuid = "test-session-with-todos"
    # ... create session file ...

    # Create todos file
    todos_dir = mock_claude_dir / "todos"
    todos_dir.mkdir(exist_ok=True)

    todos_file = todos_dir / f"{session_uuid}-agent-{session_uuid}.json"
    todos_file.write_text(json.dumps([
        {"content": "Explore codebase", "status": "completed", "activeForm": "Exploring"},
        {"content": "Write tests", "status": "in_progress", "activeForm": "Writing tests"},
        {"content": "Deploy feature", "status": "pending", "activeForm": "Deploying"}
    ]))

    return session_uuid
```

### Task 5.2: Test todos endpoint

```python
def test_get_session_todos(client, session_with_todos):
    """Test GET /sessions/{uuid}/todos returns todo items."""
    response = client.get(f"/sessions/{session_with_todos}/todos")

    assert response.status_code == 200
    todos = response.json()

    assert len(todos) == 3
    assert todos[0]["content"] == "Explore codebase"
    assert todos[0]["status"] == "completed"
    assert todos[0]["activeForm"] == "Exploring"


def test_get_session_todos_empty(client, session_without_todos):
    """Test GET /sessions/{uuid}/todos returns empty list when no todos."""
    response = client.get(f"/sessions/{session_without_todos}/todos")

    assert response.status_code == 200
    assert response.json() == []


def test_get_session_todos_not_found(client):
    """Test GET /sessions/{uuid}/todos returns 404 for invalid UUID."""
    response = client.get("/sessions/nonexistent-uuid/todos")
    assert response.status_code == 404
```

### Task 5.3: Test session detail includes todos

```python
def test_session_detail_includes_todos(client, session_with_todos):
    """Test GET /sessions/{uuid} includes todos in response."""
    response = client.get(f"/sessions/{session_with_todos}")

    assert response.status_code == 200
    data = response.json()

    assert data["has_todos"] is True
    assert data["todo_count"] == 3
    assert len(data["todos"]) == 3
    assert data["todos"][0]["content"] == "Explore codebase"
```

### Task 5.4: Test timeline with todo events

```python
def test_timeline_includes_todo_update_events(client, session_with_todowrite):
    """Test timeline includes todo_update events for TodoWrite calls."""
    response = client.get(f"/sessions/{session_with_todowrite}/timeline")

    assert response.status_code == 200
    events = response.json()

    todo_events = [e for e in events if e["event_type"] == "todo_update"]
    assert len(todo_events) >= 1

    event = todo_events[0]
    assert event["title"] == "Update todos"
    assert "todos" in event["metadata"]
    assert event["metadata"]["count"] > 0
```

### Acceptance Criteria
- [x] All tests pass (202 API tests, 479 model tests)
- [x] Edge cases covered (empty todos, missing files, invalid UUIDs)
- [x] Subagent todo tests included

---

## API Reference (After Implementation)

### Endpoints

| Method | Endpoint | Response |
|--------|----------|----------|
| GET | `/sessions/{uuid}` | `SessionDetail` with `todos[]` and `todo_count` |
| GET | `/sessions/{uuid}/todos` | `TodoItemSchema[]` |
| GET | `/sessions/{uuid}/timeline` | `TimelineEvent[]` with `todo_update` events |

### Response Examples

**GET /sessions/{uuid}/todos**
```json
[
  {
    "content": "Explore codebase structure",
    "status": "completed",
    "activeForm": "Exploring codebase"
  },
  {
    "content": "Write unit tests",
    "status": "in_progress",
    "activeForm": "Writing tests"
  }
]
```

**Timeline todo_update event**
```json
{
  "id": "evt-15",
  "event_type": "todo_update",
  "timestamp": "2026-01-10T14:30:00Z",
  "actor": "session",
  "actor_type": "session",
  "title": "Update todos",
  "summary": "Set 3 todos",
  "metadata": {
    "action": "set",
    "count": 3,
    "todos": [
      {"content": "Fix bug", "status": "pending", "activeForm": "Fixing bug"},
      {"content": "Add tests", "status": "pending", "activeForm": "Adding tests"},
      {"content": "Deploy", "status": "pending", "activeForm": "Deploying"}
    ],
    "tool_id": "toolu_abc123"
  }
}
```

---

## Checklist

### Phase 1: Schema ✅
- [x] `TodoItemSchema` created
- [x] `SessionDetail` extended with `todo_count`, `todos`
- [x] Imports updated

### Phase 2: Endpoint ✅
- [x] `GET /sessions/{uuid}/todos` implemented
- [x] `get_session` returns todos
- [x] Error handling for missing todos

### Phase 3: Timeline ✅
- [x] `todo_update` event type added to schema
- [x] TodoWrite metadata includes parsed todos
- [x] TodoWrite events use `todo_update` type

### Phase 4: Subagents ✅
- [x] Subagent todos loaded correctly
- [x] Agent context included in metadata

### Phase 5: Testing ✅
- [x] Unit tests for todos endpoint
- [x] Integration tests for timeline
- [x] Edge case tests

---

## Handoff to Frontend

✅ **Backend implementation complete.** The frontend engineer can now proceed with:

1. ✅ `GET /sessions/{uuid}/todos` is available
2. ✅ `SessionDetail` now includes `todos[]` and `todo_count`
3. ✅ Timeline events include `todo_update` type with full todo metadata
4. ✅ Metadata structure for todo events is documented above

### Files Modified

| File | Line Changes |
|------|--------------|
| `apps/api/schemas.py` | +15 lines (TodoItemSchema, extended SessionSummary/SessionDetail, TimelineEvent) |
| `apps/api/routers/sessions.py` | +50 lines (todos endpoint, get_session todos, timeline todo_update events) |
| `apps/api/tests/test_sessions.py` | +120 lines (7 new test cases for todos functionality) |

The frontend can begin their implementation immediately.
