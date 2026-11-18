<script lang="ts">
	import { onMount } from 'svelte';
	import { Brain, ExternalLink, Zap, ChevronLeft, ChevronRight } from 'lucide-svelte';
	import { tick } from 'svelte';
	import { keyboardOverrides } from '$lib/stores/keyboardOverrides';
	import type { TimelineEvent } from '$lib/api-types';
	import { createTimelineLogic, matchesSearch } from '$lib/utils/timelineLogic.svelte';
	import { formatDate } from '$lib/utils';
	import TimelineFilterBar from './TimelineFilterBar.svelte';
	import TimelineEventCard from './TimelineEventCard.svelte';
	import TimelineGap from './TimelineGap.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import ToolCallDetail from './ToolCallDetail.svelte';
	import TodoUpdateDetail from './TodoUpdateDetail.svelte';
	import EventContent from './EventContent.svelte';
	import EventTitle from './EventTitle.svelte';
	import {
		buildAgentHref,
		getDisplayTitle,
		getEventTags,
		isEventExpandable
	} from './timeline-display';

	interface Props {
		events: TimelineEvent[];
		isLive?: boolean;
		isTailing?: boolean;
		onToggleTailing?: () => void;
		/** Current agent ID - when set, events from this agent won't show subagent badges */
		currentAgentId?: string | null;
		/** Project path for formatting file paths */
		projectPath?: string | null;
		class?: string;
		/** External search query (from Cmd+F) */
		searchQuery?: string;
		/** Callback when search match count changes */
		onSearchMatchCount?: (count: number) => void;
		/** Callback when current match index changes */
		onCurrentMatchChange?: (index: number) => void;
		/** Project encoded name for building subagent links */
		projectEncoded?: string;
		/** Session slug (short UUID) for building subagent links */
		sessionSlug?: string;
		/** Reports how many events the timeline counts, which excludes hidden system events */
		onEventCountChange?: (count: number) => void;
	}

	let {
		events,
		isLive = false,
		isTailing = false,
		onToggleTailing,
		currentAgentId = null,
		projectPath = null,
		class: className = '',
		searchQuery = '',
		onSearchMatchCount,
		onCurrentMatchChange,
		projectEncoded,
		sessionSlug,
		onEventCountChange
	}: Props = $props();

	// Auto-scroll state
	let isUserScrolling = $state(false);
	let userScrollTimeout: ReturnType<typeof setTimeout> | null = null;
	let scrollRafId: number | null = null;
	let prevEventsLength = $state(0);
	let prevIsTailing = $state(false);

	// The popup follows its event by id, so a live poll refreshes what it shows.
	let popupEventId = $state<string | null>(null);
	const popupEvent = $derived(
		popupEventId === null ? null : (events.find((e) => e.id === popupEventId) ?? null)
	);
	const isPopupOpen = $derived(popupEvent !== null);

	// The event the popup showed last, so focus can return to its card after paging.
	let lastPopupEventId: string | null = null;

	function openPopup(event: TimelineEvent) {
		popupEventId = event.id;
		lastPopupEventId = event.id;
	}

	function closePopup() {
		popupEventId = null;
	}

	// Focus goes back to the card of the event last shown, not the one first opened.
	async function returnFocusToCard(e: Event) {
		const id = lastPopupEventId;
		if (!id || !containerRef) return;
		e.preventDefault();
		await tick();
		// The rail can unmount while the tick is pending.
		if (!containerRef) return;
		const card = Array.from(containerRef.querySelectorAll<HTMLElement>('[data-event-id]')).find(
			(el) => el.dataset.eventId === id
		);
		const control = card?.querySelector<HTMLElement>(
			'button[aria-haspopup], button[aria-expanded]'
		);
		control?.focus({ preventScroll: true });
		card?.scrollIntoView({ block: 'nearest' });
	}

	// If the event is gone from the list, forget it so the popup cannot reopen by itself.
	$effect(() => {
		if (popupEventId !== null && !popupEvent) popupEventId = null;
	});

	function agentHref(agentId: string): string | null {
		return buildAgentHref(projectEncoded, sessionSlug, agentId);
	}

	// On an agent's page, its parent session is one click away.
	const mainSessionHref = $derived(
		currentAgentId && projectEncoded && sessionSlug
			? `/projects/${projectEncoded}/${sessionSlug}`
			: null
	);

	// Helper to safely clear and set scroll timeout
	function setScrollTimeout(callback: () => void, delay: number) {
		if (userScrollTimeout) clearTimeout(userScrollTimeout);
		userScrollTimeout = setTimeout(callback, delay);
	}

	// Helper to scroll to last event
	function scrollToLastEvent(behavior: ScrollBehavior = 'smooth') {
		const lastEvent = timelineContentRef?.querySelector('[data-event-index]:last-of-type');
		if (lastEvent) {
			isUserScrolling = true;
			lastEvent.scrollIntoView({ behavior, block: 'end' });
			setScrollTimeout(() => {
				isUserScrolling = false;
			}, 500);
		}
	}

	// Create timeline logic instance with tailing support and agent context
	const timeline = createTimelineLogic(() => events, {
		isTailingGetter: () => isTailing,
		tailCount: 3,
		currentAgentIdGetter: () => currentAgentId
	});

	// Pre-compute visible events (excluding gaps) for correct indexing
	const visibleEvents = $derived(timeline.viewItems.filter((i) => !('type' in i)));
	// Position of each visible event; a per-row findIndex would be quadratic on long sessions.
	const visibleIndexById = $derived(new Map(visibleEvents.map((e, i) => [e.id, i])));

	// Navigable events: visible events that have expandable/popup content
	const navigableEvents = $derived((visibleEvents as TimelineEvent[]).filter(isEventExpandable));

	const popupNavIndex = $derived(
		popupEventId ? navigableEvents.findIndex((e) => e.id === popupEventId) : -1
	);

	function navigatePrev() {
		if (popupNavIndex > 0) openPopup(navigableEvents[popupNavIndex - 1]);
	}

	function navigateNext() {
		if (popupNavIndex < navigableEvents.length - 1)
			openPopup(navigableEvents[popupNavIndex + 1]);
	}

	// Arrow key navigation when popup is open
	$effect(() => {
		if (!isPopupOpen) return;
		function onKeyDown(e: KeyboardEvent) {
			if (e.key === 'ArrowLeft') {
				e.preventDefault();
				navigatePrev();
			} else if (e.key === 'ArrowRight') {
				e.preventDefault();
				navigateNext();
			}
		}
		window.addEventListener('keydown', onKeyDown);
		return () => window.removeEventListener('keydown', onKeyDown);
	});

	// Shares matchesSearch/its haystack cache with the filter bar and cards, so the count never contradicts them.
	let searchMatchIds = $derived.by<string[]>(() => {
		if (!timeline.searchQuery.trim()) return [];
		return timeline.baseEvents
			.filter((e) => matchesSearch(e, timeline.searchQuery))
			.map((e) => e.id);
	});

	let currentMatchIdx = $state(0);

	// Notify parent of match count changes
	$effect(() => {
		onSearchMatchCount?.(searchMatchIds.length);
		if (searchMatchIds.length === 0) {
			currentMatchIdx = 0;
		}
	});

	$effect(() => {
		onCurrentMatchChange?.(currentMatchIdx);
	});

	$effect(() => {
		onEventCountChange?.(timeline.baseEvents.length);
	});

	// Syncs the external (Cmd+F) search query, including clears, so Escape doesn't leave stale highlights.
	$effect(() => {
		timeline.setSearchQuery(searchQuery);
	});

	// Container ref for scroll management
	let containerRef = $state<HTMLDivElement | null>(null);
	let timelineContentRef = $state<HTMLDivElement | null>(null);

	// Setup Cmd+K and initial scroll
	onMount(() => {
		// Register Cmd+K to focus the timeline search input
		const unregisterCtrlK = keyboardOverrides.registerCtrlK(() => {
			const searchEl =
				containerRef?.querySelector<HTMLInputElement>('[data-timeline-search]');
			if (searchEl) {
				searchEl.focus({ preventScroll: true });
				searchEl.select();
			}
		});

		// Initialize previous state tracking
		prevEventsLength = events.length;
		prevIsTailing = isTailing;

		// Initial scroll to bottom if tailing is enabled on mount
		let initTimeout: ReturnType<typeof setTimeout> | null = null;
		if (isTailing && timelineContentRef) {
			initTimeout = setTimeout(() => {
				scrollToLastEvent('auto'); // Use 'auto' for initial scroll (no animation)
			}, 200); // Slightly longer delay for initial render
		}

		return () => {
			unregisterCtrlK();
			if (initTimeout) clearTimeout(initTimeout);
			if (userScrollTimeout) clearTimeout(userScrollTimeout);
			if (scrollRafId) cancelAnimationFrame(scrollRafId);
		};
	});

	// Auto-scroll to show last event when:
	// 1. New events arrive while tailing is enabled
	// 2. Tailing is first toggled on
	$effect(() => {
		const newEventsArrived =
			isTailing && events.length > prevEventsLength && timelineContentRef;
		const tailingJustEnabled = isTailing && !prevIsTailing && timelineContentRef;

		if (newEventsArrived) {
			// Cancel any pending RAF to avoid multiple scrolls
			if (scrollRafId) cancelAnimationFrame(scrollRafId);

			// Use requestAnimationFrame to ensure DOM has updated
			scrollRafId = requestAnimationFrame(() => {
				scrollToLastEvent('smooth');
				scrollRafId = null;
			});
		} else if (tailingJustEnabled) {
			// Use setTimeout to ensure DOM has fully updated after tailing state change
			setScrollTimeout(() => {
				scrollToLastEvent('smooth');
			}, 100);
		}

		// Update tracking state
		prevEventsLength = events.length;
		prevIsTailing = isTailing;

		// Cleanup function for effect
		return () => {
			if (scrollRafId) {
				cancelAnimationFrame(scrollRafId);
				scrollRafId = null;
			}
		};
	});

	// Auto-expand the last event when tailing is enabled
	$effect(() => {
		const shown = timeline.baseEvents;
		if (isTailing && shown.length > 0) {
			const lastEventId = shown[shown.length - 1]?.id;
			if (lastEventId && timeline.expandedId !== lastEventId) {
				timeline.setExpandedId(lastEventId);
			}
		}
	});
</script>

{#if events.length === 0}
	<div class="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)] p-12 text-center">
		<Brain class="mx-auto h-12 w-12 text-[var(--text-muted)]/40" />
		<p class="mt-4 text-[var(--text-muted)]">No events in this session</p>
	</div>
{:else}
	<div class="relative {className}" bind:this={containerRef}>
		<!-- Filter bar (sticky when scrolling) -->
		<TimelineFilterBar
			counts={timeline.counts}
			activeFilters={timeline.effectiveFilters}
			totalEvents={timeline.baseEvents.length}
			matchingEvents={timeline.matchingCount}
			onToggle={timeline.toggleFilter}
			onClear={timeline.clearFilters}
			searchQuery={timeline.searchQuery}
			onSearchChange={timeline.setSearchQuery}
			class="mb-6 z-20 lg:sticky lg:top-14"
		/>

		<!-- Timeline -->
		<div class="pl-2" bind:this={timelineContentRef}>
			{#if timeline.viewItems.length === 0 && timeline.systemCount > 0 && !timeline.showSystem}
				<p
					class="rounded-lg border border-dashed border-[var(--border)] p-6 text-center text-sm text-[var(--text-muted)]"
				>
					This timeline only has system events. Select System to see them.
				</p>
			{/if}
			{#each timeline.viewItems as item, loopIndex (item.id)}
				{#if 'type' in item && item.type === 'gap'}
					{@const gapItem = item}
					<TimelineGap
						gap={gapItem}
						onExpand={(ids) => timeline.expandGap(gapItem, ids)}
					/>
				{:else if !('type' in item)}
					{@const eventItem = item}
					<!-- Find this event's actual position within visible events (not viewItems) -->
					{@const visibleEventIndex = visibleIndexById.get(eventItem.id) ?? -1}
					{@const isFirstVisible = visibleEventIndex === 0}
					{@const isLastVisible = visibleEventIndex === visibleEvents.length - 1}
					{@const usePopup = !(isTailing && isLastVisible)}
					<TimelineEventCard
						event={eventItem}
						index={visibleEventIndex}
						isFirst={isFirstVisible}
						isLast={isLastVisible}
						sessionStartTime={events[0]?.timestamp}
						isHighlighted={true}
						hasActiveFilter={timeline.hasActiveFilter}
						isExpanded={timeline.expandedId === item.id}
						onToggleExpand={() => timeline.toggleExpand(visibleEventIndex, item.id)}
						{usePopup}
						onOpenPopup={() => openPopup(eventItem)}
						{currentAgentId}
						{projectPath}
						onToggleHide={() => timeline.toggleHide(eventItem.id)}
						searchQuery={timeline.searchQuery}
						{projectEncoded}
						{sessionSlug}
					/>
				{/if}
			{/each}
		</div>
	</div>
{/if}

<!-- Event Detail Popup -->
{#if popupEvent}
	<Modal
		open={isPopupOpen}
		onOpenChange={(open) => {
			if (!open) closePopup();
		}}
		title={getDisplayTitle(popupEvent)}
		description={formatDate(popupEvent.timestamp)}
		maxWidth="xl"
		anchor="top"
		onCloseAutoFocus={returnFocusToCard}
	>
		{#snippet headerActions()}
			<button
				onclick={navigatePrev}
				disabled={popupNavIndex <= 0}
				class="rounded-md p-1 text-[var(--text-muted)] transition-colors hover:text-[var(--text-primary)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] disabled:opacity-30 disabled:cursor-not-allowed"
				aria-label="Previous event"
			>
				<ChevronLeft size={20} />
			</button>
			<button
				onclick={navigateNext}
				disabled={popupNavIndex >= navigableEvents.length - 1}
				class="rounded-md p-1 text-[var(--text-muted)] transition-colors hover:text-[var(--text-primary)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] disabled:opacity-30 disabled:cursor-not-allowed"
				aria-label="Next event"
			>
				<ChevronRight size={20} />
			</button>
		{/snippet}
		{#snippet titleSnippet()}
			{#if popupEvent?.event_type === 'skill_invocation'}
				{@const skillPath = popupEvent.title?.replace(/^Skill:\s*\/?/, '') ?? ''}
				{#if skillPath}
					<a
						href="/skills/{encodeURIComponent(skillPath)}"
						class="flex items-center gap-2 text-[var(--accent)] hover:text-[var(--accent)]/80 transition-colors no-underline group"
					>
						<Zap size={18} class="shrink-0" />
						<span>{popupEvent.title}</span>
						<ExternalLink
							size={14}
							class="opacity-50 group-hover:opacity-100 transition-opacity"
						/>
					</a>
				{:else}
					{popupEvent.title}
				{/if}
			{:else if popupEvent}
				<!-- The same title, sender and tags as the card -->
				<span class="flex flex-wrap items-center gap-2">
					<EventTitle
						event={popupEvent}
						{currentAgentId}
						{agentHref}
						{mainSessionHref}
						searchQuery={timeline.searchQuery}
						titleClass=""
					/>
					{#each getEventTags(popupEvent) as tag, i (i)}
						<span
							class="max-w-full rounded bg-[var(--bg-muted)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--text-secondary)] [overflow-wrap:anywhere]"
						>
							{tag}
						</span>
					{/each}
				</span>
			{/if}
		{/snippet}

		<div class="max-h-[70vh] overflow-auto break-words">
			{#if popupEvent.event_type === 'tool_call'}
				<ToolCallDetail
					event={popupEvent}
					{projectPath}
					searchQuery={timeline.searchQuery}
				/>
			{:else if popupEvent.event_type === 'todo_update'}
				{@const todos = Array.isArray(popupEvent.metadata?.todos)
					? popupEvent.metadata.todos
					: []}
				<TodoUpdateDetail
					{todos}
					action={popupEvent.metadata?.action as 'set' | 'merge' | undefined}
					agentSlug={popupEvent.metadata?.agent_slug as string | undefined}
					isExpanded={true}
					searchQuery={timeline.searchQuery}
				/>
			{:else}
				<EventContent event={popupEvent} searchQuery={timeline.searchQuery} />
			{/if}
		</div>
	</Modal>
{/if}
