# Subagent Tracking via Walkie-Talkie

## Overview

This document describes the inference-based subagent tracking system that monitors Claude Code subagents through JSONL file analysis.

## The Problem

### Hook-Based Tracking Limitation

Claude Code hooks only receive `session_id` in their input - they do **not** receive individual subagent IDs:

```json
// What hooks receive:
{
  "session_id": "502283f5-181f-44ba-8c0d-73bec9cddcc0",
  "tool_name": "Read",
  "cwd": "/path/to/project"
}

// What hooks DON'T receive:
{
  "agent_id": "a9d027e",      // <-- MISSING
  "parent_id": "502283f5...", // <-- MISSING
  ...
}
```

This means:
- All subagents share the same `session_id` in hooks
- Radio CLI `list-agents` only shows the session-level agent
- Cannot distinguish between parallel subagents via hooks alone

## The Solution: JSONL File Inference

Claude Code writes detailed JSONL files for each subagent at:

```
~/.claude/projects/<project-path>/<session-id>/subagents/agent-<agent-id>.jsonl
```

Each JSONL entry contains rich metadata:

```json
{
  "agentId": "a9d027e",
  "sessionId": "502283f5-181f-44ba-8c0d-73bec9cddcc0",
  "timestamp": "2026-01-09T02:43:55.048Z",
  "type": "assistant",
  "slug": "eager-puzzling-fairy",
  "message": {
    "model": "claude-haiku-4-5-20251001",
    "content": [...],
    "stop_reason": "end_turn"
  }
}
```

### What We Can Infer

| Field | Source | Notes |
|-------|--------|-------|
| `agentId` | Direct | Unique subagent identifier |
| `sessionId` | Direct | Parent session |
| `model` | `message.model` | e.g., "claude-haiku-4-5-20251001" |
| `task` | First user message | The task prompt |
| `state` | Inferred | Based on `stop_reason` |
| `toolCount` | Counted | Number of `tool_use` blocks |
| `lastTool` | Last `tool_use.name` | Most recent tool used |
| `startedAt` | First entry timestamp | Agent start time |
| `updatedAt` | Last entry timestamp | Last activity |

### State Inference Logic

```typescript
// State is inferred from JSONL content using priority ordering:
let state: AgentState = 'active';  // Default

// Priority 1: Check for 'failed' state
if (lastStopReason === 'error' || hasToolError) {
  state = 'failed';
}
// Priority 2: Check for 'cancelled' state
else if (lastStopReason === 'max_tokens') {
  state = 'cancelled';
}
// Check for interrupted execution (pending tool use, file stale for 30+ seconds)
else if (msSinceModified > 30000 && lastMessageHasToolUse && !hasToolResultForLastUse) {
  state = 'cancelled';
}
// Priority 3: Check for 'completed' state
else if (hasStopReason && lastStopReason === 'end_turn') {
  state = 'completed';
} else if (lastMessageType === 'assistant' && lastMessageHasTextOnly) {
  // File hasn't been modified in 5+ seconds and last is text-only
  const msSinceModified = Date.now() - fileStats.mtimeMs;
  if (msSinceModified > 5000) {
    state = 'completed';
  }
}
// Priority 4: Check for 'waiting' state - tool_use without tool_result
else if (lastMessageType === 'assistant' && lastMessageHasToolUse && !hasToolResultForLastUse) {
  state = 'waiting';
}
// Priority 5: Check for 'pending' state - no assistant messages yet
else if (!hasAssistantMessage) {
  state = 'pending';
}
// Priority 6: Default to 'active' (already set)
```

**Why this works:**
- **Failed**: Agent encounters error tool result or error stop reason
- **Cancelled**: Agent hits token limit or tool use pending too long (30+ seconds stale)
- **Completed**: Explicit `end_turn` or text-only final message with no file updates for 5+ seconds
- **Waiting**: Last action was tool_use but haven't received tool_result yet
- **Pending**: JSONL file exists but agent hasn't generated any assistant messages
- **Active**: Default for ongoing work in progress

### Warmup Agent Filtering

Subagents created for Claude Code's internal model warmup are automatically filtered out:

```typescript
const isWarmupAgent = task.trim().toLowerCase() === 'warmup' ||
                      (toolCount === 0 && !hasAssistantMessage);
if (isWarmupAgent) {
  return null;  // Don't include in results
}
```

Warmup agents are identified by:
1. Task name is exactly "warmup"
2. No tools used AND no assistant messages (empty file)

## New CLI Commands

### `karma radio scan`

One-shot scan of subagents from JSONL files:

```bash
export KARMA_SESSION_ID=502283f5-181f-44ba-8c0d-73bec9cddcc0
export KARMA_AGENT_ID=$KARMA_SESSION_ID

karma radio scan
# Output:
# Agent      State        Model                     Tools  Task
# --------------------------------------------------------------------------------
# a9d027e    🔄 active    haiku-4-5-20251001        1      Count how many .ts files...
# a5793c3    🔄 active    haiku-4-5-20251001        1      Read karma-logger/src/index...

karma radio scan --json
# Returns full JSON with all agent details
```

### `karma radio summary`

Combined view of radio agents + JSONL subagents:

```bash
karma radio summary
# Output:
# Session: 502283f5-181f-44ba-8c0d-73bec9cddcc0
# Radio agents: 1
# Subagents (from JSONL): 11
#
# By state:
#   active: 11
#
# Agent      State        Model                     Tools  Task
# ...
```

### `karma radio watch-subagents`

Live monitoring mode with automatic radio reporting:

```bash
karma radio watch-subagents
# Continuously monitors subagents directory
# Updates display on changes
# Reports status changes to radio server

karma radio watch-subagents --json
# One-shot JSON output (same as scan --json)

karma radio watch-subagents --interval 500
# Poll every 500ms (default: 1000ms)
```

### `karma radio tree`

Display agent hierarchy as an ASCII tree:

```bash
karma radio tree
# Show tree for current session

karma radio tree --session <session-id>
# Show tree for specific session

karma radio tree --json
# Output as JSON
```

**Note:** The `tree` command shows agents registered via the radio server (from hooks). Subagents from JSONL files are not included in the tree since they don't register themselves in the radio hierarchy.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Claude Code Session                       │
│  session_id: 502283f5-181f-44ba-8c0d-73bec9cddcc0           │
├─────────────────────────────────────────────────────────────┤
│  Subagents (via Task tool)                                  │
│  ├── a9d027e (haiku) - "Count .ts files"                   │
│  ├── a5793c3 (haiku) - "Read index.ts"                     │
│  └── add3428 (haiku) - "Count lines in cli.ts"             │
└─────────────────────────────────────────────────────────────┘
              │                              │
              ▼                              ▼
┌─────────────────────┐         ┌─────────────────────────────┐
│   Hooks (Limited)   │         │   JSONL Files (Rich Data)   │
│                     │         │                             │
│ Only session_id     │         │ ~/.claude/projects/...      │
│ No subagent IDs     │         │   /subagents/agent-*.jsonl  │
│                     │         │                             │
│ Reports to radio    │         │ Contains:                   │
│ as single agent     │         │ - agentId                   │
└─────────────────────┘         │ - model                     │
                                │ - task                      │
                                │ - tool usage                │
                                │ - timestamps                │
                                └─────────────────────────────┘
                                             │
                                             ▼
                                ┌─────────────────────────────┐
                                │   Subagent Watcher          │
                                │                             │
                                │ - Polls JSONL directory     │
                                │ - Parses entries            │
                                │ - Infers state              │
                                │ - Reports to radio server   │
                                └─────────────────────────────┘
```

## Files Added/Modified

### New Files

- `src/walkie-talkie/subagent-watcher.ts` - Core inference logic
  - `scanSubagents()` - Scan directory for JSONL files
  - `createSubagentWatcher()` - Live monitoring with polling
  - `formatAgentsTable()` - Pretty-print agent list
  - `formatAgentsJson()` - JSON summary output

### Modified Files

- `src/commands/radio.ts` - Added CLI commands
  - `karma radio scan` - One-shot subagent scan
  - `karma radio summary` - Combined radio + JSONL view
  - `karma radio watch-subagents` - Live monitoring

## Known Limitations

1. **Depth tracking not available for subagents**
   - JSONL files don't contain parent-child relationships
   - All subagents inferred from JSONL are assigned `depth: 0` (direct children of root session)
   - To get proper hierarchy, agents must register via radio IPC hooks
   - **Workaround**: Use `karma radio hooks` to enable auto-registration in hooks

2. **State inference has edge cases**
   - Error detection relies on `is_error` flag in tool_result blocks
   - Error patterns in text (e.g., "failed", "exception") are detected but not definitive
   - Cannot distinguish "waiting" from "active" if no tool_use block present
   - Timeout detection uses file modification time as heuristic (30+ seconds = cancelled)

3. **Polling-based updates**
   - fs.watch is unreliable for JSONL files being appended
   - Fall back to polling (default: 1000ms)
   - May miss very rapid state changes (<1 second)

4. **No real-time integration**
   - JSONL files are written by Claude Code, not us
   - We can only observe, not influence
   - Latency between actual state change and our detection (up to polling interval)

5. **Session ID required**
   - Must know the session ID to find subagents directory
   - Cannot auto-discover sessions (need KARMA_SESSION_ID env var)

## Future Improvements

1. **Claude Code Enhancement Request**
   - Add `agent_id` and `parent_id` to hook input JSON
   - Would enable proper hook-based tracking without inference

2. **Better State Detection**
   - Analyze message patterns for failure detection
   - Track error tool results
   - Detect timeout patterns

3. **Dashboard Integration**
   - Show subagent tree in dashboard UI
   - Real-time updates via WebSocket
   - Visual progress indicators

## Usage Example

```bash
# Terminal 1: Start dashboard with radio
karma dashboard --radio

# Terminal 2: Watch subagents
export KARMA_SESSION_ID=<your-session-id>
export KARMA_AGENT_ID=$KARMA_SESSION_ID
karma radio watch-subagents

# Terminal 3: Run Claude Code with parallel agents
# Subagents will appear in Terminal 2 automatically
```
