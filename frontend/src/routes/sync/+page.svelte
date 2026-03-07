<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { RefreshCw, LayoutDashboard, Users, FolderGit2, Activity } from 'lucide-svelte';
	import type { SyncDetect, SyncStatusResponse, SyncTeam } from '$lib/api-types';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import SetupWizard from '$lib/components/sync/SetupWizard.svelte';
	import OverviewTab from '$lib/components/sync/OverviewTab.svelte';
	import MembersTab from '$lib/components/sync/MembersTab.svelte';
	import ProjectsTab from '$lib/components/sync/ProjectsTab.svelte';
	import ActivityTab from '$lib/components/sync/ActivityTab.svelte';
	import TeamSelector from '$lib/components/sync/TeamSelector.svelte';
	import Tabs from '$lib/components/ui/Tabs.svelte';
	import TabsList from '$lib/components/ui/TabsList.svelte';
	import TabsTrigger from '$lib/components/ui/TabsTrigger.svelte';
	import TabsContent from '$lib/components/ui/TabsContent.svelte';
	import { POLLING_INTERVALS, API_BASE } from '$lib/config';

	let { data } = $props();

	let syncDetect = $state<SyncDetect | null>(data.detect ?? null);
	let syncStatus = $state<SyncStatusResponse | null>(data.status ?? null);

	let activeTab = $state(data.activeTab ?? 'overview');

	// ── Team selection ───────────────────────────────────────────────────────
	let activeTeamName = $state('');

	// Derive teams array from syncStatus.teams Record
	let teamsList = $derived.by<SyncTeam[]>(() => {
		if (!syncStatus?.teams) return [];
		return Object.entries(syncStatus.teams).map(([name, entry]) => ({
			name,
			backend: entry.backend ?? 'syncthing',
			projects: [],
			members: [],
			member_count: entry.member_count ?? 0,
			project_count: entry.project_count ?? 0
		}));
	});

	// Auto-select first team when data loads or current selection becomes invalid
	$effect(() => {
		const teams = teamsList;
		if (teams.length === 0) {
			activeTeamName = '';
		} else if (!activeTeamName || !teams.some((t) => t.name === activeTeamName)) {
			activeTeamName = teams[0].name;
		}
	});

	function handleCreateTeam() {
		// Switch to overview tab — OverviewTab handles team creation flow
		activeTab = 'overview';
	}

	let pollInterval: ReturnType<typeof setInterval> | null = null;
	let isFetching = $state(false);
	let abortController: AbortController | null = null;
	let lastUpdated = $state<Date | null>(null);

	// Seconds since last update for display
	let secondsSinceUpdate = $state(0);
	let clockInterval: ReturnType<typeof setInterval> | null = null;

	// Sync active tab to URL (only react to activeTab, not $page.url)
	$effect(() => {
		const tab = activeTab;
		// Use untrack to avoid reading $page.url reactively
		const url = new URL(window.location.href);
		if (tab) {
			url.searchParams.set('tab', tab);
		} else {
			url.searchParams.delete('tab');
		}
		history.replaceState(null, '', url.toString());
	});

	async function refreshData() {
		if (isFetching) return;
		isFetching = true;
		abortController?.abort();
		abortController = new AbortController();
		try {
			const [detectRes, statusRes] = await Promise.all([
				fetch(`${API_BASE}/sync/detect`, { signal: abortController.signal }),
				fetch(`${API_BASE}/sync/status`, { signal: abortController.signal })
			]);
			if (detectRes.ok) syncDetect = await detectRes.json();
			if (statusRes.ok) syncStatus = await statusRes.json();
			lastUpdated = new Date();
			secondsSinceUpdate = 0;
		} catch (e) {
			if (e instanceof DOMException && e.name === 'AbortError') return;
		} finally {
			isFetching = false;
		}
	}

	onMount(() => {
		lastUpdated = new Date();
		pollInterval = setInterval(refreshData, POLLING_INTERVALS.SYNC_STATUS);
		clockInterval = setInterval(() => {
			if (lastUpdated) {
				secondsSinceUpdate = Math.floor((Date.now() - lastUpdated.getTime()) / 1000);
			}
		}, 1000);
	});

	onDestroy(() => {
		if (pollInterval) clearInterval(pollInterval);
		if (clockInterval) clearInterval(clockInterval);
		abortController?.abort();
	});
</script>

<div class="max-w-4xl mx-auto pb-12">
	<PageHeader
		title="Sync"
		icon={RefreshCw}
		iconColor="--nav-purple"
		breadcrumbs={[{ label: 'Dashboard', href: '/' }, { label: 'Sync' }]}
	>
		{#snippet headerRight()}
			<div class="flex items-center gap-3">
				{#if lastUpdated}
					<span class="text-xs text-[var(--text-muted)]">
						Last updated: {secondsSinceUpdate}s ago
					</span>
				{/if}
				<button
					onclick={refreshData}
					disabled={isFetching}
					class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
				>
					<RefreshCw size={12} class={isFetching ? 'animate-spin' : ''} />
					Refresh
				</button>
			</div>
		{/snippet}
	</PageHeader>

	{#if !syncStatus?.configured}
		<SetupWizard bind:detect={syncDetect} bind:status={syncStatus} ondone={refreshData} />
	{:else}
		<Tabs bind:value={activeTab}>
			<TabsList>
				<TabsTrigger value="overview" icon={LayoutDashboard}>Overview</TabsTrigger>
				<TabsTrigger value="members" icon={Users}>Members</TabsTrigger>
				<TabsTrigger value="projects" icon={FolderGit2}>Projects</TabsTrigger>
				<TabsTrigger value="activity" icon={Activity}>Activity</TabsTrigger>
			</TabsList>

			<TeamSelector teams={teamsList} bind:activeTeam={activeTeamName} oncreate={handleCreateTeam} />

			<TabsContent value="overview">
				<OverviewTab detect={syncDetect} status={syncStatus} active={activeTab === 'overview'} teamName={activeTeamName} onteamchange={refreshData} />
			</TabsContent>

			<TabsContent value="members">
				<MembersTab detect={syncDetect} active={activeTab === 'members'} teamName={activeTeamName} />
			</TabsContent>

			<TabsContent value="projects">
				<ProjectsTab active={activeTab === 'projects'} teamName={activeTeamName} />
			</TabsContent>

			<TabsContent value="activity">
				<ActivityTab active={activeTab === 'activity'} />
			</TabsContent>
		</Tabs>
	{/if}
</div>
