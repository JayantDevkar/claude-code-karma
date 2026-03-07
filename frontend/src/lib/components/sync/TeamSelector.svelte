<script lang="ts">
	import { Users, Plus, ChevronDown } from 'lucide-svelte';
	import type { SyncTeam } from '$lib/api-types';

	let {
		teams = [],
		activeTeam = $bindable(''),
		oncreate
	}: {
		teams: SyncTeam[];
		activeTeam: string;
		oncreate?: () => void;
	} = $props();

	let dropdownOpen = $state(false);

	let activeTeamObj = $derived(teams.find((t) => t.name === activeTeam) ?? null);

	let memberCount = $derived(
		activeTeamObj
			? activeTeamObj.member_count ?? activeTeamObj.members.length
			: 0
	);
	let projectCount = $derived(
		activeTeamObj
			? activeTeamObj.project_count ?? activeTeamObj.projects.length
			: 0
	);

	function selectTeam(name: string) {
		activeTeam = name;
		dropdownOpen = false;
	}

	function handleCreate() {
		oncreate?.();
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			dropdownOpen = false;
		}
	}
</script>

{#if teams.length === 0}
	<!-- No teams: prominent create button -->
	<div class="team-selector">
		<div class="flex items-center justify-between w-full">
			<div class="flex items-center gap-2">
				<Users size={14} class="text-[var(--text-muted)]" />
				<span class="text-xs text-[var(--text-muted)]">No teams configured</span>
			</div>
			<button
				onclick={handleCreate}
				class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-[var(--radius)] bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors"
			>
				<Plus size={12} />
				Create Team
			</button>
		</div>
	</div>
{:else if teams.length === 1}
	<!-- Single team: label + stats + small new team button -->
	<div class="team-selector">
		<div class="flex items-center justify-between w-full">
			<div class="flex items-center gap-2 min-w-0">
				<Users size={14} class="shrink-0 text-[var(--accent)]" />
				<span class="text-sm font-medium text-[var(--text-primary)] truncate">
					{teams[0].name}
				</span>
				<span class="text-xs text-[var(--text-muted)] shrink-0">
					{memberCount} member{memberCount !== 1 ? 's' : ''} &middot; {projectCount} project{projectCount !== 1 ? 's' : ''}
				</span>
			</div>
			<button
				onclick={handleCreate}
				class="flex items-center gap-1 px-2 py-1 text-[11px] font-medium rounded-[var(--radius)] border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-muted)] transition-colors shrink-0"
			>
				<Plus size={10} />
				New Team
			</button>
		</div>
	</div>
{:else}
	<!-- Multiple teams: dropdown selector + stats + new team button -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="team-selector" onkeydown={handleKeydown}>
		<div class="flex items-center justify-between w-full">
			<div class="flex items-center gap-2 min-w-0">
				<Users size={14} class="shrink-0 text-[var(--accent)]" />

				<!-- Dropdown trigger -->
				<div class="relative">
					<button
						onclick={() => (dropdownOpen = !dropdownOpen)}
						class="flex items-center gap-1.5 px-2.5 py-1 text-sm font-medium rounded-[var(--radius)] text-[var(--text-primary)] hover:bg-[var(--bg-muted)] transition-colors"
						aria-haspopup="listbox"
						aria-expanded={dropdownOpen}
					>
						{activeTeam || 'Select team'}
						<ChevronDown
							size={12}
							class="text-[var(--text-muted)] transition-transform {dropdownOpen ? 'rotate-180' : ''}"
						/>
					</button>

					{#if dropdownOpen}
						<!-- Backdrop to close dropdown -->
						<!-- svelte-ignore a11y_no_static_element_interactions -->
						<div
							class="fixed inset-0 z-40"
							onclick={() => (dropdownOpen = false)}
							onkeydown={handleKeydown}
						></div>

						<!-- Dropdown menu -->
						<div
							class="absolute left-0 top-full mt-1 z-50 min-w-[180px] rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-base)] shadow-lg py-1"
							role="listbox"
							aria-label="Select team"
						>
							{#each teams as team (team.name)}
								{@const tMembers = team.member_count ?? team.members.length}
								{@const tProjects = team.project_count ?? team.projects.length}
								<button
									onclick={() => selectTeam(team.name)}
									role="option"
									aria-selected={team.name === activeTeam}
									class="w-full text-left px-3 py-2 text-sm transition-colors
										{team.name === activeTeam
										? 'bg-[var(--accent)]/10 text-[var(--accent)] font-medium'
										: 'text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)] hover:text-[var(--text-primary)]'}"
								>
									<span class="block truncate">{team.name}</span>
									<span class="block text-[10px] text-[var(--text-muted)] mt-0.5">
										{tMembers} members &middot; {tProjects} projects
									</span>
								</button>
							{/each}
						</div>
					{/if}
				</div>

				{#if activeTeamObj}
					<span class="text-xs text-[var(--text-muted)] shrink-0">
						{memberCount} member{memberCount !== 1 ? 's' : ''} &middot; {projectCount} project{projectCount !== 1 ? 's' : ''}
					</span>
				{/if}
			</div>

			<button
				onclick={handleCreate}
				class="flex items-center gap-1 px-2 py-1 text-[11px] font-medium rounded-[var(--radius)] border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-muted)] transition-colors shrink-0"
			>
				<Plus size={10} />
				New Team
			</button>
		</div>
	</div>
{/if}

<style>
	.team-selector {
		display: flex;
		align-items: center;
		padding: 0.5rem 1rem;
		margin-top: 0.5rem;
		border: 1px solid var(--border);
		background: var(--bg-subtle);
		border-radius: var(--radius);
	}
</style>
