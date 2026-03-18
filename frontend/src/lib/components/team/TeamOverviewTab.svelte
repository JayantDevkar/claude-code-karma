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
	}

	let {
		team,
		teamName,
		memberTag,
		onswitchtab
	}: Props = $props();

	// Leader check for getting started banner
	let isLeader = $derived(
		!!memberTag && team.leader_member_tag === memberTag
	);

	// Derived state
	let members = $derived(team.members ?? []);
	let projects = $derived(team.projects ?? []);
	let activeCount = $derived(members.filter((m) => m.status === 'active').length);
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
			value: `${activeCount}/${members.length}`,
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
	<!-- Getting Started Guide (leaders of new teams only) -->
	<GettingStartedBanner
		memberCount={members.length}
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
