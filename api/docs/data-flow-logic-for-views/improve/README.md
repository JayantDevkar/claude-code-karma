# FastAPI Backend Optimization Plan

**Date**: 2026-01-11
**Status**: Verified and Planned
**Author**: System Engineer

---

## Executive Summary

Analysis of the FastAPI backend (`apps/api/`) revealed significant inefficiencies in JSONL file parsing. The backend performs redundant file I/O operations, with some endpoints iterating over the same data 4+ times per request.

This document outlines a 4-phase optimization plan to improve data fetching efficiency.

---

## Issues Identified

### Observation Summary

| # | Issue | Location | Severity |
|---|-------|----------|----------|
| 1 | Multiple iterator calls per request | `sessions.py:280-335` | High |
| 2 | `end_time` iterates all messages | `session.py:287-292` | Medium |
| 3 | `get_subagents()` has 4+ passes | `sessions.py:408-491` | Critical |
| 4 | `get_timeline()` double iteration | `sessions.py:824-952` | High |
| 5 | No model-level caching | `session.py` (all properties) | High |
| 6 | No HTTP caching headers | All routers | Medium |
| 7 | Date filtering after full load | `analytics.py:147-150` | Medium |
| 8 | Sequential subagent processing | `sessions.py:451-462` | Medium |

### Root Causes

1. **No caching at model layer** - Properties like `start_time`, `end_time`, `slug` re-parse the entire JSONL file on each access
2. **Multi-pass extraction patterns** - Endpoints call multiple methods that each iterate the full message stream
3. **No HTTP cache headers** - Browsers can't cache responses, every navigation triggers full backend processing
4. **Post-load filtering** - Analytics loads all sessions before applying date filters

---

## Optimization Phases

| Phase | Focus | Complexity | Impact | Risk |
|-------|-------|------------|--------|------|
| [Phase 1](./api-phase-1.md) | Model-level caching | Low | High | Low |
| [Phase 2](./api-phase-2.md) | Single-pass iteration | Medium | High | Medium |
| [Phase 3](./api-phase-3.md) | HTTP caching headers | Low-Medium | Medium-High | Low |
| [Phase 4](./api-phase-4.md) | Async/structural optimization | High | Medium-High | Medium |

---

## Phase Overview

### Phase 1: Model-Level Caching

**Goal**: Eliminate redundant file I/O within a single Session instance.

**Key Changes**:
- Add `SessionCache` class with lazy-loaded metadata
- Implement `_load_metadata()` single-pass extraction
- Update `start_time`, `end_time`, `slug`, `get_usage_summary()`, `get_tools_used()` to use cache

**Expected Impact**: 6x fewer file reads in `get_session()` endpoint

---

### Phase 2: Single-Pass Iteration Patterns

**Goal**: Refactor endpoints to extract all needed data in one iteration.

**Key Changes**:
- Create `SessionDataCollector` utility
- Refactor `get_subagents()` from 4 passes to 1
- Refactor `get_timeline()` from 2 passes to 1
- Add request-scoped caching

**Expected Impact**: 2-4x fewer iterations for affected endpoints

---

### Phase 3: HTTP Caching

**Goal**: Enable browser caching and conditional requests.

**Key Changes**:
- Add `@cacheable` decorator with configurable policies
- Implement ETag generation from file modification times
- Support `If-None-Match` and `If-Modified-Since` headers
- Return 304 Not Modified when appropriate

**Expected Impact**: 90%+ bandwidth savings on repeated requests

---

### Phase 4: Async and Structural Optimizations

**Goal**: Improve throughput through parallelism and early filtering.

**Key Changes**:
- Add `list_sessions_filtered()` with early date filtering
- Implement parallel subagent processing with thread pool
- Optional async file I/O with `aiofiles`
- Batch file operations for project listing

**Expected Impact**: 50-90% reduction in loaded sessions for date-filtered analytics

---

## Implementation Order

```
Phase 1 ─────────────────────────┐
                                 ├──> Phase 2 ──> Phase 4
Phase 3 (can run in parallel) ───┘
```

**Recommended sequence**:
1. Start with Phase 1 (low risk, high impact foundation)
2. Phase 3 can proceed in parallel (independent of model changes)
3. Phase 2 builds on Phase 1 caching infrastructure
4. Phase 4 is enhancement layer after core optimizations

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| File reads per `get_session()` | ~6 | 1 |
| Iterations in `get_subagents()` | 4+ | 1-2 |
| HTTP cache hit rate | 0% | >50% |
| Analytics date-filter efficiency | 0% (post-load) | 80%+ (pre-filter) |
| Repeated property access time | O(n) | O(1) |

---

## Files Modified Per Phase

| Phase | Files Modified | New Files |
|-------|----------------|-----------|
| 1 | `models/session.py`, `models/agent.py` | - |
| 2 | `apps/api/routers/sessions.py` | `apps/api/utils/collectors.py` |
| 3 | `apps/api/routers/*.py` | `apps/api/middleware/caching.py`, `apps/api/utils/cache_decorator.py` |
| 4 | `models/project.py`, `apps/api/routers/*.py` | `apps/api/utils/parallel.py`, `models/async_session.py` |

---

## Testing Strategy

Each phase includes:
1. **Unit tests** - Verify individual components work correctly
2. **Integration tests** - Verify API endpoints return correct responses
3. **Performance benchmarks** - Measure improvement against baseline
4. **Regression tests** - Ensure no breaking changes to API contracts

---

## Rollback Plan

All phases are designed for safe rollback:
- No database schema changes
- No API contract changes (response format unchanged)
- Cache layers can be disabled/removed without side effects
- Each phase can be reverted independently

---

## Next Steps

1. Review and approve Phase 1 plan
2. Create feature branch for implementation
3. Implement Phase 1 with full test coverage
4. Benchmark improvements
5. Proceed to Phase 2 and Phase 3
