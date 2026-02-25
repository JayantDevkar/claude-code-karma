<script lang="ts">
	import { AlertTriangle } from 'lucide-svelte';
	import type { TaskWithState } from '$lib/api-types';
	import TaskStatusIndicator from './TaskStatusIndicator.svelte';

	interface Props {
		task: TaskWithState;
		getTaskSubject: (id: string) => string;
		expanded?: boolean;
	}

	let { task, getTaskSubject, expanded = false }: Props = $props();
	let isExpanded = $state(expanded);
</script>

<button
	class="
		w-full text-left p-3 rounded-lg border transition-all
		{task.status === 'completed'
		? 'bg-[var(--success-subtle)]/30 border-[var(--success)]/20'
		: task.status === 'in_progress'
			? 'bg-[var(--nav-blue-subtle)] border-[var(--nav-blue)]/30'
			: task.isBlocked
				? 'bg-[var(--bg-muted)] border-[var(--border)] opacity-60'
				: 'bg-[var(--bg-base)] border-[var(--border)] hover:border-[var(--border-hover)]'}
	"
	onclick={() => (isExpanded = !isExpanded)}
>
	<div class="flex items-start gap-3">
		<!-- Status Icon -->
		<div class="mt-0.5 shrink-0">
			<TaskStatusIndicator status={task.status} isBlocked={task.isBlocked} />
		</div>

		<!-- Content -->
		<div class="flex-1 min-w-0">
			<div class="flex items-center justify-between gap-2">
				<h4 class="font-medium text-[var(--text-primary)] truncate flex items-center">
					<span
						class="inline-flex items-center justify-center w-5 h-5 mr-2 text-xs font-mono rounded bg-[var(--bg-muted)] text-[var(--text-muted)] shrink-0"
					>
						{task.id}
					</span>
					<span class="truncate">{task.subject}</span>
				</h4>

				<!-- Status Badge -->
				{#if task.status === 'in_progress'}
					<span
						class="shrink-0 text-xs font-medium text-[var(--nav-blue)] uppercase tracking-wide"
					>
						In Progress
					</span>
				{:else if task.isBlocked}
					<span
						class="shrink-0 flex items-center gap-1 text-xs font-medium text-[var(--warning)]"
					>
						<AlertTriangle size={12} />
						Blocked
					</span>
				{/if}
			</div>

			<!-- Description preview or full -->
			<p class="text-sm text-[var(--text-secondary)] mt-1 {isExpanded ? '' : 'line-clamp-1'}">
				{task.description}
			</p>

			<!-- Live active_form for in_progress -->
			{#if task.status === 'in_progress' && task.active_form}
				<div class="flex items-center gap-2 mt-2 text-xs text-[var(--nav-blue)]">
					<span class="w-1.5 h-1.5 rounded-full bg-[var(--nav-blue)] animate-pulse"
					></span>
					{task.active_form}
				</div>
			{/if}

			<!-- Dependency labels -->
			{#if task.blocks.length > 0}
				<div class="text-xs text-[var(--text-muted)] mt-2">
					Blocks: {task.blocks.map((id) => `Task ${id}`).join(', ')}
				</div>
			{/if}

			{#if task.isBlocked && task.blocked_by.length > 0}
				<div class="text-xs text-[var(--warning)] mt-1">
					Waiting on: {task.blocked_by.map((id) => `Task ${id}`).join(', ')}
				</div>
			{/if}
		</div>
	</div>
</button>
