# Sync v4: Domain Models Implementation — Master Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Full rewrite of sync feature with Pydantic domain models, repository pattern, and simplified 3-phase reconciliation.

**Architecture:** Pure domain models (no DB coupling) with state machines for Team, Member, SharedProject, Subscription. Repository pattern for SQLite persistence. Services orchestrate domain logic + Syncthing. Thin FastAPI routers.

**Tech Stack:** Python 3.9+, Pydantic 2.x, FastAPI, SQLite, pytest, Syncthing REST API

**Spec:** `docs/superpowers/specs/2026-03-17-sync-v4-domain-models-design.md`

---

## Phase Dependency Graph

```
Phase 1: Foundation               Phase 2: Infrastructure
(Domain Models + Schema + Repos)  (Syncthing Abstraction + Pairing)
         │                                    │
         │         ┌─── CAN RUN IN ───┐       │
         │         │    PARALLEL       │       │
         ▼         └───────────────────┘       ▼
         └──────────────┬──────────────────────┘
                        │
                        ▼
              Phase 3: Business Logic
              (Services — TeamService,
               ProjectService, MetadataService,
               ReconciliationService)
                        │
                        ▼
              Phase 4: API + Integration
              (Routers, Watcher, Cleanup,
               Delete old v3 files)
```

**Phase 1 and Phase 2 are fully independent — run them in parallel.**

## Phase Summary

| Phase | Name | Tasks | Est. Files | Parallel? | Depends On |
|-------|------|-------|------------|-----------|------------|
| 1 | Foundation | 8 | 16 | Internal parallelism (5 models, 5 repos) | — |
| 2 | Infrastructure | 5 | 8 | **Yes — parallel with Phase 1** | — |
| 3 | Business Logic | 6 | 10 | After Phase 1+2 | Phase 1, Phase 2 |
| 4 | API + Integration | 7 | 12 | Internal parallelism (4 routers) | Phase 3 |
| **Total** | | **26 tasks** | **~46 files** | | |

## Phase Details

### Phase 1: Foundation (`2026-03-17-sync-v4-phase1-foundation.md`)
Domain models, schema migration, repositories. The core that everything else builds on.

**Internal parallelism:**
- Task 1-5 (5 domain models) — ALL PARALLEL
- Task 6 (schema migration) — sequential, after models
- Task 7 (repositories) — after schema, but 5 repos can be parallel
- Task 8 (integration test) — after repos

### Phase 2: Infrastructure (`2026-03-17-sync-v4-phase2-infrastructure.md`)
Syncthing HTTP client, device/folder managers, pairing service. No domain model dependency.

**Internal parallelism:**
- Task 1 (SyncthingClient) — first
- Task 2-3 (DeviceManager, FolderManager) — PARALLEL, after Task 1
- Task 4 (PairingService) — INDEPENDENT, can parallel with all
- Task 5 (integration test) — after all

### Phase 3: Business Logic (`2026-03-17-sync-v4-phase3-services.md`)
Services that orchestrate domain models + repos + Syncthing.

**Internal parallelism:**
- Task 1 (MetadataService) — first (others use it)
- Task 2-3 (TeamService, ProjectService) — PARALLEL, after MetadataService
- Task 4 (ReconciliationService) — after TeamService + ProjectService
- Task 5 (WatcherManager) — after ReconciliationService
- Task 6 (integration test) — after all

### Phase 4: API + Integration (`2026-03-17-sync-v4-phase4-api.md`)
Thin routers, old file cleanup, end-to-end testing.

**Internal parallelism:**
- Task 1-4 (4 routers) — ALL PARALLEL
- Task 5 (router registration + conftest) — after routers
- Task 6 (delete old v3 files) — after routers confirmed working
- Task 7 (end-to-end smoke test) — final

## Agent & Skill Recommendations

### For Parallel Phase Execution (Phase 1 + Phase 2)

**Recommended:** `superpowers:dispatching-parallel-agents` or `oh-my-claudecode:ultrapilot`

Launch two worktree-isolated agents:
- Agent A: Phase 1 (Foundation) in worktree A
- Agent B: Phase 2 (Infrastructure) in worktree B

Merge both into the feature branch when complete.

### For Within-Phase Task Execution

**Recommended:** `superpowers:subagent-driven-development`

Each task dispatched as a fresh subagent with:
- The phase doc as context
- TDD enforcement (write test → verify fail → implement → verify pass → commit)
- Review between tasks

### For Individual Task TDD

**Recommended:** `oh-my-claudecode:tdd` or `superpowers:test-driven-development`

Both enforce write-tests-first methodology. Use for any task that creates new code.

### For Code Review Checkpoints

**Recommended:** `superpowers:requesting-code-review` after each phase completes

Review the phase's code against the spec before starting the next phase.

### For Build Errors

**Recommended:** `oh-my-claudecode:build-fix` or `everything-claude-code:build-error-resolver`

If tests fail unexpectedly during implementation, these agents fix with minimal diffs.

## File Map (Complete)

```
api/
├── domain/                          # Phase 1 — NEW
│   ├── __init__.py
│   ├── team.py                      # Team + TeamStatus enum
│   ├── member.py                    # Member + MemberStatus enum
│   ├── project.py                   # SharedProject + SharedProjectStatus enum
│   ├── subscription.py              # Subscription + SubscriptionStatus + SyncDirection enums
│   └── events.py                    # SyncEvent + SyncEventType enum
│
├── repositories/                    # Phase 1 — NEW
│   ├── __init__.py
│   ├── team_repo.py
│   ├── member_repo.py
│   ├── project_repo.py
│   ├── subscription_repo.py
│   └── event_repo.py
│
├── services/
│   ├── sync/                        # Phase 3 — NEW
│   │   ├── __init__.py
│   │   ├── team_service.py
│   │   ├── project_service.py
│   │   ├── reconciliation_service.py
│   │   └── metadata_service.py
│   │
│   ├── syncthing/                   # Phase 2 — NEW
│   │   ├── __init__.py
│   │   ├── client.py
│   │   ├── device_manager.py
│   │   └── folder_manager.py
│   │
│   ├── sync/
│   │   └── pairing_service.py       # Phase 2 — NEW
│   │
│   ├── watcher_manager.py           # Phase 3 — REWRITE
│   └── remote_sessions.py           # UNCHANGED
│
├── routers/                         # Phase 4 — REWRITE
│   ├── sync_teams.py
│   ├── sync_projects.py
│   ├── sync_pairing.py              # NEW
│   └── sync_system.py
│
├── db/
│   └── schema.py                    # Phase 1 — MODIFY (add v19 migration)
│
└── tests/
    ├── test_domain_team.py          # Phase 1
    ├── test_domain_member.py        # Phase 1
    ├── test_domain_project.py       # Phase 1
    ├── test_domain_subscription.py  # Phase 1
    ├── test_domain_events.py        # Phase 1
    ├── test_repo_team.py            # Phase 1
    ├── test_repo_member.py          # Phase 1
    ├── test_repo_project.py         # Phase 1
    ├── test_repo_subscription.py    # Phase 1
    ├── test_repo_event.py           # Phase 1
    ├── test_schema_v19.py           # Phase 1
    ├── test_syncthing_client.py     # Phase 2
    ├── test_device_manager.py       # Phase 2
    ├── test_folder_manager.py       # Phase 2
    ├── test_pairing_service.py      # Phase 2
    ├── test_metadata_service.py     # Phase 3
    ├── test_team_service.py         # Phase 3
    ├── test_project_service.py      # Phase 3
    ├── test_reconciliation_service.py # Phase 3
    └── api/
        ├── test_sync_teams_router.py    # Phase 4
        ├── test_sync_projects_router.py # Phase 4
        ├── test_sync_pairing_router.py  # Phase 4
        └── test_sync_system_router.py   # Phase 4
```

## Files to Delete (Phase 4, Task 6)

```
api/routers/sync_members.py
api/routers/sync_pending.py
api/routers/sync_devices.py
api/routers/sync_operations.py
api/services/sync_queries.py
api/services/sync_reconciliation.py
api/services/sync_folders.py
api/services/sync_metadata_reconciler.py
api/services/sync_metadata_writer.py
api/services/sync_identity.py
api/services/sync_policy.py
api/services/syncthing_proxy.py
api/db/sync_queries.py
```

## Execution Order

```
START
  │
  ├──→ Phase 1: Foundation          (Agent A — worktree)
  │      Tasks 1-5 (models, parallel)
  │      Task 6 (schema)
  │      Task 7 (repos, parallel)
  │      Task 8 (integration)
  │
  ├──→ Phase 2: Infrastructure      (Agent B — worktree, PARALLEL)
  │      Task 1 (client)
  │      Tasks 2-4 (managers, parallel)
  │      Task 5 (integration)
  │
  ├──→ MERGE Phase 1 + Phase 2
  │
  ├──→ Code Review Checkpoint
  │
  ├──→ Phase 3: Business Logic      (Agent C — worktree)
  │      Task 1 (metadata)
  │      Tasks 2-3 (team+project svc, parallel)
  │      Task 4 (reconciliation)
  │      Task 5 (watcher)
  │      Task 6 (integration)
  │
  ├──→ Code Review Checkpoint
  │
  ├──→ Phase 4: API + Integration   (Agent D — worktree)
  │      Tasks 1-4 (routers, parallel)
  │      Task 5 (registration)
  │      Task 6 (delete old files)
  │      Task 7 (smoke test)
  │
  └──→ Final Code Review → DONE
```

## Test Commands

```bash
cd api

# Run all v4 tests
pytest tests/test_domain_*.py tests/test_repo_*.py tests/test_*_service.py tests/test_*_manager.py -v

# Run by phase
pytest tests/test_domain_*.py -v                    # Phase 1 models
pytest tests/test_schema_v19.py tests/test_repo_*.py -v  # Phase 1 repos
pytest tests/test_syncthing_*.py tests/test_device_*.py tests/test_folder_*.py tests/test_pairing_*.py -v  # Phase 2
pytest tests/test_*_service.py -v                   # Phase 3
pytest tests/api/test_sync_*_router.py -v           # Phase 4

# Full suite with coverage
pytest --cov=domain --cov=repositories --cov=services/sync --cov=services/syncthing --cov=routers -v
```
