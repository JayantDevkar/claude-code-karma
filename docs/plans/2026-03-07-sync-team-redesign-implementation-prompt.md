# Implementation Prompt: Sync & Team Page Redesign

Copy the prompt below into a new Claude Code session on the `worktree-syncthing-sync-design` branch.

---

## Prompt

```
Read the design doc at docs/plans/2026-03-07-sync-team-page-redesign.md — it contains the full architecture, API specs, page wireframes, and implementation phases for splitting the sync/team UI.

Use /feature-dev to guide the implementation. Since we've already done discovery and architecture design (documented in the plan), skip to Phase 5 (Implementation) directly.

Before starting, use the Skill tool to invoke oh-my-claudecode:frontend-ui-ux — apply its design principles to all frontend components (distinctive typography, cohesive color palette, thoughtful spacing, no generic aesthetics).

## What We're Building

We're splitting the monolithic `/sync` page into three focused surfaces:

1. `/sync` — Syncthing setup wizard (steps 0-2 only) + sync engine status dashboard (no tabs)
2. `/team` — Team list with Create/Join CTAs → `/team/[name]` team detail (members, projects, join code)
3. `/projects/[slug]` — New "Team" tab showing remote sessions from teammates

Key new feature: **Join Code** — format `team_name:user_id:device_id` — enables one-paste team joining.

## Implementation Order

Execute these phases sequentially. After each phase, use oh-my-claudecode:code-review to review the changes before moving to the next.

### Phase 1: API Changes

Reference: design doc sections "API Changes" and "Join Code Mechanism"

Files to modify:
- `cli/karma/syncthing.py` — Add `get_pending_devices()` method to `SyncthingClient`
- `api/services/syncthing_proxy.py` — Add `get_pending_devices()` to `SyncthingProxy`
- `api/routers/sync_status.py` — Add these endpoints:
  - `POST /sync/teams/join` — Parse 3-part join code, create team, add leader, pair Syncthing, accept pending folders, return joiner's own code
  - `GET /sync/teams/{name}/join-code` — Generate join code from config
  - `GET /sync/pending-devices` — List unknown pending Syncthing devices
  - Modify `GET /sync/status` — Add `device_id` field to response
- `api/routers/projects.py` (or new file) — Add `GET /projects/{slug}/remote-sessions` — Remote sessions grouped by user

Key implementation details from the design doc:
- Join code format: `team_name:user_id:device_id` — split on first two colons
- `user_id` becomes the member name (critical: filesystem inbox path must match)
- Join endpoint should auto-accept pending folders and return the joiner's own code
- Pending devices endpoint filters out already-known device IDs from `get_known_devices()`
- Remote sessions endpoint skips local user's outbox, groups sessions by remote user

After implementing, run: `cd api && pytest` to verify nothing breaks.

### Phase 2: Frontend — `/team` Page Rewrite

Reference: design doc section "Page Designs > /team"

Delete old route files:
- `frontend/src/routes/team/[user_id]/+page.svelte`
- `frontend/src/routes/team/[user_id]/+page.server.ts`

Rewrite existing files:
- `frontend/src/routes/team/+page.server.ts` — Fetch `GET /sync/teams` + `GET /sync/status` (need `configured` and `device_id`)
- `frontend/src/routes/team/+page.svelte` — Three states:
  1. Sync not configured → CTA to `/sync`
  2. No teams → Create/Join CTAs
  3. Has teams → Grid of `TeamCard` components linking to `/team/[name]`

Create new components:
- `frontend/src/lib/components/team/TeamCard.svelte` — Card with name, backend, member count, project count
- `frontend/src/lib/components/team/CreateTeamDialog.svelte` — Team name input, calls `POST /sync/teams`
- `frontend/src/lib/components/team/JoinTeamDialog.svelte` — Paste join code with **live parsing feedback** (show detected team/leader/device as user types). Calls `POST /sync/teams/join`. On success, show `JoinSuccessCard`.
- `frontend/src/lib/components/team/JoinSuccessCard.svelte` — Shows "Joined acme!" + "Share YOUR code back" with copy button for the joiner's own code

### Phase 3: Frontend — `/team/[name]` Team Detail

Reference: design doc section "Page Designs > /team/[name]"

Create new route:
- `frontend/src/routes/team/[name]/+page.server.ts` — Fetch in parallel: `GET /sync/teams` (find this team), `GET /sync/devices` (connection status), `GET /sync/teams/{name}/join-code`, `GET /sync/pending-devices`, `GET /projects` (for add project dialog)
- `frontend/src/routes/team/[name]/+page.svelte` — Sections: Join Code, Pending Devices, Members, Shared Projects

Create components:
- `frontend/src/lib/components/team/JoinCodeCard.svelte` — Prominent code display with copy button
- `frontend/src/lib/components/team/PendingDeviceCard.svelte` — Shows device ID, name input field, "Accept as Member" button. Calls `POST /sync/teams/{name}/members` then pairs.
- `frontend/src/lib/components/team/TeamMemberCard.svelte` — Name, truncated device ID, online/offline badge (from Syncthing connections), last seen, remove button with confirm
- `frontend/src/lib/components/team/AddMemberDialog.svelte` — Dual input: paste join code (auto-parses name + device) OR manual name + device ID fields. Code paste auto-fills the manual fields.
- `frontend/src/lib/components/team/AddProjectDialog.svelte` — Checkbox list of projects from `GET /projects`, excludes already-shared ones. Calls `POST /sync/teams/{name}/projects` for each selected.

Poll for pending devices every 10 seconds on this page. Poll for device connection status every 10 seconds.

### Phase 4: Frontend — `/sync` Page Simplification

Reference: design doc section "Page Designs > /sync"

Modify `frontend/src/lib/components/sync/SetupWizard.svelte`:
- Remove step 3 entirely (create/join/solo). The wizard is now steps 0-2 only.
- After successful init in step 2, redirect to `/team` using `goto('/team')`

Modify `frontend/src/routes/sync/+page.server.ts`:
- Remove pending folders fetch (handled inline now)
- Keep: detect, status, watch status

Modify `frontend/src/routes/sync/+page.svelte`:
- Remove imports: TeamTab, ProjectsTab, TeamSelector, ActivityTab
- Remove the entire `<Tabs>` structure
- When `syncStatus.configured === true`, render a single-page dashboard (no tabs):
  - **Sync Engine** card: Syncthing status, watcher status with start/stop, device ID with copy, machine name
  - **Sync Health** stats row: projects synced, sessions packaged, sessions received, members online (aggregate across all teams)
  - **Per-Project Sync Status** list: read-only, from `GET /sync/teams/{name}/project-status` (for the first/only team, or aggregate). Show project name, status badge, local/packaged counts.
  - **Pending Actions** section (only if pending folders exist): from `GET /sync/pending`
  - **Recent Activity** section: from `GET /sync/activity?limit=10`
  - **Danger Zone**: Reset Sync Setup button

### Phase 5: Frontend — Project Team Tab

Reference: design doc section "Page Designs > /projects/[slug] Team Tab"

Create component:
- `frontend/src/lib/components/project/RemoteSessionsTab.svelte`
  - Props: `projectSlug: string`, `active: boolean`
  - Fetches `GET /projects/{slug}/remote-sessions` when active
  - Groups sessions by user, shows user header (name, session count, machine, last synced)
  - Session rows link to `/projects/{slug}/{uuid}` (existing session viewer handles remote sessions)
  - Empty state: "No team sessions yet" with link to `/team`

Modify `frontend/src/routes/projects/[project_slug]/+page.svelte`:
- Add import for `RemoteSessionsTab`
- Add `<TabsTrigger value="team" icon={Users}>Team</TabsTrigger>` after the Analytics tab (before Archived)
- Add `<TabsContent value="team">` with `<RemoteSessionsTab>`
- Conditionally show the Team tab only if remote session count > 0

Modify `frontend/src/routes/projects/[project_slug]/+page.server.ts`:
- Add a lightweight fetch to check if remote sessions exist: `GET /projects/{slug}/remote-sessions` and pass the count

### Phase 6: Cleanup

Delete these files:
- `frontend/src/lib/components/sync/TeamTab.svelte`
- `frontend/src/lib/components/sync/ProjectsTab.svelte`
- `frontend/src/lib/components/sync/TeamSelector.svelte`
- `frontend/src/lib/components/sync/MembersTab.svelte` (if it exists)

Modify `frontend/src/lib/components/Header.svelte`:
- Change "Team" to "Teams" in both desktop and mobile nav (lines 183 and 348)

Update `frontend/src/lib/api-types.ts`:
- Add any new types needed (JoinTeamResponse, PendingDevice, etc.)
- Remove unused types if any

After all phases, run:
- `cd api && pytest` — API tests pass
- `cd frontend && npm run check` — No TypeScript errors
- `cd frontend && npm run build` — Builds successfully

## Agent Guidelines

IMPORTANT: Give agents high-level requirements and pseudo-code instructions rather than
copy-pasting exact code from the plan. The agents should figure out the implementation
themselves based on the requirements, existing patterns in the codebase, and the project
conventions. The design doc is a WHAT and WHY reference — agents decide HOW by reading
existing code patterns (e.g., look at how TeamTab.svelte works before building the new
team detail page, look at existing routers before adding new endpoints).

## Skills & Agents to Use

- **oh-my-claudecode:frontend-ui-ux** — Invoke at the start. Apply to ALL frontend components. No generic Inter/Roboto fonts. Use the existing design tokens from app.css. Create distinctive, polished UI.
- **oh-my-claudecode:code-review** — After each phase, review the changes for quality, bugs, and convention adherence.
- **oh-my-claudecode:build-fix** — If TypeScript or build errors occur after any phase, use this to fix them quickly.
- **superpowers:verification-before-completion** — Before claiming any phase is complete, run the verification commands (pytest, npm run check, npm run build).

## Important Conventions (from CLAUDE.md)

- **Svelte 5 runes**: Use `$state()`, `$derived()`, `$effect()`, `$props()` — NOT Svelte 4 stores
- **API calls in components**: Use raw `fetch(${API_BASE}/...)` with `API_BASE` from `$lib/config`
- **Server load functions**: Use `safeFetch()` from `$lib/utils/api-fetch.ts`
- **Design tokens**: Use CSS custom properties from `app.css` (`--bg-base`, `--text-primary`, `--accent`, `--border`, etc.)
- **Icons**: Use `lucide-svelte`
- **Input validation in API**: Use regex patterns (`ALLOWED_PROJECT_NAME`, `ALLOWED_DEVICE_ID`) and `validate_*()` functions
- **DB operations**: Use `sync_queries.py` functions with `_get_sync_conn()`
- **Syncthing calls**: Wrap with `await run_sync(proxy.method)` for async
```

---

## How to Use This Prompt

1. Open a new Claude Code session on the `worktree-syncthing-sync-design` branch
2. Copy everything between the ``` markers above
3. Paste as your first message
4. Claude will read the design doc and begin implementation phase by phase

## Alternative: Phase-by-Phase Execution

If you prefer more control, you can split this into separate sessions per phase. Copy just one phase section at a time, prefixed with:

```
Read docs/plans/2026-03-07-sync-team-page-redesign.md for full context. Implement Phase N:
```

## Alternative: Parallel Execution with Ultrapilot

For faster execution, you can use `/ultrapilot` which parallelizes work across multiple agents with file ownership:

```
Read docs/plans/2026-03-07-sync-team-page-redesign.md

Use /ultrapilot to implement the sync/team page redesign. Partition work as:

Agent 1 (API): Phase 1 — all files under api/ and cli/
Agent 2 (Team Frontend): Phases 2-3 — all files under frontend/src/routes/team/ and frontend/src/lib/components/team/
Agent 3 (Sync + Project Frontend): Phases 4-5 — frontend/src/routes/sync/, frontend/src/routes/projects/, frontend/src/lib/components/sync/, frontend/src/lib/components/project/
Agent 4 (Cleanup): Phase 6 — Header.svelte, api-types.ts, delete deprecated files

Note: Agent 2 and 3 depend on Agent 1 (API endpoints must exist first).

IMPORTANT: Give agents high-level requirements, not exact code. They should read existing
codebase patterns and figure out implementation details themselves. The design doc describes
WHAT to build — agents decide HOW by studying existing code conventions.
```
