<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { FolderOpen, Bot, ChevronDown, ChevronRight, Radio, Trash2 } from 'lucide-svelte';
	import type {
		LiveSessionSummary,
		SessionStatusFilter,
		LiveSubStatus,
		SessionSummary
	} from '$lib/api-types';
	import { statusConfig } from '$lib/live-session-config';
	import { API_BASE } from '$lib/config';

	interface Props {
		/** Initial collapsed state */
		initialCollapsed?: boolean;
		/** Callback when live sessions change (for parent deduplication) */
		onSessionsChange?: (sessions: LiveSessionSummary[]) => void;
		/** Filter by slug/project match */
		searchQuery?: string;
		/** Filter by project encoded name */
		projectFilter?: string;
		/** To know if showing live is expected */
		statusFilter?: SessionStatusFilter;
		/** Which sub-statuses to show */
		liveSubStatuses?: LiveSubStatus[];
		/** Filter by branch names (requires historicalSessions for matching) */
		branchFilter?: Set<string>;
		/** Historical sessions for branch matching (live sessions don't have branch info) */
		historicalSessions?: SessionSummary[];
	}

	let {
		initialCollapsed = false,
		onSessionsChange,
		searchQuery,
		projectFilter,
		statusFilter,
		liveSubStatuses,
		branchFilter,
		historicalSessions
	}: Props = $props();

	// Build lookup maps for matching live sessions to historical (for branch filtering)
	const historicalBySlug = $derived.by(() => {
		if (!historicalSessions) return new Map<string, SessionSummary>();
		const map = new Map<string, SessionSummary>();
		for (const s of historicalSessions) {
			if (s.slug) map.set(s.slug, s);
		}
		return map;
	});

	const historicalByUuid = $derived.by(() => {
		if (!historicalSessions) return new Map<string, SessionSummary>();
		const map = new Map<string, SessionSummary>();
		for (const s of historicalSessions) {
			map.set(s.uuid, s);
		}
		return map;
	});

	// Find historical session for a live session (for branch matching)
	function getHistoricalForLive(live: LiveSessionSummary): SessionSummary | null {
		// Try slug first (more reliable for resumed sessions)
		if (live.slug) {
			const bySlug = historicalBySlug.get(live.slug);
			if (bySlug) return bySlug;
		}
		// Fallback to session_id
		const byId = historicalByUuid.get(live.session_id);
		return byId ?? null;
	}

	let sessions = $state<LiveSessionSummary[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let collapsed = $state(initialCollapsed);
	let collapsedInitialized = $state(false);

	let isCleaningUp = $state(false);
	let stuckSessionCount = $state(0);

	// Check for idle sessions that have been inactive for 75+ minutes
	async function checkStuckSessions() {
		try {
			const res = await fetch(`${API_BASE}/live-sessions`);
			if (res.ok) {
				const data = await res.json();
				stuckSessionCount = (data.sessions ?? []).filter(
					(s: LiveSessionSummary) => s.status === 'idle' && s.idle_seconds > 4500
				).length;
			}
		} catch {
			// ignore
		}
	}

	const hasStuckSessions = $derived(stuckSessionCount > 0);

	async function cleanupStuckSessions(event: MouseEvent) {
		event.stopPropagation();
		if (isCleaningUp) return;
		isCleaningUp = true;
		try {
			const res = await fetch(`${API_BASE}/live-sessions/cleanup-old`, { method: 'POST' });
			if (res.ok) {
				await fetchSessions();
				stuckSessionCount = 0;
			}
		} catch (e) {
			console.error('Failed to cleanup stuck sessions:', e);
		} finally {
			isCleaningUp = false;
		}
	}

	let pollInterval: ReturnType<typeof setInterval> | null = null;
	let isFetching = $state(false);
	let abortController: AbortController | null = null;
	let lastFetchTime = 0;

	// Initialize collapsed state from localStorage
	$effect(() => {
		if (typeof window !== 'undefined' && !collapsedInitialized) {
			const saved = localStorage.getItem('claude-karma-live-section-collapsed');
			if (saved !== null) {
				collapsed = saved === 'true';
			}
			collapsedInitialized = true;
		}
	});

	// Persist collapsed state
	$effect(() => {
		if (typeof window !== 'undefined' && collapsedInitialized) {
			localStorage.setItem('claude-karma-live-section-collapsed', String(collapsed));
		}
	});

	// Notify parent when sessions change
	$effect(() => {
		onSessionsChange?.(sessions);
	});

	// Count sessions by status category
	const sessionCounts = $derived({
		total: sessions.length,
		active: sessions.filter(
			(s) => s.status === 'active' || s.status === 'waiting' || s.status === 'starting'
		).length,
		idle: sessions.filter((s) => s.status === 'idle').length,
		stopped: sessions.filter((s) => s.status === 'stopped' || s.status === 'stale').length
	});

	// Filter to only show non-ended sessions, and exclude ghost sessions
	// (ended sessions whose transcript never materialized)
	const activeSessions = $derived(
		sessions.filter((s) => s.status !== 'ended' && s.transcript_exists !== false)
	);

	// Apply all filters to activeSessions
	const filteredSessions = $derived.by(() => {
		let result = activeSessions;

		// If status is 'completed', return empty (show "no matching" message)
		if (statusFilter === 'completed') {
			return [];
		}

		// Filter by live sub-statuses (only when status is 'live' or 'all')
		if (liveSubStatuses && liveSubStatuses.length > 0) {
			result = result.filter((s) => liveSubStatuses.includes(s.status as LiveSubStatus));
		}

		// Filter by project
		if (projectFilter) {
			result = result.filter((s) => s.project_encoded_name === projectFilter);
		}

		// Filter by branch (requires matching to historical sessions)
		if (branchFilter && branchFilter.size > 0 && historicalSessions) {
			result = result.filter((live) => {
				const historical = getHistoricalForLive(live);
				if (!historical) return false; // No match = can't verify branch
				return historical.git_branches?.some((b) => branchFilter.has(b)) ?? false;
			});
		}

		// Filter by search query (match slug or project name from cwd)
		if (searchQuery && searchQuery.trim()) {
			const query = searchQuery.toLowerCase().trim();
			result = result.filter((s) => {
				const slug = (s.slug || s.session_id).toLowerCase();
				const projectName = getProjectDisplayName(s).toLowerCase();
				return slug.includes(query) || projectName.includes(query);
			});
		}

		return result;
	});

	// Check if any filters are active
	const hasActiveFilters = $derived(
		!!searchQuery?.trim() ||
			!!projectFilter ||
			statusFilter === 'completed' ||
			(liveSubStatuses && liveSubStatuses.length > 0 && liveSubStatuses.length < 5) ||
			(branchFilter && branchFilter.size > 0)
	);

	// Count display helper
	const countDisplay = $derived.by(() => {
		const filtered = filteredSessions.length;
		const total = activeSessions.length;
		if (hasActiveFilters && filtered !== total) {
			return `${filtered} of ${total}`;
		}
		return `${total}`;
	});

	async function fetchSessions() {
		if (isFetching) return; // Guard against concurrent fetches
		isFetching = true;

		const fetchTime = Date.now();

		// Abort any previous request
		if (abortController) abortController.abort();
		abortController = new AbortController();

		try {
			const res = await fetch(`${API_BASE}/live-sessions/active`, {
				signal: abortController.signal
			});

			// Only update if this is the most recent request
			if (fetchTime < lastFetchTime) return;
			lastFetchTime = fetchTime;

			if (res.ok) {
				sessions = await res.json();
				error = null;
			} else if (res.status === 404) {
				error = 'API not available';
			} else {
				error = 'Failed to fetch';
			}
		} catch (e) {
			if (e instanceof Error && e.name === 'AbortError') return;
			error = 'Cannot connect to API';
			console.error('Failed to fetch live sessions:', e);
		} finally {
			isFetching = false;
			loading = false;
		}
	}

	function formatDuration(seconds: number): string {
		const mins = Math.floor(seconds / 60);
		const hrs = Math.floor(mins / 60);
		if (hrs > 0) return `${hrs}h ${mins % 60}m`;
		if (mins > 0) return `${mins}m`;
		return `${Math.floor(seconds)}s`;
	}

	function formatIdleTime(seconds: number): string {
		if (seconds < 60) return `${Math.floor(seconds)}s`;
		const mins = Math.floor(seconds / 60);
		return `${mins}m`;
	}

	function getProjectDisplayName(session: LiveSessionSummary): string {
		const parts = session.cwd.split('/').filter(Boolean);
		const skipDirs = ['Users', 'home', 'Documents', 'GitHub', 'Projects', 'repos', 'src'];

		for (let i = parts.length - 1; i >= 0; i--) {
			const part = parts[i];
			if (!skipDirs.includes(part) && part.length > 2) {
				if (
					i > 0 &&
					(part === 'frontend' ||
						part === 'backend' ||
						part === 'api' ||
						part === 'src' ||
						part === 'app')
				) {
					return parts[i - 1] || part;
				}
				return part;
			}
		}

		return parts[parts.length - 1] || 'Unknown';
	}

	function getSessionUrl(session: LiveSessionSummary): string {
		if (!session.project_encoded_name) {
			return '#';
		}
		const identifier = session.slug || session.session_id.slice(0, 8);
		return `/projects/${session.project_slug || session.project_encoded_name}/${identifier}`;
	}

	function canNavigate(session: LiveSessionSummary): boolean {
		return !!session.project_encoded_name;
	}

	function getDisplayName(session: LiveSessionSummary): string {
		return session.slug || session.session_id.slice(0, 8);
	}

	// Polling configuration - 3 seconds is a good balance between responsiveness and efficiency
	const POLL_INTERVAL = 3000;

	onMount(() => {
		fetchSessions();
		checkStuckSessions();
		// Poll every 3 seconds for live session status
		pollInterval = setInterval(fetchSessions, POLL_INTERVAL);
	});

	onDestroy(() => {
		if (pollInterval) {
			clearInterval(pollInterval);
		}
		if (abortController) {
			abortController.abort();
		}
	});
</script>

{#if activeSessions.length > 0 || loading || (statusFilter !== 'completed' && hasActiveFilters)}
	<div class="live-section mb-6">
		<!-- Header -->
		<button
			onclick={() => (collapsed = !collapsed)}
			class="live-header w-full"
			aria-expanded={!collapsed}
		>
			<div class="flex items-center gap-2">
				<div class="flex items-center gap-1.5">
					{#if collapsed}
						<ChevronRight size={16} strokeWidth={2} class="text-[var(--text-muted)]" />
					{:else}
						<ChevronDown size={16} strokeWidth={2} class="text-[var(--text-muted)]" />
					{/if}
					<Radio size={14} strokeWidth={2} class="text-[var(--success)]" />
					<span class="section-title">LIVE NOW</span>
				</div>
				{#if !loading}
					<span class="count-badge">
						{#if hasActiveFilters}
							{countDisplay} sessions
						{:else}
							{sessionCounts.active > 0 ? `${sessionCounts.active} active` : ''}
							{sessionCounts.idle > 0
								? `${sessionCounts.active > 0 ? ', ' : ''}${sessionCounts.idle} idle`
								: ''}
							{sessionCounts.stopped > 0
								? `${sessionCounts.active + sessionCounts.idle > 0 ? ', ' : ''}${sessionCounts.stopped} stopped`
								: ''}
						{/if}
					</span>
				{/if}
			</div>
			<div class="flex items-center gap-2">
				{#if hasStuckSessions}
					<button
						class="cleanup-btn"
						onclick={cleanupStuckSessions}
						disabled={isCleaningUp}
						title="Remove {stuckSessionCount} idle session{stuckSessionCount !== 1
							? 's'
							: ''} inactive for 75+ minutes"
					>
						<Trash2 size={12} strokeWidth={2} />
						<span class="cleanup-label"
							>{isCleaningUp ? 'Cleaning...' : `Clean ${stuckSessionCount}`}</span
						>
					</button>
				{/if}
				<span class="pulse-indicator" title="Polling every 1s"></span>
			</div>
		</button>

		<!-- Content -->
		{#if !collapsed}
			<div class="live-content">
				{#if loading}
					<div class="empty-state">
						<span class="loading-text">Loading live sessions...</span>
					</div>
				{:else if error}
					<div class="empty-state error">
						<span>{error}</span>
					</div>
				{:else if filteredSessions.length === 0}
					<div class="empty-state">
						<span class="empty-message">
							{#if hasActiveFilters}
								No matching live sessions
								{#if branchFilter && branchFilter.size > 0}
									<span class="empty-hint"
										>on selected branch{branchFilter.size > 1 ? 'es' : ''}</span
									>
								{/if}
							{:else}
								No active sessions
							{/if}
						</span>
					</div>
				{:else}
					<div class="sessions-list">
						{#each filteredSessions as session (session.session_id)}
							{@const config = statusConfig[session.status]}
							{@const canLink = canNavigate(session)}
							<svelte:element
								this={canLink ? 'a' : 'div'}
								href={canLink ? getSessionUrl(session) : undefined}
								class="session-row"
								class:clickable={canLink}
							>
								<!-- Status Dot -->
								<span
									class="status-dot"
									class:pulse={config.pulse}
									style="background: {config.color}"
									title={config.label}
								></span>

								<!-- Session Info -->
								<div class="session-info">
									<!-- Row 1: Name + Status + Agents -->
									<div class="session-primary">
										<span class="session-name font-mono"
											>{getDisplayName(session)}</span
										>
										<span class="status-label" style="color: {config.color}">
											{config.label.toUpperCase()}
											{#if session.status === 'idle' && session.idle_seconds > 0}
												<span class="idle-time"
													>{formatIdleTime(session.idle_seconds)}</span
												>
											{/if}
										</span>
										{#if session.active_subagent_count > 0}
											<span class="agent-badge">
												<Bot size={10} strokeWidth={2} />
												<span>{session.active_subagent_count}</span>
											</span>
										{/if}
									</div>
									<!-- Row 2: Project + Duration -->
									<div class="session-secondary">
										<span class="project" title={session.cwd}>
											<FolderOpen size={11} strokeWidth={2} />
											{getProjectDisplayName(session)}
										</span>
										<span class="duration"
											>{formatDuration(session.duration_seconds)}</span
										>
									</div>
								</div>
							</svelte:element>
						{/each}
					</div>
				{/if}
			</div>
		{/if}
	</div>
{/if}

<style>
	.live-section {
		background: var(--bg-subtle);
		border: 1px solid var(--border);
		border-radius: var(--radius-md);
		overflow: hidden;
	}

	.live-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 12px 16px;
		background: var(--bg-muted);
		border: none;
		cursor: pointer;
		transition: background var(--duration-fast);
	}

	.live-header:hover {
		background: var(--bg-subtle);
	}

	.section-title {
		font-size: 11px;
		font-weight: 600;
		letter-spacing: 0.5px;
		color: var(--text-secondary);
	}

	.count-badge {
		font-size: 11px;
		color: var(--text-muted);
		font-weight: 500;
	}

	.cleanup-btn {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		padding: 2px 8px;
		border: 1px solid var(--border-subtle);
		border-radius: var(--radius-sm);
		background: transparent;
		color: var(--text-muted);
		font-size: 11px;
		font-weight: 500;
		cursor: pointer;
		transition:
			color var(--duration-fast),
			border-color var(--duration-fast),
			opacity var(--duration-fast);
	}

	.cleanup-btn:hover:not(:disabled) {
		color: var(--text-secondary);
		border-color: var(--border);
	}

	.cleanup-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.cleanup-label {
		line-height: 1;
	}

	.pulse-indicator {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		background: var(--success);
		animation: pulse 2s ease infinite;
	}

	@keyframes pulse {
		0%,
		100% {
			opacity: 1;
		}
		50% {
			opacity: 0.4;
		}
	}

	.live-content {
		border-top: 1px solid var(--border-subtle);
	}

	.empty-state {
		padding: 16px;
		text-align: center;
		color: var(--text-muted);
		font-size: 13px;
	}

	.empty-state.error {
		color: var(--error);
	}

	.empty-message {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 4px;
	}

	.empty-hint {
		font-size: 11px;
		color: var(--text-faint);
		font-weight: 400;
	}

	.loading-text {
		animation: fade 1.5s ease infinite;
	}

	@keyframes fade {
		0%,
		100% {
			opacity: 1;
		}
		50% {
			opacity: 0.5;
		}
	}

	.sessions-list {
		display: flex;
		flex-direction: column;
	}

	.session-row {
		display: flex;
		align-items: flex-start;
		gap: 12px;
		padding: 12px 16px;
		text-decoration: none;
		color: inherit;
		transition: background var(--duration-fast);
		border-bottom: 1px solid var(--border-subtle);
	}

	.session-row:last-child {
		border-bottom: none;
	}

	.session-row.clickable:hover {
		background: var(--bg-muted);
		cursor: pointer;
	}

	.session-row.clickable:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: -2px;
	}

	.status-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		flex-shrink: 0;
		margin-top: 6px;
	}

	.status-dot.pulse {
		animation: pulse 2s ease infinite;
	}

	.session-info {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.session-primary {
		display: flex;
		align-items: center;
		gap: 10px;
		flex-wrap: wrap;
	}

	.session-name {
		color: var(--accent);
		font-weight: 500;
		font-size: 13px;
	}

	.status-label {
		font-size: 10px;
		font-weight: 600;
		letter-spacing: 0.5px;
	}

	.idle-time {
		font-weight: 500;
		margin-left: 2px;
		opacity: 0.8;
	}

	.agent-badge {
		display: inline-flex;
		align-items: center;
		gap: 3px;
		padding: 2px 6px;
		border-radius: 10px;
		background: var(--nav-purple-subtle, rgba(139, 92, 246, 0.1));
		color: var(--nav-purple);
		font-size: 10px;
		font-weight: 500;
	}

	.session-secondary {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		font-size: 12px;
		color: var(--text-muted);
	}

	.project {
		display: flex;
		align-items: center;
		gap: 4px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.duration {
		flex-shrink: 0;
		font-variant-numeric: tabular-nums;
		color: var(--text-faint);
	}
</style>
