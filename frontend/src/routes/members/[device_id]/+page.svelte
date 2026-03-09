<script lang="ts">
	import { Tabs } from 'bits-ui';
	import TabsTrigger from '$lib/components/ui/TabsTrigger.svelte';
	import MemberOverviewTab from '$lib/components/team/MemberOverviewTab.svelte';
	import MemberSessionsTab from '$lib/components/team/MemberSessionsTab.svelte';
	import MemberTeamsTab from '$lib/components/team/MemberTeamsTab.svelte';
	import MemberActivityTab from '$lib/components/team/MemberActivityTab.svelte';
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import {
		LayoutDashboard,
		FolderGit2,
		Users,
		Activity,
		Wifi,
		WifiOff,
		AlertTriangle,
		Monitor,
		ArrowDownUp
	} from 'lucide-svelte';
	import { getTeamMemberColor, formatBytes } from '$lib/utils';

	let { data } = $props();

	// Tab state
	const validTabs = ['overview', 'sessions', 'teams', 'activity'];
	let activeTab = $state('overview');
	let tabsReady = $state(false);

	let displayName = $derived(data.profile?.user_id ?? data.deviceId);
	let colors = $derived(getTeamMemberColor(displayName));
	let profile = $derived(data.profile);

	onMount(() => {
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
			window.removeEventListener('popstate', handlePopstate);
		};
	});

	// URL sync effect
	$effect(() => {
		if (!browser || !tabsReady) return;
		const url = new URL(window.location.href);
		if (activeTab === 'overview') url.searchParams.delete('tab');
		else url.searchParams.set('tab', activeTab);
		history.replaceState({}, '', url.toString());
	});
</script>

<!-- Breadcrumb -->
<div class="flex items-center gap-2 text-xs text-[var(--text-secondary)] mb-5">
	<a href="/" class="hover:text-[var(--text-primary)] transition-colors">Dashboard</a>
	<span class="text-[var(--text-faint)]">/</span>
	<a href="/members" class="hover:text-[var(--text-primary)] transition-colors">Members</a>
	<span class="text-[var(--text-faint)]">/</span>
	<span class="text-[var(--text-primary)] font-medium">{displayName}</span>
</div>

{#if profile}
	<!-- Unified Profile Header -->
	<div class="mb-8 pb-6 border-b border-[var(--border)]">
		<div class="flex items-center gap-5">
			<!-- Avatar -->
			<div
				class="w-16 h-16 rounded-2xl flex items-center justify-center text-2xl font-bold shrink-0"
				style="background: {colors.border}; color: white;"
			>
				{displayName.charAt(0).toUpperCase()}
			</div>

			<!-- Name + metadata -->
			<div class="flex-1 min-w-0">
				<div class="flex items-center gap-2.5 mb-1.5">
					<h1 class="text-2xl font-semibold tracking-tight text-[var(--text-primary)] truncate">
						{displayName}
					</h1>
					{#if profile.is_you}
						<span class="shrink-0 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide rounded-full bg-[var(--accent)]/10 text-[var(--accent)]">
							You
						</span>
					{/if}
					{#if profile.connected || profile.is_you}
						<span class="flex items-center gap-1 text-xs font-medium text-[var(--success)]">
							<Wifi size={12} />
							Online
						</span>
					{:else}
						<span class="flex items-center gap-1 text-xs text-[var(--text-muted)]">
							<WifiOff size={12} />
							Offline
						</span>
					{/if}
				</div>

				<div class="flex items-center gap-3 text-xs text-[var(--text-muted)]">
					<span class="flex items-center gap-1.5" title={profile.device_id}>
						<Monitor size={11} class="opacity-60" />
						{profile.device_id.slice(0, 8)}...
					</span>
					<span class="text-[var(--text-faint)]">&middot;</span>
					<span class="flex items-center gap-1.5">
						<ArrowDownUp size={11} class="opacity-60" />
						{formatBytes(profile.in_bytes_total)} in / {formatBytes(profile.out_bytes_total)} out
					</span>
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
		<p class="text-[var(--text-primary)] font-medium">Member not found</p>
		{#if data.error}
			<p class="text-sm text-[var(--text-muted)] mt-1">{data.error}</p>
		{/if}
		<a href="/members" class="text-sm text-[var(--accent)] hover:underline mt-2 inline-block">
			Back to Members
		</a>
	</div>
{/if}
