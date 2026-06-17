<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import type { LiveSessionSummary } from '$lib/api-types';
	import { projectHrefFromSession } from '$lib/utils/project-url';
	import { getSessionDisplayLabel } from '$lib/utils/sessionIdentifier';
	import { statusConfig } from '$lib/live-session-config';
	import { API_BASE } from '$lib/config';

	// How many recent sessions to surface in the strip.
	const MAX_ROWS = 3;
	// Poll cadence for the glanceable home strip (lighter than the full
	// real-time terminal which polls every ~1s).
	const POLL_MS = 10_000;

	let sessions = $state<LiveSessionSummary[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	let pollInterval: ReturnType<typeof setInterval> | null = null;
	let isFetching = false;
	let abortController: AbortController | null = null;
	let lastFetchTime = 0;

	// Most recent sessions first, capped to MAX_ROWS.
	const recent = $derived(
		[...sessions]
			.sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
			.slice(0, MAX_ROWS)
	);

	const counts = $derived({
		active: sessions.filter(
			(s) => s.status === 'active' || s.status === 'waiting' || s.status === 'starting'
		).length,
		stale: sessions.filter((s) => s.status === 'stale').length
	});

	async function fetchSessions() {
		if (isFetching) return;
		isFetching = true;

		const fetchTime = Date.now();
		lastFetchTime = fetchTime;
		abortController = new AbortController();

		try {
			const res = await fetch(`${API_BASE}/live-sessions/active`, {
				signal: abortController.signal
			});
			if (fetchTime !== lastFetchTime) return;

			if (res.ok) {
				sessions = await res.json();
				error = null;
			} else {
				error = 'Failed to fetch';
			}
		} catch (e) {
			if (e instanceof Error && e.name === 'AbortError') return;
			if (fetchTime !== lastFetchTime) return;
			error = 'Cannot connect to API';
		} finally {
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

	function projectName(session: LiveSessionSummary): string {
		const parts = session.cwd.split('/').filter(Boolean);
		const skip = ['Users', 'home', 'Documents', 'GitHub', 'Projects', 'repos', 'src'];
		for (let i = parts.length - 1; i >= 0; i--) {
			const part = parts[i];
			if (!skip.includes(part) && part.length > 2) {
				if (i > 0 && ['frontend', 'backend', 'api', 'src', 'app'].includes(part)) {
					return parts[i - 1] || part;
				}
				return part;
			}
		}
		return parts[parts.length - 1] || 'Unknown';
	}

	function sessionUrl(session: LiveSessionSummary): string {
		if (!session.project_encoded_name) return '#';
		const identifier = getSessionDisplayLabel(session.session_id, session.slug);
		return projectHrefFromSession(session, `/${identifier}`);
	}

	function canNavigate(session: LiveSessionSummary): boolean {
		return !!session.project_encoded_name;
	}

	onMount(() => {
		fetchSessions();
		pollInterval = setInterval(fetchSessions, POLL_MS);
	});

	onDestroy(() => {
		if (pollInterval) clearInterval(pollInterval);
		if (abortController) abortController.abort();
	});
</script>

<!-- Hide the strip entirely once loaded with no sessions and no error (pure launcher). -->
{#if loading || error || sessions.length > 0}
	<div class="strip">
		<div class="strip-header">
			<span class="cmd">$ live-sessions</span>
			<div class="meta">
				<span class="count">
					{#if loading}
						[…]
					{:else if error}
						[error]
					{:else}
						[{counts.active} active, {counts.stale} stale]
					{/if}
				</span>
				<a href="/sessions" class="view-all">view all →</a>
			</div>
		</div>

		<div class="rows">
			{#if loading}
				<div class="muted-row">Loading…</div>
			{:else if error}
				<div class="muted-row">{error} — is the API running on port 8000?</div>
			{:else}
				{#each recent as session (session.session_id)}
					{@const config = statusConfig[session.status]}
					{@const canLink = canNavigate(session)}
					<svelte:element
						this={canLink ? 'a' : 'div'}
						href={canLink ? sessionUrl(session) : undefined}
						class="row"
						class:clickable={canLink}
					>
						<span class="left">
							<span
								class="dot"
								class:pulse={config.pulse}
								style="background: {config.color}"
							></span>
							<span class="id"
								>{getSessionDisplayLabel(session.session_id, session.slug)}</span
							>
							<span
								class="badge"
								style="color: {config.color}; background: {config.bgTint}"
								>{config.label}</span
							>
							<span class="project" title={session.cwd}>{projectName(session)}</span>
						</span>
						<span class="time">{formatDuration(session.duration_seconds)}</span>
					</svelte:element>
				{/each}
			{/if}
		</div>
	</div>
{/if}

<style>
	.strip {
		background: var(--bg-subtle);
		border: 1px solid var(--border);
		border-radius: var(--radius-md, 8px);
		overflow: hidden;
	}

	.strip-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 9px 14px;
		border-bottom: 1px solid var(--border-subtle);
	}

	.cmd {
		font-family: var(--font-mono);
		font-size: 11.5px;
		font-weight: 500;
		color: var(--nav-teal, #0891b2);
	}

	.meta {
		display: flex;
		align-items: center;
		gap: 10px;
	}

	.count {
		font-family: var(--font-mono);
		font-size: 10.5px;
		color: var(--text-faint);
	}

	.view-all {
		font-size: 11px;
		font-weight: 500;
		color: var(--accent);
		text-decoration: none;
	}

	.view-all:hover {
		text-decoration: underline;
	}

	.rows {
		display: flex;
		flex-direction: column;
		gap: 7px;
		padding: 8px 14px;
	}

	.muted-row {
		font-family: var(--font-mono);
		font-size: 11px;
		color: var(--text-faint);
	}

	.row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
		text-decoration: none;
		color: inherit;
		border-radius: var(--radius-sm, 4px);
		padding: 1px 0;
	}

	.row.clickable:hover {
		background: var(--bg-muted);
	}

	.left {
		display: flex;
		align-items: center;
		gap: 8px;
		min-width: 0;
	}

	.dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		flex-shrink: 0;
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

	.id {
		font-family: var(--font-mono);
		font-size: 11px;
		color: var(--accent);
		white-space: nowrap;
	}

	.badge {
		font-size: 9.5px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		border-radius: 3px;
		padding: 1px 5px;
		flex-shrink: 0;
	}

	.project {
		font-family: var(--font-mono);
		font-size: 10px;
		color: var(--text-muted);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.time {
		font-family: var(--font-mono);
		font-size: 10px;
		color: var(--text-faint);
		flex-shrink: 0;
		font-variant-numeric: tabular-nums;
	}
</style>
