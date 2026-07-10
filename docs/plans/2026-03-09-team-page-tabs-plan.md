# Team Detail Page Tabs Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Convert the flat-section team detail page into a tabbed dashboard with Overview, Members, Projects, and Activity tabs.

**Architecture:** Wrap existing page content in `bits-ui` Tabs (same pattern as project detail page). Extract each section into its own tab component. Add a new API endpoint for session stats per member over time. Expand the team color palette from 8 to 16 colors.

**Tech Stack:** SvelteKit 2, Svelte 5 runes, bits-ui Tabs, Chart.js 4, Tailwind CSS 4, FastAPI, SQLite

---

### Task 1: Expand Team Color Palette (8 → 16)

**Files:**
- Modify: `frontend/src/app.css` (dark theme lines ~160-175, light theme lines ~363-378)
- Modify: `frontend/src/lib/utils.ts` (lines ~690-752)

**Step 1: Add CSS custom properties for new colors (dark theme)**

In `frontend/src/app.css`, after the existing 8 `--team-*` vars in the dark theme section, add:

```css
--team-sky: #38bdf8;
--team-sky-subtle: rgba(56, 189, 248, 0.1);
--team-violet: #8b5cf6;
--team-violet-subtle: rgba(139, 92, 246, 0.1);
--team-emerald: #34d399;
--team-emerald-subtle: rgba(52, 211, 153, 0.1);
--team-orange: #fb923c;
--team-orange-subtle: rgba(251, 146, 60, 0.1);
--team-fuchsia: #d946ef;
--team-fuchsia-subtle: rgba(217, 70, 239, 0.1);
--team-slate: #94a3b8;
--team-slate-subtle: rgba(148, 163, 184, 0.1);
--team-gold: #facc15;
--team-gold-subtle: rgba(250, 204, 21, 0.1);
--team-ruby: #e11d48;
--team-ruby-subtle: rgba(225, 29, 72, 0.1);
```

**Step 2: Add CSS custom properties for new colors (light theme)**

In the light theme section, add matching light-mode variants:

```css
--team-sky: #0ea5e9;
--team-sky-subtle: rgba(14, 165, 233, 0.15);
--team-violet: #7c3aed;
--team-violet-subtle: rgba(124, 58, 237, 0.15);
--team-emerald: #10b981;
--team-emerald-subtle: rgba(16, 185, 129, 0.15);
--team-orange: #f97316;
--team-orange-subtle: rgba(249, 115, 22, 0.15);
--team-fuchsia: #c026d3;
--team-fuchsia-subtle: rgba(192, 38, 211, 0.15);
--team-slate: #64748b;
--team-slate-subtle: rgba(100, 116, 139, 0.15);
--team-gold: #eab308;
--team-gold-subtle: rgba(234, 179, 8, 0.15);
--team-ruby: #be123c;
--team-ruby-subtle: rgba(190, 18, 60, 0.15);
```

**Step 3: Expand TEAM_MEMBER_PALETTE and TEAM_HEX_COLORS in utils.ts**

In `frontend/src/lib/utils.ts`, update:

```typescript
// Expand from 8 to 16 colors
const TEAM_MEMBER_PALETTE: TeamColor[] = [
  'coral', 'rose', 'amber', 'cyan', 'pink', 'lime', 'indigo', 'teal',
  'sky', 'violet', 'emerald', 'orange', 'fuchsia', 'slate', 'gold', 'ruby'
];

// Add to TEAM_HEX_COLORS
const TEAM_HEX_COLORS: Record<string, string> = {
  coral: '#f97066', rose: '#f43f5e', amber: '#f59e0b', cyan: '#06b6d4',
  pink: '#ec4899', lime: '#84cc16', indigo: '#6366f1', teal: '#14b8a6',
  sky: '#38bdf8', violet: '#8b5cf6', emerald: '#34d399', orange: '#fb923c',
  fuchsia: '#d946ef', slate: '#94a3b8', gold: '#facc15', ruby: '#e11d48'
};
```

Also update the `TeamColor` type (if it exists as a union type) to include the new colors.

**Step 4: Verify build**

Run: `cd frontend && npm run check`
Expected: No type errors

**Step 5: Commit**

```bash
git add frontend/src/app.css frontend/src/lib/utils.ts
git commit -m "feat(team): expand member color palette from 8 to 16 colors"
```

---

### Task 2: Add API Endpoint for Team Session Stats

**Files:**
- Modify: `api/routers/sync_status.py`
- Modify: `api/db/sync_queries.py`

**Step 1: Add query function in sync_queries.py**

Add to `api/db/sync_queries.py`:

```python
def query_session_stats_by_member(
    conn: sqlite3.Connection,
    team_name: str,
    days: int = 30,
) -> list[dict]:
    """Aggregate session_packaged and session_received events per member per day.

    Returns list of {date, member_name, packaged, received} dicts.
    """
    rows = conn.execute(
        """
        SELECT
            DATE(created_at) AS date,
            member_name,
            SUM(CASE WHEN event_type = 'session_packaged' THEN 1 ELSE 0 END) AS packaged,
            SUM(CASE WHEN event_type = 'session_received' THEN 1 ELSE 0 END) AS received
        FROM sync_events
        WHERE team_name = ?
          AND event_type IN ('session_packaged', 'session_received')
          AND member_name IS NOT NULL
          AND created_at >= datetime('now', ?)
        GROUP BY date, member_name
        ORDER BY date
        """,
        (team_name, f"-{days} days"),
    ).fetchall()
    return [
        {"date": r[0], "member_name": r[1], "packaged": r[2], "received": r[3]}
        for r in rows
    ]
```

**Step 2: Add API endpoint in sync_status.py**

Add after the `sync_team_activity` endpoint:

```python
@router.get("/teams/{team_name}/session-stats")
async def sync_team_session_stats(
    team_name: str,
    days: int = 30,
) -> Any:
    """Session activity stats per member per day for charts."""
    if not ALLOWED_PROJECT_NAME.match(team_name):
        raise HTTPException(400, "Invalid team name")

    days = max(1, min(days, 365))

    conn = _get_sync_conn()
    if not conn.execute("SELECT 1 FROM sync_teams WHERE name = ?", (team_name,)).fetchone():
        raise HTTPException(404, f"Team '{team_name}' not found")

    from db.sync_queries import query_session_stats_by_member
    stats = query_session_stats_by_member(conn, team_name, days)
    return {"stats": stats, "days": days}
```

**Step 3: Verify API**

Run: `cd api && python -c "from routers.sync_status import router; print('OK')"`
Expected: OK (no import errors)

**Step 4: Commit**

```bash
git add api/routers/sync_status.py api/db/sync_queries.py
git commit -m "feat(api): add team session-stats endpoint for per-member daily aggregation"
```

---

### Task 3: Add TypeScript Types for New API

**Files:**
- Modify: `frontend/src/lib/api-types.ts`

**Step 1: Add types**

```typescript
export interface TeamSessionStat {
  date: string;
  member_name: string;
  packaged: number;
  received: number;
}
```

**Step 2: Commit**

```bash
git add frontend/src/lib/api-types.ts
git commit -m "feat(types): add TeamSessionStat interface for team session stats"
```

---

### Task 4: Create TeamOverviewTab Component

**Files:**
- Create: `frontend/src/lib/components/team/TeamOverviewTab.svelte`

**Step 1: Create the component**

This tab contains: Join Code card, stat cards row, sessions sent/received bar chart, danger zone.

```svelte
<script lang="ts">
  import JoinCodeCard from './JoinCodeCard.svelte';
  import StatsGrid from '$lib/components/StatsGrid.svelte';
  import {
    Users,
    FolderSync,
    ArrowUpDown,
    AlertTriangle,
    Loader2
  } from 'lucide-svelte';
  import { onMount, onDestroy } from 'svelte';
  import {
    Chart,
    BarController,
    BarElement,
    LinearScale,
    CategoryScale,
    Tooltip,
    Legend
  } from 'chart.js';
  import { registerChartDefaults, createResponsiveConfig, createCommonScaleConfig, getThemeColors } from '$lib/components/charts/chartConfig';
  import { getTeamMemberHexColor, getUserChartLabel } from '$lib/utils';
  import type { SyncTeam, SyncTeamMember, SyncProjectStatus, TeamSessionStat } from '$lib/api-types';

  Chart.register(BarController, BarElement, LinearScale, CategoryScale, Tooltip, Legend);

  interface Props {
    team: SyncTeam;
    teamName: string;
    joinCode: string | null;
    projectStatuses: SyncProjectStatus[];
    sessionStats: TeamSessionStat[];
    userNames?: Record<string, string>;
    onleave: () => void;
    deleteConfirm: boolean;
    deleting: boolean;
    deleteError: string | null;
    ondeleteconfirm: (v: boolean) => void;
    ondeleteerror: (v: string | null) => void;
  }

  let {
    team,
    teamName,
    joinCode,
    projectStatuses,
    sessionStats,
    userNames,
    onleave,
    deleteConfirm,
    deleting,
    deleteError,
    ondeleteconfirm,
    ondeleteerror
  }: Props = $props();

  let members = $derived(team.members ?? []);
  let projects = $derived(team.projects ?? []);

  let onlineCount = $derived(members.filter((m: SyncTeamMember) => m.connected).length);
  let inSyncCount = $derived(projectStatuses.filter((p) => p.gap === 0).length);

  // Aggregate sent/received totals per member from sessionStats
  let memberTotals = $derived.by(() => {
    const totals: Record<string, { sent: number; received: number }> = {};
    for (const stat of sessionStats) {
      if (!totals[stat.member_name]) totals[stat.member_name] = { sent: 0, received: 0 };
      totals[stat.member_name].sent += stat.packaged;
      totals[stat.member_name].received += stat.received;
    }
    return totals;
  });

  let totalSent = $derived(Object.values(memberTotals).reduce((a, b) => a + b.sent, 0));
  let totalReceived = $derived(Object.values(memberTotals).reduce((a, b) => a + b.received, 0));

  // Chart
  let canvas: HTMLCanvasElement;
  let chart: Chart | null = null;

  onMount(() => {
    registerChartDefaults();
    buildChart();
  });

  onDestroy(() => {
    chart?.destroy();
  });

  function buildChart() {
    if (!canvas) return;
    chart?.destroy();

    const colors = getThemeColors();
    const memberNames = Object.keys(memberTotals);
    if (memberNames.length === 0) return;

    const labels = memberNames.map((m) => getUserChartLabel(m, userNames));
    const sentData = memberNames.map((m) => memberTotals[m].sent);
    const receivedData = memberNames.map((m) => memberTotals[m].received);
    const barColors = memberNames.map((m) => getTeamMemberHexColor(m));

    chart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels,
        datasets: [
          {
            label: 'Sent',
            data: sentData,
            backgroundColor: barColors.map((c) => c + 'cc'),
            borderColor: barColors,
            borderWidth: 1
          },
          {
            label: 'Received',
            data: receivedData,
            backgroundColor: barColors.map((c) => c + '66'),
            borderColor: barColors,
            borderWidth: 1
          }
        ]
      },
      options: {
        ...createResponsiveConfig(),
        plugins: {
          ...createResponsiveConfig().plugins,
          legend: {
            display: true,
            position: 'top',
            align: 'end',
            labels: { boxWidth: 8, boxHeight: 8, usePointStyle: true, pointStyle: 'circle', font: { size: 10 }, padding: 12 }
          },
          tooltip: {
            ...createResponsiveConfig().plugins.tooltip,
            backgroundColor: colors.bgBase,
            titleColor: colors.text,
            bodyColor: colors.textSecondary,
            borderColor: colors.border,
            borderWidth: 1
          }
        },
        scales: {
          ...createCommonScaleConfig(),
          x: { ...createCommonScaleConfig().x, grid: { display: false } }
        }
      }
    });
  }

  $effect(() => {
    if (chart && sessionStats) buildChart();
  });
</script>

<div class="space-y-8">
  {#if joinCode}
    <section>
      <h2 class="text-sm font-semibold text-[var(--text-primary)] mb-3 uppercase tracking-wider">Join Code</h2>
      <JoinCodeCard code={joinCode} />
    </section>
  {/if}

  <!-- Stat Cards -->
  <StatsGrid columns={3}
    stats={[
      { title: 'Members', value: `${onlineCount}/${members.length}`, description: 'online', icon: Users, color: 'success' },
      { title: 'Projects', value: `${inSyncCount}/${projects.length}`, description: 'in sync', icon: FolderSync, color: 'info' },
      { title: 'Sessions Shared', value: `${totalSent + totalReceived}`, description: `${totalSent} sent / ${totalReceived} received`, icon: ArrowUpDown, color: 'accent' }
    ]}
  />

  <!-- Sessions Sent/Received Chart -->
  {#if Object.keys(memberTotals).length > 0}
    <section class="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)] p-4">
      <h3 class="text-sm font-medium text-[var(--text-primary)] mb-4">Sessions by Member</h3>
      <div class="h-[200px]">
        <canvas bind:this={canvas}></canvas>
      </div>
    </section>
  {/if}

  <!-- Danger Zone -->
  <section class="pt-4 border-t border-[var(--border)]">
    <h2 class="text-sm font-semibold text-[var(--error)] mb-3 uppercase tracking-wider">Danger Zone</h2>
    {#if deleteConfirm}
      <div class="space-y-2">
        <div class="flex items-center gap-3 p-4 rounded-lg border border-[var(--error)]/20 bg-[var(--error)]/5">
          <AlertTriangle size={16} class="text-[var(--error)] shrink-0" />
          <p class="text-sm text-[var(--text-primary)] flex-1">
            Leave team "{teamName}"? This will stop syncing with all members and clean up Syncthing folders.
          </p>
          <div class="flex items-center gap-2 shrink-0">
            <button onclick={onleave} disabled={deleting}
              class="px-3 py-1.5 text-xs font-medium rounded bg-[var(--error)] text-white hover:bg-[var(--error)]/80 transition-colors disabled:opacity-50">
              {#if deleting}<Loader2 size={12} class="animate-spin" />{:else}Leave{/if}
            </button>
            <button onclick={() => { ondeleteconfirm(false); ondeleteerror(null); }}
              class="px-3 py-1.5 text-xs rounded text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition-colors">
              Cancel
            </button>
          </div>
        </div>
        {#if deleteError}
          <p class="text-xs text-[var(--error)]" aria-live="polite">{deleteError}</p>
        {/if}
      </div>
    {:else}
      <button onclick={() => ondeleteconfirm(true)}
        class="px-4 py-2 text-sm font-medium rounded-[var(--radius-md)] border border-[var(--error)]/30
          text-[var(--error)] hover:bg-[var(--error)]/10 transition-colors">
        Leave Team
      </button>
    {/if}
  </section>
</div>
```

**Step 2: Verify build**

Run: `cd frontend && npm run check`
Expected: No errors (or only warnings from unused components — acceptable at this stage)

**Step 3: Commit**

```bash
git add frontend/src/lib/components/team/TeamOverviewTab.svelte
git commit -m "feat(team): add TeamOverviewTab component with stats and sent/received chart"
```

---

### Task 5: Create TeamMembersTab Component

**Files:**
- Create: `frontend/src/lib/components/team/TeamMembersTab.svelte`
- Create: `frontend/src/lib/components/team/MemberSparkline.svelte`

**Step 1: Create MemberSparkline component**

A tiny Chart.js line chart (~80x30px) for member cards.

```svelte
<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import { Chart, LineController, LineElement, PointElement, LinearScale, CategoryScale } from 'chart.js';

  Chart.register(LineController, LineElement, PointElement, LinearScale, CategoryScale);

  interface Props {
    data: number[];
    color: string;
    class?: string;
  }

  let { data, color, class: className = '' }: Props = $props();

  let canvas: HTMLCanvasElement;
  let chart: Chart | null = null;

  onMount(() => {
    chart = new Chart(canvas, {
      type: 'line',
      data: {
        labels: data.map((_, i) => String(i)),
        datasets: [{
          data,
          borderColor: color,
          backgroundColor: color + '20',
          fill: true,
          tension: 0.4,
          pointRadius: 0,
          borderWidth: 1.5
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip: { enabled: false } },
        scales: {
          x: { display: false },
          y: { display: false, beginAtZero: true }
        }
      }
    });
  });

  onDestroy(() => { chart?.destroy(); });

  $effect(() => {
    if (chart && data) {
      chart.data.labels = data.map((_, i) => String(i));
      chart.data.datasets[0].data = data;
      chart.update();
    }
  });
</script>

<div class="w-20 h-8 {className}">
  <canvas bind:this={canvas}></canvas>
</div>
```

**Step 2: Create TeamMembersTab component**

Grid of member cards with sparklines, color borders, connection status.

```svelte
<script lang="ts">
  import MemberSparkline from './MemberSparkline.svelte';
  import { getTeamMemberColor, getTeamMemberHexColor } from '$lib/utils';
  import { API_BASE } from '$lib/config';
  import { Wifi, WifiOff, Trash2, Loader2 } from 'lucide-svelte';
  import type { SyncTeamMember, SyncDevice, TeamSessionStat } from '$lib/api-types';

  interface Props {
    members: SyncTeamMember[];
    teamName: string;
    devices: SyncDevice[];
    userId: string | undefined;
    sessionStats: TeamSessionStat[];
    detectData: { running: boolean } | null;
    onrefresh: () => void;
  }

  let { members, teamName, devices, userId, sessionStats, detectData, onrefresh }: Props = $props();

  let removeConfirm = $state<string | null>(null);
  let removing = $state(false);

  // Build 14-day sparkline data per member
  let sparklineData = $derived.by(() => {
    const result: Record<string, number[]> = {};
    const now = new Date();
    for (const member of members) {
      const days: number[] = [];
      for (let i = 13; i >= 0; i--) {
        const d = new Date(now);
        d.setDate(d.getDate() - i);
        const key = d.toISOString().slice(0, 10);
        const count = sessionStats
          .filter((s) => s.member_name === member.name && s.date === key)
          .reduce((a, b) => a + b.packaged + b.received, 0);
        days.push(count);
      }
      result[member.name] = days;
    }
    return result;
  });

  function formatBytes(bytes: number): string {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }

  async function handleRemove(memberName: string) {
    removing = true;
    try {
      const res = await fetch(
        `${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/members/${encodeURIComponent(memberName)}`,
        { method: 'DELETE' }
      );
      if (res.ok) {
        removeConfirm = null;
        onrefresh();
      }
    } finally {
      removing = false;
    }
  }
</script>

<div class="space-y-4">
  <div class="grid grid-cols-1 md:grid-cols-2 gap-3">
    {#each members as member (member.name)}
      {@const colors = getTeamMemberColor(member.name)}
      {@const hexColor = getTeamMemberHexColor(member.name)}
      {@const isSelf = member.name === userId}
      <div
        class="flex items-center gap-3 p-4 rounded-lg border border-[var(--border)] bg-[var(--bg-base)]"
        style="border-left: 3px solid {colors.border};"
      >
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2">
            <span class="text-sm font-medium text-[var(--text-primary)] truncate">{member.name}</span>
            {#if isSelf}
              <span class="px-1.5 py-0.5 text-[10px] font-medium rounded bg-[var(--accent)]/15 text-[var(--accent)] border border-[var(--accent)]/20">You</span>
            {/if}
          </div>
          <div class="flex items-center gap-2 mt-1">
            {#if member.connected}
              <span class="flex items-center gap-1 text-xs text-[var(--success)]">
                <Wifi size={11} /> Online
              </span>
            {:else}
              <span class="flex items-center gap-1 text-xs text-[var(--text-muted)]">
                <WifiOff size={11} /> Offline
              </span>
            {/if}
            <span class="text-[10px] text-[var(--text-muted)]">
              {formatBytes(member.in_bytes_total)} in / {formatBytes(member.out_bytes_total)} out
            </span>
          </div>
        </div>

        <MemberSparkline data={sparklineData[member.name] ?? []} color={hexColor} />

        {#if !isSelf}
          <div class="shrink-0">
            {#if removeConfirm === member.name}
              <div class="flex items-center gap-1">
                <button onclick={() => handleRemove(member.name)} disabled={removing}
                  class="px-2 py-1 text-xs font-medium rounded bg-[var(--error)] text-white hover:bg-[var(--error)]/80 transition-colors disabled:opacity-50">
                  {#if removing}<Loader2 size={11} class="animate-spin" />{:else}Remove{/if}
                </button>
                <button onclick={() => (removeConfirm = null)}
                  class="px-2 py-1 text-xs rounded text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition-colors">
                  Cancel
                </button>
              </div>
            {:else}
              <button onclick={() => (removeConfirm = member.name)}
                class="p-1.5 rounded text-[var(--text-muted)] hover:text-[var(--error)] hover:bg-[var(--error)]/10 transition-colors"
                title="Remove member">
                <Trash2 size={14} />
              </button>
            {/if}
          </div>
        {/if}
      </div>
    {/each}
  </div>

  {#if members.length === 0}
    <p class="text-sm text-[var(--text-muted)] py-4 text-center">No members yet. Share your join code to invite teammates.</p>
  {/if}

  <!-- Diagnostic hints when waiting for members -->
  {#if members.length <= 1}
    <div class="p-4 rounded-lg border border-[var(--border)]/50 bg-[var(--bg-subtle)]">
      <p class="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-2">Waiting for members?</p>
      <ul class="space-y-1.5 text-xs text-[var(--text-muted)]">
        <li class="flex items-start gap-2">
          <span class="shrink-0 mt-0.5 w-1 h-1 rounded-full bg-[var(--text-muted)]"></span>
          Share the join code with your teammate
        </li>
        <li class="flex items-start gap-2">
          <span class="shrink-0 mt-0.5 w-1 h-1 rounded-full bg-[var(--text-muted)]"></span>
          Both machines need <span class="font-medium text-[var(--text-secondary)]">Syncthing running</span>
        </li>
        <li class="flex items-start gap-2">
          <span class="shrink-0 mt-0.5 w-1 h-1 rounded-full bg-[var(--text-muted)]"></span>
          Discovery can take 15-60 seconds after joining
        </li>
      </ul>
      {#if detectData}
        <div class="mt-3 flex items-center gap-2 text-xs">
          {#if detectData.running}
            <span class="flex items-center gap-1 text-[var(--success)]">
              <span class="w-1.5 h-1.5 rounded-full bg-[var(--success)]"></span> Your Syncthing is running
            </span>
          {:else}
            <span class="flex items-center gap-1 text-[var(--error)]">
              <span class="w-1.5 h-1.5 rounded-full bg-[var(--error)]"></span> Your Syncthing is not running
            </span>
          {/if}
        </div>
      {/if}
    </div>
  {/if}
</div>
```

**Step 3: Verify build**

Run: `cd frontend && npm run check`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/lib/components/team/MemberSparkline.svelte frontend/src/lib/components/team/TeamMembersTab.svelte
git commit -m "feat(team): add TeamMembersTab with sparkline charts and color-coded cards"
```

---

### Task 6: Create TeamProjectsTab Component

**Files:**
- Create: `frontend/src/lib/components/team/TeamProjectsTab.svelte`
- Create: `frontend/src/lib/components/team/ProjectMemberBar.svelte`

**Step 1: Create ProjectMemberBar — mini horizontal bar showing session volume per member**

```svelte
<script lang="ts">
  import { getTeamMemberHexColor, getUserChartLabel } from '$lib/utils';
  import type { SyncTeamProject } from '$lib/api-types';

  interface Props {
    project: SyncTeamProject;
    userNames?: Record<string, string>;
    class?: string;
  }

  let { project, userNames, class: className = '' }: Props = $props();

  // received_counts is Record<member_name, count>
  let segments = $derived.by(() => {
    const counts = project.received_counts ?? {};
    const total = Object.values(counts).reduce((a, b) => a + b, 0) + project.local_count;
    if (total === 0) return [];
    return [
      // Local user's sessions
      ...(project.local_count > 0
        ? [{ name: 'You', count: project.local_count, color: '#7c3aed', pct: (project.local_count / total) * 100 }]
        : []),
      // Remote members
      ...Object.entries(counts)
        .filter(([, c]) => c > 0)
        .map(([name, count]) => ({
          name: getUserChartLabel(name, userNames),
          count,
          color: getTeamMemberHexColor(name),
          pct: (count / total) * 100
        }))
    ];
  });
</script>

{#if segments.length > 0}
  <div class="space-y-1 {className}">
    <div class="flex h-2 rounded-full overflow-hidden bg-[var(--bg-muted)]">
      {#each segments as seg}
        <div
          style="width: {Math.max(seg.pct, 2)}%; background-color: {seg.color};"
          title="{seg.name}: {seg.count} sessions"
          class="transition-all"
        ></div>
      {/each}
    </div>
    <div class="flex flex-wrap gap-x-3 gap-y-0.5">
      {#each segments as seg}
        <span class="flex items-center gap-1 text-[10px] text-[var(--text-muted)]">
          <span class="w-1.5 h-1.5 rounded-full shrink-0" style="background-color: {seg.color};"></span>
          {seg.name} ({seg.count})
        </span>
      {/each}
    </div>
  </div>
{/if}
```

**Step 2: Create TeamProjectsTab component**

Lift the projects section into its own tab with header row, cards, and member bars.

```svelte
<script lang="ts">
  import ProjectMemberBar from './ProjectMemberBar.svelte';
  import AddProjectDialog from './AddProjectDialog.svelte';
  import SessionLimitSelector from './SessionLimitSelector.svelte';
  import { API_BASE } from '$lib/config';
  import { invalidateAll } from '$app/navigation';
  import { FolderSync, Plus, RefreshCw, Trash2, CheckCircle2, Loader2 } from 'lucide-svelte';
  import type { SyncTeamProject, SyncProjectStatus } from '$lib/api-types';

  interface Props {
    projects: SyncTeamProject[];
    teamName: string;
    projectStatuses: SyncProjectStatus[];
    allProjects: { encoded_name: string; name: string; path: string }[];
    sharedProjectNames: string[];
    syncSessionLimit: string;
    userNames?: Record<string, string>;
    onrefresh: () => void;
  }

  let { projects, teamName, projectStatuses, allProjects, sharedProjectNames, syncSessionLimit, userNames, onrefresh }: Props = $props();

  let showAddProject = $state(false);
  let removeProjectConfirm = $state<string | null>(null);
  let syncAllActing = $state(false);

  function getProjectStatus(encodedName: string): SyncProjectStatus | undefined {
    return projectStatuses.find((p) => p.encoded_name === encodedName);
  }

  async function syncAllNow() {
    syncAllActing = true;
    try {
      await fetch(`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/sync-now`, { method: 'POST' });
      onrefresh();
    } finally {
      syncAllActing = false;
    }
  }

  async function handleRemoveProject(encodedName: string) {
    try {
      const res = await fetch(
        `${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/projects/${encodeURIComponent(encodedName)}`,
        { method: 'DELETE' }
      );
      if (res.ok) {
        removeProjectConfirm = null;
        onrefresh();
      }
    } catch { /* best-effort */ }
  }
</script>

<div class="space-y-4">
  <!-- Header Actions -->
  <div class="flex items-center justify-between">
    <div class="flex items-center gap-2">
      {#if projects.length > 0}
        <button onclick={syncAllNow} disabled={syncAllActing}
          class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-[var(--radius-md)]
            bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors
            disabled:opacity-50 disabled:cursor-not-allowed">
          {#if syncAllActing}<Loader2 size={12} class="animate-spin" /> Syncing...{:else}<RefreshCw size={12} /> Sync Now{/if}
        </button>
      {/if}
      <button onclick={() => (showAddProject = true)}
        class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-[var(--radius-md)]
          border border-[var(--border)] text-[var(--text-secondary)]
          hover:bg-[var(--bg-muted)] hover:text-[var(--text-primary)] transition-colors">
        <Plus size={13} /> Add Projects
      </button>
    </div>
    {#if projects.length > 0}
      <SessionLimitSelector {teamName} currentLimit={syncSessionLimit} />
    {/if}
  </div>

  <!-- Project Cards -->
  <div class="space-y-2">
    {#each projects as project (project.encoded_name)}
      {@const status = getProjectStatus(project.encoded_name)}
      <div class="p-4 rounded-lg border border-[var(--border)] bg-[var(--bg-base)] space-y-3">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-3 min-w-0">
            <FolderSync size={16} class="text-[var(--text-muted)] shrink-0" />
            <div class="min-w-0">
              <a href="/projects/{project.encoded_name}"
                class="text-sm font-medium text-[var(--text-primary)] hover:text-[var(--accent)] transition-colors truncate block">
                {project.name || project.encoded_name}
              </a>
              {#if project.path}
                <p class="text-[11px] text-[var(--text-muted)] truncate">{project.path}</p>
              {/if}
              {#if status}
                <p class="text-[11px] text-[var(--text-muted)] mt-0.5">
                  {status.packaged_count}/{status.local_count} sessions packaged
                </p>
              {/if}
            </div>
          </div>
          <div class="flex items-center gap-2 shrink-0">
            {#if status}
              {#if status.gap === 0}
                <span class="flex items-center gap-1 px-2 py-1 text-[11px] font-medium rounded-full bg-[var(--success)]/10 text-[var(--success)] border border-[var(--success)]/20">
                  <CheckCircle2 size={11} /> In Sync
                </span>
              {:else}
                <span class="flex items-center gap-1 px-2 py-1 text-[11px] font-medium rounded-full bg-[var(--warning)]/10 text-[var(--warning)] border border-[var(--warning)]/20">
                  {status.gap} behind
                </span>
              {/if}
            {/if}
            {#if removeProjectConfirm === project.encoded_name}
              <div class="flex items-center gap-1.5">
                <button onclick={() => handleRemoveProject(project.encoded_name)}
                  class="px-2 py-1 text-xs font-medium rounded bg-[var(--error)] text-white hover:bg-[var(--error)]/80 transition-colors">Remove</button>
                <button onclick={() => (removeProjectConfirm = null)}
                  class="px-2 py-1 text-xs rounded text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition-colors">Cancel</button>
              </div>
            {:else}
              <button onclick={() => (removeProjectConfirm = project.encoded_name)}
                class="p-1.5 rounded text-[var(--text-muted)] hover:text-[var(--error)] hover:bg-[var(--error)]/10 transition-colors"
                title="Remove from team">
                <Trash2 size={14} />
              </button>
            {/if}
          </div>
        </div>

        <!-- Member contribution bar -->
        <ProjectMemberBar {project} {userNames} />
      </div>
    {/each}
    {#if projects.length === 0}
      <p class="text-sm text-[var(--text-muted)] py-4 text-center">No projects shared yet. Add projects to start syncing sessions.</p>
    {/if}
  </div>
</div>

<AddProjectDialog bind:open={showAddProject} {teamName} {allProjects} {sharedProjectNames} onadded={onrefresh} />
```

**Step 3: Verify build**

Run: `cd frontend && npm run check`
Expected: No errors

**Step 4: Commit**

```bash
git add frontend/src/lib/components/team/ProjectMemberBar.svelte frontend/src/lib/components/team/TeamProjectsTab.svelte
git commit -m "feat(team): add TeamProjectsTab with per-project member contribution bars"
```

---

### Task 7: Create TeamActivityTab Component

**Files:**
- Create: `frontend/src/lib/components/team/TeamActivityTab.svelte`

**Step 1: Create the component**

Line chart with member filter chips + TeamActivityFeed below.

```svelte
<script lang="ts">
  import { onMount, onDestroy } from 'svelte';
  import {
    Chart,
    LineController,
    LineElement,
    PointElement,
    LinearScale,
    CategoryScale,
    Filler,
    Tooltip,
    Legend
  } from 'chart.js';
  import { registerChartDefaults, createResponsiveConfig, createCommonScaleConfig, getThemeColors } from '$lib/components/charts/chartConfig';
  import { getTeamMemberHexColor, getUserChartLabel } from '$lib/utils';
  import TeamActivityFeed from './TeamActivityFeed.svelte';
  import { API_BASE } from '$lib/config';
  import type { SyncEvent, TeamSessionStat } from '$lib/api-types';

  Chart.register(LineController, LineElement, PointElement, LinearScale, CategoryScale, Filler, Tooltip, Legend);

  interface Props {
    teamName: string;
    activity: SyncEvent[];
    sessionStats: TeamSessionStat[];
    userNames?: Record<string, string>;
  }

  let { teamName, activity, sessionStats, userNames }: Props = $props();

  // Period selector
  const periods = [
    { label: '7d', days: 7 },
    { label: '30d', days: 30 },
    { label: '90d', days: 90 },
    { label: 'All', days: 365 }
  ];
  let selectedPeriod = $state(30);
  let loadedStats = $state<TeamSessionStat[]>([]);
  let loading = $state(false);

  // Use initial stats or loaded stats
  let activeStats = $derived(loadedStats.length > 0 ? loadedStats : sessionStats);

  // Member visibility toggles
  let allMembers = $derived.by(() => {
    const names = new Set<string>();
    for (const stat of activeStats) names.add(stat.member_name);
    return [...names].sort();
  });
  let visibleMembers = $state<Set<string>>(new Set());

  // Initialize visible members when allMembers changes
  $effect(() => {
    visibleMembers = new Set(allMembers);
  });

  function toggleMember(name: string) {
    const next = new Set(visibleMembers);
    if (next.has(name)) next.delete(name);
    else next.add(name);
    visibleMembers = next;
  }

  async function loadPeriod(days: number) {
    selectedPeriod = days;
    loading = true;
    try {
      const res = await fetch(`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/session-stats?days=${days}`);
      if (res.ok) {
        const data = await res.json();
        loadedStats = data.stats ?? [];
      }
    } finally {
      loading = false;
    }
  }

  // Build chart data: {date -> {member -> count}}
  let chartInput = $derived.by(() => {
    const byDateMember: Record<string, Record<string, number>> = {};
    const allDatesSet = new Set<string>();

    for (const stat of activeStats) {
      if (!visibleMembers.has(stat.member_name)) continue;
      allDatesSet.add(stat.date);
      if (!byDateMember[stat.date]) byDateMember[stat.date] = {};
      byDateMember[stat.date][stat.member_name] =
        (byDateMember[stat.date][stat.member_name] ?? 0) + stat.packaged + stat.received;
    }

    const dates = [...allDatesSet].sort();
    // Fill gaps
    if (dates.length >= 2) {
      const start = new Date(dates[0]);
      const end = new Date(dates[dates.length - 1]);
      const cur = new Date(start);
      while (cur <= end) {
        const key = cur.toISOString().slice(0, 10);
        if (!byDateMember[key]) byDateMember[key] = {};
        cur.setDate(cur.getDate() + 1);
      }
    }

    const filledDates = Object.keys(byDateMember).sort();
    return { dates: filledDates, byDateMember };
  });

  // Chart
  let canvas: HTMLCanvasElement;
  let chart: Chart | null = null;

  function buildChart() {
    if (!canvas) return;
    chart?.destroy();

    const colors = getThemeColors();
    const { dates, byDateMember } = chartInput;
    const labels = dates.map((d) => {
      const [, m, day] = d.split('-').map(Number);
      return new Date(2000, m - 1, day).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    });

    const visible = [...visibleMembers];
    const datasets = visible.map((member) => {
      const hex = getTeamMemberHexColor(member);
      return {
        label: getUserChartLabel(member, userNames),
        data: dates.map((d) => byDateMember[d]?.[member] ?? 0),
        borderColor: hex,
        backgroundColor: 'transparent',
        tension: 0.4,
        pointRadius: 3,
        pointBackgroundColor: hex,
        pointBorderColor: colors.bgBase,
        pointBorderWidth: 2,
        borderWidth: 2
      };
    });

    chart = new Chart(canvas, {
      type: 'line',
      data: { labels, datasets },
      options: {
        ...createResponsiveConfig(),
        plugins: {
          ...createResponsiveConfig().plugins,
          legend: { display: false },
          tooltip: {
            ...createResponsiveConfig().plugins.tooltip,
            backgroundColor: colors.bgBase,
            titleColor: colors.text,
            bodyColor: colors.textSecondary,
            borderColor: colors.border,
            borderWidth: 1,
            mode: 'index',
            intersect: false
          }
        },
        scales: createCommonScaleConfig()
      }
    });
  }

  onMount(() => {
    registerChartDefaults();
    buildChart();
  });

  onDestroy(() => { chart?.destroy(); });

  $effect(() => {
    // Rebuild chart when data or visibility changes
    if (canvas && chartInput) buildChart();
  });
</script>

<div class="space-y-6">
  <!-- Period Selector + Chart -->
  <section class="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)] p-4">
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-sm font-medium text-[var(--text-primary)]">Sessions Over Time</h3>
      <div class="flex items-center gap-1">
        {#each periods as p}
          <button
            onclick={() => loadPeriod(p.days)}
            class="px-2.5 py-1 text-xs font-medium rounded-full transition-colors
              {selectedPeriod === p.days
                ? 'bg-[var(--accent)] text-white'
                : 'text-[var(--text-secondary)] hover:bg-[var(--bg-muted)]'}"
          >
            {p.label}
          </button>
        {/each}
      </div>
    </div>

    <div class="h-[220px]">
      <canvas bind:this={canvas}></canvas>
    </div>

    <!-- Member filter chips -->
    {#if allMembers.length > 0}
      <div class="flex flex-wrap gap-1.5 mt-3 pt-3 border-t border-[var(--border)]/50">
        {#each allMembers as member}
          {@const hex = getTeamMemberHexColor(member)}
          {@const active = visibleMembers.has(member)}
          <button
            onclick={() => toggleMember(member)}
            class="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full transition-all
              {active
                ? 'border border-current'
                : 'border border-[var(--border)] text-[var(--text-muted)] opacity-50'}"
            style={active ? `color: ${hex}; border-color: ${hex};` : ''}
          >
            <span class="w-2 h-2 rounded-full shrink-0" style="background-color: {hex}; opacity: {active ? 1 : 0.3};"></span>
            {getUserChartLabel(member, userNames)}
          </button>
        {/each}
      </div>
    {/if}
  </section>

  <!-- Activity Feed -->
  <TeamActivityFeed events={activity} {teamName} />
</div>
```

**Step 2: Verify build**

Run: `cd frontend && npm run check`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/lib/components/team/TeamActivityTab.svelte
git commit -m "feat(team): add TeamActivityTab with line chart, period selector, and member filters"
```

---

### Task 8: Wire Up Tabs in Team Detail Page

**Files:**
- Modify: `frontend/src/routes/team/[name]/+page.svelte`
- Modify: `frontend/src/routes/team/[name]/+page.server.ts`

**Step 1: Update server loader to fetch session stats**

In `+page.server.ts`, add to the parallel fetch block:

```typescript
// Add to imports
import type { TeamSessionStat } from '$lib/api-types';

// Add to Promise.all (alongside existing fetches)
fetchWithFallback<{ stats: TeamSessionStat[] }>(
  fetch,
  `${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/session-stats?days=30`,
  { stats: [] }
),
```

Add to the return object:
```typescript
sessionStats: sessionStatsData.stats ?? [],
```

**Step 2: Rewrite the page component with tabs**

Replace the entire `+page.svelte` with the tabbed version. Key changes:
- Import `Tabs` from `$lib/components/ui`
- Import `TabsTrigger` from `$lib/components/ui/TabsTrigger.svelte`
- Import all 4 tab components
- Add `activeTab` state with URL persistence (same pattern as project detail page)
- Move pending requests ABOVE the tabs
- Move each section's content into the appropriate tab component

The page structure becomes:

```svelte
<script lang="ts">
  // ... existing imports ...
  import { Tabs } from '$lib/components/ui/Tabs.svelte';
  import TabsList from '$lib/components/ui/TabsList.svelte';
  import TabsTrigger from '$lib/components/ui/TabsTrigger.svelte';
  import TabsContent from '$lib/components/ui/TabsContent.svelte';
  import TeamOverviewTab from '$lib/components/team/TeamOverviewTab.svelte';
  import TeamMembersTab from '$lib/components/team/TeamMembersTab.svelte';
  import TeamProjectsTab from '$lib/components/team/TeamProjectsTab.svelte';
  import TeamActivityTab from '$lib/components/team/TeamActivityTab.svelte';
  import { LayoutDashboard, Users as UsersIcon, FolderSync, Activity } from 'lucide-svelte';
  import { browser } from '$app/environment';

  // Tab state with URL persistence
  const validTabs = ['overview', 'members', 'projects', 'activity'];
  let activeTab = $state('overview');
  let tabsReady = $state(false);

  onMount(() => {
    const params = new URLSearchParams(window.location.search);
    const tab = params.get('tab');
    if (tab && validTabs.includes(tab)) activeTab = tab;
    tabsReady = true;

    window.addEventListener('popstate', () => {
      const p = new URLSearchParams(window.location.search);
      const t = p.get('tab');
      if (t && validTabs.includes(t)) activeTab = t;
    });
  });

  // URL sync
  $effect(() => {
    if (!browser || !tabsReady) return;
    const url = new URL(window.location.href);
    if (activeTab === 'overview') url.searchParams.delete('tab');
    else url.searchParams.set('tab', activeTab);
    history.replaceState({}, '', url.toString());
  });

  // ... keep all existing state and functions for polling, pending requests, etc ...
</script>

<PageHeader ...existing props... />

<div class="mb-6">
  <SyncStatusBanner ... />
</div>

<!-- Pending requests ABOVE tabs -->
{#if pendingDevices.length > 0}...existing pending devices section...{/if}
{#if pendingFolders.length > 0}...existing pending folders section...{/if}

{#if team}
  <Tabs.Root bind:value={activeTab} class="space-y-6">
    <Tabs.List>
      <TabsTrigger value="overview" icon={LayoutDashboard}>Overview</TabsTrigger>
      <TabsTrigger value="members" icon={UsersIcon}>Members ({members.length})</TabsTrigger>
      <TabsTrigger value="projects" icon={FolderSync}>Projects ({projects.length})</TabsTrigger>
      <TabsTrigger value="activity" icon={Activity}>Activity</TabsTrigger>
    </Tabs.List>

    <Tabs.Content value="overview">
      <TeamOverviewTab {team} {teamName} joinCode={data.joinCode} {projectStatuses}
        sessionStats={data.sessionStats} {deleteConfirm} {deleting} {deleteError}
        onleave={handleLeaveTeam} ondeleteconfirm={(v) => deleteConfirm = v} ondeleteerror={(v) => deleteError = v} />
    </Tabs.Content>

    <Tabs.Content value="members">
      <TeamMembersTab {members} teamName={data.teamName} {devices} userId={userId}
        sessionStats={data.sessionStats} detectData={data.detectData} onrefresh={handleRefresh} />
    </Tabs.Content>

    <Tabs.Content value="projects">
      <TeamProjectsTab {projects} teamName={data.teamName} {projectStatuses}
        allProjects={data.allProjects} {sharedProjectNames}
        syncSessionLimit={data.team?.sync_session_limit ?? 'all'}
        onrefresh={handleRefresh} />
    </Tabs.Content>

    <Tabs.Content value="activity">
      <TeamActivityTab teamName={data.teamName} {activity} sessionStats={data.sessionStats} />
    </Tabs.Content>
  </Tabs.Root>
{:else}
  ...existing "team not found" fallback...
{/if}

<!-- Remove AddProjectDialog from here — it's now inside TeamProjectsTab -->
```

**Important:** The existing polling logic, pending request handlers, and fetch functions stay in the parent page. Only the rendering moves into tab components.

**Step 3: Verify build**

Run: `cd frontend && npm run check`
Expected: No errors

**Step 4: Visual verification**

Run: `cd frontend && npm run dev`
Open: http://localhost:5173/team/{your-team-name}
Verify: 4 tabs render, URL updates with `?tab=`, content displays correctly in each tab

**Step 5: Commit**

```bash
git add frontend/src/routes/team/[name]/+page.svelte frontend/src/routes/team/[name]/+page.server.ts
git commit -m "feat(team): convert team detail page to tabbed layout with Overview/Members/Projects/Activity"
```

---

### Task 9: Fix Imports and Polish

After wiring everything up, there may be import path issues or minor TypeScript errors.

**Step 1: Run full type check**

Run: `cd frontend && npm run check`

Fix any errors found (typical issues: import paths for Tabs components, missing type exports, prop mismatches).

**Step 2: Run lint**

Run: `cd frontend && npm run lint`

Fix any lint warnings.

**Step 3: Visual QA**

Manually check each tab in the browser:
- Overview: Stats cards, sent/received chart, danger zone
- Members: Grid layout, sparklines render, color borders match
- Projects: Cards with member bars, sync status badges, add/remove flows
- Activity: Line chart renders, period selector works, member chips toggle visibility

**Step 4: Commit**

```bash
git add -A
git commit -m "fix(team): polish tab imports, types, and visual consistency"
```
