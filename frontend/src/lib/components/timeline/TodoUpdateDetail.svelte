<script lang="ts">
	import {
		CheckCircle2,
		Circle,
		CircleDot,
		ChevronDown,
		ChevronRight,
		ListTodo,
		Bot
	} from 'lucide-svelte';
	import type { TodoItem } from '$lib/api-types';

	interface Props {
		todos: TodoItem[];
		action?: 'set' | 'merge';
		agentSlug?: string;
		isExpanded?: boolean;
		class?: string;
	}

	let { todos, action, agentSlug, isExpanded = false, class: className = '' }: Props = $props();

	// Calculate counts
	const completed = $derived(todos.filter((t) => t.status === 'completed').length);
	const inProgress = $derived(todos.filter((t) => t.status === 'in_progress').length);
	const pending = $derived(todos.filter((t) => t.status === 'pending').length);
	const total = $derived(todos.length);

	// Show inline if few items and not expanded
	const inlineLimit = 3;
	const showInline = $derived(!isExpanded && todos.length <= inlineLimit);
	const showCollapsed = $derived(!isExpanded && todos.length > inlineLimit);

	// Progress percentages
	const completedPercent = $derived(total > 0 ? (completed / total) * 100 : 0);
	const inProgressPercent = $derived(total > 0 ? (inProgress / total) * 100 : 0);
</script>

<div class="space-y-3 {className}">
	<!-- Header badges -->
	<div class="flex items-center gap-2 flex-wrap">
		<span
			class="text-xs px-2 py-0.5 rounded inline-flex items-center gap-1
			{action === 'merge'
				? 'bg-[var(--event-prompt-subtle)] text-[var(--event-prompt)]'
				: 'bg-[var(--event-todo-subtle)] text-[var(--event-todo)]'}"
		>
			<ListTodo size={12} />
			{action === 'merge' ? 'Merged' : 'Set'}
			{total} todo{total !== 1 ? 's' : ''}
		</span>
		{#if agentSlug}
			<span
				class="text-xs px-2 py-0.5 rounded bg-[var(--event-subagent-subtle)] text-[var(--event-subagent)] inline-flex items-center gap-1"
			>
				<Bot size={12} />
				by {agentSlug}
			</span>
		{/if}
	</div>

	<!-- Summary counts -->
	<div class="flex items-center gap-3 text-xs text-[var(--text-muted)]">
		{#if completed > 0}
			<span class="flex items-center gap-1 text-[var(--success)]">
				<CheckCircle2 size={12} />
				{completed} completed
			</span>
		{/if}
		{#if inProgress > 0}
			<span class="flex items-center gap-1 text-[var(--warning)]">
				<CircleDot size={12} class="animate-pulse" />
				{inProgress} in progress
			</span>
		{/if}
		{#if pending > 0}
			<span class="flex items-center gap-1 text-[var(--text-muted)]">
				<Circle size={12} />
				{pending} pending
			</span>
		{/if}
	</div>

	<!-- Progress bar -->
	{#if total > 0}
		<div class="h-1.5 w-full bg-[var(--bg-muted)] rounded-full overflow-hidden flex">
			{#if completedPercent > 0}
				<div
					class="h-full bg-[var(--success)] transition-all duration-300"
					style="width: {completedPercent}%"
				></div>
			{/if}
			{#if inProgressPercent > 0}
				<div
					class="h-full bg-[var(--warning)] transition-all duration-300"
					style="width: {inProgressPercent}%"
				></div>
			{/if}
		</div>
	{/if}

	<!-- Inline todo list (few items) -->
	{#if showInline && todos.length > 0}
		<div
			class="p-2 rounded-[var(--radius-md)] bg-[var(--bg-muted)]/30 border border-[var(--border)]/50 space-y-1"
		>
			{#each todos as todo, index}
				<div
					class="flex items-start gap-3 p-2 rounded transition-colors
					{todo.status === 'completed' ? 'bg-[var(--success-subtle)]' : ''}
					{todo.status === 'in_progress' ? 'bg-[var(--warning-subtle)]' : ''}"
				>
					<!-- Status icon -->
					{#if todo.status === 'completed'}
						<CheckCircle2 size={16} class="text-[var(--success)] shrink-0 mt-0.5" />
					{:else if todo.status === 'in_progress'}
						<CircleDot
							size={16}
							class="text-[var(--warning)] shrink-0 mt-0.5 animate-pulse"
						/>
					{:else}
						<Circle size={16} class="text-[var(--text-muted)] shrink-0 mt-0.5" />
					{/if}

					<!-- Content -->
					<div class="flex-1 min-w-0">
						<p
							class="text-sm {todo.status === 'completed'
								? 'text-[var(--text-muted)] line-through'
								: 'text-[var(--text-primary)]'}"
						>
							{todo.content}
						</p>
						{#if todo.status === 'in_progress' && todo.activeForm}
							<p class="text-xs text-[var(--warning)] mt-0.5 italic">
								{todo.activeForm}...
							</p>
						{/if}
					</div>

					<!-- Status badge -->
					<span
						class="text-[10px] px-1.5 py-0.5 rounded shrink-0
						{todo.status === 'completed' ? 'bg-[var(--success-subtle)] text-[var(--success)]' : ''}
						{todo.status === 'in_progress' ? 'bg-[var(--warning-subtle)] text-[var(--warning)]' : ''}
						{todo.status === 'pending' ? 'bg-[var(--bg-muted)] text-[var(--text-muted)]' : ''}"
					>
						{todo.status.replace('_', ' ')}
					</span>
				</div>
			{/each}
		</div>
	{/if}

	<!-- Collapsed hint -->
	{#if showCollapsed}
		<div class="text-xs text-[var(--text-muted)] flex items-center gap-1">
			<ChevronRight size={12} />
			Click to see all {todos.length} todos
		</div>
	{/if}

	<!-- Expanded todo list (all items) -->
	{#if isExpanded && todos.length > 0}
		<div
			class="p-3 rounded-[var(--radius-md)] bg-[var(--bg-muted)]/30 border border-[var(--border)]/50 space-y-1"
		>
			{#each todos as todo, index}
				<div
					class="flex items-start gap-3 p-2 rounded transition-colors
					{todo.status === 'completed' ? 'bg-[var(--success-subtle)]' : ''}
					{todo.status === 'in_progress' ? 'bg-[var(--warning-subtle)]' : ''}"
				>
					<!-- Status icon -->
					{#if todo.status === 'completed'}
						<CheckCircle2 size={16} class="text-[var(--success)] shrink-0 mt-0.5" />
					{:else if todo.status === 'in_progress'}
						<CircleDot
							size={16}
							class="text-[var(--warning)] shrink-0 mt-0.5 animate-pulse"
						/>
					{:else}
						<Circle size={16} class="text-[var(--text-muted)] shrink-0 mt-0.5" />
					{/if}

					<!-- Content -->
					<div class="flex-1 min-w-0">
						<p
							class="text-sm {todo.status === 'completed'
								? 'text-[var(--text-muted)] line-through'
								: 'text-[var(--text-primary)]'}"
						>
							{#if todos.length > 5}
								<span class="text-[var(--text-muted)] mr-1">{index + 1}.</span>
							{/if}
							{todo.content}
						</p>
						{#if todo.status === 'in_progress' && todo.activeForm}
							<p class="text-xs text-[var(--warning)] mt-0.5 italic">
								{todo.activeForm}...
							</p>
						{/if}
					</div>

					<!-- Status badge -->
					<span
						class="text-[10px] px-1.5 py-0.5 rounded shrink-0
						{todo.status === 'completed' ? 'bg-[var(--success-subtle)] text-[var(--success)]' : ''}
						{todo.status === 'in_progress' ? 'bg-[var(--warning-subtle)] text-[var(--warning)]' : ''}
						{todo.status === 'pending' ? 'bg-[var(--bg-muted)] text-[var(--text-muted)]' : ''}"
					>
						{todo.status.replace('_', ' ')}
					</span>
				</div>
			{/each}
		</div>
	{/if}
</div>
