# Bridge: Walkie-Talkie ↔ Dashboard Integration

> **Status:** ✅ Implementation Complete | All Phases Done
> **Date:** 2026-01-08
> **Branch:** `feature/karma-logger/historical-dashboard`

---

## Overview

This document identifies the gaps between the Walkie-Talkie agent coordination system and the Dashboard, along with a concrete plan to bridge them.

## Documentation Status

All backend components have comprehensive setup documentation.

| Documentation | Location | Status |
|---------------|----------|--------|
| Main README | `karma-logger/README.md` | ✅ Complete |
| Dashboard Setup | `karma-logger/DASHBOARD_SETUP.md` | ✅ Complete |
| Walkie-Talkie API | `src/walkie-talkie/README.md` | ✅ Complete |
| Walkie-Talkie Deployment | `src/walkie-talkie/SETUP.md` | ✅ Complete |
| Frontend Radio UI | `src/dashboard/public/` | ✅ Implemented |

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
| **SocketServer** | `src/walkie-talkie/socket-server.ts` | ✅ Implemented |
| **SocketClient** | `src/walkie-talkie/socket-client.ts` | ✅ Implemented |
| **CLI Commands** | `src/commands/radio.ts` | ✅ Implemented |
| **Frontend Agent Cards** | `src/dashboard/public/app.js:529-546` | ✅ Implemented |
| **Agent Card Styles** | `src/dashboard/public/style.css:2074-2217` | ✅ Implemented |

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

## Gap Analysis (All Resolved)

### Gap 1: SocketServer Not Started in Dashboard ✅ RESOLVED

**Solution Implemented:** `src/dashboard/server.ts:165-173`
- Socket server starts automatically when `--radio` flag is passed
- Creates `/tmp/karma-radio.sock` for CLI communication

### Gap 2: Session Agent List Not Populated ✅ RESOLVED

**Solution Implemented:** `src/aggregator.ts:414-435`
- `registerAgent()` populates `session:{sessionId}:agents` cache
- `unregisterAgent()` removes agents from the list

### Gap 3: Frontend Radio UI Not Implemented ✅ RESOLVED

**Solution Implemented:**
- `app.js:529-546` - SSE handlers for `agent:status` and `agent:progress`
- `app.js:1155-1194` - Agent status tracking and card rendering
- `index.html:177` - Agent cards container
- `style.css:2074-2217` - Agent card styles with state colors

### Gap 4: Radio Flags Not Exposed in Dashboard Command ✅ RESOLVED

**Solution Implemented:** Dashboard supports radio flags:
```bash
karma dashboard --radio          # Enable radio
karma dashboard --persist-radio  # Enable persistent radio
```

---

## Implementation Plan (All Complete)

### Phase 1: Wire Socket Server ✅ COMPLETE

**Verified:** 2026-01-08
- Socket server starts with `karma dashboard --radio`
- Creates `/tmp/karma-radio.sock`
- CLI commands connect successfully

### Phase 2: Session Agent Tracking ✅ COMPLETE

**Verified:** 2026-01-08
- `session:{sessionId}:agents` populated in `aggregator.ts:414-417`
- Agent removal on unregister in `aggregator.ts:432-435`
- `/api/radio/session/:id/tree` returns hierarchy

### Phase 3: Frontend Agent Visualization ✅ COMPLETE

**Verified:** 2026-01-08
- SSE handlers in `app.js:529-546`
- Agent cards UI in `index.html:177`
- CSS styles in `style.css:2074-2217`

### Phase 4: End-to-End Testing ✅ COMPLETE

**Verified:** 2026-01-08
- Hooks configured in `.claude/hooks.yaml`
- CLI commands tested successfully
- Persistent cache verified (35+ agents survived restart)

---

## Testing Checklist (All Passing)

- [x] `karma radio set-status active` succeeds when dashboard running
- [x] `/api/radio/agents` returns agent statuses
- [x] `/api/radio/session/:id/tree` returns hierarchy
- [x] SSE `agent:status` events fire on status change
- [x] SSE `agent:progress` events fire on progress update
- [x] Frontend displays agent status cards
- [x] Frontend updates in real-time
- [x] Persistent cache survives dashboard restart

---

## Hook Integration

Claude Code hooks report agent status via JSON stdin. Copy `.claude/hooks.yaml` to your project:

```yaml
# .claude/hooks.yaml
# Requires: jq (brew install jq)
hooks:
  PreToolUse:
    - command: |
        INPUT=$(cat)
        export KARMA_SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
        export KARMA_AGENT_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
        TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // "unknown"')
        if [ -n "$KARMA_SESSION_ID" ]; then
          karma radio set-status active --message "Using $TOOL_NAME" 2>/dev/null || true
        fi
      timeout: 5000

  PostToolUse:
    - command: |
        INPUT=$(cat)
        export KARMA_SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
        export KARMA_AGENT_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
        TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // "unknown"')
        if [ -n "$KARMA_SESSION_ID" ]; then
          karma radio report-progress --percent 0 --message "Completed $TOOL_NAME" 2>/dev/null || true
        fi
      timeout: 5000

  SessionStart:
    - command: |
        INPUT=$(cat)
        export KARMA_SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
        export KARMA_AGENT_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
        if [ -n "$KARMA_SESSION_ID" ]; then
          karma radio set-status pending --message "Session started" 2>/dev/null || true
        fi
      timeout: 5000

  Stop:
    - command: |
        INPUT=$(cat)
        export KARMA_SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
        export KARMA_AGENT_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
        if [ -n "$KARMA_SESSION_ID" ]; then
          karma radio set-status completed --message "Session completed" 2>/dev/null || true
        fi
      timeout: 5000
```

**Note:** Hooks are loaded at session start. Changes require a new Claude Code session to take effect.

---

## Quick Start

```bash
# 1. Start dashboard with radio enabled
karma dashboard --radio

# 2. Verify socket exists
ls -la /tmp/karma-radio.sock

# 3. Test CLI manually
export KARMA_AGENT_ID="test" KARMA_SESSION_ID="test"
karma radio set-status active --message "Hello"
karma radio get-status

# 4. View in browser
open http://localhost:3333
```

---

## References

### Documentation
- [Main README](README.md) - Full project overview, all commands, architecture
- [Dashboard Setup](DASHBOARD_SETUP.md) - TUI + Web dashboard deployment
- [Walkie-Talkie README](src/walkie-talkie/README.md) - Complete API reference
- [Walkie-Talkie SETUP](src/walkie-talkie/SETUP.md) - Deployment guide with launchd/systemd/pm2
