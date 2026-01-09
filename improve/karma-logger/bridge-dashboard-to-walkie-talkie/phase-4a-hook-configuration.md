# Phase 4a: Configure Test Hooks for E2E Testing

> **Priority:** Medium | **Complexity:** Medium | **Type:** Testing + Documentation

## Objective

Create Claude Code hook configuration that reports agent status to karma radio.

## Prerequisites

- Phase 3 complete (full stack working)

## Files to Create

| File | Action |
|------|--------|
| `.claude/hooks.yaml` (test project) | Create hook configuration |

## Implementation

```yaml
# .claude/hooks.yaml
hooks:
  # Report when tool execution starts
  PreToolUse:
    - command: |
        karma radio set-status working --message "Using $TOOL_NAME"
      env:
        KARMA_AGENT_ID: "{{agentId}}"
        KARMA_SESSION_ID: "{{sessionId}}"
        KARMA_PARENT_ID: "{{parentAgentId}}"
        KARMA_AGENT_TYPE: "{{agentType}}"
        KARMA_MODEL: "{{model}}"
      timeout: 5000
      on_error: ignore

  # Report completion
  PostToolUse:
    - command: |
        karma radio report-progress 0 --message "Completed $TOOL_NAME"
      env:
        KARMA_AGENT_ID: "{{agentId}}"
        KARMA_SESSION_ID: "{{sessionId}}"
      timeout: 5000
      on_error: ignore

  # Report session start
  SessionStart:
    - command: |
        karma radio set-status idle --message "Session started"
      env:
        KARMA_AGENT_ID: "{{sessionId}}"
        KARMA_SESSION_ID: "{{sessionId}}"
      timeout: 5000
      on_error: ignore

  # Report session end
  Stop:
    - command: |
        karma radio set-status done --message "Session completed"
      env:
        KARMA_AGENT_ID: "{{agentId}}"
        KARMA_SESSION_ID: "{{sessionId}}"
      timeout: 5000
      on_error: ignore
```

## Acceptance Criteria

- [x] Hooks file syntax valid
- [x] Environment variables correctly templated
- [x] Timeouts prevent blocking Claude Code
- [x] `on_error: ignore` prevents failures from breaking session

**Completed:** Hook configuration created at `karma-logger/examples/.claude/hooks.yaml`

**Implementation Notes:**
- Uses correct states from radio types: `pending`, `active`, `waiting`, `completed`, `failed`, `cancelled`
- All hooks include full environment variable set
- Error suppression with `2>/dev/null || true` pattern for graceful degradation

## Testing

```bash
# Start dashboard with radio
karma dashboard --radio

# In test project with hooks configured
# Run any Claude Code command
# Watch dashboard for agent status updates
```

## Next Phase

→ Phase 4b: Full integration testing
