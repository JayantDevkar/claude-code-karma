# Frontend Review: hook-update-jan-2026

Branch: `hook-update-jan-2026`
Review Date: 2026-01-28
Reviewer: UI/UX Expert (Svelte)

## Overview

This review examines the frontend implementation of the agent-status tracking feature. The API correctly returns subagent data via hooks, but the frontend has significant gaps in displaying this information.

## Issue Summary

| Severity | Count | Category |
|----------|-------|----------|
| HIGH | 3 | Missing UI functionality, data not rendered |
| MEDIUM | 4 | UX gaps, design inconsistencies |
| LOW | 2 | Minor improvements |

---

## HIGH Severity Issues

### 1. LiveSessionsTerminal Ignores Subagent Data

**Location:** `frontend/src/lib/components/LiveSessionsTerminal.svelte`

**Problem:** The live sessions terminal displays session info (ID, status, project, duration) but completely ignores subagent tracking data that the API provides.

**API Response (verified):**
```json
{
  "session_id": "b267a9e8-...",
  "status": "active",
  "subagents": {
    "a7563de": {
      "agent_id": "a7563de",
      "agent_type": "feature-dev:code-explorer",
      "status": "running",
      "started_at": "2026-01-28T16:32:39Z"
    }
  },
  "active_subagent_count": 2,
  "total_subagent_count": 2
}
```

**Frontend Types (defined but unused):**
```typescript
// api-types.ts:466-468
subagents: Record<string, SubagentState>;
active_subagent_count: number;
total_subagent_count: number;
```

**Current UI:** Shows only `[2 active, 1 stale]` for sessions, no subagent info.

**Expected UI:** Should show per-session subagent count, e.g., `b267a9e8 ACTIVE (2 agents running)`

**Impact:** Users cannot see real-time subagent activity in the live sessions overview - the primary use case for the hook-based tracking feature.

**Screenshot Evidence:** ![Home page showing no subagent info](home-live-sessions.png)

---

### 2. SubagentCard Uses Wrong Type - No Status/Timestamps

**Location:** `frontend/src/lib/components/subagents/SubagentCard.svelte`

**Problem:** Component uses `SubagentSummary` (from JSONL parsing) instead of `SubagentState` (from hooks). These are fundamentally different:

| Field | SubagentSummary (JSONL) | SubagentState (Hooks) |
|-------|-------------------------|----------------------|
| status | Not present | `running` / `completed` / `error` |
| started_at | Not present | ISO timestamp |
| completed_at | Not present | ISO timestamp |
| transcript_path | Not present | Path to JSONL |
| tools_used | Present (aggregated) | Not present |
| message_count | Present | Not present |
| initial_prompt | Present | Not present |

**Current Implementation (line 16-17):**
```typescript
import type { SubagentSummary } from '$lib/api-types';
// ...
let { subagent, ... }: Props = $props();
```

**Missing Visual Elements:**
- No status indicator (running/completed/error)
- No start/end timestamps
- No duration display for running agents
- No visual distinction between active and completed agents

**Impact:** The Subagents tab shows agents but users cannot tell which are still running vs completed.

---

### 3. Two Disconnected Data Sources for Subagents

**Problem:** The frontend has two separate flows for subagent data that don't integrate:

1. **Live Sessions API** (`/live-sessions/active`) → Returns `SubagentState` with real-time status
2. **Session Subagents API** (`/sessions/{uuid}/subagents`) → Returns `SubagentSummary` from JSONL parsing

**Current Architecture:**
```
Live Sessions Terminal → fetches /live-sessions/active → ignores subagents field
Session Detail Page → fetches /sessions/{uuid}/subagents → uses SubagentSummary
```

**Expected Architecture:**
```
Live Sessions Terminal → fetches /live-sessions/active → displays subagent counts + status
Session Detail Page → fetches both endpoints → merges data for complete view
```

**Impact:** No unified view of subagent status - live data and historical data are siloed.

---

## MEDIUM Severity Issues

### 4. SubagentTypeBadge Missing Status Colors

**Location:** `frontend/src/lib/components/subagents/SubagentTypeBadge.svelte`

**Problem:** Badge shows only type (Explore, Plan, Bash) with type-specific colors, but doesn't indicate running/completed status.

**Current:** Shows `feature-dev:code-explorer` in purple
**Expected:** Should show status overlay or indicator, e.g., pulsing dot for running, checkmark for completed

**Recommendation:** Add optional `status` prop:
```typescript
interface Props {
  type: string | null | undefined;
  status?: 'running' | 'completed' | 'error';  // NEW
  size?: 'sm' | 'md';
}
```

---

### 5. SubagentGroup Doesn't Show Group Status

**Location:** `frontend/src/lib/components/subagents/SubagentGroup.svelte`

**Problem:** Group header shows type and count (`feature-dev:code-explorer · 1 agent`) but doesn't indicate if any agents in the group are still running.

**Current:** `feature-dev:code-explorer · 1 agent`
**Expected:** `feature-dev:code-explorer · 1 agent · 1 running` or visual pulse indicator

---

### 6. No Duration Display for Running Subagents

**Problem:** Even though `started_at` timestamp is available from hooks, no component displays the running duration (time since start).

**Opportunity:** Add live-updating duration similar to how `LiveSessionsTerminal` shows session duration:
```svelte
<!-- Example: Show "Running for 2m 30s" -->
<span class="duration">{formatDuration(now - started_at)}</span>
```

---

### 7. Polling vs Real-Time for Subagent Status

**Location:** `frontend/src/lib/components/LiveSessionsTerminal.svelte:89-91`

**Problem:** Component polls every 1 second for live sessions, which is reasonable, but subagent status in session detail doesn't poll at all.

```typescript
// LiveSessionsTerminal.svelte
pollInterval = setInterval(fetchSessions, 1000);
```

**Impact:** If viewing a session detail page, subagent status won't update until page refresh.

**Recommendation:** Either add polling to session detail or implement SSE for real-time updates.

---

## LOW Severity Issues

### 8. Missing Transcript Link in SubagentCard

**Problem:** `SubagentState.transcript_path` is available from API but not displayed anywhere.

**Opportunity:** When subagent completes, show link to view full transcript:
```svelte
{#if subagent.transcript_path}
  <a href={`/transcripts/${encodeURIComponent(subagent.transcript_path)}`}>
    View Transcript
  </a>
{/if}
```

---

### 9. Inconsistent Loading States

**Problem:** `LiveSessionsTerminal` has loading animation ("Loading...") but doesn't show loading state when refreshing data during polling.

**Current:** Initial load shows spinner, subsequent polls show stale data until response
**Expected:** Subtle indicator when data is refreshing

---

## Verification Screenshots

| Screenshot | Description |
|------------|-------------|
| `home-live-sessions.png` | Home page - live sessions show NO subagent counts |
| `session-subagents-tab.png` | Session detail - subagents shown but no status indicators |

---

## API Data Verification

Verified via `curl http://localhost:8000/live-sessions/active`:

```json
{
  "session_id": "b267a9e8-63a9-4b50-87c4-351f5286f791",
  "status": "active",
  "subagents": {
    "acdeee0": {
      "agent_id": "acdeee0",
      "agent_type": "feature-dev:code-reviewer",
      "status": "running",
      "started_at": "2026-01-28T16:32:39Z",
      "completed_at": null
    },
    "a7563de": {
      "agent_id": "a7563de",
      "agent_type": "feature-dev:code-explorer",
      "status": "running",
      "started_at": "2026-01-28T16:32:39Z",
      "completed_at": null
    }
  },
  "active_subagent_count": 2,
  "total_subagent_count": 2
}
```

**Conclusion:** API returns rich subagent data. Frontend types expect it. UI doesn't render it.

---

## Recommended Actions

### Priority 1 (Must Fix)
1. **Update LiveSessionsTerminal** to display `active_subagent_count` per session
2. **Add status prop to SubagentCard** to show running/completed indicator
3. **Create bridge** between `SubagentState` (hooks) and `SubagentSummary` (JSONL) data

### Priority 2 (Should Fix)
4. **Add status indicator to SubagentTypeBadge**
5. **Show running duration** for active subagents
6. **Add polling** to session detail subagents tab

### Priority 3 (Nice to Have)
7. **Add transcript link** when available
8. **Improve loading states** during polling

---

## Files to Modify

| File | Changes Needed |
|------|----------------|
| `LiveSessionsTerminal.svelte` | Render `active_subagent_count`, add subagent indicator |
| `SubagentCard.svelte` | Accept `SubagentState` or add status prop, show timestamps |
| `SubagentTypeBadge.svelte` | Add optional status indicator |
| `SubagentGroup.svelte` | Show group-level status summary |
| `api-types.ts` | Add merged type or adapter for both data sources |
| Session detail page | Add polling or SSE for real-time subagent updates |

---

## Implementation Suggestions

### Quick Win: LiveSessionsTerminal Subagent Display (~10 lines)

**Location:** `LiveSessionsTerminal.svelte:167-169` (after duration display)

```svelte
<!-- Add after <span class="duration">{formatDuration(session.duration_seconds)}</span> -->
{#if session.active_subagent_count > 0}
  <div class="flex items-center gap-1.5 text-[10px] text-[var(--nav-purple)]">
    <Users size={10} strokeWidth={2} class="animate-pulse" />
    <span>{session.active_subagent_count} running</span>
  </div>
{/if}
```

Import required: `import { Users } from 'lucide-svelte';`

---

### New Component: LiveSubagentBadge.svelte

```svelte
<script lang="ts">
  import { Bot } from 'lucide-svelte';
  import type { SubagentState } from '$lib/api-types';
  import { getSubagentColorVars } from '$lib/utils';

  interface Props {
    subagent: SubagentState;
    compact?: boolean;
  }

  let { subagent, compact = false }: Props = $props();
  let colorVars = $derived(getSubagentColorVars(subagent.agent_type));

  // Calculate running duration
  let duration = $derived(() => {
    const start = new Date(subagent.started_at).getTime();
    const end = subagent.completed_at
      ? new Date(subagent.completed_at).getTime()
      : Date.now();
    return Math.floor((end - start) / 1000);
  });
</script>

<div class="flex items-center gap-2" style="color: {colorVars.color}">
  <div class="relative">
    <Bot size={14} />
    {#if subagent.status === 'running'}
      <span class="absolute -top-1 -right-1 w-2 h-2 bg-green-500 rounded-full animate-pulse" />
    {/if}
  </div>
  {#if !compact}
    <span class="text-xs">{subagent.agent_type}</span>
    <span class="text-xs text-[var(--text-muted)]">{formatDuration(duration())}</span>
  {/if}
</div>
```

---

### ConversationView Live Subagent Integration

**Location:** `ConversationView.svelte:229-251` (pollLiveStatus function)

**Current:** Only updates `message_count` and `subagent_count` from live session
**Missing:** Doesn't store or display `subagents` dict

```typescript
// Add state for live subagents (line ~181)
let liveSubagents = $state<Record<string, SubagentState>>({});

// Update in pollLiveStatus (line ~240)
if (res.ok) {
  const newStatus: LiveSessionSummary = await res.json();
  liveStatus = newStatus;
  liveSubagents = newStatus.subagents || {};  // ADD THIS
}
```

**Update Subagents Tab (line ~910):**
```svelte
<Tabs.Content value="agents">
  {#if isCurrentlyLive && Object.keys(liveSubagents).length > 0}
    <!-- Show live status indicators for running subagents -->
    <div class="mb-4 p-3 bg-[var(--status-active-bg)] rounded-lg">
      <span class="text-sm font-medium">Live: {Object.values(liveSubagents).filter(s => s.status === 'running').length} running</span>
    </div>
  {/if}
  <!-- Existing SubagentGroup display -->
</Tabs.Content>
```

---

### Type Conversion Utility

**Location:** `frontend/src/lib/utils.ts`

```typescript
import type { SubagentState, SubagentSummary } from './api-types';

/**
 * Merge SubagentState (live hooks) with SubagentSummary (JSONL) data
 * Returns enriched object with both real-time status and historical details
 */
export function mergeSubagentData(
  liveState: SubagentState | undefined,
  summary: SubagentSummary
): SubagentSummary & Partial<SubagentState> {
  return {
    ...summary,
    status: liveState?.status,
    started_at: liveState?.started_at,
    completed_at: liveState?.completed_at,
    transcript_path: liveState?.transcript_path,
  };
}
```

---

## Data Flow Diagrams

### Current Flow (Broken)

```
                   ┌──────────────────────────────────┐
                   │     SubagentStart/Stop Hooks     │
                   └───────────────┬──────────────────┘
                                   │
                                   ▼
                   ┌──────────────────────────────────┐
                   │   live_session_tracker.py        │
                   │   (writes to JSON file)          │
                   └───────────────┬──────────────────┘
                                   │
                                   ▼
                   ┌──────────────────────────────────┐
                   │   ~/.claude_karma/live-sessions/ │
                   │   {slug}.json (with subagents)   │
                   └───────────────┬──────────────────┘
                                   │
                                   ▼
                   ┌──────────────────────────────────┐
                   │   GET /live-sessions/active      │
                   │   Returns: subagents dict ✅      │
                   └───────────────┬──────────────────┘
                                   │
                                   ▼
                   ┌──────────────────────────────────┐
                   │   LiveSessionsTerminal.svelte    │
                   │   Receives: subagents ✅          │
                   │   Renders: NOTHING ❌             │
                   └──────────────────────────────────┘
```

### Expected Flow (Fixed)

```
GET /live-sessions/active ──► LiveSessionsTerminal
                                    │
                                    ▼
                            ┌───────────────┐
                            │ Per-session:  │
                            │ • Status dot  │
                            │ • Agent count │◄── NEW
                            │ • Subagent    │
                            │   indicators  │
                            └───────────────┘

GET /sessions/{uuid} ──► ConversationView
       │                        │
       │                        ▼
       │                ┌───────────────┐
       │                │ Subagents Tab │
       │                │ • SubagentCard│
       │                │ • Live status │◄── NEW (merge w/ hooks)
       │                └───────────────┘
       │
       ▼
GET /live-sessions/{session_id} ──► liveSubagents state
                                         │
                                         ▼
                                 ┌───────────────┐
                                 │ Status overlay│
                                 │ on SubagentCard│
                                 └───────────────┘
```

---

## Related API Issues

See `docs/issues/pr/hook-update-jan-2026/issues.md` for API-side issues that may affect frontend:
- Schema updates needed for `LiveSessionSummary`
- Race condition in parallel subagent tracking (may cause missing subagents in UI)

---

## Summary

| What Works | What's Missing |
|------------|----------------|
| ✅ API returns subagent data | ❌ LiveSessionsTerminal doesn't render it |
| ✅ Frontend types defined | ❌ SubagentCard doesn't show status |
| ✅ SubagentCard components built | ❌ No live status polling in session detail |
| ✅ Color/icon utilities exist | ❌ No data bridge between SubagentState and SubagentSummary |

**Bottom Line:** The plumbing is 90% complete. The API returns data, the types are defined, the display components exist. The missing piece is ~50 lines of code to wire them together.
