<script lang="ts">
	import type { TaskWithState } from '$lib/api-types';
	import TaskCard from './TaskCard.svelte';

	interface Props {
		tasks: TaskWithState[];
		getTaskSubject: (id: string) => string;
	}

	let { tasks, getTaskSubject }: Props = $props();

	// Group tasks by status
	const pendingTasks = $derived(tasks.filter((t) => t.status === 'pending'));
	const inProgressTasks = $derived(tasks.filter((t) => t.status === 'in_progress'));
	const completedTasks = $derived(tasks.filter((t) => t.status === 'completed'));
</script>

<div class="grid grid-cols-1 md:grid-cols-3 gap-4">
	<!-- Pending Column -->
	<div class="space-y-3">
		<div class="flex items-center justify-between pb-2 border-b border-[var(--border)]">
			<h3 class="text-sm font-semibold text-[var(--text-secondary)]">Pending</h3>
			<span
				class="text-xs font-mono px-1.5 py-0.5 rounded bg-[var(--bg-muted)] text-[var(--text-muted)]"
			>
				{pendingTasks.length}
			</span>
		</div>
		<div class="space-y-2 min-h-[100px]">
			{#each pendingTasks as task (task.id)}
				<TaskCard {task} {getTaskSubject} />
			{/each}
			{#if pendingTasks.length === 0}
				<div
					class="flex items-center justify-center h-20 rounded-lg border border-dashed border-[var(--border)] text-xs text-[var(--text-muted)]"
				>
					No pending tasks
				</div>
			{/if}
		</div>
	</div>

	<!-- In Progress Column -->
	<div class="space-y-3">
		<div class="flex items-center justify-between pb-2 border-b border-[var(--nav-blue)]/30">
			<h3 class="text-sm font-semibold text-[var(--nav-blue)]">In Progress</h3>
			<span
				class="text-xs font-mono px-1.5 py-0.5 rounded bg-[var(--nav-blue-subtle)] text-[var(--nav-blue)]"
			>
				{inProgressTasks.length}
			</span>
		</div>
		<div class="space-y-2 min-h-[100px]">
			{#each inProgressTasks as task (task.id)}
				<TaskCard {task} {getTaskSubject} />
			{/each}
			{#if inProgressTasks.length === 0}
				<div
					class="flex items-center justify-center h-20 rounded-lg border border-dashed border-[var(--nav-blue)]/30 text-xs text-[var(--text-muted)]"
				>
					No tasks in progress
				</div>
			{/if}
		</div>
	</div>

	<!-- Completed Column -->
	<div class="space-y-3">
		<div class="flex items-center justify-between pb-2 border-b border-[var(--success)]/30">
			<h3 class="text-sm font-semibold text-[var(--success)]">Completed</h3>
			<span
				class="text-xs font-mono px-1.5 py-0.5 rounded bg-[var(--success-subtle)] text-[var(--success)]"
			>
				{completedTasks.length}
			</span>
		</div>
		<div class="space-y-2 min-h-[100px]">
			{#each completedTasks as task (task.id)}
				<TaskCard {task} {getTaskSubject} />
			{/each}
			{#if completedTasks.length === 0}
				<div
					class="flex items-center justify-center h-20 rounded-lg border border-dashed border-[var(--success)]/30 text-xs text-[var(--text-muted)]"
				>
					No completed tasks
				</div>
			{/if}
		</div>
	</div>
</div>
