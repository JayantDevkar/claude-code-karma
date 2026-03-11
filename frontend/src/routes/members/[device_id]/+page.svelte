<script lang="ts">
	import { Tabs } from 'bits-ui';
	import TabsTrigger from '$lib/components/ui/TabsTrigger.svelte';
	import MemberOverviewTab from '$lib/components/team/MemberOverviewTab.svelte';
	import MemberSessionsTab from '$lib/components/team/MemberSessionsTab.svelte';
	import MemberTeamsTab from '$lib/components/team/MemberTeamsTab.svelte';
	import MemberActivityTab from '$lib/components/team/MemberActivityTab.svelte';
	import MemberSettingsTab from '$lib/components/team/MemberSettingsTab.svelte';
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import {
		LayoutDashboard,
		FolderGit2,
		Users,
		Activity,
		Settings,
		Wifi,
		WifiOff,
		AlertTriangle,
		Monitor,
		ArrowDownUp,
		Clock
	} from 'lucide-svelte';
	import { getTeamMemberHexColor, formatBytes, formatRelativeTime, formatDate } from '$lib/utils';

	let { data } = $props();

	// Tab state
	const validTabs = ['overview', 'sessions', 'teams', 'activity', 'settings'];
	let activeTab = $state('overview');
	let tabsReady = $state(false);

	let displayName = $derived(data.profile?.user_id ?? data.deviceId);
	let hexColor = $derived(getTeamMemberHexColor(displayName));
	let profile = $derived(data.profile);

	// Inline stats
	let lastActiveRelative = $derived(
		profile?.stats.last_active
			? formatRelativeTime(profile.stats.last_active.replace(' ', 'T'))
			: null
	);
	let lastActiveFormatted = $derived(
		profile?.stats.last_active
			? formatDate(profile.stats.last_active.replace(' ', 'T'))
			: null
	);

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
		window.history.replaceState(window.history.state, '', url.toString());
	});
</script>

<!-- Scoped member theme via CSS custom properties -->
<div
	style="--member-color: {hexColor}; --member-color-subtle: {hexColor}15; --member-color-border: {hexColor}40; --member-color-muted: {hexColor}0a; --member-color-wash: {hexColor}08;"
>

<!-- Breadcrumb -->
<div class="flex items-center gap-2 text-xs text-[var(--text-secondary)] mb-4">
	<a href="/" class="hover:text-[var(--text-primary)] transition-colors">Dashboard</a>
	<span class="text-[var(--text-faint)]">/</span>
	<a href="/members" class="hover:text-[var(--text-primary)] transition-colors">Members</a>
	<span class="text-[var(--text-faint)]">/</span>
	<span class="text-[var(--member-color)] font-medium">{displayName}</span>
</div>

{#if profile}
	<!-- Profile Header -->
	<div class="mb-6 pb-6 border-b border-[var(--border)]">
		<div class="flex items-start gap-4">
			<!-- Avatar icon box -->
			<div
				class="inline-flex items-center justify-center w-12 h-12 border rounded-[var(--radius-md)] shrink-0 text-lg font-bold
					bg-[var(--member-color-subtle)] border-[var(--member-color-border)] text-[var(--member-color)]"
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
						<span
							class="shrink-0 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide rounded-full
								bg-[var(--member-color-subtle)] text-[var(--member-color)]"
						>
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

				<!-- Metadata row -->
				<div class="flex items-center gap-3 text-xs text-[var(--text-muted)] flex-wrap">
					<span class="flex items-center gap-1.5" title={profile.device_id}>
						<Monitor size={12} strokeWidth={2} />
						{profile.device_id.slice(0, 8)}...
					</span>
					<span class="text-[var(--text-faint)]">&middot;</span>
					<span class="flex items-center gap-1.5">
						<ArrowDownUp size={12} strokeWidth={2} />
						{formatBytes(profile.in_bytes_total)} in / {formatBytes(profile.out_bytes_total)} out
					</span>
					{#if lastActiveRelative}
						<span class="text-[var(--text-faint)]">&middot;</span>
						<span class="flex items-center gap-1.5" title={lastActiveFormatted}>
							<Clock size={12} strokeWidth={2} />
							Active {lastActiveRelative}
						</span>
					{/if}
				</div>
			</div>
		</div>
	</div>

	<!-- Tabs -->
	<Tabs.Root bind:value={activeTab} class="space-y-5">
		<Tabs.List class="flex gap-1 p-1 bg-[var(--bg-subtle)] border border-[var(--border)] rounded-lg w-fit mx-auto">
			<TabsTrigger value="overview" icon={LayoutDashboard}>Overview</TabsTrigger>
			<TabsTrigger value="sessions" icon={FolderGit2}>Sessions ({profile.stats.sessions_sent})</TabsTrigger>
			<TabsTrigger value="teams" icon={Users}>Teams ({profile.teams.length})</TabsTrigger>
			<TabsTrigger value="activity" icon={Activity}>Activity</TabsTrigger>
			<TabsTrigger value="settings" icon={Settings}>Settings</TabsTrigger>
		</Tabs.List>

		<Tabs.Content value="overview">
			<MemberOverviewTab {profile} />
		</Tabs.Content>

		<Tabs.Content value="sessions">
			<MemberSessionsTab {profile} />
		</Tabs.Content>

		<Tabs.Content value="teams">
			<MemberTeamsTab {profile} />
		</Tabs.Content>

		<Tabs.Content value="activity">
			<MemberActivityTab {profile} />
		</Tabs.Content>

		<Tabs.Content value="settings">
			<MemberSettingsTab {profile} />
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

</div>
