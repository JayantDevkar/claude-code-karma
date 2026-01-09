# Phase 4b: Full Integration Testing

> **Priority:** Medium | **Complexity:** Medium | **Type:** Testing

## Objective

Verify end-to-end flow from Claude Code hooks through to dashboard visualization.

## Prerequisites

- Phase 4a complete (hooks configured)

## Test Scenarios

### Scenario 1: Single Agent Lifecycle

```bash
# Terminal 1: Start dashboard
karma dashboard --radio

# Terminal 2: Simulate agent lifecycle
export KARMA_AGENT_ID="agent-001"
export KARMA_SESSION_ID="session-test"
export KARMA_AGENT_TYPE="test-agent"
export KARMA_MODEL="sonnet"

karma radio set-status idle
sleep 1
karma radio set-status working --message "Processing task"
karma radio report-progress 25 --message "Step 1 complete"
sleep 1
karma radio report-progress 50 --message "Step 2 complete"
sleep 1
karma radio report-progress 75 --message "Step 3 complete"
sleep 1
karma radio report-progress 100 --message "Finishing"
karma radio set-status done

# Verify in browser: agent card appears, progress updates, completes
```

### Scenario 2: Parent-Child Agents

```bash
# Parent agent
export KARMA_AGENT_ID="parent-001"
export KARMA_SESSION_ID="session-test"
karma radio set-status working

# Child agent
export KARMA_AGENT_ID="child-001"
export KARMA_PARENT_ID="parent-001"
karma radio set-status working

# Verify tree structure in API
curl http://localhost:3333/api/radio/session/session-test/tree
```

### Scenario 3: Persistence Test

```bash
# Start with persistence
karma dashboard --persist-radio

# Register agents, note states

# Stop dashboard (Ctrl+C)

# Restart dashboard
karma dashboard --persist-radio

# Verify agents restored
curl http://localhost:3333/api/radio/agents
```

## Acceptance Criteria

- [ ] Single agent lifecycle visible in dashboard
- [ ] Progress bar updates in real-time
- [ ] Parent-child relationships shown in tree
- [ ] Persistence survives restart
- [ ] Multiple concurrent agents handled

## Next Phase

→ Phase 4c: Documentation update
