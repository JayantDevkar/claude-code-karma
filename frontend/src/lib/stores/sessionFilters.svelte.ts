/**
 * Session Filters Composable
 *
 * Shared reactive state and logic for session filtering across pages.
 * Uses Svelte 5 runes for reactivity.
 */

import { browser } from '$app/environment';
import type {
	SearchFilters,
	SearchScopeSelection,
	SessionStatusFilter,
	SearchDateRange,
	LiveSubStatus,
	LiveSessionSummary,
	LiveStatusCounts,
	SessionSummary,
	SessionWithContext,
	BranchSummary,
	BranchesData
} from '$lib/api-types';
import { ALL_LIVE_SUB_STATUSES, scopeSelectionToApi, apiToScopeSelection } from '$lib/api-types';
import {
	DEFAULT_FILTERS,
	DEFAULT_SCOPE_SELECTION,
	getFilterChips,
	hasActiveFilters as checkHasActiveFilters,
	getDateRangeTimestamps,
	filterSessionsByQuery,
	filterSessionsByStatus,
	filterSessionsByDateRange,
	filterSessionsByBranch,
	createLiveSessionLookup,
	calculateLiveStatusCounts,
	createHistoricalSessionLookup,
	shouldShowEndedStatus,
	type LiveSessionLookupFn
} from '$lib/search';
import { API_BASE } from '$lib/config';

/**
 * Filterable session type - works with both SessionSummary and SessionWithContext
 */
type FilterableSession = SessionSummary | SessionWithContext;

/**
 * Options for creating session filters
 */
export interface SessionFiltersOptions {
	/** Initial project filter (encoded name) */
	initialProject?: string;
	/** Initial branch filter */
	initialBranch?: string;
	/** Initial search query */
	initialQuery?: string;
	/** Initial scope */
	initialScope?: 'both' | 'titles' | 'prompts';
	/** Initial status */
	initialStatus?: SessionStatusFilter;
	/** API base URL */
	apiBase?: string;
}

/**
 * Creates a reactive session filters store with all filter state and logic.
 *
 * @param options - Initial filter options
 * @returns Reactive filter state and methods
 */
export function createSessionFilters(options: SessionFiltersOptions = {}) {
	// ============================================================================
	// Core Filter State
	// ============================================================================

	let searchQuery = $state(options.initialQuery || '');
	let scopeSelection = $state<SearchScopeSelection>(
		apiToScopeSelection(options.initialScope || 'both')
	);
	let selectedStatus = $state<SessionStatusFilter>(options.initialStatus || 'all');
	let selectedDateRange = $state<SearchDateRange>('all');
	let selectedLiveSubStatuses = $state<LiveSubStatus[]>([...ALL_LIVE_SUB_STATUSES]);
	let selectedProject = $state(options.initialProject || '');
	let selectedBranchFilters = $state<Set<string>>(
		new Set(options.initialBranch ? [options.initialBranch] : [])
	);

	// UI state
	let showFiltersDropdown = $state(false);
	let isMobile = $state(false);

	// ============================================================================
	// Lazy Loading State
	// ============================================================================

	let allSessionsLoaded = $state(false);
	let allSessions = $state<FilterableSession[] | null>(null);
	let isLoadingAllSessions = $state(false);
	let branchesData = $state<BranchesData | null>(null);
	let lastLoadedProject = $state<string | null>(null);

	// AbortController for cancelling in-flight fetches
	let fetchAbortController: AbortController | null = null;
	let currentFetchId = 0;

	// ============================================================================
	// Live Session State (provided externally)
	// ============================================================================

	let liveSessions = $state<LiveSessionSummary[]>([]);

	// ============================================================================
	// Derived State
	// ============================================================================

	// Build SearchFilters object for chips display
	const currentFilters = $derived<SearchFilters>({
		query: searchQuery,
		tokens: [], // Tokens are managed at page level, not in store
		scope: scopeSelectionToApi(scopeSelection),
		status: selectedStatus,
		dateRange: selectedDateRange,
		liveSubStatuses: selectedLiveSubStatuses
	});

	const filterChips = $derived(getFilterChips(currentFilters));
	const hasActiveFilters = $derived(
		checkHasActiveFilters(currentFilters) || selectedBranchFilters.size > 0
	);
	const activeFilterCount = $derived(
		filterChips.length + (selectedBranchFilters.size > 0 ? 1 : 0)
	);

	// Live session lookup function
	const getLiveSessionFn = $derived<LiveSessionLookupFn>(createLiveSessionLookup(liveSessions));

	// Live status counts
	const liveStatusCounts = $derived<LiveStatusCounts>(calculateLiveStatusCounts(liveSessions));

	// ============================================================================
	// Filter Handlers
	// ============================================================================

	function handleSearchChange(query: string) {
		searchQuery = query;
	}

	function handleScopeSelectionChange(selection: SearchScopeSelection) {
		scopeSelection = selection;
	}

	function handleStatusChange(status: SessionStatusFilter) {
		selectedStatus = status;
	}

	function handleDateRangeChange(range: SearchDateRange) {
		selectedDateRange = range;
	}

	function handleLiveSubStatusChange(statuses: LiveSubStatus[]) {
		selectedLiveSubStatuses = statuses;
	}

	function handleBranchToggle(branch: string) {
		const newSet = new Set(selectedBranchFilters);
		if (newSet.has(branch)) {
			newSet.delete(branch);
		} else {
			newSet.add(branch);
		}
		selectedBranchFilters = newSet;
	}

	function handleClearBranches() {
		selectedBranchFilters = new Set();
	}

	function handleRemoveFilter(key: keyof SearchFilters) {
		switch (key) {
			case 'scope':
				scopeSelection = { ...DEFAULT_SCOPE_SELECTION };
				break;
			case 'status':
				selectedStatus = 'all';
				selectedLiveSubStatuses = [...ALL_LIVE_SUB_STATUSES];
				break;
			case 'dateRange':
				selectedDateRange = 'all';
				break;
			case 'liveSubStatuses':
				selectedLiveSubStatuses = [...ALL_LIVE_SUB_STATUSES];
				break;
			case 'query':
				searchQuery = '';
				break;
		}
	}

	function handleClearAllFilters() {
		searchQuery = '';
		scopeSelection = { ...DEFAULT_SCOPE_SELECTION };
		selectedStatus = 'all';
		selectedDateRange = 'all';
		selectedLiveSubStatuses = [...ALL_LIVE_SUB_STATUSES];
		selectedBranchFilters = new Set();
		selectedProject = '';

		// Reset lazy-loaded data
		allSessionsLoaded = false;
		allSessions = null;
		branchesData = null;
		lastLoadedProject = null;
	}

	function toggleFiltersDropdown() {
		showFiltersDropdown = !showFiltersDropdown;
	}

	function closeFiltersDropdown() {
		showFiltersDropdown = false;
	}

	// ============================================================================
	// Project Selection
	// ============================================================================

	async function handleProjectSelect(encodedName: string | null) {
		// Cancel any in-flight fetch
		if (fetchAbortController) {
			fetchAbortController.abort();
		}

		selectedProject = encodedName || '';
		selectedBranchFilters = new Set();
		allSessionsLoaded = false;
		allSessions = null;
		branchesData = null;

		if (!encodedName) return;

		// Fetch project sessions
		fetchAbortController = new AbortController();
		const fetchId = ++currentFetchId;

		isLoadingAllSessions = true;
		try {
			const [projectRes, branchesRes] = await Promise.all([
				fetch(`${API_BASE}/projects/${encodedName}`, {
					signal: fetchAbortController.signal
				}),
				fetch(`${API_BASE}/projects/${encodedName}/branches`, {
					signal: fetchAbortController.signal
				})
			]);

			// Check if stale
			if (fetchId !== currentFetchId || selectedProject !== encodedName) {
				return;
			}

			if (projectRes.ok) {
				const projectData = await projectRes.json();
				allSessions = (projectData.sessions ?? []).map((s: FilterableSession) => ({
					...s,
					project_encoded_name: encodedName,
					project_path: projectData.path
				}));
				allSessionsLoaded = true;
				lastLoadedProject = encodedName;
			}

			if (branchesRes.ok) {
				branchesData = await branchesRes.json();
			}
		} catch (e) {
			if (e instanceof Error && e.name === 'AbortError') return;
			console.error('Failed to load project sessions:', e);
		} finally {
			if (fetchId === currentFetchId) {
				isLoadingAllSessions = false;
			}
		}
	}

	// ============================================================================
	// Filter Sessions
	// ============================================================================

	/**
	 * Apply all filters to a session array.
	 *
	 * @param sessions - Sessions to filter
	 * @returns Filtered sessions
	 */
	function applyFilters<T extends FilterableSession>(sessions: T[]): T[] {
		let result = [...sessions];

		// Filter by branch
		result = filterSessionsByBranch(result, selectedBranchFilters);

		// Filter by search query
		result = filterSessionsByQuery(result, searchQuery, scopeSelection);

		// Filter by status
		result = filterSessionsByStatus(
			result,
			selectedStatus,
			getLiveSessionFn,
			selectedLiveSubStatuses
		);

		// Filter by date range
		result = filterSessionsByDateRange(result, selectedDateRange);

		return result;
	}

	// ============================================================================
	// Mobile Detection
	// ============================================================================

	function setupMobileDetection() {
		if (!browser) return () => {};

		const checkMobile = () => {
			isMobile = window.innerWidth < 640;
		};
		checkMobile();
		window.addEventListener('resize', checkMobile);

		return () => window.removeEventListener('resize', checkMobile);
	}

	// ============================================================================
	// Cleanup
	// ============================================================================

	function cleanup() {
		if (fetchAbortController) {
			fetchAbortController.abort();
		}
	}

	// ============================================================================
	// Set Live Sessions (called by parent component)
	// ============================================================================

	function setLiveSessions(sessions: LiveSessionSummary[]) {
		liveSessions = sessions;
	}

	// ============================================================================
	// Return Public API
	// ============================================================================

	return {
		// State (reactive getters)
		get searchQuery() {
			return searchQuery;
		},
		get scopeSelection() {
			return scopeSelection;
		},
		get selectedStatus() {
			return selectedStatus;
		},
		get selectedDateRange() {
			return selectedDateRange;
		},
		get selectedLiveSubStatuses() {
			return selectedLiveSubStatuses;
		},
		get selectedProject() {
			return selectedProject;
		},
		get selectedBranchFilters() {
			return selectedBranchFilters;
		},
		get showFiltersDropdown() {
			return showFiltersDropdown;
		},
		get isMobile() {
			return isMobile;
		},

		// Lazy loading state
		get allSessionsLoaded() {
			return allSessionsLoaded;
		},
		get allSessions() {
			return allSessions;
		},
		get isLoadingAllSessions() {
			return isLoadingAllSessions;
		},
		get branchesData() {
			return branchesData;
		},

		// Derived state
		get currentFilters() {
			return currentFilters;
		},
		get filterChips() {
			return filterChips;
		},
		get hasActiveFilters() {
			return hasActiveFilters;
		},
		get activeFilterCount() {
			return activeFilterCount;
		},
		get liveStatusCounts() {
			return liveStatusCounts;
		},
		get getLiveSessionFn() {
			return getLiveSessionFn;
		},

		// Handlers
		handleSearchChange,
		handleScopeSelectionChange,
		handleStatusChange,
		handleDateRangeChange,
		handleLiveSubStatusChange,
		handleBranchToggle,
		handleClearBranches,
		handleRemoveFilter,
		handleClearAllFilters,
		toggleFiltersDropdown,
		closeFiltersDropdown,
		handleProjectSelect,

		// Utility functions
		applyFilters,
		setLiveSessions,
		setupMobileDetection,
		cleanup
	};
}

/**
 * Type for the session filters store
 */
export type SessionFiltersStore = ReturnType<typeof createSessionFilters>;
