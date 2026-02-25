# Feature Research: Show Todo Items in Session Timeline

**Date**: 2026-01-10
**Status**: ✅ Backend Implemented (2026-01-10), Frontend Pending
**Researcher**: Claude Opus 4.5 via multi-agent investigation

---

## Executive Summary

**Verdict: FEASIBLE**

The current architecture fully supports displaying todo items in the session timeline. The data exists, the Python models can load it, and the frontend timeline component is designed for extensibility. Implementation requires coordinated backend and frontend changes but no architectural rewrites.

---

## Research Questions

1. Where does todo data exist in the JSONL and filesystem?
2. Can the API expose this data?
3. Can the timeline UI render it?

---

## 1. Data Layer: Where Todos Live

### 1.1 Dual Storage Architecture

Todos exist in **two locations**:

| Location | Content | Usage |
|----------|---------|-------|
| Session JSONL `UserMessage.todos[]` | Empty array (placeholder) | Currently unused |
| `~/.claude/todos/{uuid}-*.json` | Full todo JSON array | **Primary storage** |

### 1.2 TodoItem Structure

From `models/todo.py`:

```python
class TodoItem(BaseModel):
    model_config = ConfigDict(frozen=True, populate_by_name=True)

    content: str                                              # Required
    status: Literal["pending", "in_progress", "completed"]    # Default: pending
    active_form: Optional[str] = None                         # Alias: activeForm
```

**Sample Data** (from `~/.claude/todos/{session-uuid}-agent-{session-uuid}.json`):
```json
[
  {"content": "Explore codebase structure", "status": "completed", "activeForm": "Exploring codebase"},
  {"content": "Initialize feature", "status": "in_progress", "activeForm": "Initializing feature"},
  {"content": "Write tests", "status": "pending", "activeForm": "Writing tests"}
]
```

### 1.3 Session Access Methods

From `models/session.py`:

```python
@property
def has_todos(self) -> bool:
    """Check if session has any associated todos."""
    return self.todos_dir.exists() and any(self.todos_dir.glob(f"{self.uuid}-*.json"))

def list_todos(self) -> List[TodoItem]:
    """Load todos associated with this session."""
    todos: List[TodoItem] = []
    for todo_file in self.todos_dir.glob(f"{self.uuid}-*.json"):
        todos.extend(load_todos_from_file(todo_file))
    return todos
```

**Key Insight**: The Python layer can already load todos. No new parsing logic needed.

---

## 2. API Layer: Current State

### 2.1 Current Endpoints

| Endpoint | Todo Data |
|----------|-----------|
| `GET /sessions/{uuid}` | `has_todos: bool` only |
| `GET /sessions/{uuid}/timeline` | TodoWrite as generic `tool_call` |
| `GET /sessions/{uuid}/tools` | TodoWrite count in tool usage |

### 2.2 Gap Analysis

| Missing | Impact |
|---------|--------|
| No `GET /sessions/{uuid}/todos` | Cannot fetch actual todo items |
| No dedicated timeline event type | Todo updates buried in tool_call events |
| No todo count in session summary | UI shows boolean, not quantity |
| No todo lifecycle tracking | Can't see pending → completed transitions |

### 2.3 TodoWrite in Timeline (Current)

The timeline **already captures** TodoWrite tool calls:

```python
# routers/sessions.py lines 566-572
elif tool_name == "TodoWrite":
    todos = tool_input.get("todos", [])
    count = len(todos) if isinstance(todos, list) else 0
    merge = tool_input.get("merge", False)
    action = "Merge" if merge else "Set"
    summary = f"{action} {count} todo{'s' if count != 1 else ''}"
    return "Update todos", summary, {"action": action, "count": count}
```

This produces timeline events like:
- **title**: "Update todos"
- **summary**: "Set 5 todos"
- **metadata**: `{"action": "Set", "count": 5, "tool_name": "TodoWrite"}`

---

## 3. Frontend Layer: Timeline Architecture

### 3.1 Current Event Types

From `packages/types/src/index.ts`:

```typescript
type TimelineEventType = "prompt" | "tool_call" | "subagent_spawn" | "thinking" | "response";
```

### 3.2 TimelineEvent Interface

```typescript
interface TimelineEvent {
  id: string;
  event_type: TimelineEventType;
  timestamp: string;
  actor: string;
  actor_type: "user" | "session" | "subagent";
  title: string;
  summary: string | null;
  metadata: Record<string, unknown>;
}
```

### 3.3 Event Configuration (timeline-rail.tsx)

```typescript
const eventConfig = {
  prompt: { icon: MessageSquareIcon, color: "text-blue-400", ... },
  tool_call: { icon: WrenchIcon, color: "text-emerald-400", ... },
  thinking: { icon: BrainIcon, color: "text-amber-400", ... },
  response: { icon: MessageCircleIcon, color: "text-slate-400", ... },
  // NEW types would go here
};
```

---

## 4. Implementation Approaches

### Approach A: Enhance TodoWrite Tool Calls (Minimal)

**Scope**: Backend-only changes

**Changes**:
1. In timeline generation, when processing TodoWrite:
   - Load current todos from `~/.claude/todos/`
   - Include todo content and statuses in metadata

**Result**:
```json
{
  "event_type": "tool_call",
  "title": "Update todos",
  "metadata": {
    "tool_name": "TodoWrite",
    "todos": [
      {"content": "Fix bug", "status": "in_progress", "activeForm": "Fixing bug"}
    ]
  }
}
```

**Pros**: No frontend changes, backward compatible
**Cons**: Todos still mixed with other tool calls, no lifecycle view

---

### Approach B: Dedicated Todo Event Types (Recommended)

**Scope**: Backend + Frontend + Types

#### Backend Changes

1. **Add `/sessions/{uuid}/todos` endpoint**:
```python
@router.get("/{uuid}/todos", response_model=list[TodoItemSchema])
def get_session_todos(uuid: str):
    session = find_session(uuid)
    return session.list_todos()
```

2. **Add TodoItemSchema** to `apps/api/schemas.py`:
```python
class TodoItemSchema(BaseModel):
    content: str
    status: Literal["pending", "in_progress", "completed"]
    active_form: Optional[str] = Field(None, alias="activeForm")
```

3. **Extend SessionDetail** response:
```python
class SessionDetail(SessionSummary):
    # ... existing fields ...
    todo_count: int = 0
    todos: list[TodoItemSchema] = Field(default_factory=list)
```

#### Types Changes

```typescript
// packages/types/src/index.ts
export type TimelineEventType =
  | "prompt"
  | "tool_call"
  | "subagent_spawn"
  | "thinking"
  | "response"
  | "todo_update";  // NEW

export interface TodoItem {
  content: string;
  status: "pending" | "in_progress" | "completed";
  activeForm?: string;
}

export interface TodoUpdateMetadata {
  todos: TodoItem[];
  action: "set" | "merge";
  count: number;
}
```

#### Frontend Changes

1. **Add to eventConfig**:
```typescript
todo_update: {
  icon: ListTodoIcon,
  color: "text-violet-400",
  bgColor: "bg-violet-500/20",
  borderColor: "border-violet-500/40",
}
```

2. **Render todo list in metadata expansion**:
```tsx
{metadata.todos && (
  <ul className="space-y-1">
    {metadata.todos.map((todo, i) => (
      <li key={i} className="flex items-center gap-2">
        <StatusIcon status={todo.status} />
        <span>{todo.content}</span>
      </li>
    ))}
  </ul>
)}
```

---

### Approach C: Full Todo Lifecycle Tracking (Advanced)

**Scope**: Full feature with status transitions

**Additional Requirements**:
- Parse TodoWrite inputs to detect status changes
- Track todo items across multiple TodoWrite calls
- Show timeline entries for:
  - `todo_created` - New todo added
  - `todo_started` - Status changed to in_progress
  - `todo_completed` - Status changed to completed

**Complexity**: High - requires diffing todo states between calls

---

## 5. Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      CURRENT FLOW                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ~/.claude/todos/{uuid}-*.json                                   │
│           │                                                      │
│           ▼                                                      │
│  Session.list_todos()  ──────►  TodoItem[]                       │
│           │                          │                           │
│           ▼                          │ (NOT EXPOSED)             │
│  Session.has_todos  ─────────►  API: has_todos: bool             │
│                                      │                           │
│                                      ▼                           │
│                              Frontend: Shows "Todos: Yes/No"     │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                      PROPOSED FLOW                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ~/.claude/todos/{uuid}-*.json                                   │
│           │                                                      │
│           ▼                                                      │
│  Session.list_todos()  ──────►  TodoItem[]                       │
│           │                          │                           │
│           ▼                          ▼                           │
│  GET /sessions/{uuid}/todos    Timeline event generation         │
│           │                          │                           │
│           ▼                          ▼                           │
│  [TodoItemSchema, ...]        TimelineEvent(todo_update)         │
│           │                          │                           │
│           └──────────┬───────────────┘                           │
│                      ▼                                           │
│             Frontend Timeline Tab                                │
│                      │                                           │
│           ┌──────────┴──────────┐                                │
│           ▼                     ▼                                │
│    Dedicated Todo Card    Inline in Timeline                     │
│    (expandable list)      (chronological)                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Large todo files slow API | Low | Medium | Pagination, lazy load |
| Todo file format changes | Low | High | Validate against schema |
| Timeline gets cluttered | Medium | Low | Filter options in UI |
| Subagent todos not linked | Medium | Medium | Track agent_id in filename |

---

## 7. Recommendation

**Implement Approach B (Dedicated Todo Event Types)** with phased rollout:

### Phase 1: Backend (1-2 hours) ✅ COMPLETE
- ✅ Add `GET /sessions/{uuid}/todos` endpoint
- ✅ Extend `SessionDetail` with `todo_count` and `todos[]`
- ✅ Modify timeline generation to emit `todo_update` events

### Phase 2: Types (30 min)
- Add `TodoItem` interface
- Extend `TimelineEventType` union
- Add `TodoUpdateMetadata` interface

### Phase 3: Frontend (1-2 hours)
- Add todo_update to eventConfig
- Render todo list in expandable metadata
- Add todo count to session stats bar

### Phase 4: Polish (Optional)
- Add todo filtering in timeline
- Show todo status transitions
- Link todos to subagents

---

## 8. Files to Modify

| Layer | File | Changes | Status |
|-------|------|---------|--------|
| Backend | `apps/api/routers/sessions.py` | Add `/todos` endpoint, modify timeline generation | ✅ Done |
| Backend | `apps/api/schemas.py` | Add `TodoItemSchema`, extend `SessionDetail` | ✅ Done |
| Backend | `apps/api/tests/test_sessions.py` | Add tests for todos endpoint and timeline | ✅ Done |
| Types | `packages/types/src/index.ts` | Add `TodoItem`, extend event types | Pending |
| Frontend | `apps/web/components/timeline-rail.tsx` | Add event config, render logic | Pending |
| Frontend | `apps/web/hooks/use-session.ts` | Add `useTodos` hook (optional) | Pending |

---

## 9. Test Coverage

### Backend Tests
```python
def test_get_session_todos(client, session_with_todos):
    response = client.get(f"/sessions/{session_with_todos.uuid}/todos")
    assert response.status_code == 200
    todos = response.json()
    assert len(todos) == 3
    assert todos[0]["status"] == "completed"

def test_timeline_includes_todo_events(client, session_with_todos):
    response = client.get(f"/sessions/{session_with_todos.uuid}/timeline")
    events = response.json()
    todo_events = [e for e in events if e["event_type"] == "todo_update"]
    assert len(todo_events) > 0
```

### Frontend Tests
```typescript
it("renders todo_update events with todo list", () => {
  render(<TimelineEventCard event={todoUpdateEvent} />);
  expect(screen.getByText("Fix bug")).toBeInTheDocument();
  expect(screen.getByText("in_progress")).toBeInTheDocument();
});
```

---

## 10. Conclusion

**The feature is fully feasible.** The data layer already supports loading todos via `Session.list_todos()`. The API needs a new endpoint and enhanced timeline generation. The frontend timeline component is designed for extensibility with its `eventConfig` pattern.

Recommended approach: **Approach B** with phased implementation starting from backend changes.

### Implementation Progress

| Phase | Status | Date |
|-------|--------|------|
| Backend | ✅ Complete | 2026-01-10 |
| Types | Pending | - |
| Frontend | Pending | - |
| Polish | Pending | - |

---

## Appendix: Agent Investigation Summary

Three parallel subagents investigated:

1. **Todo JSONL Structure Agent** - Confirmed todos stored in `~/.claude/todos/`, not in JSONL. `TodoItem` model has `content`, `status`, `active_form` fields.

2. **API Endpoints Agent** - Found no dedicated todo endpoints. Only `has_todos: bool` exposed. TodoWrite captured as generic tool_call in timeline.

3. **Frontend Timeline Agent** - Confirmed timeline is extensible via `eventConfig`. Adding new event types requires type extension + config entry + render logic.

All findings synthesized into this research document.
