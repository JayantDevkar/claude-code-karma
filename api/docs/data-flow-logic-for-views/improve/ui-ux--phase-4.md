# UI/UX Improvement Plan - Phase 4: Timeline & Interactivity

**Priority**: High
**Effort**: High
**Impact**: High (core feature for session exploration)

---

## Overview

The Timeline view is the heart of session exploration. This phase focuses on enhancing the timeline experience with better filtering, clearer event representation, and improved interactivity.

---

## Issue 1: Filter Bar Clarity

### Current State

```
| 💬 15 user prompts | 🔧 89 tool calls | 🤖 5 subagents |
```

Filter chips blend together, no clear indication of active/inactive state.

### Solution: Enhanced Filter Bar

```typescript
// apps/web/components/timeline-filter-bar.tsx

interface FilterBarProps {
  counts: {
    prompts: number;
    toolCalls: number;
    subagents: number;
    todoUpdates: number;
  };
  activeFilters: Set<FilterCategory>;
  onToggle: (category: FilterCategory) => void;
  totalEvents: number;
}

export function TimelineFilterBar({
  counts,
  activeFilters,
  onToggle,
  totalEvents,
}: FilterBarProps) {
  const hasActiveFilters = activeFilters.size > 0;

  return (
    <div className="sticky top-0 z-10 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 border-b py-3">
      <div className="flex items-center justify-between gap-4 px-4">
        {/* Filter Chips */}
        <div className="flex items-center gap-2 overflow-x-auto pb-1">
          <FilterChip
            label="User prompts"
            count={counts.prompts}
            icon={MessageSquareIcon}
            color="blue"
            active={activeFilters.has('prompt')}
            onClick={() => onToggle('prompt')}
          />
          <FilterChip
            label="Tool calls"
            count={counts.toolCalls}
            icon={TerminalIcon}
            color="emerald"
            active={activeFilters.has('tool_call')}
            onClick={() => onToggle('tool_call')}
          />
          <FilterChip
            label="Subagents"
            count={counts.subagents}
            icon={BotIcon}
            color="purple"
            active={activeFilters.has('subagent')}
            onClick={() => onToggle('subagent')}
          />
          {counts.todoUpdates > 0 && (
            <FilterChip
              label="Todo updates"
              count={counts.todoUpdates}
              icon={ListTodoIcon}
              color="violet"
              active={activeFilters.has('todo_update')}
              onClick={() => onToggle('todo_update')}
            />
          )}
        </div>

        {/* Summary & Clear */}
        <div className="flex items-center gap-3 shrink-0">
          <span className="text-sm text-muted-foreground tabular-nums">
            {hasActiveFilters
              ? `Showing filtered · ${totalEvents} total`
              : `${totalEvents} events`
            }
          </span>
          {hasActiveFilters && (
            <button
              onClick={() => activeFilters.clear()}
              className="text-sm text-primary hover:underline"
            >
              Clear filters
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
```

### Filter Chip Component

```typescript
interface FilterChipProps {
  label: string;
  count: number;
  icon: LucideIcon;
  color: 'blue' | 'emerald' | 'purple' | 'violet' | 'amber';
  active: boolean;
  onClick: () => void;
}

const colorClasses = {
  blue: {
    active: 'bg-blue-500/20 text-blue-400 border-blue-500/50',
    inactive: 'bg-transparent text-muted-foreground border-border hover:border-blue-500/30',
  },
  emerald: {
    active: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/50',
    inactive: 'bg-transparent text-muted-foreground border-border hover:border-emerald-500/30',
  },
  purple: {
    active: 'bg-purple-500/20 text-purple-400 border-purple-500/50',
    inactive: 'bg-transparent text-muted-foreground border-border hover:border-purple-500/30',
  },
  violet: {
    active: 'bg-violet-500/20 text-violet-400 border-violet-500/50',
    inactive: 'bg-transparent text-muted-foreground border-border hover:border-violet-500/30',
  },
  amber: {
    active: 'bg-amber-500/20 text-amber-400 border-amber-500/50',
    inactive: 'bg-transparent text-muted-foreground border-border hover:border-amber-500/30',
  },
};

export function FilterChip({
  label,
  count,
  icon: Icon,
  color,
  active,
  onClick,
}: FilterChipProps) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        'inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm border',
        'transition-all duration-200',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        active ? colorClasses[color].active : colorClasses[color].inactive
      )}
    >
      <Icon className="h-4 w-4" />
      <span>{label}</span>
      <span className={cn(
        'tabular-nums px-1.5 py-0.5 rounded-full text-xs',
        active ? 'bg-white/10' : 'bg-secondary'
      )}>
        {count}
      </span>
    </button>
  );
}
```

---

## Issue 2: Event Card Visual Hierarchy

### Current State

All events look similar, making it hard to scan for important activities.

### Solution: Tiered Event Importance

```typescript
// apps/web/components/timeline-event-card.tsx

type EventImportance = 'high' | 'medium' | 'low';

function getEventImportance(event: TimelineEvent): EventImportance {
  // High importance: User actions, major state changes
  if (event.event_type === 'prompt') return 'high';
  if (event.event_type === 'subagent_spawn') return 'high';
  if (event.event_type === 'todo_update') return 'medium';

  // Medium: File modifications
  if (event.event_type === 'tool_call') {
    const modifyTools = ['Write', 'StrReplace', 'Delete', 'Shell'];
    if (modifyTools.includes(event.metadata?.tool_name)) return 'medium';
  }

  // Low: Read operations, thinking
  return 'low';
}

export function TimelineEventCard({
  event,
  isFiltered,
  sessionStartTime,
}: {
  event: TimelineEvent;
  isFiltered: boolean;
  sessionStartTime: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const importance = getEventImportance(event);
  const elapsedTime = formatElapsedTime(event.timestamp, sessionStartTime);

  return (
    <div
      className={cn(
        'relative pl-10 pb-6',
        isFiltered && 'opacity-40'
      )}
    >
      {/* Timeline Node */}
      <div className={cn(
        'absolute left-0 top-0 h-8 w-8 rounded-full border-2 flex items-center justify-center',
        'transition-all duration-200',
        EVENT_STYLES[event.event_type].node,
        importance === 'high' && 'ring-2 ring-offset-2 ring-offset-background'
      )}>
        {EVENT_STYLES[event.event_type].icon}
      </div>

      {/* Timeline Rail */}
      <div className="absolute left-[15px] top-8 bottom-0 w-0.5 bg-border" />

      {/* Event Card */}
      <div
        className={cn(
          'ml-4 rounded-lg border bg-card overflow-hidden',
          'hover:bg-surface-2 transition-colors cursor-pointer',
          importance === 'high' && 'border-primary/30'
        )}
        onClick={() => setExpanded(!expanded)}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-3">
          <div className="flex items-center gap-2">
            <span className={cn(
              'font-medium',
              EVENT_STYLES[event.event_type].text
            )}>
              {event.title}
            </span>

            {/* Badges */}
            {event.metadata?.tool_name && (
              <code className="text-xs px-1.5 py-0.5 rounded bg-secondary font-mono">
                {event.metadata.tool_name}
              </code>
            )}
            {event.metadata?.spawned_agent_id && (
              <span className="text-xs px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-400">
                → {event.metadata.spawned_agent_id.slice(0, 7)}
              </span>
            )}
            {event.metadata?.result_status && (
              <span className={cn(
                'text-xs px-1.5 py-0.5 rounded',
                event.metadata.result_status === 'success'
                  ? 'bg-green-500/20 text-green-400'
                  : 'bg-red-500/20 text-red-400'
              )}>
                {event.metadata.result_status === 'success' ? '✓' : '✗'}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span className="tabular-nums">{elapsedTime}</span>
            <ChevronDownIcon className={cn(
              'h-4 w-4 transition-transform',
              expanded && 'rotate-180'
            )} />
          </div>
        </div>

        {/* Summary (always visible) */}
        {event.summary && !expanded && (
          <div className="px-3 pb-3">
            <p className="text-sm text-muted-foreground line-clamp-2">
              {sanitizePromptContent(event.summary)}
            </p>
          </div>
        )}

        {/* Expanded Content */}
        {expanded && (
          <ExpandedEventContent event={event} />
        )}
      </div>
    </div>
  );
}
```

---

## Issue 3: Tool Call Detail View

### Current State

Expanded tool calls show raw JSON input/output.

### Solution: Formatted Tool Content

```typescript
// apps/web/components/tool-call-detail.tsx

export function ToolCallDetail({ event }: { event: TimelineEvent }) {
  const { tool_name, input, result } = event.metadata;

  return (
    <div className="border-t bg-surface-1 p-4 space-y-4">
      {/* Input Section */}
      <div>
        <h4 className="text-xs font-medium text-muted-foreground uppercase mb-2">
          Input
        </h4>
        <ToolInput tool={tool_name} input={input} />
      </div>

      {/* Output Section */}
      {result && (
        <div>
          <h4 className="text-xs font-medium text-muted-foreground uppercase mb-2">
            Result
          </h4>
          <ToolResult tool={tool_name} result={result} />
        </div>
      )}
    </div>
  );
}

function ToolInput({ tool, input }: { tool: string; input: any }) {
  switch (tool) {
    case 'Read':
      return (
        <div className="font-mono text-sm bg-secondary rounded p-2">
          <span className="text-blue-400">Reading:</span> {input.file_path}
          {input.offset && <span className="text-muted-foreground"> (lines {input.offset}-{input.offset + input.limit})</span>}
        </div>
      );

    case 'Write':
    case 'StrReplace':
      return (
        <div className="space-y-2">
          <div className="font-mono text-sm bg-secondary rounded p-2">
            <span className="text-green-400">File:</span> {input.file_path}
          </div>
          {input.content && (
            <pre className="font-mono text-xs bg-secondary rounded p-2 overflow-x-auto max-h-40">
              {input.content.slice(0, 500)}
              {input.content.length > 500 && '...'}
            </pre>
          )}
        </div>
      );

    case 'Shell':
      return (
        <pre className="font-mono text-sm bg-secondary rounded p-2 text-emerald-400">
          $ {input.command}
        </pre>
      );

    case 'Glob':
    case 'Grep':
      return (
        <div className="font-mono text-sm bg-secondary rounded p-2">
          <span className="text-purple-400">Pattern:</span> {input.pattern}
          {input.path && <span className="text-muted-foreground"> in {input.path}</span>}
        </div>
      );

    default:
      return (
        <pre className="font-mono text-xs bg-secondary rounded p-2 overflow-x-auto max-h-40">
          {JSON.stringify(input, null, 2)}
        </pre>
      );
  }
}

function ToolResult({ tool, result }: { tool: string; result: any }) {
  // Truncate long results
  const maxLength = 1000;
  const content = typeof result === 'string' ? result : JSON.stringify(result, null, 2);
  const truncated = content.length > maxLength;

  return (
    <div>
      <pre className="font-mono text-xs bg-secondary rounded p-2 overflow-x-auto max-h-60">
        {truncated ? content.slice(0, maxLength) + '\n...' : content}
      </pre>
      {truncated && (
        <button className="text-xs text-primary mt-1 hover:underline">
          Show full result ({Math.round(content.length / 1024)}KB)
        </button>
      )}
    </div>
  );
}
```

---

## Issue 4: Todo Update Display

### Current State

Todo updates show as a list, but lack visual status indicators.

### Solution: Enhanced Todo List Display

```typescript
// apps/web/components/todo-update-detail.tsx

export function TodoUpdateDetail({ todos }: { todos: TodoItem[] }) {
  const completed = todos.filter(t => t.status === 'completed').length;
  const inProgress = todos.filter(t => t.status === 'in_progress').length;
  const pending = todos.filter(t => t.status === 'pending').length;

  return (
    <div className="border-t bg-surface-1 p-4">
      {/* Summary */}
      <div className="flex items-center gap-3 mb-3 text-xs text-muted-foreground">
        {completed > 0 && (
          <span className="flex items-center gap-1 text-green-400">
            <CheckCircleIcon className="h-3 w-3" /> {completed} completed
          </span>
        )}
        {inProgress > 0 && (
          <span className="flex items-center gap-1 text-amber-400">
            <CircleDotIcon className="h-3 w-3" /> {inProgress} in progress
          </span>
        )}
        {pending > 0 && (
          <span className="flex items-center gap-1 text-slate-400">
            <CircleIcon className="h-3 w-3" /> {pending} pending
          </span>
        )}
      </div>

      {/* Todo List */}
      <div className="space-y-2">
        {todos.map((todo, index) => (
          <div
            key={index}
            className={cn(
              'flex items-start gap-3 p-2 rounded',
              todo.status === 'completed' && 'bg-green-500/10',
              todo.status === 'in_progress' && 'bg-amber-500/10'
            )}
          >
            <TodoStatusIcon status={todo.status} />
            <div className="flex-1 min-w-0">
              <p className={cn(
                'text-sm',
                todo.status === 'completed' && 'text-muted-foreground line-through'
              )}>
                {todo.content}
              </p>
              {todo.status === 'in_progress' && todo.activeForm && (
                <p className="text-xs text-amber-400 mt-0.5 italic">
                  {todo.activeForm}
                </p>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function TodoStatusIcon({ status }: { status: TodoItem['status'] }) {
  switch (status) {
    case 'completed':
      return <CheckCircleIcon className="h-4 w-4 text-green-400 shrink-0 mt-0.5" />;
    case 'in_progress':
      return <CircleDotIcon className="h-4 w-4 text-amber-400 shrink-0 mt-0.5 animate-pulse" />;
    default:
      return <CircleIcon className="h-4 w-4 text-slate-400 shrink-0 mt-0.5" />;
  }
}
```

---

## Issue 5: Keyboard Navigation

### Current State

No keyboard shortcuts for timeline navigation.

### Solution: Add Keyboard Navigation

```typescript
// apps/web/hooks/use-timeline-keyboard.ts

export function useTimelineKeyboard({
  events,
  expandedId,
  setExpandedId,
}: {
  events: TimelineEvent[];
  expandedId: string | null;
  setExpandedId: (id: string | null) => void;
}) {
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      // Don't capture when typing in inputs
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return;
      }

      const currentIndex = events.findIndex(ev => ev.id === expandedId);

      switch (e.key) {
        case 'j':
        case 'ArrowDown':
          e.preventDefault();
          if (currentIndex < events.length - 1) {
            setExpandedId(events[currentIndex + 1].id);
          }
          break;

        case 'k':
        case 'ArrowUp':
          e.preventDefault();
          if (currentIndex > 0) {
            setExpandedId(events[currentIndex - 1].id);
          }
          break;

        case 'Enter':
        case ' ':
          e.preventDefault();
          // Toggle current expansion
          setExpandedId(expandedId ? null : events[currentIndex]?.id || events[0]?.id);
          break;

        case 'Escape':
          setExpandedId(null);
          break;
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [events, expandedId, setExpandedId]);
}
```

### Keyboard Shortcuts Hint

```typescript
// Show hint at bottom of timeline
<div className="text-xs text-muted-foreground text-center py-4 border-t">
  <kbd className="px-1.5 py-0.5 rounded bg-secondary">j</kbd> / <kbd className="px-1.5 py-0.5 rounded bg-secondary">k</kbd> to navigate
  <span className="mx-2">·</span>
  <kbd className="px-1.5 py-0.5 rounded bg-secondary">Enter</kbd> to expand
  <span className="mx-2">·</span>
  <kbd className="px-1.5 py-0.5 rounded bg-secondary">Esc</kbd> to collapse
</div>
```

---

## Implementation Checklist

### New Files

- [ ] `apps/web/components/timeline-filter-bar.tsx`
- [ ] `apps/web/components/tool-call-detail.tsx`
- [ ] `apps/web/components/todo-update-detail.tsx`
- [ ] `apps/web/hooks/use-timeline-keyboard.ts`

### Modified Files

- [ ] `apps/web/components/timeline-rail.tsx` - Major refactor
- [ ] `apps/web/app/session/[uuid]/timeline/page.tsx` - Add keyboard support

---

## Verification Steps

1. **Filter Bar**: Verify filters toggle correctly with visual feedback
2. **Event Cards**: Verify high-importance events are visually distinct
3. **Tool Details**: Verify formatted tool inputs for Read, Write, Shell
4. **Todo Display**: Verify status icons and progress indicators
5. **Keyboard**: Verify j/k navigation, Enter expand, Esc collapse

---

## Dependencies

- Phase 2 (Data Sanitization) - Content sanitizer
- Phase 3 (Components) - Shared utilities

---

## Next Phase

Phase 5: Navigation & Accessibility - adds command palette and improves overall accessibility.
