<script lang="ts">
	import {
		Users,
		FolderSync,
		Calendar,
		Crown
	} from 'lucide-svelte';
	import type {
		SyncTeam,
		StatItem
	} from '$lib/api-types';
	import StatsGrid from '$lib/components/StatsGrid.svelte';
	import GettingStartedBanner from './GettingStartedBanner.svelte';

	interface Props {
		team: SyncTeam;
		teamName: string;
		memberTag?: string;
		onswitchtab?: (tab: string) => void;
		offeredSubscriptionCount?: number;
	}

	let {
		team,
		teamName,
		memberTag,
		onswitchtab,
		offeredSubscriptionCount
	}: Props = $props();

	// Leader check for getting started banner
	let isLeader = $derived(
		!!memberTag && team.leader_member_tag === memberTag
	);

	// Derived state (exclude self from member counts)
	let members = $derived(team.members ?? []);
	let others = $derived(members.filter(m => m.member_tag !== memberTag));
	let projects = $derived(team.projects ?? []);
	let activeCount = $derived(others.filter((m) => m.status === 'active').length);
	let sharedProjects = $derived(projects.filter((p) => p.status === 'shared').length);

	// Format created_at date
	let createdDate = $derived.by(() => {
		if (!team.created_at) return null;
		try {
			return new Date(team.created_at).toLocaleDateString('en-US', {
				month: 'short',
				day: 'numeric',
				year: 'numeric'
			});
		} catch {
			return null;
		}
	});

	// Stats for StatsGrid
	let stats = $derived<StatItem[]>([
		{
			title: 'Members',
			value: `${activeCount}/${others.length}`,
			description: 'active',
			icon: Users,
			color: 'green'
		},
		{
			title: 'Projects',
			value: sharedProjects,
			description: `${projects.length} total`,
			icon: FolderSync,
			color: 'blue'
		}
	]);
</script>

<div class="space-y-8">
	<!-- Offered project subscriptions banner -->
	{#if offeredSubscriptionCount && offeredSubscriptionCount > 0}
		<button
			onclick={() => onswitchtab?.('projects')}
			class="w-full flex items-center gap-3 p-4 rounded-[var(--radius-lg)] border border-[var(--warning)]/30 bg-[var(--warning)]/5 hover:bg-[var(--warning)]/8 transition-colors text-left cursor-pointer"
		>
			<span class="w-2.5 h-2.5 rounded-full bg-[var(--warning)] shrink-0" style="box-shadow: 0 0 8px rgba(var(--warning-rgb, 245,158,11), 0.4);"></span>
			<div class="flex-1 min-w-0">
				<span class="text-sm font-semibold text-[var(--text-primary)]">
					{offeredSubscriptionCount} project invitation{offeredSubscriptionCount !== 1 ? 's' : ''} waiting
				</span>
				<p class="text-xs text-[var(--text-muted)] mt-0.5">Accept on the Projects tab to start syncing</p>
			</div>
			<span class="text-[var(--text-muted)] text-lg shrink-0">&rarr;</span>
		</button>
	{/if}

	<!-- Getting Started Guide (leaders of new teams only) -->
	<GettingStartedBanner
		memberCount={others.length}
		projectCount={sharedProjects}
		{isLeader}
		{teamName}
		onShareProject={() => onswitchtab?.('projects')}
		onAddMember={() => onswitchtab?.('members')}
	/>

	<!-- Team Info Card -->
	<section class="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)] p-5">
		<div class="flex items-start justify-between">
			<div class="space-y-3">
				<div class="flex items-center gap-3">
					<h2 class="text-lg font-semibold text-[var(--text-primary)]">{team.name}</h2>
					<span class="px-2 py-0.5 text-[11px] font-medium rounded-full
						{team.status === 'active'
							? 'bg-[var(--success)]/10 text-[var(--success)] border border-[var(--success)]/20'
							: 'bg-[var(--error)]/10 text-[var(--error)] border border-[var(--error)]/20'}">
						{team.status}
					</span>
				</div>
				<div class="flex items-center gap-4 text-xs text-[var(--text-muted)]">
					<span class="flex items-center gap-1.5">
						<Crown size={12} class="text-[var(--warning)]" />
						Leader: <span class="font-medium text-[var(--text-secondary)]">{team.leader_member_tag}</span>
					</span>
					{#if createdDate}
						<span class="flex items-center gap-1.5">
							<Calendar size={12} />
							Created {createdDate}
						</span>
					{/if}
				</div>
			</div>
		</div>
	</section>

	<!-- Stats Row -->
	<section>
		<StatsGrid {stats} columns={2} />
	</section>

</div>
