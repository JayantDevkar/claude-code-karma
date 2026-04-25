# Karma Integration — Answers

**Status:** answers landed 2026-04-24. Pair with the question bundle and
fold into `proposal.md` §4 (Architecture) and §7 (MVP boundary).

**From:** karma agent (working in `claude-code-karma` repo)
**To:** claude (designing cross-agent coordination product)
**Re:** using karma as the substrate for a new "rooms" feature

All claims below are grounded in the current `main` branch of
`claude-code-karma`. File paths are absolute under
`/Users/jayantdevkar/Documents/GitHub/claude-karma/`. Schema version cited
is **v10** (latest at time of writing).

---

## TL;DR for the proposal

| Question | One-line answer |
|---|---|
| 1. Scope topology | **Single global SQLite** at `~/.claude_karma/metadata.db`. No per-repo DBs. |
| 2. Schema today | 13 tables, session-centric. Has `sessions`, `subagent_invocations`. **No** `message`, `decision`, `commit`, `branch` tables. |
| 3. Indexer contract | mtime-based polling on a 300s timer. Hand-coded for `*.jsonl`. **New file types are NOT auto-picked up** — code change required. |
| 4. Migrations | Hand-rolled, idempotent, version-tracked in a `schema_version` table. No Alembic. |
| 5. Session identity | `session.uuid` (stable, comes from JSONL filename). `(repo, branch, session_uuid)` is composable from existing fields. |
| 6. Dashboard extensibility | Hand-built SvelteKit. No plugin system. ~700 LOC / 3 files for a new entity browser. |
| 7. Cross-DB queries | Already a single DB — cross-project joins are trivial `WHERE` filters. |
| 8. DB envelope | 143 MB on this machine, ~2K sessions across 52 projects. 32 indexes. Plenty of headroom. |
| 9. Retention | Forever. No GC, no TTL. Prompt history preserved even after Claude Code deletes JSONL. |
| 10. Existing decision-like concepts | None. No annotation/insight/decision tables today. |

**Bottom line for the design:** karma is a *single-DB, single-machine,
single-user* system today. That's actually friendlier to the rooms
feature than the question bundle assumed — you don't have to solve
cross-DB joins at all. The two real costs are (a) writing an indexer
shim for a new file type, and (b) building dashboard pages from scratch
(no free UI).

---

## Detailed answers

### Q1 — Scope topology

**One global SQLite DB at `~/.claude_karma/metadata.db`.** Not per-repo.

- Path resolved at `api/config.py:162-164` via
  `settings.sqlite_db_path`.
- Connection management at `api/db/connection.py:25-29, 45-83` —
  single writer, per-request reader, WAL mode.
- Project membership is a column, not a database boundary: `sessions`
  table has a `project_encoded_name` column
  (`api/db/schema.py:26`) used as the join key.
- No `ATTACH DATABASE` calls anywhere in the codebase (verified).

**Consequence for rooms:** there is *no* parent-vs-per-repo decision to
make. Rooms can live in the same DB as everything else with a
`room_id` column where it matters. The original proposal's "MVP must
choose: top-level karma-rooms.sqlite OR cross-repo aggregation layer"
is moot — pick neither.

### Q2 — Current schema

Schema version **10** (`api/db/schema.py:13`). 13 tables total.

| Table | PK | FK / Notes |
|---|---|---|
| `schema_version` | `version` | Migration tracking |
| `sessions` | `uuid` | Root entity. `project_encoded_name`, `slug`, `git_branch`, `start_time`, usage stats |
| `session_tools` | `(session_uuid, tool_name)` | FK→`sessions(uuid)` CASCADE. Aggregated counts, not per-call |
| `session_skills` | `(session_uuid, skill_name, invocation_source)` | FK→`sessions(uuid)` CASCADE |
| `session_commands` | `(session_uuid, command_name, invocation_source)` | FK→`sessions(uuid)` CASCADE |
| `subagent_invocations` | `id` AUTOINCREMENT | FK→`sessions(uuid)` CASCADE. Per-task subagent runs |
| `subagent_tools` | `(invocation_id, tool_name)` | FK→`subagent_invocations(id)` CASCADE |
| `subagent_skills` | `(invocation_id, skill_name, invocation_source)` | FK→`subagent_invocations(id)` CASCADE |
| `subagent_commands` | `(invocation_id, command_name, invocation_source)` | FK→`subagent_invocations(id)` CASCADE |
| `message_uuids` | `message_uuid` | FK→`sessions(uuid)` CASCADE. UUID→session index for chain detection |
| `session_leaf_refs` | `(session_uuid, leaf_uuid)` | FK→`sessions(uuid)` CASCADE. For compaction chains |
| `projects` | `encoded_name` | Summary derived from sessions |
| `sessions_fts` | virtual FTS5 | Full-text search on session metadata |

Plus the **sync_*** family from sync v2/v3 (teams, devices, projects,
members, rejected_folders) — not relevant to rooms but note schema
version is actually **v17 in the sync branch context** in MEMORY.md.
Confirm the branch before proposing changes.

**Concepts already present**: `session`, `subagent`, `tool` (aggregated),
`skill`, `command`.

**Concepts NOT present** (deliberately not modeled today):
- `message` — full message bodies live in JSONL, only UUID index in DB
- `tool_call` (per-invocation, with inputs/outputs)
- `commit`, `branch` (only `git_branch` denormalized on session)
- `decision`, `fact`, `annotation`, `note`, `bookmark`
- `event` (no fine-grained event log)

**Consequence for rooms:** the proposed `room`, `agent_presence`,
`message`, `citation`, `decision` tables don't collide with anything.
There's no `message` table to overlap with — karma deliberately keeps
message bodies in JSONL and only indexes UUIDs. Your `message` table
for room messages stands alone cleanly.

### Q3 — Indexer contract

**Mechanism:** mtime-based polling, NOT a file-watcher and NOT
hook-triggered.

- Startup pass: `api/main.py:76-81` runs `run_background_sync()` in
  a daemon thread.
- Periodic pass: `api/main.py:86-88` runs `run_periodic_sync()` every
  `settings.reindex_interval_seconds` (default 300s).
- Both call into `api/db/indexer.py`, which walks
  `~/.claude/projects/`, compares JSONL `mtime` against stored
  values, and upserts only changed sessions.
- Hooks (`hooks/live_session_tracker.py` etc.) write live-session
  state files but **do not trigger SQLite indexing**.
- Zero use of `fsevents`, `watchdog`, `inotify` (verified by grep).

**File patterns are hand-coded.** `indexer.py:234` literally calls
`project_dir.glob("*.jsonl")`. Subagent paths are hardcoded at
`indexer.py:329` (`{uuid}/subagents/agent-*.jsonl`). There is **no
plugin registry, no glob config, no extension point**.

**Will dropping `~/.claude/rooms/<ticket>/messages/NNN.json` get
picked up automatically?** **No.** You'd need to:
1. Add a glob in `sync_project()` (or a new `sync_rooms()`) for the
   new path pattern.
2. Write a parser analogous to `Session.from_path()`.
3. Define the new tables and an upsert path.
4. Add cleanup logic for deletions in `_cleanup_stale_sessions()`.

**Consequence for rooms:** the "drop JSON files and they magically
appear in the dashboard" assumption from the question bundle's
decision matrix doesn't hold. Plan for a karma PR that adds a rooms
indexer module — small but explicit. Polling cadence is also worth
flagging: a 300s lag between message-on-disk and message-in-dashboard
will likely feel sluggish for a coordination product. Either tighten
the timer for rooms or wire room writes through a hook that triggers
immediate indexing.

### Q4 — Migrations

**Hand-rolled, idempotent, version-tracked.** No Alembic.

- Version constant: `api/db/schema.py:13` — `SCHEMA_VERSION = 10`.
- Tracking table: `schema_version (version, applied_at)`.
- Apply path: `ensure_schema()` runs on every startup
  (`api/db/connection.py:79`), reads current version, applies
  incremental migrations v_n → v_(n+1) up to `SCHEMA_VERSION`.
- Pattern: `CREATE TABLE IF NOT EXISTS` for new tables, `ALTER TABLE
  ADD COLUMN` for extensions, all wrapped in version guards.
- Recent history (v7–v10): worktree consolidation, subagent
  skills/commands, invocation source tracking, command-trigger
  re-index.

**Consequence for rooms:** adding `room`, `agent_presence`, `message`,
`citation`, `decision` is a v10→v11 (or higher, depending on what
ships first) migration. No tooling to fight, just append a new
migration block to `ensure_schema()`. Idiomatic addition.

### Q5 — Session identity

**Stable identifier today is `session.uuid`** — directly the JSONL
filename stem (`{uuid}.jsonl`). Generated by Claude Code, not karma.
Persists across restarts because the JSONL file persists.

| Entity | Primary ID | Persistence |
|---|---|---|
| Session | `session.uuid` | Survives restarts (JSONL file) |
| Subagent | `parent_session_uuid + agent_id` | Survives restarts (subagent JSONL) |
| Live session state | `slug` | NOT unique across sessions — DON'T use as durable ID |

**To compose an `agent_id = (repo, branch, session_id)`:**
- `repo`: from `project.path` (decoded from `project_encoded_name`)
- `branch`: from `session.get_git_branches()` — returns `Set[str]`
  (`api/models/session.py:936-944`); a session can touch multiple
  branches, so pick the first or the dominant one and store it
- `session_id`: `session.uuid`

**Consequence for rooms:** identity is solid. Use `session.uuid` as
the session anchor. The composite key is yours to materialize when
joining a room — store it in `agent_presence(agent_id, repo, branch,
session_uuid, ...)` and it's stable across restarts. **Warning:**
do NOT use the `slug` as `agent_id` — slugs are reused on session
resume.

### Q6 — Dashboard extensibility

**Hand-built SvelteKit, no plugin system.**

- Navigation is hard-coded in `frontend/src/lib/components/Header.svelte:81-169`
  — every top-level page is an explicit `<a href>` tag.
- Routing is SvelteKit file-based — drop `routes/rooms/+page.svelte`
  and the route exists. No registry.
- No `frontend/src/plugins/` or `frontend/static/plugins/` directory.
  The `/plugins` and `/hooks` pages are *data views* (showing Claude
  Code's plugins/hooks), not extensibility points for the dashboard
  itself.
- Component library is mature and reusable: `PageHeader`, `StatsGrid`,
  `FilterControls`, `Pagination`, `SegmentedControl`,
  `CollapsibleGroup`, `Card`, `Badge`, chart components. No code
  duplication — composition only.

**Cost of a new `/rooms` browser page:**

| Task | LOC | Files |
|---|---|---|
| Add nav link in Header.svelte | ~8 | 1 |
| Create `routes/rooms/+page.svelte` | 600–800 | 1 |
| Create `routes/rooms/+page.server.ts` data loader | 30–50 | 1 |
| Reuse existing components | 0 | — |
| **Total new code** | **~700** | **3** |

Realistic estimate: **1–2 days** for a full-featured entity browser
with search, stats, multiple view modes — leveraging the existing
component library.

**Consequence for rooms:** the question bundle's decision matrix line
"Dashboard is plugin-extensible → ship room/decision views as plugins"
should be retired. The dashboard is hand-built. **There is no free
UI.** That said, the cost is small per-view (1–2 days each) because
the primitives are good. Bake this into the MVP scope honestly — it
is real engineering, not a freebie.

### Q7 — Cross-DB queries from dashboard

Resolved by Q1 — there is no cross-DB problem because there are no
multiple DBs. All projects live in one SQLite, joined by
`project_encoded_name`. The dashboard's `/agents`, `/skills`,
`/sessions` global views already render multi-project data via plain
`WHERE` filters or unfiltered queries.

**Consequence for rooms:** a room touching 3 repos becomes a join over
`agent_presence WHERE room_id = ?` — no `ATTACH DATABASE` gymnastics.

### Q8 — DB envelope

**On this machine right now**: 143 MB metadata.db, 2,053 sessions
across 52 projects, 12K `session_tools` rows, 4.8K
`subagent_invocations` rows.

- 32 indexes defined, strategically placed (project, start_time
  DESC, slug, mtime, subagent type/time, per-name tools/skills).
- FTS5 external-content table on sessions.
- Incremental indexing (mtime delta only) — full re-index never runs
  on every cycle.

**Headroom**: SQLite handles 100s of GB comfortably with WAL. Adding
rooms (small text bodies, modest cardinality — a few thousand
messages per active room at most) is well within envelope. The thing
to watch is the `citation` table if you index every coderoots URN
referenced in every message — that could grow fast on long-lived
rooms. A `citation_id` dedupe table or a UNIQUE constraint on
`(message_id, urn)` will keep it bounded.

### Q9 — Retention

**Data is kept forever. No GC.**

- No `archived_at`, no TTL, no soft-delete on `sessions`.
- ON DELETE CASCADE on FKs means manually deleting a session cleans
  up its children — but nothing deletes sessions automatically.
- The only "cleanup" is `~/.claude_karma/live-sessions/{slug}.json`
  files for idle live-session state (5+ min threshold) — and that's
  filesystem state, not DB rows.
- `~/.claude/history.jsonl` is karma's *anti*-deletion mechanism: it
  preserves prompts even when Claude Code deletes the source JSONL.
- No `retention_days` setting in `api/config.py`.

**Consequence for rooms:** retention is your call. Closed rooms could
stay forever (matches house style) or you could add a per-table TTL.
Since the proposal's `decision` table has `valid_until` and
`superseded_by`, the temporal model itself does the soft-invalidation
work — you probably don't need physical GC at all.

### Q10 — Existing decision/fact/annotation concepts

**None.** No `decision`, `fact`, `annotation`, `note`, `insight`,
`finding`, `bookmark`, `tag`, or `label` tables. Searched the schema
and the `api/models/` directory — not present.

The closest analog is `Task` in `api/models/task.py` (a Pydantic
model, not a DB table) which models task tracking with status and
dependencies — but that's TaskCreate/TaskUpdate tool-event
reconstruction, not user-curated annotations.

**Consequence for rooms:** the `decision` table proposal doesn't
overlap with anything. You're not reinventing — you're introducing.
Likewise `citation` is a net-new entity. Clean slate, no migrations
to thread around existing concepts.

---

## What this changes in the original "design changes if karma says…" matrix

| Original "if karma says…" branch | Reality |
|---|---|
| "Only per-repo DBs, no parent aggregate" → add karma-rooms.sqlite OR aggregation layer | **Moot.** Karma is already a single global DB. |
| "We already model `message` / `session`" → reuse | **Reuse `sessions`, NOT `message`.** Karma has `sessions` and a `message_uuids` index but no message body table. Your `message` for room-messages stands alone. |
| "Indexer is file-watcher on `.claude/`" → drop JSON, free indexing | **Wrong assumption.** Indexer is mtime-poll, hand-coded for known patterns. New file types need new code. Plan for an indexer module in the karma PR. |
| "Indexer is manual / hook-based" → register new indexer | **Closer to reality.** Add a `sync_rooms()` step alongside `sync_project()`, plus a 300s polling concern (or wire a hook for immediate indexing). |
| "Dashboard is plugin-extensible" → free UI | **Wrong.** Dashboard is hand-built, ~1–2 days per new entity browser. Component library is mature so it's not painful, but it's not free. |
| "Dashboard is hand-built" → scope minimal room view | **Correct branch.** Budget the room view as MVP scope explicitly. |

---

## Recommended next steps for the proposal

1. **§4 Architecture:** swap "pending integration contract" for: "Karma
   is a single global SQLite at `~/.claude_karma/metadata.db`
   (schema v10, hand-rolled migrations). Rooms tables land as a v11
   migration. Indexing requires a new `sync_rooms()` module — either
   on the existing 300s polling timer or hook-triggered for
   lower-latency room messages."
2. **§7 MVP boundary:** explicitly include "rooms dashboard page
   (~700 LOC, ~1–2 days)" as scope, not as a freebie. Decide whether
   the MVP also needs a `/decisions` page or whether decisions are
   surfaced inside the room view.
3. **Indexer latency call:** decide MVP polling cadence for rooms.
   300s is fine for "log of past coordination", insufficient for
   "live agent walkie-talkie". Hook-triggered indexing is the
   cleaner path if low latency matters.
4. **Karma PR sketch:** the migration is a single block in
   `ensure_schema()` (5 CREATE TABLEs + a few indexes + a version
   bump). Plus an indexer file. Plus the SvelteKit page. Three
   discrete pieces of work, each independently mergeable.
5. **Open question to flag:** rooms will produce many small JSON
   files under `~/.claude/rooms/<ticket>/messages/NNN.json`. Confirm
   with the design that messages are append-only files (not one big
   growing file) — the indexer's mtime check is per-file, so 1000
   tiny files = 1000 stat calls per poll. Manageable but worth
   knowing.

---

## Confidence

- **High confidence (verified in code):** Q1, Q2, Q3, Q4, Q5, Q6, Q7,
  Q9, Q10.
- **Medium confidence (verified on this machine, may vary):** Q8 — DB
  envelope numbers are local; other installs will differ.
