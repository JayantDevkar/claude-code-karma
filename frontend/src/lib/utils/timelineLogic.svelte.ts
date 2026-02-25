import type { TimelineEvent, FilterCategory, FilterCounts } from '$lib/api-types';

/**
 * Timeline Logic Utility
 * Extracted from TimelineRail component for better separation of concerns
 * Uses Svelte 5 runes for reactive state management
 */

/**
 * Check if an event matches a specific filter category
 * @param event - The timeline event to check
 * @param filter - The filter category to match against
 * @param currentAgentId - When viewing an agent's timeline, the agent's ID (affects subagent filter)
 */
function matchesSingleFilter(
	event: TimelineEvent,
	filter: FilterCategory,
	currentAgentId?: string | null
): boolean {
	switch (filter) {
		case 'prompt':
			return event.event_type === 'prompt';
		case 'tool_call':
			return event.event_type === 'tool_call';
		case 'subagent':
			// In agent view (currentAgentId is set), only match events that spawn OTHER subagents,
			// not all events with actor_type === 'subagent' (which would be ALL agent events)
			if (currentAgentId) {
				return (
					event.event_type === 'subagent_spawn' ||
					Boolean(event.metadata?.spawned_agent_id)
				);
			}
			// In session view, match events from subagents OR events that spawn subagents
			return (
				event.actor_type === 'subagent' ||
				event.event_type === 'subagent_spawn' ||
				Boolean(event.metadata?.spawned_agent_id)
			);
		case 'todo_update':
			return event.event_type === 'todo_update';
		case 'error':
			return (
				event.metadata?.result_status === 'error' ||
				(event.event_type === 'tool_call' &&
					event.metadata?.has_result === true &&
					!event.metadata.result_status) // Fallback for error detection if needed
			);
		case 'thinking':
			return event.event_type === 'thinking';
		case 'response':
			return event.event_type === 'response';
		case 'skill':
			return event.event_type === 'skill_invocation';
		case 'command':
			return (
				event.event_type === 'command_invocation' || event.event_type === 'builtin_command'
			);
		default:
			return false;
	}
}

/**
 * Check if event matches search query
 */
function matchesSearch(event: TimelineEvent, query: string): boolean {
	if (!query.trim()) return true;
	const q = query.toLowerCase();

	// Check basic fields
	if (event.title.toLowerCase().includes(q)) return true;
	if (event.summary?.toLowerCase().includes(q)) return true;
	if (event.actor.toLowerCase().includes(q)) return true;

	// Check metadata content
	const metadata = event.metadata || {};
	if (metadata.tool_name?.toLowerCase().includes(q)) return true;
	if (metadata.full_content?.toLowerCase().includes(q)) return true;
	if (metadata.full_thinking?.toLowerCase().includes(q)) return true;
	if (metadata.full_text?.toLowerCase().includes(q)) return true;
	if (metadata.result_content?.toLowerCase().includes(q)) return true;
	if (metadata.error_message && String(metadata.error_message).toLowerCase().includes(q))
		return true;

	return false;
}

/**
 * Check if event matches any active filter (OR logic) AND search query
 */
function matchesFilters(
	event: TimelineEvent,
	filters: Set<FilterCategory>,
	searchQuery: string,
	currentAgentId?: string | null
): boolean {
	// First check search query
	if (!matchesSearch(event, searchQuery)) return false;

	// Then check category filters
	if (filters.size === 0) return true;
	for (const filter of filters) {
		if (matchesSingleFilter(event, filter, currentAgentId)) return true;
	}
	return false;
}

/**
 * Calculate filter counts from events (optimized single-pass)
 */
function calculateFilterCounts(
	events: TimelineEvent[],
	currentAgentId?: string | null
): FilterCounts {
	const counts = {
		prompt: 0,
		tool_call: 0,
		subagent: 0,
		todo_update: 0,
		error: 0,
		thinking: 0,
		response: 0,
		skill: 0,
		command: 0
	};

	for (const event of events) {
		const type = event.event_type;

		// Simple direct matches
		if (type === 'prompt') counts.prompt++;
		if (type === 'tool_call') counts.tool_call++;
		if (type === 'todo_update') counts.todo_update++;
		if (type === 'thinking') counts.thinking++;
		if (type === 'response') counts.response++;

		// Subagent logic (complex)
		if (currentAgentId) {
			if (type === 'subagent_spawn' || event.metadata?.spawned_agent_id) {
				counts.subagent++;
			}
		} else {
			if (
				event.actor_type === 'subagent' ||
				type === 'subagent_spawn' ||
				event.metadata?.spawned_agent_id
			) {
				counts.subagent++;
			}
		}

		// Skill/command invocation
		if (type === 'skill_invocation') counts.skill++;
		if (type === 'command_invocation' || type === 'builtin_command') counts.command++;

		// Error detection
		if (
			event.metadata?.result_status === 'error' ||
			(type === 'tool_call' &&
				event.metadata?.has_result === true &&
				!event.metadata.result_status)
		) {
			counts.error++;
		}
	}

	return counts;
}

/**
 * Create timeline logic state and actions
 * Returns reactive state and helper functions for timeline management
 * @param eventsGetter - Function that returns the current events array (maintains reactivity)
 */
/**
 * Gap in the timeline representing hidden events
 */
export interface TimelineGap {
	type: 'gap';
	id: string;
	events: TimelineEvent[];
}

export type TimelineViewItem = TimelineEvent | TimelineGap;

/**
 * Options for timeline logic creation
 */
export interface TimelineLogicOptions {
	/** Function that returns whether tailing mode is active */
	isTailingGetter?: () => boolean;
	/** Number of events to show when tailing (default: 3) */
	tailCount?: number;
	/** Function that returns the current agent ID (reactive, affects filter behavior) */
	currentAgentIdGetter?: () => string | null;
}

/**
 * Create timeline logic state and actions
 * Returns reactive state and helper functions for timeline management
 * @param eventsGetter - Function that returns the current events array (maintains reactivity)
 * @param options - Optional configuration for tailing behavior
 */
export function createTimelineLogic(
	eventsGetter: () => TimelineEvent[],
	options: TimelineLogicOptions = {}
) {
	const {
		isTailingGetter = () => false,
		tailCount = 3,
		currentAgentIdGetter = () => null
	} = options;

	// Use getter for reactive agent ID
	const getAgentId = currentAgentIdGetter;

	// State
	let activeFilters = $state<Set<FilterCategory>>(new Set());
	let searchQuery = $state('');
	let expandedId = $state<string | null>(null);
	let focusedIndex = $state(-1);
	let manuallyRevealedIds = $state<Set<string>>(new Set());
	let manuallyHiddenIds = $state<Set<string>>(new Set());

	// Derived state - filter counts
	const counts = $derived.by<FilterCounts>(() => {
		return calculateFilterCounts(eventsGetter(), getAgentId());
	});

	// Derived state - effective filters (if all relevant selected, treat as none)
	const effectiveFilters = $derived.by<Set<FilterCategory>>(() => {
		// Calculate how many non-zero categories exist
		const categories: FilterCategory[] = [
			'prompt',
			'tool_call',
			'subagent',
			'todo_update',
			'error',
			'thinking',
			'response',
			'skill',
			'command'
		];
		const availableCategories = categories.filter((c) => counts[c] > 0);

		// If all available categories are selected, it's equivalent to no filter
		// But only if we have at least 2 categories to toggle between
		if (
			availableCategories.length > 1 &&
			availableCategories.every((c) => activeFilters.has(c)) &&
			activeFilters.size === availableCategories.length
		) {
			return new Set<FilterCategory>();
		}
		return activeFilters;
	});

	const hasActiveFilter = $derived(effectiveFilters.size > 0 || searchQuery.length > 0);

	// Derived state - is tailing active (reactive via getter)
	const isTailing = $derived(isTailingGetter());

	// Derived state - View Items (Events + Gaps)
	// Handles both filter-based visibility AND tailing mode
	const viewItems = $derived.by<TimelineViewItem[]>(() => {
		const events = eventsGetter();
		const totalEvents = events.length;

		// If no filter AND not tailing AND no manual hides, show all events
		if (!hasActiveFilter && !isTailing && manuallyHiddenIds.size === 0) {
			return events;
		}

		const items: TimelineViewItem[] = [];
		let currentGapEvents: TimelineEvent[] = [];

		for (let i = 0; i < events.length; i++) {
			const event = events[i];

			// Check if event is in the last N (for tailing)
			const isInLastN = isTailing && i >= totalEvents - tailCount;

			// Determine visibility based on mode:
			// - When tailing is ON:
			//   - If no filter: ONLY show last N events
			//   - If filter active: show filter matches + last N
			// - When tailing is OFF:
			//   - Show based on filter/search only
			// - manuallyRevealedIds overrides to show
			// - manuallyHiddenIds overrides to hide (unless revealed)
			let isVisible: boolean;

			// Check manual reveal/hide first
			if (manuallyRevealedIds.has(event.id)) {
				// Always show if manually revealed
				isVisible = true;
			} else if (manuallyHiddenIds.has(event.id)) {
				// Always hide if manually hidden (and not revealed)
				isVisible = false;
			} else if (isTailing && !hasActiveFilter) {
				// Tailing ON, no filter: ONLY show last N
				isVisible = isInLastN;
			} else if (isTailing && hasActiveFilter) {
				// Tailing ON, filter active: show filter matches + last N
				isVisible =
					isInLastN ||
					matchesFilters(event, effectiveFilters, searchQuery, getAgentId()) ||
					manuallyRevealedIds.has(event.id);
			} else {
				// Tailing OFF: show based on filter/search
				isVisible =
					matchesFilters(event, effectiveFilters, searchQuery, getAgentId()) ||
					manuallyRevealedIds.has(event.id);
			}

			if (isVisible) {
				// If we have accumulated hidden events, push a gap
				if (currentGapEvents.length > 0) {
					items.push({
						type: 'gap',
						id: `gap-${currentGapEvents[0].id}-${currentGapEvents[currentGapEvents.length - 1].id}`,
						events: [...currentGapEvents]
					});
					currentGapEvents = [];
				}
				items.push(event);
			} else {
				currentGapEvents.push(event);
			}
		}

		// Trailing gap (should be rare when tailing since last N are always visible)
		if (currentGapEvents.length > 0) {
			items.push({
				type: 'gap',
				id: `gap-end-${currentGapEvents[0].id}`,
				events: [...currentGapEvents]
			});
		}

		return items;
	});

	// Derived state - matching count (only truly matching events, excluding manually revealed for stat correctness? Or inclusive? User typically wants to know matches count. Let's keep strict matches for the count.)
	const matchingCount = $derived.by(() => {
		return eventsGetter().filter((e) =>
			matchesFilters(e, effectiveFilters, searchQuery, getAgentId())
		).length;
	});

	// Derived state - event IDs for keyboard navigation (navigates only visible events)
	const eventIds = $derived(
		viewItems
			.filter((item): item is TimelineEvent => !('type' in item && item.type === 'gap'))
			.map((e) => e.id)
	);

	// Actions
	function toggleFilter(filter: FilterCategory) {
		const newFilters = new Set(activeFilters);
		if (newFilters.has(filter)) {
			newFilters.delete(filter);
		} else {
			newFilters.add(filter);
		}
		activeFilters = newFilters;
		// Reset manual reveals when filters change? Maybe safer to avoid confusion.
		// Or keep them? User might want to keep context. Let's keep them for now.
		// Actually, if we clear filters, we should clear reveals.
	}

	function clearFilters() {
		activeFilters = new Set();
		searchQuery = '';
		manuallyRevealedIds = new Set();
		manuallyHiddenIds = new Set();
	}

	function setSearchQuery(query: string) {
		searchQuery = query;
		manuallyRevealedIds = new Set(); // Reset reveals on search change
	}

	function toggleExpand(index: number, eventId: string) {
		focusedIndex = index;
		expandedId = expandedId === eventId ? null : eventId;
	}

	function setExpandedId(eventId: string | null) {
		expandedId = eventId;
	}

	function expandGap(gap: TimelineGap, specificIds?: string[]) {
		const newReveals = new Set(manuallyRevealedIds);
		const idsToAdd = specificIds || gap.events.map((e) => e.id);
		idsToAdd.forEach((id) => newReveals.add(id));
		manuallyRevealedIds = newReveals;
		// Remove from hidden when revealing
		const newHidden = new Set(manuallyHiddenIds);
		idsToAdd.forEach((id) => newHidden.delete(id));
		manuallyHiddenIds = newHidden;
	}

	function toggleHide(eventId: string) {
		const newHidden = new Set(manuallyHiddenIds);
		if (newHidden.has(eventId)) {
			newHidden.delete(eventId);
		} else {
			newHidden.add(eventId);
			// Remove from revealed if it was revealed
			const newRevealed = new Set(manuallyRevealedIds);
			newRevealed.delete(eventId);
			manuallyRevealedIds = newRevealed;
		}
		manuallyHiddenIds = newHidden;
	}

	/**
	 * Handle keyboard navigation
	 * Returns cleanup function to remove event listener
	 */
	function setupKeyboardNavigation(enableKeyboard: boolean) {
		if (!enableKeyboard) return () => {};

		let gKeyPressed = false;
		let gKeyTimeout: ReturnType<typeof setTimeout> | null = null;

		function handleKeyDown(e: KeyboardEvent) {
			const target = e.target as HTMLElement;
			// Use visible event IDs for navigation
			const ids = eventIds;

			// Don't handle if user is typing in an input
			if (
				target.tagName === 'INPUT' ||
				target.tagName === 'TEXTAREA' ||
				target.isContentEditable
			) {
				return;
			}

			// focusedIndex matches index in `eventIds` array (visible events only, excluding gaps)

			switch (e.key) {
				case 'j':
				case 'ArrowDown':
					e.preventDefault();
					focusedIndex = Math.min(focusedIndex + 1, ids.length - 1);
					if (focusedIndex === -1) focusedIndex = 0;
					expandedId = ids[focusedIndex] ?? null;
					break;

				case 'k':
				case 'ArrowUp':
					e.preventDefault();
					if (focusedIndex === -1) {
						focusedIndex = ids.length - 1;
					} else {
						focusedIndex = Math.max(focusedIndex - 1, 0);
					}
					expandedId = ids[focusedIndex] ?? null;
					break;

				case 'Enter':
				case ' ':
					e.preventDefault();
					if (focusedIndex >= 0 && focusedIndex < ids.length) {
						const currentId = ids[focusedIndex];
						expandedId = expandedId === currentId ? null : currentId;
					}
					break;

				case 'Escape':
					e.preventDefault();
					expandedId = null;
					break;

				case 'g':
					if (gKeyPressed) {
						e.preventDefault();
						focusedIndex = 0;
						expandedId = ids[0] ?? null;
						gKeyPressed = false;
						if (gKeyTimeout) clearTimeout(gKeyTimeout);
					} else {
						gKeyPressed = true;
						gKeyTimeout = setTimeout(() => {
							gKeyPressed = false;
						}, 500);
					}
					break;

				case 'G':
					e.preventDefault();
					focusedIndex = ids.length - 1;
					expandedId = ids[ids.length - 1] ?? null;
					break;

				case 'Home':
					e.preventDefault();
					focusedIndex = 0;
					expandedId = ids[0] ?? null;
					break;

				case 'End':
					e.preventDefault();
					focusedIndex = ids.length - 1;
					expandedId = ids[ids.length - 1] ?? null;
					break;
			}
		}

		window.addEventListener('keydown', handleKeyDown);

		// Return cleanup function
		return () => {
			window.removeEventListener('keydown', handleKeyDown);
			if (gKeyTimeout) clearTimeout(gKeyTimeout);
		};
	}

	return {
		// State (exposed as getters/setters via runes)
		get activeFilters() {
			return activeFilters;
		},
		get searchQuery() {
			return searchQuery;
		},
		set searchQuery(v: string) {
			searchQuery = v;
		},
		get expandedId() {
			return expandedId;
		},
		get focusedIndex() {
			return focusedIndex;
		},
		// Derived state
		get counts() {
			return counts;
		},
		get effectiveFilters() {
			return effectiveFilters;
		},
		get hasActiveFilter() {
			return hasActiveFilter;
		},
		get matchingCount() {
			return matchingCount;
		},
		get eventIds() {
			return eventIds;
		},
		get viewItems() {
			return viewItems;
		},
		get isTailing() {
			return isTailing;
		},
		get tailCount() {
			return tailCount;
		},
		// Actions
		toggleFilter,
		clearFilters,
		setSearchQuery,
		toggleExpand,
		setExpandedId,
		setupKeyboardNavigation,
		expandGap,
		toggleHide,
		// Utility functions
		matchesFilters: (event: TimelineEvent) =>
			matchesFilters(event, effectiveFilters, searchQuery, getAgentId())
	};
}
