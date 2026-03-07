<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { FolderOpen, Bot, Trash2 } from 'lucide-svelte';
	import type { LiveSessionSummary } from '$lib/api-types';
	import { statusConfig } from '$lib/live-session-config';
	import { API_BASE } from '$lib/config';

	let sessions = $state<LiveSessionSummary[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let isCleaningUp = $state(false);
	let stuckSessionCount = $state(0);

	let pollInterval: ReturnType<typeof setInterval> | null = null;

	// Polling guards to prevent race conditions
	let isFetching = $state(false);
	let abortController: AbortController | null = null;
	let lastFetchTime = 0;

	// Count sessions by category
	const sessionCounts = $derived({
		total: sessions.length,
		active: sessions.filter(
			(s) => s.status === 'active' || s.status === 'waiting' || s.status === 'starting'
		).length,
		needsAttention: sessions.filter((s) => s.status === 'stale').length
	});

	async function fetchSessions() {
		// Guard against concurrent fetches
		if (isFetching) return;
		isFetching = true;

		// Track this request's timestamp to detect stale responses
		const fetchTime = Date.now();
		lastFetchTime = fetchTime;

		// Create new AbortController for this request
		abortController = new AbortController();

		try {
			const res = await fetch(`${API_BASE}/live-sessions/active`, {
				signal: abortController.signal
			});

			// Only update state if this is still the most recent request
			if (fetchTime !== lastFetchTime) return;

			if (res.ok) {
				sessions = await res.json();
				error = null;
			} else if (res.status === 404) {
				// API endpoint not found - likely API not running
				error = 'API not available';
			} else {
				error = 'Failed to fetch';
			}
		} catch (e) {
			// Ignore abort errors (expected on unmount)
			if (e instanceof Error && e.name === 'AbortError') return;

			// Only update error state if this is still the most recent request
			if (fetchTime !== lastFetchTime) return;

			error = 'Cannot connect to API';
			console.error('Failed to fetch live sessions:', e);
		} finally {
			// Only clear fetching flag if this is still the most recent request
			if (fetchTime === lastFetchTime) {
				isFetching = false;
				loading = false;
			}
		}
	}

	function formatDuration(seconds: number): string {
		const mins = Math.floor(seconds / 60);
		const hrs = Math.floor(mins / 60);
		if (hrs > 0) return `${hrs}h ${mins % 60}m`;
		if (mins > 0) return `${mins}m`;
		return `${Math.floor(seconds)}s`;
	}

	function getProjectDisplayName(session: LiveSessionSummary): string {
		// Use cwd which has proper path separators
		// cwd: /Users/username/projects/claude-karma/frontend
		// We want the git root name, not the subdirectory
		const parts = session.cwd.split('/').filter(Boolean);

		// Try to find a meaningful project name (skip common directories)
		const skipDirs = ['Users', 'home', 'Documents', 'GitHub', 'Projects', 'repos', 'src'];

		// Walk backwards to find the first meaningful directory
		for (let i = parts.length - 1; i >= 0; i--) {
			const part = parts[i];
			// Skip common directories and short names
			if (!skipDirs.includes(part) && part.length > 2) {
				// Check if this looks like a project root (has hyphen or is capitalized)
				// For paths like /GitHub/claude-karma/frontend, prefer claude-karma over frontend
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
		// Handle edge case: no project_encoded_name
		if (!session.project_encoded_name) {
			return '#'; // Can't link without project
		}
		const identifier = session.session_id.slice(0, 8);
		return `/projects/${session.project_slug || session.project_encoded_name}/${identifier}`;
	}

	function canNavigate(session: LiveSessionSummary): boolean {
		return !!session.project_encoded_name;
	}

	const hasStuckSessions = $derived(stuckSessionCount > 0);

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

	async function cleanupStuckSessions() {
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

	onMount(() => {
		fetchSessions();
		checkStuckSessions();
		// Poll every 1 second for real-time status monitoring
		// TODO: Replace with SSE for true real-time
		pollInterval = setInterval(fetchSessions, 1000);
	});

	onDestroy(() => {
		if (pollInterval) {
			clearInterval(pollInterval);
		}
		// Abort any in-flight request
		if (abortController) {
			abortController.abort();
		}
	});
</script>

<div class="terminal-container">
	<!-- Header -->
	<div class="terminal-header">
		<span class="prompt">$ live-sessions</span>
		<div class="header-right">
			{#if hasStuckSessions}
				<button
					class="cleanup-btn"
					onclick={cleanupStuckSessions}
					disabled={isCleaningUp}
					title="Remove {stuckSessionCount} idle session{stuckSessionCount !== 1
						? 's'
						: ''} inactive for 75+ minutes"
				>
					<Trash2 size={11} strokeWidth={2} />
					<span>{isCleaningUp ? 'Cleaning...' : `Clean ${stuckSessionCount}`}</span>
				</button>
			{/if}
			<span class="badge">
				{#if loading}
					...
				{:else if error}
					[error]
				{:else if sessionCounts.total === 0}
					[none]
				{:else}
					[{sessionCounts.active} active{sessionCounts.needsAttention > 0
						? `, ${sessionCounts.needsAttention} stale`
						: ''}]
				{/if}
			</span>
		</div>
	</div>

	<!-- Sessions List -->
	<div class="terminal-body">
		{#if loading}
			<div class="empty-state">
				<span class="loading-dots">Loading</span>
			</div>
		{:else if error}
			<div class="empty-state error">
				<span>{error}</span>
				<span class="hint">Is the API running on port 8000?</span>
			</div>
		{:else if sessions.length === 0}
			<div class="empty-state">
				<span>No active sessions</span>
				<span class="hint">Start a Claude Code session to see it here</span>
			</div>
		{:else}
			{#each sessions as session (session.session_id)}
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
						class="dot"
						class:pulse={config.pulse}
						style="background: {config.color}"
						title={config.label}
					></span>

					<!-- Session Info -->
					<div class="session-info">
						<!-- Row 1: Session ID + Status + Agents -->
						<div class="session-primary">
							<span class="session-id">{session.session_id.slice(0, 8)}</span>
							<span class="status-badge" style="color: {config.color}"
								>{config.label}</span
							>
							{#if session.active_subagent_count > 0}
								<span class="agent-indicator">
									<Bot size={10} strokeWidth={2} class="agent-icon" />
									<span class="agent-count">{session.active_subagent_count}</span>
								</span>
							{/if}
						</div>
						<!-- Row 2: Project + Duration -->
						<div class="session-secondary">
							<span class="project" title={session.cwd}>
								<FolderOpen size={11} strokeWidth={2} />
								{getProjectDisplayName(session)}
							</span>
							<span class="duration">{formatDuration(session.duration_seconds)}</span>
						</div>
					</div>
				</svelte:element>
			{/each}
		{/if}
	</div>
</div>

<style>
	.terminal-container {
		background: var(--bg-subtle);
		border: 1px solid var(--border);
		border-radius: var(--radius-md);
		font-family: var(--font-mono);
		overflow: hidden;
	}

	.terminal-header {
		padding: 10px 14px;
		border-bottom: 1px solid var(--border);
		display: flex;
		justify-content: space-between;
		align-items: center;
		background: var(--bg-muted);
	}

	.prompt {
		color: var(--accent);
		font-size: 13px;
		font-weight: 500;
	}

	.header-right {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.badge {
		color: var(--text-muted);
		font-size: 12px;
	}

	.cleanup-btn {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		padding: 2px 8px;
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		background: transparent;
		color: var(--text-muted);
		font-size: 11px;
		font-family: var(--font-mono);
		cursor: pointer;
		transition: all var(--duration-fast);
	}

	.cleanup-btn:hover:not(:disabled) {
		color: var(--error);
		border-color: var(--error);
		background: rgba(239, 68, 68, 0.05);
	}

	.cleanup-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.terminal-body {
		max-height: 130px;
		overflow-y: auto;
	}

	/* Empty States */
	.empty-state {
		padding: 20px 14px;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 4px;
		color: var(--text-muted);
		font-size: 13px;
		text-align: center;
	}

	.empty-state.error {
		color: var(--error);
	}

	.empty-state .hint {
		font-size: 11px;
		color: var(--text-faint);
	}

	.loading-dots::after {
		content: '';
		animation: dots 1.5s steps(4, end) infinite;
	}

	@keyframes dots {
		0%,
		20% {
			content: '';
		}
		40% {
			content: '.';
		}
		60% {
			content: '..';
		}
		80%,
		100% {
			content: '...';
		}
	}

	/* Session Rows */
	.session-row {
		display: flex;
		align-items: flex-start;
		gap: 10px;
		padding: 10px 14px;
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
		border-radius: var(--radius-sm);
	}

	/* Status Dot */
	.dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		flex-shrink: 0;
		margin-top: 5px;
	}

	.pulse {
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

	/* Session Info */
	.session-info {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 3px;
	}

	.session-primary {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.session-id {
		color: var(--accent);
		font-weight: 500;
		font-size: 13px;
	}

	.status-badge {
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.5px;
		font-weight: 500;
	}

	.session-secondary {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
		font-size: 11px;
		color: var(--text-muted);
	}

	.project {
		display: flex;
		align-items: center;
		gap: 4px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		max-width: 70%;
	}

	.duration {
		flex-shrink: 0;
		font-variant-numeric: tabular-nums;
		color: var(--text-faint);
	}

	/* Agent indicator */
	.agent-indicator {
		display: inline-flex;
		align-items: center;
		gap: 3px;
		padding: 1px 6px;
		border-radius: 10px;
		background: var(--nav-purple-subtle, rgba(139, 92, 246, 0.1));
		color: var(--nav-purple);
		font-size: 10px;
		font-weight: 500;
		animation: agent-pulse 2s ease-in-out infinite;
	}

	.agent-indicator :global(.agent-icon) {
		flex-shrink: 0;
	}

	.agent-count {
		font-variant-numeric: tabular-nums;
	}

	@keyframes agent-pulse {
		0%,
		100% {
			opacity: 1;
		}
		50% {
			opacity: 0.7;
		}
	}
</style>
