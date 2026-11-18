import type { TimelineEvent, FilterCategory, FilterCounts } from '$lib/api-types';
import { getDisplayTitle, isFailedTask } from '$lib/components/timeline/timeline-display';

/**
 * Timeline Logic Utility
 * Extracted from TimelineRail component for better separation of concerns
 * Uses Svelte 5 runes for reactive state management
 */

const TASK_TOOLS = ['TaskCreate', 'TaskUpdate', 'TaskGet', 'TaskList'];

/** Filter chips in display order, grouped by who acts. */
export const FILTER_CATEGORIES: FilterCategory[] = [
	'prompt',
	'command',
	'thinking',
	'response',
	'big_response',
	'ask_user',
	'tool_call',
	'mcp_tool',
	'skill',
	'task',
	'error',
	'subagent',
	'message',
	'background',
	'api_error',
	'notice',
	'system'
];

/** Text injected for the model; left out of the timeline unless the System filter is selected. */
export function isSystemContext(event: TimelineEvent): boolean {
	return event.event_type === 'system_context';
}

/** Events the timeline works with: everything, minus system context unless System is selected. */
export function selectBaseEvents(events: TimelineEvent[], showSystem: boolean): TimelineEvent[] {
	if (showSystem) return events;
	return events.some(isSystemContext) ? events.filter((e) => !isSystemContext(e)) : events;
}

function toolName(event: TimelineEvent): string | null {
	const name = event.metadata?.tool_name;
	return typeof name === 'string' ? name : null;
}

/** Check if an event matches one filter chip; currentAgentId is set in an agent's own timeline. */
export function matchesSingleFilter(
	event: TimelineEvent,
	filter: FilterCategory,
	currentAgentId?: string | null
): boolean {
	const type = event.event_type;
	// System events belong to the System chip only, whoever their actor is.
	if (isSystemContext(event)) return filter === 'system';
	switch (filter) {
		case 'prompt':
			return type === 'prompt';
		case 'command':
			return (
				type === 'command_invocation' ||
				type === 'builtin_command' ||
				type === 'shell_command'
			);
		case 'thinking':
			return type === 'thinking';
		case 'response':
			return type === 'response';
		case 'big_response':
			return type === 'response' && event.metadata?.is_big_response === true;
		case 'ask_user':
			return type === 'tool_call' && toolName(event) === 'AskUserQuestion';
		case 'tool_call':
			return type === 'tool_call';
		case 'mcp_tool': {
			const name = toolName(event);
			return (
				type === 'tool_call' &&
				name !== null &&
				(name.startsWith('mcp__') || name === 'CallMcpTool')
			);
		}
		case 'skill':
			return type === 'skill_invocation';
		case 'task':
			// TodoWrite is the older form of the Task tools, so they share one chip.
			return (
				type === 'todo_update' ||
				(type === 'tool_call' && TASK_TOOLS.includes(toolName(event) ?? ''))
			);
		case 'error':
			return (
				event.metadata?.result_status === 'error' ||
				(type === 'tool_call' &&
					event.metadata?.has_result === true &&
					!event.metadata.result_status) ||
				isFailedTask(event)
			);
		case 'subagent':
			// In an agent view, only spawns of OTHER agents count; every event there is the agent's own.
			if (currentAgentId) {
				return type === 'subagent_spawn' || Boolean(event.metadata?.spawned_agent_id);
			}
			return (
				event.actor_type === 'subagent' ||
				type === 'subagent_spawn' ||
				Boolean(event.metadata?.spawned_agent_id)
			);
		case 'message':
			return type === 'message';
		case 'background':
			return type === 'task_notification' || type === 'scheduled_fire';
		case 'api_error':
			return type === 'api_error';
		case 'notice':
			return type === 'system_notice' || type === 'compaction';
		default:
			return false;
	}
}

// Metadata keys holding binary/opaque data — skipped to avoid false-positive
// matches and wasted cycles lowercasing multi-MB strings.
const SEARCH_SKIP_KEYS = new Set([
	'image_attachments',
	'tool_id',
	'result_timestamp',
	'spawned_agent_id',
	'result_parsed'
]);

// Recursively collects every searchable string value inside `value` into `out`,
// walking nested objects/arrays and skipping SEARCH_SKIP_KEYS at any depth.
function collectSearchableText(value: unknown, out: string[]): void {
	if (value == null) return;
	if (typeof value === 'string') {
		out.push(value);
		return;
	}
	if (Array.isArray(value)) {
		for (const item of value) collectSearchableText(item, out);
		return;
	}
	if (typeof value === 'object') {
		for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
			if (SEARCH_SKIP_KEYS.has(key)) continue;
			collectSearchableText(item, out);
		}
	}
}

// Per-event lowercased "haystack" cache, invalidated by content fingerprint rather than object identity
// (live-session polling replaces the event list every second). Cleared per session view in createTimelineLogic.
const haystackCache = new Map<string, { fingerprint: string; haystack: string }>();

// A separator no realistic query contains, so a multi-word query can't match across two fields' boundary.
const FIELD_SEPARATOR = String.fromCharCode(0);

// Total length of the metadata's own string values: cheap, and changes when the backend fills one in later.
function metadataTextLength(metadata: TimelineEvent['metadata'] | undefined): number {
	if (!metadata) return 0;
	let total = 0;
	for (const value of Object.values(metadata)) {
		if (typeof value === 'string') total += value.length + 1;
		else if (value != null) total += 1;
	}
	return total;
}

function getEventFingerprint(event: TimelineEvent): string {
	const m = event.metadata;
	return [
		event.timestamp,
		event.event_type,
		event.title,
		event.actor_name ?? '',
		event.summary?.length ?? 0,
		m?.has_result ? 1 : 0,
		m?.result_status ?? '',
		m?.peer_name ?? '',
		m?.spawned_agent_slug ?? '',
		m ? Object.keys(m).length : 0,
		metadataTextLength(m)
	].join('|');
}

function getHaystack(event: TimelineEvent): string {
	const fingerprint = getEventFingerprint(event);
	const cached = haystackCache.get(event.id);
	if (cached && cached.fingerprint === fingerprint) {
		return cached.haystack;
	}
	const parts: string[] = [
		event.title,
		getDisplayTitle(event),
		event.summary ?? '',
		event.actor,
		event.actor_name ?? ''
	];
	collectSearchableText(event.metadata, parts);
	const haystack = parts.join(FIELD_SEPARATOR).toLowerCase();
	haystackCache.set(event.id, { fingerprint, haystack });
	return haystack;
}

/**
 * Check if event matches search query
 */
export function matchesSearch(event: TimelineEvent, query: string): boolean {
	const trimmed = query.trim();
	if (!trimmed) return true;
	return getHaystack(event).includes(trimmed.toLowerCase());
}

/**
 * Check if event matches any active filter (OR logic) AND search query
 */
export function matchesFilters(
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

/** Count how many events each filter chip matches. */
export function calculateFilterCounts(
	events: TimelineEvent[],
	currentAgentId?: string | null
): FilterCounts {
	const counts = Object.fromEntries(FILTER_CATEGORIES.map((c) => [c, 0])) as FilterCounts;
	for (const event of events) {
		for (const category of FILTER_CATEGORIES) {
			if (matchesSingleFilter(event, category, currentAgentId)) counts[category]++;
		}
	}
	return counts;
}

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

export interface ViewItemsInput {
	events: TimelineEvent[];
	hasActiveFilter: boolean;
	isTailing: boolean;
	tailCount: number;
	revealedIds: Set<string>;
	hiddenIds: Set<string>;
	matches: (event: TimelineEvent) => boolean;
}

/** Turn events into visible events plus gaps for the hidden runs between them. */
export function buildViewItems(input: ViewItemsInput): TimelineViewItem[] {
	const { events, hasActiveFilter, isTailing, tailCount, revealedIds, hiddenIds, matches } = input;
	if (!hasActiveFilter && !isTailing && hiddenIds.size === 0) return events;

	const items: TimelineViewItem[] = [];
	let gapEvents: TimelineEvent[] = [];
	const flushGap = (trailing: boolean) => {
		if (gapEvents.length === 0) return;
		const first = gapEvents[0].id;
		const last = gapEvents[gapEvents.length - 1].id;
		items.push({
			type: 'gap',
			id: trailing ? `gap-end-${first}` : `gap-${first}-${last}`,
			events: gapEvents
		});
		gapEvents = [];
	};

	events.forEach((event, i) => {
		const isInLastN = isTailing && i >= events.length - tailCount;
		let isVisible: boolean;
		if (revealedIds.has(event.id)) {
			isVisible = true;
		} else if (hiddenIds.has(event.id)) {
			isVisible = false;
		} else if (isTailing && !hasActiveFilter) {
			// Tailing with no filter shows only the last N.
			isVisible = isInLastN;
		} else {
			isVisible = isInLastN || matches(event);
		}

		if (isVisible) {
			flushGap(false);
			items.push(event);
		} else {
			gapEvents.push(event);
		}
	});
	flushGap(true);
	return items;
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
	// New session view — event ids are session-scoped, so prior entries can never hit again.
	haystackCache.clear();

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
	let manuallyRevealedIds = $state<Set<string>>(new Set());
	let manuallyHiddenIds = $state<Set<string>>(new Set());

	// System is a filter like the others, except that unselected its events are not in the list at all.
	const showSystem = $derived(activeFilters.has('system'));
	const baseEvents = $derived(selectBaseEvents(eventsGetter(), showSystem));
	const systemCount = $derived(eventsGetter().filter(isSystemContext).length);

	// The System chip always shows how many there are, selected or not.
	const counts = $derived.by<FilterCounts>(() => {
		return { ...calculateFilterCounts(baseEvents, getAgentId()), system: systemCount };
	});

	// Selecting every available category is the same as selecting none.
	const effectiveFilters = $derived.by<Set<FilterCategory>>(() => {
		// With System selected the filter is never "everything": other kinds still need their chips.
		if (activeFilters.has('system')) return activeFilters;
		const availableCategories = FILTER_CATEGORIES.filter((c) => c !== 'system' && counts[c] > 0);
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
	const viewItems = $derived.by<TimelineViewItem[]>(() =>
		buildViewItems({
			events: baseEvents,
			hasActiveFilter,
			isTailing,
			tailCount,
			revealedIds: manuallyRevealedIds,
			hiddenIds: manuallyHiddenIds,
			matches: (event) => matchesFilters(event, effectiveFilters, searchQuery, getAgentId())
		})
	);

	// Strict matches only; manually revealed events do not count.
	const matchingCount = $derived.by(() => {
		return baseEvents.filter((e) =>
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

	function toggleExpand(_index: number, eventId: string) {
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
		get baseEvents() {
			return baseEvents;
		},
		get showSystem() {
			return showSystem;
		},
		get systemCount() {
			return systemCount;
		},
		// Actions
		toggleFilter,
		clearFilters,
		setSearchQuery,
		toggleExpand,
		setExpandedId,
		expandGap,
		toggleHide,
		// Utility functions
		matchesFilters: (event: TimelineEvent) =>
			matchesFilters(event, effectiveFilters, searchQuery, getAgentId())
	};
}
