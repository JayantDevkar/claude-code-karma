<script lang="ts">
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import { Contact, Wifi, WifiOff, AlertTriangle, Users, Search, X } from 'lucide-svelte';
	import { getTeamMemberColor, getTeamMemberHexColor } from '$lib/utils';

	let { data } = $props();

	let search = $state('');

	let filteredMembers = $derived(() => {
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
</script>

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
	<!-- Summary Bar + Search -->
	<div class="flex items-center justify-between gap-4 mb-6">
		<div class="flex items-center gap-4 text-sm text-[var(--text-secondary)]">
			<span class="flex items-center gap-1.5">
				<Wifi size={14} class="text-[var(--success)]" />
				{onlineCount} online
			</span>
			<span class="text-[var(--text-muted)]">
				{data.total - onlineCount} offline
			</span>
		</div>

		<div class="relative">
			<Search
				size={14}
				class="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--text-muted)] pointer-events-none"
			/>
			<input
				type="text"
				placeholder="Search members..."
				bind:value={search}
				class="pl-8 pr-8 py-1.5 text-sm rounded-lg border border-[var(--border)] bg-[var(--bg-base)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-[var(--accent)] w-52 transition-colors"
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
	</div>

	{#if search && filteredMembers().length === 0}
		<div class="text-center py-12 text-[var(--text-muted)]">
			<Search size={32} class="mx-auto mb-2 opacity-40" />
			<p class="text-sm">No members matching "{search}"</p>
		</div>
	{:else}

	<!-- Members Grid -->
	<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
		{#each filteredMembers() as member (member.device_id)}
			{@const colors = getTeamMemberColor(member.name)}
			{@const hexColor = getTeamMemberHexColor(member.name)}
			<a
				href="/members/{encodeURIComponent(member.device_id)}"
				class="flex items-center gap-4 p-4 rounded-lg border border-[var(--border)] bg-[var(--bg-base)] hover:border-[var(--accent)]/30 hover:shadow-sm transition-all"
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
{/if}
