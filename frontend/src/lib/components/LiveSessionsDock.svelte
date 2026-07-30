<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { scale } from 'svelte/transition';
	import { page } from '$app/stores';
	import { afterNavigate } from '$app/navigation';
	import { FolderOpen, Radio, X } from 'lucide-svelte';
	import { liveSessionsFeed } from '$lib/stores/liveSessionsFeed';
	import { statusConfig } from '$lib/live-session-config';
	import TerminalFocusButton from '$lib/components/TerminalFocusButton.svelte';
	import {
		formatDuration,
		getProjectDisplayName,
		getSessionUrl,
		canNavigate,
		getDisplayName,
		matchesRoute
	} from '$lib/utils/live-session-display';

	// Hidden on routes that already render the full live-sessions table —
	// the dock would just be a redundant floating copy there.
	const HIDDEN_ROUTES = new Set(['/', '/sessions']);
	const hidden = $derived(HIDDEN_ROUTES.has($page.url.pathname));

	const sessions = $derived(
		$liveSessionsFeed.filter((s) => s.status !== 'ended' && s.transcript_exists !== false)
	);

	// "active" means Claude is working and needs nothing; "waiting" means it's
	// blocked on you. Only the second one earns motion — a dot that pulses
	// whenever a session is merely busy trains you to ignore it.
	const hasWorking = $derived(sessions.some((s) => s.status === 'active'));
	const needsInput = $derived(sessions.some((s) => s.status === 'waiting'));

	let expanded = $state(false);
	let container: HTMLDivElement | undefined = $state();

	// Close after navigation completes — NOT via onclick on the row link.
	// Collapsing synchronously inside the anchor's own click handler unmounts
	// the anchor (via {#if expanded}) before the browser processes its native
	// href navigation, which silently cancels the navigation.
	afterNavigate(() => {
		expanded = false;
	});

	function handleDocumentClick(e: MouseEvent) {
		if (expanded && container && !container.contains(e.target as Node)) {
			expanded = false;
		}
	}

	onMount(() => {
		liveSessionsFeed.start();
		document.addEventListener('click', handleDocumentClick);
	});

	onDestroy(() => {
		liveSessionsFeed.stop();
		if (typeof document !== 'undefined') {
			document.removeEventListener('click', handleDocumentClick);
		}
	});
</script>

{#if !hidden && sessions.length > 0}
	<div class="dock" bind:this={container} transition:scale={{ duration: 150, start: 0.9 }}>
		{#if expanded}
			<div class="dock-panel" transition:scale={{ duration: 140, start: 0.94, opacity: 0 }}>
				<div class="dock-panel-header">
					<span class="dock-panel-title">
						<Radio size={12} strokeWidth={2} class="text-[var(--success)]" />
						Live sessions
					</span>
					<button
						class="dock-close"
						onclick={() => (expanded = false)}
						aria-label="Collapse"
					>
						<X size={14} strokeWidth={2} />
					</button>
				</div>
				<div class="dock-list">
					{#each sessions as session (session.session_id)}
						{@const config = statusConfig[session.status]}
						{@const current = matchesRoute($page.url.pathname, session)}
						{@const linkable = canNavigate(session) && !current}
						<!-- bgTint is the app-wide status wash (SessionCard uses the same
						     token), and it stays on for the current row too — hover and
						     "you are here" layer on top instead of erasing the status. -->
						<div
							class="dock-row"
							class:current
							class:clickable={linkable}
							style="--row-tint: {config.bgTint}"
						>
							{#if linkable}
								<a
									class="row-link"
									href={getSessionUrl(session, 'timeline')}
									aria-label={`Open session ${getDisplayName(session)}`}
								></a>
							{/if}
							<span
								class="status-dot"
								class:pulse={config.pulse}
								style="background: {config.color}"
								title={config.label}
							></span>
							<div class="dock-row-info">
								<div class="dock-row-primary">
									<span class="dock-row-name font-mono"
										>{getDisplayName(session)}</span
									>
									{#if current}
										<span class="here-badge">you are here</span>
									{/if}
								</div>
								<div class="dock-row-secondary">
									<span class="project" title={session.cwd}>
										<FolderOpen size={10} strokeWidth={2} />
										{getProjectDisplayName(session)}
									</span>
									<span class="duration"
										>{formatDuration(session.duration_seconds)}</span
									>
								</div>
							</div>
							{#if session.can_focus_terminal}
								<div class="dock-row-actions">
									<TerminalFocusButton sessionId={session.session_id} />
								</div>
							{/if}
						</div>
					{/each}
				</div>
			</div>
		{/if}

		<button
			class="dock-pill"
			class:attention={needsInput}
			onclick={() => (expanded = !expanded)}
			aria-expanded={expanded}
			aria-label={needsInput ? 'Live sessions — one is waiting on you' : 'Live sessions'}
		>
			<span class="dock-icon">
				<Radio size={13} strokeWidth={2} />
			</span>
			<span class="dock-count">{sessions.length}</span>
			{#if needsInput || hasWorking}
				<span class="dock-badge" class:pulse={needsInput}></span>
			{/if}
		</button>
	</div>
{/if}

<style>
	.dock {
		position: fixed;
		right: var(--spacing-5);
		bottom: var(--spacing-5);
		/* Above the sticky header (50), below the command palette (9998) — an
		   always-on floating dock should never be painted under page chrome. */
		z-index: 60;
		display: flex;
		flex-direction: column;
		align-items: flex-end;
		gap: var(--spacing-2);
		/* Anchored bottom-right, so it should grow from there — scaling from the
		   centre reads as a diagonal drift. */
		transform-origin: bottom right;
	}

	.dock-pill {
		position: relative;
		display: inline-flex;
		align-items: center;
		gap: var(--spacing-2);
		padding: var(--spacing-2) var(--spacing-3) var(--spacing-2) var(--spacing-2);
		border: 1px solid var(--border);
		border-radius: 999px;
		background: var(--bg-base);
		color: var(--text-secondary);
		box-shadow: var(--shadow-lg);
		cursor: pointer;
		transition:
			background var(--duration-fast),
			border-color var(--duration-fast),
			color var(--duration-fast),
			transform var(--duration-fast);
	}

	.dock-pill:hover {
		background: var(--bg-subtle);
		color: var(--text-primary);
		border-color: var(--accent);
		transform: translateY(-1px);
	}

	.dock-pill:active {
		transform: translateY(0);
	}

	.dock-pill.attention {
		border-color: color-mix(in srgb, var(--info) 60%, var(--border));
	}

	.dock-icon {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 24px;
		height: 24px;
		border-radius: 50%;
		background: var(--nav-teal-subtle);
		color: var(--nav-teal);
	}

	.dock-count {
		font-size: 12px;
		font-weight: 600;
		font-variant-numeric: tabular-nums;
	}

	.dock-badge {
		position: absolute;
		top: -1px;
		right: -1px;
		width: 9px;
		height: 9px;
		border-radius: 50%;
		background: var(--success);
		border: 2px solid var(--bg-base);
	}

	.dock-badge.pulse {
		background: var(--info);
		animation: dock-pulse 2s ease infinite;
	}

	@keyframes dock-pulse {
		0%,
		100% {
			opacity: 1;
			transform: scale(1);
		}
		50% {
			opacity: 0.5;
			transform: scale(1.2);
		}
	}

	.dock-panel {
		width: 320px;
		max-height: 60vh;
		display: flex;
		flex-direction: column;
		background: var(--bg-base);
		border: 1px solid var(--border);
		border-radius: var(--radius-lg);
		box-shadow: var(--shadow-elevated);
		overflow: hidden;
		transform-origin: bottom right;
	}

	.dock-panel-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: var(--spacing-2) var(--spacing-3);
		border-bottom: 1px solid var(--border-subtle);
		background: var(--bg-muted);
	}

	.dock-panel-title {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		font-size: 11px;
		font-weight: 600;
		letter-spacing: 0.5px;
		color: var(--text-secondary);
		text-transform: uppercase;
	}

	.dock-close {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		border: none;
		background: transparent;
		color: var(--text-muted);
		cursor: pointer;
		padding: 2px;
		border-radius: var(--radius-sm);
	}

	.dock-close:hover {
		color: var(--text-primary);
		background: var(--bg-subtle);
	}

	.dock-list {
		overflow-y: auto;
	}

	.dock-row {
		position: relative;
		display: flex;
		align-items: flex-start;
		gap: var(--spacing-2);
		padding: var(--spacing-2) var(--spacing-3);
		border-bottom: 1px solid var(--border-subtle);
		background-color: var(--row-tint, transparent);
		transition: background-color var(--duration-fast);
	}

	.dock-row:last-child {
		border-bottom: none;
	}

	/* Hover is a layer over the status wash, not a replacement for it — a row
	   shouldn't lose its meaning the moment you point at it. */
	.dock-row.clickable:hover {
		background-image: linear-gradient(var(--accent-muted), var(--accent-muted));
	}

	.dock-row.current {
		box-shadow: inset 2px 0 0 var(--accent);
	}

	.row-link {
		position: absolute;
		inset: 0;
	}

	.row-link:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: -2px;
	}

	.status-dot {
		width: 7px;
		height: 7px;
		border-radius: 50%;
		flex-shrink: 0;
		margin-top: 5px;
	}

	.status-dot.pulse {
		animation: dock-pulse 2s ease infinite;
	}

	.dock-row-info {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 3px;
	}

	.dock-row-primary {
		display: flex;
		align-items: center;
		min-width: 0;
		gap: 6px;
	}

	/* Accent is the app's "this is a link" colour; spending it on every row name
	   flattens the list. Names are body text; accent marks where you are. */
	.dock-row-name {
		font-size: 12px;
		color: var(--text-primary);
		font-weight: 500;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.dock-row.current .dock-row-name {
		color: var(--accent);
	}

	/* The most useful marker in the list, so it reads as a marker — it was the
	   faintest colour in the system before. */
	.here-badge {
		flex-shrink: 0;
		padding: 1px 5px;
		border-radius: var(--radius-sm);
		font-size: 9px;
		font-weight: 600;
		letter-spacing: 0.3px;
		text-transform: uppercase;
		background: var(--accent-subtle);
		color: var(--accent);
	}

	.dock-row-secondary {
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
	}

	.duration {
		flex-shrink: 0;
		font-variant-numeric: tabular-nums;
		color: var(--text-faint);
	}

	.dock-row-actions {
		position: relative;
		z-index: 1;
		display: flex;
		align-items: center;
		gap: var(--spacing-1);
		flex-shrink: 0;
	}

	@media (prefers-reduced-motion: reduce) {
		.dock-badge.pulse,
		.status-dot.pulse {
			animation: none;
		}

		.dock-pill {
			transition: none;
		}

		.dock-pill:hover {
			transform: none;
		}
	}
</style>
