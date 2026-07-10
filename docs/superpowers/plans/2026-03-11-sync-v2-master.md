# Sync Architecture v2 — Master Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the P2P sync layer so each device is a distinct member with its own stream, fix the session merging bug, add state convergence via metadata folders, and make the pending folder UX clear and unambiguous.

**Architecture:** Device = Member identity model. Each machine gets a unique `member_tag` (`{user_id}.{machine_tag}`) embedded in Syncthing folder IDs. A team metadata folder (`karma-meta--{team}`, `sendreceive` type) syncs membership state, subscriptions, and removal signals across machines. Opt-out selective subscriptions. Creator-only removal authority.

**Tech Stack:** Python 3.9+, FastAPI, Pydantic 2.x, SQLite, Syncthing REST API

---

## Design Decisions (Locked)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Identity model | Device = Member | Each machine has independent send/receive control |
| member_tag format | `{user_id}.{machine_tag}` | Human-readable, parseable via `.` separator |
| machine_tag derivation | Auto from hostname, sanitized | No user friction at setup |
| Removal authority | Creator only | Small trusted teams, `team.json.created_by` check |
| Metadata folder type | `sendreceive` | Each member writes own file, no conflicts |
| Subscription model | Opt-out | Everyone gets everything by default, can unsubscribe |
| Cross-team dedup | Folder IDs are globally unique | Same outbox folder shared across teams, no duplication |
| Breaking changes | Allowed | Feature in development, no backward compat needed |

## Dependency Graph

```
Phase 0: Quick Wins (all parallel)
═══════════════════════════════════
  T0.1 (reconcile fix)     ─┐
  T0.2 (self-introducer)   ─┤
  T0.3 (collision check)   ─┼── All 6 independent, run in parallel
  T0.4 (settings cleanup)  ─┤
  T0.5 (project cleanup)   ─┤
  T0.6 (exception fix)     ─┘

Phase 1: Device = Member Identity (sequential core → parallel fan-out)
══════════════════════════════════════════════════════════════════════
  T1.1 (SyncConfig + machine_tag)
    │
    ▼
  T1.2 (DB migration v17)
    │
    ▼
  T1.3 (folder_id.py v2)
    │
    ├──────────────────┬──────────────────┐
    ▼                  ▼                  ▼
  T1.4 (sync_folders) T1.5 (reconcile)  T1.6 (pending.py)
    │                  │                  │
    └──────────────────┼──────────────────┘
                       ▼
                 T1.7 (routers)
                   ├──────────┐
                   ▼          ▼
            T1.8 (remote)  T1.9 (packager)

Phase 2: Metadata Folder (sequential)
═════════════════════════════════════
  T2.1 (file format + helpers)
    │
    ▼
  T2.2 (create on team create/join)
    │
    ├──────────────────┐
    ▼                  ▼
  T2.3 (member write)  T2.4 (removal write)
    │                    │
    └──────────┬─────────┘
               ▼
         T2.5 (reconciliation reads metadata)
               │
               ├──────────┐
               ▼          ▼
         T2.6 (auto-leave) T2.7 (watcher loop)

Phase 3: UX Polish (mostly parallel)
════════════════════════════════════
  T3.1 (rejected table) ──→ T3.2 (rejection endpoint)
  T3.3 (subscriptions)  ──→ T3.4 (auto_share check)
  T3.5 (any-member invite)  ── independent
  T3.6 (session limit per-device) ── independent
```

## Phase Documents

| Phase | Plan File | Effort | Strategy |
|-------|-----------|--------|----------|
| 0 | `2026-03-11-sync-v2-phase0-quick-wins.md` | 1 day | `superpowers:dispatching-parallel-agents` — all 6 tasks independent |
| 1 | `2026-03-11-sync-v2-phase1-device-identity.md` | 2-3 days | `superpowers:subagent-driven-development` — sequential core, fan-out |
| 2 | `2026-03-11-sync-v2-phase2-metadata-folder.md` | 2-3 days | `superpowers:subagent-driven-development` — sequential |
| 3 | `2026-03-11-sync-v2-phase3-ux-polish.md` | 1-2 days | `superpowers:dispatching-parallel-agents` — mostly independent |

## Agent & Skill Hints

| Task Group | Recommended Agent | Skill to Invoke | Notes |
|------------|------------------|-----------------|-------|
| Phase 0 (all) | Parallel worktree agents | `superpowers:dispatching-parallel-agents` | Each task gets own worktree, merge after |
| T1.1–T1.3 | Main session (sequential) | `superpowers:executing-plans` | Core identity changes, needs coordination |
| T1.4–T1.6 | 3 parallel subagents | `superpowers:subagent-driven-development` | Independent files after T1.3 |
| T1.7–T1.9 | 3 parallel subagents | `superpowers:subagent-driven-development` | Independent files after T1.4–T1.6 |
| T2.1–T2.5 | Main session (sequential) | `superpowers:executing-plans` | State convergence needs careful ordering |
| T2.6–T2.7 | 2 parallel subagents | `superpowers:subagent-driven-development` | Independent after T2.5 |
| Phase 3 (all) | 4 parallel subagents | `superpowers:dispatching-parallel-agents` | All independent features |

## Test Infrastructure

All sync tests follow this pattern:
```python
import sqlite3
import pytest
from db.schema import ensure_schema

@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    ensure_schema(c)
    return c
```

Run tests: `cd api && pytest tests/test_sync_*.py -v`

## Key File Map

| File | Role | Phases Modified |
|------|------|----------------|
| `cli/karma/config.py` | SyncConfig model | 1 |
| `api/services/folder_id.py` | Folder ID build/parse | 1 |
| `api/services/sync_folders.py` | Folder CRUD helpers | 0, 1, 2, 3 |
| `api/services/sync_reconciliation.py` | 4-phase reconciliation | 0, 1, 2 |
| `api/services/sync_identity.py` | Identity + validation | 1 |
| `api/services/sync_policy.py` | Policy evaluation | 3 |
| `api/db/schema.py` | SQLite schema | 1, 3 |
| `api/db/sync_queries.py` | DB CRUD | 0, 1, 2, 3 |
| `api/routers/sync_devices.py` | Device pairing | 0, 1 |
| `api/routers/sync_teams.py` | Team lifecycle | 0, 1, 2, 3 |
| `api/routers/sync_members.py` | Member management | 1, 2 |
| `api/routers/sync_projects.py` | Project sharing | 0, 1, 3 |
| `api/routers/sync_pending.py` | Pending folder UX | 1, 3 |
| `cli/karma/pending.py` | CLI folder acceptance | 1 |
| `cli/karma/packager.py` | Session packaging | 1 |
| `api/services/remote_sessions.py` | Remote session discovery | 1 |

## Verification Checklist (After All Phases)

- [ ] Two devices with same user_id produce distinct folder IDs
- [ ] Pending UI shows device-specific descriptions (no "Receive Receive" duplicates)
- [ ] Removed member detects removal via metadata folder and auto-leaves
- [ ] Rejected folder offers don't reappear
- [ ] Unsubscribed projects don't create inbox folders
- [ ] Any team member can generate invite codes
- [ ] Session limit per-device works via metadata file
- [ ] Settings cleaned up on team delete
- [ ] Remove-project cleans filesystem + DB
- [ ] `reconcile_introduced_devices` creates folders for introduced peers
- [ ] All existing sync tests pass (`pytest tests/test_sync_*.py -v`)
