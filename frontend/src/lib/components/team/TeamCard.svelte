<script lang="ts">
	import { Users, FolderSync, ChevronRight, Bell } from 'lucide-svelte';
	import type { SyncTeam } from '$lib/api-types';
	import { getTeamMemberHexColor } from '$lib/utils';

	let { team, pendingCount = 0, myMemberTag = '' }: { team: SyncTeam; pendingCount?: number; myMemberTag?: string } = $props();

	let members = $derived(team.members ?? []);
	let others = $derived(members.filter(m => m.member_tag !== myMemberTag));
	let projects = $derived(team.projects ?? []);
	let memberCount = $derived(others.length || Math.max(0, (team.member_count || 0) - 1));
	let projectCount = $derived(projects.length || team.project_count || 0);
	let activeCount = $derived(others.filter((m) => m.status === 'active').length);

	function memberDisplayName(member: { member_tag: string; user_id?: string }): string {
		return member.user_id || member.member_tag;
	}

	function initials(name: string): string {
		return name
			.split(/[-_.\s]+/)
			.slice(0, 2)
			.map((w) => w[0]?.toUpperCase() ?? '')
			.join('');
	}
</script>

<a
	href="/team/{encodeURIComponent(team.name)}"
	class="group flex items-center gap-5 px-5 py-4 border border-[var(--border)] rounded-[var(--radius-md)] bg-[var(--bg-subtle)]
		hover:shadow-md transition-all"
	data-list-item
	style="transition-duration: var(--duration-fast);"
	aria-label="Team {team.name}, {memberCount} {memberCount === 1 ? 'member' : 'members'}, {projectCount} {projectCount === 1 ? 'project' : 'projects'}"
>
	<!-- Team name + status indicator -->
	<div class="flex-1 min-w-0">
		<div class="flex items-center gap-2.5">
			<h3
				class="font-semibold text-[var(--text-primary)] group-hover:text-[var(--accent)] transition-colors truncate"
			>
				{team.name}
			</h3>
			<span class="px-2 py-0.5 text-[10px] font-medium rounded-full
				{team.status === 'active'
					? 'bg-[var(--success)]/10 text-[var(--success)] border border-[var(--success)]/20'
					: 'bg-[var(--error)]/10 text-[var(--error)] border border-[var(--error)]/20'}">
				{team.status}
			</span>
			{#if activeCount > 0}
				<span class="flex items-center gap-1 px-2 py-0.5 text-[11px] font-medium rounded-full
					bg-[var(--success)]/10 text-[var(--success)] border border-[var(--success)]/20 whitespace-nowrap">
					<span class="w-1.5 h-1.5 rounded-full bg-[var(--success)] animate-pulse"></span>
					{activeCount} active
				</span>
			{/if}
			{#if pendingCount > 0}
				<span class="flex items-center gap-1 px-2 py-0.5 text-[11px] font-medium rounded-full
					bg-[var(--warning)]/10 text-[var(--warning)] border border-[var(--warning)]/20 whitespace-nowrap">
					<Bell size={10} />
					{pendingCount} pending
				</span>
			{/if}
		</div>
		<div class="flex items-center gap-3 mt-1 text-xs text-[var(--text-muted)]">
			<span class="flex items-center gap-1">
				<Users size={12} />
				{memberCount} {memberCount === 1 ? 'member' : 'members'}
			</span>
			<span class="text-[var(--border)]">&middot;</span>
			<span class="flex items-center gap-1">
				<FolderSync size={12} />
				{projectCount} {projectCount === 1 ? 'project' : 'projects'}
			</span>
		</div>
	</div>

	<!-- Member avatars -->
	<div class="flex items-center -space-x-2 shrink-0">
		{#each members.slice(0, 5) as member (member.member_tag)}
			{@const displayName = memberDisplayName(member)}
			<div
				class="w-8 h-8 rounded-full flex items-center justify-center text-[10px] font-bold text-white
					border-2 border-[var(--bg-subtle)] transition-colors relative"
				style="background-color: {getTeamMemberHexColor(displayName)};"
				title="{displayName} ({member.status})"
			>
				{initials(displayName)}
				{#if member.status === 'active'}
					<span class="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-[var(--success)] border-2 border-[var(--bg-base)] group-hover:border-[var(--bg-subtle)]"></span>
				{/if}
			</div>
		{/each}
		{#if memberCount > 5}
			<div
				class="w-8 h-8 rounded-full flex items-center justify-center text-[10px] font-medium
					bg-[var(--bg-muted)] text-[var(--text-muted)] border-2 border-[var(--bg-subtle)] transition-colors"
			>
				+{memberCount - 5}
			</div>
		{/if}
	</div>

	<!-- Chevron -->
	<ChevronRight
		size={16}
		class="shrink-0 text-[var(--text-muted)] group-hover:text-[var(--accent)] group-hover:translate-x-0.5 transition-all"
	/>
</a>
