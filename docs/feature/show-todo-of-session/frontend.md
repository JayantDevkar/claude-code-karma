# Frontend Implementation Plan: Session Todos in Timeline

**Feature**: Show Todo Items in Session Timeline
**Role**: Frontend Engineer
**Estimated Effort**: 2-3 hours
**Dependencies**: Backend Phase 2 must be complete before starting Phase 2

---

## Overview

You will add todo visualization to the session timeline. This includes updating TypeScript types, extending the timeline component to render todo events, and optionally adding a dedicated todos section.

---

## Phase 1: Update TypeScript Types

**Duration**: 20 minutes
**File**: `packages/types/src/index.ts`
**Dependencies**: None (can start immediately)

### Task 1.1: Add TodoItem interface

Add after the existing interfaces:

```typescript
/**
 * A single todo item from a session or agent.
 */
export interface TodoItem {
  /** The todo task description */
  content: string;
  /** Current status of the todo */
  status: "pending" | "in_progress" | "completed";
  /** Present continuous form for display (e.g., "Exploring codebase") */
  activeForm?: string;
}
```

### Task 1.2: Extend TimelineEventType

Find the `TimelineEventType` definition and add `todo_update`:

```typescript
export type TimelineEventType =
  | "prompt"
  | "tool_call"
  | "subagent_spawn"
  | "thinking"
  | "response"
  | "todo_update";  // ADD THIS
```

### Task 1.3: Add TodoUpdateMetadata interface

```typescript
/**
 * Metadata for todo_update timeline events.
 */
export interface TodoUpdateMetadata {
  /** Whether todos were set or merged */
  action: "set" | "merge";
  /** Number of todos in this update */
  count: number;
  /** The actual todo items */
  todos: TodoItem[];
  /** Tool use ID that created this event */
  tool_id?: string;
  /** Agent ID if from a subagent */
  agent_id?: string;
  /** Agent slug if from a subagent */
  agent_slug?: string;
}
```

### Task 1.4: Extend SessionDetail type

Find the `SessionDetail` interface and add:

```typescript
export interface SessionDetail extends SessionSummary {
  // ... existing fields ...
  tools_used: Record<string, number>;
  git_branches: string[];
  working_directories: string[];
  total_input_tokens: number;
  total_output_tokens: number;
  cache_hit_rate: number;

  // ADD THESE:
  todo_count: number;
  todos: TodoItem[];
}
```

### Task 1.5: Extend SessionSummary type (if needed)

```typescript
export interface SessionSummary {
  // ... existing fields ...
  has_todos: boolean;
  todo_count: number;  // ADD THIS
}
```

### Acceptance Criteria
- [ ] `TodoItem` interface exported
- [ ] `TimelineEventType` includes `todo_update`
- [ ] `TodoUpdateMetadata` interface exported
- [ ] `SessionDetail` includes `todos` and `todo_count`
- [ ] TypeScript compiles without errors

---

## Phase 2: Extend Timeline Rail Component

**Duration**: 1 hour
**File**: `apps/web/components/timeline-rail.tsx`
**Dependencies**: Backend Phase 2 complete

### Task 2.1: Import required icons

Add to the icon imports at the top:

```typescript
import {
  // ... existing icons ...
  ListTodoIcon,
  CheckCircle2Icon,
  CircleDotIcon,
  CircleIcon,
} from "lucide-react";
```

### Task 2.2: Add todo_update to eventConfig

Find the `eventConfig` object and add the todo_update configuration:

```typescript
const eventConfig: Record<TimelineEventType, EventConfig> = {
  prompt: {
    icon: MessageSquareIcon,
    color: "text-blue-400",
    bgColor: "bg-blue-500/20",
    borderColor: "border-blue-500/40",
  },
  tool_call: {
    icon: WrenchIcon,
    color: "text-emerald-400",
    bgColor: "bg-emerald-500/20",
    borderColor: "border-emerald-500/40",
  },
  subagent_spawn: {
    icon: BotIcon,
    color: "text-purple-400",
    bgColor: "bg-purple-500/20",
    borderColor: "border-purple-500/40",
  },
  thinking: {
    icon: BrainIcon,
    color: "text-amber-400",
    bgColor: "bg-amber-500/20",
    borderColor: "border-amber-500/40",
  },
  response: {
    icon: MessageCircleIcon,
    color: "text-slate-400",
    bgColor: "bg-slate-500/20",
    borderColor: "border-slate-500/40",
  },
  // ADD THIS:
  todo_update: {
    icon: ListTodoIcon,
    color: "text-violet-400",
    bgColor: "bg-violet-500/20",
    borderColor: "border-violet-500/40",
  },
};
```

### Task 2.3: Create TodoStatusIcon component

Add a helper component for rendering todo status:

```typescript
interface TodoStatusIconProps {
  status: "pending" | "in_progress" | "completed";
  className?: string;
}

function TodoStatusIcon({ status, className = "" }: TodoStatusIconProps) {
  switch (status) {
    case "completed":
      return <CheckCircle2Icon className={`h-4 w-4 text-green-400 ${className}`} />;
    case "in_progress":
      return <CircleDotIcon className={`h-4 w-4 text-amber-400 ${className}`} />;
    case "pending":
    default:
      return <CircleIcon className={`h-4 w-4 text-slate-400 ${className}`} />;
  }
}
```

### Task 2.4: Create TodoList component

Add a component for rendering the list of todos:

```typescript
interface TodoListProps {
  todos: TodoItem[];
  maxItems?: number;
}

function TodoList({ todos, maxItems = 10 }: TodoListProps) {
  const displayTodos = maxItems ? todos.slice(0, maxItems) : todos;
  const hasMore = todos.length > displayTodos.length;

  return (
    <div className="space-y-1.5">
      {displayTodos.map((todo, index) => (
        <div
          key={index}
          className="flex items-start gap-2 text-sm"
        >
          <TodoStatusIcon status={todo.status} className="mt-0.5 flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <span className={cn(
              "block",
              todo.status === "completed" && "line-through text-muted-foreground"
            )}>
              {todo.content}
            </span>
            {todo.activeForm && todo.status === "in_progress" && (
              <span className="text-xs text-amber-400">
                {todo.activeForm}...
              </span>
            )}
          </div>
          <span className={cn(
            "text-xs px-1.5 py-0.5 rounded flex-shrink-0",
            todo.status === "completed" && "bg-green-500/20 text-green-400",
            todo.status === "in_progress" && "bg-amber-500/20 text-amber-400",
            todo.status === "pending" && "bg-slate-500/20 text-slate-400"
          )}>
            {todo.status.replace("_", " ")}
          </span>
        </div>
      ))}
      {hasMore && (
        <div className="text-xs text-muted-foreground pl-6">
          +{todos.length - displayTodos.length} more todos
        </div>
      )}
    </div>
  );
}
```

### Task 2.5: Add TodoUpdateContent component

Create the content renderer for todo_update events:

```typescript
interface TodoUpdateContentProps {
  metadata: TodoUpdateMetadata;
  isExpanded: boolean;
}

function TodoUpdateContent({ metadata, isExpanded }: TodoUpdateContentProps) {
  const { action, count, todos, agent_slug } = metadata;

  return (
    <div className="space-y-2">
      {/* Summary badges */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className={cn(
          "text-xs px-2 py-0.5 rounded",
          action === "merge" ? "bg-blue-500/20 text-blue-400" : "bg-violet-500/20 text-violet-400"
        )}>
          {action === "merge" ? "Merged" : "Set"} {count} todo{count !== 1 ? "s" : ""}
        </span>
        {agent_slug && (
          <span className="text-xs px-2 py-0.5 rounded bg-purple-500/20 text-purple-400">
            by {agent_slug}
          </span>
        )}
      </div>

      {/* Todo list - show when expanded or if few items */}
      {(isExpanded || todos.length <= 3) && todos.length > 0 && (
        <div className="mt-2 p-2 rounded bg-muted/30 border border-border/50">
          <TodoList todos={todos} maxItems={isExpanded ? undefined : 3} />
        </div>
      )}

      {/* Show expand hint if collapsed with many items */}
      {!isExpanded && todos.length > 3 && (
        <div className="text-xs text-muted-foreground">
          Click to see all {todos.length} todos
        </div>
      )}
    </div>
  );
}
```

### Task 2.6: Integrate into TimelineEventCard

In the `TimelineEventCard` component, add rendering for `todo_update` events. Find where content is rendered based on event type:

```typescript
function TimelineEventCard({ event, isExpanded, onToggle }: TimelineEventCardProps) {
  const config = eventConfig[event.event_type];
  const Icon = config.icon;

  // ... existing code ...

  const renderContent = () => {
    switch (event.event_type) {
      case "todo_update":
        return (
          <TodoUpdateContent
            metadata={event.metadata as TodoUpdateMetadata}
            isExpanded={isExpanded}
          />
        );

      case "tool_call":
        // Check if this is a TodoWrite that wasn't converted to todo_update
        if (event.metadata.tool_name === "TodoWrite" && event.metadata.todos) {
          return (
            <TodoUpdateContent
              metadata={event.metadata as TodoUpdateMetadata}
              isExpanded={isExpanded}
            />
          );
        }
        return <ToolCallContent metadata={event.metadata} isExpanded={isExpanded} />;

      // ... other cases ...
    }
  };

  // ... rest of component ...
}
```

### Task 2.7: Update stats bar

Add todo count to the stats bar at the top of the timeline:

```typescript
function TimelineStats({ events }: { events: TimelineEvent[] }) {
  const stats = useMemo(() => {
    return {
      prompts: events.filter(e => e.event_type === "prompt").length,
      toolCalls: events.filter(e => e.event_type === "tool_call").length,
      thinking: events.filter(e => e.event_type === "thinking").length,
      responses: events.filter(e => e.event_type === "response").length,
      // ADD THIS:
      todoUpdates: events.filter(e =>
        e.event_type === "todo_update" ||
        (e.event_type === "tool_call" && e.metadata.tool_name === "TodoWrite")
      ).length,
    };
  }, [events]);

  return (
    <div className="flex items-center gap-4 text-sm text-muted-foreground">
      <span>{stats.prompts} prompts</span>
      <span>{stats.toolCalls} tool calls</span>
      {stats.todoUpdates > 0 && (
        <span className="text-violet-400">{stats.todoUpdates} todo updates</span>
      )}
      {/* ... other stats ... */}
    </div>
  );
}
```

### Acceptance Criteria
- [ ] `todo_update` events render with violet color scheme
- [ ] TodoList shows status icons and strikethrough for completed
- [ ] Expandable content shows full todo list
- [ ] Stats bar shows todo update count
- [ ] Backwards compatible with `tool_call` TodoWrite events

---

## Phase 3: Add Session Todos Hook

**Duration**: 30 minutes
**File**: `apps/web/hooks/use-session.ts` or new file `apps/web/hooks/use-todos.ts`
**Dependencies**: Backend Phase 2 complete

### Task 3.1: Create useTodos hook

```typescript
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { TodoItem } from "@claude-karma/types";

interface UseTodosOptions {
  enabled?: boolean;
}

export function useTodos(sessionUuid: string, options: UseTodosOptions = {}) {
  return useQuery<TodoItem[]>({
    queryKey: ["session-todos", sessionUuid],
    queryFn: () => api.getTodos(sessionUuid),
    enabled: options.enabled !== false && !!sessionUuid,
    staleTime: 30 * 1000, // 30 seconds
  });
}
```

### Task 3.2: Add API method

In `apps/web/lib/api.ts`:

```typescript
export const api = {
  // ... existing methods ...

  async getTodos(sessionUuid: string): Promise<TodoItem[]> {
    const response = await fetch(`${API_BASE}/sessions/${sessionUuid}/todos`);
    if (!response.ok) {
      throw new Error(`Failed to fetch todos: ${response.statusText}`);
    }
    return response.json();
  },
};
```

### Acceptance Criteria
- [ ] `useTodos` hook fetches from `/sessions/{uuid}/todos`
- [ ] Proper caching with TanStack Query
- [ ] Error handling for failed requests

---

## Phase 4: Add Todos Section to Session Page (Optional Enhancement)

**Duration**: 45 minutes
**File**: `apps/web/app/session/[uuid]/page.tsx` or new component
**Dependencies**: Phase 3 complete

### Task 4.1: Create SessionTodosCard component

Create `apps/web/components/session-todos-card.tsx`:

```typescript
"use client";

import { useTodos } from "@/hooks/use-todos";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ListTodoIcon, CheckCircle2Icon, CircleDotIcon, CircleIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import type { TodoItem } from "@claude-karma/types";

interface SessionTodosCardProps {
  sessionUuid: string;
}

export function SessionTodosCard({ sessionUuid }: SessionTodosCardProps) {
  const { data: todos, isLoading, error } = useTodos(sessionUuid);

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <ListTodoIcon className="h-5 w-5" />
            Todos
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="animate-pulse space-y-2">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-6 bg-muted rounded" />
            ))}
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error || !todos) {
    return null; // Don't show card if no todos
  }

  if (todos.length === 0) {
    return null; // Don't show empty card
  }

  const completed = todos.filter(t => t.status === "completed").length;
  const inProgress = todos.filter(t => t.status === "in_progress").length;
  const pending = todos.filter(t => t.status === "pending").length;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span className="flex items-center gap-2 text-lg">
            <ListTodoIcon className="h-5 w-5 text-violet-400" />
            Todos
          </span>
          <span className="text-sm font-normal text-muted-foreground">
            {completed}/{todos.length} completed
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {/* Progress bar */}
        <div className="h-2 rounded-full bg-muted mb-4 overflow-hidden flex">
          {completed > 0 && (
            <div
              className="bg-green-500 h-full"
              style={{ width: `${(completed / todos.length) * 100}%` }}
            />
          )}
          {inProgress > 0 && (
            <div
              className="bg-amber-500 h-full"
              style={{ width: `${(inProgress / todos.length) * 100}%` }}
            />
          )}
          {pending > 0 && (
            <div
              className="bg-slate-500 h-full"
              style={{ width: `${(pending / todos.length) * 100}%` }}
            />
          )}
        </div>

        {/* Todo list */}
        <div className="space-y-2">
          {todos.map((todo, index) => (
            <TodoItemRow key={index} todo={todo} />
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function TodoItemRow({ todo }: { todo: TodoItem }) {
  const StatusIcon = {
    completed: CheckCircle2Icon,
    in_progress: CircleDotIcon,
    pending: CircleIcon,
  }[todo.status];

  const statusColor = {
    completed: "text-green-400",
    in_progress: "text-amber-400",
    pending: "text-slate-400",
  }[todo.status];

  return (
    <div className="flex items-start gap-2 py-1">
      <StatusIcon className={cn("h-4 w-4 mt-0.5 flex-shrink-0", statusColor)} />
      <div className="flex-1 min-w-0">
        <span className={cn(
          "text-sm",
          todo.status === "completed" && "line-through text-muted-foreground"
        )}>
          {todo.content}
        </span>
        {todo.activeForm && todo.status === "in_progress" && (
          <span className="block text-xs text-amber-400">
            {todo.activeForm}...
          </span>
        )}
      </div>
    </div>
  );
}
```

### Task 4.2: Add to session detail page

In `apps/web/app/session/[uuid]/page.tsx`, add the todos card:

```typescript
import { SessionTodosCard } from "@/components/session-todos-card";

export default function SessionPage({ params }: { params: { uuid: string } }) {
  const { uuid } = params;
  const { data: session } = useSession(uuid);

  return (
    <div className="space-y-6">
      {/* Existing session content */}
      <SessionHeader session={session} />

      {/* Add todos card if session has todos */}
      {session?.has_todos && (
        <SessionTodosCard sessionUuid={uuid} />
      )}

      {/* Rest of session content */}
    </div>
  );
}
```

### Acceptance Criteria
- [ ] Todos card shows when session has todos
- [ ] Progress bar visualizes completion status
- [ ] Each todo shows status icon and content
- [ ] In-progress todos show activeForm text
- [ ] Completed todos show strikethrough

---

## Phase 5: Testing

**Duration**: 30 minutes
**File**: `apps/web/__tests__/timeline-rail.test.tsx` (create or extend)

### Task 5.1: Test todo_update event rendering

```typescript
import { render, screen } from "@testing-library/react";
import { TimelineEventCard } from "@/components/timeline-rail";
import type { TimelineEvent } from "@claude-karma/types";

describe("TimelineEventCard - todo_update", () => {
  const todoUpdateEvent: TimelineEvent = {
    id: "evt-1",
    event_type: "todo_update",
    timestamp: "2026-01-10T10:00:00Z",
    actor: "session",
    actor_type: "session",
    title: "Update todos",
    summary: "Set 3 todos",
    metadata: {
      action: "set",
      count: 3,
      todos: [
        { content: "Fix bug", status: "completed", activeForm: "Fixing bug" },
        { content: "Add tests", status: "in_progress", activeForm: "Adding tests" },
        { content: "Deploy", status: "pending", activeForm: "Deploying" },
      ],
    },
  };

  it("renders todo_update event with correct styling", () => {
    render(<TimelineEventCard event={todoUpdateEvent} />);

    expect(screen.getByText("Update todos")).toBeInTheDocument();
    expect(screen.getByText("Set 3 todos")).toBeInTheDocument();
  });

  it("shows todo items when expanded", async () => {
    render(<TimelineEventCard event={todoUpdateEvent} isExpanded />);

    expect(screen.getByText("Fix bug")).toBeInTheDocument();
    expect(screen.getByText("Add tests")).toBeInTheDocument();
    expect(screen.getByText("Deploy")).toBeInTheDocument();
  });

  it("shows status indicators for todos", () => {
    render(<TimelineEventCard event={todoUpdateEvent} isExpanded />);

    expect(screen.getByText("completed")).toBeInTheDocument();
    expect(screen.getByText("in progress")).toBeInTheDocument();
    expect(screen.getByText("pending")).toBeInTheDocument();
  });

  it("applies strikethrough to completed todos", () => {
    render(<TimelineEventCard event={todoUpdateEvent} isExpanded />);

    const completedTodo = screen.getByText("Fix bug");
    expect(completedTodo).toHaveClass("line-through");
  });
});
```

### Task 5.2: Test TodoList component

```typescript
import { render, screen } from "@testing-library/react";
import { TodoList } from "@/components/timeline-rail";

describe("TodoList", () => {
  const todos = [
    { content: "Task 1", status: "completed" as const },
    { content: "Task 2", status: "in_progress" as const },
    { content: "Task 3", status: "pending" as const },
  ];

  it("renders all todos", () => {
    render(<TodoList todos={todos} />);

    expect(screen.getByText("Task 1")).toBeInTheDocument();
    expect(screen.getByText("Task 2")).toBeInTheDocument();
    expect(screen.getByText("Task 3")).toBeInTheDocument();
  });

  it("limits displayed todos with maxItems", () => {
    const manyTodos = Array.from({ length: 10 }, (_, i) => ({
      content: `Task ${i + 1}`,
      status: "pending" as const,
    }));

    render(<TodoList todos={manyTodos} maxItems={3} />);

    expect(screen.getByText("Task 1")).toBeInTheDocument();
    expect(screen.getByText("Task 2")).toBeInTheDocument();
    expect(screen.getByText("Task 3")).toBeInTheDocument();
    expect(screen.queryByText("Task 4")).not.toBeInTheDocument();
    expect(screen.getByText("+7 more todos")).toBeInTheDocument();
  });
});
```

### Task 5.3: Test useTodos hook

```typescript
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useTodos } from "@/hooks/use-todos";

describe("useTodos", () => {
  const queryClient = new QueryClient();
  const wrapper = ({ children }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );

  beforeEach(() => {
    fetchMock.resetMocks();
  });

  it("fetches todos from API", async () => {
    const mockTodos = [
      { content: "Test todo", status: "pending" },
    ];
    fetchMock.mockResponseOnce(JSON.stringify(mockTodos));

    const { result } = renderHook(() => useTodos("test-uuid"), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(mockTodos);
  });

  it("handles missing todos gracefully", async () => {
    fetchMock.mockResponseOnce(JSON.stringify([]));

    const { result } = renderHook(() => useTodos("test-uuid"), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([]);
  });
});
```

### Acceptance Criteria
- [ ] All unit tests pass
- [ ] Component rendering tests cover todo_update
- [ ] Hook tests verify API integration
- [ ] Edge cases tested (empty todos, many todos)

---

## Visual Design Reference

### Colors
| Status | Color | Tailwind Class |
|--------|-------|----------------|
| todo_update event | Violet | `text-violet-400`, `bg-violet-500/20` |
| completed | Green | `text-green-400` |
| in_progress | Amber | `text-amber-400` |
| pending | Slate | `text-slate-400` |

### Icons
| Element | Icon | Package |
|---------|------|---------|
| Todo update event | `ListTodoIcon` | lucide-react |
| Completed | `CheckCircle2Icon` | lucide-react |
| In progress | `CircleDotIcon` | lucide-react |
| Pending | `CircleIcon` | lucide-react |

---

## Checklist

### Phase 1: Types
- [ ] `TodoItem` interface added
- [ ] `TimelineEventType` includes `todo_update`
- [ ] `TodoUpdateMetadata` interface added
- [ ] `SessionDetail` includes `todos` and `todo_count`
- [ ] Types compile without errors

### Phase 2: Timeline Component
- [ ] `eventConfig` includes `todo_update`
- [ ] `TodoStatusIcon` component created
- [ ] `TodoList` component created
- [ ] `TodoUpdateContent` component created
- [ ] `TimelineEventCard` renders todo_update events
- [ ] Stats bar shows todo update count

### Phase 3: Hook
- [ ] `useTodos` hook created
- [ ] API method added
- [ ] Proper error handling

### Phase 4: Todos Card (Optional)
- [ ] `SessionTodosCard` component created
- [ ] Progress bar implemented
- [ ] Integrated into session page

### Phase 5: Testing
- [ ] Component tests written
- [ ] Hook tests written
- [ ] All tests pass

---

## Coordination with Backend

| Backend Phase | Frontend Can Start |
|---------------|-------------------|
| Phase 1 (Schema) | Phase 1 (Types) |
| Phase 2 (Endpoint) | Phase 2, 3, 4 |
| Phase 3 (Timeline) | Test Phase 2 |

You can start **Phase 1 (Types)** immediately. Wait for backend **Phase 2** before testing API integration.
