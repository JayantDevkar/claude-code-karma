# Member Page Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a read-only member detail page at `/members/[user_id]` with 4 tabs (Overview, Sessions, Teams, Activity), themed with the member's hash-assigned color from the 16-color palette.

**Architecture:** New backend endpoint aggregates member data across teams. SvelteKit page loads data server-side, renders a color-themed profile header + bits-ui tabs. Each tab is a standalone Svelte component following the exact patterns from the redesigned team detail page (`TeamOverviewTab`, `TeamMembersTab`, etc.). TeamMembersTab is modified to link member cards to the new page.

**Tech Stack:** FastAPI (backend endpoint), SvelteKit + Svelte 5 (page + 4 tab components), bits-ui (tabs), Chart.js (overview chart), lucide-svelte (icons), Tailwind CSS 4 (styling)

**Design Doc:** `docs/plans/2026-03-09-member-page-design.md`

---

### Task 1: Backend — Add `/sync/members/{user_id}` Endpoint

**Files:**
- Modify: `api/routers/sync_status.py` — add new endpoint at bottom of file (before settings endpoint)

**Context:** This endpoint aggregates data across all teams for a single member. It reuses existing DB queries and Syncthing device APIs already used by the team detail page. The `sync_members` table has `(team_name, name, device_id)` as key columns. The `sync_events` table has `member_name` for filtering. Session stats come from `query_session_stats_by_member()` already in `api/db/sync_queries.py`.

**Step 1: Add the endpoint**

Add this endpoint to `api/routers/sync_status.py`, right before the `sync_update_team_settings` function:

```python
@router.get("/members/{member_name}")
async def sync_member_profile(member_name: str) -> Any:
    """Aggregated member profile across all teams."""
    if not ALLOWED_MEMBER_NAME.match(member_name):
        raise HTTPException(400, "Invalid member name")

    conn = _get_sync_conn()

    # Find all teams this member belongs to
    rows = conn.execute(
        "SELECT team_name, device_id FROM sync_members WHERE name = ?",
        (member_name,),
    ).fetchall()

    if not rows:
        raise HTTPException(404, f"Member '{member_name}' not found")

    device_id = rows[0]["device_id"]
    team_names = [r["team_name"] for r in rows]

    # Get device connection info from Syncthing
    connected = False
    in_bytes = 0
    out_bytes = 0
    try:
        st = _get_st()
        devices = st.system.get_status().get("connections", {})
        if device_id in devices:
            dev_info = devices[device_id]
            connected = dev_info.get("connected", False)
            in_bytes = dev_info.get("inBytesTotal", 0)
            out_bytes = dev_info.get("outBytesTotal", 0)
    except Exception:
        pass

    # Build team details with project contribution for this member
    teams_data = []
    all_session_stats = []
    total_projects = set()

    for tn in team_names:
        team_row = conn.execute(
            "SELECT name FROM sync_teams WHERE name = ?", (tn,)
        ).fetchone()
        if not team_row:
            continue

        # Members in this team
        team_members = conn.execute(
            "SELECT name, device_id FROM sync_members WHERE team_name = ?", (tn,)
        ).fetchall()

        # Online count from Syncthing
        online_count = 0
        try:
            st = _get_st()
            for tm in team_members:
                dev_conns = st.system.get_status().get("connections", {})
                if tm["device_id"] in dev_conns and dev_conns[tm["device_id"]].get("connected"):
                    online_count += 1
        except Exception:
            pass

        # Projects in this team
        team_projects = conn.execute(
            "SELECT project_encoded_name, path FROM sync_team_projects WHERE team_name = ?",
            (tn,),
        ).fetchall()

        project_list = []
        for tp in team_projects:
            total_projects.add(tp["project_encoded_name"])
            # Count received sessions for this member in this project
            received = conn.execute(
                """SELECT COUNT(*) as cnt FROM sync_events
                   WHERE team_name = ? AND member_name = ? AND project_encoded_name = ?
                   AND event_type IN ('session_packaged', 'session_received')""",
                (tn, member_name, tp["project_encoded_name"]),
            ).fetchone()
            project_list.append({
                "encoded_name": tp["project_encoded_name"],
                "name": tp["project_encoded_name"],
                "session_count": received["cnt"] if received else 0,
            })

        teams_data.append({
            "name": tn,
            "member_count": len(team_members),
            "project_count": len(team_projects),
            "online_count": online_count,
            "projects": project_list,
        })

        # Session stats for this team
        stats = query_session_stats_by_member(conn, tn, 30)
        member_stats = [s for s in stats if s["member_name"] == member_name]
        all_session_stats.extend(member_stats)

    # Activity across all teams for this member
    activity_rows = conn.execute(
        """SELECT id, event_type, team_name, member_name, project_encoded_name,
                  session_uuid, detail, created_at
           FROM sync_events WHERE member_name = ?
           ORDER BY created_at DESC LIMIT 50""",
        (member_name,),
    ).fetchall()
    activity = [dict(r) for r in activity_rows]

    # Aggregate stats
    total_sessions = sum(
        s.get("packaged", 0) + s.get("received", 0) for s in all_session_stats
    )
    last_active = None
    if activity:
        last_active = activity[0]["created_at"]

    return {
        "user_id": member_name,
        "device_id": device_id,
        "connected": connected,
        "in_bytes_total": in_bytes,
        "out_bytes_total": out_bytes,
        "teams": teams_data,
        "stats": {
            "total_sessions": total_sessions,
            "total_projects": len(total_projects),
            "last_active": last_active,
        },
        "session_stats": all_session_stats,
        "activity": activity,
    }
```

**Step 2: Verify endpoint works**

Run: `cd api && uvicorn main:app --reload --port 8000`

Then test: `curl http://localhost:8000/sync/members/{some_member_name} | python -m json.tool`

Expected: JSON with user_id, teams, stats, session_stats, activity fields.

**Step 3: Commit**

```bash
git add api/routers/sync_status.py
git commit -m "feat(api): add /sync/members/{member_name} aggregated profile endpoint"
```

---

### Task 2: Frontend Types — Add MemberProfile Interface

**Files:**
- Modify: `frontend/src/lib/api-types.ts` — add new types near the bottom, after `TeamSessionStat`

**Step 1: Add types**

Add these interfaces after the `TeamSessionStat` interface in `api-types.ts`:

```typescript
export interface MemberTeamProject {
	encoded_name: string;
	name: string;
	session_count: number;
}

export interface MemberTeam {
	name: string;
	member_count: number;
	project_count: number;
	online_count: number;
	projects: MemberTeamProject[];
}

export interface MemberStats {
	total_sessions: number;
	total_projects: number;
	last_active: string | null;
}

export interface MemberProfile {
	user_id: string;
	device_id: string;
	connected: boolean;
	in_bytes_total: number;
	out_bytes_total: number;
	teams: MemberTeam[];
	stats: MemberStats;
	session_stats: TeamSessionStat[];
	activity: SyncEvent[];
}
```

**Step 2: Type-check**

Run: `cd frontend && npm run check`

Expected: No errors.

**Step 3: Commit**

```bash
git add frontend/src/lib/api-types.ts
git commit -m "feat(types): add MemberProfile and related interfaces"
```

---

### Task 3: Frontend — Data Loader (`+page.server.ts`)

**Files:**
- Create: `frontend/src/routes/members/[user_id]/+page.server.ts`

**Context:** Follow the exact pattern from `frontend/src/routes/team/[name]/+page.server.ts`. Use `safeFetch` for the primary member profile call (so we can show 404), and `fetchWithFallback` for supplementary data.

**Step 1: Create the directory and data loader**

```bash
mkdir -p frontend/src/routes/members/\[user_id\]
```

Write `frontend/src/routes/members/[user_id]/+page.server.ts`:

```typescript
import type { PageServerLoad } from './$types';
import { API_BASE } from '$lib/config';
import { safeFetch, fetchWithFallback } from '$lib/utils/api-fetch';
import type { MemberProfile, SyncDevice, RemoteSessionUser } from '$lib/api-types';

export const load: PageServerLoad = async ({ fetch, params }) => {
	const userId = params.user_id;

	const [profileResult, devicesData, remoteUserData] = await Promise.all([
		safeFetch<MemberProfile>(fetch, `${API_BASE}/sync/members/${encodeURIComponent(userId)}`),
		fetchWithFallback<{ devices: SyncDevice[] }>(fetch, `${API_BASE}/sync/devices`, {
			devices: []
		}),
		fetchWithFallback<RemoteSessionUser[]>(
			fetch,
			`${API_BASE}/remote/users`,
			[]
		)
	]);

	// Find this user's remote session info
	const remoteUser = (Array.isArray(remoteUserData) ? remoteUserData : []).find(
		(u) => u.user_id === userId
	);

	return {
		userId,
		profile: profileResult.ok ? profileResult.data : null,
		error: profileResult.ok ? null : profileResult.message,
		devices: devicesData.devices ?? [],
		remoteUser: remoteUser ?? null
	};
};
```

**Step 2: Type-check**

Run: `cd frontend && npm run check`

Note: We may need to check if `RemoteSessionUser` exists in api-types.ts. If not, we'll add it or use the inline type. Check existing types first — look for `RemoteSessionUser` or similar. The backend has `RemoteUser(user_id, project_count, total_sessions)`. Match this:

If `RemoteSessionUser` doesn't exist in api-types.ts, add it near the other remote types:

```typescript
export interface RemoteSessionUser {
	user_id: string;
	project_count: number;
	total_sessions: number;
}
```

However, `RemoteSessionUser` already exists in api-types.ts (line 1864) — verify it has the right fields. If it differs, use the existing shape.

**Step 3: Commit**

```bash
git add frontend/src/routes/members/\[user_id\]/+page.server.ts
# Also add api-types.ts if RemoteSessionUser was added
git commit -m "feat(member): add page data loader for /members/[user_id]"
```

---

### Task 4: Frontend — MemberOverviewTab Component

**Files:**
- Create: `frontend/src/lib/components/team/MemberOverviewTab.svelte`

**Context:** Follow `TeamOverviewTab.svelte` pattern exactly. Shows stats grid (3 cols), a bar chart of daily sent/received sessions, and a project contribution list. Uses the member's color for chart bars.

**Step 1: Create the component**

Write `frontend/src/lib/components/team/MemberOverviewTab.svelte`:

```svelte
<script lang="ts">
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
	import { Activity, FolderGit2, Clock } from 'lucide-svelte';
	import type { MemberProfile, StatItem } from '$lib/api-types';
	import StatsGrid from '$lib/components/StatsGrid.svelte';
	import {
		registerChartDefaults,
		createResponsiveConfig,
		createCommonScaleConfig,
		getThemeColors
	} from '$lib/components/charts/chartConfig';
	import { getTeamMemberHexColor, formatRelativeTime } from '$lib/utils';

	Chart.register(BarController, BarElement, LinearScale, CategoryScale, Tooltip, Legend);

	interface Props {
		profile: MemberProfile;
	}

	let { profile }: Props = $props();

	let canvas: HTMLCanvasElement;
	let chart: Chart | null = null;

	// Aggregate session stats by date
	let dailyTotals = $derived.by(() => {
		const totals = new Map<string, { sent: number; received: number }>();
		for (const stat of profile.session_stats) {
			const existing = totals.get(stat.date) ?? { sent: 0, received: 0 };
			existing.sent += stat.packaged;
			existing.received += stat.received;
			totals.set(stat.date, existing);
		}
		// Sort by date
		return new Map([...totals.entries()].sort());
	});

	// All projects this member contributes to (flatten from teams)
	let allProjects = $derived.by(() => {
		const projects = new Map<string, { encoded_name: string; name: string; session_count: number }>();
		for (const team of profile.teams) {
			for (const project of team.projects) {
				const existing = projects.get(project.encoded_name);
				if (existing) {
					existing.session_count += project.session_count;
				} else {
					projects.set(project.encoded_name, { ...project });
				}
			}
		}
		return [...projects.values()].sort((a, b) => b.session_count - a.session_count);
	});

	let stats = $derived<StatItem[]>([
		{
			title: 'Sessions',
			value: profile.stats.total_sessions,
			description: 'sent & received',
			icon: Activity,
			color: 'accent'
		},
		{
			title: 'Projects',
			value: profile.stats.total_projects,
			description: `across ${profile.teams.length} team${profile.teams.length !== 1 ? 's' : ''}`,
			icon: FolderGit2,
			color: 'green'
		},
		{
			title: 'Last Active',
			value: profile.stats.last_active
				? formatRelativeTime(new Date(profile.stats.last_active.replace(' ', 'T')))
				: 'Never',
			description: profile.stats.last_active
				? new Date(profile.stats.last_active.replace(' ', 'T')).toLocaleDateString('en-US', {
						month: 'short',
						day: 'numeric',
						year: 'numeric'
					})
				: '',
			icon: Clock,
			color: 'orange'
		}
	]);

	// Chart labels and data
	let chartLabels = $derived(
		[...dailyTotals.keys()].map((d) => {
			const [year, month, day] = d.split('-').map(Number);
			return new Date(year, month - 1, day).toLocaleDateString('en-US', {
				month: 'short',
				day: 'numeric'
			});
		})
	);
	let chartSentData = $derived([...dailyTotals.values()].map((t) => t.sent));
	let chartReceivedData = $derived([...dailyTotals.values()].map((t) => t.received));

	onMount(() => {
		registerChartDefaults();
	});

	onDestroy(() => {
		chart?.destroy();
	});

	$effect(() => {
		if (!canvas || dailyTotals.size === 0) return;

		const hex = getTeamMemberHexColor(profile.user_id);

		if (!chart) {
			const colors = getThemeColors();
			const scaleConfig = createCommonScaleConfig();

			chart = new Chart(canvas, {
				type: 'bar',
				data: {
					labels: chartLabels,
					datasets: [
						{
							label: 'Sent',
							data: chartSentData,
							backgroundColor: hex,
							borderRadius: 4
						},
						{
							label: 'Received',
							data: chartReceivedData,
							backgroundColor: hex + '66',
							borderRadius: 4
						}
					]
				},
				options: {
					...createResponsiveConfig(),
					scales: scaleConfig,
					plugins: {
						...createResponsiveConfig().plugins,
						legend: {
							...createResponsiveConfig().plugins.legend,
							position: 'bottom'
						},
						tooltip: {
							...createResponsiveConfig().plugins.tooltip,
							backgroundColor: colors.bgBase,
							titleColor: colors.text,
							bodyColor: colors.textSecondary,
							borderColor: colors.border,
							borderWidth: 1,
							displayColors: true
						}
					}
				}
			});
		} else {
			chart.data.labels = chartLabels;
			chart.data.datasets[0].data = chartSentData;
			chart.data.datasets[1].data = chartReceivedData;
			chart.update();
		}
	});
</script>

<div class="space-y-8">
	<!-- Stats -->
	<section>
		<StatsGrid {stats} columns={3} />
	</section>

	<!-- Sessions Over Time Chart -->
	{#if dailyTotals.size > 0}
		<section>
			<div class="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)] p-4">
				<h3 class="text-sm font-medium text-[var(--text-primary)] mb-4">Sessions Over Time</h3>
				<div class="h-[200px]">
					<canvas bind:this={canvas}></canvas>
				</div>
			</div>
		</section>
	{/if}

	<!-- Projects Contributed To -->
	{#if allProjects.length > 0}
		<section>
			<h2 class="text-sm font-semibold text-[var(--text-primary)] mb-3 uppercase tracking-wider">
				Projects
			</h2>
			<div class="space-y-2">
				{#each allProjects as project (project.encoded_name)}
					<a
						href="/projects/{project.encoded_name}"
						class="flex items-center justify-between p-3 rounded-lg border border-[var(--border)] bg-[var(--bg-base)] hover:border-[var(--accent)]/30 hover:shadow-sm transition-all"
					>
						<div class="flex items-center gap-2.5 min-w-0">
							<FolderGit2 size={15} class="text-[var(--text-muted)] shrink-0" />
							<span class="text-sm font-medium text-[var(--text-primary)] truncate">
								{project.name || project.encoded_name}
							</span>
						</div>
						<span class="text-xs text-[var(--text-muted)] shrink-0 ml-2">
							{project.session_count} session{project.session_count !== 1 ? 's' : ''}
						</span>
					</a>
				{/each}
			</div>
		</section>
	{/if}
</div>
```

**Step 2: Type-check**

Run: `cd frontend && npm run check`

Expected: No errors. If `StatItem` import path differs, adjust.

**Step 3: Commit**

```bash
git add frontend/src/lib/components/team/MemberOverviewTab.svelte
git commit -m "feat(member): add MemberOverviewTab with stats grid and session chart"
```

---

### Task 5: Frontend — MemberSessionsTab Component

**Files:**
- Create: `frontend/src/lib/components/team/MemberSessionsTab.svelte`

**Context:** This tab shows the remote sessions synced from this member. Uses the `/remote/users/{user_id}/projects` API to list projects and session counts, and `/remote/users/{user_id}/projects/{project}/sessions` to list individual sessions. Each session links to the session detail page. Sessions are grouped by project.

**Step 1: Create the component**

Write `frontend/src/lib/components/team/MemberSessionsTab.svelte`:

```svelte
<script lang="ts">
	import { FolderGit2, FileText, Loader2, ChevronDown, ChevronRight } from 'lucide-svelte';
	import { API_BASE } from '$lib/config';
	import { formatRelativeTime } from '$lib/utils';
	import type { MemberProfile } from '$lib/api-types';

	interface RemoteProject {
		encoded_name: string;
		session_count: number;
		synced_at: string | null;
		machine_id: string | null;
	}

	interface RemoteSessionItem {
		uuid: string;
		mtime: string;
		size_bytes: number;
		worktree_name: string | null;
	}

	interface Props {
		profile: MemberProfile;
	}

	let { profile }: Props = $props();

	let projects = $state<RemoteProject[]>([]);
	let loading = $state(true);
	let expandedProject = $state<string | null>(null);
	let projectSessions = $state<Record<string, RemoteSessionItem[]>>({});
	let loadingSessions = $state<string | null>(null);

	// Fetch projects on mount
	$effect(() => {
		fetchProjects();
	});

	async function fetchProjects() {
		loading = true;
		try {
			const res = await fetch(
				`${API_BASE}/remote/users/${encodeURIComponent(profile.user_id)}/projects`
			);
			if (res.ok) {
				projects = await res.json();
			}
		} catch {
			// silently fail
		} finally {
			loading = false;
		}
	}

	async function toggleProject(encodedName: string) {
		if (expandedProject === encodedName) {
			expandedProject = null;
			return;
		}

		expandedProject = encodedName;

		if (!projectSessions[encodedName]) {
			loadingSessions = encodedName;
			try {
				const res = await fetch(
					`${API_BASE}/remote/users/${encodeURIComponent(profile.user_id)}/projects/${encodeURIComponent(encodedName)}/sessions`
				);
				if (res.ok) {
					const sessions: RemoteSessionItem[] = await res.json();
					projectSessions = {
						...projectSessions,
						[encodedName]: sessions.sort(
							(a, b) => new Date(b.mtime).getTime() - new Date(a.mtime).getTime()
						)
					};
				}
			} catch {
				// silently fail
			} finally {
				loadingSessions = null;
			}
		}
	}

	function formatBytes(bytes: number): string {
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
		return `${(bytes / 1048576).toFixed(1)} MB`;
	}

	let totalSessions = $derived(projects.reduce((sum, p) => sum + p.session_count, 0));
</script>

<div class="space-y-4">
	{#if loading}
		<div class="flex items-center justify-center py-12">
			<Loader2 size={20} class="animate-spin text-[var(--text-muted)]" />
		</div>
	{:else if projects.length === 0}
		<p class="text-sm text-[var(--text-muted)] py-8 text-center">
			No synced sessions from this member yet.
		</p>
	{:else}
		<p class="text-sm text-[var(--text-secondary)]">
			{totalSessions} session{totalSessions !== 1 ? 's' : ''} across {projects.length} project{projects.length !== 1 ? 's' : ''}
		</p>

		<div class="space-y-2">
			{#each projects as project (project.encoded_name)}
				{@const isExpanded = expandedProject === project.encoded_name}
				{@const sessions = projectSessions[project.encoded_name] ?? []}
				{@const isLoading = loadingSessions === project.encoded_name}

				<div class="rounded-lg border border-[var(--border)] bg-[var(--bg-base)] overflow-hidden">
					<!-- Project header (clickable) -->
					<button
						onclick={() => toggleProject(project.encoded_name)}
						class="w-full flex items-center justify-between p-3 hover:bg-[var(--bg-muted)]/50 transition-colors text-left"
					>
						<div class="flex items-center gap-2.5 min-w-0">
							{#if isExpanded}
								<ChevronDown size={14} class="text-[var(--text-muted)] shrink-0" />
							{:else}
								<ChevronRight size={14} class="text-[var(--text-muted)] shrink-0" />
							{/if}
							<FolderGit2 size={15} class="text-[var(--text-muted)] shrink-0" />
							<span class="text-sm font-medium text-[var(--text-primary)] truncate">
								{project.encoded_name}
							</span>
						</div>
						<div class="flex items-center gap-3 shrink-0">
							{#if project.synced_at}
								<span class="text-[11px] text-[var(--text-muted)]">
									synced {formatRelativeTime(new Date(project.synced_at))}
								</span>
							{/if}
							<span class="text-xs text-[var(--text-muted)]">
								{project.session_count} session{project.session_count !== 1 ? 's' : ''}
							</span>
						</div>
					</button>

					<!-- Expanded session list -->
					{#if isExpanded}
						<div class="border-t border-[var(--border)]">
							{#if isLoading}
								<div class="flex items-center justify-center py-6">
									<Loader2 size={16} class="animate-spin text-[var(--text-muted)]" />
								</div>
							{:else if sessions.length === 0}
								<p class="py-4 text-center text-xs text-[var(--text-muted)]">
									No session details available
								</p>
							{:else}
								<div class="divide-y divide-[var(--border)]/50">
									{#each sessions as session (session.uuid)}
										<a
											href="/sessions/{session.uuid}?project={project.encoded_name}&source=remote&user={encodeURIComponent(profile.user_id)}"
											class="flex items-center justify-between px-4 py-2.5 hover:bg-[var(--bg-muted)]/30 transition-colors"
										>
											<div class="flex items-center gap-2 min-w-0">
												<FileText size={13} class="text-[var(--text-muted)] shrink-0" />
												<span class="text-xs font-mono text-[var(--text-secondary)] truncate">
													{session.uuid.substring(0, 8)}...
												</span>
												{#if session.worktree_name}
													<span class="px-1.5 py-0.5 text-[10px] font-medium rounded bg-[var(--bg-muted)] text-[var(--text-muted)]">
														{session.worktree_name}
													</span>
												{/if}
											</div>
											<div class="flex items-center gap-3 text-[11px] text-[var(--text-muted)] shrink-0">
												<span>{formatBytes(session.size_bytes)}</span>
												<span>{formatRelativeTime(new Date(session.mtime))}</span>
											</div>
										</a>
									{/each}
								</div>
							{/if}
						</div>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</div>
```

**Step 2: Type-check**

Run: `cd frontend && npm run check`

**Step 3: Commit**

```bash
git add frontend/src/lib/components/team/MemberSessionsTab.svelte
git commit -m "feat(member): add MemberSessionsTab with expandable project sessions"
```

---

### Task 6: Frontend — MemberTeamsTab Component

**Files:**
- Create: `frontend/src/lib/components/team/MemberTeamsTab.svelte`

**Context:** Shows team cards for each team this member belongs to. Follows `TeamCard.svelte` styling patterns — card with member count, project count, online count, plus a per-team project contribution breakdown for this member.

**Step 1: Create the component**

Write `frontend/src/lib/components/team/MemberTeamsTab.svelte`:

```svelte
<script lang="ts">
	import { Users, FolderGit2, Wifi, ChevronRight } from 'lucide-svelte';
	import type { MemberProfile, MemberTeam } from '$lib/api-types';

	interface Props {
		profile: MemberProfile;
	}

	let { profile }: Props = $props();
</script>

<div class="space-y-4">
	{#if profile.teams.length === 0}
		<p class="text-sm text-[var(--text-muted)] py-8 text-center">
			Not a member of any teams.
		</p>
	{:else}
		<p class="text-sm text-[var(--text-secondary)]">
			Member of {profile.teams.length} team{profile.teams.length !== 1 ? 's' : ''}
		</p>

		<div class="space-y-3">
			{#each profile.teams as team (team.name)}
				<a
					href="/team/{encodeURIComponent(team.name)}"
					class="block p-4 rounded-lg border border-[var(--border)] bg-[var(--bg-base)] hover:border-[var(--accent)]/30 hover:shadow-sm transition-all group"
				>
					<!-- Team header -->
					<div class="flex items-center justify-between mb-3">
						<h3 class="text-sm font-semibold text-[var(--text-primary)] group-hover:text-[var(--accent)] transition-colors">
							{team.name}
						</h3>
						<ChevronRight
							size={16}
							class="text-[var(--text-muted)] group-hover:text-[var(--accent)] group-hover:translate-x-0.5 transition-all"
						/>
					</div>

					<!-- Stats row -->
					<div class="flex items-center gap-4 text-xs text-[var(--text-muted)]">
						<span class="flex items-center gap-1">
							<Users size={12} />
							{team.member_count} member{team.member_count !== 1 ? 's' : ''}
						</span>
						<span class="flex items-center gap-1">
							<FolderGit2 size={12} />
							{team.project_count} project{team.project_count !== 1 ? 's' : ''}
						</span>
						{#if team.online_count > 0}
							<span class="flex items-center gap-1 text-[var(--success)]">
								<Wifi size={12} />
								{team.online_count} online
							</span>
						{/if}
					</div>

					<!-- Project contributions for this member -->
					{#if team.projects.length > 0}
						<div class="mt-3 pt-3 border-t border-[var(--border)]/50">
							<div class="flex flex-wrap gap-2">
								{#each team.projects as project (project.encoded_name)}
									<span class="inline-flex items-center gap-1.5 px-2 py-1 text-[11px] rounded-full bg-[var(--bg-muted)] text-[var(--text-secondary)]">
										{project.name || project.encoded_name}
										<span class="text-[var(--text-muted)]">
											{project.session_count}
										</span>
									</span>
								{/each}
							</div>
						</div>
					{/if}
				</a>
			{/each}
		</div>
	{/if}
</div>
```

**Step 2: Type-check**

Run: `cd frontend && npm run check`

**Step 3: Commit**

```bash
git add frontend/src/lib/components/team/MemberTeamsTab.svelte
git commit -m "feat(member): add MemberTeamsTab with team cards and project contributions"
```

---

### Task 7: Frontend — MemberActivityTab Component

**Files:**
- Create: `frontend/src/lib/components/team/MemberActivityTab.svelte`

**Context:** Reuses `TeamActivityFeed` component directly, passing the member-scoped activity events. The feed component already supports type filter pills and load-more pagination. We just need to wrap it and remove the member filter (since it's already scoped to one member). The `TeamActivityFeed` doesn't show member filter pills if `members` prop is empty/omitted, so we can just not pass it.

**Step 1: Create the component**

Write `frontend/src/lib/components/team/MemberActivityTab.svelte`:

```svelte
<script lang="ts">
	import { Loader2 } from 'lucide-svelte';
	import type { SyncEvent, MemberProfile } from '$lib/api-types';
	import { formatSyncEvent, syncEventColor, isSyncEventWarning, SYNC_EVENT_META } from '$lib/utils/sync-events';
	import { API_BASE } from '$lib/config';

	interface Props {
		profile: MemberProfile;
	}

	let { profile }: Props = $props();

	let events = $state<SyncEvent[]>([]);
	let loading = $state(false);
	let offset = $state(0);
	let hasMore = $state(false);
	let filterType = $state<string>('');

	// Initialize from profile data
	$effect(() => {
		events = profile.activity;
		offset = profile.activity.length;
		hasMore = profile.activity.length >= 50;
	});

	const typePills = [
		{ value: '', label: 'All' },
		{ value: 'member_joined', label: 'Joins' },
		{ value: 'project_shared', label: 'Shares' },
		{ value: 'session_packaged,session_received', label: 'Sessions' },
		{ value: 'sync_now', label: 'Syncs' },
		{ value: 'file_rejected', label: 'Rejections' },
		{ value: 'settings_changed', label: 'Settings' }
	];

	function formatEventTime(timestamp: string): string {
		const date = new Date(timestamp.replace(' ', 'T'));
		const now = new Date();
		const diffMs = now.getTime() - date.getTime();
		const diffSecs = Math.floor(diffMs / 1000);
		const diffMins = Math.floor(diffSecs / 60);
		const diffHours = Math.floor(diffMins / 60);
		const diffDays = Math.floor(diffHours / 24);

		if (diffSecs < 60) return 'just now';
		if (diffMins < 60) return `${diffMins}m ago`;
		if (diffHours < 24) return `${diffHours}h ago`;
		if (diffDays < 7) return `${diffDays}d ago`;

		return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
	}

	async function fetchEvents(append: boolean = false) {
		loading = true;
		try {
			// Query all teams this member belongs to — use first team for activity API
			// In practice, sync_events stores member_name globally so querying any team works
			// But we need to use the member-scoped endpoint from the backend
			const params = new URLSearchParams({ limit: '50', member_name: profile.user_id });
			if (filterType) params.set('event_type', filterType);
			if (append) params.set('offset', String(offset));

			// Use the first team for the activity endpoint
			const teamName = profile.teams[0]?.name;
			if (!teamName) return;

			const res = await fetch(
				`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/activity?${params}`
			);
			if (res.ok) {
				const data = await res.json();
				const newEvents: SyncEvent[] = data.events || [];
				if (append) {
					events = [...events, ...newEvents];
					offset += newEvents.length;
				} else {
					events = newEvents;
					offset = newEvents.length;
				}
				hasMore = newEvents.length >= 50;
			}
		} finally {
			loading = false;
		}
	}

	function selectTypeFilter(type: string) {
		filterType = type;
		fetchEvents();
	}
</script>

<div class="space-y-4">
	<section class="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)]">
		<!-- Header -->
		<div class="flex items-center justify-between px-4 pt-4 pb-3">
			<h3 class="text-sm font-medium text-[var(--text-primary)]">Activity</h3>
			{#if loading}
				<Loader2 size={14} class="animate-spin text-[var(--text-muted)]" />
			{/if}
		</div>

		<!-- Type filter pills -->
		<div class="flex flex-wrap gap-1.5 px-4 pb-3">
			{#each typePills as pill}
				<button
					class="px-2.5 py-1 text-xs font-medium rounded-full transition-colors
						{filterType === pill.value
							? 'bg-[var(--accent)] text-white'
							: 'bg-[var(--bg-muted)] text-[var(--text-muted)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-muted)]/80'}"
					onclick={() => selectTypeFilter(pill.value)}
				>
					{pill.label}
				</button>
			{/each}
		</div>

		<!-- Event list -->
		<div class="border-t border-[var(--border)]">
			{#if events.length === 0}
				<p class="py-8 text-center text-sm text-[var(--text-muted)]">No activity yet</p>
			{:else}
				<div class="divide-y divide-[var(--border)]/50">
					{#each events as event (event.id)}
						<div
							class="flex items-start gap-3 px-4 py-3 {isSyncEventWarning(event.event_type)
								? 'bg-[var(--warning)]/5'
								: 'hover:bg-[var(--bg-muted)]/50'} transition-colors"
						>
							<span class="mt-1.5 shrink-0 {syncEventColor(event.event_type)}">
								{#if isSyncEventWarning(event.event_type)}
									<svg
										class="h-3 w-3"
										fill="none"
										viewBox="0 0 24 24"
										stroke="currentColor"
										stroke-width="2.5"
									>
										<path
											d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z"
										/>
									</svg>
								{:else}
									<span class="block w-2 h-2 rounded-full bg-current"></span>
								{/if}
							</span>

							<div class="flex-1 min-w-0">
								<p class="text-sm text-[var(--text-primary)]">
									{formatSyncEvent(event)}
								</p>
								<div class="flex items-center gap-2 mt-1">
									<span class="text-[11px] text-[var(--text-muted)]">
										{formatEventTime(event.created_at)}
									</span>
									{#if event.team_name}
										<span class="inline-flex px-1.5 py-0.5 text-[10px] font-medium rounded-full bg-[var(--bg-muted)] text-[var(--text-muted)]">
											{event.team_name}
										</span>
									{/if}
									{#if event.event_type && SYNC_EVENT_META[event.event_type]}
										<span class="inline-flex px-1.5 py-0.5 text-[10px] font-medium rounded-full bg-[var(--bg-muted)] text-[var(--text-muted)]">
											{event.event_type.replace(/_/g, ' ')}
										</span>
									{/if}
								</div>
							</div>
						</div>
					{/each}
				</div>

				{#if hasMore}
					<div class="px-4 py-3 border-t border-[var(--border)]">
						<button
							class="w-full py-2 text-xs font-medium rounded-[var(--radius-md)]
								border border-[var(--border)] text-[var(--text-muted)]
								hover:text-[var(--text-secondary)] hover:bg-[var(--bg-muted)] transition-colors"
							onclick={() => fetchEvents(true)}
							disabled={loading}
						>
							{loading ? 'Loading...' : 'Load More'}
						</button>
					</div>
				{/if}
			{/if}
		</div>
	</section>
</div>
```

**Step 2: Type-check**

Run: `cd frontend && npm run check`

**Step 3: Commit**

```bash
git add frontend/src/lib/components/team/MemberActivityTab.svelte
git commit -m "feat(member): add MemberActivityTab with type-filtered activity feed"
```

---

### Task 8: Frontend — Member Page (`+page.svelte`)

**Files:**
- Create: `frontend/src/routes/members/[user_id]/+page.svelte`

**Context:** This is the main page component. Follows the team detail page pattern: PageHeader with breadcrumbs, color-themed profile card, bits-ui tabs with URL persistence. Imports all 4 tab components. No polling needed for v1 (member data doesn't change rapidly).

**Step 1: Create the page**

Write `frontend/src/routes/members/[user_id]/+page.svelte`:

```svelte
<script lang="ts">
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import { Tabs } from 'bits-ui';
	import TabsTrigger from '$lib/components/ui/TabsTrigger.svelte';
	import MemberOverviewTab from '$lib/components/team/MemberOverviewTab.svelte';
	import MemberSessionsTab from '$lib/components/team/MemberSessionsTab.svelte';
	import MemberTeamsTab from '$lib/components/team/MemberTeamsTab.svelte';
	import MemberActivityTab from '$lib/components/team/MemberActivityTab.svelte';
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import {
		User,
		LayoutDashboard,
		FolderGit2,
		Users,
		Activity,
		Wifi,
		WifiOff,
		AlertTriangle
	} from 'lucide-svelte';
	import { getTeamMemberColor, formatBytes } from '$lib/utils';

	let { data } = $props();

	// Tab state
	const validTabs = ['overview', 'sessions', 'teams', 'activity'];
	let activeTab = $state('overview');
	let tabsReady = $state(false);

	let profile = $derived(data.profile);
	let colors = $derived(getTeamMemberColor(data.userId));

	// Truncate device ID for display
	function truncateDeviceId(deviceId: string): string {
		if (deviceId.length <= 12) return deviceId;
		return deviceId.substring(0, 7) + '...' + deviceId.substring(deviceId.length - 4);
	}

	onMount(() => {
		const params = new URLSearchParams(window.location.search);
		const tab = params.get('tab');
		if (tab && validTabs.includes(tab)) activeTab = tab;
		tabsReady = true;

		const handlePopstate = () => {
			const p = new URLSearchParams(window.location.search);
			const t = p.get('tab');
			if (t && validTabs.includes(t)) activeTab = t;
		};
		window.addEventListener('popstate', handlePopstate);

		return () => {
			window.removeEventListener('popstate', handlePopstate);
		};
	});

	// URL sync
	$effect(() => {
		if (!browser || !tabsReady) return;
		const url = new URL(window.location.href);
		if (activeTab === 'overview') url.searchParams.delete('tab');
		else url.searchParams.set('tab', activeTab);
		history.replaceState({}, '', url.toString());
	});
</script>

<PageHeader
	title={data.userId}
	icon={User}
	iconColor="--nav-purple"
	subtitle="Member profile and activity"
	breadcrumbs={[
		{ label: 'Dashboard', href: '/' },
		{ label: 'Teams', href: '/team' },
		{ label: data.userId }
	]}
/>

{#if profile}
	<!-- Profile Card -->
	<div
		class="mb-6 p-4 rounded-lg border border-[var(--border)] bg-[var(--bg-base)]"
		style="border-left: 4px solid {colors.border}; background-color: {colors.bg};"
	>
		<div class="flex items-center gap-4">
			<!-- Avatar -->
			<div
				class="w-12 h-12 rounded-full flex items-center justify-center text-lg font-bold shrink-0"
				style="background-color: {colors.border}22; color: {colors.border}; border: 2px solid {colors.border};"
			>
				{data.userId.charAt(0).toUpperCase()}
			</div>

			<!-- Info -->
			<div class="flex-1 min-w-0">
				<div class="flex items-center gap-2 flex-wrap">
					<h2 class="text-base font-semibold text-[var(--text-primary)]">
						{data.userId}
					</h2>
					<span
						class="flex items-center gap-1 text-xs shrink-0 {profile.connected
							? 'text-[var(--success)]'
							: 'text-[var(--text-muted)]'}"
					>
						{#if profile.connected}
							<Wifi size={12} />
							Online
						{:else}
							<WifiOff size={12} />
							Offline
						{/if}
					</span>
				</div>

				<div class="flex items-center gap-3 mt-1 text-xs text-[var(--text-muted)]">
					<span class="font-mono" title={profile.device_id}>
						{truncateDeviceId(profile.device_id)}
					</span>
					{#if profile.in_bytes_total > 0 || profile.out_bytes_total > 0}
						<span>&darr; {formatBytes(profile.in_bytes_total)}</span>
						<span>&uarr; {formatBytes(profile.out_bytes_total)}</span>
					{/if}
				</div>
			</div>
		</div>
	</div>

	<!-- Tabs -->
	<Tabs.Root bind:value={activeTab} class="space-y-6">
		<Tabs.List class="flex gap-1 p-1 bg-[var(--bg-subtle)] border border-[var(--border)] rounded-lg w-fit mx-auto">
			<TabsTrigger value="overview" icon={LayoutDashboard}>Overview</TabsTrigger>
			<TabsTrigger value="sessions" icon={FolderGit2}>Sessions</TabsTrigger>
			<TabsTrigger value="teams" icon={Users}>Teams ({profile.teams.length})</TabsTrigger>
			<TabsTrigger value="activity" icon={Activity}>Activity</TabsTrigger>
		</Tabs.List>

		<Tabs.Content value="overview" class="mt-4">
			<MemberOverviewTab {profile} />
		</Tabs.Content>

		<Tabs.Content value="sessions" class="mt-4">
			<MemberSessionsTab {profile} />
		</Tabs.Content>

		<Tabs.Content value="teams" class="mt-4">
			<MemberTeamsTab {profile} />
		</Tabs.Content>

		<Tabs.Content value="activity" class="mt-4">
			<MemberActivityTab {profile} />
		</Tabs.Content>
	</Tabs.Root>
{:else}
	<div class="text-center py-16">
		<AlertTriangle size={32} class="mx-auto mb-3 text-[var(--warning)]" />
		<p class="text-[var(--text-primary)] font-medium">
			Member "{data.userId}" not found
		</p>
		{#if data.error}
			<p class="text-sm text-[var(--text-muted)] mt-1">{data.error}</p>
		{/if}
		<a href="/team" class="text-sm text-[var(--accent)] hover:underline mt-3 inline-block">
			Back to Teams
		</a>
	</div>
{/if}
```

**Step 2: Type-check**

Run: `cd frontend && npm run check`

**Step 3: Verify in browser**

Run: `cd frontend && npm run dev`

Navigate to `http://localhost:5173/members/{some_member_name}`. Verify:
- Profile card renders with member color
- All 4 tabs load and switch correctly
- URL updates with `?tab=` parameter
- Back button restores tab state
- 404 state shows for unknown members

**Step 4: Commit**

```bash
git add frontend/src/routes/members/\[user_id\]/+page.svelte
git commit -m "feat(member): add member detail page with color-themed profile and tabbed layout"
```

---

### Task 9: Frontend — Link TeamMembersTab Cards to Member Page

**Files:**
- Modify: `frontend/src/lib/components/team/TeamMembersTab.svelte`

**Context:** Wrap each member card in the grid with an `<a>` tag linking to `/members/{member.name}`. The card itself keeps its current styling — we just make it clickable. Follow the same pattern as `TeamCard.svelte` which wraps content in an `<a>` tag.

**Step 1: Make member cards linkable**

In `TeamMembersTab.svelte`, change the member card `<div>` (line 92-94) to an `<a>` tag:

Replace the existing card wrapper:
```svelte
				<div
					class="relative flex flex-col gap-2 p-3 rounded-lg border border-[var(--border)] bg-[var(--bg-base)]"
					style="border-left: 3px solid {colors.border};"
				>
```

With:
```svelte
				<a
					href="/members/{encodeURIComponent(member.name)}"
					class="relative flex flex-col gap-2 p-3 rounded-lg border border-[var(--border)] bg-[var(--bg-base)] hover:border-[var(--accent)]/30 hover:shadow-sm transition-all"
					style="border-left: 3px solid {colors.border};"
				>
```

And change the corresponding closing `</div>` (line 179) to `</a>`.

**Step 2: Prevent link navigation when clicking remove buttons**

The remove button is inside the `<a>` tag, so we need to stop propagation. Add `onclick|preventDefault|stopPropagation` to the remove button and confirm buttons. In Svelte 5, use `onclick={(e) => { e.preventDefault(); e.stopPropagation(); ... }}` pattern.

Update the remove button (around line 167):
```svelte
									<button
										onclick={(e) => { e.preventDefault(); e.stopPropagation(); confirmRemove = member.name; }}
```

Update the confirm Remove button (around line 149):
```svelte
										<button
											onclick={(e) => { e.preventDefault(); e.stopPropagation(); handleRemove(member.name); }}
```

Update the confirm Cancel button (around line 160):
```svelte
										<button
											onclick={(e) => { e.preventDefault(); e.stopPropagation(); confirmRemove = null; }}
```

**Step 3: Type-check and verify**

Run: `cd frontend && npm run check`

Verify in browser: navigate to a team page, click a member card, confirm it navigates to `/members/{name}`. Verify the remove button still works without navigating away.

**Step 4: Commit**

```bash
git add frontend/src/lib/components/team/TeamMembersTab.svelte
git commit -m "feat(team): link member cards to /members/[user_id] detail page"
```

---

### Task 10: Verify End-to-End and Fix Issues

**Step 1: Run type checker**

Run: `cd frontend && npm run check`

Fix any TypeScript errors.

**Step 2: Run linter**

Run: `cd frontend && npm run lint`

Fix any lint issues.

**Step 3: Run backend**

Run: `cd api && uvicorn main:app --reload --port 8000`

**Step 4: Manual browser testing**

Test the full flow:
1. Go to `/team/{name}` → Members tab → click a member → lands on `/members/{user_id}`
2. Verify profile card shows correct color, name, device ID, connection status
3. Switch between all 4 tabs — verify content loads
4. Verify URL updates with `?tab=` parameter
5. Use browser back/forward — tabs should restore
6. Try unknown member — should show 404 state
7. Verify overview chart renders (if session stats exist)
8. Verify sessions tab expands projects to show sessions
9. Verify teams tab shows correct team cards with project badges
10. Verify activity tab filters by event type

**Step 5: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix(member): address issues found during end-to-end testing"
```
