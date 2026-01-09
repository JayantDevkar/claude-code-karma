# Live Page Issues Analysis

**Date**: 2026-01-09
**Status**: Identified
**Priority**: High

---

## Overview

The Live page in the karma-logger dashboard has several UX and data filtering issues that prevent users from effectively monitoring sessions in real-time.

---

## Architecture Summary

### Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                         DATA SOURCES                                 │
├─────────────────────────────────────────────────────────────────────┤
│  SSE /events           Real-time session/metrics/agent updates       │
│  REST /api/totals      Aggregate metrics (all sessions)              │
│  REST /api/sessions    Session list with isRunning flag              │
│  REST /api/session/:id Single session details + agent tree           │
│  REST /api/projects    Project list (from SQLite DB)                 │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      FRONTEND STATE (app.js)                         │
├─────────────────────────────────────────────────────────────────────┤
│  liveProject         Selected project filter ('' = all)              │
│  projectSessions     Sessions filtered by liveProject                │
│  liveSessionId       Currently displayed session ID                  │
│  agentTree           Agent hierarchy for liveSessionId               │
│  metrics             Aggregate metrics object                        │
│  activeSessions      Sessions with isRunning = true                  │
│  completedSessions   Sessions with isRunning = false                 │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         UI COMPONENTS                                │
├─────────────────────────────────────────────────────────────────────┤
│  Header              Project dropdown + session badge                │
│  Session Sidebar     Active/completed session list (CONDITIONAL)     │
│  Metrics Cards       Token counts, cost, agent count                 │
│  Token Chart         Real-time usage chart (uPlot)                   │
│  Agent Tree          Hierarchical agent display                      │
│  Session Stats       Aggregate stats footer                          │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Files

| File | Purpose |
|------|---------|
| `src/dashboard/public/app.js` | Petite-Vue frontend application |
| `src/dashboard/public/index.html` | HTML template with v-if/v-show directives |
| `src/dashboard/sse.ts` | SSEManager for real-time event broadcasting |
| `src/dashboard/api.ts` | REST API route handlers |
| `src/dashboard/server.ts` | Hono server setup and static file serving |

---

## Issues Identified

### Issue #1: Session Sidebar Hidden When "All Projects" Selected

**Severity**: High
**Location**: `src/dashboard/public/index.html:59`

**Problem**:
```html
<aside class="live-sidebar" v-if="liveProject">
```

The session sidebar only renders when a specific project is selected. When "All Projects" is chosen (`liveProject = ''`), the sidebar is completely hidden, preventing users from:
- Viewing available sessions
- Switching between sessions
- Filtering active vs completed sessions

**Evidence**:
- Screenshot with "All Projects": No sidebar visible
- Screenshot with "karma" selected: Sidebar shows 10+ sessions

**Recommended Fix**:
```html
<!-- Option A: Always show sidebar -->
<aside class="live-sidebar">

<!-- Option B: Show with different content when no project -->
<aside class="live-sidebar" v-if="liveProject || sessions.length > 0">
```

---

### Issue #2: Session Stats Count Mismatch

**Severity**: Medium
**Location**: `src/dashboard/public/index.html:262-264`

**Problem**:
```html
<span class="session-summary__count">{{ sessions.length }} sessions</span>
```

The `sessions` array is populated from SSE init and may not match the filtered `projectSessions` or `filteredSessions`. When a project is selected, the count shows incorrect total.

**Evidence**:
- Sidebar shows 10 active sessions
- Session Stats shows "4 sessions"

**Recommended Fix**:
```html
<span class="session-summary__count">{{ projectSessions.length }} sessions</span>
```

Or use computed property that respects current filter:
```html
<span class="session-summary__count">{{ filteredSessions.length }} sessions</span>
```

---

### Issue #3: Metrics Show Aggregate Totals Instead of Session-Specific

**Severity**: Medium
**Location**: `src/dashboard/public/app.js:596-605`

**Problem**:
```javascript
updateMetrics(data) {
  if (data.tokensIn != null) this.metrics.tokensIn = data.tokensIn;
  // ... always updates aggregate metrics
}
```

The metric cards always show aggregate totals from `/api/totals`, regardless of:
- Selected project
- Selected session
- Active filter state

**Expected Behavior**:
- When "All Projects" selected: Show aggregate totals
- When specific project selected: Show project totals
- When specific session selected: Show session metrics

**Recommended Fix**:
```javascript
async selectLiveSession(sessionId) {
  this.liveSessionId = sessionId;
  const data = await this.fetchSessionData(sessionId);
  // Update metrics to show session-specific values
  if (data.metrics) {
    this.metrics = { ...this.metrics, ...data.metrics };
  }
}
```

---

### Issue #4: isRunning Threshold May Be Inaccurate

**Severity**: Low
**Location**: `src/dashboard/sse.ts:188-190`, `src/dashboard/api.ts:80-82`

**Problem**:
```typescript
const RUNNING_THRESHOLD_MS = 30000; // 30 seconds
const isRunning = s.status === 'active' &&
  (now - s.lastActivity.getTime()) < RUNNING_THRESHOLD_MS;
```

Sessions are marked as "running" if they had activity within 30 seconds. This threshold:
- May mark idle sessions as running
- May mark slow operations as completed prematurely
- Is hardcoded without configuration option

**Recommended Fix**:
- Make threshold configurable
- Consider using explicit session end signals instead of timeout
- Add visual indicator for "possibly idle" state

---

## SSE Event Flow

### Events Broadcast by SSEManager

| Event | Trigger | Payload |
|-------|---------|---------|
| `init` | Client connects | `{ metrics, sessions[] }` |
| `metrics` | Log entry processed | `{ tokensIn, tokensOut, cost, ... }` |
| `agents` | Agent spawned | `AgentTree[]` |
| `session:start` | New session detected | `{ sessionId, projectName, startedAt }` |
| `session:end` | Session ended | `{ sessionId, endedAt, finalCost }` |
| `agent:spawn` | Agent spawned | `{ agentId, sessionId, parentId, type }` |
| `agent:status` | Radio status update | `{ agentId, status }` |
| `agent:progress` | Radio progress update | `{ agentId, progress }` |

### Frontend Event Handlers (app.js:351-548)

```javascript
// SSE event attachment
attachSSEHandlers(es, markData) {
  es.addEventListener('init', ...);      // Lines 353-403
  es.addEventListener('metrics', ...);   // Lines 406-426
  es.addEventListener('agents', ...);    // Lines 429-438
  es.addEventListener('session:start', ...); // Lines 441-479
  es.addEventListener('session:end', ...);   // Lines 482-490
  es.addEventListener('agent:spawn', ...);   // Lines 493-526
  es.addEventListener('agent:status', ...);  // Lines 529-537
  es.addEventListener('agent:progress', ...); // Lines 540-548
}
```

---

## Filtering Logic

### Current Implementation

```javascript
// Project filter
onLiveProjectChange() {
  localStorage.setItem('karma-live-project', this.liveProject);
  this.refreshLiveView();
}

// Session categorization
categorizeSessions(sessions) {
  this.activeSessions = sessions.filter(s => s.isRunning);
  this.completedSessions = sessions.filter(s => !s.isRunning);
}

// Computed filtered sessions
get filteredSessions() {
  if (this.sessionFilter === 'active') return this.activeSessions;
  if (this.sessionFilter === 'completed') return this.completedSessions;
  return [...this.activeSessions, ...this.completedSessions];
}
```

### Data Inconsistencies

| Array | Source | When Updated |
|-------|--------|--------------|
| `sessions` | SSE init, fetchProjectSessions | On connect, project change |
| `projectSessions` | Filtered from sessions | On project change |
| `activeSessions` | categorizeSessions() | On SSE init |
| `completedSessions` | categorizeSessions() | On SSE init |
| `filteredSessions` | Computed getter | Real-time |

**Problem**: Multiple arrays can become out of sync when:
- New session starts (only added to `activeSessions`)
- Session ends (moved to `completedSessions`)
- Project filter changes (doesn't re-categorize)

---

## Recommended Fixes Summary

| Priority | Issue | Fix |
|----------|-------|-----|
| **P0** | Sidebar hidden | Remove `v-if="liveProject"` or show alternative UI |
| **P1** | Session count mismatch | Use `projectSessions.length` |
| **P1** | Metrics not filtered | Update metrics on session selection |
| **P2** | isRunning threshold | Make configurable, add idle indicator |
| **P2** | Array sync issues | Refactor to single source of truth |

---

## Test Commands

```bash
# Start dashboard
npx tsx src/index.ts dashboard --no-open

# Test API endpoints
curl http://localhost:3333/api/health
curl http://localhost:3333/api/sessions
curl http://localhost:3333/api/totals
curl http://localhost:3333/api/projects

# Test SSE stream
curl -N http://localhost:3333/events
```

---

## Related Files

- `src/dashboard/public/style.css` - Sidebar styling (`.live-sidebar`)
- `src/dashboard/public/charts.js` - uPlot chart configuration
- `src/aggregator.ts` - MetricsAggregator that feeds SSE
- `src/watcher.ts` - LogWatcher that emits events
