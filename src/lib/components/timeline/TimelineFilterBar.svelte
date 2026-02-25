<script lang="ts">
	import {
		MessageSquare,
		Terminal,
		Bot,
		ListTodo,
		AlertCircle,
		X,
		Search,
		Brain,
		Sparkles,
		Zap,
		TerminalSquare
	} from 'lucide-svelte';
	import type { FilterCategory, FilterCounts } from '$lib/api-types';

	interface Props {
		counts: FilterCounts;
		activeFilters: Set<FilterCategory>;
		totalEvents: number;
		matchingEvents: number;
		onToggle: (filter: FilterCategory) => void;
		onClear: () => void;
		searchQuery: string;
		onSearchChange: (query: string) => void;
		class?: string;
	}

	let {
		counts,
		activeFilters,
		totalEvents,
		matchingEvents,
		onToggle,
		onClear,
		searchQuery,
		onSearchChange,
		class: className = ''
	}: Props = $props();

	// Color mapping for each filter category - matches timeline event node colors
	const filterColors: Record<
		FilterCategory,
		{ active: string; inactive: string; icon: string; hoverBg: string }
	> = {
		prompt: {
			active: 'bg-[var(--event-prompt-subtle)] border-[var(--event-prompt)]/50 text-[var(--event-prompt)]',
			inactive:
				'bg-[var(--bg-base)] border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--event-prompt)]/30',
			icon: 'text-[var(--event-prompt)]',
			hoverBg: 'hover:bg-[var(--event-prompt-subtle)]/50'
		},
		tool_call: {
			active: 'bg-[var(--event-tool-subtle)] border-[var(--event-tool)]/50 text-[var(--event-tool)]',
			inactive:
				'bg-[var(--bg-base)] border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--event-tool)]/30',
			icon: 'text-[var(--event-tool)]',
			hoverBg: 'hover:bg-[var(--event-tool-subtle)]/50'
		},
		subagent: {
			active: 'bg-[var(--event-subagent-subtle)] border-[var(--event-subagent)]/50 text-[var(--event-subagent)]',
			inactive:
				'bg-[var(--bg-base)] border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--event-subagent)]/30',
			icon: 'text-[var(--event-subagent)]',
			hoverBg: 'hover:bg-[var(--event-subagent-subtle)]/50'
		},
		todo_update: {
			active: 'bg-[var(--event-todo-subtle)] border-[var(--event-todo)]/50 text-[var(--event-todo)]',
			inactive:
				'bg-[var(--bg-base)] border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--event-todo)]/30',
			icon: 'text-[var(--event-todo)]',
			hoverBg: 'hover:bg-[var(--event-todo-subtle)]/50'
		},
		error: {
			active: 'bg-[var(--error-subtle)] border-[var(--error)]/50 text-[var(--error)]',
			inactive:
				'bg-[var(--bg-base)] border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--error)]/30',
			icon: 'text-[var(--error)]',
			hoverBg: 'hover:bg-[var(--error-subtle)]/50'
		},
		thinking: {
			active: 'bg-[var(--event-thinking-subtle)] border-[var(--event-thinking)]/50 text-[var(--event-thinking)]',
			inactive:
				'bg-[var(--bg-base)] border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--event-thinking)]/30',
			icon: 'text-[var(--event-thinking)]',
			hoverBg: 'hover:bg-[var(--event-thinking-subtle)]/50'
		},
		response: {
			active: 'bg-[var(--event-response-subtle)] border-[var(--event-response)]/50 text-[var(--event-response)]',
			inactive:
				'bg-[var(--bg-base)] border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--event-response)]/30',
			icon: 'text-[var(--event-response)]',
			hoverBg: 'hover:bg-[var(--event-response-subtle)]/50'
		},
		skill: {
			active: 'bg-purple-500/10 border-purple-500/50 text-purple-500',
			inactive:
				'bg-[var(--bg-base)] border-[var(--border)] text-[var(--text-secondary)] hover:border-purple-500/30',
			icon: 'text-purple-500',
			hoverBg: 'hover:bg-purple-500/5'
		},
		command: {
			active: 'bg-teal-500/10 border-teal-500/50 text-teal-500',
			inactive:
				'bg-[var(--bg-base)] border-[var(--border)] text-[var(--text-secondary)] hover:border-teal-500/30',
			icon: 'text-teal-500',
			hoverBg: 'hover:bg-teal-500/5'
		}
	};

	// Define filters with their metadata
	const filters = [
		{
			id: 'prompt' as const,
			label: 'Prompts',
			icon: MessageSquare,
			countKey: 'prompt' as const
		},
		{
			id: 'tool_call' as const,
			label: 'Tools',
			icon: Terminal,
			countKey: 'tool_call' as const
		},
		{ id: 'subagent' as const, label: 'Subagents', icon: Bot, countKey: 'subagent' as const },
		{
			id: 'todo_update' as const,
			label: 'Todos',
			icon: ListTodo,
			countKey: 'todo_update' as const
		},
		{ id: 'error' as const, label: 'Errors', icon: AlertCircle, countKey: 'error' as const },
		{
			id: 'thinking' as const,
			label: 'Thinking',
			icon: Brain,
			countKey: 'thinking' as const
		},
		{
			id: 'response' as const,
			label: 'Response',
			icon: Sparkles,
			countKey: 'response' as const
		},
		{
			id: 'skill' as const,
			label: 'Skills',
			icon: Zap,
			countKey: 'skill' as const
		},
		{
			id: 'command' as const,
			label: 'Commands',
			icon: TerminalSquare,
			countKey: 'command' as const
		}
	];

	const hasActiveFilters = $derived(activeFilters.size > 0 || searchQuery.length > 0);
</script>

<div
	class="
		flex flex-col gap-2.5 p-3
		bg-[var(--bg-subtle)]
		border border-[var(--border)]
		rounded-[var(--radius-lg)]
		{className}
	"
>
	<!-- Top Row: Search and Event Count -->
	<div class="flex items-center justify-between gap-4">
		<!-- Search Input -->
		<div class="relative group flex-1">
			<div
				class="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--text-muted)] group-focus-within:text-[var(--text-primary)] transition-colors"
			>
				<Search size={14} strokeWidth={2} />
			</div>
			<input
				type="text"
				value={searchQuery}
				oninput={(e) => onSearchChange(e.currentTarget.value)}
				placeholder="Search events..."
				class="
					w-full pl-8 pr-3 py-1.5
					text-xs
					bg-[var(--bg-base)]
					border border-[var(--border)]
					rounded-[var(--radius-md)]
					focus:outline-none focus:border-[var(--accent)]
					transition-all
					placeholder:text-[var(--text-faint)]
				"
			/>
			{#if searchQuery}
				<button
					onclick={() => onSearchChange('')}
					class="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
				>
					<X size={12} strokeWidth={2} />
				</button>
			{/if}
		</div>

		<!-- Event Count -->
		<div class="text-[11px] text-[var(--text-muted)] font-mono shrink-0 opacity-60">
			{#if hasActiveFilters}
				<span class="text-[var(--text-primary)] font-semibold opacity-100"
					>{matchingEvents}</span
				>
				<span class="opacity-50"> of </span>
				<span class="opacity-80">{totalEvents}</span>
				<span class="opacity-50 ml-0.5">events</span>
			{:else}
				<span class="font-medium opacity-80">{totalEvents}</span>
				<span class="opacity-50 ml-0.5">events</span>
			{/if}
		</div>
	</div>

	<!-- Bottom Row: Filters -->
	<div class="flex flex-wrap items-center gap-x-1.5 gap-y-2 min-h-[32px]">
		{#each filters as filter}
			{@const count = counts[filter.countKey]}
			{@const isActive = activeFilters.has(filter.id)}
			{@const colors = filterColors[filter.id]}

			{#if count > 0}
				<button
					onclick={() => onToggle(filter.id)}
					class="
						inline-flex items-center gap-1.5
						px-2.5 py-1.5
						text-xs font-medium
						rounded-[var(--radius-md)]
						border
						transition-all duration-150
						whitespace-nowrap
						{isActive ? colors.active : colors.inactive}
						{!isActive ? colors.hoverBg : ''}
					"
					title="{filter.label} ({count})"
				>
					<filter.icon size={14} strokeWidth={2} class={colors.icon} />
					<span class="hidden md:inline">{filter.label}</span>
					<span class="font-mono opacity-70">
						{count}
					</span>
				</button>
			{/if}
		{/each}

		{#if hasActiveFilters}
			<button
				onclick={onClear}
				class="
					ml-auto
					inline-flex items-center gap-1.5
					px-2.5 py-1.5
					text-xs font-medium
					text-[var(--text-muted)]
					hover:text-[var(--text-primary)]
					hover:bg-[var(--bg-muted)]
					rounded-[var(--radius-md)]
					border border-[var(--border)]
					transition-colors
				"
			>
				<X size={14} strokeWidth={2} />
				<span>Clear</span>
			</button>
		{/if}
	</div>
</div>
