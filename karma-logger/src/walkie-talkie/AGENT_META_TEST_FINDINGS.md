# Walkie-Talkie Meta-Testing: Agent Perspective

Testing conducted by Claude Opus 4.5 using the radio CLI as an actual agent would.

## Summary

The walkie-talkie system works well for basic agent coordination. I found and fixed one critical bug (status not persisting) and identified several UX improvements for agent efficiency.

## Bug Fixed

### Status Not Persisting (Critical)

**Problem**: `set-status active` returned `{"success":true}` but `get-status` showed `pending`.

**Root Cause**: `socket-server.ts` created new `AgentRadioImpl` instances for each request without registering them with the aggregator. Each request got a fresh instance that was garbage collected.

**Fix**: Added `getOrCreateAgentRadio()` method to `aggregator.ts` that creates AND registers new radio instances. Updated `socket-server.ts` to use this method instead of creating untracked instances.

**Files Changed**:
- `src/aggregator.ts` - Added `getOrCreateAgentRadio()` method
- `src/walkie-talkie/socket-server.ts` - Use aggregator method instead of direct instantiation

## What Works Well

| Feature | Agent Benefit |
|---------|--------------|
| JSON output | Easy to parse in bash hooks or tool output |
| Status lifecycle | Maps naturally to agent states (pending→active→waiting→completed) |
| Metadata accumulation | Can add context incrementally |
| Parent-child awareness | `KARMA_PARENT_ID` auto-establishes hierarchy |
| Inbox messaging | Clean task delegation pattern |
| Exit codes | `0=success`, `1=timeout`, `2=error` - good for conditional logic |

## Pain Points for Agents

### 1. No Agent Discovery

**Problem**: I have to know agent IDs ahead of time. Can't discover siblings or children dynamically.

**Current Workaround**: Must track agent IDs manually in metadata.

**Suggested Addition**:
```bash
karma radio list-agents                    # All agents in session
karma radio list-agents --children         # My children
karma radio list-agents --siblings         # My siblings
```

### 2. Separate Status and Progress Queries

**Problem**: Progress is stored at `agent:{id}:progress` but `get-status` only returns status. To see full agent state, need two queries.

**Current**:
```bash
karma radio get-status       # Gets status
karma radio ???              # No way to get progress
```

**Suggested**: Either include progress in status response or add:
```bash
karma radio get-status --include-progress
```

### 3. No Batch Operations

**Problem**: Common pattern is: set status + report progress. Currently requires two CLI calls.

**Suggested**:
```bash
karma radio set-status active --percent 0 --message "Starting..."
```

### 4. wait-for is Polling (Known Limitation)

**Problem**: Per README, `wait-for` is polling-based, not true subscription.

**Impact**: Higher latency, more CPU cycles for long waits.

**Future**: True socket-based subscription would be more efficient.

### 5. No Schema Validation for Metadata

**Problem**: Metadata is `Record<string, unknown>`. No validation of shape.

**Risk**: Different agents might store conflicting metadata structures.

**Suggested**: Optional metadata schema per agent-type.

## Test Results

### Status Lifecycle ✅
```
set-status active    → get-status: state=active
set-status waiting   → get-status: state=waiting
set-status completed → get-status: state=completed
```

### Metadata Persistence ✅
```
set-status waiting --metadata '{"waiting_for": "child"}'
set-status completed --metadata '{"result": 42}'
get-status → metadata: {"waiting_for": "child", "result": 42}
```

### Inter-Agent Messaging ✅
```
Parent: send child-001 '{"task": "explore"}'
Child: listen → messages: [{"fromAgentId": "parent", "message": {"task": "explore"}}]
```

### Parent-Child Awareness ✅
```
Child with KARMA_PARENT_ID=parent-001:
get-status → parentId: "parent-001", parentType: "agent"
```

### Server Down Handling ✅
```
Server not running:
get-status → {"error": "Server not running"}
Exit code: 2
```

## Recommendations for Agent Integration

### Hook Setup Pattern
```bash
# .claude/hooks.yaml
hooks:
  PreToolUse:
    - command: |
        karma radio set-status active --tool "$TOOL_NAME" 2>/dev/null || true
      env:
        KARMA_AGENT_ID: "{{sessionId}}"
        KARMA_SESSION_ID: "{{rootSessionId}}"

  Stop:
    - command: |
        karma radio set-status completed 2>/dev/null || true
```

**Note**: Use `|| true` to prevent hook failures when server isn't running.

### Agent Spawn Pattern
When spawning a child agent, the parent should:
1. Set status to `waiting`
2. Send task message to child ID
3. Periodically check child status with `wait-for`

### Error Handling
```bash
result=$(karma radio set-status active 2>&1)
exit_code=$?
if [ $exit_code -eq 2 ]; then
  # Server error - continue without radio
  echo "Radio unavailable, continuing..." >&2
fi
```

## Next Steps

1. **High Priority**: Add agent discovery command (`list-agents`)
2. **Medium Priority**: Include progress in status response option
3. **Low Priority**: Batch status+progress in single call
4. **Future**: True subscription-based `wait-for`

---

*Meta-testing conducted: 2026-01-08*
*Agent: Claude Opus 4.5 (claude-opus-4-5-20251101)*
