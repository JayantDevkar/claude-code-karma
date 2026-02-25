# Frontend Engineer: Implement Todos in Timeline

**Date**: 2026-01-10
**Backend Status**: ✅ COMPLETE
**Frontend Status**: 🚧 IN PROGRESS
**Your Task**: Implement frontend rendering for todo events in timeline

---

## Context

We've added the ability to show todo items in the session timeline. The backend is complete and tested (202 tests passing). Your job is to implement the frontend rendering.

## What's New in the API

### 1. New Endpoint: `GET /sessions/{uuid}/todos`

Returns all todos for a session:
```json
[
  {"content": "Fix bug", "status": "completed", "activeForm": "Fixing bug"},
  {"content": "Add tests", "status": "in_progress", "activeForm": "Adding tests"},
  {"content": "Deploy", "status": "pending", "activeForm": "Deploying"}
]
```

### 2. Enhanced Session Detail

`GET /sessions/{uuid}` now includes:
- `todo_count: number` - count of todos
- `todos: TodoItem[]` - full todo list

### 3. New Timeline Event Type: `todo_update`

Timeline now emits `todo_update` events (instead of `tool_call` for TodoWrite):
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
    "agent_id": null,
    "agent_slug": null
  }
}
```

For subagent todos, `agent_id` and `agent_slug` will be populated.

---

## Your Implementation Tasks

### Phase 1: Update Types ✅ COMPLETE

**File**: `packages/types/src/index.ts`

Already implemented:
- ✅ `TodoItem` interface (lines 14-18)
- ✅ `TimelineEventType` includes `todo_update` (line 11)
- ✅ `SessionSummary` includes `todo_count` (line 48)
- ✅ `SessionDetail` includes `todos: TodoItem[]` (line 59)
- ✅ `TodoUpdateMetadata` interface (lines 162-176)

### Phase 2: Timeline Component 🚧 IN PROGRESS

**File**: `apps/web/components/timeline-rail.tsx`

1. ✅ **eventConfig updated** - `todo_update` with violet colors already added

2. **TODO: Create TodoList component** to render todos with status icons:
- `CheckCircle2Icon` for completed (green)
- `CircleDotIcon` for in_progress (amber)
- `CircleIcon` for pending (slate)

3. **TODO: Handle `todo_update` in TimelineEventCard**:
- Show todo list in expandable content
- Display status badges
- Show agent context if subagent todo

### Phase 3: Optional Enhancements

- Add `useTodos` hook for dedicated todos fetching
- Create `SessionTodosCard` for session detail page
- Add todo count to timeline stats bar

---

## Design Specs

| Element | Color |
|---------|-------|
| todo_update event | Violet (`text-violet-400`) |
| completed status | Green (`text-green-400`) |
| in_progress status | Amber (`text-amber-400`) |
| pending status | Slate (`text-slate-400`) |

Completed todos should have `line-through` text decoration.

---

## Testing

Run existing tests:
```bash
pnpm --filter @claude-karma/web test
```

Add tests for:
- `todo_update` event rendering
- TodoList component
- Status icon display

---

## Reference

Full implementation guide: `docs/feature/show-todo-of-session/frontend.md`

Backend implementation: `docs/feature/show-todo-of-session/backend.md`

---

## Questions?

The backend is fully implemented. Key files to reference:
- `apps/api/schemas.py` - `TodoItemSchema`, `TimelineEvent` with `todo_update`
- `apps/api/routers/sessions.py:611-633` - TodoWrite metadata structure
- `apps/api/routers/sessions.py:868-889` - todo_update event generation
