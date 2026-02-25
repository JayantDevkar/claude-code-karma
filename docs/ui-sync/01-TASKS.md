# Tasks System

> Claude Code v2.1.16 introduced a structured task system with dependencies. This replaces/augments the legacy Todos for sessions that use the new format.

## API Implementation

**Endpoint**: `GET /sessions/{uuid}/tasks`

**Files**:

- `api/models/task.py` - Task model with dependency tracking
- `api/routers/sessions.py` - Tasks endpoint
- `api/schemas.py` - TaskSchema

**Storage Location**:

```
~/.claude/tasks/{session-uuid}/
├── 1.json
├── 2.json
└── 3.json
```

Each task is stored as an individual JSON file within a session-specific directory.

---

## Data Schema

### Task

```typescript
interface Task {
	id: string; // Numeric string: "1", "2", "3"
	subject: string; // Brief task title (imperative)
	description: string; // Detailed description
	status: 'pending' | 'in_progress' | 'completed';
	active_form: string | null; // Present-tense verb form
	blocks: string[]; // Task IDs this task blocks
	blocked_by: string[]; // Task IDs blocking this task
}
```

### Key Fields

| Field         | Description                          | Example                                     |
| ------------- | ------------------------------------ | ------------------------------------------- |
| `subject`     | Imperative action phrase             | "Implement user authentication"             |
| `description` | Full context and acceptance criteria | "Add JWT-based auth with refresh tokens..." |
| `active_form` | Gerund form for progress states      | "Implementing user authentication"          |
| `blocks`      | Downstream dependencies              | `["3", "4"]` - tasks 3 and 4 wait for this  |
| `blocked_by`  | Upstream dependencies                | `["1"]` - this task waits for task 1        |

---

## Example Response

```json
[
	{
		"id": "1",
		"subject": "Phase 1: Discover project scope",
		"description": "Analyze the existing codebase structure, identify key patterns, and document the current architecture for the authentication module.",
		"active_form": "Discovering project scope",
		"status": "completed",
		"blocks": ["2", "3"],
		"blocked_by": []
	},
	{
		"id": "2",
		"subject": "Phase 2: Implement JWT middleware",
		"description": "Create Express middleware for JWT validation, including token refresh logic and error handling.",
		"active_form": "Implementing JWT middleware",
		"status": "in_progress",
		"blocks": ["4"],
		"blocked_by": ["1"]
	},
	{
		"id": "3",
		"subject": "Phase 3: Add database schema",
		"description": "Design and implement user table with password hashing and session tracking.",
		"active_form": "Adding database schema",
		"status": "pending",
		"blocks": ["4"],
		"blocked_by": ["1"]
	},
	{
		"id": "4",
		"subject": "Phase 4: Integration tests",
		"description": "Write comprehensive integration tests for the auth flow, including edge cases for token expiration.",
		"active_form": "Writing integration tests",
		"status": "pending",
		"blocks": [],
		"blocked_by": ["2", "3"]
	}
]
```

---

## Dependency Graph

The `blocks` and `blocked_by` fields form a Directed Acyclic Graph (DAG):

```
Task 1 (completed)
├── blocks → Task 2 (in_progress)
│             └── blocks → Task 4 (pending)
└── blocks → Task 3 (pending)
               └── blocks → Task 4 (pending)
```

### Graph Properties

- **Root tasks**: `blocked_by: []` - can start immediately
- **Leaf tasks**: `blocks: []` - no downstream dependencies
- **Blocked tasks**: `blocked_by` contains incomplete task IDs
- **Critical path**: Longest dependency chain to completion

---

## Status Semantics

| Status        | Meaning                     | Visual Suggestion |
| ------------- | --------------------------- | ----------------- |
| `pending`     | Not started, may be blocked | Gray/neutral      |
| `in_progress` | Currently being worked on   | Blue/active       |
| `completed`   | Done                        | Green/success     |

### Blocked State

A task is effectively blocked when:

- `status === "pending"` AND
- `blocked_by.some(id => tasks[id].status !== "completed")`

---

## Existing Frontend Context

### Current Todo Display

The legacy `TodoItem` type exists in `api-types.ts`:

```typescript
interface TodoItem {
	id: string;
	content: string;
	status: TodoStatus; // 'pending' | 'in_progress' | 'completed' | 'cancelled'
	activeForm?: string;
}
```

Legacy todos are displayed in timeline events (`TodoUpdateDetail.svelte`) and session detail views.

### Related Components

| Component                  | Location               | Relevance                   |
| -------------------------- | ---------------------- | --------------------------- |
| `SessionCard.svelte`       | `components/`          | Shows `has_todos` indicator |
| `TimelineEventCard.svelte` | `components/timeline/` | Renders todo_update events  |
| `TodoUpdateDetail.svelte`  | `components/timeline/` | Todo state change rendering |
| `Badge.svelte`             | `components/ui/`       | Status badges               |
| `Card.svelte`              | `components/ui/`       | Container component         |
| `Tabs.svelte`              | `components/ui/`       | Tab navigation              |

### Session Detail Tabs

Current tabs in session detail view:

- Overview
- Timeline
- Tools
- Files
- Agents
- Messages

---

## Design Considerations

### Kanban Visualization

Three columns mapping to status:

- **Pending** (left)
- **In Progress** (center)
- **Completed** (right)

### Dependency Indicators

Tasks in "Pending" column may need visual distinction:

- Blocked (has incomplete upstream dependencies)
- Ready (all blockers completed, can start)

### Empty State

Sessions without tasks return `[]`. Many sessions (especially older ones pre-v2.1.16) have no tasks.

### Relationship to Timeline

Tasks are session-level metadata, separate from timeline events. A session can have:

- Tasks (new system) - structured work plan
- Todos (legacy) - simpler checklist items
- Both
- Neither

---

## Test Commands

```bash
# Fetch tasks for a session
curl http://localhost:8000/sessions/{session-uuid}/tasks | jq

# Sessions with tasks will have non-empty arrays
# Sessions without tasks will return []
```

---

## Related API Git Commit

Phase 2 implementation: `ed7e79d`
