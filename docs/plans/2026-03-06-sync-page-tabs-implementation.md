# Sync Page Tabs Redesign — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restructure the sync page's 4 tabs (Overview, Members, Projects, Activity) to eliminate information duplication, consolidate team management, and translate raw Syncthing events into session-meaningful activity.

**Architecture:** Rename Members→Team tab and move team-level config into it. Strip Overview down to health-check essentials. Refocus Activity on human-readable session events. Keep Projects mostly as-is but ensure sync health data is fully surfaced. No backend changes needed — all APIs already exist.

**Tech Stack:** Svelte 5 (runes), Tailwind CSS 4, lucide-svelte icons, existing API endpoints

---

### Task 1: Restructure OverviewTab — strip it down

**Files:**
- Modify: `frontend/src/lib/components/sync/OverviewTab.svelte`
- Modify: `frontend/src/routes/sync/+page.svelte` (tab label)

**Context:** The current OverviewTab has 6 sections. We need to remove: team management card (moving to Team tab), getting started guide (moving to Team tab), and "Your Sync ID" from machine details (moving to Team tab). We also refocus the stats row.

**Step 1: Update tab label in +page.svelte**

In `frontend/src/routes/sync/+page.svelte`, change the "members" tab trigger:

```svelte
<!-- Line ~148: Change "Members" to "Team" -->
<TabsTrigger value="team" icon={Users}>Team</TabsTrigger>
```

Also update the TabsContent value from "members" to "team":

```svelte
<TabsContent value="team">
    <TeamTab detect={syncDetect} active={activeTab === 'team'} teamName={activeTeamName} onteamchange={refreshData} />
</TabsContent>
```

Update the import: rename `MembersTab` → `TeamTab` and update the import path to `./TeamTab.svelte`.

Update the default tab in the `handleCreateTeam` function — it currently sets `activeTab = 'overview'`; leave as-is since team creation still happens via TeamSelector.

**Step 2: Strip OverviewTab**

Remove from `OverviewTab.svelte`:

1. **Team Management section** (lines ~290-336): The entire `<div>` with heading "Team" that shows active team display and delete team button. This moves to TeamTab.

2. **Getting Started section** (lines ~371-397): The entire `{#if showGettingStarted}` block with the numbered steps. This moves to TeamTab.

3. **Sync ID from Machine Details** (lines ~420-441): Remove the `{#if detect?.device_id}` block showing "Sync ID" with copy button inside Machine Details. This moves to TeamTab. Keep the machine details card but without the Sync ID row.

4. **Remove related state**: `deleteConfirm`, `deletingTeam`, `deleteTeam()`, `showGettingStarted` derived, and the `copiedDeviceId`/`copyDeviceId` function (these move to TeamTab).

**Step 3: Refocus stats row**

Change the 4 stat cards from:
- Members / Projects / Synced In / Synced Out

To:
- Members Online (e.g., "2/3") / Projects Syncing / Sessions Shared / Sessions Received

This requires fetching device connection data. Add to `loadStats()`:

```typescript
// Fetch devices to count connected members
const devicesRes = await fetch(`${API_BASE}/sync/devices`).catch(() => null);
let connectedCount = 0;
let totalDeviceCount = 0;
if (devicesRes?.ok) {
    const devData = await devicesRes.json();
    const devices = devData.devices ?? [];
    // Exclude self device
    const remoteDevices = devices.filter((d: { is_self?: boolean }) => !d.is_self);
    totalDeviceCount = remoteDevices.length;
    connectedCount = remoteDevices.filter((d: { connected?: boolean }) => d.connected).length;
}

// Fetch project status for session counts
let sessionsShared = 0;
let sessionsReceived = 0;
if (teamName) {
    const statusRes = await fetch(
        `${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/project-status`
    ).catch(() => null);
    if (statusRes?.ok) {
        const statusData = await statusRes.json();
        const projects = statusData.projects ?? [];
        for (const p of projects) {
            sessionsShared += p.packaged_count ?? 0;
            const received = p.received_counts ?? {};
            for (const count of Object.values(received)) {
                sessionsReceived += (count as number) ?? 0;
            }
        }
    }
}
```

Update stat card state variables:

```typescript
let connectedMembers = $state(0);
let totalMembers = $state(0);
let sessionsSharedCount = $state(0);
let sessionsReceivedCount = $state(0);
```

Update the stat cards markup:

```svelte
<!-- Card 1: Members Online -->
<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-4 text-center">
    <Users size={16} class="mx-auto text-[var(--text-muted)] mb-1.5" />
    <p class="text-lg font-semibold text-[var(--text-primary)]">
        {connectedMembers}/{totalMembers}
    </p>
    <p class="text-[11px] text-[var(--text-muted)]">Members Online</p>
</div>

<!-- Card 2: Projects Syncing -->
<div class="...">
    <FolderGit2 size={16} class="mx-auto text-[var(--text-muted)] mb-1.5" />
    <p class="text-lg font-semibold text-[var(--text-primary)]">{projectCount}</p>
    <p class="text-[11px] text-[var(--text-muted)]">Projects</p>
</div>

<!-- Card 3: Sessions Shared -->
<div class="...">
    <ArrowUp size={16} class="mx-auto text-[var(--accent)] mb-1.5" />
    <p class="text-lg font-semibold text-[var(--text-primary)]">{sessionsSharedCount}</p>
    <p class="text-[11px] text-[var(--text-muted)]">Sessions Shared</p>
</div>

<!-- Card 4: Sessions Received -->
<div class="...">
    <ArrowDown size={16} class="mx-auto text-[var(--info)] mb-1.5" />
    <p class="text-lg font-semibold text-[var(--text-primary)]">{sessionsReceivedCount}</p>
    <p class="text-[11px] text-[var(--text-muted)]">Sessions Received</p>
</div>
```

**Step 4: Conditionally render Pending Actions**

Change the Pending Actions section so it only renders when there are pending items. Replace:

```svelte
<!-- Current: always renders with empty state -->
<div class="rounded-[var(--radius-lg)] border ...">
```

With:

```svelte
{#if !pendingLoading && pendingFolders.length > 0}
    <div class="rounded-[var(--radius-lg)] border ...">
        <!-- Keep header + list, remove the empty state block -->
    </div>
{/if}
```

Remove the `{:else if pendingFolders.length === 0}` empty state block entirely (the green checkmark "No pending actions" section).

**Step 5: Verify and commit**

Run: `cd frontend && npm run check`
Expected: No type errors

```bash
git add frontend/src/lib/components/sync/OverviewTab.svelte frontend/src/routes/sync/+page.svelte
git commit -m "refactor: strip Overview tab — move team mgmt, sync ID, getting started to Team tab"
```

---

### Task 2: Create TeamTab component (rename from MembersTab)

**Files:**
- Rename: `frontend/src/lib/components/sync/MembersTab.svelte` → `frontend/src/lib/components/sync/TeamTab.svelte`
- Modify: `frontend/src/routes/sync/+page.svelte` (import)

**Context:** The current MembersTab already has member list, add member form, and "Your Sync ID". We need to add: team header card with delete action, and getting started guide (moved from Overview).

**Step 1: Rename the file**

```bash
cd frontend/src/lib/components/sync
mv MembersTab.svelte TeamTab.svelte
```

**Step 2: Update import in +page.svelte**

```typescript
// Change:
import MembersTab from '$lib/components/sync/MembersTab.svelte';
// To:
import TeamTab from '$lib/components/sync/TeamTab.svelte';
```

**Step 3: Add `onteamchange` prop to TeamTab**

Add to props:

```typescript
let {
    detect,
    active = false,
    teamName = null,
    onteamchange   // NEW
}: {
    detect: SyncDetect | null;
    active?: boolean;
    teamName: string | null;
    onteamchange?: () => void;  // NEW
} = $props();
```

**Step 4: Add Team Header Card with delete action**

Add at the top of the `{:else}` block (after `{#if !teamName}` ... `{:else}`), before "Your Sync ID":

```svelte
<!-- Team Header -->
<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)] p-4">
    <div class="flex items-center justify-between">
        <div class="flex items-center gap-2 min-w-0">
            <Users size={16} class="shrink-0 text-[var(--accent)]" />
            <div class="min-w-0">
                <p class="text-sm font-semibold text-[var(--text-primary)] truncate">{teamName}</p>
                <p class="text-xs text-[var(--text-muted)]">Syncthing team</p>
            </div>
        </div>
        {#if deleteConfirm}
            <div class="flex items-center gap-1.5 bg-[var(--bg-base)] rounded-lg px-2.5 py-1.5 border border-[var(--border)] shadow-md">
                <span class="text-xs text-[var(--text-secondary)]">Delete team?</span>
                <button
                    onclick={deleteTeam}
                    disabled={deletingTeam}
                    class="px-2.5 py-1 text-xs font-medium rounded-md bg-[var(--error)] text-white hover:opacity-90 transition-opacity disabled:opacity-50"
                >
                    {deletingTeam ? '...' : 'Yes'}
                </button>
                <button
                    onclick={() => (deleteConfirm = false)}
                    class="px-2.5 py-1 text-xs font-medium rounded-md border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
                >
                    No
                </button>
            </div>
        {:else}
            <button
                onclick={() => (deleteConfirm = true)}
                aria-label="Delete team"
                class="shrink-0 flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-[var(--radius)] border border-[var(--error)]/30 text-[var(--error)] hover:bg-[var(--error-subtle)] transition-colors"
            >
                <Trash2 size={12} />
                Delete
            </button>
        {/if}
    </div>
</div>
```

Add the state and function for team deletion (moved from OverviewTab):

```typescript
let deletingTeam = $state(false);
let deleteConfirm = $state(false);

async function deleteTeam() {
    if (!teamName) return;
    deletingTeam = true;
    try {
        const res = await fetch(`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}`, {
            method: 'DELETE'
        });
        if (res.ok) {
            deleteConfirm = false;
            showFlash(`Team "${teamName}" deleted`);
            onteamchange?.();
        }
    } catch {
        // ignore
    } finally {
        deletingTeam = false;
    }
}
```

Add the `Trash2` import from `lucide-svelte`.

**Step 5: Add Getting Started guide for empty team**

After the member list empty state (`{:else if members.length === 0}`), add a getting started section:

```svelte
{:else if members.length === 0}
    <!-- Empty state -->
    <div class="py-10 flex flex-col items-center gap-3 text-center border border-dashed border-[var(--border)] rounded-[var(--radius-lg)]">
        <Users size={28} class="text-[var(--text-muted)]" />
        <p class="text-sm font-medium text-[var(--text-secondary)]">No team members yet</p>
        <p class="text-xs text-[var(--text-muted)] max-w-[280px]">
            Add a teammate below using their Sync ID, or share yours so they can add you.
        </p>
    </div>

    <!-- Getting Started -->
    <div class="rounded-[var(--radius-lg)] border border-dashed border-[var(--accent)]/30 bg-[var(--accent)]/5 p-5 space-y-3">
        <div class="flex items-center gap-2">
            <Sparkles size={14} class="text-[var(--accent)]" />
            <h3 class="text-sm font-semibold text-[var(--text-primary)]">Getting Started</h3>
        </div>
        <ol class="space-y-2 ml-1">
            <li class="flex items-start gap-2.5">
                <span class="shrink-0 w-5 h-5 rounded-full bg-[var(--accent)]/10 text-[var(--accent)] text-xs font-semibold flex items-center justify-center mt-0.5">1</span>
                <div>
                    <p class="text-sm font-medium text-[var(--text-primary)]">Add a teammate</p>
                    <p class="text-xs text-[var(--text-muted)]">Paste their Sync ID in the form below</p>
                </div>
            </li>
            <li class="flex items-start gap-2.5">
                <span class="shrink-0 w-5 h-5 rounded-full bg-[var(--accent)]/10 text-[var(--accent)] text-xs font-semibold flex items-center justify-center mt-0.5">2</span>
                <div>
                    <p class="text-sm font-medium text-[var(--text-primary)]">Enable project sync</p>
                    <p class="text-xs text-[var(--text-muted)]">Switch to the Projects tab to choose which projects to sync</p>
                </div>
            </li>
            <li class="flex items-start gap-2.5">
                <span class="shrink-0 w-5 h-5 rounded-full bg-[var(--accent)]/10 text-[var(--accent)] text-xs font-semibold flex items-center justify-center mt-0.5">3</span>
                <div>
                    <p class="text-sm font-medium text-[var(--text-primary)]">Start the sync engine</p>
                    <p class="text-xs text-[var(--text-muted)]">Go to Overview and click Start to begin watching for changes</p>
                </div>
            </li>
        </ol>
    </div>
```

Add the `Sparkles` import from `lucide-svelte`.

**Step 6: Verify and commit**

Run: `cd frontend && npm run check`
Expected: No type errors

```bash
git add frontend/src/lib/components/sync/TeamTab.svelte frontend/src/routes/sync/+page.svelte
git rm frontend/src/lib/components/sync/MembersTab.svelte
git commit -m "refactor: rename MembersTab → TeamTab, add team header card + getting started guide"
```

---

### Task 3: Enhance ProjectsTab — surface full sync health

**Files:**
- Modify: `frontend/src/lib/components/sync/ProjectRow.svelte`

**Context:** ProjectRow already has an expanded view with `projectStatus` data (local_count, packaged_count, received_counts, gap). But the collapsed row only shows session count and a badge. We need to surface the gap indicator in the collapsed view so users don't have to expand every row.

**Step 1: Add gap indicator to collapsed row**

In `ProjectRow.svelte`, inside the collapsed row's right-side div (after the session count span, around line ~165), add:

```svelte
<!-- Gap indicator (visible without expanding) -->
{#if projectStatus && project.synced}
    {#if projectStatus.gap > 0}
        <span class="text-xs font-medium text-[var(--warning)]">
            {projectStatus.gap} behind
        </span>
    {:else if projectStatus.packaged_count > 0}
        <span class="text-xs text-[var(--success)]">up to date</span>
    {/if}
{/if}
```

**Step 2: Show received session totals in collapsed view**

After the gap indicator, add a received count summary:

```svelte
{#if projectStatus && project.synced}
    {@const totalReceived = Object.values(projectStatus.received_counts).reduce((a, b) => a + b, 0)}
    {#if totalReceived > 0}
        <span class="text-xs text-[var(--text-muted)] hidden sm:block">
            {totalReceived} received
        </span>
    {/if}
{/if}
```

**Step 3: Verify and commit**

Run: `cd frontend && npm run check`
Expected: No type errors

```bash
git add frontend/src/lib/components/sync/ProjectRow.svelte
git commit -m "feat: show sync gap + received count in collapsed project row"
```

---

### Task 4: Refocus ActivityTab — human-readable session events

**Files:**
- Modify: `frontend/src/lib/components/sync/ActivityTab.svelte`

**Context:** Currently shows raw Syncthing events (FolderCompletion, StateChanged, etc.) and a full bandwidth chart. We refocus on session-meaningful descriptions, compact bandwidth display, and collapsible folder details.

**Step 1: Replace bandwidth chart with compact status bar**

Replace the bandwidth section (the `<div>` containing `<BandwidthChart>`) with a compact inline display:

```svelte
<!-- Compact bandwidth status -->
<div class="flex items-center justify-between px-4 py-3 rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)]">
    <span class="text-xs font-medium text-[var(--text-secondary)]">Transfer Rate</span>
    <div class="flex items-center gap-4 text-xs font-mono text-[var(--text-secondary)]">
        <span class="flex items-center gap-1">
            <ArrowUp size={11} class="text-[var(--accent)]" />
            {formatBytesRate(uploadRate)}
        </span>
        <span class="flex items-center gap-1">
            <ArrowDown size={11} class="text-[var(--info)]" />
            {formatBytesRate(downloadRate)}
        </span>
    </div>
</div>
```

Remove the `BandwidthChart` import and the `uploadHistory`, `downloadHistory`, `labels`, `pushHistory()`, `timeLabel()` state/functions since we no longer need the chart.

Simplify `fetchActivity` to no longer call `pushHistory`:

```typescript
// Remove: pushHistory(uploadRate, downloadRate);
// Just assign the rates directly
uploadRate = data.upload_rate ?? 0;
downloadRate = data.download_rate ?? 0;
```

**Step 2: Translate events to session-meaningful descriptions**

Replace the `formatEvent` function with session-focused translations:

```typescript
function formatEvent(event: SyncEvent): { title: string; detail: string; dotColor: string } {
    const folder = (event.data?.folder as string) || '';
    const device = (event.data?.device as string) || (event.data?.id as string) || '';
    const folderName = resolveFolderName(folder);
    const deviceName = resolveDeviceName(device);

    switch (event.type) {
        case 'ItemFinished': {
            const item = (event.data?.item as string) || '';
            const isSession = item.endsWith('.jsonl');
            const isManifest = item === 'manifest.json';
            if (isSession) {
                return {
                    title: `Session synced`,
                    detail: `${folderName} — ${item.replace('.jsonl', '').slice(0, 8)}...`,
                    dotColor: 'bg-[var(--success)]'
                };
            }
            if (isManifest) {
                return {
                    title: 'Sync manifest updated',
                    detail: folderName,
                    dotColor: 'bg-[var(--success)]'
                };
            }
            return {
                title: 'File synced',
                detail: `${folderName} — ${item}`,
                dotColor: 'bg-[var(--success)]'
            };
        }
        case 'DeviceConnected':
            return {
                title: `${deviceName || 'Teammate'} connected`,
                detail: 'Ready to sync sessions',
                dotColor: 'bg-[var(--success)]'
            };
        case 'DeviceDisconnected':
            return {
                title: `${deviceName || 'Teammate'} went offline`,
                detail: '',
                dotColor: 'bg-[var(--text-muted)]'
            };
        case 'FolderCompletion': {
            const pct = (event.data?.completion as number) ?? 0;
            if (pct >= 100) {
                return {
                    title: 'All sessions up to date',
                    detail: folderName,
                    dotColor: 'bg-[var(--success)]'
                };
            }
            return {
                title: `Syncing sessions — ${pct}%`,
                detail: folderName,
                dotColor: 'bg-[var(--info)]'
            };
        }
        case 'FolderSummary':
            return {
                title: 'Scan completed',
                detail: folderName,
                dotColor: 'bg-[var(--text-muted)]'
            };
        case 'StateChanged': {
            const to = (event.data?.to as string) || '';
            if (to === 'idle') {
                return {
                    title: 'Sync completed',
                    detail: folderName,
                    dotColor: 'bg-[var(--success)]'
                };
            }
            if (to === 'syncing') {
                return {
                    title: 'Syncing sessions...',
                    detail: folderName,
                    dotColor: 'bg-[var(--info)]'
                };
            }
            if (to === 'scanning') {
                return {
                    title: 'Scanning for changes...',
                    detail: folderName,
                    dotColor: 'bg-[var(--info)]'
                };
            }
            return {
                title: `State: ${to}`,
                detail: folderName,
                dotColor: 'bg-[var(--text-muted)]'
            };
        }
        case 'FolderErrors':
            return {
                title: 'Sync error',
                detail: ((event.data?.errors as Array<{ error: string }>) || [])[0]?.error || 'Unknown error',
                dotColor: 'bg-[var(--error)]'
            };
        default:
            return {
                title: event.type.replace(/([A-Z])/g, ' $1').trim(),
                detail: deviceName || folderName || '',
                dotColor: 'bg-[var(--text-muted)]'
            };
    }
}
```

**Step 3: Make folder stats collapsible**

Wrap the "Synced Folders" section in a collapsible toggle:

```svelte
{#if folderStats.length > 0}
    <div class="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)]">
        <button
            onclick={() => (showFolderDetails = !showFolderDetails)}
            class="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-[var(--bg-muted)] transition-colors"
        >
            <h3 class="text-sm font-medium text-[var(--text-primary)]">Folder Details</h3>
            <div class="flex items-center gap-2">
                <span class="text-xs text-[var(--text-muted)]">{folderStats.length} folders</span>
                {#if showFolderDetails}
                    <ChevronDown size={14} class="text-[var(--text-muted)]" />
                {:else}
                    <ChevronRight size={14} class="text-[var(--text-muted)]" />
                {/if}
            </div>
        </button>
        {#if showFolderDetails}
            <div class="px-4 border-t border-[var(--border-subtle)] divide-y divide-[var(--border-subtle)]">
                <!-- existing folder stats rows -->
            </div>
        {/if}
    </div>
{/if}
```

Add state:

```typescript
let showFolderDetails = $state(false);
```

Add `ChevronDown`, `ChevronRight` imports from `lucide-svelte`.

Remove the `syncedUpTotal` and `syncedDownTotal` derived values and their footer display (these were byproducts of the old bandwidth section).

**Step 4: Verify and commit**

Run: `cd frontend && npm run check`
Expected: No type errors

```bash
git add frontend/src/lib/components/sync/ActivityTab.svelte
git commit -m "refactor: refocus Activity tab — session-level events, compact bandwidth, collapsible folders"
```

---

### Task 5: Clean up unused imports and files

**Files:**
- Check: `frontend/src/lib/components/sync/BandwidthChart.svelte` — verify no other component imports it
- Modify: `frontend/src/routes/sync/+page.svelte` — verify all imports are correct after renaming

**Step 1: Check if BandwidthChart is imported anywhere else**

Run: `cd frontend && grep -r "BandwidthChart" src/`

If only ActivityTab imported it (which we removed in Task 4), the file can be kept for future use but is no longer imported.

**Step 2: Verify page.svelte imports**

Ensure `+page.svelte` has:
```typescript
import TeamTab from '$lib/components/sync/TeamTab.svelte';
// NOT: import MembersTab from ...
```

And the TabsContent for "team" uses `<TeamTab ... />`.

**Step 3: Run full type check and dev server**

```bash
cd frontend && npm run check
cd frontend && npm run dev  # verify in browser
```

**Step 4: Commit cleanup**

```bash
git add -A frontend/src/
git commit -m "chore: clean up imports after sync tab redesign"
```

---

### Task 6: Pass server-loaded data through to tabs

**Files:**
- Modify: `frontend/src/routes/sync/+page.svelte`
- Modify: `frontend/src/lib/components/sync/OverviewTab.svelte`

**Context:** The `+page.server.ts` already fetches `watchStatus` and `pending` data on server load, but the current `+page.svelte` doesn't pass them to OverviewTab — instead, OverviewTab re-fetches them client-side. We should pass them as initial values to avoid duplicate fetches on load.

**Step 1: Pass server data to OverviewTab**

In `+page.svelte`, update the OverviewTab usage:

```svelte
<OverviewTab
    detect={syncDetect}
    status={syncStatus}
    active={activeTab === 'overview'}
    teamName={activeTeamName}
    onteamchange={refreshData}
    initialWatchStatus={data.watchStatus}
    initialPending={data.pending}
/>
```

**Step 2: Accept initial data in OverviewTab**

Add to OverviewTab props:

```typescript
let {
    detect = null,
    status = null,
    active = false,
    teamName = null,
    onteamchange,
    initialWatchStatus = null,   // NEW
    initialPending = []          // NEW
}: {
    // ... existing types ...
    initialWatchStatus?: SyncWatchStatus | null;
    initialPending?: SyncPendingFolder[];
} = $props();
```

Use them as initial state:

```typescript
let watchStatus = $state<SyncWatchStatus | null>(initialWatchStatus ?? null);
let pendingFolders = $state<SyncPendingFolder[]>(initialPending ?? []);
let watchLoading = $state(initialWatchStatus === null);
let pendingLoading = $state(initialPending.length === 0 && initialWatchStatus === null);
```

**Step 3: Verify and commit**

Run: `cd frontend && npm run check`

```bash
git add frontend/src/routes/sync/+page.svelte frontend/src/lib/components/sync/OverviewTab.svelte
git commit -m "perf: pass server-loaded watch/pending data to OverviewTab, avoid duplicate fetches"
```

---

### Task 7: Final integration test

**Step 1: Manual verification checklist**

Start the dev servers:
```bash
cd api && uvicorn main:app --reload --port 8000 &
cd frontend && npm run dev
```

Open `http://localhost:5173/sync` and verify:

1. **Overview tab**: Sync engine banner, 4 refocused stats (members online, projects, sessions shared, sessions received), pending actions only when > 0, machine details without Sync ID
2. **Team tab**: Team header with delete, Your Sync ID with copy, member list with device cards, add member form, getting started guide when empty
3. **Projects tab**: Project list with gap indicator visible in collapsed rows, received count in collapsed rows
4. **Activity tab**: Compact bandwidth bar (no chart), session-meaningful event descriptions, collapsible folder details
5. **Tab switching**: URL updates with `?tab=team`, `?tab=projects` etc.
6. **No duplication**: Sync ID only in Team tab. Member count only in TeamSelector + Overview stats. Delete team only in Team tab.

**Step 2: Type check**

```bash
cd frontend && npm run check
```

**Step 3: Final commit (if any fixes needed)**

```bash
git add -A frontend/src/
git commit -m "fix: sync tab integration fixes"
```
