<script lang="ts">
	import {
		MessageSquare,
		Terminal,
		Bot,
		AlertCircle,
		CloudOff,
		X,
		Search,
		Brain,
		Sparkles,
		Zap,
		TerminalSquare,
		BookOpen,
		HelpCircle,
		Plug,
		ClipboardList,
		MessagesSquare,
		BellRing,
		Info,
		ScrollText
	} from 'lucide-svelte';
	import { onDestroy } from 'svelte';
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

	// Debounces the downstream search (a full metadata scan) so it doesn't re-run on every keystroke.
	let debounceTimeout: ReturnType<typeof setTimeout>;
	function handleSearchInput(value: string) {
		clearTimeout(debounceTimeout);
		debounceTimeout = setTimeout(() => onSearchChange(value), 200);
	}
	function clearSearch() {
		clearTimeout(debounceTimeout);
		onSearchChange('');
	}
	onDestroy(() => clearTimeout(debounceTimeout));

	// Cancels a pending debounced edit on external searchQuery changes, so a stale keystroke can't resurrect a cleared query.
	$effect(() => {
		void searchQuery;
		clearTimeout(debounceTimeout);
	});

	interface FilterChip {
		id: FilterCategory;
		label: string;
		icon: any;
		/** CSS colour the chip takes when active; matches the event's node colour */
		color: string;
		/** Grey chips need a stronger selected look, or selected reads as disabled */
		strong?: boolean;
		/** Longer explanation for the tooltip and screen readers */
		hint?: string;
	}

	// Chips grouped by who acts: you, Claude, tools, agents, the harness.
	const filterGroups: FilterChip[][] = [
		[
			{ id: 'prompt', label: 'Prompts', icon: MessageSquare, color: 'var(--event-prompt)' },
			{
				id: 'command',
				label: 'Commands',
				icon: TerminalSquare,
				color: 'var(--event-command)'
			}
		],
		[
			{ id: 'thinking', label: 'Thinking', icon: Brain, color: 'var(--event-thinking)' },
			{ id: 'response', label: 'Response', icon: Sparkles, color: 'var(--event-response)' },
			{
				id: 'big_response',
				label: 'Big Response',
				icon: BookOpen,
				color: 'var(--nav-amber)'
			},
			{ id: 'ask_user', label: 'Ask User', icon: HelpCircle, color: 'var(--nav-blue)' }
		],
		[
			{ id: 'tool_call', label: 'Tools', icon: Terminal, color: 'var(--event-tool)' },
			{ id: 'mcp_tool', label: 'MCP Tools', icon: Plug, color: 'var(--nav-indigo)' },
			{ id: 'skill', label: 'Skills', icon: Zap, color: 'var(--accent)' },
			{ id: 'task', label: 'Tasks', icon: ClipboardList, color: 'var(--event-todo)' },
			{ id: 'error', label: 'Errors', icon: AlertCircle, color: 'var(--error)' }
		],
		[
			{ id: 'subagent', label: 'Subagents', icon: Bot, color: 'var(--event-subagent)' },
			{
				id: 'message',
				label: 'Messages',
				icon: MessagesSquare,
				color: 'var(--event-message)'
			},
			{
				id: 'background',
				label: 'Background',
				icon: BellRing,
				color: 'var(--event-background)'
			}
		],
		[
			{
				id: 'api_error',
				label: 'API errors',
				icon: CloudOff,
				color: 'var(--event-system)',
				strong: true
			},
			{
				id: 'notice',
				label: 'Notices',
				icon: Info,
				color: 'var(--event-system)',
				strong: true
			},
			{
				id: 'system',
				label: 'System',
				icon: ScrollText,
				color: 'var(--event-system)',
				strong: true,
				hint: 'Reminders and other text added for Claude. Not shown unless selected.'
			}
		]
	];

	// Empty chips are not shown, and groups left empty take their divider with them.
	const visibleGroups = $derived(
		filterGroups
			.map((group) => group.filter((f) => counts[f.id] > 0))
			.filter((g) => g.length > 0)
	);

	const chipBase =
		'inline-flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium rounded-[var(--radius-md)] border transition-all duration-150 whitespace-nowrap';
	const chipActive = 'bg-[var(--chip)]/12 border-[var(--chip)]/50 text-[var(--chip)]';
	// Slate at the usual 12% tint reads as disabled, so grey chips get a stronger fill and full-contrast text.
	const chipActiveStrong =
		'bg-[var(--chip)]/25 border-[var(--chip)] text-[var(--text-primary)] font-semibold';
	const chipInactive =
		'bg-[var(--bg-base)] border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--chip)]/30 hover:bg-[var(--chip)]/5';

	// One id per filter bar for the hint text a chip points at.
	const hintIdBase = `timeline-filter-hint-${Math.random().toString(36).slice(2, 8)}`;

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
				oninput={(e) => handleSearchInput(e.currentTarget.value)}
				aria-label="Search events"
				placeholder="Search events..."
				data-timeline-search="true"
				class="
					w-full pl-8 pr-14 py-1.5
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
					onclick={clearSearch}
					class="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
				>
					<X size={12} strokeWidth={2} />
				</button>
			{:else}
				<div
					class="absolute right-2 top-1/2 -translate-y-1/2 pointer-events-none flex items-center gap-0.5"
				>
					<kbd
						class="inline-flex items-center justify-center rounded border border-[var(--border)] bg-[var(--bg-subtle)] px-1.5 py-0.5 text-[10px] font-sans text-[var(--text-faint)]"
						>⌘</kbd
					>
					<kbd
						class="inline-flex items-center justify-center rounded border border-[var(--border)] bg-[var(--bg-subtle)] px-1.5 py-0.5 text-[10px] font-sans text-[var(--text-faint)]"
						>K</kbd
					>
				</div>
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

	<!-- Bottom Row: Filters. Below lg one row that scrolls sideways; from lg up the chips wrap one by one. -->
	<div class="flex min-h-[32px] items-start gap-2">
		<!-- Clips the divider slot of whichever chip starts a row; the 4px padding keeps focus rings whole -->
		<div
			class="filter-chips -my-1 -ml-1 min-w-0 flex-1 overflow-x-auto py-1 pl-1 lg:overflow-x-clip lg:overflow-y-visible"
			role="group"
			aria-label="Filter events by kind"
		>
			<div class="filter-chip-row flex flex-nowrap items-center gap-y-2 lg:flex-wrap">
				{#each visibleGroups as group, groupIndex (group[0].id)}
					{#each group as filter, chipIndex (filter.id)}
						{@const count = counts[filter.id]}
						{@const isActive = activeFilters.has(filter.id)}
						{@const hintId = filter.hint ? `${hintIdBase}-${filter.id}` : undefined}
						<!-- Every chip has the same slot to its left; a group's first chip draws its divider there -->
						<span
							class="chip-slot inline-flex shrink-0 items-center"
							class:group-start={chipIndex === 0 && groupIndex > 0}
						>
							<button
								onclick={() => onToggle(filter.id)}
								onfocus={(e) =>
									e.currentTarget.scrollIntoView?.({
										inline: 'nearest',
										block: 'nearest'
									})}
								aria-pressed={isActive}
								aria-describedby={hintId}
								style="--chip: {filter.color}"
								class="{chipBase} {isActive
									? filter.strong
										? chipActiveStrong
										: chipActive
									: chipInactive}"
								title={filter.hint
									? `${filter.label} (${count}): ${filter.hint}`
									: `${filter.label} (${count})`}
							>
								<filter.icon size={14} strokeWidth={2} class="text-[var(--chip)]" />
								<span>{filter.label}</span>
								<span class="font-mono opacity-70">
									{count}
								</span>
							</button>
							{#if filter.hint}
								<span id={hintId} class="sr-only">{filter.hint}</span>
							{/if}
						</span>
					{/each}
				{/each}
			</div>
		</div>

		{#if hasActiveFilters}
			<button
				onclick={onClear}
				class="
					inline-flex shrink-0 items-center gap-1.5
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

<style>
	/* Pull the row left by one slot, so the slot of each row's first chip falls outside the clip edge. */
	.filter-chip-row {
		margin-left: -0.625rem;
	}

	.chip-slot {
		position: relative;
		padding-left: 0.625rem;
	}

	/* A 20px divider in the slot before the first chip of a group; clipped away when it starts a row. */
	.chip-slot.group-start::before {
		content: '';
		position: absolute;
		left: 0.25rem;
		top: 50%;
		width: 1px;
		height: 1.25rem;
		transform: translateY(-50%);
		background: var(--border);
	}

	/* The sideways-scrolling row needs no scrollbar chrome. */
	.filter-chips {
		scrollbar-width: none;
	}
	.filter-chips::-webkit-scrollbar {
		display: none;
	}
</style>
