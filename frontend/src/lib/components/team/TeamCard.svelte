<script lang="ts">
	import { Users, FolderSync, Radio } from 'lucide-svelte';
	import type { SyncTeam } from '$lib/api-types';

	let { team }: { team: SyncTeam } = $props();

	let memberCount = $derived(team.members?.length ?? team.member_count ?? 0);
	let projectCount = $derived(team.projects?.length ?? team.project_count ?? 0);
	let onlineCount = $derived(team.members?.filter((m) => m.connected).length ?? 0);
</script>

<a
	href="/team/{encodeURIComponent(team.name)}"
	class="group block border border-[var(--border)] rounded-xl p-5 bg-[var(--bg-base)] hover:border-[var(--accent)]/40 hover:shadow-md transition-all"
	style="transition-duration: var(--duration-base);"
>
	<div class="flex items-start justify-between mb-4">
		<div class="flex items-center gap-3">
			<div
				class="w-10 h-10 rounded-lg flex items-center justify-center bg-[var(--nav-purple-subtle)] text-[var(--nav-purple)]"
			>
				<Users size={20} />
			</div>
			<div>
				<h3
					class="font-semibold text-[var(--text-primary)] group-hover:text-[var(--accent)] transition-colors"
				>
					{team.name}
				</h3>
				<span class="text-xs text-[var(--text-muted)]">{team.backend}</span>
			</div>
		</div>
	</div>

	<div class="flex items-center gap-4 text-sm text-[var(--text-secondary)]">
		<span class="flex items-center gap-1.5">
			<Users size={14} class="text-[var(--text-muted)]" />
			{memberCount}
			{memberCount === 1 ? 'member' : 'members'}
		</span>
		<span class="text-[var(--border)]">|</span>
		<span class="flex items-center gap-1.5">
			<FolderSync size={14} class="text-[var(--text-muted)]" />
			{projectCount}
			{projectCount === 1 ? 'project' : 'projects'}
		</span>
	</div>

	{#if onlineCount > 0}
		<div class="mt-3 flex items-center gap-1.5 text-xs text-[var(--success)]">
			<Radio size={12} />
			{onlineCount} online
		</div>
	{/if}
</a>
