<script lang="ts">
	import { browser } from '$app/environment';
	import { goto, replaceState } from '$app/navigation';
	import { page } from '$app/stores';
	import { Tabs } from 'bits-ui';
	import {
		FolderOpen,
		GitBranch,
		MessageSquare,
		Search,
		Bot,
		Wrench,
		Cable,
		LayoutDashboard,
		BarChart3,
		Layers,
		Cpu,
		DollarSign,
		Percent,
		Clock,
		PieChart,
		Briefcase,
		X,
		Archive,
		LayoutGrid,
		List,
		Brain
	} from 'lucide-svelte';
	import { isToday, isYesterday, isThisWeek, isThisMonth } from 'date-fns';
	import TabsTrigger from '$lib/components/ui/TabsTrigger.svelte';
	import { API_BASE } from '$lib/config';
	import { ProjectDetailSkeleton, SkeletonSessionCard } from '$lib/components/skeleton';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import SessionCard from '$lib/components/SessionCard.svelte';
	import ArchivedSessionCard from '$lib/components/ArchivedSessionCard.svelte';
	import AgentList from '$lib/components/agents/AgentList.svelte';
	import SkillList from '$lib/components/skills/SkillList.svelte';
	import ToolList from '$lib/components/tools/ToolList.svelte';
	import MemoryViewer from '$lib/components/memory/MemoryViewer.svelte';
	import StatsGrid from '$lib/components/StatsGrid.svelte';
	import ActiveBranches from '$lib/components/ActiveBranches.svelte';
	import Pagination from '$lib/components/Pagination.svelte';
	import { SessionsChart } from '$lib/components/charts/index';
	import TimeFilterDropdown from '$lib/components/TimeFilterDropdown.svelte';
	import TokenSearchInput from '$lib/components/TokenSearchInput.svelte';
	import FiltersDropdown from '$lib/components/FiltersDropdown.svelte';
	import FiltersBottomSheet from '$lib/components/FiltersBottomSheet.svelte';
	import ActiveFilterChips from '$lib/components/ActiveFilterChips.svelte';
	import LiveSessionsSection from '$lib/components/LiveSessionsSection.svelte';
	import type {
		Project,
		BranchesData,
		ProjectAnalytics,
		ProjectArchivedResponse,
		SessionSummary,
		StatItem,
		AnalyticsFilterPeriod,
		LiveSessionSummary,
		SearchFilters,
		SearchScopeSelection,
		LiveSubStatus,
		LiveStatusCounts
	} from '$lib/api-types';
	import { ALL_LIVE_SUB_STATUSES } from '$lib/api-types';
	import {
		formatDuration,
		formatTokens,
		formatCost,
		getProjectName,
		analyticsFilterOptions,
		getTimestampRangeForFilter,
		getAnalyticsFilterLabel
	} from '$lib/utils';
	import {
		DEFAULT_FILTERS,
		DEFAULT_SCOPE_SELECTION,
		getFilterChips,
		hasActiveFilters as checkHasActiveFilters,
		getDateRangeTimestamps,
		scopeSelectionToApi,
		apiToScopeSelection,
		restoreAllFiltersFromUrl,
		buildFilterUrlParams,
		filterSessionsByTokens,
		filterSessionsByStatus,
		filterSessionsByDateRange,
		filterSessionsByBranch,
		filterSessionsBySource,
		createLiveSessionLookup,
		calculateLiveStatusCounts,
		createHistoricalSessionLookup,
		shouldShowEndedStatus,
		paramToTokens,
		tokensToParam
	} from '$lib/search';

	// ==========================================================================
	// Time Filter Logic
	// ==========================================================================

	// Read filter from URL
	let selectedFilter = $derived.by((): AnalyticsFilterPeriod => {
		const filterParam = $page.url.searchParams.get('filter');
		if (filterParam && analyticsFilterOptions.some((o) => o.id === filterParam)) {
			return filterParam as AnalyticsFilterPeriod;
		}
		return 'all';
	});

	const handleFilterChange = (filter: AnalyticsFilterPeriod) => {
		const url = new URL($page.url);
		const range = getTimestampRangeForFilter(filter);

		// Always include timezone offset for accurate local date grouping
		if (browser) {
			url.searchParams.set('tz_offset', new Date().getTimezoneOffset().toString());
		}

		if (filter === 'all') {
			url.searchParams.delete('filter');
			url.searchParams.delete('start_ts');
			url.searchParams.delete('end_ts');
		} else {
			url.searchParams.set('filter', filter);
			if (range) {
				url.searchParams.set('start_ts', range.start.toString());
				url.searchParams.set('end_ts', range.end.toString());
			}
		}

		// Preserve the current active tab in URL
		if (activeTab !== 'overview') {
			url.searchParams.set('tab', activeTab);
		}

		goto(url.toString(), { replaceState: true, keepFocus: true });
	};

	// ==========================================================================
	// Page Data and State
	// ==========================================================================
	import { onMount, onDestroy } from 'svelte';

	let { data } = $props();
	let project = $derived(data.project as Project);
	let branchesData = $derived(data.branches as BranchesData);
	let archived = $derived(data.archived as ProjectArchivedResponse);

	// Analytics state - fetched client-side on-demand
	let analytics = $state<ProjectAnalytics | null>(null);
	let analyticsLoading = $state(false);
	let analyticsError = $state(false);
	let lastAnalyticsFilter = $state<string | null>(null); // Track filter to detect changes

	// ==========================================================================
	// Pagination State (basic params - filter-dependent logic defined later)
	// ==========================================================================

	// Pagination params from server loader
	const paginationPage = $derived(data.pagination?.page ?? 1);
	const paginationPerPage = $derived(data.pagination?.perPage ?? 50);

	// Total sessions count (before pagination) - used for calculating total pages
	const totalSessionCount = $derived(project?.session_count ?? 0);

	// Pagination calculations
	const totalPages = $derived(Math.ceil(totalSessionCount / paginationPerPage) || 1);
	const currentPage = $derived(paginationPage);
	const hasNextPage = $derived(currentPage < totalPages);
	const hasPrevPage = $derived(currentPage > 1);

	// ==========================================================================
	// Lazy-loaded full session list for filtering
	// ==========================================================================
	// When paginated, we only have a subset of sessions. When user activates
	// filters, we need ALL sessions to filter correctly. This state holds
	// the full list once fetched.
	let allSessionsLoaded = $state(false);
	let allSessions = $state<SessionSummary[] | null>(null);
	let isLoadingAllSessions = $state(false);

	// Server-side search state
	let serverSearchResults = $state<SessionSummary[] | null>(null);
	let isServerSearching = $state(false);
	let lastServerSearchQuery = $state('');
	let searchDebounceTimer: ReturnType<typeof setTimeout> | null = null;
	const isListLoading = $derived(isLoadingAllSessions || isServerSearching);

	// Determine if we're in paginated mode (some sessions not loaded)
	const isPaginated = $derived(totalSessionCount > (project?.sessions?.length ?? 0));

	// The sessions to use for filtering:
	// 1. Server search results (when searching by text)
	// 2. All sessions (when non-search filters are active)
	// 3. Paginated subset (default)
	const sessionsForFiltering = $derived(
		serverSearchResults !== null
			? serverSearchResults
			: allSessionsLoaded && allSessions
				? allSessions
				: (project?.sessions ?? [])
	);

	// Fetch all sessions when filters are activated and we're paginated
	async function ensureAllSessionsLoaded() {
		if (!browser || !project || !isPaginated || allSessionsLoaded || isLoadingAllSessions) {
			return;
		}

		isLoadingAllSessions = true;
		try {
			// Fetch all sessions by removing pagination limit
			// The API caps per_page at 200, so use no limit by setting a high value
			const res = await fetch(
				`${API_BASE}/projects/${project.encoded_name}?per_page=200&page=1`
			);
			if (res.ok) {
				const fullProject = await res.json();
				let loaded: SessionSummary[] = fullProject.sessions ?? [];
				// If there are more sessions than returned, fetch remaining pages
				const totalCount = fullProject.session_count ?? 0;
				if (totalCount > loaded.length) {
					const totalPages = Math.ceil(totalCount / 200);
					const promises = [];
					for (let p = 2; p <= totalPages; p++) {
						promises.push(
							fetch(
								`${API_BASE}/projects/${project.encoded_name}?per_page=200&page=${p}`
							).then((r) => (r.ok ? r.json() : null))
						);
					}
					const results = await Promise.all(promises);
					for (const result of results) {
						if (result?.sessions) {
							loaded = [...loaded, ...result.sessions];
						}
					}
				}
				allSessions = loaded;
				allSessionsLoaded = true;
			}
		} catch (e) {
			console.error('Failed to load all sessions for filtering:', e);
		} finally {
			isLoadingAllSessions = false;
		}
	}

	// Server-side search: fetch filtered sessions from API
	async function serverSearch(query: string) {
		if (!browser || !project) return;

		// Clear results if query is empty
		if (!query.trim()) {
			serverSearchResults = null;
			lastServerSearchQuery = '';
			return;
		}

		// Skip if same query
		if (query === lastServerSearchQuery) return;

		isServerSearching = true;
		try {
			const params = new URLSearchParams({
				search: query,
				per_page: '200'
			});
			const res = await fetch(`${API_BASE}/projects/${project.encoded_name}?${params}`);
			if (res.ok) {
				const data = await res.json();
				serverSearchResults = data.sessions ?? [];
				lastServerSearchQuery = query;
			}
		} catch (e) {
			console.error('Failed to search sessions:', e);
		} finally {
			isServerSearching = false;
		}
	}

	function debouncedServerSearch(query: string) {
		if (searchDebounceTimer) clearTimeout(searchDebounceTimer);
		searchDebounceTimer = setTimeout(() => serverSearch(query), 200);
	}

	// Track last project to detect navigation between projects
	let lastProjectEncodedName = $state<string | null>(null);

	// Reset all-sessions cache AND analytics ONLY when project actually changes
	$effect(() => {
		const currentName = project?.encoded_name ?? null;
		if (currentName && lastProjectEncodedName && currentName !== lastProjectEncodedName) {
			// Navigated to a different project - reset cache
			allSessionsLoaded = false;
			allSessions = null;
			analytics = null;
			analyticsLoading = false;
			analyticsError = false;
			serverSearchResults = null;
			lastServerSearchQuery = '';
		}
		lastProjectEncodedName = currentName;
	});

	// Tab state - initialize from URL immediately (not deferred to onMount)
	const validTabs = ['overview', 'analytics', 'agents', 'skills', 'tools', 'memory', 'archived'];
	const initialTab = $page.url.searchParams.get('tab');
	let activeTab = $state(initialTab && validTabs.includes(initialTab) ? initialTab : 'overview');
	let tabsReady = $state(false);

	// Fetch analytics client-side when analytics tab is activated
	async function fetchAnalytics() {
		if (!browser || !project || analyticsLoading || analytics) return;

		analyticsLoading = true;
		analyticsError = false;

		try {
			// Build analytics URL with timestamp params from server
			const analyticsParams = new URLSearchParams();
			const urlParams = data.analyticsUrlParams;

			if (urlParams?.startTs) analyticsParams.set('start_ts', urlParams.startTs);
			if (urlParams?.endTs) analyticsParams.set('end_ts', urlParams.endTs);
			if (urlParams?.tzOffset) analyticsParams.set('tz_offset', urlParams.tzOffset);

			const analyticsUrl = analyticsParams.toString()
				? `${API_BASE}/analytics/projects/${project.encoded_name}?${analyticsParams}`
				: `${API_BASE}/analytics/projects/${project.encoded_name}`;

			const res = await fetch(analyticsUrl);
			if (res.ok) {
				analytics = await res.json();
			} else {
				analyticsError = true;
			}
		} catch (e) {
			console.error('Failed to fetch analytics:', e);
			analyticsError = true;
		} finally {
			analyticsLoading = false;
		}
	}

	// Trigger analytics fetch when analytics tab becomes active
	$effect(() => {
		if (activeTab === 'analytics' && !analytics && !analyticsLoading) {
			fetchAnalytics();
		}
	});

	// Restore all filter + UI state from URL params (uses shared utility)
	function restoreFiltersFromUrl(params: URLSearchParams) {
		const restored = restoreAllFiltersFromUrl(params);

		// Restore search tokens
		searchTokens = restored.tokens;
		if (restored.tokens.length > 0) {
			// Trigger server search to populate results
			debouncedServerSearch(restored.tokens.join(' '));
		}

		// Restore core filters
		filters.status = restored.status;
		filters.dateRange = restored.dateRange;
		filters.customStart = restored.customStart;
		filters.customEnd = restored.customEnd;

		// Restore scope selection
		scopeSelection = apiToScopeSelection(restored.scope);

		// Restore live sub-statuses
		if (restored.liveSubStatuses && restored.liveSubStatuses.length > 0) {
			selectedLiveSubStatuses = restored.liveSubStatuses;
		} else {
			selectedLiveSubStatuses = [...ALL_LIVE_SUB_STATUSES];
		}

		// Restore branch filters
		selectedBranchFilters = restored.branches;

		// If any non-search filters are active, ensure all sessions are loaded for accurate filtering
		if (
			restored.status !== 'all' ||
			restored.dateRange !== 'all' ||
			selectedBranchFilters.size > 0
		) {
			ensureAllSessionsLoaded();
		}
	}

	// Initialize tab and all filters from URL, add popstate handler for browser back/forward
	onMount(() => {
		const params = new URLSearchParams(window.location.search);
		const tabParam = params.get('tab');
		if (tabParam && validTabs.includes(tabParam)) {
			activeTab = tabParam;
		}

		// Restore all filter state from URL
		restoreFiltersFromUrl(params);

		tabsReady = true;
		// Mark filters as ready AFTER restoration so the URL sync effect doesn't fire prematurely
		filtersReady = true;

		// Handle browser back/forward navigation
		const handlePopState = () => {
			const params = new URLSearchParams(window.location.search);
			const tabParam = params.get('tab');
			if (tabParam && validTabs.includes(tabParam)) {
				activeTab = tabParam;
			} else {
				activeTab = 'overview';
			}
			// Restore all filter state from URL on back/forward
			restoreFiltersFromUrl(params);
		};

		window.addEventListener('popstate', handlePopState);
		return () => window.removeEventListener('popstate', handlePopState);
	});

	// NOTE: Tab URL sync is consolidated into the unified URL sync effect below (L617+)
	// to prevent race conditions between two effects both calling replaceState().

	// Refetch analytics when filter changes (on analytics tab)
	$effect(() => {
		if (!browser || activeTab !== 'analytics') return;

		// Only reset analytics when filter actually changes
		const filterParam = $page.url.searchParams.get('filter') || 'all';
		if (lastAnalyticsFilter !== null && filterParam !== lastAnalyticsFilter) {
			analytics = null;
			analyticsLoading = false; // Reset loading state to allow new fetch
		}
		lastAnalyticsFilter = filterParam;
	});

	// ==========================================================================
	// Live Session State (matching sessions page pattern)
	// ==========================================================================

	// Track live sessions from the LiveSessionsSection component (for deduplication)
	let currentLiveSessions = $state<LiveSessionSummary[]>([]);

	// Reactive copy of server-loaded live sessions (props are not reactive when mutated)
	// svelte-ignore state_referenced_locally
	let liveSessions = $state<LiveSessionSummary[]>(data.liveSessions ?? []);

	// Sync from props on navigation (project changes trigger new server load)
	$effect(() => {
		liveSessions = data.liveSessions ?? [];
	});

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

	// Unified live session lookup using shared utility (slug-first strategy)
	const getLiveSessionFn = $derived(createLiveSessionLookup(liveSessions));

	// Wrapper function for components that need function reference
	function getLiveSession(session: SessionSummary): LiveSessionSummary | null {
		return getLiveSessionFn(session);
	}

	// Unified historical session lookup using shared utility
	// Uses sessionsForFiltering for access to all sessions when lazy-loaded
	const getHistoricalSessionFn = $derived(
		sessionsForFiltering.length > 0
			? createHistoricalSessionLookup(sessionsForFiltering)
			: () => null
	);

	// Helper to find historical session for a live session (reverse lookup)
	function getHistoricalSession(liveSession: LiveSessionSummary): SessionSummary | null {
		return getHistoricalSessionFn(liveSession);
	}

	// Handle live sessions updates from the LiveSessionsSection
	function handleLiveSessionsChange(sessions: LiveSessionSummary[]) {
		currentLiveSessions = sessions;
	}

	// 30s poll to refresh liveSessions (for Recently Ended + card overlays)
	// Matches sessions page pattern: LiveSessionsSection handles fast 3s polling for LIVE NOW,
	// this slower poll refreshes ended session data for card overlays
	$effect(() => {
		if (!browser || !project?.encoded_name) return;

		const encodedName = project.encoded_name;
		let cancelled = false;
		let isFetching = false;

		const interval = setInterval(async () => {
			if (cancelled || isFetching) return;
			isFetching = true;
			try {
				const res = await fetch(`${API_BASE}/live-sessions/project/${encodedName}`);
				if (!cancelled && res.ok) {
					liveSessions = await res.json();
				}
			} catch {
				/* ignore polling errors */
			} finally {
				isFetching = false;
			}
		}, 30000);

		return () => {
			cancelled = true;
			clearInterval(interval);
		};
	});

	// ==========================================================================
	// Filter state for sessions on Overview tab
	// ==========================================================================
	let filters = $state<SearchFilters>({ ...DEFAULT_FILTERS });
	let scopeSelection = $state<SearchScopeSelection>({ ...DEFAULT_SCOPE_SELECTION });
	let selectedLiveSubStatuses = $state<LiveSubStatus[]>([...ALL_LIVE_SUB_STATUSES]);
	let showFiltersDropdown = $state(false);
	let isMobile = $state(false);
	let selectedBranchFilters = $state<Set<string>>(new Set());

	// Token-based search state
	let searchTokens = $state<string[]>([]);
	let resultsAnimationKey = $state(0); // Trigger animation on token changes

	// Track whether filter URL sync is initialized (prevent overwriting URL before reading it)
	let filtersReady = $state(false);

	// Unified URL sync: tab + filters + branches in a single effect to prevent race conditions.
	// Both tab and filter state are serialized together so replaceState is only called once.
	$effect(() => {
		if (!browser || !tabsReady || !filtersReady) return;

		const url = buildFilterUrlParams(window.location.href, {
			filters: {
				query: '',
				tokens: searchTokens,
				scope: scopeSelectionToApi(scopeSelection),
				status: filters.status,
				dateRange: filters.dateRange,
				customStart: filters.customStart,
				customEnd: filters.customEnd,
				liveSubStatuses: selectedLiveSubStatuses
			},
			branches: selectedBranchFilters,
			tab: activeTab,
			defaultTab: 'overview',
			// Clear analytics-specific params when not on analytics tab
			clearKeys: activeTab !== 'analytics' ? ['filter', 'start_ts', 'end_ts'] : undefined
		});

		// Single replaceState call for all URL state — synchronous to avoid UI/URL lag
		try {
			replaceState(url.toString(), {});
		} catch {
			// Router may not be initialized yet during SSR/hydration
		}
	});

	// Computed: live status counts using shared utility
	// Uses currentLiveSessions (3s poll via LiveSessionsSection) to stay in sync with LIVE NOW panel
	let liveStatusCounts = $derived(calculateLiveStatusCounts(currentLiveSessions));

	// Computed: count of completed (historical) sessions
	// Use totalSessionCount (from project.session_count) instead of project.sessions.length
	// to account for pagination - we want the total across all pages, not just current page
	let completedCount = $derived(Math.max(0, totalSessionCount - liveStatusCounts.total));

	// Display-aware total that matches the current status filter context
	// Prevents nonsensical "X of Y" when Y doesn't match the filtered category
	let displayTotalCount = $derived.by(() => {
		if (filters.status === 'live') {
			return liveStatusCounts.total;
		} else if (filters.status === 'completed') {
			return Math.max(0, totalSessionCount - liveStatusCounts.total);
		} else {
			return totalSessionCount;
		}
	});

	// Computed: recently ended sessions for the "Recently Ended" card section
	// These are ended sessions within 45-min timeout, with filters applied, matched to historical data
	let recentlyEndedSessions = $derived.by(() => {
		// Don't show when status is 'completed' (only historical)
		if (filters.status === 'completed') return [];

		// Get ended sessions within 45-min timeout (from reactive liveSessions, refreshed by 30s poll)
		// No project filter needed: liveSessions already scoped to this project via /live-sessions/project/{slug} API
		let endedLive = liveSessions.filter(
			(s) => s.status === 'ended' && shouldShowEndedStatus(s.updated_at)
		);

		// Apply live sub-status filter (must include 'ended')
		if (!selectedLiveSubStatuses.includes('ended')) {
			return [];
		}

		// Apply branch filter (if a branch is selected)
		if (selectedBranchFilters.size > 0) {
			// Can't filter live sessions by branch directly - they don't have branch info
			// So we'll filter by matching to historical sessions that have the branch
			endedLive = endedLive.filter((ls) => {
				const historical = getHistoricalSession(ls);
				if (!historical) return false;
				return historical.git_branches?.some((b) => selectedBranchFilters.has(b)) ?? false;
			});
		}

		// Apply search filter (tokens or query)
		if (searchTokens.length > 0) {
			// Token-based search: match against historical session data
			endedLive = endedLive.filter((ls) => {
				const historical = getHistoricalSession(ls);
				if (!historical) return false;
				const matches = filterSessionsByTokens([historical], searchTokens, scopeSelection);
				return matches.length > 0;
			});
		}

		// Match to historical sessions and create pairs for rendering
		const pairs: { session: SessionSummary; liveSession: LiveSessionSummary }[] = [];
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

	// Check if Recently Ended section should be visible
	let showRecentlyEnded = $derived(
		filters.status !== 'completed' && recentlyEndedSessions.length > 0
	);

	// Detect mobile viewport
	$effect(() => {
		if (!browser) return;
		const checkMobile = () => {
			isMobile = window.innerWidth < 640;
		};
		checkMobile();
		window.addEventListener('resize', checkMobile);
		return () => window.removeEventListener('resize', checkMobile);
	});

	// Derived filter state - sync scope selection to filters for chip generation
	let filtersWithScope = $derived({
		...filters,
		scope: scopeSelectionToApi(scopeSelection)
	});
	let filterChips = $derived(getFilterChips(filtersWithScope));
	let hasActiveFilters = $derived(
		checkHasActiveFilters(filtersWithScope) || !scopeSelection.titles || !scopeSelection.prompts
	);
	let activeFilterCount = $derived(filterChips.length);

	function handleTokensChange(tokens: string[]) {
		searchTokens = tokens;
		// Trigger animation when tokens change
		resultsAnimationKey++;
		// Use server-side search for text queries
		if (tokens.length > 0) {
			debouncedServerSearch(tokens.join(' '));
		} else {
			// Clear server search results when tokens are cleared
			serverSearchResults = null;
			lastServerSearchQuery = '';
		}
	}

	function handleScopeSelectionChange(selection: SearchScopeSelection) {
		scopeSelection = selection;
	}

	function handleStatusChange(status: SearchFilters['status']) {
		filters.status = status;
		// When filtering by status (completed or live), ensure all sessions are loaded
		// to get accurate counts across all pages
		if (status !== 'all') {
			ensureAllSessionsLoaded();
		}
	}

	function handleDateRangeChange(range: SearchFilters['dateRange']) {
		filters.dateRange = range;
	}

	function handleSourceChange(source: SearchFilters['source']) {
		filters.source = source;
	}

	function handleLiveSubStatusChange(statuses: LiveSubStatus[]) {
		selectedLiveSubStatuses = statuses;
	}

	function handleRemoveFilter(key: keyof SearchFilters) {
		if (key === 'scope') {
			// Reset scope selection to default (both checked)
			scopeSelection = { ...DEFAULT_SCOPE_SELECTION };
		}
		filters = { ...filters, [key]: DEFAULT_FILTERS[key] };
	}

	function handleClearAllFilters() {
		filters = { ...DEFAULT_FILTERS };
		scopeSelection = { ...DEFAULT_SCOPE_SELECTION };
		selectedLiveSubStatuses = [...ALL_LIVE_SUB_STATUSES];
		selectedBranchFilters = new Set();
		searchTokens = [];
		serverSearchResults = null;
		lastServerSearchQuery = '';
	}

	function handleBranchToggle(branch: string) {
		const newSet = new Set(selectedBranchFilters);
		if (newSet.has(branch)) {
			newSet.delete(branch);
		} else {
			newSet.add(branch);
		}
		selectedBranchFilters = newSet;

		// Ensure all sessions are loaded only when filters are active
		if (newSet.size > 0) {
			ensureAllSessionsLoaded();
		}
	}

	function handleClearAllBranches() {
		selectedBranchFilters = new Set();
	}

	// Stats for overview tab - grouped by semantic meaning
	// Activity (blue), Resources (teal), Time (orange), Financial (purple/accent)
	let overviewStats = $derived.by<StatItem[]>(() => {
		if (!project) return [];
		if (!analytics) {
			return [
				{ title: 'Sessions', value: project.session_count, icon: Layers, color: 'blue' },
				{ title: 'Agents', value: project.agent_count, icon: Bot, color: 'green' }
			];
		}
		return [
			{ title: 'Sessions', value: analytics.total_sessions, icon: Layers, color: 'blue' },
			{
				title: 'Total Tokens',
				value: formatTokens(analytics.total_tokens),
				icon: Cpu,
				color: 'teal',
				tokenIn: analytics.total_input_tokens,
				tokenOut: analytics.total_output_tokens
			},
			{
				title: 'Total Duration',
				value: formatDuration(analytics.total_duration_seconds),
				icon: Clock,
				color: 'orange'
			},
			{
				title: 'Estimated Cost',
				value: formatCost(analytics.estimated_cost_usd),
				icon: DollarSign,
				color: 'purple'
			},
			{
				title: 'Cache Hit Rate',
				value: `${(analytics.cache_hit_rate * 100).toFixed(1)}%`,
				icon: Percent,
				color: 'accent'
			}
		];
	});

	// Filtered sessions count - applies user filters only (for "X of Y" display)
	// Does NOT exclude sessions shown in special sections (live, recently ended)
	// Uses sessionsForFiltering which may be the full list if lazy-loaded
	let filteredSessionsCount = $derived.by(() => {
		if (sessionsForFiltering.length === 0) return 0;
		let sessions = [...sessionsForFiltering];

		// Filter by selected branches using shared utility
		sessions = filterSessionsByBranch(sessions, selectedBranchFilters);

		// Filter by search tokens using shared utility
		if (searchTokens.length > 0) {
			sessions = filterSessionsByTokens(sessions, searchTokens, scopeSelection);
		}

		// Filter by status using shared utility (unified behavior)
		sessions = filterSessionsByStatus(
			sessions,
			filters.status,
			getLiveSessionFn,
			selectedLiveSubStatuses
		);

		// Filter by date range using shared utility
		sessions = filterSessionsByDateRange(
			sessions,
			filters.dateRange,
			filters.customStart,
			filters.customEnd
		);

		// Filter by source (local vs remote)
		sessions = filterSessionsBySource(sessions, filters.source || 'all');

		return sessions.length;
	});

	// ==========================================================================
	// Pagination Logic (filter-dependent)
	// ==========================================================================

	// Check if client-side filters are active (disables pagination)
	// When active, we're filtering the paginated subset so pagination doesn't make sense
	const hasClientSideFilters = $derived(
		searchTokens.length > 0 ||
			scopeSelectionToApi(scopeSelection) !== 'both' ||
			filters.status !== 'all' ||
			selectedBranchFilters.size > 0 ||
			(filters.source !== undefined && filters.source !== 'all')
	);

	// Clear server search results when search tokens are removed.
	// NOTE: We intentionally do NOT reset allSessions/allSessionsLoaded when filters
	// are cleared. The cached full session list is harmless to keep and avoids an
	// expensive flash where sessionsForFiltering briefly reverts to the paginated
	// subset, triggering re-computation of all derived values (filteredSessions,
	// groupedByDate, etc.). The paginated view still works correctly because
	// sessionsForFiltering falls through to allSessions → project.sessions.
	$effect(() => {
		if (!hasClientSideFilters) {
			if (serverSearchResults !== null) {
				serverSearchResults = null;
				lastServerSearchQuery = '';
			}
		}
	});

	// Navigate to a specific page
	function goToPage(pageNum: number) {
		if (hasClientSideFilters) return;
		if (pageNum < 1 || pageNum > totalPages) return;

		const url = new URL($page.url);
		url.searchParams.set('page', pageNum.toString());
		url.searchParams.set('per_page', paginationPerPage.toString());
		goto(url.toString(), { replaceState: false, keepFocus: true });
	}

	// Filtered sessions for Overview tab using shared utilities
	// This is for DISPLAY - excludes sessions shown in special sections to avoid duplicates
	// Uses sessionsForFiltering which may be the full list if lazy-loaded
	let filteredSessions = $derived.by(() => {
		if (sessionsForFiltering.length === 0) return [];

		// Prevent showing partial results while loading
		// if ((isLoadingAllSessions && isPaginated) || isServerSearching) {
		// 	return [];
		// }

		let sessions = [...sessionsForFiltering];

		// Filter by selected branches using shared utility
		sessions = filterSessionsByBranch(sessions, selectedBranchFilters);

		// Filter by search tokens using shared utility
		if (searchTokens.length > 0) {
			sessions = filterSessionsByTokens(sessions, searchTokens, scopeSelection);
		}

		// Filter by status using shared utility (unified behavior)
		sessions = filterSessionsByStatus(
			sessions,
			filters.status,
			getLiveSessionFn,
			selectedLiveSubStatuses
		);

		// Filter by date range using shared utility
		sessions = filterSessionsByDateRange(
			sessions,
			filters.dateRange,
			filters.customStart,
			filters.customEnd
		);

		// Filter by source (local vs remote)
		sessions = filterSessionsBySource(sessions, filters.source || 'all');

		// Exclude sessions that appear in the "Recently Ended" section to avoid duplicates
		const recentlyEndedUuids = new Set(recentlyEndedSessions.map((pair) => pair.session.uuid));
		sessions = sessions.filter((s) => !recentlyEndedUuids.has(s.uuid));

		// Exclude sessions shown in LIVE NOW section (identity-based, matching sessions page)
		sessions = sessions.filter((s) => {
			if (s.slug && liveSessionIdentifiers.has(s.slug)) return false;
			if (liveSessionIdentifiers.has(s.uuid)) return false;
			return true;
		});

		return sessions.sort(
			(a, b) => new Date(b.start_time).getTime() - new Date(a.start_time).getTime()
		);
	});

	// ==========================================================================
	// View Mode and Time-Based Grouping
	// ==========================================================================

	// View mode: 'list' (time-grouped) or 'grid' (compact flat)
	let viewMode = $state<'list' | 'grid'>('list');
	let viewModeInitialized = $state(false);

	// Initialize from localStorage on mount (client-side only)
	$effect(() => {
		if (browser && !viewModeInitialized) {
			const saved = localStorage.getItem('claude-code-karma-project-sessions-view-mode');
			if (saved === 'list' || saved === 'grid') {
				viewMode = saved;
			}
			viewModeInitialized = true;
		}
	});

	// Persist view mode changes
	$effect(() => {
		if (browser && viewModeInitialized) {
			localStorage.setItem('claude-code-karma-project-sessions-view-mode', viewMode);
		}
	});

	// Time-based grouping for list view
	type DateGroup = {
		label: string;
		sessions: SessionSummary[];
	};

	const groupedByDate = $derived.by(() => {
		const today: SessionSummary[] = [];
		const yesterday: SessionSummary[] = [];
		const thisWeek: SessionSummary[] = [];
		const thisMonth: SessionSummary[] = [];
		const older: SessionSummary[] = [];

		for (const session of filteredSessions) {
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
</script>

{#if !project}
	<EmptyState
		icon={FolderOpen}
		title="Project not found"
		description="The project you're looking for doesn't exist or couldn't be loaded."
	>
		<a
			href="/projects"
			class="text-sm text-[var(--accent)] hover:text-[var(--accent-hover)] transition-colors"
		>
			Back to Projects
		</a>
	</EmptyState>
{:else}
	<div>
		<!-- Page Header with Breadcrumb -->
		<PageHeader
			title={project.display_name}
			icon={project.is_git_repository ? GitBranch : FolderOpen}
			iconColor={project.is_git_repository ? '--nav-green' : undefined}
			breadcrumbs={[
				{ label: 'Dashboard', href: '/' },
				{ label: 'Projects', href: '/projects' },
				{ label: project.display_name }
			]}
			subtitle={project.path}
		/>

		<!-- Tab Navigation using Bits UI -->
		{#if tabsReady}
			<Tabs.Root bind:value={activeTab} class="space-y-6">
				<Tabs.List
					class="flex items-center gap-1 p-1 bg-[var(--bg-subtle)] rounded-lg w-fit mx-auto border border-[var(--border)]"
				>
					<TabsTrigger value="overview" icon={LayoutDashboard}>Overview</TabsTrigger>
					<TabsTrigger value="agents" icon={Bot}>Project Agents</TabsTrigger>
					<TabsTrigger value="skills" icon={Wrench}>Project Skills</TabsTrigger>
					<TabsTrigger value="tools" icon={Cable}>Project Tools</TabsTrigger>
					<TabsTrigger value="memory" icon={Brain}>Project Memory</TabsTrigger>
					<TabsTrigger value="analytics" icon={BarChart3}>Analytics</TabsTrigger>
					{#if archived.total_sessions > 0}
						<TabsTrigger value="archived" icon={Archive}>
							Archived ({archived.total_sessions})
						</TabsTrigger>
					{/if}
				</Tabs.List>

				<!-- Overview Tab -->
				<Tabs.Content value="overview" class="space-y-6 animate-fade-in">
					<!-- Active Branches (for git projects) - now with filter functionality -->
					{#if project.is_git_repository && branchesData?.branches?.length > 0}
						<ActiveBranches
							branches={branchesData.branches}
							activeBranches={branchesData.active_branches}
							selectedBranches={selectedBranchFilters}
							onBranchToggle={handleBranchToggle}
							onClearAll={handleClearAllBranches}
							isLoading={isLoadingAllSessions}
						/>
					{/if}

					<!-- Sessions Section -->
					<div class="space-y-4">
						<!-- Header row: title + count + view toggle -->
						<div class="flex items-center justify-between">
							<h2 class="text-sm font-semibold text-[var(--text-primary)]">
								Recent Sessions
							</h2>
							<div class="flex items-center gap-3">
								<span
									class="text-xs text-[var(--text-muted)] font-mono tabular-nums flex items-center gap-2"
								>
									{#if isLoadingAllSessions || isServerSearching}
										<span
											class="inline-block w-3 h-3 border-2 border-[var(--accent)]/30 border-t-[var(--accent)] rounded-full animate-spin"
										></span>
									{/if}
									{#if hasClientSideFilters}
										{filteredSessionsCount} filtered sessions
									{:else}
										{filteredSessionsCount} of {displayTotalCount} sessions
									{/if}
								</span>
								<!-- View Mode Toggle -->
								<div
									class="flex items-center gap-1 p-1 bg-[var(--bg-subtle)] rounded-[6px] border border-[var(--border)]"
									role="group"
									aria-label="View mode"
								>
									<button
										onclick={() => (viewMode = 'list')}
										class="p-1.5 rounded transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:ring-offset-2 {viewMode ===
										'list'
											? 'bg-[var(--bg-base)] text-[var(--text-primary)] shadow-sm'
											: 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'}"
										aria-label="List view (grouped by date)"
										aria-pressed={viewMode === 'list'}
									>
										<List size={16} strokeWidth={2} />
									</button>
									<button
										onclick={() => (viewMode = 'grid')}
										class="p-1.5 rounded transition-colors focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:ring-offset-2 {viewMode ===
										'grid'
											? 'bg-[var(--bg-base)] text-[var(--text-primary)] shadow-sm'
											: 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'}"
										aria-label="Grid view (compact)"
										aria-pressed={viewMode === 'grid'}
									>
										<LayoutGrid size={16} strokeWidth={2} />
									</button>
								</div>
							</div>
						</div>

						<!-- Search & Filters -->
						<div class="space-y-3">
							<!-- Token Search Input with Filters Button -->
							<div class="relative flex gap-2">
								<TokenSearchInput
									tokens={searchTokens}
									onTokensChange={handleTokensChange}
									placeholder="Search titles, prompts, or slugs..."
									class="flex-1"
									isLoading={isLoadingAllSessions || isServerSearching}
								/>

								<!-- Filters Button -->
								<button
									onclick={() => (showFiltersDropdown = !showFiltersDropdown)}
									class="inline-flex items-center gap-2 px-3 h-[38px] text-xs font-medium rounded-lg hover:border-[var(--border-hover)] transition-all whitespace-nowrap {hasActiveFilters
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
										status={filters.status}
										onStatusChange={handleStatusChange}
										dateRange={filters.dateRange}
										onDateRangeChange={handleDateRangeChange}
										onReset={handleClearAllFilters}
										onClose={() => (showFiltersDropdown = false)}
										liveSubStatuses={selectedLiveSubStatuses}
										onLiveSubStatusChange={handleLiveSubStatusChange}
										{liveStatusCounts}
										{completedCount}
										isLoading={isLoadingAllSessions || isServerSearching}
										source={filters.source || 'all'}
										onSourceChange={handleSourceChange}
									/>
								{/if}
							</div>
						</div>

						<!-- Mobile Filters Bottom Sheet -->
						{#if isMobile}
							<FiltersBottomSheet
								open={showFiltersDropdown}
								onClose={() => (showFiltersDropdown = false)}
								{scopeSelection}
								onScopeSelectionChange={handleScopeSelectionChange}
								status={filters.status}
								onStatusChange={handleStatusChange}
								dateRange={filters.dateRange}
								onDateRangeChange={handleDateRangeChange}
								onReset={handleClearAllFilters}
								liveSubStatuses={selectedLiveSubStatuses}
								onLiveSubStatusChange={handleLiveSubStatusChange}
								{liveStatusCounts}
								{completedCount}
								source={filters.source || 'all'}
								onSourceChange={handleSourceChange}
							/>
						{/if}

						<!-- Active Filters -->
						<ActiveFilterChips
							chips={filterChips}
							onRemove={handleRemoveFilter}
							onClearAll={handleClearAllFilters}
							totalCount={displayTotalCount}
							filteredCount={filteredSessionsCount}
						/>

						<!-- Branch filter chips (separate from search filters) -->
						{#if selectedBranchFilters.size > 0}
							<div class="flex items-center gap-2 flex-wrap">
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

						<!-- Live Sessions Section (matching sessions page) -->
						{#if filters.status !== 'completed'}
							<LiveSessionsSection
								onSessionsChange={handleLiveSessionsChange}
								searchQuery={searchTokens.join(' ')}
								projectFilter={project.encoded_name}
								statusFilter={filters.status}
								liveSubStatuses={selectedLiveSubStatuses}
								branchFilter={selectedBranchFilters.size > 0
									? selectedBranchFilters
									: undefined}
								historicalSessions={sessionsForFiltering}
							/>
						{/if}

						<!-- Recently Ended Section -->
						{#if showRecentlyEnded}
							<div class="mb-6">
								<!-- Section Header -->
								<div class="flex items-center gap-2 mb-4">
									<div class="flex items-center gap-2 text-[var(--text-muted)]">
										<Clock size={14} strokeWidth={2} />
										<h2 class="text-sm font-semibold uppercase tracking-wide">
											Recently Ended
										</h2>
									</div>
									<span
										class="inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 bg-[var(--bg-muted)] text-[var(--text-secondary)] rounded text-xs font-medium tabular-nums"
									>
										{recentlyEndedSessions.length}
									</span>
									<span class="text-xs text-[var(--text-faint)]">
										(within 45 min)
									</span>
								</div>

								<!-- Recently Ended Cards Grid - respects view mode -->
								<div
									class={viewMode === 'grid'
										? 'grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2'
										: 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3'}
								>
									{#each recentlyEndedSessions as { session, liveSession }}
										<SessionCard
											{session}
											projectEncodedName={project.encoded_name}
											showBranch={selectedBranchFilters.size === 0}
											compact={viewMode === 'grid'}
											{liveSession}
										/>
									{/each}
								</div>
							</div>
						{/if}

						<!-- Session Cards -->
						{#if filteredSessions.length > 0}
							{#key resultsAnimationKey}
								{#if viewMode === 'list'}
									<!-- List View: Time-Based Grouping -->
									<div class="space-y-8 animate-results-update">
										{#each groupedByDate as group (group.label)}
											<div>
												<!-- Section Header -->
												<h2
													class="text-sm font-semibold uppercase tracking-wide text-[var(--text-secondary)] mb-4"
												>
													{group.label}
													<span
														class="text-[var(--text-faint)] font-medium ml-1.5"
													>
														({group.sessions.length})
													</span>
												</h2>

												<!-- Session Cards Grid -->
												<div
													class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3"
												>
													{#each group.sessions as session (session.uuid)}
														<SessionCard
															{session}
															projectEncodedName={project.encoded_name}
															showBranch={selectedBranchFilters.size ===
																0}
															liveSession={getLiveSession(
																session
															)}
														/>
													{/each}
												</div>
											</div>
										{/each}
									</div>
								{:else}
									<!-- Grid View: Compact with Time-Based Grouping -->
									<div class="space-y-6 animate-results-update">
										{#each groupedByDate as group (group.label)}
											<div>
												<!-- Section Header -->
												<h2
													class="text-sm font-semibold uppercase tracking-wide text-[var(--text-secondary)] mb-3"
												>
													{group.label}
													<span
														class="text-[var(--text-faint)] font-medium ml-1.5"
													>
														({group.sessions.length})
													</span>
												</h2>

												<!-- Session Cards Grid (Compact) -->
												<div
													class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2"
												>
													{#each group.sessions as session (session.uuid)}
														<SessionCard
															{session}
															projectEncodedName={project.encoded_name}
															showBranch={selectedBranchFilters.size ===
																0}
															compact
															liveSession={getLiveSession(
																session
															)}
														/>
													{/each}
												</div>
											</div>
										{/each}
									</div>
								{/if}
							{/key}
						{:else if isListLoading}
							<!-- Loading State - Skeleton Cards -->
							<div class="space-y-6" aria-busy="true">
								<div>
									<!-- Fake Section Header -->
									<div
										class="h-4 w-24 bg-[var(--bg-muted)] rounded mb-4 animate-pulse"
									></div>
									<div
										class={viewMode === 'grid'
											? 'grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2'
											: 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3'}
									>
										{#each Array(6) as _}
											<SkeletonSessionCard />
										{/each}
									</div>
								</div>
							</div>
						{:else if hasActiveFilters || searchTokens.length > 0}
							<EmptyState icon={Search} title="No sessions match your filters">
								<div class="text-sm text-[var(--text-muted)] space-y-2 max-w-md">
									{#if searchTokens.length > 0}
										<p>
											No sessions found matching: <span
												class="font-medium text-[var(--text-secondary)]"
												>{searchTokens.join(', ')}</span
											>
										</p>
									{/if}
									{#if filters.status !== 'all' || filters.dateRange !== 'all' || selectedBranchFilters.size > 0}
										<p class="text-xs">
											Active filters: {filterChips
												.map((c) => c.label)
												.join(', ')}
											{#if selectedBranchFilters.size > 0}
												{filterChips.length > 0 ? ', ' : ''}Branches: {[
													...selectedBranchFilters
												].join(', ')}
											{/if}
										</p>
									{/if}
								</div>
								<button
									onclick={handleClearAllFilters}
									class="mt-4 px-4 py-2 text-sm bg-[var(--accent)] text-white rounded-lg hover:bg-[var(--accent-hover)] transition-colors"
								>
									Clear all filters
								</button>
							</EmptyState>
						{:else if selectedBranchFilters.size > 0}
							<EmptyState
								icon={GitBranch}
								title="No sessions on selected branches"
								description={selectedBranchFilters.size === 1
									? `No sessions found for '${[...selectedBranchFilters][0]}'.`
									: `No sessions found for the ${selectedBranchFilters.size} selected branches.`}
							>
								<button
									onclick={handleClearAllBranches}
									class="text-sm text-[var(--accent)] hover:underline"
								>
									Show all sessions
								</button>
							</EmptyState>
						{:else}
							<EmptyState
								icon={MessageSquare}
								title="No sessions yet"
								description="Sessions will appear here once you start working."
							/>
						{/if}

						<!-- Pagination / Results Info -->
						{#if !hasClientSideFilters && project && (project.sessions?.length ?? 0) > 0}
							<Pagination
								total={totalSessionCount}
								page={currentPage}
								perPage={paginationPerPage}
								{totalPages}
								onPageChange={goToPage}
								itemLabel="sessions"
							/>
						{:else if hasClientSideFilters && project && (project.sessions?.length ?? 0) > 0}
							<div class="mt-8 text-xs text-[var(--text-muted)] tabular-nums">
								Showing <span class="font-medium text-[var(--text-secondary)]"
									>{filteredSessionsCount.toLocaleString()}</span
								> filtered sessions
							</div>
						{/if}
					</div>
				</Tabs.Content>

				<!-- Analytics Tab -->
				<Tabs.Content value="analytics" class="animate-fade-in">
					<div class="space-y-6">
						<!-- Header with Time Filter -->
						<div
							class="flex flex-col sm:flex-row sm:items-center justify-between gap-3"
						>
							<div>
								<h2 class="text-lg font-semibold text-[var(--text-primary)]">
									Project Analytics
								</h2>
								<p class="text-sm text-[var(--text-muted)]">
									Insights into your coding patterns and project health
								</p>
							</div>

							<!-- Time Filter Dropdown -->
							<TimeFilterDropdown
								{selectedFilter}
								onFilterChange={handleFilterChange}
							/>
						</div>

						{#if analyticsLoading}
							<!-- Loading State -->
							<div class="flex items-center justify-center py-12">
								<div class="flex flex-col items-center gap-3">
									<div
										class="w-8 h-8 border-4 border-[var(--accent)]/30 border-t-[var(--accent)] rounded-full animate-spin"
									></div>
									<p class="text-sm text-[var(--text-muted)]">
										Loading analytics...
									</p>
								</div>
							</div>
						{:else if analyticsError}
							<!-- Error State -->
							<EmptyState
								icon={BarChart3}
								title="Failed to load analytics"
								description="There was an error loading analytics data. Please try again."
							>
								<button
									onclick={() => {
										analytics = null;
										fetchAnalytics();
									}}
									class="mt-4 px-4 py-2 text-sm bg-[var(--accent)] text-white rounded-lg hover:bg-[var(--accent-hover)] transition-colors"
								>
									Retry
								</button>
							</EmptyState>
						{:else if analytics}
							<!-- Stats Grid -->
							<StatsGrid stats={overviewStats} columns={5} />

							<!-- Summary Cards Row -->
							<div class="grid grid-cols-1 md:grid-cols-2 gap-3">
								<!-- Time Investment Card -->
								<Card variant="subtle" class="p-5">
									<div class="flex items-start justify-between mb-4">
										<div
											class="flex items-center gap-2 text-[var(--text-muted)]"
										>
											<Clock size={16} />
											<h3
												class="text-xs font-semibold uppercase tracking-wider"
											>
												Time Investment
											</h3>
										</div>
									</div>

									<div class="mb-4 flex flex-col justify-center">
										<div class="flex items-center gap-3">
											<div
												class="p-2 rounded-full bg-[var(--bg-active)] text-[var(--accent)]"
											>
												<PieChart size={24} />
											</div>
											<div>
												<div
													class="text-2xl font-bold text-[var(--text-primary)]"
												>
													{formatDuration(
														analytics.total_duration_seconds
													)}
												</div>
												<div class="text-xs text-[var(--text-muted)]">
													Total Time
												</div>
											</div>
										</div>
									</div>

									<div class="pt-4 border-t border-[var(--border)] space-y-2">
										<div class="flex justify-between items-center text-xs">
											<span class="text-[var(--text-muted)]">Est. Cost</span>
											<span class="font-mono text-[var(--text-primary)]"
												>${analytics.estimated_cost_usd}</span
											>
										</div>
										<div class="flex justify-between items-center text-xs">
											<span class="text-[var(--text-muted)]">Tokens</span>
											<span class="font-mono text-[var(--text-primary)]"
												>{formatTokens(analytics.total_tokens)}</span
											>
										</div>
									</div>
								</Card>

								<!-- Work Mode Distribution Card -->
								{#if analytics.work_mode_distribution}
									<Card
										variant="subtle"
										class="p-5 flex flex-col justify-between h-full"
									>
										<div class="flex items-start justify-between mb-4">
											<div
												class="flex items-center gap-2 text-[var(--text-muted)]"
											>
												<Briefcase size={16} />
												<h3
													class="text-xs font-semibold uppercase tracking-wider"
												>
													Work Mode
												</h3>
											</div>
											<span
												class="text-[10px] font-medium px-2 py-0.5 rounded-full bg-[var(--bg-muted)] text-[var(--text-primary)] border border-[var(--border)]"
											>
												{analytics.work_mode_distribution.primary_mode}
											</span>
										</div>

										<div class="flex-1 flex flex-col justify-center mb-2">
											<!-- Progress Bar -->
											<div
												class="h-3 w-full flex rounded-full overflow-hidden bg-[var(--bg-muted)]"
											>
												<div
													class="bg-blue-500/80 h-full first:rounded-l-full last:rounded-r-full"
													style="width: {analytics.work_mode_distribution
														.exploration_pct}%"
												></div>
												<div
													class="bg-purple-500/80 h-full first:rounded-l-full last:rounded-r-full"
													style="width: {analytics.work_mode_distribution
														.building_pct}%"
												></div>
												<div
													class="bg-orange-500/80 h-full first:rounded-l-full last:rounded-r-full"
													style="width: {analytics.work_mode_distribution
														.testing_pct}%"
												></div>
											</div>
										</div>

										<div class="space-y-2 text-xs">
											<div class="flex justify-between items-center">
												<div class="flex items-center gap-2">
													<div
														class="w-2 h-2 rounded-full bg-blue-500/80"
													></div>
													<span class="text-[var(--text-secondary)]"
														>Exploration</span
													>
												</div>
												<span class="font-mono"
													>{analytics.work_mode_distribution
														.exploration_pct}%</span
												>
											</div>
											<div class="flex justify-between items-center">
												<div class="flex items-center gap-2">
													<div
														class="w-2 h-2 rounded-full bg-purple-500/80"
													></div>
													<span class="text-[var(--text-secondary)]"
														>Building</span
													>
												</div>
												<span class="font-mono"
													>{analytics.work_mode_distribution
														.building_pct}%</span
												>
											</div>
											<div class="flex justify-between items-center">
												<div class="flex items-center gap-2">
													<div
														class="w-2 h-2 rounded-full bg-orange-500/80"
													></div>
													<span class="text-[var(--text-secondary)]"
														>Testing</span
													>
												</div>
												<span class="font-mono"
													>{analytics.work_mode_distribution
														.testing_pct}%</span
												>
											</div>
										</div>
									</Card>
								{/if}
							</div>

							<!-- Additional Detailed Charts or Analysis -->
							<div class="mt-6">
								<!-- Sessions Chart - uses full history from analytics API -->
								<SessionsChart sessionsByDate={analytics.sessions_by_date} />
							</div>
						{:else}
							<EmptyState
								icon={BarChart3}
								title="Analytics not available"
								description="Start working on the project to generate analytics data."
							/>
						{/if}
					</div>
				</Tabs.Content>

				<!-- Agents Tab -->
				<Tabs.Content value="agents" class="animate-fade-in">
					<AgentList projectEncodedName={project.encoded_name} />
				</Tabs.Content>

				<!-- Skills Tab -->
				<Tabs.Content value="skills" class="animate-fade-in">
					<SkillList projectEncodedName={project.encoded_name} />
				</Tabs.Content>

				<!-- Tools Tab -->
				<Tabs.Content value="tools" class="animate-fade-in">
					<ToolList projectEncodedName={project.encoded_name} />
				</Tabs.Content>

				<!-- Memory Tab -->
				<Tabs.Content value="memory" class="animate-fade-in">
					<MemoryViewer projectEncodedName={project.encoded_name} />
				</Tabs.Content>

				<!-- Archived Tab -->
				{#if archived.total_sessions > 0}
					<Tabs.Content value="archived" class="animate-fade-in">
						<div class="space-y-6">
							<!-- Header -->
							<div>
								<h2 class="text-lg font-semibold text-[var(--text-primary)]">
									Archived Sessions
								</h2>
								<p class="text-sm text-[var(--text-muted)]">
									{archived.total_sessions}
									{archived.total_sessions === 1 ? 'session' : 'sessions'} with {archived.total_prompts}
									prompts cleaned up by retention policy
								</p>
							</div>

							<!-- Archived Cards Grid -->
							<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
								{#each archived.sessions as session}
									<ArchivedSessionCard {session} />
								{/each}
							</div>
						</div>
					</Tabs.Content>
				{/if}
			</Tabs.Root>
		{:else}
			<ProjectDetailSkeleton />
		{/if}
	</div>
{/if}
