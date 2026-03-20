<script lang="ts">
	import { Tabs } from 'bits-ui';
	import TabsTrigger from '$lib/components/ui/TabsTrigger.svelte';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import MemberOverviewTab from '$lib/components/team/MemberOverviewTab.svelte';
	import MemberSessionsTab from '$lib/components/team/MemberSessionsTab.svelte';
	import MemberTeamsTab from '$lib/components/team/MemberTeamsTab.svelte';
	import MemberActivityTab from '$lib/components/team/MemberActivityTab.svelte';
	import MemberSettingsTab from '$lib/components/team/MemberSettingsTab.svelte';
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import {
		Contact,
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
	import { getTeamMemberHexColor, formatRelativeTime } from '$lib/utils';

	let { data } = $props();

	// Tab state
	const validTabs = ['overview', 'sessions', 'teams', 'activity', 'settings'];
	let activeTab = $state('overview');
	let tabsReady = $state(false);

	let displayName = $derived(data.profile?.user_id ?? data.memberTag);
	let hexColor = $derived(getTeamMemberHexColor(displayName));
	let profile = $derived(data.profile);

	// Last packaged relative time (for self sync health)
	let lastPackagedRelative = $derived(
		profile?.last_packaged_at
			? formatRelativeTime(profile.last_packaged_at.replace(' ', 'T'))
			: null
	);

	// Metadata items for PageHeader
	let metadataItems = $derived.by(() => {
		if (!profile) return [];
		const items: { icon?: typeof Monitor; text: string; class?: string }[] = [
			{ icon: Contact, text: profile.member_tag },
			{ icon: Monitor, text: `Machine: ${profile.machine_tag}` },
			{ icon: Users, text: `${profile.teams.length} team${profile.teams.length === 1 ? '' : 's'}` }
		];
		if (profile.is_you) {
			// Unsynced count
			if (profile.unsynced_count !== null) {
				if (profile.unsynced_count > 0) {
					items.push({
						icon: AlertTriangle,
						text: `${profile.unsynced_count} unsynced`,
						class: 'text-[var(--warning)]'
					});
				} else {
					items.push({ text: 'All synced', class: 'text-[var(--success)]' });
				}
			}
			// Sync direction
			if (profile.sync_direction !== null) {
				items.push({ icon: ArrowDownUp, text: `Direction: ${profile.sync_direction}` });
			}
			// Last synced
			if (lastPackagedRelative) {
				items.push({ icon: Clock, text: `Last synced: ${lastPackagedRelative}` });
			}
		}
		return items;
	});

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

<PageHeader
	title={displayName}
	icon={Contact}
	iconColorRaw={{ color: hexColor, subtle: `${hexColor}15` }}
	breadcrumbs={[
		{ label: 'Dashboard', href: '/' },
		{ label: 'Members', href: '/members' },
		{ label: profile?.user_id ?? data.memberTag, tooltip: profile?.member_tag }
	]}
	metadata={metadataItems}
>
	{#snippet badges()}
		{#if profile?.is_you}
			<span
				class="shrink-0 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide rounded-full
					bg-[var(--member-color-subtle)] text-[var(--member-color)]"
			>
				You
			</span>
		{/if}
		{#if profile}
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
		{/if}
	{/snippet}
</PageHeader>

{#if profile}
	<!-- Tabs -->
	<Tabs.Root bind:value={activeTab} class="space-y-5">
		<Tabs.List class="flex gap-1 p-1 bg-[var(--bg-subtle)] border border-[var(--border)] rounded-lg w-fit mx-auto max-w-full overflow-x-auto">
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
