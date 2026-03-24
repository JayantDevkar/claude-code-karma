<script lang="ts">
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import { Tabs } from 'bits-ui';
	import TabsTrigger from '$lib/components/ui/TabsTrigger.svelte';
	import TeamOverviewTab from '$lib/components/team/TeamOverviewTab.svelte';
	import TeamMembersTab from '$lib/components/team/TeamMembersTab.svelte';
	import TeamProjectsTab from '$lib/components/team/TeamProjectsTab.svelte';
	import TeamActivityTab from '$lib/components/team/TeamActivityTab.svelte';
	import { API_BASE } from '$lib/config';
	import { POLLING_INTERVALS } from '$lib/config';
	import { invalidateAll } from '$app/navigation';
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import {
		Users,
		Contact,
		FolderSync,
		Loader2,
		AlertTriangle,
		RefreshCw,
		LayoutDashboard,
		Activity,
		Settings
	} from 'lucide-svelte';
	import type { SyncTeam, SyncEvent } from '$lib/api-types';

	let { data } = $props();

	let deleteConfirm = $state(false);
	let deleting = $state(false);
	let deleteError = $state<string | null>(null);
	let isRefreshing = $state(false);

	// Tab state
	const validTabs = ['overview', 'members', 'projects', 'activity', 'settings'];
	let activeTab = $state('overview');
	let tabsReady = $state(false);

	// Team data — $state so polling can update it directly
	let team = $state<SyncTeam | null>(null);
	let teamEverLoaded = $state(false);
	$effect(() => {
		team = data.team ?? null;
		if (data.team) teamEverLoaded = true;
	});
	let members = $derived(team?.members ?? []);
	let projects = $derived(team?.projects ?? []);
	let subscriptions = $derived(team?.subscriptions ?? []);

	// Activity feed
	let activity = $state<SyncEvent[]>([]);
	$effect(() => { activity = data.activity ?? []; });

	let memberTag = $derived(data.syncStatus?.member_tag);

	// Offered subscription count — driven by DB subscriptions, not Syncthing pending folders
	let offeredCount = $derived(
		subscriptions.filter(s => s.member_tag === memberTag && s.status === 'offered').length
	);

	// Fetch all team data (used by both polling and manual refresh)
	async function fetchTeamData(signal?: AbortSignal) {
		const teamNameEnc = encodeURIComponent(data.teamName);
		const [teamRes, activityRes] = await Promise.all([
			fetch(`${API_BASE}/sync/teams/${teamNameEnc}`, { signal }),
			fetch(`${API_BASE}/sync/teams/${teamNameEnc}/activity?limit=20`, { signal })
		]);

		if (teamRes.ok) {
			const td: SyncTeam = await teamRes.json();
			team = td;
		}
		if (activityRes.ok) {
			const ad = await activityRes.json();
			activity = ad.events ?? [];
		}
	}

	// Poll for team data and activity
	onMount(() => {
		let controller = new AbortController();
		let retryCount = 0;
		let fastRetryTimer: ReturnType<typeof setTimeout> | null = null;

		// Fast retry when team isn't loaded yet (e.g. just accepted invitation)
		async function fastRetryIfNeeded() {
			if (team || teamEverLoaded || retryCount >= 10) return;
			retryCount++;
			try {
				// Trigger reconciliation to pick up freshly synced metadata
				await fetch(`${API_BASE}/sync/reconcile`, { method: 'POST' }).catch(() => {});
				await fetchTeamData();
			} catch { /* ignore */ }
			if (!team && retryCount < 10) {
				fastRetryTimer = setTimeout(fastRetryIfNeeded, 3000);
			}
		}
		if (!team) fastRetryTimer = setTimeout(fastRetryIfNeeded, 2000);

		const interval = setInterval(async () => {
			controller.abort();
			controller = new AbortController();
			try {
				await fetchTeamData(controller.signal);
			} catch (e) {
				if (e instanceof DOMException && e.name === 'AbortError') return;
			}
		}, POLLING_INTERVALS.SYNC_STATUS);

		// Tab URL persistence
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
			clearInterval(interval);
			if (fastRetryTimer) clearTimeout(fastRetryTimer);
			controller.abort();
			window.removeEventListener('popstate', handlePopstate);
		};
	});

	// URL sync effect
	$effect(() => {
		if (!browser || !tabsReady) return;
		const url = new URL(window.location.href);
		if (activeTab === 'overview') url.searchParams.delete('tab');
		else url.searchParams.set('tab', activeTab);
		window.history.replaceState(window.history.state, '', url.toString());
	});

	let isLeader = $derived(
		!!memberTag && team?.leader_member_tag === memberTag
	);

	async function handleLeaveTeam() {
		if (deleting) return;
		deleting = true;
		deleteError = null;
		try {
			// Leader dissolves; non-leader leaves
			const url = isLeader
				? `${API_BASE}/sync/teams/${encodeURIComponent(data.teamName)}`
				: `${API_BASE}/sync/teams/${encodeURIComponent(data.teamName)}/leave`;
			const res = await fetch(url, { method: isLeader ? 'DELETE' : 'POST' });
			if (res.ok) {
				window.location.href = '/team';
			} else {
				const body = await res.json().catch(() => ({}));
				if (res.status === 409) {
					deleteError = 'Team is already dissolved.';
				} else {
					deleteError = body.detail || `Failed (${res.status})`;
				}
			}
		} catch {
			deleteError = 'Network error.';
		} finally {
			deleting = false;
		}
	}

	async function handleRefresh() {
		if (isRefreshing) return;
		isRefreshing = true;
		try {
			await fetchTeamData();
		} catch {
			invalidateAll();
		} finally {
			isRefreshing = false;
		}
	}
</script>

<PageHeader
	title={data.teamName}
	icon={Users}
	iconColor="--nav-indigo"
	subtitle="Team members, shared projects, and sync status"
	breadcrumbs={[
		{ label: 'Dashboard', href: '/' },
		{ label: 'Teams', href: '/team' },
		{ label: data.teamName }
	]}
>
	{#snippet headerRight()}
		<div class="flex items-center gap-2">
			{#if team}
				<span class="px-2 py-1 text-[11px] font-medium rounded-full
					{team.status === 'active'
						? 'bg-[var(--success)]/10 text-[var(--success)] border border-[var(--success)]/20'
						: 'bg-[var(--error)]/10 text-[var(--error)] border border-[var(--error)]/20'}">
					{team.status}
				</span>
			{/if}
			<button
				onclick={handleRefresh}
				disabled={isRefreshing}
				class="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-[var(--radius-md)] border border-[var(--border)]
					text-[var(--text-secondary)] hover:bg-[var(--bg-muted)] transition-colors
					disabled:opacity-50 disabled:cursor-not-allowed"
			>
				<RefreshCw size={14} class={isRefreshing ? 'animate-spin' : ''} />
				Refresh
			</button>
		</div>
	{/snippet}
</PageHeader>

{#if team}
	<Tabs.Root bind:value={activeTab} class="space-y-6">
		<Tabs.List class="flex gap-1 p-1 bg-[var(--bg-subtle)] border border-[var(--border)] rounded-lg w-fit mx-auto max-w-full overflow-x-auto">
			<TabsTrigger value="overview" icon={LayoutDashboard}>Overview</TabsTrigger>
			<TabsTrigger value="members" icon={Contact}>Members ({members.filter(m => m.member_tag !== memberTag).length})</TabsTrigger>
			<TabsTrigger value="projects" icon={FolderSync}>
				Projects ({projects.length})
				{#if offeredCount > 0}
					<span class="ml-1 px-1.5 py-0.5 text-[10px] font-bold rounded-full bg-[var(--warning)] text-[var(--bg-base)]">{offeredCount}</span>
				{/if}
			</TabsTrigger>
			<TabsTrigger value="activity" icon={Activity}>Activity</TabsTrigger>
			<TabsTrigger value="settings" icon={Settings}>Settings</TabsTrigger>
		</Tabs.List>

		<Tabs.Content value="overview" class="mt-4">
			<TeamOverviewTab
				{team}
				teamName={data.teamName}
				{memberTag}
				onswitchtab={(tab) => activeTab = tab}
				offeredSubscriptionCount={offeredCount}
			/>
		</Tabs.Content>

		<Tabs.Content value="members" class="mt-4">
			<TeamMembersTab
				{members}
				teamName={data.teamName}
				{memberTag}
				{isLeader}
				onrefresh={handleRefresh}
			/>
		</Tabs.Content>

		<Tabs.Content value="projects" class="mt-4">
			<TeamProjectsTab
				{projects}
				teamName={data.teamName}
				{subscriptions}
				{memberTag}
				{isLeader}
				allProjects={data.allProjects}
				onrefresh={handleRefresh}
			/>
		</Tabs.Content>

		<Tabs.Content value="activity" class="mt-4">
			<TeamActivityTab
				teamName={data.teamName}
				{activity}
				{members}
			/>
		</Tabs.Content>

		<Tabs.Content value="settings" class="mt-4">
			<div class="space-y-6">
				<!-- Team Actions -->
				<div class="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)] p-5 space-y-4">
					<h3 class="text-sm font-semibold text-[var(--text-primary)]">Team Actions</h3>

					{#if deleteConfirm}
						<!-- Confirmation card -->
						<div class="flex items-center gap-3 p-4 rounded-lg border border-[var(--error)]/20 bg-[var(--error)]/5">
							<AlertTriangle size={16} class="text-[var(--error)] shrink-0" />
							<p class="text-sm text-[var(--text-primary)] flex-1">
								{#if isLeader}
									Dissolve team "{data.teamName}"? This will remove all members, stop syncing, and clean up Syncthing folders for everyone.
								{:else}
									Leave team "{data.teamName}"? This will stop syncing with all members and clean up Syncthing folders on this machine.
								{/if}
							</p>
							<div class="flex items-center gap-2 shrink-0">
								<button onclick={handleLeaveTeam} disabled={deleting}
									class="px-3 py-1.5 text-xs font-medium rounded bg-[var(--error)] text-white hover:bg-[var(--error)]/80 transition-colors disabled:opacity-50">
									{#if deleting}<Loader2 size={12} class="animate-spin" />{:else}{isLeader ? 'Dissolve' : 'Leave'}{/if}
								</button>
								<button onclick={() => { deleteConfirm = false; deleteError = null; }}
									class="px-3 py-1.5 text-xs rounded text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition-colors">
									Cancel
								</button>
							</div>
						</div>
						{#if deleteError}
							<p class="text-xs text-[var(--error)]" aria-live="polite">{deleteError}</p>
						{/if}
					{:else}
						<button onclick={() => deleteConfirm = true}
							class="px-4 py-2 text-sm font-medium rounded-[var(--radius-md)] border border-[var(--error)]/30
								text-[var(--error)] hover:bg-[var(--error)]/5 transition-colors">
							{isLeader ? 'Dissolve Team' : 'Leave Team'}
						</button>
					{/if}
				</div>
			</div>
		</Tabs.Content>
	</Tabs.Root>
{:else if !teamEverLoaded}
	<div class="text-center py-16">
		<Loader2 size={32} class="mx-auto mb-3 text-[var(--accent)] animate-spin" />
		<p class="text-[var(--text-primary)] font-medium">Setting up "{data.teamName}"...</p>
		<p class="text-sm text-[var(--text-muted)] mt-1">Waiting for team metadata to sync</p>
	</div>
{:else}
	<div class="text-center py-16">
		<AlertTriangle size={32} class="mx-auto mb-3 text-[var(--warning)]" />
		<p class="text-[var(--text-primary)] font-medium">Team "{data.teamName}" not found</p>
		<a href="/team" class="text-sm text-[var(--accent)] hover:underline mt-2 inline-block">
			Back to Teams
		</a>
	</div>
{/if}
