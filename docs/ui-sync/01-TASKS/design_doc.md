# Tasks Tab Design Document

> Design specification for the Tasks visualization in Session and Agent views.

---

## Overview

The Tasks system (Claude Code v2.1.16+) provides a structured work plan with dependencies. This document defines the UI/UX for displaying tasks within the existing `ConversationView` component.

### Design Goals

1. **Glanceable status** — Quick visual of session progress
2. **Live updates** — Real-time `active_form` display for in-progress tasks
3. **Dependency clarity** — Text labels showing blockers (no SVG lines)
4. **Minimal chrome** — Read-only view that complements existing tabs

---

## Placement

### Tab Integration

Add "Tasks" tab to both session and agent tab lists:

```typescript
// ConversationView.svelte
const sessionTabs = ['overview', 'timeline', 'tasks', 'files', 'agents', 'analytics'];
const agentTabs = ['overview', 'timeline', 'tasks', 'files', 'analytics'];
```

**Position**: After Timeline, before Files. Tasks represent the "what" (planned work), Timeline shows the "when" (actual events), Files show the "where" (artifacts).

### Tab Badge

Show progress indicator in tab trigger when tasks exist:

```
┌─────────────────────────────────────────┐
│  Tasks  3/5                             │
│         ↑ completed/total               │
└─────────────────────────────────────────┘
```

---

## Data Model

### TypeScript Interface

```typescript
// api-types.ts

export type TaskStatus = 'pending' | 'in_progress' | 'completed';

export interface Task {
	id: string; // Numeric string: "1", "2", "3"
	subject: string; // Brief title (imperative)
	description: string; // Detailed description
	status: TaskStatus;
	active_form: string | null; // Present-tense verb form
	blocks: string[]; // Task IDs this task blocks
	blocked_by: string[]; // Task IDs blocking this task
}

// Computed state
export interface TaskWithState extends Task {
	isBlocked: boolean; // Has incomplete blockers
	isReady: boolean; // Pending with no blockers
}
```

### API Endpoint

```
GET /sessions/{uuid}/tasks
GET /agents/{encoded_name}/{session_uuid}/agents/{agent_id}/tasks
```

Returns `Task[]` — empty array for sessions without tasks.

---

## Component Architecture

```
src/lib/components/tasks/
├── index.ts                    # Barrel export
├── TasksTab.svelte             # Main tab content wrapper
├── TasksProgressBar.svelte     # Horizontal summary bar
├── TasksFlow.svelte            # Vertical progress flow (default view)
├── TasksKanban.svelte          # 3-column grid view (toggle)
├── TaskCard.svelte             # Individual task display
└── TaskStatusIndicator.svelte  # Status icon with animation
```

---

## Visual Design

### Progress Summary Bar

Always visible at top of Tasks tab content:

```
┌─────────────────────────────────────────────────────────────────┐
│  ●●●○○  3 of 5 tasks complete                                   │
│  ↑ status dots: green=done, blue=active, gray=pending           │
│                                                                 │
│  Currently: Implementing JWT middleware...                      │
│  ↑ active_form of in_progress task (animated pulse)             │
└─────────────────────────────────────────────────────────────────┘
```

**Implementation:**

```svelte
<!-- TasksProgressBar.svelte -->
<div
	class="flex items-center gap-4 p-4 bg-[var(--bg-subtle)] rounded-lg border border-[var(--border)]"
>
	<!-- Status dots -->
	<div class="flex items-center gap-1">
		{#each tasks as task}
			<span
				class="w-2.5 h-2.5 rounded-full {getStatusColor(task.status)}"
				class:animate-pulse={task.status === 'in_progress'}
			/>
		{/each}
	</div>

	<!-- Progress text -->
	<span class="text-sm text-[var(--text-secondary)]">
		{completedCount} of {tasks.length} tasks complete
	</span>

	<!-- Active task indicator -->
	{#if activeTask}
		<div class="ml-auto flex items-center gap-2 text-sm">
			<span class="text-[var(--text-muted)]">Currently:</span>
			<span class="text-[var(--nav-blue)] font-medium animate-pulse">
				{activeTask.active_form}
			</span>
		</div>
	{/if}
</div>
```

### Status Colors

| Status              | Dot Color   | CSS Variable                |
| ------------------- | ----------- | --------------------------- |
| `completed`         | Green       | `bg-[var(--success)]`       |
| `in_progress`       | Blue        | `bg-[var(--nav-blue)]`      |
| `pending` (ready)   | Gray        | `bg-[var(--text-muted)]`    |
| `pending` (blocked) | Gray dimmed | `bg-[var(--text-muted)]/50` |

---

## View Modes

### Default: Progress Flow

Vertical list showing task sequence with dependency flow:

```
┌─────────────────────────────────────────────────────────────────┐
│  Tasks (5)                                        [Flow] [Grid] │
├─────────────────────────────────────────────────────────────────┤
│  ●●●○○  3 of 5 complete · Currently: Implementing middleware... │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ✓  Discover project scope                                      │
│  │  Analyze existing codebase structure...                      │
│  │                                                              │
│  ├──┬──────────────────────────────────────────────────────     │
│  │  │                                                           │
│  │  ◐  Implement JWT middleware                    IN PROGRESS  │
│  │  │  Create Express middleware for JWT validation...          │
│  │  │  ↳ Blocks: Integration tests                              │
│  │  │                                                           │
│  ○  Add database schema                               BLOCKED   │
│  │  Design and implement user table...                          │
│  │  ↳ Waiting on: Discover project scope                        │
│  │                                                              │
│  └──┴─► Integration tests                             BLOCKED   │
│         Write comprehensive integration tests...                │
│         ↳ Waiting on: JWT middleware, Database schema           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Visual language:**

| Symbol | Meaning       | Styling                              |
| ------ | ------------- | ------------------------------------ |
| `✓`    | Completed     | `text-[var(--success)]` muted        |
| `◐`    | In Progress   | `text-[var(--nav-blue)]` with pulse  |
| `○`    | Pending/Ready | `text-[var(--text-muted)]`           |
| `○`    | Blocked       | `text-[var(--text-muted)]/50` dimmed |

**Dependency Labels:**

```svelte
<!-- Downstream (this task blocks others) -->
{#if task.blocks.length > 0}
	<div class="text-xs text-[var(--text-muted)] mt-1">
		↳ Blocks: {getTaskSubjects(task.blocks).join(', ')}
	</div>
{/if}

<!-- Upstream (this task is blocked by others) -->
{#if isBlocked}
	<div class="text-xs text-[var(--warning)] mt-1">
		↳ Waiting on: {getBlockerSubjects(task.blocked_by).join(', ')}
	</div>
{/if}
```

### Alternative: Kanban Grid

3-column layout for sessions with many tasks:

```
┌─────────────────────────────────────────────────────────────────┐
│  Tasks (5)                                        [Flow] [Grid] │
├─────────────────────────────────────────────────────────────────┤
│  ●●●○○  3 of 5 complete · Currently: Implementing middleware... │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Pending (2)          │ In Progress (1)    │ Completed (2)      │
│ ──────────────────────│────────────────────│─────────────────── │
│ ┌──────────────────┐  │ ┌────────────────┐ │ ┌────────────────┐ │
│ │ Add schema       │  │ │ ◐ JWT middle.. │ │ │ ✓ Discover     │ │
│ │ ⚠ blocked        │  │ │                │ │ │   scope        │ │
│ │ ↳ Waiting on: 1  │  │ │ Implementing.. │ │ └────────────────┘ │
│ └──────────────────┘  │ └────────────────┘ │ ┌────────────────┐ │
│ ┌──────────────────┐  │                    │ │ ✓ Setup env    │ │
│ │ Integration      │  │                    │ └────────────────┘ │
│ │ ⚠ 2 blockers     │  │                    │                    │
│ └──────────────────┘  │                    │                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**View Toggle:**

```svelte
<div class="flex items-center gap-1 p-0.5 bg-[var(--bg-muted)] rounded-md">
	<button
		class="px-2 py-1 text-xs rounded {view === 'flow' ? 'bg-[var(--bg-base)] shadow-sm' : ''}"
		onclick={() => (view = 'flow')}
	>
		Flow
	</button>
	<button
		class="px-2 py-1 text-xs rounded {view === 'grid' ? 'bg-[var(--bg-base)] shadow-sm' : ''}"
		onclick={() => (view = 'grid')}
	>
		Grid
	</button>
</div>
```

---

## Task Card Component

### Collapsed State (Flow View)

```
┌─────────────────────────────────────────────────────────────────┐
│  ◐  Implement JWT middleware                       IN PROGRESS  │
│     Create Express middleware for JWT validation...             │
│     ↳ Blocks: Integration tests                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Expanded State (on click)

```
┌─────────────────────────────────────────────────────────────────┐
│  ◐  Implement JWT middleware                       IN PROGRESS  │
│                                                                 │
│  Create Express middleware for JWT validation, including        │
│  token refresh logic and error handling. Should integrate       │
│  with existing auth service and support both access and         │
│  refresh tokens.                                                │
│                                                                 │
│  ┌────────────┐  ┌──────────────────────────────────────────┐   │
│  │  Blocks    │  │ Task 4: Integration tests                │   │
│  └────────────┘  └──────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### Component Implementation

```svelte
<!-- TaskCard.svelte -->
<script lang="ts">
	import { CheckCircle2, Circle, Loader2, AlertTriangle } from 'lucide-svelte';
	import type { TaskWithState } from '$lib/api-types';

	interface Props {
		task: TaskWithState;
		getTaskSubject: (id: string) => string;
		expanded?: boolean;
	}

	let { task, getTaskSubject, expanded = false }: Props = $props();
	let isExpanded = $state(expanded);
</script>

<button
	class="
    w-full text-left p-3 rounded-lg border transition-all
    {task.status === 'completed'
		? 'bg-[var(--success-subtle)]/30 border-[var(--success)]/20'
		: task.status === 'in_progress'
			? 'bg-[var(--nav-blue-subtle)] border-[var(--nav-blue)]/30'
			: task.isBlocked
				? 'bg-[var(--bg-muted)] border-[var(--border)] opacity-60'
				: 'bg-[var(--bg-base)] border-[var(--border)]'}
  "
	onclick={() => (isExpanded = !isExpanded)}
>
	<div class="flex items-start gap-3">
		<!-- Status Icon -->
		<div class="mt-0.5 shrink-0">
			{#if task.status === 'completed'}
				<CheckCircle2 size={18} class="text-[var(--success)]" />
			{:else if task.status === 'in_progress'}
				<Loader2 size={18} class="text-[var(--nav-blue)] animate-spin" />
			{:else if task.isBlocked}
				<Circle size={18} class="text-[var(--text-muted)]/50" />
			{:else}
				<Circle size={18} class="text-[var(--text-muted)]" />
			{/if}
		</div>

		<!-- Content -->
		<div class="flex-1 min-w-0">
			<div class="flex items-center justify-between gap-2">
				<h4 class="font-medium text-[var(--text-primary)] truncate">
					{task.subject}
				</h4>

				<!-- Status Badge -->
				{#if task.status === 'in_progress'}
					<span
						class="shrink-0 text-xs font-medium text-[var(--nav-blue)] uppercase tracking-wide"
					>
						In Progress
					</span>
				{:else if task.isBlocked}
					<span
						class="shrink-0 flex items-center gap-1 text-xs font-medium text-[var(--warning)]"
					>
						<AlertTriangle size={12} />
						Blocked
					</span>
				{/if}
			</div>

			<!-- Description preview or full -->
			<p class="text-sm text-[var(--text-secondary)] mt-1 {isExpanded ? '' : 'line-clamp-1'}">
				{task.description}
			</p>

			<!-- Live active_form for in_progress -->
			{#if task.status === 'in_progress' && task.active_form}
				<div class="flex items-center gap-2 mt-2 text-xs text-[var(--nav-blue)]">
					<span class="w-1.5 h-1.5 rounded-full bg-[var(--nav-blue)] animate-pulse" />
					{task.active_form}
				</div>
			{/if}

			<!-- Dependency labels -->
			{#if task.blocks.length > 0}
				<div class="text-xs text-[var(--text-muted)] mt-2">
					Blocks: {task.blocks.map((id) => getTaskSubject(id)).join(', ')}
				</div>
			{/if}

			{#if task.isBlocked && task.blocked_by.length > 0}
				<div class="text-xs text-[var(--warning)] mt-1">
					Waiting on: {task.blocked_by.map((id) => getTaskSubject(id)).join(', ')}
				</div>
			{/if}
		</div>
	</div>
</button>
```

---

## Empty State

For sessions without tasks (common for older sessions):

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│                          ○ ○ ○                                  │
│                                                                 │
│                   No structured tasks                           │
│                                                                 │
│     This session predates Claude Code v2.1.16 or used          │
│     simple prompts without planning.                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Implementation:**

```svelte
<EmptyState
	icon={ListTodo}
	title="No structured tasks"
	description="This session predates Claude Code v2.1.16 or used simple prompts without planning."
/>
```

---

## Live Updates

### Polling Integration

Extend existing `refreshData()` to include tasks:

```typescript
// ConversationView.svelte

let tasksArray = $state<Task[]>([]);

async function refreshSessionData() {
	// ... existing fetches ...
	const [sessionRes, timelineRes, fileActivityRes, subagentsRes, toolsRes, tasksRes] =
		await Promise.all([
			fetch(`http://localhost:8000/sessions/${uuid}?fresh=1`),
			fetch(`http://localhost:8000/sessions/${uuid}/timeline?fresh=1`),
			fetch(`http://localhost:8000/sessions/${uuid}/file-activity?fresh=1`),
			fetch(`http://localhost:8000/sessions/${uuid}/subagents?fresh=1`),
			fetch(`http://localhost:8000/sessions/${uuid}/tools?fresh=1`),
			fetch(`http://localhost:8000/sessions/${uuid}/tasks?fresh=1`) // NEW
		]);

	// ... existing processing ...
	tasksArray = tasksRes.ok ? await tasksRes.json() : [];
}
```

### Active Form Animation

When a task is `in_progress`, its `active_form` text should:

1. Display with a pulsing dot indicator
2. Update in real-time via polling
3. Show in both the summary bar and the task card

```svelte
<!-- Live status indicator -->
<div class="flex items-center gap-2">
	<span class="w-2 h-2 rounded-full bg-[var(--nav-blue)] animate-pulse" />
	<span class="text-sm text-[var(--nav-blue)] font-medium">
		{activeTask.active_form}
	</span>
</div>
```

---

## Computed States

### Task Processing

```typescript
// utils/tasks.ts

export function enrichTasks(tasks: Task[]): TaskWithState[] {
	const taskMap = new Map(tasks.map((t) => [t.id, t]));

	return tasks.map((task) => {
		// Check if any blocker is incomplete
		const isBlocked = task.blocked_by.some((id) => {
			const blocker = taskMap.get(id);
			return blocker && blocker.status !== 'completed';
		});

		const isReady = task.status === 'pending' && !isBlocked;

		return { ...task, isBlocked, isReady };
	});
}

export function getActiveTask(tasks: Task[]): Task | null {
	return tasks.find((t) => t.status === 'in_progress') || null;
}

export function getCompletedCount(tasks: Task[]): number {
	return tasks.filter((t) => t.status === 'completed').length;
}
```

---

## Interactions

| Action              | Behavior                           |
| ------------------- | ---------------------------------- |
| Click task card     | Toggle expanded description        |
| Hover blocked task  | No special behavior (read-only)    |
| Click view toggle   | Switch between Flow and Grid views |
| Live session active | Poll tasks, update active_form     |

---

## Responsive Behavior

### Desktop (>1024px)

- Full 3-column Kanban in Grid view
- Flow view with full dependency tree

### Tablet (768-1024px)

- Kanban columns stack to 2 + 1
- Flow view unchanged

### Mobile (<768px)

- Kanban hidden, Flow view only
- Cards stack vertically
- View toggle hidden

---

## Implementation Phases

### Phase 1: Core Implementation

1. Add `Task` interface to `api-types.ts`
2. Create `TasksTab.svelte` with basic list
3. Add "tasks" to tab arrays in `ConversationView.svelte`
4. Wire up API fetch in `refreshData()`

### Phase 2: Visual Polish

1. Create `TaskCard.svelte` with status styling
2. Add `TasksProgressBar.svelte` summary
3. Implement expand/collapse for descriptions
4. Add dependency text labels

### Phase 3: Live Updates

1. Integrate tasks into polling cycle
2. Add pulse animation for active_form
3. Add live indicator in progress bar

### Phase 4: Kanban View (Optional)

1. Create `TasksKanban.svelte` 3-column layout
2. Add view toggle
3. Persist view preference

---

## Test Cases

1. **Session with tasks** — Displays all tasks with correct statuses
2. **Session without tasks** — Shows empty state
3. **Live session** — Tasks update in real-time, active_form pulses
4. **Blocked tasks** — Shows "Waiting on" with blocker subjects
5. **Completed session** — All tasks show final state
6. **Agent session** — Tasks tab appears, scoped to agent

---

## Related Files

| File                      | Changes                                   |
| ------------------------- | ----------------------------------------- |
| `api-types.ts`            | Add `Task`, `TaskStatus`, `TaskWithState` |
| `ConversationView.svelte` | Add tasks tab, polling                    |
| `components/tasks/*`      | New component directory                   |
| `utils/tasks.ts`          | Task enrichment helpers                   |
