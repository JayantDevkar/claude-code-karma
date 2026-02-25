<script lang="ts">
	import { onMount } from 'svelte';
	import { Brain, Keyboard, Copy, Check } from 'lucide-svelte';
	import { marked } from 'marked';
	import DOMPurify from 'isomorphic-dompurify';
	import type { TimelineEvent } from '$lib/api-types';
	import { createTimelineLogic } from '$lib/utils/timelineLogic.svelte';
	import { formatDate } from '$lib/utils';
	import TimelineFilterBar from './TimelineFilterBar.svelte';
	import TimelineEventCard from './TimelineEventCard.svelte';
	import TimelineGap from './TimelineGap.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import ToolCallDetail from './ToolCallDetail.svelte';
	import TodoUpdateDetail from './TodoUpdateDetail.svelte';

	interface Props {
		events: TimelineEvent[];
		enableKeyboard?: boolean;
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
	}

	let {
		events,
		enableKeyboard = true,
		isLive = false,
		isTailing = false,
		onToggleTailing,
		currentAgentId = null,
		projectPath = null,
		class: className = '',
		searchQuery = '',
		onSearchMatchCount,
		onCurrentMatchChange
	}: Props = $props();

	// Auto-scroll state
	let isUserScrolling = $state(false);
	let userScrollTimeout: ReturnType<typeof setTimeout> | null = null;
	let scrollRafId: number | null = null;
	let prevEventsLength = $state(0);
	let prevIsTailing = $state(false);

	// Popup state for event detail modal
	let popupEvent = $state<TimelineEvent | null>(null);
	const isPopupOpen = $derived(popupEvent !== null);
	let isCopied = $state(false);

	// Rendered markdown content for popup modal
	let renderedPopupContent = $state('');

	// Render markdown when popup opens or content changes
	$effect(() => {
		if (popupEvent) {
			const rawContent =
				popupEvent.metadata?.full_content ||
				popupEvent.metadata?.full_thinking ||
				popupEvent.metadata?.full_text ||
				popupEvent.metadata?.result_content ||
				popupEvent.summary ||
				'';

			const parsed = marked.parse(rawContent);
			if (parsed instanceof Promise) {
				parsed.then((html) => {
					renderedPopupContent = DOMPurify.sanitize(html);
				});
			} else {
				renderedPopupContent = DOMPurify.sanitize(parsed);
			}
		}
	});

	function openPopup(event: TimelineEvent) {
		popupEvent = event;
		isCopied = false; // Reset copied state when opening popup
	}

	function closePopup() {
		popupEvent = null;
		isCopied = false; // Reset copied state when closing popup
	}

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

	// Search match tracking
	let searchMatchIds = $derived.by<string[]>(() => {
		if (!searchQuery) return [];
		const q = searchQuery.toLowerCase();
		return events
			.filter((e) => {
				const text = [
					e.summary,
					e.title,
					e.metadata?.full_content,
					e.metadata?.full_text,
					e.metadata?.full_thinking
				]
					.filter(Boolean)
					.join(' ')
					.toLowerCase();
				return text.includes(q);
			})
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

	// When search query changes, also update TimelineFilterBar's search if searchQuery is set externally
	$effect(() => {
		if (searchQuery) {
			timeline.setSearchQuery(searchQuery);
		}
	});

	// Container ref for scroll management
	let containerRef = $state<HTMLDivElement | null>(null);
	let timelineContentRef = $state<HTMLDivElement | null>(null);

	// Setup keyboard navigation and initial scroll
	onMount(() => {
		const keyboardCleanup = timeline.setupKeyboardNavigation(enableKeyboard);

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
			keyboardCleanup();
			if (initTimeout) clearTimeout(initTimeout);
			if (userScrollTimeout) clearTimeout(userScrollTimeout);
			if (scrollRafId) cancelAnimationFrame(scrollRafId);
		};
	});

	// Scroll focused event into view (keyboard navigation)
	$effect(() => {
		if (timeline.focusedIndex >= 0 && containerRef) {
			const eventElement = containerRef.querySelector(
				`[data-event-index="${timeline.focusedIndex}"]`
			);
			if (eventElement) {
				isUserScrolling = true;
				eventElement.scrollIntoView({
					behavior: 'smooth',
					block: 'nearest'
				});
				setScrollTimeout(() => {
					isUserScrolling = false;
				}, 500);
			}
		}
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
		if (isTailing && events.length > 0) {
			// Get the last event ID
			const lastEventId = events[events.length - 1]?.id;
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
			totalEvents={events.length}
			matchingEvents={timeline.matchingCount}
			onToggle={timeline.toggleFilter}
			onClear={timeline.clearFilters}
			searchQuery={timeline.searchQuery}
			onSearchChange={timeline.setSearchQuery}
			class="mb-6 sticky top-14 z-20"
		/>

		<!-- Timeline -->
		<div class="pl-2" bind:this={timelineContentRef}>
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
					{@const visibleEventIndex = visibleEvents.findIndex(
						(e) => e.id === eventItem.id
					)}
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
						isFocused={timeline.focusedIndex === visibleEventIndex}
						isExpanded={timeline.expandedId === item.id}
						onToggleExpand={() => timeline.toggleExpand(visibleEventIndex, item.id)}
						{usePopup}
						onOpenPopup={() => openPopup(eventItem)}
						{currentAgentId}
						{projectPath}
						onToggleHide={() => timeline.toggleHide(eventItem.id)}
						{searchQuery}
					/>
				{/if}
			{/each}
		</div>

		<!-- Keyboard shortcuts hint (hidden when tailing to avoid obstructing view) -->
		{#if enableKeyboard && !isTailing}
			<div
				class="
					fixed bottom-4 right-4
					flex items-center gap-2
					px-3 py-2
					bg-[var(--bg-muted)]
					border border-[var(--border)]
					rounded-lg
					text-xs text-[var(--text-muted)]
					opacity-60 hover:opacity-100
					transition-opacity
				"
			>
				<Keyboard size={14} />
				<span>j/k to navigate, Enter to expand, gg/G first/last</span>
			</div>
		{/if}
	</div>
{/if}

<!-- Event Detail Popup -->
{#if popupEvent}
	<Modal
		open={isPopupOpen}
		onOpenChange={(open) => {
			if (!open) closePopup();
		}}
		title={popupEvent.title}
		description={formatDate(popupEvent.timestamp)}
		maxWidth="xl"
	>
		<div class="max-h-[70vh] overflow-auto">
			{#if popupEvent.event_type === 'tool_call'}
				<ToolCallDetail event={popupEvent} {projectPath} />
			{:else if popupEvent.event_type === 'todo_update'}
				{@const todos = Array.isArray(popupEvent.metadata?.todos)
					? popupEvent.metadata.todos
					: []}
				<TodoUpdateDetail
					{todos}
					action={popupEvent.metadata?.action as 'set' | 'merge' | undefined}
					agentSlug={popupEvent.metadata?.agent_slug as string | undefined}
					isExpanded={true}
				/>
			{:else}
				<!-- Generic content display for prompts, thinking, responses -->
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
								popupEvent?.metadata?.full_content ||
								popupEvent?.metadata?.full_thinking ||
								popupEvent?.metadata?.full_text ||
								popupEvent?.metadata?.result_content ||
								popupEvent?.summary ||
								'';
							navigator.clipboard.writeText(content);
							isCopied = true;
							setTimeout(() => (isCopied = false), 2000);
						}}
						title={isCopied ? 'Copied!' : 'Copy to clipboard'}
					>
						{#if isCopied}
							<Check size={14} class="text-[var(--success)]" />
						{:else}
							<Copy size={14} />
						{/if}
					</button>
					<div class="markdown-preview text-sm">
						{@html renderedPopupContent}
					</div>
				</div>
			{/if}
		</div>
	</Modal>
{/if}
```
