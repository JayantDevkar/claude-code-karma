# Agent Work Summary - Frontend Implementation Guide

## Overview

This document provides implementation details for updating the Agents tab UI to display task summary data including duration, token usage, completion status, and file operations.

**Goal**: Enhance the SubagentCard component to show rich task completion information.

**Prerequisite**: Backend changes must be deployed first (see `backend.md`).

---

## Current State

**Page**: `apps/web/app/session/[uuid]/agents/page.tsx`
**Card Component**: `apps/web/components/subagent-card.tsx`
**Types**: `packages/types/src/index.ts`

**Current SubagentSummary Type**:
```typescript
interface SubagentSummary {
  agent_id: string;
  slug: string | null;
  subagent_type: string | null;
  tools_used: Record<string, number>;
  message_count: number;
  initial_prompt: string | null;
}
```

---

## Phase 1: Update Types

**File**: `packages/types/src/index.ts`

### 1.1 Extend SubagentSummary Interface

```typescript
export interface SubagentSummary {
  // Existing fields
  agent_id: string;
  slug: string | null;
  subagent_type: string | null;
  tools_used: Record<string, number>;
  message_count: number;
  initial_prompt: string | null;

  // NEW: Timing
  start_time: string | null;      // ISO timestamp
  end_time: string | null;        // ISO timestamp
  duration_seconds: number | null;

  // NEW: Token usage
  total_input_tokens: number;
  total_output_tokens: number;
  cache_read_tokens: number;
  cache_creation_tokens: number;
  cache_hit_rate: number;         // 0.0 to 1.0

  // NEW: Completion
  completion_status: 'completed' | 'error' | null;
  final_output: string | null;

  // NEW: File operations
  file_read_count: number;
  file_write_count: number;

  // NEW: Models
  models_used: string[];
}
```

### 1.2 Rebuild Types Package

```bash
pnpm --filter @claude-karma/types build
```

---

## Phase 2: Create Helper Utilities

**File**: `apps/web/lib/format.ts`

### 2.1 Add Duration Formatter

```typescript
/**
 * Format duration in seconds to human-readable string.
 * Examples: "2m 30s", "1h 15m", "45s"
 */
export function formatDuration(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return '-';

  if (seconds < 60) {
    return `${Math.round(seconds)}s`;
  }

  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.round(seconds % 60);

  if (minutes < 60) {
    return remainingSeconds > 0
      ? `${minutes}m ${remainingSeconds}s`
      : `${minutes}m`;
  }

  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;

  return remainingMinutes > 0
    ? `${hours}h ${remainingMinutes}m`
    : `${hours}h`;
}
```

### 2.2 Add Token Formatter

```typescript
/**
 * Format token count with K/M suffix.
 * Examples: "1.2K", "15.4K", "2.1M"
 */
export function formatTokens(count: number): string {
  if (count < 1000) return count.toString();
  if (count < 1000000) return `${(count / 1000).toFixed(1)}K`;
  return `${(count / 1000000).toFixed(1)}M`;
}
```

### 2.3 Add Cache Rate Formatter

```typescript
/**
 * Format cache hit rate as percentage.
 * Example: 0.778 -> "78%"
 */
export function formatCacheRate(rate: number): string {
  return `${Math.round(rate * 100)}%`;
}
```

---

## Phase 3: Create Completion Status Badge

**File**: `apps/web/components/completion-status-badge.tsx` (NEW)

```tsx
import { CheckCircle, XCircle, Circle } from 'lucide-react';
import { cn } from '@/lib/utils';

interface CompletionStatusBadgeProps {
  status: 'completed' | 'error' | null;
  className?: string;
}

export function CompletionStatusBadge({ status, className }: CompletionStatusBadgeProps) {
  if (!status) {
    return (
      <span className={cn(
        "inline-flex items-center gap-1 text-xs text-muted-foreground",
        className
      )}>
        <Circle className="h-3 w-3" />
        Unknown
      </span>
    );
  }

  if (status === 'completed') {
    return (
      <span className={cn(
        "inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400",
        className
      )}>
        <CheckCircle className="h-3 w-3" />
        Completed
      </span>
    );
  }

  return (
    <span className={cn(
      "inline-flex items-center gap-1 text-xs text-red-600 dark:text-red-400",
      className
    )}>
      <XCircle className="h-3 w-3" />
      Error
    </span>
  );
}
```

---

## Phase 4: Create Stats Components

**File**: `apps/web/components/agent-stats.tsx` (NEW)

```tsx
import { Clock, Cpu, FileText, FileEdit, Zap } from 'lucide-react';
import { formatDuration, formatTokens, formatCacheRate } from '@/lib/format';
import { cn } from '@/lib/utils';

interface AgentStatsProps {
  durationSeconds: number | null;
  totalInputTokens: number;
  totalOutputTokens: number;
  cacheHitRate: number;
  fileReadCount: number;
  fileWriteCount: number;
  className?: string;
}

export function AgentStats({
  durationSeconds,
  totalInputTokens,
  totalOutputTokens,
  cacheHitRate,
  fileReadCount,
  fileWriteCount,
  className,
}: AgentStatsProps) {
  const totalTokens = totalInputTokens + totalOutputTokens;

  return (
    <div className={cn("grid grid-cols-2 gap-2 text-xs", className)}>
      {/* Duration */}
      <div className="flex items-center gap-1.5 text-muted-foreground">
        <Clock className="h-3.5 w-3.5" />
        <span>{formatDuration(durationSeconds)}</span>
      </div>

      {/* Tokens */}
      <div className="flex items-center gap-1.5 text-muted-foreground">
        <Cpu className="h-3.5 w-3.5" />
        <span>{formatTokens(totalTokens)} tokens</span>
      </div>

      {/* Cache */}
      {cacheHitRate > 0 && (
        <div className="flex items-center gap-1.5 text-muted-foreground">
          <Zap className="h-3.5 w-3.5 text-amber-500" />
          <span>{formatCacheRate(cacheHitRate)} cache</span>
        </div>
      )}

      {/* File Operations */}
      {(fileReadCount > 0 || fileWriteCount > 0) && (
        <div className="flex items-center gap-1.5 text-muted-foreground">
          {fileWriteCount > 0 ? (
            <>
              <FileEdit className="h-3.5 w-3.5" />
              <span>{fileReadCount}R / {fileWriteCount}W</span>
            </>
          ) : (
            <>
              <FileText className="h-3.5 w-3.5" />
              <span>{fileReadCount} reads</span>
            </>
          )}
        </div>
      )}
    </div>
  );
}
```

---

## Phase 5: Update SubagentCard Component

**File**: `apps/web/components/subagent-card.tsx`

### 5.1 Import New Components

```tsx
import { CompletionStatusBadge } from './completion-status-badge';
import { AgentStats } from './agent-stats';
import { formatDuration } from '@/lib/format';
```

### 5.2 Update Card Header

Add completion status badge next to the type badge:

```tsx
// In the card header section
<div className="flex items-center justify-between">
  <div className="flex items-center gap-2">
    <code className="text-xs font-mono text-muted-foreground">
      {subagent.agent_id}
    </code>
    <SubagentTypeBadge type={subagent.subagent_type} size="sm" />
    <CompletionStatusBadge status={subagent.completion_status} />
  </div>

  {/* Duration in header for quick glance */}
  {subagent.duration_seconds !== null && (
    <span className="text-xs text-muted-foreground">
      {formatDuration(subagent.duration_seconds)}
    </span>
  )}
</div>
```

### 5.3 Replace Stats Row with AgentStats

Replace the existing stats row with the new component:

```tsx
// Replace existing stats row
<AgentStats
  durationSeconds={subagent.duration_seconds}
  totalInputTokens={subagent.total_input_tokens}
  totalOutputTokens={subagent.total_output_tokens}
  cacheHitRate={subagent.cache_hit_rate}
  fileReadCount={subagent.file_read_count}
  fileWriteCount={subagent.file_write_count}
  className="mt-3"
/>
```

### 5.4 Add Final Output in Expanded View

When the card is expanded, show the final output:

```tsx
{isExpanded && subagent.final_output && (
  <div className="mt-3 pt-3 border-t">
    <h4 className="text-xs font-medium text-muted-foreground mb-1">
      Final Output
    </h4>
    <p className="text-sm text-foreground/80 whitespace-pre-wrap">
      {subagent.final_output}
    </p>
  </div>
)}
```

### 5.5 Show Models Used

Add models used section:

```tsx
{isExpanded && subagent.models_used.length > 0 && (
  <div className="mt-2 flex items-center gap-1">
    <span className="text-xs text-muted-foreground">Models:</span>
    {subagent.models_used.map((model) => (
      <span
        key={model}
        className="text-xs px-1.5 py-0.5 bg-secondary rounded"
      >
        {model.replace('claude-', '').replace('-20250514', '')}
      </span>
    ))}
  </div>
)}
```

### 5.6 Complete Updated Component

```tsx
'use client';

import { useState } from 'react';
import { ChevronDown, ChevronUp, MessageSquare, Wrench } from 'lucide-react';
import { SubagentSummary } from '@claude-karma/types';
import { SubagentTypeBadge } from './subagent-type-badge';
import { CompletionStatusBadge } from './completion-status-badge';
import { AgentStats } from './agent-stats';
import { formatDuration } from '@/lib/format';
import { cn } from '@/lib/utils';

interface SubagentCardProps {
  subagent: SubagentSummary;
}

export function SubagentCard({ subagent }: SubagentCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const toolEntries = Object.entries(subagent.tools_used).sort(
    ([, a], [, b]) => b - a
  );
  const totalToolCalls = toolEntries.reduce((sum, [, count]) => sum + count, 0);
  const topTools = toolEntries.slice(0, 5);
  const hasMoreTools = toolEntries.length > 5;
  const hasLongPrompt = (subagent.initial_prompt?.length ?? 0) > 200;
  const isExpandable = hasMoreTools || hasLongPrompt || subagent.final_output;

  return (
    <div
      className={cn(
        "rounded-lg border bg-card p-4 transition-all",
        isExpandable && "cursor-pointer hover:border-primary/50"
      )}
      onClick={() => isExpandable && setIsExpanded(!isExpanded)}
      onKeyDown={(e) => {
        if (isExpandable && (e.key === 'Enter' || e.key === ' ')) {
          e.preventDefault();
          setIsExpanded(!isExpanded);
        }
      }}
      tabIndex={isExpandable ? 0 : undefined}
      role={isExpandable ? 'button' : undefined}
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 flex-wrap">
          <code className="text-xs font-mono text-muted-foreground">
            {subagent.agent_id}
          </code>
          <SubagentTypeBadge type={subagent.subagent_type} size="sm" />
          <CompletionStatusBadge status={subagent.completion_status} />
        </div>

        <div className="flex items-center gap-2">
          {subagent.duration_seconds !== null && (
            <span className="text-xs text-muted-foreground">
              {formatDuration(subagent.duration_seconds)}
            </span>
          )}
          {isExpandable && (
            isExpanded ? (
              <ChevronUp className="h-4 w-4 text-muted-foreground" />
            ) : (
              <ChevronDown className="h-4 w-4 text-muted-foreground" />
            )
          )}
        </div>
      </div>

      {/* Initial Prompt */}
      {subagent.initial_prompt && (
        <p className={cn(
          "mt-2 text-sm text-foreground/80",
          !isExpanded && hasLongPrompt && "line-clamp-2"
        )}>
          {subagent.initial_prompt}
        </p>
      )}

      {/* Stats */}
      <AgentStats
        durationSeconds={subagent.duration_seconds}
        totalInputTokens={subagent.total_input_tokens}
        totalOutputTokens={subagent.total_output_tokens}
        cacheHitRate={subagent.cache_hit_rate}
        fileReadCount={subagent.file_read_count}
        fileWriteCount={subagent.file_write_count}
        className="mt-3"
      />

      {/* Quick Stats Row */}
      <div className="mt-3 flex items-center gap-4 text-xs text-muted-foreground">
        <span className="flex items-center gap-1">
          <MessageSquare className="h-3.5 w-3.5" />
          {subagent.message_count}
        </span>
        <span className="flex items-center gap-1">
          <Wrench className="h-3.5 w-3.5" />
          {totalToolCalls} calls
        </span>
      </div>

      {/* Tool Pills */}
      <div className="mt-2 flex flex-wrap gap-1">
        {(isExpanded ? toolEntries : topTools).map(([tool, count]) => (
          <span
            key={tool}
            className="inline-flex items-center gap-1 px-2 py-0.5 text-xs bg-secondary rounded-full"
          >
            {tool}
            <span className="text-muted-foreground">×{count}</span>
          </span>
        ))}
        {!isExpanded && hasMoreTools && (
          <span className="text-xs text-muted-foreground">
            +{toolEntries.length - 5} more
          </span>
        )}
      </div>

      {/* Expanded Content */}
      {isExpanded && (
        <>
          {/* Final Output */}
          {subagent.final_output && (
            <div className="mt-4 pt-3 border-t">
              <h4 className="text-xs font-medium text-muted-foreground mb-2">
                Final Output
              </h4>
              <p className="text-sm text-foreground/80 whitespace-pre-wrap bg-muted/50 p-3 rounded-md">
                {subagent.final_output}
              </p>
            </div>
          )}

          {/* Models Used */}
          {subagent.models_used.length > 0 && (
            <div className="mt-3 flex items-center gap-2">
              <span className="text-xs text-muted-foreground">Models:</span>
              {subagent.models_used.map((model) => (
                <span
                  key={model}
                  className="text-xs px-1.5 py-0.5 bg-secondary rounded"
                >
                  {model.replace('claude-', '').replace(/-\d+$/, '')}
                </span>
              ))}
            </div>
          )}

          {/* Slug */}
          {subagent.slug && (
            <div className="mt-2 text-xs text-muted-foreground">
              Slug: <code>{subagent.slug}</code>
            </div>
          )}
        </>
      )}
    </div>
  );
}
```

---

## Phase 6: Update Agents Page

**File**: `apps/web/app/session/[uuid]/agents/page.tsx`

### 6.1 Add Summary Stats at Top

Add an overall summary section above the groups:

```tsx
// After data fetching, before groups
const totalAgents = data?.length ?? 0;
const completedCount = data?.filter(a => a.completion_status === 'completed').length ?? 0;
const errorCount = data?.filter(a => a.completion_status === 'error').length ?? 0;
const totalTokens = data?.reduce(
  (sum, a) => sum + a.total_input_tokens + a.total_output_tokens,
  0
) ?? 0;
const totalDuration = data?.reduce(
  (sum, a) => sum + (a.duration_seconds ?? 0),
  0
) ?? 0;
```

```tsx
{/* Summary Bar */}
{data && data.length > 0 && (
  <div className="mb-6 p-4 bg-muted/50 rounded-lg flex flex-wrap gap-6 text-sm">
    <div>
      <span className="text-muted-foreground">Total Agents: </span>
      <span className="font-medium">{totalAgents}</span>
    </div>
    <div>
      <span className="text-muted-foreground">Completed: </span>
      <span className="font-medium text-emerald-600">{completedCount}</span>
    </div>
    {errorCount > 0 && (
      <div>
        <span className="text-muted-foreground">Errors: </span>
        <span className="font-medium text-red-600">{errorCount}</span>
      </div>
    )}
    <div>
      <span className="text-muted-foreground">Total Tokens: </span>
      <span className="font-medium">{formatTokens(totalTokens)}</span>
    </div>
    <div>
      <span className="text-muted-foreground">Total Time: </span>
      <span className="font-medium">{formatDuration(totalDuration)}</span>
    </div>
  </div>
)}
```

---

## Phase 7: Testing

**File**: `apps/web/__tests__/components/subagent-card.test.tsx` (if tests exist)

### 7.1 Add Tests for New Features

```tsx
import { render, screen } from '@testing-library/react';
import { SubagentCard } from '@/components/subagent-card';

const mockSubagent = {
  agent_id: 'a5793c3',
  slug: 'test-agent',
  subagent_type: 'Explore',
  tools_used: { Read: 5, Grep: 3 },
  message_count: 10,
  initial_prompt: 'Test prompt',
  start_time: '2024-01-15T10:00:00Z',
  end_time: '2024-01-15T10:02:30Z',
  duration_seconds: 150,
  total_input_tokens: 5000,
  total_output_tokens: 1500,
  cache_read_tokens: 3000,
  cache_creation_tokens: 2000,
  cache_hit_rate: 0.6,
  completion_status: 'completed' as const,
  final_output: 'Task completed successfully',
  file_read_count: 8,
  file_write_count: 0,
  models_used: ['claude-sonnet-4-20250514'],
};

describe('SubagentCard', () => {
  it('displays duration', () => {
    render(<SubagentCard subagent={mockSubagent} />);
    expect(screen.getByText('2m 30s')).toBeInTheDocument();
  });

  it('displays completion status', () => {
    render(<SubagentCard subagent={mockSubagent} />);
    expect(screen.getByText('Completed')).toBeInTheDocument();
  });

  it('displays token count', () => {
    render(<SubagentCard subagent={mockSubagent} />);
    expect(screen.getByText('6.5K tokens')).toBeInTheDocument();
  });

  it('displays cache hit rate', () => {
    render(<SubagentCard subagent={mockSubagent} />);
    expect(screen.getByText('60% cache')).toBeInTheDocument();
  });

  it('displays file operations', () => {
    render(<SubagentCard subagent={mockSubagent} />);
    expect(screen.getByText('8 reads')).toBeInTheDocument();
  });
});
```

---

## Visual Design Reference

### Card Layout (Collapsed)

```
┌─────────────────────────────────────────────────────────┐
│ a5793c3  [Explore]  ✓ Completed                  2m 30s │
│                                                         │
│ Explore the codebase to find all API endpoints...       │
│                                                         │
│ ⏱ 2m 30s    ⚡ 6.5K tokens    ⚡ 60% cache   📄 8 reads  │
│                                                         │
│ 💬 10    🔧 8 calls                                     │
│                                                         │
│ [Read ×5] [Grep ×3] +2 more                             │
└─────────────────────────────────────────────────────────┘
```

### Card Layout (Expanded)

```
┌─────────────────────────────────────────────────────────┐
│ a5793c3  [Explore]  ✓ Completed                  2m 30s │
│                                                     ▲   │
│ Explore the codebase to find all API endpoints and  │   │
│ understand the routing structure. Look for FastAPI  │   │
│ decorators and document the patterns used.          │   │
│                                                         │
│ ⏱ 2m 30s    ⚡ 6.5K tokens    ⚡ 60% cache   📄 8 reads  │
│                                                         │
│ 💬 10    🔧 8 calls                                     │
│                                                         │
│ [Read ×5] [Grep ×3] [Glob ×2] [LS ×1]                   │
│                                                         │
│ ─────────────────────────────────────────────────────── │
│ Final Output                                            │
│ ┌─────────────────────────────────────────────────────┐ │
│ │ I've completed the exploration. Found 15 API       │ │
│ │ endpoints across 3 router files...                 │ │
│ └─────────────────────────────────────────────────────┘ │
│                                                         │
│ Models: [sonnet-4]                                      │
│ Slug: eager-puzzling-fairy                              │
└─────────────────────────────────────────────────────────┘
```

---

## Validation Checklist

- [ ] Types updated in `packages/types/src/index.ts`
- [ ] Types package rebuilt: `pnpm --filter @claude-karma/types build`
- [ ] Format utilities added to `apps/web/lib/format.ts`
- [ ] CompletionStatusBadge component created
- [ ] AgentStats component created
- [ ] SubagentCard updated with new fields
- [ ] Agents page updated with summary bar
- [ ] All tests passing: `pnpm --filter @claude-karma/web test`
- [ ] Lint passes: `pnpm --filter @claude-karma/web lint`
- [ ] Type-check passes: `pnpm --filter @claude-karma/web type-check`
- [ ] Visual review in browser

---

## Dependencies

| Component | Depends On |
|-----------|------------|
| Types | Backend API deployed |
| Format utilities | None |
| CompletionStatusBadge | lucide-react |
| AgentStats | Format utilities, lucide-react |
| SubagentCard | All above components |
| Agents page | SubagentCard |

---

## Rollout Order

1. **Backend deploys first** (see `backend.md`)
2. Update types package
3. Add format utilities
4. Create CompletionStatusBadge
5. Create AgentStats
6. Update SubagentCard
7. Update Agents page with summary bar
8. Test end-to-end
9. Deploy frontend
