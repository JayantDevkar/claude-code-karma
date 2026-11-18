<script lang="ts">
	import {
		ChevronDown,
		ChevronRight,
		CheckCircle2,
		AlertCircle,
		CirclePause,
		Hand
	} from 'lucide-svelte';
	import type { TimelineEvent, EventImportance, TodoItem } from '$lib/api-types';
	import { formatElapsedTime, formatDate, truncate } from '$lib/utils';
	import { getEventConfig, apiErrorToneConfig, getToolIcon } from './tool-icons';
	import ToolCallDetail from './ToolCallDetail.svelte';
	import TodoUpdateDetail from './TodoUpdateDetail.svelte';
	import EventContent from './EventContent.svelte';
	import EventTitle from './EventTitle.svelte';
	import { highlightPlainText } from '$lib/utils/highlight';
	import { matchesSearch } from '$lib/utils/timelineLogic.svelte';
	import {
		buildAgentHref,
		getDisplaySummary,
		getDisplayTitle,
		getEventBadgeLabels,
		getEventBadges,
		getEventTags,
		getPeerLabel,
		isEventExpandable,
		isFailedTask
	} from './timeline-display';

	interface Props {
		event: TimelineEvent;
		index: number;
		isFirst: boolean;
		isLast: boolean;
		sessionStartTime: string;
		isHighlighted: boolean;
		hasActiveFilter: boolean;
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
		/** Project encoded name for building agent links */
		projectEncoded?: string;
		/** Session slug for building agent links */
		sessionSlug?: string;
	}

	let {
		event,
		index,
		isFirst,
		isLast,
		sessionStartTime,
		isHighlighted: _isHighlighted,
		hasActiveFilter: _hasActiveFilter,
		isExpanded,
		onToggleExpand,
		usePopup = false,
		onOpenPopup,
		currentAgentId = null,
		projectPath = null,
		onToggleHide,
		searchQuery = '',
		projectEncoded,
		sessionSlug
	}: Props = $props();

	const meta = $derived(event.metadata ?? {});
	const type = $derived(event.event_type);

	const isPlanEvent = $derived(
		type === 'tool_call' &&
			(meta.tool_name === 'ExitPlanMode' || meta.tool_name === 'EnterPlanMode')
	);
	const isHealedApiError = $derived(type === 'api_error' && meta.healed === true);
	const isMediumEffortThinking = $derived(
		type === 'thinking' && !meta.full_thinking && !event.summary
	);
	const failedTask = $derived(isFailedTask(event));
	const isAgentIdle = $derived(type === 'system_context' && meta.kind === 'agent_idle');

	// compaction is a boundary across the rail; quiet rows are low-emphasis one-liners.
	const variant = $derived.by<'boundary' | 'quiet' | 'card'>(() => {
		if (type === 'compaction') return 'boundary';
		// System events only appear when their filter is selected, so they render as full cards.
		if (isMediumEffortThinking || isHealedApiError) return 'quiet';
		if (type === 'system_notice' && meta.kind === 'interrupted') return 'quiet';
		return 'card';
	});

	// Loud only for the final (unhealed) limit/refusal turn and failed background tasks.
	const config = $derived.by(() => {
		const base = getEventConfig(type);
		if (type === 'api_error' && !meta.healed) {
			if (meta.kind === 'limit') return apiErrorToneConfig.warning;
			if (meta.kind === 'refusal') return apiErrorToneConfig.error;
		}
		if (failedTask) return { ...apiErrorToneConfig.error, icon: base.icon };
		if (isAgentIdle) return { ...base, icon: CirclePause };
		if (type === 'system_notice' && meta.kind === 'interrupted') return { ...base, icon: Hand };
		// A notice the harness flagged as a warning or error keeps its icon but takes that tone.
		if (type === 'system_notice') {
			if (meta.level === 'warning') return { ...apiErrorToneConfig.warning, icon: base.icon };
			if (meta.level === 'error') return { ...apiErrorToneConfig.error, icon: base.icon };
		}
		return base;
	});

	const toolName = $derived(meta.tool_name as string | undefined);
	const IconComponent = $derived(type === 'tool_call' ? getToolIcon(toolName) : config.icon);

	const displayTitle = $derived(getDisplayTitle(event));
	const displaySummary = $derived(getDisplaySummary(event));

	const importance = $derived.by<EventImportance>(() => {
		if (type === 'prompt') return 'high';
		if (meta.spawned_agent_id) return 'high';
		if (type === 'todo_update') return 'medium';
		if (type === 'tool_call') {
			const modifyTools = ['Write', 'Edit', 'StrReplace', 'Delete', 'Bash', 'Shell'];
			if (toolName && modifyTools.includes(toolName)) return 'medium';
		}
		return 'low';
	});

	const hasToolResult = $derived(meta.has_result === true);

	const todosArray = $derived.by<TodoItem[]>(() => {
		if (type === 'todo_update' && Array.isArray(meta.todos)) return meta.todos as TodoItem[];
		return [];
	});

	const hasExpandableContent = $derived(isEventExpandable(event));

	function agentHref(agentId: string): string | null {
		return buildAgentHref(projectEncoded, sessionSlug, agentId);
	}

	// On an agent's page, its parent session is one click away.
	const mainSessionHref = $derived(
		currentAgentId && projectEncoded && sessionSlug
			? `/projects/${projectEncoded}/${sessionSlug}`
			: null
	);

	// The same badges and tags the popup shows; kept here only for the search-match check.
	const badgeLabels = $derived(getEventBadgeLabels(getEventBadges(event, currentAgentId)));
	const tags = $derived(getEventTags(event));

	const quietNote = $derived.by(() => {
		if (isMediumEffortThinking) return 'content not stored';
		if (isHealedApiError) return 'resumed';
		return '';
	});

	// True when the event matched the search but the match is buried in content not shown on the collapsed card.
	const hasHiddenMatch = $derived.by(() => {
		if (isExpanded) return false;
		const trimmedQuery = searchQuery.trim();
		if (!trimmedQuery) return false;

		const visibleParts = [displayTitle, ...tags];
		if (displaySummary && type !== 'todo_update')
			visibleParts.push(truncate(displaySummary, 100));
		if (toolName && type === 'tool_call') visibleParts.push(toolName);
		visibleParts.push(...badgeLabels);
		if (type === 'message') visibleParts.push(getPeerLabel(event));
		if (type === 'todo_update' && todosArray.length <= 3) {
			// Mirrors TodoUpdateDetail's own inlineLimit (beyond 3 it shows a "click to see all" hint, not content).
			for (const todo of todosArray) {
				visibleParts.push(todo.content);
				if (todo.status === 'in_progress' && todo.activeForm)
					visibleParts.push(todo.activeForm);
			}
		}
		const visibleText = visibleParts.join(' ').toLowerCase();
		if (visibleText.includes(trimmedQuery.toLowerCase())) return false;
		return matchesSearch(event, searchQuery);
	});

	function open() {
		if (!hasExpandableContent) return;
		if (usePopup && onOpenPopup) onOpenPopup();
		else onToggleExpand();
	}

	// One tab stop per card: Delete on its control hides the event. A Mac's delete key sends Backspace.
	function hideOnDelete(e: KeyboardEvent) {
		if ((e.key !== 'Delete' && e.key !== 'Backspace') || !onToggleHide) return;
		e.preventDefault();
		// A held key repeats on whichever card focus moved to; one press hides one event.
		if (e.repeat) return;
		onToggleHide();
	}

	// The whole card opens on a mouse click; clicks on the controls inside it are theirs alone.
	function openFromCard(e: MouseEvent) {
		const target = e.target as HTMLElement | null;
		if (target?.closest('a, button, input, textarea, select')) return;
		open();
	}
</script>

{#snippet highlighted(text: string)}
	{#if searchQuery}{@html highlightPlainText(text, searchQuery)}{:else}{text}{/if}
{/snippet}

{#snippet tagList()}
	{#each tags as tag, i (i)}
		<span
			class="max-w-full rounded bg-[var(--bg-muted)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--text-secondary)] [overflow-wrap:anywhere]"
		>
			{@render highlighted(tag)}
		</span>
	{/each}
{/snippet}

{#snippet trailing(dim: boolean)}
	<div class="flex shrink-0 items-center gap-2 self-end sm:self-auto">
		{#if hasHiddenMatch}
			<span
				class="h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--warning)]"
				title="Search match found in expanded content"
			></span>
		{/if}
		<span
			class="whitespace-nowrap font-mono text-xs tabular-nums {dim
				? 'text-[var(--text-muted)]/50'
				: 'text-[var(--text-muted)]/70'}"
			title={formatDate(event.timestamp)}
		>
			{formatElapsedTime(event.timestamp, sessionStartTime)}
		</span>
		{#if hasExpandableContent}
			<!-- The one keyboard control for opening the event -->
			<button
				type="button"
				class="rounded p-0.5 text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-muted)] hover:text-[var(--text-primary)]"
				aria-expanded={usePopup ? undefined : isExpanded}
				aria-haspopup={usePopup ? 'dialog' : undefined}
				aria-label="{isExpanded ? 'Collapse' : 'Show'} details: {displayTitle}"
				aria-keyshortcuts="Delete Backspace"
				title="{isExpanded ? 'Collapse' : 'Show'} details. Press Delete to hide this event."
				data-timeline-primary
				onclick={open}
				onkeydown={hideOnDelete}
			>
				{#if isExpanded}
					<ChevronDown class="h-4 w-4" />
				{:else}
					<ChevronRight class="h-4 w-4" />
				{/if}
			</button>
		{/if}
	</div>
{/snippet}

{#snippet expanded()}
	{#if isExpanded && hasExpandableContent && !usePopup}
		{#if type === 'tool_call'}
			<ToolCallDetail {event} {projectPath} {searchQuery} />
		{:else if type !== 'todo_update'}
			<div class="mt-3 border-t border-[var(--border)] pt-3">
				<EventContent {event} {searchQuery} />
			</div>
		{/if}
	{/if}
{/snippet}

<div
	data-event-index={index}
	data-event-type={type}
	data-event-id={event.id}
	class="timeline-row group relative -mx-1 -mt-1 flex gap-4 px-1 pt-1 transition-all duration-200"
>
	<!-- Rail line -->
	<div class="relative flex flex-col items-center">
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
				{variant === 'boundary' ? 'border-dashed' : ''}
				group-hover:scale-110 group-hover:shadow-lg
				{importance === 'high'
				? 'ring-2 ring-offset-2 ring-offset-[var(--bg-base)] ring-[var(--accent)]/20'
				: ''}
				cursor-pointer hover:opacity-80
			"
			onclick={(e) => {
				e.stopPropagation();
				onToggleHide?.();
			}}
			onkeydown={hasExpandableContent ? undefined : hideOnDelete}
			aria-keyshortcuts={hasExpandableContent ? undefined : 'Delete Backspace'}
			tabindex={hasExpandableContent ? -1 : 0}
			data-timeline-primary={hasExpandableContent ? undefined : ''}
			title="Hide event"
			aria-label="Hide event: {displayTitle}"
		>
			<IconComponent
				class="h-4 w-4 {isPlanEvent ? 'text-[var(--event-plan)]' : config.color}"
			/>
		</button>

		{#if !isLast}
			<div
				class="h-full w-px flex-1 bg-gradient-to-b from-[var(--border)]/50 to-[var(--border)]"
			></div>
		{/if}
	</div>

	{#if variant === 'boundary'}
		<!-- Compaction: a divider across the timeline, not a card -->
		<div class="mb-4 min-w-0 flex-1">
			<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
			<div
				class="flex min-h-8 flex-wrap items-center gap-x-3 gap-y-1.5 {hasExpandableContent
					? 'cursor-pointer'
					: ''}"
				onclick={openFromCard}
			>
				<div
					class="flex min-w-0 flex-1 flex-wrap items-center gap-x-2 gap-y-1 sm:flex-none"
				>
					<span class="text-sm font-medium text-[var(--text-secondary)]">
						{@render highlighted(displayTitle)}
					</span>
					{@render tagList()}
				</div>
				<!-- Below sm the rule gets its own full-width line, so it still reads as a divider -->
				<div
					class="order-last h-px basis-full border-t border-dashed border-[var(--event-system)]/50 sm:order-none sm:min-w-4 sm:flex-1 sm:basis-0"
					aria-hidden="true"
				></div>
				{@render trailing(true)}
			</div>
			{@render expanded()}
		</div>
	{:else if variant === 'quiet'}
		<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
		<div
			class="
				mb-4 flex-1 min-w-0 rounded-lg border border-dashed border-l-[3px] bg-[var(--bg-subtle)]/50 px-4 py-2.5 pl-5
				{isMediumEffortThinking
				? 'border-[var(--event-thinking)]/30 border-l-[var(--event-thinking)]/40'
				: 'border-[var(--border)] border-l-[var(--text-muted)]/40'}
				{hasExpandableContent ? 'cursor-pointer' : ''}
			"
			onclick={openFromCard}
		>
			<div
				class="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between sm:gap-3"
			>
				<div class="flex min-w-0 flex-wrap items-baseline gap-x-2 gap-y-0.5">
					<span
						class="text-sm font-medium {isMediumEffortThinking
							? 'text-[var(--text-muted)]'
							: 'text-[var(--text-secondary)]'}"
					>
						{@render highlighted(displayTitle)}
					</span>
					<span class="text-xs text-[var(--text-muted)]">{quietNote}</span>
				</div>
				{@render trailing(true)}
			</div>
			{@render expanded()}
		</div>
	{:else}
		<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
		<div
			class="
				mb-4 flex-1 min-w-0 rounded-lg border border-l-[3px] bg-[var(--bg-subtle)] p-4 pl-5 transition-all duration-200
				hover:shadow-md
				{hasExpandableContent ? 'cursor-pointer' : ''}
				{isPlanEvent ? 'border-[var(--event-plan)]/60' : config.borderColor}
				{isPlanEvent ? 'border-l-[var(--event-plan)]' : config.leftAccent}
			"
			onclick={openFromCard}
		>
			<!-- Header: below sm the time and chevron take their own row, so the title gets the full width -->
			<div class="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
				<div class="min-w-0 space-y-1 sm:flex-1">
					<!-- Title and badges -->
					<div class="flex flex-wrap items-center gap-2">
						<EventTitle
							{event}
							{currentAgentId}
							{agentHref}
							{mainSessionHref}
							{searchQuery}
						/>

						{#if toolName && type === 'tool_call'}
							<span
								class="max-w-full rounded bg-[var(--bg-muted)] px-1.5 py-0.5 text-[10px] font-mono text-[var(--text-muted)] [overflow-wrap:anywhere]"
							>
								{toolName}
							</span>
						{/if}

						<!-- Result status badge -->
						{#if type === 'tool_call'}
							{#if !hasToolResult}
								<span
									class="inline-flex items-center gap-1 rounded-full bg-[var(--warning-subtle)] px-2 py-0.5 text-[10px] font-medium text-[var(--warning)]"
								>
									pending
								</span>
							{:else if meta.result_status === 'error'}
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

						{@render tagList()}

						{#if type === 'system_context' && !isAgentIdle}
							<span class="text-xs text-[var(--text-muted)]">
								added for Claude, not typed by you
							</span>
						{/if}
					</div>

					<!-- Summary -->
					{#if displaySummary && type !== 'todo_update' && !(type === 'api_error' && displaySummary === displayTitle)}
						<p class="break-words font-mono text-xs text-[var(--text-muted)]">
							{@render highlighted(
								isExpanded ? displaySummary : truncate(displaySummary, 100)
							)}
						</p>
					{/if}

					<!-- Todo preview - show inline for todo_update events -->
					{#if type === 'todo_update'}
						<div class="mt-1">
							<TodoUpdateDetail
								todos={todosArray}
								action={meta.action as 'set' | 'merge' | undefined}
								agentSlug={meta.agent_slug as string | undefined}
								{isExpanded}
								{searchQuery}
							/>
						</div>
					{/if}

					<!-- Mini image thumbnails — visible on collapsed card; hidden when inline-expanded -->
					{#if !isExpanded && meta.image_attachments?.length}
						{@const images = meta.image_attachments}
						<div class="mt-2 flex items-center gap-1.5">
							{#each images.slice(0, 5) as attachment, i}
								<div
									class="relative h-8 w-8 shrink-0 overflow-hidden rounded border border-[var(--border)] opacity-80 transition-opacity hover:opacity-100"
									title="Image attachment {i + 1}"
								>
									<img
										src="data:{attachment.media_type};base64,{attachment.data}"
										alt="Attached image {i + 1}"
										class="h-full w-full object-cover"
									/>
								</div>
							{/each}
							{#if images.length > 5}
								<span class="text-[10px] text-[var(--text-muted)]">
									+{images.length - 5} more
								</span>
							{/if}
						</div>
					{/if}
				</div>

				{@render trailing(false)}
			</div>

			{@render expanded()}
		</div>
	{/if}
</div>

<style>
	/* Off-screen rows skip layout and paint; rings fit in the 4px padding, and fixed children stay in the row. */
	.timeline-row {
		content-visibility: auto;
		contain-intrinsic-block-size: auto 96px;
		overflow-clip-margin: 16px;
	}
</style>
