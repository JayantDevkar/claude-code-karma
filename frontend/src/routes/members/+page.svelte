<script lang="ts">
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import StatsGrid from '$lib/components/StatsGrid.svelte';
	import SkeletonBox from '$lib/components/skeleton/SkeletonBox.svelte';
	import SkeletonText from '$lib/components/skeleton/SkeletonText.svelte';
	import { Contact, Wifi, WifiOff, AlertTriangle, Users, Search, X } from 'lucide-svelte';
	import type { StatItem } from '$lib/api-types';
	import { navigating } from '$app/stores';
	import { listNavigation } from '$lib/actions/listNavigation';
	import { getTeamMemberColor, getTeamMemberHexColor } from '$lib/utils';

	let { data } = $props();

	let isPageLoading = $derived(!!$navigating && $navigating.to?.route.id === '/members');

	let search = $state('');

	let filteredMembers = $derived.by(() => {
		if (!search.trim()) return data.members;
		const q = search.toLowerCase().trim();
		return data.members.filter(
			(m) =>
				m.name.toLowerCase().includes(q) ||
				m.device_id.toLowerCase().includes(q) ||
				m.teams.some((t) => t.toLowerCase().includes(q))
		);
	});

	let onlineCount = $derived(data.members.filter((m) => m.connected).length);
	let uniqueTeams = $derived(new Set(data.members.flatMap((m) => m.teams)).size);

	let stats = $derived<StatItem[]>([
		{ title: 'Members', value: data.total, icon: Contact, color: 'rose' },
		{ title: 'Online', value: onlineCount, icon: Wifi, color: 'green' },
		{ title: 'Offline', value: data.total - onlineCount, icon: WifiOff, color: 'gray' },
		{ title: 'Teams', value: uniqueTeams, icon: Users, color: 'purple' }
	]);
</script>

{#if isPageLoading}
	<div class="space-y-6" role="status" aria-busy="true" aria-label="Loading...">
		<!-- Header skeleton -->
		<div>
			<div class="flex items-center gap-2 mb-2">
				<SkeletonText width="70px" size="xs" />
				<span class="text-[var(--text-muted)]">/</span>
				<SkeletonText width="60px" size="xs" />
			</div>
			<div class="flex items-center gap-4">
				<SkeletonBox width="48px" height="48px" rounded="lg" />
				<div>
					<SkeletonText width="100px" size="xl" class="mb-2" />
					<SkeletonText width="220px" size="sm" />
				</div>
			</div>
		</div>
		<!-- Summary + search skeleton -->
		<div class="flex items-center justify-between gap-4">
			<div class="flex items-center gap-4">
				<SkeletonText width="80px" size="sm" />
				<SkeletonText width="70px" size="sm" />
			</div>
			<SkeletonBox width="208px" height="36px" rounded="lg" />
		</div>
		<!-- Members grid skeleton -->
		<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
			{#each Array(6) as _}
				<SkeletonBox height="72px" rounded="lg" />
			{/each}
		</div>
	</div>
{:else}
<PageHeader
	title="Members"
	icon={Contact}
	iconColor="--nav-rose"
	subtitle="{data.total} member{data.total !== 1 ? 's' : ''} across all teams"
	breadcrumbs={[
		{ label: 'Dashboard', href: '/' },
		{ label: 'Members' }
	]}
/>

{#if data.error}
	<div class="text-center py-16">
		<AlertTriangle size={32} class="mx-auto mb-3 text-[var(--warning)]" />
		<p class="text-[var(--text-primary)] font-medium">Could not load members</p>
		<p class="text-sm text-[var(--text-muted)] mt-1">{data.error}</p>
	</div>
{:else if data.members.length === 0}
	<div class="text-center py-20 bg-[var(--bg-subtle)] rounded-2xl border border-dashed border-[var(--border)]">
		<Users class="mx-auto text-[var(--text-muted)] mb-3" size={48} />
		<p class="text-[var(--text-secondary)] font-medium">No members yet</p>
		<p class="text-sm text-[var(--text-muted)] mt-1">
			Members will appear here once you set up sync and add teammates
		</p>
		<a href="/team" class="text-sm text-[var(--accent)] hover:underline mt-3 inline-block">
			Go to Teams
		</a>
	</div>
{:else}
<div class="space-y-6">
	<!-- Stats overview -->
	<StatsGrid {stats} columns={4} />

	<!-- Quick links -->
	<div class="flex items-center gap-4 text-xs text-[var(--text-muted)]">
		<a href="/team" class="hover:text-[var(--accent)] transition-colors">
			View all teams &rarr;
		</a>
		<a href="/sync" class="hover:text-[var(--accent)] transition-colors">
			Sync status &rarr;
		</a>
	</div>

	<!-- Search -->
	<div class="relative group">
		<div class="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--text-faint)] group-focus-within:text-[var(--text-secondary)] transition-colors">
			<Search size={14} strokeWidth={2} />
		</div>
		<input
			type="text"
			placeholder="Search members..."
			bind:value={search}
			class="w-full pl-8 pr-8 h-9 text-sm font-medium bg-[var(--bg-base)] border border-[var(--border)] rounded-[6px] focus:outline-none focus:border-[var(--border-hover)] focus:ring-1 focus:ring-[var(--border-subtle)] transition-all placeholder:text-[var(--text-faint)] placeholder:font-normal text-[var(--text-primary)]"
			data-search-input
		/>
		{#if search}
			<button
				onclick={() => (search = '')}
				class="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
			>
				<X size={14} />
			</button>
		{/if}
	</div>

	{#if search && filteredMembers.length === 0}
		<div class="text-center py-12 text-[var(--text-muted)]">
			<Search size={32} class="mx-auto mb-2 opacity-40" />
			<p class="text-sm">No members matching "{search}"</p>
		</div>
	{:else}

	<!-- Members Grid -->
	<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" use:listNavigation>
		{#each filteredMembers as member (member.member_tag)}
			{@const colors = getTeamMemberColor(member.name)}
			{@const hexColor = getTeamMemberHexColor(member.name)}
			<a
				href="/members/{encodeURIComponent(member.member_tag)}"
				class="flex items-center gap-4 p-4 rounded-lg border border-[var(--border)] bg-[var(--bg-base)] hover:border-[var(--accent)]/30 hover:shadow-sm transition-all"
			data-list-item
			>
				<!-- Avatar -->
				<div
					class="w-11 h-11 rounded-full flex items-center justify-center text-sm font-bold shrink-0"
					style="background: {hexColor}; color: white; box-shadow: 0 0 0 2px {hexColor}33;"
				>
					{member.name.charAt(0).toUpperCase()}
				</div>

				<!-- Info -->
				<div class="flex-1 min-w-0">
					<div class="flex items-center gap-2">
						<span class="font-medium text-[var(--text-primary)] truncate">
							{member.name}
						</span>
						{#if member.is_you}
							<span class="shrink-0 px-1.5 py-0.5 text-[10px] font-medium rounded {colors.badge}">
								You
							</span>
						{/if}
						{#if member.connected || member.is_you}
							<Wifi size={12} class="text-[var(--success)] shrink-0" />
						{:else}
							<WifiOff size={12} class="text-[var(--text-muted)] shrink-0" />
						{/if}
					</div>
					<div class="text-xs text-[var(--text-muted)] mt-0.5">
						{member.team_count} team{member.team_count !== 1 ? 's' : ''}
						<span class="mx-1">&middot;</span>
						{member.device_id.slice(0, 7)}...
					</div>
				</div>
			</a>
		{/each}
	</div>

	{/if}
</div>
{/if}
{/if}
