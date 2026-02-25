# UI/UX Improvement Plan - Phase 3: Session Cards & Components

**Priority**: High
**Effort**: Medium
**Impact**: High (core user interaction)

---

## Overview

This phase focuses on enhancing the session card experience, which is the primary entry point for users exploring their Claude Code activity. Better visual hierarchy, clearer information density, and improved interactivity.

---

## Issue 1: Session Name Display Inconsistency

### Current State

```typescript
// Sessions without slugs display UUID prefix (8 chars)
session.slug || session.uuid.slice(0, 8)
```

UUID fragments like "25c9848a" are not user-friendly and provide no context.

### Solution: Smart Session Naming

```typescript
// apps/web/lib/session-display.ts

interface SessionDisplayInfo {
  primaryName: string;      // Main display name
  secondaryLabel?: string;  // Subtitle or context
  isSlugBased: boolean;     // True if using human-readable slug
  shortId: string;          // Always available: first 8 chars of UUID
}

export function getSessionDisplayInfo(session: {
  slug: string | null;
  uuid: string;
  initial_prompt: string | null;
  models_used: string[];
}): SessionDisplayInfo {
  const shortId = session.uuid.slice(0, 8);

  // Case 1: Has a slug - use it directly
  if (session.slug) {
    return {
      primaryName: formatSlug(session.slug),
      secondaryLabel: shortId,
      isSlugBased: true,
      shortId,
    };
  }

  // Case 2: No slug - try to derive context from initial prompt
  const promptContext = deriveContextFromPrompt(session.initial_prompt);
  if (promptContext) {
    return {
      primaryName: promptContext,
      secondaryLabel: shortId,
      isSlugBased: false,
      shortId,
    };
  }

  // Case 3: Fallback - use model-based identifier
  const modelHint = session.models_used[0]
    ? parseModelName(session.models_used[0])?.family
    : null;

  return {
    primaryName: modelHint ? `${modelHint} Session` : 'Session',
    secondaryLabel: shortId,
    isSlugBased: false,
    shortId,
  };
}

function formatSlug(slug: string): string {
  // "eager-puzzling-fairy" -> "Eager Puzzling Fairy"
  return slug
    .split('-')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function deriveContextFromPrompt(prompt: string | null): string | null {
  if (!prompt) return null;

  const sanitized = sanitizePromptContent(prompt);
  if (sanitized.length < 20) return null;

  // Try to extract first meaningful phrase (up to 30 chars)
  const firstLine = sanitized.split('\n')[0].trim();
  if (firstLine.length > 30) {
    return firstLine.slice(0, 30) + '...';
  }
  return firstLine.length > 10 ? firstLine : null;
}
```

### Visual Result

| Scenario | Before | After |
|----------|--------|-------|
| Has slug | `eager-puzzling-fairy` | `Eager Puzzling Fairy` |
| No slug, has prompt | `25c9848a` | `"Add user auth..."` |
| No slug, no prompt | `25c9848a` | `Opus Session` |

---

## Issue 2: Session Card Visual Hierarchy

### Current State

Flat information presentation with no clear visual priority.

### Solution: Redesigned Session Card Layout

```
┌─────────────────────────────────────────────────────────────────┐
│ ┌──────────────────────────────────────────────────────────────┐│
│ │  🟣 Eager Puzzling Fairy                    4.5 Opus   2h ago ││
│ │     25c9848a                                                  ││
│ └──────────────────────────────────────────────────────────────┘│
│                                                                  │
│   "Help me implement a user authentication system with OAuth    │
│    2.0 support and JWT tokens..."                               │
│                                                                  │
│ ┌────────────────────────────────────────────────────────────┐  │
│ │  57 msgs  ·  18m 5s  ·  3 subagents  ·  12 tools          │  │
│ └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│ ┌─────┐ ┌────────┐ ┌───────────┐                               │
│ │main │ │feature │ │ 📋 Todos  │                               │
│ └─────┘ └────────┘ └───────────┘                               │
└─────────────────────────────────────────────────────────────────┘
```

### Component Structure

```typescript
// apps/web/components/session-card.tsx

interface SessionCardProps {
  session: SessionSummary;
  variant?: 'default' | 'compact';
}

export function SessionCard({ session, variant = 'default' }: SessionCardProps) {
  const displayInfo = getSessionDisplayInfo(session);
  const modelInfo = parseModelName(session.models_used[0]);
  const sanitizedPrompt = sanitizePromptContent(session.initial_prompt);
  const isSystemSession = isSystemContent(session.initial_prompt);

  return (
    <Link
      href={`/session/${session.uuid}`}
      className={cn(
        'group block rounded-lg border bg-card p-4',
        'hover:bg-surface-2 hover:border-primary/30',
        'transition-all duration-200',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'
      )}
    >
      {/* Header Row */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          {/* Activity indicator */}
          <div className={cn(
            'h-2 w-2 rounded-full shrink-0',
            isRecentSession(session.start_time) ? 'bg-green-500' : 'bg-muted'
          )} />

          <div className="min-w-0">
            <h3 className={cn(
              'font-medium truncate',
              displayInfo.isSlugBased ? 'text-foreground' : 'text-muted-foreground'
            )}>
              {displayInfo.primaryName}
            </h3>
            <p className="text-xs text-muted-foreground font-mono">
              {displayInfo.secondaryLabel}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {modelInfo && <ModelBadge modelName={session.models_used[0]} />}
          <span className="text-xs text-muted-foreground">
            {formatRelativeTime(session.start_time)}
          </span>
        </div>
      </div>

      {/* Prompt Preview */}
      {variant === 'default' && (
        <div className="mb-3">
          {isSystemSession ? (
            <p className="text-sm text-muted-foreground italic">
              System session
            </p>
          ) : (
            <p className="text-sm text-muted-foreground line-clamp-2">
              {sanitizedPrompt || 'No prompt captured'}
            </p>
          )}
        </div>
      )}

      {/* Stats Row */}
      <div className="flex items-center gap-3 text-xs text-muted-foreground mb-3">
        <span className="tabular-nums">{session.message_count} msgs</span>
        <span className="text-border">·</span>
        <span className="tabular-nums">{formatDurationCompact(session.duration_seconds)}</span>
        {session.subagent_count > 0 && (
          <>
            <span className="text-border">·</span>
            <span className="tabular-nums">{session.subagent_count} subagents</span>
          </>
        )}
        {Object.keys(session.tools_used || {}).length > 0 && (
          <>
            <span className="text-border">·</span>
            <span className="tabular-nums">
              {Object.values(session.tools_used || {}).reduce((a, b) => a + b, 0)} tools
            </span>
          </>
        )}
      </div>

      {/* Tags Row */}
      <div className="flex flex-wrap gap-1.5">
        {session.git_branches.slice(0, 2).map(branch => (
          <span
            key={branch}
            className="inline-flex items-center px-2 py-0.5 rounded-sm text-xs bg-secondary text-secondary-foreground"
          >
            <GitBranchIcon className="h-3 w-3 mr-1" />
            {branch}
          </span>
        ))}
        {session.git_branches.length > 2 && (
          <span className="text-xs text-muted-foreground">
            +{session.git_branches.length - 2}
          </span>
        )}
        {session.has_todos && (
          <span className="inline-flex items-center px-2 py-0.5 rounded-sm text-xs bg-green-500/20 text-green-400">
            <ListTodoIcon className="h-3 w-3 mr-1" />
            {session.todo_count} todos
          </span>
        )}
      </div>
    </Link>
  );
}

function isRecentSession(startTime: string | null): boolean {
  if (!startTime) return false;
  const hourAgo = Date.now() - 60 * 60 * 1000;
  return new Date(startTime).getTime() > hourAgo;
}
```

---

## Issue 3: Compact Card Variant for Lists

### Use Case

When viewing "By Branch" groupings, cards should be more compact to show more sessions.

### Solution

```typescript
// Compact variant for dense lists
{variant === 'compact' && (
  <div className="flex items-center justify-between">
    <div className="flex items-center gap-2">
      <span className="font-medium">{displayInfo.primaryName}</span>
      {modelInfo && <ModelBadge modelName={session.models_used[0]} />}
    </div>
    <div className="flex items-center gap-2 text-xs text-muted-foreground">
      <span className="tabular-nums">{session.message_count} msgs</span>
      <span className="text-border">·</span>
      <span>{formatRelativeTime(session.start_time)}</span>
    </div>
  </div>
)}
```

---

## Issue 4: Project Card Improvements

### Current Issues

- Icon and text alignment inconsistent
- No hover interaction feedback
- Missing activity indicator

### Solution

```typescript
// apps/web/components/project-card.tsx

export function ProjectCard({ project, relativePath }: ProjectCardProps) {
  const hasRecentActivity = isRecentProject(project.latest_session_time);

  return (
    <Link
      href={`/project/${project.encoded_name}`}
      className={cn(
        'group flex items-start gap-3 p-4 rounded-lg border bg-card',
        'hover:bg-surface-2 hover:border-primary/30',
        'transition-all duration-200'
      )}
    >
      {/* Icon with activity indicator */}
      <div className="relative shrink-0">
        <div className={cn(
          'h-10 w-10 rounded-lg flex items-center justify-center',
          project.is_git_repository
            ? 'bg-primary/10 text-primary'
            : 'bg-muted text-muted-foreground'
        )}>
          {project.is_git_repository ? (
            <GitBranchIcon className="h-5 w-5" />
          ) : (
            <FolderIcon className="h-5 w-5" />
          )}
        </div>
        {hasRecentActivity && (
          <div className="absolute -top-0.5 -right-0.5 h-2.5 w-2.5 rounded-full bg-green-500 border-2 border-card" />
        )}
      </div>

      {/* Content */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <h3 className="font-medium truncate group-hover:text-primary transition-colors">
            {getProjectDisplayName(project.path)}
          </h3>
          {project.is_nested_project && (
            <span className="shrink-0 text-xs px-1.5 py-0.5 rounded bg-secondary text-secondary-foreground">
              Nested
            </span>
          )}
        </div>

        <p className="text-sm text-muted-foreground truncate mt-0.5">
          {relativePath || project.path}
        </p>

        <div className="flex items-center gap-3 mt-2 text-xs text-muted-foreground">
          <span className="tabular-nums">{project.session_count} sessions</span>
          {project.agent_count > 0 && (
            <>
              <span className="text-border">·</span>
              <span className="tabular-nums">{project.agent_count} agents</span>
            </>
          )}
        </div>
      </div>

      {/* Arrow indicator on hover */}
      <ChevronRightIcon className="h-5 w-5 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity shrink-0" />
    </Link>
  );
}

function isRecentProject(latestTime: string | null): boolean {
  if (!latestTime) return false;
  const dayAgo = Date.now() - 24 * 60 * 60 * 1000;
  return new Date(latestTime).getTime() > dayAgo;
}
```

---

## Issue 5: Subagent Card Enhancements

### Current State

Basic card with limited information hierarchy.

### Solution

```typescript
// apps/web/components/subagent-card.tsx

export function SubagentCard({ agent }: { agent: SubagentSummary }) {
  const topTools = getTopTools(agent.tools_used, 3);

  return (
    <div className={cn(
      'p-4 rounded-lg border bg-card',
      'hover:bg-surface-2 transition-colors'
    )}>
      {/* Header */}
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2">
          <div className="h-8 w-8 rounded-lg bg-purple-500/20 flex items-center justify-center">
            <BotIcon className="h-4 w-4 text-purple-400" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <code className="text-sm font-mono font-medium">
                {agent.agent_id}
              </code>
              {agent.subagent_type && (
                <SubagentTypeBadge type={agent.subagent_type} />
              )}
            </div>
            <p className="text-xs text-muted-foreground tabular-nums">
              {agent.message_count} messages
            </p>
          </div>
        </div>
      </div>

      {/* Task Description */}
      {agent.initial_prompt && (
        <p className="text-sm text-muted-foreground line-clamp-2 mb-3">
          {sanitizePromptContent(agent.initial_prompt)}
        </p>
      )}

      {/* Tools Used */}
      {topTools.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {topTools.map(([tool, count]) => (
            <span
              key={tool}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-secondary text-secondary-foreground"
            >
              {tool}
              <span className="text-muted-foreground tabular-nums">x{count}</span>
            </span>
          ))}
          {Object.keys(agent.tools_used).length > 3 && (
            <span className="text-xs text-muted-foreground">
              +{Object.keys(agent.tools_used).length - 3}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

function getTopTools(tools: Record<string, number>, limit: number): [string, number][] {
  return Object.entries(tools)
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit);
}
```

---

## Implementation Checklist

### New Files

- [ ] `apps/web/lib/session-display.ts` - Session naming utilities

### Modified Files

- [ ] `apps/web/components/session-card.tsx` - Full redesign
- [ ] `apps/web/components/project-card.tsx` - Enhanced layout
- [ ] `apps/web/components/subagent-card.tsx` - Better hierarchy
- [ ] `apps/web/components/sessions-by-branch.tsx` - Support compact variant

---

## Verification Steps

1. **Session Cards**: Verify human-readable names appear for slug-based sessions
2. **Fallback Names**: Verify non-slug sessions show contextual names
3. **Hover States**: Verify smooth transitions on card hover
4. **Activity Indicators**: Verify green dots appear for recent sessions
5. **Responsive**: Test card layouts on mobile, tablet, desktop

---

## Dependencies

- Phase 1 (Foundation) - CSS variables and typography
- Phase 2 (Data Sanitization) - Content sanitizer utility

---

## Next Phase

Phase 4: Timeline & Interactivity - enhances the timeline experience with better filtering and event display.
