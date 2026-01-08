# Karma Logger - Implementation Phases

This directory contains atomic phase documents for building the karma-logger MVP.

## Phase Overview

| Phase | Title | Effort | Dependencies | Deliverable |
|-------|-------|--------|--------------|-------------|
| **0** | Project Scaffold | Small | None | Buildable TypeScript CLI |
| **1** | JSONL Parser | Medium | 0 | Streaming log parser |
| **2** | Log Discovery & Watcher | Medium | 1 | File watching system |
| **3** | Metrics & Cost | Medium | 1, 2 | Aggregation engine |
| **4** | `karma status` | Small | 3 | First user command |
| **5** | `karma watch` | Medium | 4 | Real-time display |
| **6** | SQLite & Report | Medium | 4 | Persistence layer |
| **7** | Polish & Packaging | Small | 5, 6 | npm-ready package |

## Dependency Graph

```
Phase 0: Scaffold
    │
    ▼
Phase 1: Parser
    │
    ├──────────────────┐
    ▼                  ▼
Phase 2: Watcher    (parallel)
    │                  │
    └────────┬─────────┘
             ▼
    Phase 3: Aggregation
             │
             ▼
    Phase 4: karma status
             │
    ┌────────┴────────┐
    ▼                 ▼
Phase 5: watch    Phase 6: report
    │                 │
    └────────┬────────┘
             ▼
    Phase 7: Polish
```

## Execution Strategy

### Sequential Path (Safe)
0 → 1 → 2 → 3 → 4 → 5 → 6 → 7

### Parallel Optimization
- Phases 5 and 6 can run in parallel after Phase 4
- Parser tests (Phase 1) can start while Scaffold (Phase 0) completes

## Progress Tracking

Mark phases as completed by updating this table:

| Phase | Status | Started | Completed | Notes |
|-------|--------|---------|-----------|-------|
| 0 | Complete | 2026-01-08 | 2026-01-08 | TypeScript CLI scaffold with Commander |
| 1 | Complete | 2026-01-08 | 2026-01-08 | Streaming JSONL parser with 20 tests |
| 2 | Complete | 2026-01-08 | 2026-01-08 | Log discovery + file watcher with 10 tests |
| 3 | Complete | 2026-01-08 | 2026-01-08 | Metrics aggregator + cost calc with 37 tests |
| 4 | Complete | 2026-01-08 | 2026-01-08 | `karma status` with --project, --all, --json flags |
| 5 | Complete | 2026-01-08 | 2026-01-08 | `karma watch` streaming mode with activity feed |
| 6 | Complete | 2026-01-08 | 2026-01-08 | SQLite persistence + `karma report` with JSON/CSV |
| 7 | Complete | 2026-01-08 | 2026-01-08 | Config system, error handling, docs, npm-ready |

## Quick Reference

### Commands Delivered
- Phase 4: `karma status`
- Phase 5: `karma watch`
- Phase 6: `karma report`
- Phase 7: `karma config`

### Key Files Per Phase
- **Phase 0**: `package.json`, `tsconfig.json`, `src/cli.ts`
- **Phase 1**: `src/parser.ts`, `src/types.ts`
- **Phase 2**: `src/watcher.ts`, `src/discovery.ts`
- **Phase 3**: `src/aggregator.ts`, `src/cost.ts`
- **Phase 4**: `src/commands/status.ts`, `src/format.ts`
- **Phase 5**: `src/commands/watch.ts`
- **Phase 6**: `src/db.ts`, `src/commands/report.ts`
- **Phase 7**: `src/config.ts`, `README.md`
