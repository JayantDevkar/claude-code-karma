<script lang="ts">
	import { ChevronDown, FolderOpen } from 'lucide-svelte';
	import ArchivedSessionCard from './ArchivedSessionCard.svelte';
	import type { ArchivedProject } from '$lib/api-types';
	import { getProjectNameFromEncoded } from '$lib/utils';

	interface Props {
		project: ArchivedProject;
		defaultExpanded?: boolean;
	}

	let { project, defaultExpanded = false }: Props = $props();
	let expanded = $state(defaultExpanded);

	// Parse project name from encoded name to preserve hyphens (e.g., "claude-karma" not "karma")
	const displayProjectName = $derived(
		getProjectNameFromEncoded(project.encoded_name) || project.project_name
	);

	function formatDateRange(start: string, end: string): string {
		const startDate = new Date(start);
		const endDate = new Date(end);

		const startMonth = startDate.toLocaleDateString('en-US', { month: 'short' });
		const endMonth = endDate.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });

		if (startMonth === endMonth.split(' ')[0]) {
			return endMonth;
		}
		return `${startMonth} - ${endMonth}`;
	}
</script>

<div
	class="border border-[var(--border)] rounded-[var(--radius-md)] overflow-hidden bg-[var(--bg-base)]"
>
	<!-- Header (clickable to expand/collapse) -->
	<button
		onclick={() => (expanded = !expanded)}
		class="
			w-full px-4 py-3
			flex items-center justify-between gap-4
			bg-[var(--bg-subtle)]
			hover:bg-[var(--bg-muted)]
			transition-colors
			text-left
			border-l-3 border-l-[#B85450]
		"
	>
		<!-- Left: Icon + Project Name -->
		<div class="flex items-center gap-3 min-w-0 flex-1">
			<div class="p-1.5 rounded-md bg-[rgba(184,84,80,0.12)] text-[#B85450]">
				<FolderOpen size={16} strokeWidth={2} />
			</div>
			<div class="min-w-0 flex-1">
				<span class="text-sm font-semibold text-[var(--text-primary)] truncate block">
					{displayProjectName}
				</span>
			</div>
		</div>

		<!-- Right: Date Range + Session Count + Prompt Count + Chevron -->
		<div class="flex items-center gap-4 shrink-0">
			<span class="text-xs text-[var(--text-muted)]">
				{formatDateRange(project.date_range.start, project.date_range.end)}
			</span>
			<div class="flex items-center gap-2">
				<span
					class="
						text-xs font-mono font-medium
						px-2 py-0.5 rounded-full
						bg-[var(--bg-muted)] text-[var(--text-secondary)]
					"
				>
					{project.session_count}
					{project.session_count === 1 ? 'session' : 'sessions'}
				</span>
				<span class="text-xs text-[var(--text-faint)]">
					({project.prompt_count} prompts)
				</span>
			</div>
			<ChevronDown
				size={16}
				class="text-[var(--text-muted)] transition-transform {expanded ? 'rotate-180' : ''}"
			/>
		</div>
	</button>

	<!-- Content (sessions grid) -->
	{#if expanded}
		<div class="p-4 border-t border-[var(--border-subtle)] bg-[var(--bg-base)]">
			<div
				class="sessions-grid grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 items-stretch"
			>
				{#each project.sessions as session}
					<div class="session-card-wrapper">
						<ArchivedSessionCard
							{session}
							showProject={true}
							projectName={displayProjectName}
						/>
					</div>
				{/each}
			</div>
		</div>
	{/if}
</div>

<style>
	/* Expanded card spans full width and moves to top on larger screens */
	@media (min-width: 768px) {
		.session-card-wrapper:global(:has([aria-expanded='true'])) {
			grid-column: 1 / -1;
			order: -1; /* Move expanded card above adjacent cards */
		}
	}
</style>
