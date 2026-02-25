<script lang="ts">
	import { browser } from '$app/environment';
	import { replaceState } from '$app/navigation';
	import { navigating } from '$app/stores';
	import { onMount, onDestroy, tick } from 'svelte';
	import {
		Search,
		X,
		ChevronDown,
		LayoutGrid,
		List,
		FolderOpen,
		GitBranch,
		MessageSquareText,
		Clock
	} from 'lucide-svelte';
	import GlobalSessionCard from '$lib/components/GlobalSessionCard.svelte';
	import LiveSessionsSection from '$lib/components/LiveSessionsSection.svelte';
	import { SkeletonGlobalSessionCard } from '$lib/components/skeleton';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import TokenSearchInput from '$lib/components/TokenSearchInput.svelte';
	import FiltersDropdown from '$lib/components/FiltersDropdown.svelte';
	import FiltersBottomSheet from '$lib/components/FiltersBottomSheet.svelte';
	import ActiveFilterChips from '$lib/components/ActiveFilterChips.svelte';
	import ActiveBranches from '$lib/components/ActiveBranches.svelte';
	import Pagination from '$lib/components/Pagination.svelte';
	import { listNavigation } from '$lib/actions/listNavigation';
	import { keyboardOverrides } from '$lib/stores/keyboardOverrides';
	import { dropdownNavigation } from '$lib/actions/dropdownNavigation';
	import { API_BASE } from '$lib/config';
	import type {
		SessionWithContext,
		ProjectFilterOption,
		LiveSessionSummary,
		StatusFilterOption,
		SearchScope,
		SearchScopeSelection,
		SessionStatusFilter,
		SearchDateRange,
		SearchFilters,
		LiveSubStatus,
		LiveStatusCounts,
		BranchSummary,
		BranchesData
	} from '$lib/api-types';
	import {
		ALL_LIVE_SUB_STATUSES,
		scopeSelectionToApi,
		apiToScopeSelection
	} from '$lib/api-types';
	import {
		filterSessionsByBranch,
		filterSessionsByTokens,
		paramToTokens,
		tokensToParam,
		restoreAllFiltersFromUrl,
		buildFilterUrlParams
	} from '$lib/search';
	import { isToday, isYesterday, isThisWeek, isThisMonth } from 'date-fns';
	import {
		DEFAULT_FILTERS,
		DEFAULT_SCOPE_SELECTION,
		getFilterChips,
		hasActiveFilters as checkHasActiveFilters,
		filterSessionsByStatus,
		filterSessionsByDateRange,
		createLiveSessionLookup,
		calculateLiveStatusCounts,
		createHistoricalSessionLookup,
		shouldShowEndedStatus,
		type LiveSessionLookupFn
	} from '$lib/search';
	import { getProjectNameFromEncoded } from '$lib/utils';

	interface PageData {
		sessions: SessionWithContext[];
		total: number;
		projects: ProjectFilterOption[];
		statusOptions: StatusFilterOption[];
		liveSessions: LiveSessionSummary[];
		error: string | null;
		filters: {
			search?: string;
			project?: string;
			branch?: string;
			scope?: SearchScope;
			status?: SessionStatusFilter;
			start_ts?: string;
			end_ts?: string;
			page: number;
			perPage: number;
		};
	}

	let { data: propsData }: { data: PageData } = $props();
	// Create reactive local copy of data to allow client-side updates (reloadSessions)
	// and ensure derived values track changes.
	let data = $state(propsData);

	$effect(() => {
		data = propsData;

		// Sync local state when navigation occurs (props update)
		searchTokens = paramToTokens(propsData.filters.search || '');

		const pVal = propsData.filters.project || '';
		if (!pVal || pVal.startsWith('-')) {
			selectedProject = pVal;
		} else {
			const m = propsData.projects.find((p: any) => p.slug === pVal);
			selectedProject = m ? m.encoded_name : pVal;
		}

		selectedBranchFilters = new Set(propsData.filters.branch ? [propsData.filters.branch] : []);
		scopeSelection = apiToScopeSelection(propsData.filters.scope || 'both');
		selectedStatus = propsData.filters.status || 'all';
	});

	// Track live sessions from the LiveSessionsSection component (for deduplication)
	let currentLiveSessions = $state<LiveSessionSummary[]>([]);

	// Reference to TokenSearchInput for CTRL+K override
	let searchInputRef: { focus: () => void } | undefined;

	// Create a Set of session identifiers that are currently live (for deduplication)
	const liveSessionIdentifiers = $derived.by(() => {
		const identifiers = new Set<string>();
		for (const ls of currentLiveSessions) {
			// Only exclude non-ended sessions from historical list
			if (ls.status !== 'ended') {
				if (ls.slug) identifiers.add(ls.slug);
				if (ls.session_id) identifiers.add(ls.session_id);
			}
		}
		return identifiers;
	});

	// Filter historical sessions to exclude those shown in Live section
	const historicalSessions = $derived(
		data.sessions.filter((session) => {
			// Check if this session is currently shown in the live section
			if (session.slug && liveSessionIdentifiers.has(session.slug)) {
				return false;
			}
			if (liveSessionIdentifiers.has(session.uuid)) {
				return false;
			}
			return true;
		})
	);

	// Unified live session lookup using shared utility (slug-first strategy)
	const getLiveSessionFn: LiveSessionLookupFn = $derived(
		createLiveSessionLookup(data.liveSessions)
	);

	// Wrapper function for components that need function reference
	function getLiveSession(session: SessionWithContext): LiveSessionSummary | null {
		return getLiveSessionFn(session);
	}

	// Unified historical session lookup using shared utility
	const getHistoricalSessionFn = $derived(createHistoricalSessionLookup(data.sessions));

	// Helper to find historical session for a live session (reverse lookup)
	function getHistoricalSession(liveSession: LiveSessionSummary): SessionWithContext | null {
		return getHistoricalSessionFn(liveSession);
	}

	// Handle live sessions updates from the LiveSessionsSection
	function handleLiveSessionsChange(sessions: LiveSessionSummary[]) {
		currentLiveSessions = sessions;
	}

	// Local state for filter inputs
	let searchTokens = $state<string[]>(paramToTokens(data.filters.search || ''));
	// Resolve project filter: URL may contain slug, but internal state uses encoded_name
	let selectedProject = $state(
		(() => {
			const filterVal = data.filters.project || '';
			if (!filterVal || filterVal.startsWith('-')) return filterVal;
			// Resolve slug to encoded_name from projects list
			const match = data.projects.find((p: any) => p.slug === filterVal);
			return match ? match.encoded_name : filterVal;
		})()
	);
	let selectedBranchFilters = $state<Set<string>>(
		new Set(data.filters.branch ? [data.filters.branch] : [])
	);
	let scopeSelection = $state<SearchScopeSelection>(
		apiToScopeSelection(data.filters.scope || 'both')
	);
	let selectedStatus = $state<SessionStatusFilter>(data.filters.status || 'all');
	let selectedDateRange = $state<SearchDateRange>('all');
	let selectedLiveSubStatuses = $state<LiveSubStatus[]>([...ALL_LIVE_SUB_STATUSES]);
	let showFiltersDropdown = $state(false);
	let isMobile = $state(false);
	let isLoading = $state(false);
	let isInvalidating = $state(false);
	let isSearching = $state(false); // Used for loading indicator during search
	let searchAbortController: AbortController | null = null;

	// Track whether filter URL sync is initialized (prevent overwriting URL before reading it)
	let filtersReady = $state(false);

	// Combined loading state: true when navigating to this page OR manual loading
	const isPageLoading = $derived(isLoading || $navigating?.to?.url.pathname === '/sessions');

	// Branches data for selected project (still needed for ActiveBranches component)
	let branchesData = $state<BranchesData | null>(null);

	// Load branches data when project is selected
	$effect(() => {
		if (browser && selectedProject && !branchesData) {
			const targetProject = selectedProject; // Capture for staleness check
			const abortController = new AbortController();

			fetch(`${API_BASE}/projects/${targetProject}/branches`, {
				signal: abortController.signal
			})
				.then((res) => (res.ok ? res.json() : null))
				.then((data) => {
					// Only update if project hasn't changed
					if (data && selectedProject === targetProject) {
						branchesData = data;
					}
				})
				.catch((e) => {
					if (e instanceof Error && e.name === 'AbortError') return;
					console.error('Failed to load branches:', e);
				});

			// Return cleanup function to abort on effect re-run
			return () => abortController.abort();
		}
	});

	// Filtered sessions count - applies user filters only (for "X of Y" display)
	// Filtered sessions count - uses server total directly
	const filteredSessionsCount = $derived(data.total);

	// Client-side filtered sessions using shared utilities
	// This is for DISPLAY - excludes sessions shown in Live section to avoid duplicates
	// Filtered sessions - now uses server data directly (already filtered)
	// Only client-side logic is to exclude sessions shown in Live section
	const filteredSessions = $derived.by(() => {
		return historicalSessions;
	});

	// Detect mobile viewport
	$effect(() => {
		if (typeof window === 'undefined') return;
		const checkMobile = () => {
			isMobile = window.innerWidth < 640;
		};
		checkMobile();
		window.addEventListener('resize', checkMobile);
		return () => window.removeEventListener('resize', checkMobile);
	});

	// ==========================================================================
	// Restore all filter state from URL params (unified)
	// ==========================================================================

	/** Resolve slug to encoded_name using project list */
	function resolveProjectFilter(val: string): string {
		if (!val || val.startsWith('-')) return val;
		const match = data.projects.find((p: any) => p.slug === val);
		return match ? match.encoded_name : val;
	}

	/** Get project slug from encoded name (for cleaner URLs) */
	function getProjectSlug(encodedName: string): string | undefined {
		return data.projects.find((p: any) => p.encoded_name === encodedName)?.slug;
	}

	function restoreFiltersFromUrl(params: URLSearchParams) {
		const restored = restoreAllFiltersFromUrl(params);

		// Restore search tokens
		searchTokens = restored.tokens;

		// Restore scope selection
		scopeSelection = apiToScopeSelection(restored.scope);

		// Restore status
		selectedStatus = restored.status;

		// Restore date range
		selectedDateRange = restored.dateRange;

		// Restore live sub-statuses
		if (restored.liveSubStatuses && restored.liveSubStatuses.length > 0) {
			selectedLiveSubStatuses = restored.liveSubStatuses;
		} else {
			selectedLiveSubStatuses = [...ALL_LIVE_SUB_STATUSES];
		}

		// Restore branch filters
		selectedBranchFilters = restored.branches;

		// Restore project filter (resolve slug to encoded_name)
		selectedProject = resolveProjectFilter(restored.project);
	}

	// Build SearchFilters object for chips display
	let currentFilters = $derived<SearchFilters>({
		query: '',
		tokens: searchTokens,
		scope: scopeSelectionToApi(scopeSelection),
		status: selectedStatus,
		dateRange: selectedDateRange,
		liveSubStatuses: selectedLiveSubStatuses
	});

	let filterChips = $derived(getFilterChips(currentFilters));
	let hasSearchFilters = $derived(checkHasActiveFilters(currentFilters));
	let activeFilterCount = $derived(filterChips.length);

	// ==========================================================================
	// Unified URL sync: all filter state in a single effect to prevent race conditions.
	// Serializes tokens, scope, status, dateRange, liveSubStatuses, branches, project
	// into URL params via a single replaceState call.
	// ==========================================================================
	$effect(() => {
		if (!browser || !filtersReady) return;

		const url = buildFilterUrlParams(window.location.href, {
			filters: currentFilters,
			branches: selectedBranchFilters,
			project: selectedProject || undefined,
			projectSlug: selectedProject ? getProjectSlug(selectedProject) : undefined
		});

		// Single replaceState call for all URL state (tick ensures reactive updates settled)
		tick().then(() => replaceState(url.toString(), {}));
	});

	// Compute live status counts using shared utility
	let liveStatusCounts = $derived(calculateLiveStatusCounts(data.liveSessions));

	// Compute visible live sessions (filtered like LiveSessionsSection does)
	// This mirrors the filtering logic in LiveSessionsSection for accurate counts
	const visibleLiveSessions = $derived.by(() => {
		// Don't count live sessions when status is 'completed'
		if (selectedStatus === 'completed') return [];

		// Filter ended sessions by timeout - only show recently ended (within 45 min)
		let result = currentLiveSessions.filter(
			(s) => s.status !== 'ended' || shouldShowEndedStatus(s.updated_at)
		);

		// Filter by live sub-statuses
		if (
			selectedLiveSubStatuses.length > 0 &&
			selectedLiveSubStatuses.length < ALL_LIVE_SUB_STATUSES.length
		) {
			result = result.filter((s) =>
				selectedLiveSubStatuses.includes(s.status as LiveSubStatus)
			);
		}

		// Filter by project
		if (selectedProject) {
			result = result.filter((s) => s.project_encoded_name === selectedProject);
		}

		// Filter by branch (requires matching to historical sessions, multi-select)
		if (selectedBranchFilters.size > 0) {
			result = result.filter((live) => {
				const historical = getHistoricalSession(live);
				if (!historical) return false;
				return historical.git_branches?.some((b) => selectedBranchFilters.has(b)) ?? false;
			});
		}

		// Filter by search tokens (match slug or project)
		if (searchTokens.length > 0) {
			result = result.filter((s) => {
				const slug = (s.slug || s.session_id || '').toLowerCase();
				const projectName = (s.cwd || '').split('/').pop()?.toLowerCase() || '';
				const combinedText = `${slug} ${projectName}`;
				// AND logic: all tokens must match
				return searchTokens.every((token) => combinedText.includes(token.toLowerCase()));
			});
		}

		return result;
	});

	// Compute recently ended sessions for the "Recently Ended" card section
	// These are ended sessions within 45-min timeout, with filters applied, matched to historical data
	// NOTE: Uses data.liveSessions (from /live-sessions API) which includes ended sessions,
	// not currentLiveSessions (from LiveSessionsSection which uses /live-sessions/active)
	const recentlyEndedSessions = $derived.by(() => {
		// Don't show when status is 'completed' (only historical)
		if (selectedStatus === 'completed') return [];

		// Filter ended sessions within 45-min timeout
		let endedLive = data.liveSessions.filter(
			(s) => s.status === 'ended' && shouldShowEndedStatus(s.updated_at)
		);

		// Apply live sub-status filter (must include 'ended')
		if (!selectedLiveSubStatuses.includes('ended')) {
			return [];
		}

		// Apply project filter
		if (selectedProject) {
			endedLive = endedLive.filter((s) => s.project_encoded_name === selectedProject);
		}

		// Apply branch filter (requires matching to historical sessions, multi-select)
		if (selectedBranchFilters.size > 0) {
			endedLive = endedLive.filter((ls) => {
				const historical = getHistoricalSession(ls);
				if (!historical) return false;
				return historical.git_branches?.some((b) => selectedBranchFilters.has(b)) ?? false;
			});
		}

		// Apply search tokens filter
		if (searchTokens.length > 0) {
			endedLive = endedLive.filter((s) => {
				const slug = (s.slug || s.session_id || '').toLowerCase();
				const projectName = (s.cwd || '').split('/').pop()?.toLowerCase() || '';
				const combinedText = `${slug} ${projectName}`;
				// AND logic: all tokens must match
				return searchTokens.every((token) => combinedText.includes(token.toLowerCase()));
			});
		}

		// Match to historical sessions and create pairs for rendering
		const pairs: { session: SessionWithContext; liveSession: LiveSessionSummary }[] = [];
		for (const ls of endedLive) {
			const historical = getHistoricalSession(ls);
			if (historical) {
				pairs.push({ session: historical, liveSession: ls });
			}
		}

		// Sort by updated_at descending (most recently ended first)
		pairs.sort(
			(a, b) =>
				new Date(b.liveSession.updated_at).getTime() -
				new Date(a.liveSession.updated_at).getTime()
		);

		// Deduplicate by session UUID (multiple live sessions can map to the same historical session)
		const seen = new Set<string>();
		const deduped = pairs.filter((p) => {
			if (seen.has(p.session.uuid)) return false;
			seen.add(p.session.uuid);
			return true;
		});

		// Cap to avoid overwhelming the section (e.g., after batch hook runs)
		return deduped.slice(0, 12);
	});

	// Deduped filtered sessions: exclude sessions already shown in "Recently Ended" section
	const dedupedFilteredSessions = $derived.by(() => {
		const recentlyEndedUuids = new Set(recentlyEndedSessions.map((pair) => pair.session.uuid));
		return filteredSessions.filter((s) => !recentlyEndedUuids.has(s.uuid));
	});

	// Count live sessions that have corresponding historical records (for deduplication)
	// These sessions appear in both live and historical, so we count them once
	const liveHistoricalOverlap = $derived.by(() => {
		let count = 0;
		for (const ls of currentLiveSessions) {
			// Skip ended sessions outside the 45-min timeout
			if (ls.status === 'ended' && !shouldShowEndedStatus(ls.updated_at)) continue;
			// Check if this live session has a matching historical session
			const hasHistorical = data.sessions.some(
				(s) =>
					(ls.slug && s.slug === ls.slug) || (ls.session_id && s.uuid === ls.session_id)
			);
			if (hasHistorical) count++;
		}
		return count;
	});

	// Derived: selected project details (must be defined before displayTotalCount)
	const selectedProjectDetails = $derived(
		data.projects.find((p) => p.encoded_name === selectedProject)
	);

	// Derived: contextual total (project total if selected, global total otherwise)
	// Must be defined before displayTotalCount which references it
	const contextualTotal = $derived(
		selectedProject && selectedProjectDetails
			? selectedProjectDetails.session_count
			: data.total
	);

	// Compute display counts for ActiveFilterChips
	// These counts reflect what's actually visible based on the status filter
	const displayFilteredCount = $derived.by(() => {
		if (selectedStatus === 'live') {
			// Only live sessions visible
			return visibleLiveSessions.length;
		} else if (selectedStatus === 'completed') {
			// Only historical sessions visible (server total)
			return data.total;
		} else {
			// Both live and historical visible
			// Note: data.total from server already includes filtered historical sessions
			return data.total + visibleLiveSessions.length;
		}
	});

	const displayTotalCount = $derived.by(() => {
		// Filter ended sessions by timeout - only count recently ended (within 45 min)
		const activeLiveSessions = currentLiveSessions.filter(
			(s) => s.status !== 'ended' || shouldShowEndedStatus(s.updated_at)
		);
		if (selectedStatus === 'live') {
			// Total live sessions (before client-side filters like search)
			return activeLiveSessions.length;
		} else if (selectedStatus === 'completed') {
			// Total historical sessions (contextual to project if selected)
			return contextualTotal;
		} else {
			// Both: historical total + live total - overlap (avoid double-counting)
			// Using data.total here because it reflects the current server-side filter state
			return data.total + activeLiveSessions.length - liveHistoricalOverlap;
		}
	});

	// 30-second polling for historical sessions
	let historicalPollInterval: ReturnType<typeof setInterval> | null = null;
	let unregisterCtrlK: (() => void) | undefined;

	onMount(() => {
		// Register CTRL+K override to focus search input on this page
		unregisterCtrlK = keyboardOverrides.registerCtrlK(() => {
			searchInputRef?.focus();
		});

		// Restore all filter state from URL params
		const params = new URLSearchParams(window.location.search);
		restoreFiltersFromUrl(params);

		// Mark filters as ready AFTER restoration so the URL sync effect doesn't fire prematurely
		filtersReady = true;

		// Handle browser back/forward navigation
		const handlePopState = () => {
			const params = new URLSearchParams(window.location.search);
			restoreFiltersFromUrl(params);
		};

		window.addEventListener('popstate', handlePopState);

		// Poll historical sessions every 30 seconds
		historicalPollInterval = setInterval(async () => {
			// Guard against concurrent invalidations AND active searches
			// Pausing polling during search prevents UI flicker/jitter while typing
			if (!isLoading && !isInvalidating && !isSearching) {
				// Only refresh live sessions (historical data is stable)
				try {
					const res = await fetch(`${API_BASE}/live-sessions`);
					if (res.ok) {
						const liveData = await res.json();
						// Update live sessions reactively
						data.liveSessions = liveData.sessions || [];
					}
				} catch {
					/* ignore polling errors */
				}
			}
		}, 30000);

		return () => window.removeEventListener('popstate', handlePopState);
	});

	onDestroy(() => {
		// Unregister CTRL+K override
		unregisterCtrlK?.();

		if (historicalPollInterval) {
			clearInterval(historicalPollInterval);
		}
		// Clear search debounce timer
		if (searchDebounceTimer) {
			clearTimeout(searchDebounceTimer);
		}
	});

	// View mode: 'list' (time-grouped) or 'grid' (compact flat)
	let viewMode = $state<'list' | 'grid'>('list');
	let viewModeInitialized = $state(false);

	// Initialize from localStorage on mount (client-side only)
	$effect(() => {
		if (typeof window !== 'undefined' && !viewModeInitialized) {
			const saved = localStorage.getItem('claude-karma-sessions-view-mode');
			if (saved === 'list' || saved === 'grid') {
				viewMode = saved;
			}
			viewModeInitialized = true;
		}
	});

	// Persist view mode changes
	$effect(() => {
		if (typeof window !== 'undefined' && viewModeInitialized) {
			localStorage.setItem('claude-karma-sessions-view-mode', viewMode);
		}
	});

	// Dropdown state
	let showProjectDropdown = $state(false);

	// Derived: active filters count (uses local state, not URL params)
	const activeFiltersCount = $derived(
		(searchTokens.length > 0 ? 1 : 0) +
			(selectedProject ? 1 : 0) +
			(selectedBranchFilters.size > 0 ? 1 : 0)
	);

	// Derived: available branches for selected project
	// Uses branchesData if available (from API), otherwise extract from sessions
	const availableBranches = $derived.by((): BranchSummary[] => {
		if (!selectedProject) return [];

		// Prefer branches data from API (matches projects page behavior)
		if (branchesData?.branches) {
			return branchesData.branches;
		}

		// Fallback: extract from sessions
		const branchCounts = new Map<string, { count: number; lastActive?: string }>();
		const projectSessions = data.sessions.filter(
			(s) => s.project_encoded_name === selectedProject
		);
		for (const session of projectSessions) {
			if (session.git_branches) {
				for (const branch of session.git_branches) {
					const existing = branchCounts.get(branch);
					if (existing) {
						existing.count++;
						if (
							session.start_time &&
							(!existing.lastActive || session.start_time > existing.lastActive)
						) {
							existing.lastActive = session.start_time;
						}
					} else {
						branchCounts.set(branch, { count: 1, lastActive: session.start_time });
					}
				}
			}
		}

		return Array.from(branchCounts.entries())
			.map(([name, { count, lastActive }]) => ({
				name,
				session_count: count,
				last_active: lastActive,
				is_active: false
			}))
			.sort((a, b) => b.session_count - a.session_count);
	});

	// Active branches (branches with live sessions)
	const activeBranchNames = $derived.by(() => {
		if (!selectedProject) return [];
		return branchesData?.active_branches ?? [];
	});

	// Reset branch filters when project changes
	$effect(() => {
		if (!selectedProject && selectedBranchFilters.size > 0) {
			selectedBranchFilters = new Set();
		}
	});

	// Time-based grouping (uses filteredSessions with all client-side filters applied)
	type DateGroup = {
		label: string;
		sessions: SessionWithContext[];
	};

	const groupedByDate = $derived.by(() => {
		const today: SessionWithContext[] = [];
		const yesterday: SessionWithContext[] = [];
		const thisWeek: SessionWithContext[] = [];
		const thisMonth: SessionWithContext[] = [];
		const older: SessionWithContext[] = [];

		for (const session of dedupedFilteredSessions) {
			const startTime = new Date(session.start_time);

			if (isToday(startTime)) {
				today.push(session);
			} else if (isYesterday(startTime)) {
				yesterday.push(session);
			} else if (isThisWeek(startTime, { weekStartsOn: 1 })) {
				thisWeek.push(session);
			} else if (isThisMonth(startTime)) {
				thisMonth.push(session);
			} else {
				older.push(session);
			}
		}

		const groups: DateGroup[] = [];
		if (today.length > 0) groups.push({ label: 'Today', sessions: today });
		if (yesterday.length > 0) groups.push({ label: 'Yesterday', sessions: yesterday });
		if (thisWeek.length > 0) groups.push({ label: 'This Week', sessions: thisWeek });
		if (thisMonth.length > 0) groups.push({ label: 'This Month', sessions: thisMonth });
		if (older.length > 0) groups.push({ label: 'Older', sessions: older });

		return groups;
	});

	// Direct API fetch to update session data without goto() + invalidate()
	// This avoids full SvelteKit page navigation which causes double-rendering
	// Direct API fetch to update session data without goto() + invalidate()
	// This avoids full SvelteKit page navigation which causes double-rendering
	async function reloadSessions(opts: { page?: number; signal?: AbortSignal } = {}) {
		// Build filter params using shared utility - ensures consistency with initial load
		// and includes all filters (status, date, branch, etc.)
		const currentFiltersState: SearchFilters = {
			query: '',
			tokens: searchTokens,
			scope: scopeSelectionToApi(scopeSelection),
			status: selectedStatus,
			dateRange: selectedDateRange,
			customStart: undefined, // Add if custom date support needed
			customEnd: undefined,
			liveSubStatuses: selectedLiveSubStatuses
		};

		const params = buildFilterUrlParams(window.location.href, {
			filters: currentFiltersState,
			branches: selectedBranchFilters,
			project: selectedProject || undefined
		}).searchParams;

		// Ensure pagination params are correct
		params.set('page', (opts.page ?? 1).toString());
		params.set('per_page', data.filters.perPage.toString());

		// Important: buildFilterUrlParams uses 'q' for query/tokens, but API expects 'search'
		// Map 'q' to 'search' if present
		if (params.has('q')) {
			params.set('search', params.get('q')!);
			params.delete('q');
		}

		// Map 'branches' (comma-separated) to 'branch' (single for now, until API supports multi)
		// API currently only supports single branch filtering, so we take the first one
		if (selectedBranchFilters.size > 0) {
			const branch = Array.from(selectedBranchFilters)[0];
			params.set('branch', branch);
			// Clean up the frontend-only 'branches' param
			params.delete('branches');
		}

		isLoading = true;
		isSearching = true;

		try {
			const [sessionsRes, liveRes] = await Promise.all([
				fetch(`${API_BASE}/sessions/all?${params.toString()}`, { signal: opts.signal }),
				fetch(`${API_BASE}/live-sessions`, { signal: opts.signal })
			]);

			if (sessionsRes.ok) {
				const result = await sessionsRes.json();
				data.sessions = result.sessions;
				data.total = result.total;
				data.projects = result.projects;
				data.filters = {
					...data.filters,
					search: params.get('search') || undefined,
					project: selectedProject || undefined,
					scope: currentFiltersState.scope,
					status: selectedStatus,
					page: opts.page ?? 1
				};
			}

			if (liveRes.ok) {
				const liveData = await liveRes.json();
				data.liveSessions = liveData.sessions || [];
			}
		} catch (e) {
			if (e instanceof DOMException && e.name === 'AbortError') {
				// Ignore abort errors
				return;
			}
			console.error('Failed to reload sessions:', e);
		} finally {
			// Only reset loading if this wasn't aborted (i.e. we are the latest request)
			if (!opts.signal?.aborted) {
				isLoading = false;
				isSearching = false;
			}
		}
	}

	// NOTE: Removed fetchSearchResults function - now using pure client-side filtering
	// Search is handled by reactive $derived computations (filteredSessions)
	// URL sync happens in handleTokensChange for shareability

	// Debounce timer for search token changes
	let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null;

	// Token change handler for TokenSearchInput - fetches filtered data directly
	function handleTokensChange(tokens: string[]) {
		searchTokens = tokens;

		if (searchDebounceTimer) clearTimeout(searchDebounceTimer);

		searchDebounceTimer = setTimeout(() => {
			// Cancel previous pending search request
			if (searchAbortController) {
				searchAbortController.abort();
			}
			searchAbortController = new AbortController();

			reloadSessions({
				page: 1, // Reset to page 1 on search change
				signal: searchAbortController.signal
			});
		}, 300);
	}

	// Scope filter change (multi-select) - triggers server reload when search tokens present
	function handleScopeSelectionChange(selection: SearchScopeSelection) {
		scopeSelection = selection;

		// If filters change, reload from server
		// Reset to page 1 for new filter context
		reloadSessions({ page: 1 });
	}

	// Legacy scope filter change (for components that still use SearchScope)
	function handleScopeChange(scope: SearchScope) {
		scopeSelection = apiToScopeSelection(scope);
	}

	// Status filter change - client-side only
	function handleStatusChange(status: SessionStatusFilter) {
		selectedStatus = status;
		reloadSessions({ page: 1 });
	}

	// Date range filter change - client-side only (URL sync handled by unified effect)
	function handleDateRangeChange(range: SearchDateRange) {
		selectedDateRange = range;
		reloadSessions({ page: 1 });
	}

	// Live sub-status filter change - client-side only
	function handleLiveSubStatusChange(statuses: LiveSubStatus[]) {
		selectedLiveSubStatuses = statuses;
	}

	// Remove a single search filter - client-side (no page reload)
	function handleRemoveSearchFilter(key: keyof SearchFilters) {
		switch (key) {
			case 'scope':
				handleScopeSelectionChange({ ...DEFAULT_SCOPE_SELECTION });
				break;
			case 'status':
				selectedStatus = 'all';
				selectedLiveSubStatuses = [...ALL_LIVE_SUB_STATUSES];
				reloadSessions({ page: 1 });
				break;
			case 'dateRange':
				selectedDateRange = 'all';
				reloadSessions({ page: 1 });
				break;
			case 'liveSubStatuses':
				selectedLiveSubStatuses = [...ALL_LIVE_SUB_STATUSES];
				break;
			case 'query':
				handleTokensChange([]);
				break;
		}
	}

	// Clear search filters only (not project/branch) - client-side (no page reload)
	function handleClearSearchFilters() {
		scopeSelection = { ...DEFAULT_SCOPE_SELECTION };
		selectedStatus = 'all';
		selectedDateRange = 'all';
		selectedLiveSubStatuses = [...ALL_LIVE_SUB_STATUSES];

		// Clear search tokens and re-fetch original sessions
		handleTokensChange([]);
	}

	// Project filter change - fetches project-filtered data directly
	function handleProjectSelect(encodedName: string | null, slug?: string | null) {
		showProjectDropdown = false;

		// Update local state directly
		if (encodedName) {
			selectedProject = encodedName;
		} else {
			selectedProject = '';
		}

		// Reset branch filters when project changes
		selectedBranchFilters = new Set();
		branchesData = null;

		reloadSessions();
	}

	// Branch filter toggle - client-side (matches projects page UX)
	function handleBranchToggle(branch: string) {
		const newSet = new Set(selectedBranchFilters);
		if (newSet.has(branch)) {
			newSet.delete(branch);
		} else {
			newSet.add(branch);
		}
		selectedBranchFilters = newSet;
		reloadSessions({ page: 1 });
	}

	function handleClearAllBranches() {
		selectedBranchFilters = new Set();
	}

	// Clear all filters - client-side (URL sync handled by unified effect)
	function clearAllFilters() {
		// Reset all client-side filters
		scopeSelection = { ...DEFAULT_SCOPE_SELECTION };
		selectedStatus = 'all';
		selectedDateRange = 'all';
		selectedLiveSubStatuses = [...ALL_LIVE_SUB_STATUSES];
		selectedBranchFilters = new Set();
		selectedProject = '';

		// Reset branches data
		branchesData = null;

		// Re-fetch original unfiltered sessions from API
		handleTokensChange([]);
	}

	// Helper to get project name — prefer display_name from API data
	function getProjectName(encodedName: string): string {
		const proj = data.projects.find((p: any) => p.encoded_name === encodedName);
		if (proj) return proj.display_name || proj.name;
		return getProjectNameFromEncoded(encodedName) || encodedName;
	}

	// Check if client-side filters are active (filters applied in browser)
	// All filters are now client-side: project, branch, search tokens, scope, status
	// When client-side filters are active, we show filtered count instead of pagination
	const hasClientSideFilters = $derived(
		false // All filtering is now server-side
	);

	// Pagination calculations - use filtered count when client-side filters are active
	const effectiveTotal = $derived(
		hasClientSideFilters ? dedupedFilteredSessions.length : contextualTotal
	);
	const totalPages = $derived(
		hasClientSideFilters ? 1 : Math.ceil(contextualTotal / data.filters.perPage)
	);
	const currentPage = $derived(data.filters.page);
	const hasNextPage = $derived(!hasClientSideFilters && currentPage < totalPages);
	const hasPrevPage = $derived(!hasClientSideFilters && currentPage > 1);
	const hasActiveFilters = $derived(activeFiltersCount > 0);

	// Navigate to a specific page (only works when no client-side filters)
	function goToPage(newPage: number) {
		if (hasClientSideFilters) return;
		if (newPage < 1 || newPage > totalPages) return;
		reloadSessions({ page: newPage });
	}

	// Determine if live sessions should be visible based on date filter
	// Live sessions are "happening now" so only show when date range includes today
	const showLiveSessions = $derived.by(() => {
		// No date filter = show live sessions
		if (!data.filters.end_ts) return true;

		// Check if end_ts includes today (end of today)
		const endTs = parseInt(data.filters.end_ts);
		const now = Date.now();
		return endTs >= now;
	});

	// Check if Recently Ended section should be visible
	const showRecentlyEnded = $derived(
		showLiveSessions && selectedStatus !== 'completed' && recentlyEndedSessions.length > 0
	);
</script>

<svelte:head>
	<title>Sessions | Claude Karma</title>
</svelte:head>

<div use:listNavigation>
	<!-- Page Header with Breadcrumb -->
	<PageHeader
		title="Sessions"
		icon={MessageSquareText}
		iconColor="--nav-teal"
		breadcrumbs={[{ label: 'Dashboard', href: '/' }, { label: 'Sessions' }]}
		subtitle="Browse all Claude Code sessions across projects"
	/>

	<!-- Search and Filters -->
	<div class="mb-6 flex flex-col sm:flex-row gap-2">
		<!-- Token Search Input with Filters -->
		<div class="relative flex-1 flex gap-2">
			<TokenSearchInput
				bind:this={searchInputRef}
				tokens={searchTokens}
				onTokensChange={handleTokensChange}
				placeholder="Search titles, prompts, or slugs..."
				class="flex-1"
				isLoading={isSearching}
			/>

			<!-- Filters Button -->
			<button
				onclick={() => (showFiltersDropdown = !showFiltersDropdown)}
				class="inline-flex items-center gap-2 px-3 h-[38px] text-xs font-medium rounded-[6px] hover:border-[var(--border-hover)] transition-all whitespace-nowrap {hasSearchFilters
					? 'bg-[var(--accent-subtle)] border border-[var(--accent)] text-[var(--accent)]'
					: 'bg-[var(--bg-base)] border border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)]'}"
			>
				<span>Filters</span>
				{#if activeFilterCount > 0}
					<span
						class="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 bg-[var(--accent)] text-white rounded-full text-[10px] font-bold tabular-nums"
					>
						{activeFilterCount}
					</span>
				{/if}
			</button>

			{#if showFiltersDropdown && !isMobile}
				<FiltersDropdown
					{scopeSelection}
					onScopeSelectionChange={handleScopeSelectionChange}
					status={selectedStatus}
					onStatusChange={handleStatusChange}
					dateRange={selectedDateRange}
					onDateRangeChange={handleDateRangeChange}
					onReset={handleClearSearchFilters}
					onClose={() => (showFiltersDropdown = false)}
					liveSubStatuses={selectedLiveSubStatuses}
					onLiveSubStatusChange={handleLiveSubStatusChange}
					{liveStatusCounts}
					completedCount={contextualTotal}
				/>
			{/if}
		</div>

		<!-- Mobile Filters Bottom Sheet -->
		{#if isMobile}
			<FiltersBottomSheet
				open={showFiltersDropdown}
				onClose={() => (showFiltersDropdown = false)}
				{scopeSelection}
				onScopeSelectionChange={handleScopeSelectionChange}
				status={selectedStatus}
				onStatusChange={handleStatusChange}
				dateRange={selectedDateRange}
				onDateRangeChange={handleDateRangeChange}
				onReset={handleClearSearchFilters}
				liveSubStatuses={selectedLiveSubStatuses}
				onLiveSubStatusChange={handleLiveSubStatusChange}
				{liveStatusCounts}
				completedCount={contextualTotal}
			/>
		{/if}

		<!-- Project Filter Dropdown -->
		<div class="relative" data-dropdown-container>
			<button
				onclick={() => {
					showProjectDropdown = !showProjectDropdown;
				}}
				disabled={isLoading}
				aria-expanded={showProjectDropdown}
				aria-haspopup="listbox"
				class="inline-flex items-center gap-2 px-3 h-[38px] text-xs font-medium rounded-[6px] hover:border-[var(--border-hover)] transition-all whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed {selectedProject
					? 'bg-[var(--accent-subtle)] border border-[var(--accent)] text-[var(--accent)]'
					: 'bg-[var(--bg-base)] border border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)]'}"
			>
				<FolderOpen
					size={12}
					strokeWidth={2}
					class={selectedProject ? 'text-[var(--accent)]' : 'text-[var(--text-faint)]'}
				/>
				<span>Project:</span>
				<span
					class="max-w-[120px] truncate {selectedProject
						? 'text-[var(--accent)]'
						: 'text-[var(--text-primary)]'}"
				>
					{selectedProject ? getProjectName(selectedProject) : 'All'}
				</span>
				<ChevronDown
					size={12}
					strokeWidth={2}
					class={selectedProject ? 'text-[var(--accent)]' : 'text-[var(--text-faint)]'}
				/>
			</button>
			{#if showProjectDropdown}
				<div
					role="listbox"
					aria-label="Select project"
					use:dropdownNavigation={{ onClose: () => (showProjectDropdown = false) }}
					class="absolute right-0 mt-1 w-64 bg-[var(--bg-base)] border border-[var(--border)] rounded-lg shadow-[var(--shadow-md)] z-10 py-1 max-h-80 overflow-y-auto"
				>
					<button
						role="option"
						aria-selected={selectedProject === ''}
						onclick={() => handleProjectSelect(null)}
						class="w-full px-4 py-1.5 text-left text-xs font-medium hover:bg-[var(--bg-subtle)] data-[highlighted=true]:bg-[var(--bg-muted)] transition-colors {selectedProject ===
						''
							? 'text-[var(--text-primary)] bg-[var(--bg-subtle)]'
							: 'text-[var(--text-secondary)]'}"
					>
						All Projects
					</button>
					<div class="border-t border-[var(--border-subtle)] my-1"></div>
					{#each data.projects as project (project.encoded_name)}
						<button
							role="option"
							aria-selected={selectedProject === project.encoded_name}
							onclick={() => handleProjectSelect(project.encoded_name, project.slug)}
							class="w-full px-4 py-1.5 text-left text-xs font-medium hover:bg-[var(--bg-subtle)] data-[highlighted=true]:bg-[var(--bg-muted)] transition-colors flex items-center justify-between gap-2 {selectedProject ===
							project.encoded_name
								? 'text-[var(--text-primary)] bg-[var(--bg-subtle)]'
								: 'text-[var(--text-secondary)]'}"
						>
							<span class="truncate" title={project.display_name || project.name}
								>{project.display_name || project.name}</span
							>
							<span class="text-[var(--text-faint)] text-[10px] tabular-nums shrink-0"
								>{project.session_count}</span
							>
						</button>
					{/each}
				</div>
			{/if}
		</div>

		<!-- View Mode Toggle -->
		<div
			class="flex items-center gap-1 p-1 h-[38px] bg-[var(--bg-subtle)] rounded-[6px] border border-[var(--border)]"
		>
			<button
				onclick={() => (viewMode = 'list')}
				class="p-1.5 rounded transition-colors {viewMode === 'list'
					? 'bg-[var(--bg-base)] text-[var(--text-primary)] shadow-sm'
					: 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'}"
				title="List view (grouped by date)"
			>
				<List size={16} strokeWidth={2} />
			</button>
			<button
				onclick={() => (viewMode = 'grid')}
				class="p-1.5 rounded transition-colors {viewMode === 'grid'
					? 'bg-[var(--bg-base)] text-[var(--text-primary)] shadow-sm'
					: 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'}"
				title="Grid view (compact)"
			>
				<LayoutGrid size={16} strokeWidth={2} />
			</button>
		</div>

		<!-- Clear Filters Button -->
		{#if hasActiveFilters}
			<button
				onclick={clearAllFilters}
				class="inline-flex items-center gap-1.5 px-3 h-[38px] text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] bg-[var(--bg-base)] border border-[var(--border)] rounded-[6px] hover:bg-[var(--bg-subtle)] hover:border-[var(--border-hover)] transition-all"
			>
				<X size={12} strokeWidth={2} />
				<span>Clear</span>
			</button>
		{/if}
	</div>

	<!-- Active Search Filters (scope, status, date) -->
	{#if hasSearchFilters}
		<ActiveFilterChips
			chips={filterChips}
			onRemove={handleRemoveSearchFilter}
			onClearAll={handleClearSearchFilters}
			totalCount={displayTotalCount}
			filteredCount={displayFilteredCount}
			class="mb-4"
		/>
	{/if}

	<!-- Active Filters Summary - project filter chip -->
	{#if selectedProject}
		<div
			class="mb-4 flex items-center gap-2 text-xs text-[var(--text-muted)] flex-wrap"
			role="status"
			aria-live="polite"
			aria-atomic="true"
		>
			<span>Filtered by</span>
			<button
				onclick={() => handleProjectSelect(null)}
				class="inline-flex items-center gap-1 px-2 py-0.5 bg-[var(--bg-muted)] border border-[var(--border)] rounded font-medium text-[var(--text-secondary)] hover:border-[var(--border-hover)] transition-colors group"
			>
				<FolderOpen size={10} />
				{getProjectName(selectedProject)}
				<X size={10} class="opacity-60 group-hover:opacity-100" />
			</button>
			<!-- Session count -->
			<span
				class="ml-auto text-xs text-[var(--text-muted)] font-mono tabular-nums flex items-center gap-2"
			>
				{displayFilteredCount} of {displayTotalCount} sessions
			</span>
		</div>
	{/if}

	<!-- Active Branches (shown when project is selected, matches projects page UX) -->
	{#if selectedProject && availableBranches.length > 0}
		<ActiveBranches
			branches={availableBranches}
			activeBranches={activeBranchNames}
			selectedBranches={selectedBranchFilters}
			onBranchToggle={handleBranchToggle}
			onClearAll={handleClearAllBranches}
			class="mb-4"
		/>
	{/if}

	<!-- Branch filter chips (when branches are selected but no ActiveBranches component) -->
	{#if selectedBranchFilters.size > 0 && (!selectedProject || availableBranches.length === 0)}
		<div class="mb-4 flex items-center gap-2 flex-wrap">
			{#each [...selectedBranchFilters] as branch}
				<button
					onclick={() => handleBranchToggle(branch)}
					class="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs
						bg-[var(--bg-muted)] text-[var(--text-secondary)] rounded-full
						border border-[var(--border)]
						hover:border-[var(--border-hover)] hover:text-[var(--text-primary)]
						transition-colors group"
				>
					<GitBranch size={10} />
					{branch}
					<X size={10} class="opacity-60 group-hover:opacity-100" />
				</button>
			{/each}
			{#if selectedBranchFilters.size > 1}
				<button
					onclick={handleClearAllBranches}
					class="text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
				>
					Clear branches
				</button>
			{/if}
		</div>
	{/if}

	<!-- Live Sessions Section - only shown when date range includes today -->
	{#if showLiveSessions}
		<LiveSessionsSection
			onSessionsChange={handleLiveSessionsChange}
			searchQuery={searchTokens.join(' ')}
			projectFilter={selectedProject}
			statusFilter={selectedStatus}
			liveSubStatuses={selectedLiveSubStatuses}
			branchFilter={selectedBranchFilters.size > 0 ? selectedBranchFilters : undefined}
			historicalSessions={data.sessions}
		/>
	{/if}

	<!-- Recently Ended Section - shows ended sessions as cards between live and historical -->
	{#if showRecentlyEnded}
		<div class="mb-6">
			<!-- Section Header -->
			<div class="flex items-center gap-2 mb-4">
				<div class="flex items-center gap-2 text-[var(--text-muted)]">
					<Clock size={14} strokeWidth={2} />
					<h2 class="text-sm font-semibold uppercase tracking-wide">Recently Ended</h2>
				</div>
				<span
					class="inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 bg-[var(--bg-muted)] text-[var(--text-secondary)] rounded text-xs font-medium tabular-nums"
				>
					{recentlyEndedSessions.length}
				</span>
				<span class="text-xs text-[var(--text-faint)]"> (within 45 min) </span>
				<!-- Session count - shown on first visible section header -->
				<span class="ml-auto text-xs text-[var(--text-muted)] font-mono tabular-nums">
					{displayFilteredCount} of {displayTotalCount} sessions
				</span>
			</div>

			<!-- Recently Ended Cards Grid - respects view mode -->
			<div
				class={viewMode === 'grid'
					? 'grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2'
					: 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3'}
			>
				{#each recentlyEndedSessions as { session, liveSession } (session.uuid)}
					<GlobalSessionCard {session} {liveSession} compact={viewMode === 'grid'} />
				{/each}
			</div>
		</div>
	{/if}

	<!-- Loading Indicator - Show skeleton cards while loading -->
	{#if isPageLoading}
		<div class="space-y-8" role="status" aria-busy="true" aria-label="Loading sessions...">
			<!-- Skeleton group -->
			<div>
				<div class="flex items-center gap-2 mb-4">
					<div class="h-4 w-16 skeleton-shimmer rounded"></div>
					<div class="h-3 w-8 skeleton-shimmer rounded"></div>
				</div>
				<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
					{#each Array(6) as _}
						<SkeletonGlobalSessionCard />
					{/each}
				</div>
			</div>
		</div>
	{:else if data.error}
		<!-- Error State -->
		<div
			class="p-4 bg-[var(--error-subtle)] border border-[var(--error)]/20 rounded-[var(--radius-md)] text-sm text-[var(--error)]"
		>
			{data.error}
		</div>
	{:else if dedupedFilteredSessions.length === 0 && (!showLiveSessions || currentLiveSessions.filter((s) => s.status !== 'ended').length === 0) && recentlyEndedSessions.length === 0}
		<!-- Empty State - only show when no filtered sessions AND no live sessions AND no recently ended -->
		<EmptyState
			title={activeFiltersCount > 0 || hasSearchFilters
				? 'No matching sessions'
				: 'No sessions yet'}
			description={activeFiltersCount > 0 || hasSearchFilters
				? 'Try adjusting your filters or search term'
				: 'Start a Claude Code session to see it here'}
			icon={MessageSquareText}
		>
			{#if activeFiltersCount > 0 || hasSearchFilters}
				<button
					onclick={clearAllFilters}
					class="mt-4 px-4 py-2 text-sm font-medium bg-[var(--accent)] text-white rounded-[var(--radius-md)] hover:bg-[var(--accent-hover)] transition-colors"
				>
					Clear filters
				</button>
			{/if}
		</EmptyState>
	{:else if dedupedFilteredSessions.length === 0 && !showRecentlyEnded}
		<!-- No filtered sessions but have live ones (not recently ended) - show minimal message -->
		<div class="text-center py-8 text-sm text-[var(--text-muted)]">
			No completed sessions match your filters
		</div>
	{:else if dedupedFilteredSessions.length === 0}
		<!-- No filtered sessions but have recently ended - don't show message (cards are above) -->
	{:else if viewMode === 'list'}
		<!-- List View: Time-Based Grouping -->
		<div class="space-y-8">
			{#each groupedByDate as group, index (group.label)}
				<div>
					<!-- Section Header -->
					<div class="flex items-center gap-2 mb-4">
						<h2
							class="text-sm font-semibold uppercase tracking-wide text-[var(--text-secondary)]"
						>
							{group.label}
							<span class="text-[var(--text-faint)] font-medium ml-1.5">
								({group.sessions.length})
							</span>
						</h2>
						<!-- Session count - shown only on first group if Recently Ended is not visible -->
						{#if index === 0 && !showRecentlyEnded}
							<span
								class="ml-auto text-xs text-[var(--text-muted)] font-mono tabular-nums"
							>
								{displayFilteredCount} of {displayTotalCount} sessions
							</span>
						{/if}
					</div>

					<!-- Session Cards Grid -->
					<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
						{#each group.sessions as session (session.uuid)}
							<GlobalSessionCard {session} liveSession={getLiveSession(session)} />
						{/each}
					</div>
				</div>
			{/each}
		</div>
	{:else}
		<!-- Grid View: Compact with Time-Based Grouping -->
		<div class="space-y-6">
			{#each groupedByDate as group, index (group.label)}
				<div>
					<!-- Section Header -->
					<div class="flex items-center gap-2 mb-3">
						<h2
							class="text-sm font-semibold uppercase tracking-wide text-[var(--text-secondary)]"
						>
							{group.label}
							<span class="text-[var(--text-faint)] font-medium ml-1.5">
								({group.sessions.length})
							</span>
						</h2>
						<!-- Session count - shown only on first group if Recently Ended is not visible -->
						{#if index === 0 && !showRecentlyEnded}
							<span
								class="ml-auto text-xs text-[var(--text-muted)] font-mono tabular-nums"
							>
								{displayFilteredCount} of {displayTotalCount} sessions
							</span>
						{/if}
					</div>

					<!-- Session Cards Grid (Compact) -->
					<div
						class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2"
					>
						{#each group.sessions as session (session.uuid)}
							<GlobalSessionCard
								{session}
								compact
								liveSession={getLiveSession(session)}
							/>
						{/each}
					</div>
				</div>
			{/each}
		</div>
	{/if}

	<!-- Pagination / Results Info -->
	{#if !hasClientSideFilters && !data.error && !isLoading && dedupedFilteredSessions.length > 0}
		<div class="mt-8">
			<Pagination
				total={effectiveTotal}
				page={currentPage}
				perPage={data.filters.perPage}
				{totalPages}
				onPageChange={goToPage}
				itemLabel="sessions"
			/>
		</div>
	{:else if hasClientSideFilters && !data.error && !isLoading && dedupedFilteredSessions.length > 0}
		<div class="mt-8 text-xs text-[var(--text-muted)] tabular-nums">
			Showing <span class="font-medium text-[var(--text-secondary)]"
				>{effectiveTotal.toLocaleString()}</span
			> filtered sessions
		</div>
	{/if}
</div>

<!-- Click outside to close dropdowns -->
<svelte:window
	onclick={(e) => {
		const target = e.target as HTMLElement;
		// Close dropdowns when clicking outside of dropdown containers
		if (!target.closest('[data-dropdown-container]')) {
			showProjectDropdown = false;
		}
	}}
/>
