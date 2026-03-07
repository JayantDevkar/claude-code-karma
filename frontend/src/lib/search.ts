/**
 * Session Search Utilities
 *
 * URL serialization, filter chips, and date range calculations
 * for the session search feature.
 */

import type {
	SearchFilters,
	FilterChip,
	SearchScope,
	SearchScopeSelection,
	SessionStatusFilter,
	SessionSourceFilter,
	SearchDateRange,
	LiveSubStatus,
	LiveSessionSummary,
	LiveStatusCounts,
	SessionSummary,
	SessionWithContext
} from './api-types';
import { ALL_LIVE_SUB_STATUSES, scopeSelectionToApi, apiToScopeSelection } from './api-types';
import { shouldShowEndedStatus } from './live-session-config';

// ============================================================================
// Default Filter State
// ============================================================================

export const DEFAULT_FILTERS: SearchFilters = {
	query: '',
	tokens: [],
	scope: 'both',
	status: 'all',
	dateRange: 'all',
	liveSubStatuses: [...ALL_LIVE_SUB_STATUSES],
	source: 'all'
};

/** Maximum number of search tokens allowed */
export const MAX_SEARCH_TOKENS = 7;

// ============================================================================
// URL Serialization
// ============================================================================

/**
 * Convert search filters to URL search params.
 * Only includes non-default values to keep URLs clean.
 * Tokens are serialized as comma-separated values in 'q' param.
 */
export function filtersToParams(filters: SearchFilters): URLSearchParams {
	const params = new URLSearchParams();

	// Use tokens if available, fallback to query for backward compat
	if (filters.tokens && filters.tokens.length > 0) {
		params.set('q', tokensToParam(filters.tokens));
	} else if (filters.query) {
		params.set('q', filters.query);
	}
	if (filters.scope !== 'both') params.set('scope', filters.scope);
	if (filters.status !== 'all') params.set('status', filters.status);
	if (filters.dateRange !== 'all') params.set('range', filters.dateRange);
	if (filters.customStart) params.set('from', filters.customStart.toISOString().split('T')[0]);
	if (filters.customEnd) params.set('to', filters.customEnd.toISOString().split('T')[0]);
	if (filters.liveSubStatuses && filters.liveSubStatuses.length < ALL_LIVE_SUB_STATUSES.length) {
		params.set('substatus', filters.liveSubStatuses.join(','));
	}
	if (filters.source && filters.source !== 'all') params.set('source', filters.source);

	return params;
}

/**
 * Convert tokens array to comma-separated URL param value.
 */
export function tokensToParam(tokens: string[]): string {
	return tokens.map((t) => encodeURIComponent(t)).join(',');
}

/**
 * Parse comma-separated URL param value to tokens array.
 */
export function paramToTokens(param: string): string[] {
	if (!param) return [];
	return param
		.split(',')
		.map((t) => decodeURIComponent(t.trim()))
		.filter(Boolean)
		.slice(0, MAX_SEARCH_TOKENS);
}

/**
 * Parse URL search params to filter state.
 * Validates values against allowed options.
 * Parses 'q' param as comma-separated tokens.
 */
export function paramsToFilters(params: URLSearchParams): SearchFilters {
	const scopeParam = params.get('scope');
	const statusParam = params.get('status');
	const rangeParam = params.get('range');
	const substatusParam = params.get('substatus');
	const sourceParam = params.get('source');
	const queryParam = params.get('q') || '';

	// Parse tokens from query param
	const tokens = paramToTokens(queryParam);

	return {
		query: queryParam,
		tokens,
		scope: isValidScope(scopeParam) ? scopeParam : 'both',
		status: isValidStatus(statusParam) ? statusParam : 'all',
		dateRange: isValidDateRange(rangeParam) ? rangeParam : 'all',
		customStart: params.get('from') ? new Date(params.get('from')!) : undefined,
		customEnd: params.get('to') ? new Date(params.get('to')!) : undefined,
		liveSubStatuses: substatusParam
			? (substatusParam
					.split(',')
					.filter((s) =>
						ALL_LIVE_SUB_STATUSES.includes(s as LiveSubStatus)
					) as LiveSubStatus[])
			: [...ALL_LIVE_SUB_STATUSES],
		source: isValidSource(sourceParam) ? sourceParam : 'all'
	};
}

function isValidScope(value: string | null): value is SearchScope {
	return value === 'both' || value === 'titles' || value === 'prompts';
}

function isValidStatus(value: string | null): value is SessionStatusFilter {
	return value === 'all' || value === 'live' || value === 'completed';
}

function isValidSource(value: string | null): value is SessionSourceFilter {
	return value === 'all' || value === 'local' || value === 'remote';
}

function isValidDateRange(value: string | null): value is SearchDateRange {
	return (
		value === 'all' ||
		value === 'today' ||
		value === '7d' ||
		value === '30d' ||
		value === 'custom'
	);
}

// ============================================================================
// Full Page Filter State — URL Serialization & Restoration
// ============================================================================

/**
 * All filter-related URL params that pages use.
 * Used by buildFilterUrlParams to clear stale values before writing new ones.
 */
const ALL_FILTER_PARAM_KEYS = [
	'q',
	'scope',
	'status',
	'range',
	'from',
	'to',
	'substatus',
	'source',
	'branches',
	'project',
	'page'
];

/**
 * Complete filter state restored from URL params.
 * Includes both SearchFilters fields and page-level state (branches, project).
 */
export interface RestoredFilterState extends SearchFilters {
	branches: Set<string>;
	project: string;
}

/**
 * Options for building filter URL params.
 * Pages pass their current state + any page-specific extras.
 */
export interface FilterUrlOptions {
	/** Core search filters (tokens, scope, status, dateRange, etc.) */
	filters: SearchFilters;
	/** Selected branch names */
	branches?: Set<string>;
	/** Selected project encoded name (sessions page only) */
	project?: string;
	/** Project slug for cleaner URLs (used instead of encoded name when available) */
	projectSlug?: string;
	/** Active tab value */
	tab?: string;
	/** Tab value that should be omitted from URL (the default tab) */
	defaultTab?: string;
	/** Extra params to set (e.g., analytics filter/start_ts/end_ts). Takes precedence over clearKeys. */
	extraParams?: Record<string, string>;
	/** Param keys to clear when not on a specific tab (e.g., analytics params). Runs before extraParams. */
	clearKeys?: string[];
}

/**
 * Restore all filter + page state from URL search params.
 * Pure function — returns a typed object, caller applies to reactive state.
 *
 * Handles: search tokens (q), scope, status, dateRange, liveSubStatuses,
 * branches, project. Validates all values against allowed options.
 */
export function restoreAllFiltersFromUrl(params: URLSearchParams): RestoredFilterState {
	// Use existing paramsToFilters for core filter state
	const base = paramsToFilters(params);

	// Parse branches
	const branchesParam = params.get('branches');
	let branches = new Set<string>();
	if (branchesParam) {
		branches = new Set(
			branchesParam
				.split(',')
				.map((b) => decodeURIComponent(b.trim()))
				.filter(Boolean)
		);
	}

	// Parse project
	const project = params.get('project') || '';

	return {
		...base,
		branches,
		project
	};
}

/**
 * Build URL search params from all filter + page state.
 * Pure function — returns a new URL object with params applied.
 *
 * Clears all filter-related params first, then sets non-default values.
 * Handles page-specific extras like tab and analytics params.
 */
export function buildFilterUrlParams(currentUrl: string, options: FilterUrlOptions): URL {
	const url = new URL(currentUrl);

	// ---- Tab params ----
	if (options.tab !== undefined) {
		if (options.tab === options.defaultTab || !options.tab) {
			url.searchParams.delete('tab');
		} else {
			url.searchParams.set('tab', options.tab);
		}
	}

	// ---- Clear keys (page-specific, e.g., analytics params when not on analytics tab) ----
	if (options.clearKeys) {
		for (const key of options.clearKeys) {
			url.searchParams.delete(key);
		}
	}

	// ---- Clear all filter-related params first to avoid stale values ----
	for (const key of ALL_FILTER_PARAM_KEYS) {
		url.searchParams.delete(key);
	}

	// ---- Apply core filter params (only non-default values) ----
	const filterParams = filtersToParams(options.filters);
	for (const [key, value] of filterParams.entries()) {
		url.searchParams.set(key, value);
	}

	// ---- Serialize branch filters ----
	if (options.branches && options.branches.size > 0) {
		url.searchParams.set(
			'branches',
			Array.from(options.branches)
				.map((b) => encodeURIComponent(b))
				.join(',')
		);
	}

	// ---- Serialize project filter ----
	if (options.project) {
		// Use slug for cleaner URLs when available
		url.searchParams.set('project', options.projectSlug || options.project);
	}

	// ---- Extra params (analytics etc.) ----
	if (options.extraParams) {
		for (const [key, value] of Object.entries(options.extraParams)) {
			url.searchParams.set(key, value);
		}
	}

	return url;
}

// ============================================================================
// Filter Chips
// ============================================================================

/**
 * Generate filter chips for active (non-default) filters.
 * Used to display active filters with remove buttons.
 */
export function getFilterChips(filters: SearchFilters): FilterChip[] {
	const chips: FilterChip[] = [];

	// Note: tokens are displayed inline in TokenSearchInput, so we don't show them here

	if (filters.scope !== 'both') {
		chips.push({
			key: 'scope',
			label: 'Search in',
			value: filters.scope === 'titles' ? 'Titles' : 'Prompts'
		});
	}

	if (filters.status === 'live') {
		const subStatuses = filters.liveSubStatuses || ALL_LIVE_SUB_STATUSES;
		if (subStatuses.length < ALL_LIVE_SUB_STATUSES.length) {
			// Show which sub-statuses are selected
			const labels = subStatuses.map((s) => capitalizeFirst(s)).join(', ');
			chips.push({ key: 'status', label: 'Status', value: `Live (${labels})` });
		} else {
			chips.push({ key: 'status', label: 'Status', value: 'Live' });
		}
	} else if (filters.status === 'completed') {
		chips.push({ key: 'status', label: 'Status', value: 'Completed' });
	}

	if (filters.dateRange !== 'all') {
		chips.push({
			key: 'dateRange',
			label: 'Date',
			value: getDateRangeLabel(filters.dateRange)
		});
	}

	if (filters.source && filters.source !== 'all') {
		chips.push({
			key: 'source',
			label: 'Source',
			value: filters.source === 'local' ? 'Local' : 'Remote'
		});
	}

	return chips;
}

function capitalizeFirst(str: string): string {
	return str.charAt(0).toUpperCase() + str.slice(1);
}

function getDateRangeLabel(range: SearchDateRange): string {
	const labels: Record<SearchDateRange, string> = {
		all: 'All time',
		today: 'Today',
		'7d': 'Last 7 days',
		'30d': 'Last 30 days',
		custom: 'Custom'
	};
	return labels[range];
}

// ============================================================================
// Date Range Timestamps
// ============================================================================

/**
 * Calculate Unix timestamps (milliseconds) for a date range filter.
 * Used for API query parameters.
 */
export function getDateRangeTimestamps(
	range: SearchDateRange,
	customStart?: Date,
	customEnd?: Date
): { start_ts?: number; end_ts?: number } {
	const now = new Date();

	switch (range) {
		case 'today': {
			const todayStart = new Date(now.getFullYear(), now.getMonth(), now.getDate());
			return { start_ts: todayStart.getTime() };
		}

		case '7d': {
			const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
			return { start_ts: weekAgo.getTime() };
		}

		case '30d': {
			const monthAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
			return { start_ts: monthAgo.getTime() };
		}

		case 'custom':
			return {
				start_ts: customStart?.getTime(),
				end_ts: customEnd?.getTime()
			};

		default:
			return {};
	}
}

// ============================================================================
// Filter State Helpers
// ============================================================================

/**
 * Check if any filters are active (non-default).
 */
export function hasActiveFilters(filters: SearchFilters): boolean {
	const hasSubStatusFilter =
		filters.liveSubStatuses !== undefined &&
		filters.liveSubStatuses.length < ALL_LIVE_SUB_STATUSES.length;
	const hasTokens = filters.tokens && filters.tokens.length > 0;
	const hasSourceFilter = filters.source !== undefined && filters.source !== 'all';
	return (
		hasTokens ||
		filters.query !== '' ||
		filters.scope !== 'both' ||
		filters.status !== 'all' ||
		filters.dateRange !== 'all' ||
		hasSubStatusFilter ||
		hasSourceFilter
	);
}

/**
 * Reset a specific filter to its default value.
 */
export function resetFilter(filters: SearchFilters, key: keyof SearchFilters): SearchFilters {
	return {
		...filters,
		[key]: DEFAULT_FILTERS[key]
	};
}

/**
 * Merge partial filter updates into existing filters.
 */
export function updateFilters(
	filters: SearchFilters,
	updates: Partial<SearchFilters>
): SearchFilters {
	return { ...filters, ...updates };
}

// ============================================================================
// API Query Parameter Builder
// ============================================================================

/**
 * Build API query parameters from search filters.
 * Converts frontend filter state to API-compatible params.
 */
export function buildApiParams(
	filters: SearchFilters,
	additionalParams?: Record<string, string>
): URLSearchParams {
	const params = new URLSearchParams(additionalParams);

	if (filters.query) {
		params.set('search', filters.query);
	}

	if (filters.scope !== 'both') {
		params.set('scope', filters.scope);
	}

	if (filters.status !== 'all') {
		params.set('status', filters.status);
	}

	const { start_ts, end_ts } = getDateRangeTimestamps(
		filters.dateRange,
		filters.customStart,
		filters.customEnd
	);

	if (start_ts) {
		params.set('start_ts', start_ts.toString());
	}

	if (end_ts) {
		params.set('end_ts', end_ts.toString());
	}

	// Branch filter (if provided in additional params or separate arg)
	// Note: Branch filtering is typically handled via separate `branch` param in API

	return params;
}

// ============================================================================
// Display Label Helpers
// ============================================================================

/**
 * Default scope selection (both checked).
 */
export const DEFAULT_SCOPE_SELECTION: SearchScopeSelection = {
	titles: true,
	prompts: true
};

/**
 * Scope options for multi-select checkboxes.
 */
export const SCOPE_CHECKBOX_OPTIONS: { key: keyof SearchScopeSelection; label: string }[] = [
	{ key: 'titles', label: 'Titles' },
	{ key: 'prompts', label: 'Prompts' }
];

/**
 * @deprecated Use SCOPE_CHECKBOX_OPTIONS with multi-select UI instead.
 */
export const SCOPE_OPTIONS: { value: SearchScope; label: string }[] = [
	{ value: 'both', label: 'Titles & Prompts' },
	{ value: 'titles', label: 'Titles only' },
	{ value: 'prompts', label: 'Prompts only' }
];

// Re-export scope conversion helpers for convenience
export { scopeSelectionToApi, apiToScopeSelection };

export const STATUS_OPTIONS: { value: SessionStatusFilter; label: string; color?: string }[] = [
	{ value: 'all', label: 'All' },
	{ value: 'live', label: 'Live', color: 'var(--success)' },
	{ value: 'completed', label: 'Completed', color: 'var(--text-muted)' }
];

export const SOURCE_OPTIONS: { value: SessionSourceFilter; label: string }[] = [
	{ value: 'all', label: 'All' },
	{ value: 'local', label: 'Local' },
	{ value: 'remote', label: 'Remote' }
];

export const DATE_RANGE_OPTIONS: { value: SearchDateRange; label: string }[] = [
	{ value: 'all', label: 'All time' },
	{ value: 'today', label: 'Today' },
	{ value: '7d', label: 'Last 7 days' },
	{ value: '30d', label: 'Last 30 days' },
	{ value: 'custom', label: 'Custom range...' }
];

// ============================================================================
// Shared Session Filtering Utilities
// ============================================================================

/**
 * Base session type for filtering (works with both SessionSummary and SessionWithContext).
 */
type FilterableSession = SessionSummary | SessionWithContext;

/**
 * Filter sessions by search query with scope selection.
 *
 * @param sessions - Array of sessions to filter
 * @param query - Search query string
 * @param scopeSelection - Which fields to search (titles, prompts, or both)
 * @returns Filtered sessions matching the query
 * @deprecated Use filterSessionsByTokens for multi-token AND search
 */
export function filterSessionsByQuery<T extends FilterableSession>(
	sessions: T[],
	query: string,
	scopeSelection: SearchScopeSelection
): T[] {
	if (!query.trim()) return sessions;

	const normalizedQuery = query.toLowerCase().trim();

	return sessions.filter((session) => {
		let matches = false;

		// Search in prompts/slug/uuid (if prompts is selected)
		if (scopeSelection.prompts) {
			const matchSlug = session.slug?.toLowerCase().includes(normalizedQuery);
			const matchPrompt = session.initial_prompt?.toLowerCase().includes(normalizedQuery);
			const matchUuid = session.uuid.toLowerCase().includes(normalizedQuery);
			if (matchSlug || matchPrompt || matchUuid) {
				matches = true;
			}
		}

		// Search in session titles (if titles is selected)
		if (scopeSelection.titles) {
			const matchTitle = session.session_titles?.some((t) =>
				t.toLowerCase().includes(normalizedQuery)
			);
			if (matchTitle) {
				matches = true;
			}
		}

		return matches;
	});
}

/**
 * Filter sessions by search tokens with AND logic.
 * All tokens must be found in the searchable fields for a session to match.
 *
 * @param sessions - Array of sessions to filter
 * @param tokens - Array of search tokens (max 7)
 * @param scopeSelection - Which fields to search (titles, prompts, or both)
 * @returns Filtered sessions where ALL tokens match
 */
export function filterSessionsByTokens<T extends FilterableSession>(
	sessions: T[],
	tokens: string[],
	scopeSelection: SearchScopeSelection
): T[] {
	if (!tokens || tokens.length === 0) return sessions;

	const normalizedTokens = tokens.map((t) => t.toLowerCase().trim()).filter(Boolean);
	if (normalizedTokens.length === 0) return sessions;

	return sessions.filter((session) => {
		// Build combined searchable text based on scope
		const searchableTexts: string[] = [];

		if (scopeSelection.prompts) {
			if (session.slug) searchableTexts.push(session.slug.toLowerCase());
			if (session.initial_prompt) searchableTexts.push(session.initial_prompt.toLowerCase());
			searchableTexts.push(session.uuid.toLowerCase());
		}

		if (scopeSelection.titles) {
			session.session_titles?.forEach((t) => searchableTexts.push(t.toLowerCase()));
		}

		const combinedText = searchableTexts.join(' ');

		// AND logic: ALL tokens must be found
		return normalizedTokens.every((token) => combinedText.includes(token));
	});
}

/**
 * Live session lookup function type.
 * Created by createLiveSessionLookup for consistent live session matching.
 */
export type LiveSessionLookupFn = (session: FilterableSession) => LiveSessionSummary | null;

/**
 * Historical session lookup function type.
 * Created by createHistoricalSessionLookup for reverse lookups.
 */
export type HistoricalSessionLookupFn<T extends FilterableSession = FilterableSession> = (
	liveSession: LiveSessionSummary
) => T | null;

// ============================================================================
// Memoization Cache for Lookup Functions
// ============================================================================

/**
 * Memoized lookup cache - stores last input reference and computed result.
 * This prevents rebuilding Maps on every render when input hasn't changed.
 */
let liveSessionLookupCache: {
	input: LiveSessionSummary[] | Map<string, LiveSessionSummary> | null;
	result: LiveSessionLookupFn | null;
} = { input: null, result: null };

let historicalSessionLookupCache: {
	input: FilterableSession[] | null;
	result: HistoricalSessionLookupFn | null;
} = { input: null, result: null };

/**
 * Create a live session lookup function with slug-first matching strategy.
 * This unified strategy ensures consistent behavior across all pages.
 *
 * MEMOIZED: Returns cached result if input reference hasn't changed.
 *
 * @param liveSessions - Array or Map of live sessions
 * @returns Lookup function that finds live session for a given session
 */
export function createLiveSessionLookup(
	liveSessions: LiveSessionSummary[] | Map<string, LiveSessionSummary>
): LiveSessionLookupFn {
	// Return cached result if input reference is the same
	if (liveSessionLookupCache.input === liveSessions && liveSessionLookupCache.result) {
		return liveSessionLookupCache.result;
	}

	// Build lookup maps for efficient matching
	const bySlug = new Map<string, LiveSessionSummary>();
	const bySessionId = new Map<string, LiveSessionSummary>();

	const sessions = liveSessions instanceof Map ? Array.from(liveSessions.values()) : liveSessions;

	for (const ls of sessions) {
		if (ls.slug) {
			bySlug.set(ls.slug, ls);
		}
		if (ls.session_id) {
			bySessionId.set(ls.session_id, ls);
		}
	}

	const lookupFn: LiveSessionLookupFn = (
		session: FilterableSession
	): LiveSessionSummary | null => {
		// Slug-first matching strategy (preferred - works for resumed sessions)
		if (session.slug) {
			const bySlugMatch = bySlug.get(session.slug);
			if (bySlugMatch) {
				// Apply 45-minute timeout for ended sessions
				if (
					bySlugMatch.status === 'ended' &&
					!shouldShowEndedStatus(bySlugMatch.updated_at)
				) {
					return null;
				}
				return bySlugMatch;
			}
		}

		// Fallback to UUID/session_id matching
		const byIdMatch = bySessionId.get(session.uuid);
		if (byIdMatch) {
			// Apply 45-minute timeout for ended sessions
			if (byIdMatch.status === 'ended' && !shouldShowEndedStatus(byIdMatch.updated_at)) {
				return null;
			}
			return byIdMatch;
		}

		return null;
	};

	// Cache the result
	liveSessionLookupCache = { input: liveSessions, result: lookupFn };
	return lookupFn;
}

/**
 * Filter sessions by status (all, live, completed).
 *
 * UNIFIED BEHAVIOR:
 * - 'all': Returns all sessions
 * - 'completed': Returns only sessions without active live status
 * - 'live': Returns only sessions WITH active live status that match the selected sub-statuses
 *
 * @param sessions - Array of sessions to filter
 * @param status - Status filter to apply
 * @param getLiveSession - Function to lookup live session for a given session
 * @param selectedLiveSubStatuses - Selected live sub-statuses (only applies when status='live')
 * @returns Filtered sessions
 */
export function filterSessionsByStatus<T extends FilterableSession>(
	sessions: T[],
	status: SessionStatusFilter,
	getLiveSession: LiveSessionLookupFn,
	selectedLiveSubStatuses: LiveSubStatus[] = [...ALL_LIVE_SUB_STATUSES]
): T[] {
	if (status === 'all') {
		return sessions;
	}

	if (status === 'completed') {
		// Show only sessions without active live status
		return sessions.filter((session) => !getLiveSession(session));
	}

	if (status === 'live') {
		// Show only sessions with active live status, filtered by sub-statuses
		return sessions.filter((session) => {
			const live = getLiveSession(session);
			if (!live) return false;
			return selectedLiveSubStatuses.includes(live.status as LiveSubStatus);
		});
	}

	return sessions;
}

/**
 * Filter sessions by date range.
 *
 * @param sessions - Array of sessions to filter
 * @param dateRange - Date range preset
 * @param customStart - Custom start date (only used when dateRange='custom')
 * @param customEnd - Custom end date (only used when dateRange='custom')
 * @returns Filtered sessions within the date range
 */
export function filterSessionsByDateRange<T extends FilterableSession>(
	sessions: T[],
	dateRange: SearchDateRange,
	customStart?: Date,
	customEnd?: Date
): T[] {
	const { start_ts, end_ts } = getDateRangeTimestamps(dateRange, customStart, customEnd);

	let result = sessions;

	if (start_ts) {
		result = result.filter((s) => s.start_time && new Date(s.start_time).getTime() >= start_ts);
	}

	if (end_ts) {
		result = result.filter((s) => s.start_time && new Date(s.start_time).getTime() <= end_ts);
	}

	return result;
}

/**
 * Filter sessions by branch (OR logic - matches ANY selected branch).
 *
 * @param sessions - Array of sessions to filter
 * @param branches - Set or array of branch names to match
 * @returns Sessions that have at least one matching branch
 */
export function filterSessionsByBranch<T extends FilterableSession>(
	sessions: T[],
	branches: Set<string> | string[]
): T[] {
	const branchSet = branches instanceof Set ? branches : new Set(branches);

	if (branchSet.size === 0) {
		return sessions;
	}

	return sessions.filter((session) =>
		session.git_branches?.some((branch) => branchSet.has(branch))
	);
}

/**
 * Filter sessions by source (local vs remote).
 *
 * @param sessions - Array of sessions to filter
 * @param source - Source filter: 'all', 'local', or 'remote'
 * @returns Filtered sessions matching the source
 */
export function filterSessionsBySource<T extends FilterableSession>(
	sessions: T[],
	source: SessionSourceFilter
): T[] {
	if (source === 'all') return sessions;

	return sessions.filter((session) => {
		const isRemote = !!(session as SessionSummary).remote_user_id;
		return source === 'remote' ? isRemote : !isRemote;
	});
}

/**
 * Filter sessions by project (OR logic - matches ANY selected project).
 *
 * @param sessions - Array of sessions to filter
 * @param projects - Set or array of project names to match
 * @returns Sessions that match any selected project
 */
export function filterSessionsByProject<T extends FilterableSession>(
	sessions: T[],
	projects: Set<string> | string[]
): T[] {
	const projectSet = projects instanceof Set ? projects : new Set(projects);

	if (projectSet.size === 0) {
		return sessions;
	}

	return sessions.filter((session) => {
		const projectName =
			'project_name' in session ? (session as SessionWithContext).project_name : '';
		return projectSet.has(projectName);
	});
}

/**
 * Calculate live status counts from live sessions array.
 *
 * @param liveSessions - Array of live sessions
 * @returns Counts for each live sub-status
 */
export function calculateLiveStatusCounts(liveSessions: LiveSessionSummary[]): LiveStatusCounts {
	// Filter ended sessions by 45-minute timeout
	const visibleSessions = liveSessions.filter(
		(s) => s.status !== 'ended' || shouldShowEndedStatus(s.updated_at)
	);

	return {
		total: visibleSessions.length,
		starting: visibleSessions.filter((s) => s.status === 'starting').length,
		active: visibleSessions.filter((s) => s.status === 'active').length,
		idle: visibleSessions.filter((s) => s.status === 'idle').length,
		waiting: visibleSessions.filter((s) => s.status === 'waiting').length,
		stopped: visibleSessions.filter((s) => s.status === 'stopped').length,
		stale: visibleSessions.filter((s) => s.status === 'stale').length,
		ended: visibleSessions.filter((s) => s.status === 'ended').length
	};
}

/**
 * Create a lookup function to find historical session for a live session (reverse lookup).
 *
 * MEMOIZED: Returns cached result if input reference hasn't changed.
 *
 * @param sessions - Array of historical sessions
 * @returns Function to find historical session matching a live session
 */
export function createHistoricalSessionLookup<T extends FilterableSession>(
	sessions: T[]
): (liveSession: LiveSessionSummary) => T | null {
	// Return cached result if input reference is the same
	// Note: Type assertion needed due to generic type parameter
	if (historicalSessionLookupCache.input === sessions && historicalSessionLookupCache.result) {
		return historicalSessionLookupCache.result as (liveSession: LiveSessionSummary) => T | null;
	}

	// Build lookup maps
	const bySlug = new Map<string, T>();
	const byUuid = new Map<string, T>();

	for (const s of sessions) {
		if (s.slug) {
			bySlug.set(s.slug, s);
		}
		byUuid.set(s.uuid, s);
	}

	const lookupFn = (liveSession: LiveSessionSummary): T | null => {
		// Try slug match first
		if (liveSession.slug) {
			const bySlugMatch = bySlug.get(liveSession.slug);
			if (bySlugMatch) return bySlugMatch;
		}

		// Fallback to session_id match
		if (liveSession.session_id) {
			const byIdMatch = byUuid.get(liveSession.session_id);
			if (byIdMatch) return byIdMatch;
		}

		return null;
	};

	// Cache the result
	historicalSessionLookupCache = {
		input: sessions,
		result: lookupFn as HistoricalSessionLookupFn
	};

	return lookupFn;
}

// Re-export shouldShowEndedStatus for convenience
export { shouldShowEndedStatus } from './live-session-config';
