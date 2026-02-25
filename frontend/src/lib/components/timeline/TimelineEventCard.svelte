<script lang="ts">
	import {
		ChevronDown,
		ChevronRight,
		Bot,
		CheckCircle2,
		AlertCircle,
		Copy,
		Check
	} from 'lucide-svelte';
	import { marked } from 'marked';
	import DOMPurify from 'isomorphic-dompurify';
	import type { TimelineEvent, EventImportance, TodoItem } from '$lib/api-types';
	import { formatElapsedTime, formatDate, truncate } from '$lib/utils';
	import { eventTypeConfig, getToolIcon } from './tool-icons';
	import ToolCallDetail from './ToolCallDetail.svelte';
	import TodoUpdateDetail from './TodoUpdateDetail.svelte';

	interface Props {
		event: TimelineEvent;
		index: number;
		isFirst: boolean;
		isLast: boolean;
		sessionStartTime: string;
		isHighlighted: boolean;
		hasActiveFilter: boolean;
		isFocused: boolean;
		isExpanded: boolean;
		onToggleExpand: () => void;
		usePopup?: boolean;
		onOpenPopup?: () => void;
		/** Current agent ID - when set, events from this agent won't show subagent badges */
		currentAgentId?: string | null;
		/** Project path for formatting file paths */
		projectPath?: string | null;
		/** Callback to hide this event */
		onToggleHide?: () => void;
		/** Search query for highlighting matches */
		searchQuery?: string;
	}

	let {
		event,
		index,
		isFirst,
		isLast,
		sessionStartTime,
		isHighlighted,
		hasActiveFilter,
		isFocused,
		isExpanded,
		onToggleExpand,
		usePopup = false,
		onOpenPopup,
		currentAgentId = null,
		projectPath = null,
		onToggleHide,
		searchQuery = ''
	}: Props = $props();

	let isCopied = $state(false);

	// Rendered markdown content for expanded view
	let renderedExpandedContent = $state('');

	// Render markdown when content changes or expansion state changes
	$effect(() => {
		if (isExpanded && hasExpandableContent) {
			const rawContent =
				event.metadata?.full_content ||
				event.metadata?.full_thinking ||
				event.metadata?.full_text ||
				event.metadata?.result_content ||
				event.summary ||
				'';

			const parsed = marked.parse(rawContent);
			if (parsed instanceof Promise) {
				parsed.then((html) => {
					renderedExpandedContent = DOMPurify.sanitize(html);
				});
			} else {
				renderedExpandedContent = DOMPurify.sanitize(parsed);
			}
		}
	});

	// Get event configuration
	const isPlanEvent = $derived(
		event.event_type === 'tool_call' &&
			(event.metadata?.tool_name === 'ExitPlanMode' ||
				event.metadata?.tool_name === 'EnterPlanMode')
	);
	const config = $derived(eventTypeConfig[event.event_type] || eventTypeConfig.tool_call);

	// Get tool-specific icon for tool_call events
	const toolName = $derived(event.metadata?.tool_name as string | undefined);
	const IconComponent = $derived(
		event.event_type === 'tool_call' ? getToolIcon(toolName) : config.icon
	);

	// Determine importance
	const importance = $derived.by<EventImportance>(() => {
		if (event.event_type === 'prompt') return 'high';
		if (event.metadata?.spawned_agent_id) return 'high';
		if (event.event_type === 'todo_update') return 'medium';
		if (event.event_type === 'tool_call') {
			const modifyTools = ['Write', 'Edit', 'StrReplace', 'Delete', 'Bash', 'Shell'];
			if (toolName && modifyTools.includes(toolName)) return 'medium';
		}
		return 'low';
	});

	// Check for expandable content
	const hasToolResult = $derived(event.metadata?.has_result === true);

	// Get todos for todo_update events
	const todosArray = $derived.by<TodoItem[]>(() => {
		if (event.event_type === 'todo_update' && Array.isArray(event.metadata?.todos)) {
			return event.metadata.todos as TodoItem[];
		}
		return [];
	});
	const hasExpandableTodos = $derived(todosArray.length > 3);

	const hasExpandableContent = $derived(
		event.event_type === 'tool_call' ||
			event.event_type === 'todo_update' ||
			event.metadata?.full_content ||
			event.metadata?.full_thinking ||
			event.metadata?.full_text ||
			event.metadata?.result_content ||
			(event.summary && event.summary.length > 100)
	);

	// Dimmed when filter active but doesn't match
	const isDimmed = $derived(hasActiveFilter && !isHighlighted);

	// Show actor badge only if:
	// 1. Event is from a subagent (actor_type === 'subagent')
	// 2. AND it's not the current agent being viewed (for agent timeline views)
	const shouldShowActorBadge = $derived(
		event.actor_type === 'subagent' && (!currentAgentId || event.actor !== currentAgentId)
	);

	function highlightText(text: string, query: string): string {
		if (!query || !text) return text;
		const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
		const regex = new RegExp(`(${escaped})`, 'gi');
		return text.replace(regex, '<mark class="search-highlight">$1</mark>');
	}
</script>

<div
	data-event-index={index}
	class="
		group relative flex gap-4 transition-all duration-200
	"
>
	<!-- Rail line -->
	<div class="relative flex flex-col items-center">
		<!-- Top connector -->
		{#if !isFirst}
			<div
				class="absolute -top-4 h-4 w-px bg-gradient-to-b from-[var(--border)] to-[var(--border)]/50"
			></div>
		{/if}

		<!-- Node circle -->
		<button
			class="
				relative z-10 flex h-8 w-8 items-center justify-center rounded-full border-2 transition-all duration-200
				{isPlanEvent ? 'bg-[var(--event-plan-subtle)]' : config.bgColor}
				{isPlanEvent ? 'border-[var(--event-plan)]/60' : config.borderColor}
				group-hover:scale-110 group-hover:shadow-lg
				{importance === 'high'
				? 'ring-2 ring-offset-2 ring-offset-[var(--bg-base)] ring-[var(--accent)]/20'
				: ''}
				{isFocused ? 'scale-110 shadow-lg' : ''}
				cursor-pointer hover:opacity-80
			"
			onclick={(e) => {
				e.stopPropagation();
				if (onToggleHide) onToggleHide();
			}}
			title="Hide event"
			aria-label="Hide event"
		>
			<IconComponent
				class="h-4 w-4 {isPlanEvent ? 'text-[var(--event-plan)]' : config.color}"
			/>
		</button>

		<!-- Bottom connector -->
		{#if !isLast}
			<div
				class="h-full w-px flex-1 bg-gradient-to-b from-[var(--border)]/50 to-[var(--border)]"
			></div>
		{/if}
	</div>

	<!-- Content card -->
	<div
		class="
			mb-4 flex-1 min-w-0 rounded-lg border border-l-[3px] bg-[var(--bg-subtle)] p-4 pl-5 transition-all duration-200
			hover:shadow-md
			{hasExpandableContent ? 'cursor-pointer' : ''}
			{isPlanEvent ? 'border-[var(--event-plan)]/60' : config.borderColor}
			{isPlanEvent ? 'border-l-[var(--event-plan)]' : config.leftAccent}
			{isFocused ? 'shadow-md ring-1 ring-[var(--accent)]/20' : ''}
		"
		onclick={() => {
			if (!hasExpandableContent) return;
			if (usePopup && onOpenPopup) {
				onOpenPopup();
			} else {
				onToggleExpand();
			}
		}}
		onkeydown={(e) => {
			if (hasExpandableContent && (e.key === 'Enter' || e.key === ' ')) {
				e.preventDefault();
				if (usePopup && onOpenPopup) {
					onOpenPopup();
				} else {
					onToggleExpand();
				}
			}
		}}
		role={hasExpandableContent ? 'button' : undefined}
		tabindex={hasExpandableContent ? 0 : undefined}
	>
		<!-- Header -->
		<div class="flex items-start justify-between gap-4">
			<div class="flex-1 space-y-1">
				<!-- Title and badges -->
				<div class="flex items-center gap-2 flex-wrap">
					<span class="font-medium text-[var(--text-primary)]">
						{#if searchQuery}
							{@html highlightText(event.title, searchQuery)}
						{:else}
							{event.title}
						{/if}
					</span>

					<!-- Actor badge (if subagent and not the current agent being viewed) -->
					{#if shouldShowActorBadge}
						<span
							class="inline-flex items-center gap-1 rounded-full bg-[var(--event-subagent-subtle)] px-2 py-0.5 text-[10px] font-medium text-[var(--event-subagent)]"
						>
							<Bot class="h-2.5 w-2.5" />
							{event.actor}
						</span>
					{/if}

					<!-- Tool name badge -->
					{#if toolName && event.event_type === 'tool_call'}
						<span
							class="rounded bg-[var(--bg-muted)] px-1.5 py-0.5 text-[10px] font-mono text-[var(--text-muted)]"
						>
							{toolName}
						</span>
					{/if}

					<!-- Result status badge -->
					{#if event.event_type === 'tool_call'}
						{#if !hasToolResult}
							<span
								class="inline-flex items-center gap-1 rounded-full bg-[var(--warning-subtle)] px-2 py-0.5 text-[10px] font-medium text-[var(--warning)]"
							>
								pending
							</span>
						{:else if event.metadata?.result_status === 'error'}
							<span
								class="inline-flex items-center gap-1 rounded-full bg-[var(--error-subtle)] px-2 py-0.5 text-[10px] font-medium text-[var(--error)]"
							>
								<AlertCircle class="h-2.5 w-2.5" />
								error
							</span>
						{:else}
							<span
								class="inline-flex items-center gap-1 rounded-full bg-[var(--success-subtle)] px-2 py-0.5 text-[10px] font-medium text-[var(--success)]"
							>
								<CheckCircle2 class="h-2.5 w-2.5" />
								done
							</span>
						{/if}
					{/if}

					<!-- Spawned agent badge -->
					{#if event.metadata?.spawned_agent_id}
						<span
							class="inline-flex items-center gap-1 rounded-full bg-[var(--event-subagent-subtle)] px-2 py-0.5 text-[10px] font-medium text-[var(--event-subagent)]"
						>
							<Bot class="h-2.5 w-2.5" />
							→ {event.metadata.spawned_agent_id}
						</span>
					{/if}
				</div>

				<!-- Summary - show regular summary for non-todo events -->
				{#if event.summary && event.event_type !== 'todo_update'}
					<p class="font-mono text-xs text-[var(--text-muted)]">
						{#if searchQuery}
							{@html highlightText(
								isExpanded ? event.summary : truncate(event.summary, 100),
								searchQuery
							)}
						{:else}
							{isExpanded ? event.summary : truncate(event.summary, 100)}
						{/if}
					</p>
				{/if}

				<!-- Todo preview - show inline for todo_update events -->
				{#if event.event_type === 'todo_update'}
					<div class="mt-1">
						<TodoUpdateDetail
							todos={todosArray}
							action={event.metadata?.action as 'set' | 'merge' | undefined}
							agentSlug={event.metadata?.agent_slug as string | undefined}
							{isExpanded}
						/>
					</div>
				{/if}
			</div>

			<!-- Timestamp and expand -->
			<div class="flex items-center gap-2 shrink-0">
				<span
					class="whitespace-nowrap font-mono text-xs text-[var(--text-muted)]/70 tabular-nums"
					title={formatDate(event.timestamp)}
				>
					{formatElapsedTime(event.timestamp, sessionStartTime)}
				</span>
				{#if hasExpandableContent}
					<button
						class="rounded p-0.5 text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-muted)] hover:text-[var(--text-primary)]"
						aria-expanded={isExpanded}
						aria-label={isExpanded ? 'Collapse' : 'Expand'}
					>
						{#if isExpanded}
							<ChevronDown class="h-4 w-4" />
						{:else}
							<ChevronRight class="h-4 w-4" />
						{/if}
					</button>
				{/if}
			</div>
		</div>

		<!-- Expanded content (only shown for inline expansion, not when using popup) -->
		{#if isExpanded && hasExpandableContent && !usePopup}
			<!-- Tool call detail - use specialized component -->
			{#if event.event_type === 'tool_call'}
				<ToolCallDetail {event} {projectPath} />
			{:else if event.event_type !== 'todo_update'}
				<!-- Non-tool-call, non-todo content (prompts, thinking, responses) -->
				<div class="mt-3 border-t border-[var(--border)] pt-3 relative">
					<div class="rounded bg-[var(--bg-muted)]/50 p-3 relative">
						<button
							class="
								sticky top-2 float-right
								ml-2 mb-2
								p-1.5
								rounded-md
								bg-[var(--bg-base)]
								border border-[var(--border)]
								text-[var(--text-muted)]
								shadow-sm
								hover:text-[var(--text-primary)] hover:border-[var(--accent)]
								transition-colors
								z-10
							"
							onclick={(e) => {
								e.stopPropagation();
								const content =
									event.metadata?.full_content ||
									event.metadata?.full_thinking ||
									event.metadata?.full_text ||
									event.metadata?.result_content ||
									event.summary ||
									'';
								navigator.clipboard.writeText(content);
								isCopied = true;
								setTimeout(() => (isCopied = false), 2000);
							}}
							title="Copy content"
						>
							{#if isCopied}
								<Check size={14} class="text-[var(--success)]" />
							{:else}
								<Copy size={14} />
							{/if}
						</button>
						<div class="markdown-preview text-sm">
							{@html renderedExpandedContent}
						</div>
					</div>
				</div>
			{/if}
			<!-- todo_update uses TodoUpdateDetail inline, no extra expanded content needed -->
		{/if}
	</div>
</div>
