# Agent Walkie-Talkie - Implementation Phases

Fast key:value cache communication layer for agent coordination.

## Phase Overview

| Phase | Focus | Deliverables | Dependencies | Status |
|-------|-------|--------------|--------------|--------|
| 1 | Core Cache | `cache-store.ts` + tests | None | Ready |
| 2 | Agent Radio | `agent-radio.ts` + tests | Phase 1 | Ready |
| 3 | CLI Tool | `karma radio` commands + socket-client | Phase 2, 5 | Ready |
| 4 | Hook Templates | YAML frontmatter examples | Phase 3 | **DEFERRED** |
| 5 | Aggregator Integration | Enhanced `aggregator.ts` + socket-server | Phase 2 | Ready |

**Implementation Order:** 1 → 2 → 5 → 3 → 4 (Phase 4 deferred until hook system validated)

## File Structure (Target)

```
src/
├── walkie-talkie/
│   ├── index.ts              # Public exports
│   ├── cache-store.ts        # Phase 1: CacheStore implementation
│   ├── agent-radio.ts        # Phase 2: AgentRadio implementation
│   ├── types.ts              # Phase 1-2: Interfaces
│   ├── socket-server.ts      # Phase 5: IPC server (owned by aggregator)
│   └── socket-client.ts      # Phase 3: IPC client (for CLI)
├── commands/
│   └── radio.ts              # Phase 3: `karma radio` subcommands
└── aggregator.ts             # Phase 5: Enhanced with radio support

tests/walkie-talkie/
├── cache-store.test.ts       # Phase 1
├── agent-radio.test.ts       # Phase 2
├── socket-client.test.ts     # Phase 3
└── integration.test.ts       # Phase 5

templates/hooks/              # Phase 4 (DEFERRED until validated)
├── walkie-talkie-hooks.yaml
└── README.md
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
