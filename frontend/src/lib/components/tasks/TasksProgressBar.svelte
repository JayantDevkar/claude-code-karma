<script lang="ts">
	import type { Task, TaskWithState } from '$lib/api-types';
	import { getActiveTask, getCompletedCount } from '$lib/utils/tasks';

	interface Props {
		tasks: TaskWithState[];
	}

	let { tasks }: Props = $props();

	const completedCount = $derived(getCompletedCount(tasks));
	const activeTask = $derived(getActiveTask(tasks));

	function getStatusColor(status: Task['status'], isBlocked: boolean = false): string {
		switch (status) {
			case 'completed':
				return 'bg-[var(--success)]';
			case 'in_progress':
				return 'bg-[var(--nav-blue)]';
			default:
				return isBlocked ? 'bg-[var(--text-muted)]/50' : 'bg-[var(--text-muted)]';
		}
	}
</script>

<div
	class="flex flex-wrap items-center gap-4 p-4 bg-[var(--bg-subtle)] rounded-lg border border-[var(--border)]"
>
	<!-- Status dots -->
	<div class="flex items-center gap-1">
		{#each tasks as task (task.id)}
			<span
				class="w-2.5 h-2.5 rounded-full {getStatusColor(task.status, task.isBlocked)}"
				class:animate-pulse={task.status === 'in_progress'}
				title={task.subject}
			></span>
		{/each}
	</div>

	<!-- Progress text -->
	<span class="text-sm text-[var(--text-secondary)]">
		{completedCount} of {tasks.length} tasks complete
	</span>

	<!-- Active task indicator -->
	{#if activeTask}
		<div class="ml-auto flex items-center gap-2 text-sm">
			<span class="text-[var(--text-muted)]">Currently:</span>
			<span class="text-[var(--nav-blue)] font-medium animate-pulse">
				{activeTask.active_form || activeTask.subject}
			</span>
		</div>
	{/if}
</div>
