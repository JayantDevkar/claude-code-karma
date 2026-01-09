# Bridge: Walkie-Talkie ↔ Dashboard Integration

> **Status:** Gap Analysis Complete | Documentation Audit Complete
> **Date:** 2026-01-08
> **Branch:** `feature/karma-logger/historical-dashboard`

---

## Overview

This document identifies the gaps between the Walkie-Talkie agent coordination system and the Dashboard, along with a concrete plan to bridge them.

## Documentation Status

All backend components have comprehensive setup documentation. The gaps identified below are **code implementation gaps**, not documentation gaps.

| Documentation | Location | Status |
|---------------|----------|--------|
| Main README | `karma-logger/README.md` | ✅ Complete |
| Dashboard Setup | `karma-logger/DASHBOARD_SETUP.md` | ✅ Complete |
| Walkie-Talkie API | `src/walkie-talkie/README.md` | ✅ Complete |
| Walkie-Talkie Deployment | `src/walkie-talkie/SETUP.md` | ✅ Complete |
| Frontend Radio UI | — | ⚠️ Needs creation (after code implementation) |

## Architecture Vision

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Dashboard (Web UI)                                 │
│                        localhost:3333                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────────────┐   │
│  │  REST APIs   │  │  SSE Stream  │  │    Static Frontend               │   │
│  │ /api/radio/* │  │   /events    │  │   (agent tree, status cards)     │   │
│  └──────┬───────┘  └──────┬───────┘  └──────────────────────────────────┘   │
│         │                 │                                                  │
│         │    Reads from   │    Subscribes to                                │
│         ▼                 ▼                                                  │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     MetricsAggregator                                │    │
│  │  • CacheStore (in-memory or persistent)                              │    │
│  │  • AgentRadio instances per agent                                    │    │
│  │  • Status change callbacks                                           │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ▲
                                    │ Unix Socket IPC
                                    │ /tmp/karma-radio.sock
                                    │
┌───────────────────────────────────┴─────────────────────────────────────────┐
│                          SocketServer                                        │
│               (Handles karma radio CLI commands)                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ▲
                                    │
          ┌─────────────────────────┼─────────────────────────┐
          │                         │                         │
          ▼                         ▼                         ▼
┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│  karma radio     │    │  karma radio     │    │  karma radio     │
│  set-status      │    │  report-progress │    │  wait-for        │
│  (from hooks)    │    │  (from hooks)    │    │  (from agents)   │
└──────────────────┘    └──────────────────┘    └──────────────────┘
```

---

## Current Implementation Status

### What's Built and Working

| Component | Location | Status |
|-----------|----------|--------|
| **Radio API Routes** | `src/dashboard/api.ts:267-315` | ✅ Implemented |
| **SSE Radio Events** | `src/dashboard/sse.ts:108-142` | ✅ Implemented |
| **Aggregator Radio Methods** | `src/aggregator.ts:706-829` | ✅ Implemented |
| **CacheStore (Memory)** | `src/walkie-talkie/cache-store.ts` | ✅ Implemented |
| **CacheStore (Persistent)** | `src/walkie-talkie/persistent-cache.ts` | ✅ Implemented |
| **SocketServer** | `src/walkie-talkie/socket-server.ts` | ✅ Code exists |
| **SocketClient** | `src/walkie-talkie/socket-client.ts` | ✅ Code exists |
| **CLI Commands** | `src/commands/radio.ts` | ✅ Code exists |

### API Endpoints (Implemented)

```
GET /api/radio/agents           → All agent statuses (from cache)
GET /api/radio/agent/:id        → Single agent status
GET /api/radio/session/:id/tree → Agent hierarchy tree
```

### SSE Events (Implemented)

```
agent:status   → { agentId, status: AgentStatus }
agent:progress → { agentId, progress: ProgressUpdate }
```

---

## Gap Analysis

### Gap 1: SocketServer Not Started in Dashboard

**Problem:** The `SocketServer` class exists but is never instantiated when the dashboard starts.

**Impact:** `karma radio` CLI commands have no server to connect to.

**Location:** `src/dashboard/server.ts`

**Solution:**
```typescript
// In startServer() function
import { SocketServer } from '../walkie-talkie/socket-server.js';

// After aggregator initialization
if (aggregator.isRadioEnabled()) {
  const socketServer = new SocketServer(aggregator);
  await socketServer.start();

  // Store for cleanup
  server.socketServer = socketServer;
}
```

---

### Gap 2: Session Agent List Not Populated

**Problem:** The cache key `session:{sessionId}:agents` is never set, so `/api/radio/session/:id/tree` returns empty trees.

**Impact:** Agent hierarchy visualization doesn't work.

**Location:** `src/aggregator.ts:379-413` (registerAgent method)

**Solution:**
```typescript
// In registerAgent() method, after creating AgentRadio
if (this.cache) {
  const sessionKey = `session:${sessionId}:agents`;
  const agents = this.cache.get<string[]>(sessionKey) || [];
  if (!agents.includes(agentId)) {
    agents.push(agentId);
    this.cache.set(sessionKey, agents, 3600000); // 1 hour TTL
  }
}
```

---

### Gap 3: Frontend Radio UI Not Implemented

**Problem:** The frontend (`public/app.js`) does NOT consume `agent:status` and `agent:progress` SSE events.

**Analysis (2026-01-08):** Reviewed `app.js` - the SSE handler (`attachSSEHandlers`) only listens for:
- `init` - Initial state
- `metrics` - Token/cost updates
- `agents` - Agent list refresh
- `session:start` / `session:end` - Session lifecycle
- `agent:spawn` - New agent spawned

The backend emits `agent:status` and `agent:progress` (see `sse.ts:108-142`), but no frontend handler exists.

**Impact:** Even with backend working, users won't see real-time agent status/progress in the dashboard.

**Files requiring changes:**
- `src/dashboard/public/app.js` - Add SSE handlers for `agent:status`, `agent:progress`
- `src/dashboard/public/index.html` - Add agent status panel HTML
- `src/dashboard/public/style.css` - Add status card styles

**Required frontend features:**
1. Agent status cards showing state (pending/active/completed/failed)
2. Progress bars for in-flight operations
3. Agent hierarchy tree visualization (partially exists via `agentTree`)
4. Real-time updates via SSE for `agent:status` and `agent:progress`

**Code snippet needed in `app.js`:**
```javascript
// Add in attachSSEHandlers()
es.addEventListener('agent:status', (event) => {
  markData();
  try {
    const data = JSON.parse(event.data);
    // Update agent status in tree or dedicated panel
    this.handleAgentStatus(data.agentId, data.status);
  } catch (err) {
    console.error('Failed to parse agent:status event:', err);
  }
});

es.addEventListener('agent:progress', (event) => {
  markData();
  try {
    const data = JSON.parse(event.data);
    // Update progress indicator for agent
    this.handleAgentProgress(data.agentId, data.progress);
  } catch (err) {
    console.error('Failed to parse agent:progress event:', err);
  }
});
```

---

### Gap 4: Radio Flags Not Exposed in Dashboard Command

**Problem:** `karma dashboard` may not pass `enableRadio` option to aggregator.

**Location:** `src/commands/dashboard.ts` or `src/dashboard/index.ts`

**Solution:** Ensure radio is enabled by default or via flag:
```bash
karma dashboard --radio          # Enable radio
karma dashboard --persist-radio  # Enable persistent radio
```

---

## Implementation Plan

> **Note:** All phases are CODE implementation tasks. Setup documentation already exists for all backend components.

### Phase 1: Wire Socket Server (Priority: High)

**Type:** Code Implementation
**Docs Needed:** None (covered in `walkie-talkie/SETUP.md`)

**Objective:** Enable `karma radio` CLI to communicate with running dashboard.

**Tasks:**
1. Import and instantiate `SocketServer` in `server.ts`
2. Start socket server when radio is enabled
3. Clean up socket on server shutdown
4. Test with `karma radio set-status active`

**Estimated Complexity:** Low (plumbing work)

---

### Phase 2: Session Agent Tracking (Priority: High)

**Type:** Code Implementation
**Docs Needed:** None (API already documented in `walkie-talkie/README.md`)

**Objective:** Populate `session:{sessionId}:agents` for hierarchy tree.

**Tasks:**
1. Update `registerAgent()` in aggregator
2. Update `unregisterAgent()` to remove from list
3. Test `/api/radio/session/:id/tree` endpoint

**Estimated Complexity:** Low

---

### Phase 3: Frontend Agent Visualization (Priority: Medium)

**Type:** Code Implementation
**Docs Needed:** Yes - create `FRONTEND_RADIO_GUIDE.md` after implementation

**Objective:** Display agent status and progress in dashboard UI.

**Tasks:**
1. ~~Audit existing frontend code for SSE handling~~ ✅ Done (see Gap 3 analysis)
2. Add `agent:status` and `agent:progress` SSE handlers to `app.js`
3. Add agent status panel/cards to `index.html`
4. Add progress indicators component
5. Style for different agent states in `style.css`
6. Document UI components after implementation

**Estimated Complexity:** Medium

---

### Phase 4: End-to-End Testing (Priority: Medium)

**Type:** Testing + Documentation
**Docs Needed:** Update `walkie-talkie/SETUP.md` with E2E testing instructions

**Objective:** Verify full flow from hooks to dashboard.

**Tasks:**
1. Configure test hooks in `.claude/hooks.yaml`
2. Run Claude Code session with hooks
3. Verify dashboard shows live agent updates
4. Test persistence across restarts
5. Document E2E testing procedure

**Estimated Complexity:** Medium

---

## File Changes Required

| File | Change Type | Description | Docs |
|------|-------------|-------------|------|
| `src/dashboard/server.ts` | Modify | Start SocketServer | Covered |
| `src/aggregator.ts` | Modify | Update session:*:agents cache | Covered |
| `src/dashboard/public/app.js` | Modify | Add `agent:status`/`agent:progress` handlers | **Needs docs** |
| `src/dashboard/public/index.html` | Modify | Agent status panel HTML | **Needs docs** |
| `src/dashboard/public/style.css` | Modify | Agent status styles | **Needs docs** |
| `src/commands/dashboard.ts` | Modify | Add --radio flag | Covered |

---

## Testing Checklist

- [ ] `karma radio set-status active` succeeds when dashboard running
- [ ] `/api/radio/agents` returns agent statuses
- [ ] `/api/radio/session/:id/tree` returns hierarchy
- [ ] SSE `agent:status` events fire on status change
- [ ] SSE `agent:progress` events fire on progress update
- [ ] Frontend displays agent status cards
- [ ] Frontend updates in real-time
- [ ] Persistent cache survives dashboard restart

---

## Hook Integration Example

Once bridged, Claude Code hooks can report status:

```yaml
# .claude/hooks.yaml
hooks:
  PreToolUse:
    - command: |
        karma radio set-status active --tool "$TOOL_NAME"
      env:
        KARMA_AGENT_ID: "{{sessionId}}"
        KARMA_SESSION_ID: "{{rootSessionId}}"

  PostToolUse:
    - command: |
        karma radio report-progress --tool "$TOOL_NAME" --message "Completed"

  Stop:
    - command: |
        karma radio set-status completed
```

---

## References

### Existing Documentation (All Complete)
- [Main README](README.md) - Full project overview, all commands, architecture
- [Dashboard Setup](DASHBOARD_SETUP.md) - TUI + Web dashboard deployment
- [Walkie-Talkie README](src/walkie-talkie/README.md) - Complete API reference
- [Walkie-Talkie SETUP](src/walkie-talkie/SETUP.md) - Deployment guide with launchd/systemd/pm2
- [Dashboard MVP Plan](DASHBOARD_MVP_PLAN.md) - Original dashboard design

### Documentation To Create (After Code Implementation)
- `FRONTEND_RADIO_GUIDE.md` - Frontend UI components for agent status/progress (Phase 3)
- E2E Testing section in `walkie-talkie/SETUP.md` (Phase 4)
