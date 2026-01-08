# Agent Walkie-Talkie Improvement Phases

Atomic improvement phases for the karma-logger walkie-talkie system, derived from agent meta-testing findings.

## Phase Overview

| Phase | Name | Priority | Complexity | Status |
|-------|------|----------|------------|--------|
| 1 | [Agent Discovery](./phase-1-agent-discovery.md) | High | Medium | **DONE** |
| 2 | [Status + Progress Consolidation](./phase-2-status-progress-consolidation.md) | Medium | Low | **DONE** |
| 3 | [Batch Operations](./phase-3-batch-operations.md) | Low | Low | **DONE** |
| 4 | [Subscription-Based Wait](./phase-4-subscription-based-wait.md) | Future | High | **DONE** |
| 5 | [Metadata Schema Validation](./phase-5-metadata-schema-validation.md) | Low | Medium | **DONE** |
| 6 | [Cache Persistence](./phase-6-cache-persistence.md) | Future | High | Planned |

## Recommended Implementation Order

```
Phase 1 (Agent Discovery)
    │
    ▼
Phase 2 (Status + Progress)  ──┬──▶  Phase 3 (Batch Operations)
                               │
                               └──▶  Phase 5 (Schema Validation)


Phase 4 (Subscription Wait)  ◀──┐
                                │
Phase 6 (Cache Persistence)  ◀──┘   [Future - Independent]
```

**Rationale:**
- Phase 1 is highest value for agent workflows
- Phases 2-3 are quick wins with low complexity
- Phase 5 is independent, do when needed
- Phases 4 & 6 are architectural changes, defer until proven necessary

## Source Documentation

- [Meta-Test Findings](../../karma-logger/src/walkie-talkie/AGENT_META_TEST_FINDINGS.md)
- [Walkie-Talkie README](../../karma-logger/src/walkie-talkie/README.md)

## Bug Fixed (Pre-Phase)

Status persistence bug was fixed before these phases:
- **Problem**: `set-status` didn't persist across CLI calls
- **Fix**: `aggregator.ts` now manages AgentRadio instances via `getOrCreateAgentRadio()`
- **Commit**: `0726ef7`

## Success Metrics

| Metric | Target | Status |
|--------|--------|--------|
| CLI calls per agent lifecycle | Reduce from 4-5 to 2-3 | ✅ Phase 3 |
| Agent discovery capability | Yes (currently No) | ✅ Phase 1 |
| Wait latency (P99) | <100ms (was ~1s polling) | ✅ Phase 4 |
| Crash recovery | Restore state (currently lost) | Pending (Phase 6) |

## Testing Strategy

Each phase includes:
1. Unit tests for new methods
2. Integration tests for CLI commands
3. Socket protocol tests where applicable
4. Backward compatibility verification
