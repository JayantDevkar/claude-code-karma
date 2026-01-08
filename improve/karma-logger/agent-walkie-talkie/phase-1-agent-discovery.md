# Phase 1: Agent Discovery

**Priority:** High
**Complexity:** Medium
**Estimated Files:** 4-5

## Problem Statement

From meta-testing: "I have to know agent IDs ahead of time. Can't discover siblings or children dynamically."

Agents currently must track IDs manually in metadata. There's no way to query the agent hierarchy at runtime.

## Goal

Enable agents to discover other agents in the session dynamically.

## Implementation

### 1. CLI Command

Add `karma radio list-agents` to `src/commands/radio.ts`:

```bash
karma radio list-agents                    # All agents in session
karma radio list-agents --children         # My children only
karma radio list-agents --siblings         # My siblings only
karma radio list-agents --parent           # My parent only
karma radio list-agents --status active    # Filter by status
karma radio list-agents --json             # JSON output (default)
```

### 2. AgentRadio Method

Add to `src/walkie-talkie/agent-radio.ts`:

```typescript
interface AgentDiscoveryOptions {
  filter?: 'children' | 'siblings' | 'parent' | 'all';
  status?: AgentState;
}

listAgents(options?: AgentDiscoveryOptions): AgentStatus[]
```

### 3. Socket Server Handler

Add handler in `src/walkie-talkie/socket-server.ts`:

```typescript
case 'list-agents':
  const agents = radio.listAgents(payload.options);
  return { agents };
```

### 4. API Endpoint

Already partially exists: `GET /api/radio/agents`

Extend with query params:
```
GET /api/radio/agents?filter=children&agentId=xyz
GET /api/radio/agents?status=active
```

## Files to Modify

| File | Change |
|------|--------|
| `src/walkie-talkie/agent-radio.ts` | Add `listAgents()` method |
| `src/walkie-talkie/types.ts` | Add `AgentDiscoveryOptions` interface |
| `src/walkie-talkie/socket-server.ts` | Add `list-agents` handler |
| `src/commands/radio.ts` | Add `list-agents` subcommand |
| `src/dashboard/api.ts` | Extend agents endpoint |

## Test Cases

```typescript
// agent-radio.test.ts additions
describe('listAgents', () => {
  it('returns all agents in session');
  it('filters by children');
  it('filters by siblings');
  it('filters by parent');
  it('filters by status');
  it('returns empty array when no matches');
});
```

## Acceptance Criteria

- [x] `karma radio list-agents` returns all agents in current session
- [x] `--children` flag returns only child agents
- [x] `--siblings` flag returns only sibling agents
- [x] `--status` flag filters by agent state
- [x] JSON output is parseable by agents
- [x] Exit code 0 on success, 2 on error

## Implementation Status: COMPLETED (2026-01-08)

### Files Modified
- `src/walkie-talkie/types.ts` - Added `list-agents` to RadioCommand, AgentDiscoveryOptions interface, listAgents to AgentRadio interface
- `src/walkie-talkie/agent-radio.ts` - Implemented `listAgents()` method with filter and status options
- `src/walkie-talkie/socket-server.ts` - Added `list-agents` case handler
- `src/commands/radio.ts` - Added `handleListAgents()` function and CLI subcommand

## Dependencies

- Requires session:agents key to be reliably maintained
- Parent-child relationships must be tracked in status

## Rollback

Command is additive; no rollback needed.
