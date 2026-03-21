<script lang="ts">
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import StatsGrid from '$lib/components/StatsGrid.svelte';
	import TeamCard from '$lib/components/team/TeamCard.svelte';
	import CreateTeamDialog from '$lib/components/team/CreateTeamDialog.svelte';
	import PendingInvitationCard from '$lib/components/sync/PendingInvitationCard.svelte';
	import { Users, Plus, ArrowRight, FolderSync, Contact, Crown, UserPlus } from 'lucide-svelte';
	import { goto, invalidateAll } from '$app/navigation';
	import { listNavigation } from '$lib/actions/listNavigation';
	import type { StatItem } from '$lib/api-types';
	import PairingCodeCard from '$lib/components/shared/PairingCodeCard.svelte';

	let { data } = $props();

	let showCreateDialog = $state(false);

	let configured = $derived(data.syncStatus?.configured ?? false);
	let teams = $derived(data.teams ?? []);

	// Current user's member tag (to exclude self from counts)
	let myTag = $derived(data.syncStatus?.member_tag);

	// Aggregate stats across all teams (excluding self)
	let totalMembers = $derived(teams.reduce((sum, t) => {
		const others = (t.members ?? []).filter(m => m.member_tag !== myTag);
		return sum + (others.length || Math.max(0, (t.member_count ?? 0) - 1));
	}, 0));
	let activeMembers = $derived(teams.reduce((sum, t) => {
		return sum + (t.members ?? []).filter(m => m.member_tag !== myTag && m.status === 'active').length;
	}, 0));
	let totalProjects = $derived(teams.reduce((sum, t) => sum + (t.projects?.length ?? t.project_count ?? 0), 0));

	let stats = $derived<StatItem[]>([
		{ title: 'Teams', value: teams.length, icon: Users, color: 'purple' },
		{ title: 'Members', value: totalMembers, icon: Contact, color: 'rose' },
		{ title: 'Active', value: activeMembers, icon: Users, color: 'green' },
		{ title: 'Projects Synced', value: totalProjects, icon: FolderSync, color: 'blue' }
	]);

	async function handleTeamCreated(teamName: string) {
		if (teamName) {
			await goto(`/team/${encodeURIComponent(teamName)}`);
		} else {
			await invalidateAll();
		}
	}


</script>

<PageHeader
	title="Teams"
	icon={Users}
	iconColor="--nav-indigo"
	breadcrumbs={[{ label: 'Dashboard', href: '/' }, { label: 'Teams' }]}
	subtitle="Create and manage teams to share sessions with teammates &middot; Sync status on /sync"
>
	{#snippet headerRight()}
		{#if configured && teams.length > 0}
			<button
				onclick={() => (showCreateDialog = true)}
				class="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-[var(--radius-md)]
					bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors"
			>
				<Plus size={14} />
				Create Team
			</button>
		{/if}
	{/snippet}
</PageHeader>

<div class="space-y-6">
	<PendingInvitationCard onaccepted={(teams) => {
		if (teams?.length) goto(`/team/${encodeURIComponent(teams[0])}`);
		else invalidateAll();
	}} />

	{#if !configured}
		<!-- State 1: Sync not configured -->
		<div class="flex flex-col items-center justify-center py-16 text-center">
			<div
				class="w-16 h-16 rounded-2xl flex items-center justify-center bg-[var(--nav-indigo-subtle)] text-[var(--nav-indigo)] mb-5"
			>
				<Users size={32} strokeWidth={1.5} />
			</div>
			<h3 class="text-lg font-semibold text-[var(--text-primary)] mb-2">Set up sync first</h3>
			<p class="text-sm text-[var(--text-muted)] mb-6 max-w-sm">
				Before creating or joining a team, you need to install Syncthing and initialize sync.
			</p>
			<a
				href="/sync"
				class="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium rounded-lg
					bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors"
			>
				Go to Sync Setup
				<ArrowRight size={16} />
			</a>
		</div>
	{:else if teams.length === 0}
		<!-- State 2: No teams yet — dual-path (leader vs member) -->
		<div class="flex flex-col items-center pt-10 pb-14">
			<div
				class="w-14 h-14 rounded-2xl flex items-center justify-center bg-[var(--nav-indigo-subtle)] text-[var(--nav-indigo)] mb-4"
			>
				<Users size={28} strokeWidth={1.5} />
			</div>
			<h3 class="text-lg font-semibold text-[var(--text-primary)] mb-1">No teams yet</h3>
			<p class="text-sm text-[var(--text-muted)] mb-8">
				Get started by creating or joining a team
			</p>

			<div class="grid grid-cols-1 md:grid-cols-2 gap-4 w-full max-w-2xl">
				<!-- Leader path: Create a Team -->
				<div
					class="relative flex flex-col rounded-xl border border-[var(--accent)]/20 bg-[var(--accent)]/[0.03] p-6 min-h-[220px]"
				>
					<div class="flex items-center gap-3 mb-3">
						<div
							class="w-9 h-9 rounded-lg flex items-center justify-center bg-[var(--accent)]/10 text-[var(--accent)]"
						>
							<Crown size={18} strokeWidth={1.8} />
						</div>
						<h4 class="text-sm font-semibold text-[var(--text-primary)]">Create a Team</h4>
					</div>
					<p class="text-[13px] leading-relaxed text-[var(--text-muted)] mb-auto">
						You're the leader. Create a team, share projects, and add members using their pairing codes.
					</p>
					<button
						onclick={() => (showCreateDialog = true)}
						class="mt-5 inline-flex items-center justify-center gap-2 w-full px-4 py-2.5 text-sm font-medium rounded-lg
							bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors cursor-pointer"
					>
						<Plus size={15} />
						Create Team
					</button>
				</div>

				<!-- Member path: Join a Team -->
				<div
					class="relative flex flex-col rounded-xl border border-[var(--info)]/20 bg-[var(--info)]/[0.03] p-6 min-h-[220px]"
				>
					<div class="flex items-center gap-3 mb-3">
						<div
							class="w-9 h-9 rounded-lg flex items-center justify-center bg-[var(--info)]/10 text-[var(--info)]"
						>
							<UserPlus size={18} strokeWidth={1.8} />
						</div>
						<h4 class="text-sm font-semibold text-[var(--text-primary)]">Join a Team</h4>
					</div>
					<p class="text-[13px] leading-relaxed text-[var(--text-muted)] mb-4">
						Share your pairing code with a team leader. They'll add you from their end.
					</p>

					<!-- Pairing code display -->
					<div class="mt-auto">
						<PairingCodeCard variant="inline" />
					</div>
				</div>
			</div>
		</div>
	{:else}
		<!-- Stats overview -->
		<StatsGrid {stats} columns={4} />

		<!-- Quick links -->
		<div class="flex items-center gap-4 text-xs text-[var(--text-muted)]">
			<a href="/sync" class="hover:text-[var(--accent)] transition-colors">
				Sync status &rarr;
			</a>
		</div>

		<!-- State 3: Has teams -->
		<div class="space-y-2" use:listNavigation>
			{#each teams as team (team.name)}
				<TeamCard {team} pendingCount={data.pendingByTeam?.[team.name] ?? 0} myMemberTag={myTag ?? ''} />
			{/each}
		</div>
	{/if}
</div>

<CreateTeamDialog bind:open={showCreateDialog} oncreated={handleTeamCreated} />
