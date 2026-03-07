<script lang="ts">
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import TeamCard from '$lib/components/team/TeamCard.svelte';
	import CreateTeamDialog from '$lib/components/team/CreateTeamDialog.svelte';
	import JoinTeamDialog from '$lib/components/team/JoinTeamDialog.svelte';
	import { Users, Plus, UserPlus, ArrowRight } from 'lucide-svelte';
	import { goto, invalidateAll } from '$app/navigation';
	import type { JoinTeamResponse } from '$lib/api-types';

	let { data } = $props();

	let showCreateDialog = $state(false);
	let showJoinDialog = $state(false);

	let configured = $derived(data.syncStatus?.configured ?? false);
	let teams = $derived(data.teams ?? []);

	function handleTeamCreated(teamName: string) {
		invalidateAll();
		if (teamName) goto(`/team/${encodeURIComponent(teamName)}`);
	}

	function handleTeamJoined(result: JoinTeamResponse) {
		// Stay on dialog to show the "share your code back" CTA
		// Navigation happens when they close the dialog
		invalidateAll();
	}
</script>

<PageHeader
	title="Teams"
	icon={Users}
	iconColor="--nav-purple"
	breadcrumbs={[{ label: 'Dashboard', href: '/' }, { label: 'Teams' }]}
>
	{#snippet headerRight()}
		{#if configured && teams.length > 0}
			<div class="flex items-center gap-2">
				<button
					onclick={() => (showCreateDialog = true)}
					class="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-[var(--radius-md)]
						bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors"
				>
					<Plus size={14} />
					Create Team
				</button>
				<button
					onclick={() => (showJoinDialog = true)}
					class="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-[var(--radius-md)]
						border border-[var(--border)] text-[var(--text-secondary)]
						hover:bg-[var(--bg-muted)] hover:text-[var(--text-primary)] transition-colors"
				>
					<UserPlus size={14} />
					Join Team
				</button>
			</div>
		{/if}
	{/snippet}
</PageHeader>

<div class="max-w-5xl mx-auto space-y-6">
	{#if !configured}
		<!-- State 1: Sync not configured -->
		<div class="flex flex-col items-center justify-center py-16 text-center">
			<div
				class="w-16 h-16 rounded-2xl flex items-center justify-center bg-[var(--nav-purple-subtle)] text-[var(--nav-purple)] mb-5"
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
		<!-- State 2: No teams yet -->
		<div class="flex flex-col items-center justify-center py-16 text-center">
			<div
				class="w-16 h-16 rounded-2xl flex items-center justify-center bg-[var(--nav-purple-subtle)] text-[var(--nav-purple)] mb-5"
			>
				<Users size={32} strokeWidth={1.5} />
			</div>
			<h3 class="text-lg font-semibold text-[var(--text-primary)] mb-2">No teams yet</h3>
			<p class="text-sm text-[var(--text-muted)] mb-6 max-w-sm">
				Create a team to start sharing sessions with teammates, or join an existing team.
			</p>
			<div class="flex items-center gap-3">
				<button
					onclick={() => (showCreateDialog = true)}
					class="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium rounded-lg
						bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors"
				>
					<Plus size={16} />
					Create Team
				</button>
				<button
					onclick={() => (showJoinDialog = true)}
					class="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium rounded-lg
						border border-[var(--border)] text-[var(--text-secondary)]
						hover:bg-[var(--bg-muted)] hover:text-[var(--text-primary)] transition-colors"
				>
					<UserPlus size={16} />
					Join Team
				</button>
			</div>
		</div>
	{:else}
		<!-- State 3: Has teams -->
		<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
			{#each teams as team (team.name)}
				<TeamCard {team} />
			{/each}
		</div>
	{/if}
</div>

<CreateTeamDialog bind:open={showCreateDialog} oncreated={handleTeamCreated} />
<JoinTeamDialog bind:open={showJoinDialog} onjoined={handleTeamJoined} />
