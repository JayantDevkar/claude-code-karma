# Tasks Cross-Session Behavior

> Investigation findings on how Claude Code handles tasks across related sessions (continuation, compaction, session chains).

## Key Finding

**Tasks are NOT shared between sessions.** Each session maintains its own independent task set.

---

## Storage Architecture

### Per-Session Task Storage

```
~/.claude/tasks/
├── {session-uuid-A}/
│   ├── 1.json
│   ├── 2.json
│   └── .lock
├── {session-uuid-B}/      # Child/continuation session
│   ├── 1.json             # Its OWN task #1, not inherited
│   ├── 2.json
│   └── .lock
└── {session-uuid-C}/
    └── .lock              # Empty - tasks only in JSONL
```

Each session UUID has its own task directory. There is no sharing, symlinking, or inheritance between directories.

---

## Session Relationships vs Tasks

### Session Chain Structure

Sessions can be related via:

- **Continuation**: User resumes a session → new UUID created
- **Compaction**: Context compacted mid-session → same UUID, summary added
- **Project Context**: New session loads summaries from previous sessions

```
Session A (parent)
├── Tasks: [1, 2, 3]
├── leafUuid referenced by →
│
Session B (child - resumed from A)
├── Tasks: [1, 2, 3, 4, 5]    ← These are NEW tasks, not inherited
├── Has project_context_summaries from A
```

### Evidence from JSONL Analysis

Session `0eb6e3e3` (child session with `leafUuid` references to parents):

| Metric              | Value                  |
| ------------------- | ---------------------- |
| TaskCreate events   | 27                     |
| TaskUpdate events   | 69                     |
| TaskList events     | 7                      |
| leafUuid references | 2 (to parent sessions) |
| Task files          | 0 (only .lock)         |

**Conclusion**: The session created its own 27 tasks via TaskCreate. It did NOT inherit tasks from parent sessions.

---

## Why Tasks Aren't Shared

### Design Rationale

1. **Tasks are conversation-scoped**
    - Tasks track work items within a single conversation flow
    - When conversation ends/compacts, tasks represent that conversation's work

2. **Compaction creates context, not task inheritance**
    - When compacted, Claude summarizes what was accomplished
    - The summary captures task completions as narrative context
    - New conversation starts with fresh task tracking

3. **Session boundaries = work boundaries**
    - Each session represents a distinct work session
    - User may have different goals in continuation sessions
    - Fresh task slate allows clean tracking of new objectives

### What Carries Over

| Data Type            | Inherited? | How                             |
| -------------------- | ---------- | ------------------------------- |
| Tasks                | ❌ No      | Each session creates own tasks  |
| Context summaries    | ✅ Yes     | Via `project_context_summaries` |
| Code changes         | ✅ Yes     | Persisted to filesystem         |
| Conversation history | ⚠️ Partial | Summary only, not full messages |

---

## Implications for Dashboard

### Current Implementation (Correct)

The task fallback mechanism correctly:

- Reconstructs tasks from each session's own JSONL
- Does NOT traverse session chains for task inheritance
- Treats each session's tasks as independent

### API Response

```json
GET /sessions/{uuid}/tasks

// Returns ONLY tasks from this specific session
[
  {"id": "1", "subject": "Task from THIS session", ...},
  {"id": "2", "subject": "Another task from THIS session", ...}
]
```

### Frontend Display

When viewing a session:

- Tasks tab shows only that session's tasks
- No aggregation from parent/child sessions
- Each session in a chain has its own task history

---

## Future Considerations

### Option 1: Session Chain Tasks View

If users want visibility into related session tasks:

```typescript
interface SessionChainTasks {
	current_session: Task[];
	parent_sessions: {
		uuid: string;
		slug: string;
		tasks: Task[];
	}[];
	child_sessions: {
		uuid: string;
		slug: string;
		tasks: Task[];
	}[];
}
```

**API Endpoint**: `GET /sessions/{uuid}/chain-tasks`

### Option 2: Task Continuation Markers

Track which tasks conceptually "continue" work from parent sessions:

```typescript
interface Task {
	// ... existing fields
	continues_from?: {
		session_uuid: string;
		task_id: string;
	};
}
```

### Option 3: Project-Level Task Aggregation

Aggregate all tasks across a project's sessions:

```typescript
GET /projects/{encoded_name}/all-tasks

// Returns tasks from all sessions, grouped by session
{
  "sessions": [
    {
      "uuid": "abc123",
      "slug": "working-on-feature",
      "tasks": [...]
    },
    {
      "uuid": "def456",
      "slug": "working-on-feature",  // Same slug = related
      "tasks": [...]
    }
  ]
}
```

---

## Test Commands

```bash
# Check task directory structure
ls -la ~/.claude/tasks/

# Count TaskCreate events in a session
grep -c "TaskCreate" ~/.claude/projects/{project}/{uuid}.jsonl

# Find sessions with leafUuid references (continuation chains)
grep "leafUuid" ~/.claude/projects/{project}/*.jsonl

# Compare task counts across related sessions
for uuid in session1 session2 session3; do
  echo "$uuid: $(grep -c TaskCreate ~/.claude/projects/{project}/$uuid.jsonl) TaskCreate events"
done
```

---

## Related Documentation

- [01-TASKS.md](./01-TASKS.md) - Tasks system overview
- [02-TASKS-FALLBACK.md](./02-TASKS-FALLBACK.md) - JSONL reconstruction fallback
- `api/models/session_relationship.py` - Session chain detection
- `api/services/session_relationships.py` - Chain building logic

---

## Summary

| Question                                | Answer                     |
| --------------------------------------- | -------------------------- |
| Are tasks shared between sessions?      | No                         |
| Are tasks inherited on continuation?    | No                         |
| Does compaction preserve tasks?         | No (summarized in context) |
| Should dashboard aggregate chain tasks? | Optional future feature    |
| Is current implementation correct?      | Yes                        |
