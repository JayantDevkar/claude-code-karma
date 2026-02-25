# Tasks Fallback Mechanism

> Design document for reconstructing tasks from JSONL events when task files are not persisted.

## Problem Statement

### Current Behavior

The Tasks tab reads task data from `~/.claude/tasks/{session-uuid}/` directory:

```
~/.claude/tasks/
├── {session-uuid}/
│   ├── 1.json
│   ├── 2.json
│   └── .lock
```

**Issue**: Many sessions show task events in the timeline (TaskCreate, TaskUpdate) but the Tasks tab is empty because:

1. Task JSON files are **ephemeral** - managed in-memory during sessions
2. Files may not be written to disk if session ends abnormally
3. Files may be cleaned up after session completion
4. The `.lock` file exists but no actual task data

### Evidence

Session `dazzling-riding-dream` (a07b2843-d981-4523-8096-69487e64864a):

- **Timeline**: 14 task-related events (4 TaskCreate, 10 TaskUpdate)
- **Task Files**: Only `.lock` file, no JSON files
- **Tasks Tab**: Empty

```bash
# Timeline shows tasks were created and updated
$ curl /sessions/{uuid}/timeline | grep -c "Task"
14

# But task directory is empty
$ ls ~/.claude/tasks/{uuid}/
.lock
```

---

## Storage Architecture

### Two Sources of Truth

| Source           | Location                                 | Persistence | Content                          |
| ---------------- | ---------------------------------------- | ----------- | -------------------------------- |
| **Task Files**   | `~/.claude/tasks/{uuid}/*.json`          | Ephemeral   | Current task state               |
| **JSONL Events** | `~/.claude/projects/{path}/{uuid}.jsonl` | Permanent   | TaskCreate/TaskUpdate tool calls |

### JSONL Event Structure

**TaskCreate** event in JSONL:

```json
{
	"message": {
		"content": [
			{
				"type": "tool_use",
				"name": "TaskCreate",
				"input": {
					"subject": "Add Task interfaces to api-types.ts",
					"description": "Add TaskStatus type, Task interface...",
					"activeForm": "Adding Task interfaces"
				}
			}
		]
	},
	"timestamp": "2026-01-24T23:33:09.588Z"
}
```

**TaskUpdate** event in JSONL:

```json
{
	"message": {
		"content": [
			{
				"type": "tool_use",
				"name": "TaskUpdate",
				"input": {
					"taskId": "1",
					"status": "completed",
					"addBlockedBy": ["2", "3"]
				}
			}
		]
	},
	"timestamp": "2026-01-24T23:35:00.000Z"
}
```

---

## Fallback Mechanism Design

### Algorithm

```
GET /sessions/{uuid}/tasks

1. Check ~/.claude/tasks/{uuid}/ for JSON files
2. IF task files exist:
   - Return tasks from files (current behavior)
3. ELSE:
   - Parse session JSONL file
   - Extract TaskCreate and TaskUpdate events
   - Reconstruct task state by replaying events
   - Return reconstructed tasks
```

### Task Reconstruction Logic

```python
def reconstruct_tasks_from_jsonl(session_path: Path) -> List[Task]:
    tasks = {}  # id -> task data
    task_counter = 0

    for message in parse_jsonl(session_path):
        for tool_use in message.tool_uses:
            if tool_use.name == "TaskCreate":
                task_counter += 1
                task_id = str(task_counter)
                tasks[task_id] = Task(
                    id=task_id,
                    subject=tool_use.input.subject,
                    description=tool_use.input.description,
                    active_form=tool_use.input.activeForm,
                    status="pending",
                    blocks=[],
                    blocked_by=[]
                )

            elif tool_use.name == "TaskUpdate":
                task_id = tool_use.input.taskId
                if task_id in tasks:
                    # Apply updates
                    if "status" in tool_use.input:
                        tasks[task_id].status = tool_use.input.status
                    if "addBlockedBy" in tool_use.input:
                        tasks[task_id].blocked_by.extend(...)
                    if "addBlocks" in tool_use.input:
                        tasks[task_id].blocks.extend(...)
                    # ... other fields

    return sorted(tasks.values(), key=lambda t: int(t.id))
```

### API Response

The response format remains identical whether from files or JSONL reconstruction:

```json
[
	{
		"id": "1",
		"subject": "Add Task interfaces to api-types.ts",
		"description": "Add TaskStatus type, Task interface...",
		"status": "completed",
		"active_form": "Adding Task interfaces",
		"blocks": [],
		"blocked_by": ["2", "3"]
	}
]
```

---

## UI Implications

### Live Session Updates

**Current Behavior:**

- Poll `/sessions/{uuid}/tasks` every 2 seconds during live sessions
- Returns current state from task files

**With Fallback:**

- Same polling behavior
- During live session: Task files likely exist (in-memory state is active)
- After session ends: Falls back to JSONL reconstruction

```
Timeline: ----[TaskCreate]----[TaskUpdate]----[Session End]----
Files:    ----[1.json created]-[1.json updated]-[files may be cleaned]----
Fallback:                                       [JSONL reconstruction]
```

### Task Status Accuracy

| Scenario                      | File-based      | JSONL Reconstruction      |
| ----------------------------- | --------------- | ------------------------- |
| Live session                  | Real-time state | Real-time state           |
| Ended session (files exist)   | Final state     | N/A                       |
| Ended session (files cleaned) | Empty           | Reconstructed final state |

### Performance Considerations

| Source               | Performance       | When Used     |
| -------------------- | ----------------- | ------------- |
| Task Files           | O(n) file reads   | Files exist   |
| JSONL Reconstruction | O(m) message scan | Files missing |

Where:

- n = number of tasks
- m = number of messages in session

**Mitigation**: Cache reconstructed tasks in memory or add a `tasks_cache.json` file.

---

## Implementation Checklist

### API Changes

- [ ] Add `reconstruct_tasks_from_jsonl()` function in `api/models/task.py`
- [ ] Modify `Session.list_tasks()` to use fallback
- [ ] Add caching layer for reconstructed tasks
- [ ] Update `/sessions/{uuid}/tasks` endpoint

### Frontend Changes

- [ ] No changes needed - same API response format
- [ ] Consider adding indicator for "reconstructed" vs "live" tasks (optional)

### Testing

- [ ] Test with session that has task files
- [ ] Test with session that has only JSONL events
- [ ] Test live session polling
- [ ] Test task reconstruction accuracy
- [ ] Performance test with large JSONL files

---

## Edge Cases

### 1. TaskCreate without matching tool_use ID

The JSONL uses auto-incrementing IDs based on order of TaskCreate events, not explicit IDs in the input. This matches how Claude Code assigns task IDs.

### 2. Partial updates

TaskUpdate events may update only specific fields. The reconstruction must apply updates incrementally:

```python
# Only update fields present in the input
if "status" in input:
    task.status = input["status"]
# Don't reset other fields
```

### 3. Deleted tasks

If TaskUpdate sets a task to a "deleted" state (not currently implemented in Claude Code), we should:

- Either exclude from results
- Or mark with a `deleted: true` flag

### 4. Task ID conflicts

If both task files AND JSONL events exist but disagree:

- **Priority**: Task files (they represent the authoritative final state)
- **Fallback**: Only used when files are missing

---

## Future Considerations

### 1. Write-through to files

When reconstructing from JSONL, optionally write the reconstructed tasks to the task directory for faster subsequent access:

```python
def list_tasks(self) -> List[Task]:
    tasks = load_tasks_from_directory(self.tasks_dir)
    if not tasks:
        tasks = reconstruct_tasks_from_jsonl(self.jsonl_path)
        # Optional: persist for faster future access
        save_tasks_to_directory(self.tasks_dir, tasks)
    return tasks
```

### 2. Task history timeline

Since JSONL contains the full history of TaskCreate/TaskUpdate events, we could expose a task history endpoint:

```
GET /sessions/{uuid}/tasks/history

[
  { "timestamp": "...", "event": "create", "task_id": "1", "data": {...} },
  { "timestamp": "...", "event": "update", "task_id": "1", "status": "in_progress" },
  { "timestamp": "...", "event": "update", "task_id": "1", "status": "completed" }
]
```

### 3. Real-time task events in timeline

The frontend could show task state changes inline in the timeline view, similar to how todo_update events are displayed.

---

## Related Files

| File                                 | Purpose                         |
| ------------------------------------ | ------------------------------- |
| `api/models/task.py`                 | Task model and file loading     |
| `api/models/session.py`              | Session.list_tasks() method     |
| `api/routers/sessions.py`            | /sessions/{uuid}/tasks endpoint |
| `frontend/src/lib/api-types.ts`      | Task TypeScript interfaces      |
| `frontend/src/lib/components/tasks/` | Task UI components              |

---

## References

- [01-TASKS.md](./01-TASKS.md) - Original tasks system documentation
- Claude Code v2.1.16+ - Introduced structured task system
- `~/.claude/tasks/` - Task storage directory
