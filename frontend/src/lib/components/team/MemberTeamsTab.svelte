<script lang="ts">
	import { Users, FolderGit2, Wifi, ChevronRight } from 'lucide-svelte';
	import type { MemberProfile } from '$lib/api-types';

	interface Props {
		profile: MemberProfile;
	}

	let { profile }: Props = $props();
</script>

{#if profile.teams.length === 0}
	<p class="text-sm text-[var(--text-muted)] py-8 text-center">
		Not a member of any teams.
	</p>
{:else}
	<div class="space-y-4">
		<p class="text-xs text-[var(--text-muted)]">
			Member of {profile.teams.length} team{profile.teams.length === 1 ? '' : 's'}
		</p>

		<div class="space-y-2">
			{#each profile.teams as team (team.name)}
				<a
					href="/team/{encodeURIComponent(team.name)}"
					class="block p-4 rounded-lg border border-[var(--border)] bg-[var(--bg-base)]
						hover:border-[var(--accent)]/30 hover:shadow-sm transition-all group"
				>
					<!-- Header: team name + chevron -->
					<div class="flex items-center justify-between">
						<h3 class="text-sm font-semibold text-[var(--text-primary)] group-hover:text-[var(--accent)] transition-colors">
							{team.name}
						</h3>
						<ChevronRight
							size={16}
							class="text-[var(--text-muted)] group-hover:text-[var(--accent)] group-hover:translate-x-0.5 transition-all"
						/>
					</div>

					<!-- Stats row -->
					<div class="flex items-center gap-4 mt-2">
						<span class="flex items-center gap-1 text-xs text-[var(--text-muted)]">
							<Users size={12} />
							{team.member_count} member{team.member_count === 1 ? '' : 's'}
						</span>
						<span class="flex items-center gap-1 text-xs text-[var(--text-muted)]">
							<FolderGit2 size={12} />
							{team.project_count} project{team.project_count === 1 ? '' : 's'}
						</span>
						{#if team.online_count > 0}
							<span class="flex items-center gap-1 text-xs text-[var(--success)]">
								<Wifi size={12} />
								{team.online_count} online
							</span>
						{/if}
					</div>

					<!-- Project contribution pills — sorted by session_count descending -->
					{#if team.projects.length > 0}
						<div class="border-t border-[var(--border)] mt-3 pt-3 flex flex-wrap gap-1.5">
							{#each [...team.projects].sort((a, b) => b.session_count - a.session_count) as project (project.encoded_name)}
								<span
									class="inline-flex items-center gap-1.5 px-2 py-1 text-[11px] rounded-full
										bg-[var(--bg-muted)] text-[var(--text-secondary)]"
								>
									{project.name}
									<span class="text-[var(--text-muted)] font-medium tabular-nums">{project.session_count}</span>
								</span>
							{/each}
						</div>
					{/if}
				</a>
			{/each}
		</div>
	</div>
{/if}
