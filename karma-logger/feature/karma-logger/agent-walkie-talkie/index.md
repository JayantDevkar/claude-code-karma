# Agent Walkie-Talkie - Implementation Phases

Fast key:value cache communication layer for agent coordination.

## Phase Overview

| Phase | Focus | Deliverables | Dependencies |
|-------|-------|--------------|--------------|
| 1 | Core Cache | `cache-store.ts` + tests | None |
| 2 | Agent Radio | `agent-radio.ts` + tests | Phase 1 |
| 3 | CLI Tool | `karma-radio` commands | Phase 2 |
| 4 | Hook Templates | YAML frontmatter examples | Phase 3 |
| 5 | Aggregator Integration | Enhanced `aggregator.ts` | Phase 2 |

## File Structure (Target)

```
src/walkie-talkie/
├── index.ts              # Public exports
├── cache-store.ts        # Phase 1
├── agent-radio.ts        # Phase 2
├── types.ts              # Phase 1-2
└── cli.ts                # Phase 3

tests/walkie-talkie/
├── cache-store.test.ts   # Phase 1
├── agent-radio.test.ts   # Phase 2
└── integration.test.ts   # Phase 5
```

## Success Criteria

- [ ] CacheStore <1ms p99 latency
- [ ] AgentRadio tracks parent-child relationships
- [ ] Hooks auto-broadcast status
- [ ] `karma watch` shows real-time agent status
- [ ] Zero bash/tail polling
- [ ] >50% context token reduction

## Links

- [Phase 1: Core Cache](./phase-1.md)
- [Phase 2: Agent Radio](./phase-2.md)
- [Phase 3: CLI Tool](./phase-3.md)
- [Phase 4: Hook Templates](./phase-4.md)
- [Phase 5: Aggregator Integration](./phase-5.md)
- [Original v0 Plan](../../agent-walkie-talkie/plan/v0.md)
