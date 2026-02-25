<script lang="ts">
	import { FolderGit2, Layers } from 'lucide-svelte';
	import CollapsibleGroup from './ui/CollapsibleGroup.svelte';
	import ProjectCard from './ProjectCard.svelte';
	import type { GitRootGroup } from '$lib/utils/grouped-projects';
	import { getRelativePath } from '$lib/utils/grouped-projects';
	import { projectTreeStore } from '$lib/stores/project-tree-store';

	interface Props {
		group: GitRootGroup;
		class?: string;
	}

	let { group, class: className = '' }: Props = $props();

	// Subscribe to store state
	const storeState = $derived($projectTreeStore);

	// Track open state with store
	let isOpen = $derived(projectTreeStore.isExpanded(group.rootPath, storeState));

	function handleOpenChange(open: boolean) {
		projectTreeStore.toggleRoot(group.rootPath);
	}

	// Calculate stats for the group
	const projectCount = $derived((group.rootProject ? 1 : 0) + group.nestedProjects.length);
</script>

<CollapsibleGroup
	bind:open={isOpen}
	onOpenChange={handleOpenChange}
	title={group.displayName}
	class={className}
>
	{#snippet icon()}
		<FolderGit2 size={18} strokeWidth={2} class="text-[var(--accent-primary)]" />
	{/snippet}

	{#snippet metadata()}
		<!-- Project Count -->
		<div
			class="
				flex items-center gap-1.5
				px-2 py-1
				bg-[var(--bg-subtle)]
				rounded-[var(--radius-sm)]
				text-xs font-medium
			"
		>
			<Layers size={12} strokeWidth={2} class="text-[var(--text-muted)]" />
			<span class="text-[var(--text-secondary)]">
				{projectCount}
				{projectCount === 1 ? 'project' : 'projects'}
			</span>
		</div>

		<!-- Total Sessions -->
		{#if group.totalSessions > 0}
			<div
				class="
					px-2 py-1
					bg-[var(--bg-subtle)]
					rounded-[var(--radius-sm)]
					text-xs font-medium
					text-[var(--text-secondary)]
					mono
				"
			>
				{group.totalSessions}
				{group.totalSessions === 1 ? 'session' : 'sessions'}
			</div>
		{/if}

		<!-- Total Agents -->
		{#if group.totalAgents > 0}
			<div
				class="
					px-2 py-1
					bg-[var(--bg-subtle)]
					rounded-[var(--radius-sm)]
					text-xs font-medium
					text-[var(--text-secondary)]
					mono
				"
			>
				{group.totalAgents}
				{group.totalAgents === 1 ? 'agent' : 'agents'}
			</div>
		{/if}
	{/snippet}

	{#snippet children()}
		<div class="space-y-2">
			<!-- Root Project (if exists) -->
			{#if group.rootProject}
				<ProjectCard project={group.rootProject} variant="compact" showRootBadge={true} />
			{/if}

			<!-- Separator if root project exists and there are nested projects -->
			{#if group.rootProject && group.nestedProjects.length > 0}
				<div class="border-t border-[var(--border)] my-3"></div>
			{/if}

			<!-- Nested Projects -->
			{#each group.nestedProjects as nestedProject}
				<ProjectCard
					project={nestedProject}
					variant="compact"
					relativePath={getRelativePath(nestedProject.path, group.rootPath)}
					showNestedGitBadge={nestedProject.is_git_repository}
				/>
			{/each}
		</div>
	{/snippet}
</CollapsibleGroup>
