# Feature: Subagent Type Visibility

## Summary

Expose `subagent_type` (e.g., `Explore`, `Plan`, `Bash`) from Task tool invocations throughout the API and UI.

## Current State

| Layer | Status | Review |
|-------|--------|--------|
| JSONL Data | Has `subagent_type` in `Task.input` | — |
| ToolUseBlock Model | Captures in `input` dict | — |
| API Response | **DONE** - Extracted in `/subagents` and `/timeline` | ✅ Approved |
| TypeScript Types | **DONE** - Added to `SubagentSummary` and `ToolCallMetadata` | ✅ Approved |
| UI | **DONE** - Badge in timeline + subagent cards | ✅ Approved |

## Implementation Order

```
1. Backend Phase 1-2  →  Schema + Timeline extraction         ✅ DONE (reviewed)
2. Frontend Phase 1   →  TypeScript types                     ✅ DONE (reviewed)
3. Backend Phase 3    →  Link subagents to Task invocations   ✅ DONE (reviewed)
4. Backend Refinement →  Whitespace normalization + logging   ✅ DONE
5. Frontend Phase 2-4 →  Badge component + display in UI      ✅ DONE
```

## Execution

| Phase | Owner | Depends On | Status |
|-------|-------|------------|--------|
| Backend P1-3 | Backend eng | None | ✅ Complete |
| Backend Refinement | Backend eng | Review feedback | ✅ Complete |
| Frontend P1 | Frontend eng | None (parallel) | ✅ Complete |
| Frontend P2-4 | Frontend eng | Backend P3, Frontend P1 | ✅ Complete |

## Code Review (2026-01-10)

| Component | Verdict | Blockers | Non-Blocking Issues |
|-----------|---------|----------|---------------------|
| Backend | ✅ APPROVE | 0 | 3 concerns |
| Frontend Types | ✅ APPROVE | 0 | 2 concerns |

See [backend.md](./backend.md#code-review-2026-01-10) and [frontend.md](./frontend.md#code-review-2026-01-10) for details.

## Files

- [backend.md](./backend.md) - Python/FastAPI changes
- [frontend.md](./frontend.md) - TypeScript/React changes

## Testing Checklist

- [x] API returns `subagent_type` in `/sessions/{uuid}/subagents`
- [x] Timeline events for Task tool include `subagent_type` in metadata
- [x] Missing `subagent_type` doesn't break parsing (optional field)
- [x] TypeScript types updated and compile without errors
- [ ] Badge renders correctly for known types (Explore, Plan, Bash)
- [ ] Badge handles unknown types gracefully

## API Response Examples

### GET /sessions/{uuid}/subagents

```json
[
  {
    "agent_id": "a1b2c3d",
    "slug": "curious-explorer",
    "subagent_type": "Explore",
    "tools_used": {"Glob": 5, "Read": 12},
    "message_count": 8,
    "initial_prompt": "Explore the codebase structure..."
  }
]
```

### GET /sessions/{uuid}/timeline (Task tool event)

```json
{
  "id": "evt-42",
  "event_type": "tool_call",
  "title": "Spawn subagent",
  "summary": "Explore the codebase structure",
  "metadata": {
    "tool_name": "Task",
    "description": "Explore the codebase structure...",
    "subagent_type": "Explore"
  }
}
```
