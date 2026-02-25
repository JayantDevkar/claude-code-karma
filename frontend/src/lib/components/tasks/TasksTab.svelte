<script lang="ts">
	import { browser } from '$app/environment';
	import { onMount } from 'svelte';
	import { ListTodo, LayoutList, LayoutGrid } from 'lucide-svelte';
	import type { Task } from '$lib/api-types';
	import { enrichTasks, createTaskSubjectLookup } from '$lib/utils/tasks';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import TaskCard from './TaskCard.svelte';
	import TasksProgressBar from './TasksProgressBar.svelte';
	import TasksKanban from './TasksKanban.svelte';
	import TaskFlowView from './TaskFlowView.svelte';

	interface Props {
		tasks: Task[];
	}

	let { tasks }: Props = $props();

	// View mode: 'flow' (list) or 'grid' (kanban)
	type ViewMode = 'flow' | 'grid';
	const STORAGE_KEY = 'tasks-view-preference';
	let viewMode = $state<ViewMode>('flow');

	// Load saved preference on mount
	onMount(() => {
		if (browser) {
			const saved = localStorage.getItem(STORAGE_KEY);
			if (saved === 'flow' || saved === 'grid') {
				viewMode = saved;
			}
		}
	});

	// Save preference when changed
	function setViewMode(mode: ViewMode) {
		viewMode = mode;
		if (browser) {
			localStorage.setItem(STORAGE_KEY, mode);
		}
	}

	// Enrich tasks with computed state
	const enrichedTasks = $derived(enrichTasks(tasks));

	// Create subject lookup function
	const getTaskSubject = $derived(createTaskSubjectLookup(tasks));
</script>

<div class="space-y-4">
	<div class="flex items-start justify-between gap-4">
		<div>
			<h2 class="text-lg font-semibold text-[var(--text-primary)]">
				Tasks ({tasks.length})
			</h2>
			<p class="text-sm text-[var(--text-muted)]">Structured work plan for this session</p>
		</div>

		<!-- View Toggle -->
		{#if tasks.length > 0}
			<div
				class="flex items-center gap-0.5 p-0.5 bg-[var(--bg-muted)] rounded-md border border-[var(--border)]"
			>
				<button
					class="
						flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded transition-all
						{viewMode === 'flow'
						? 'bg-[var(--bg-base)] text-[var(--text-primary)] shadow-sm'
						: 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'}
					"
					onclick={() => setViewMode('flow')}
					aria-pressed={viewMode === 'flow'}
				>
					<LayoutList size={14} />
					Flow
				</button>
				<button
					class="
						flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded transition-all
						{viewMode === 'grid'
						? 'bg-[var(--bg-base)] text-[var(--text-primary)] shadow-sm'
						: 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'}
					"
					onclick={() => setViewMode('grid')}
					aria-pressed={viewMode === 'grid'}
				>
					<LayoutGrid size={14} />
					Grid
				</button>
			</div>
		{/if}
	</div>

	{#if tasks.length > 0}
		<!-- Progress Summary -->
		<TasksProgressBar tasks={enrichedTasks} />

		<!-- Task Views -->
		{#if viewMode === 'flow'}
			<!-- Flow View: Vertical list with dependency lines -->
			<TaskFlowView tasks={enrichedTasks} {getTaskSubject} />
		{:else}
			<!-- Grid View: Kanban columns -->
			<TasksKanban tasks={enrichedTasks} {getTaskSubject} />
		{/if}
	{:else}
		<EmptyState
			icon={ListTodo}
			title="No structured tasks"
			description="This session predates Claude Code v2.1.16 or used simple prompts without planning."
		/>
	{/if}
</div>
