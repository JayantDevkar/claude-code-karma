# DEPRECATED: performance-auditor

**Deprecated:** January 7, 2026
**Reason:** 7 responsibilities, 139 lines, configuration bloat
**Work Item:** CLAUDEKARM-31

## Why Deprecated

The `performance-auditor` was a monolithic agent with:
- 7 distinct responsibilities
- 139 lines of embedded configuration
- Role-based naming
- No tool specifications

## Replacement Agents

| Old Capability | New Agent | Focus |
|----------------|-----------|-------|
| Query benchmarking | `benchmark-queries` | Query timing only |
| Memory profiling | `measure-memory` | Memory tracking only |
| Concurrency testing | `test-concurrency` | Thread testing only |
| Report generation | `generate-perf-report` | Report creation only |

## Configuration Extracted

Configuration moved to:
- `config/benchmark/query_config.yaml`
- `config/benchmark/memory_config.yaml`
- `config/benchmark/concurrency_config.yaml`

## Token Impact

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Lines | 139 | ~45 each | 70% per agent |
| Tokens | 2000+ | ~400 each | 80% per operation |
| Responsibilities | 7 | 1 each | SOLID compliant |

---
*Deprecated as part of Claude Karma Philosophy compliance initiative*
