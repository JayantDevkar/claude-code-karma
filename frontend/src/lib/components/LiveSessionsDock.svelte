<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { scale } from 'svelte/transition';
	import { page } from '$app/stores';
	import { afterNavigate } from '$app/navigation';
	import { ChevronUp, FolderOpen, Radio, X } from 'lucide-svelte';
	import { liveSessionsFeed } from '$lib/stores/liveSessionsFeed';
	import { statusConfig } from '$lib/live-session-config';
	import TerminalFocusButton from '$lib/components/TerminalFocusButton.svelte';
	import {
		formatDuration,
		getProjectDisplayName,
		getSessionUrl,
		canNavigate,
		getDisplayName,
		matchesRoute,
		visibleLiveSessions
	} from '$lib/utils/live-session-display';

	// Hidden where the full live-sessions table already renders — the dock would be a copy.
	const HIDDEN_ROUTES = new Set(['/', '/sessions']);
	const hidden = $derived(HIDDEN_ROUTES.has($page.url.pathname));

	const sessions = $derived(visibleLiveSessions($liveSessionsFeed));

	// Only "waiting" (blocked on you) earns motion — pulsing for merely-busy trains you to ignore it.
	const waitingCount = $derived(sessions.filter((s) => s.status === 'waiting').length);

	let expanded = $state(false);
	let container: HTMLDivElement | undefined = $state();

	// Collapse after navigation, not on row click — unmounting the anchor mid-click cancels it.
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
						<Radio size={15} strokeWidth={2} class="text-[var(--success)]" />
						Live sessions
					</span>
					<button
						class="dock-close"
						onclick={() => (expanded = false)}
						aria-label="Collapse"
					>
						<X size={17} strokeWidth={2} />
					</button>
				</div>
				<div class="dock-list">
					{#each sessions as session (session.session_id)}
						{@const config = statusConfig[session.status]}
						{@const current = matchesRoute($page.url.pathname, session)}
						{@const linkable = canNavigate(session) && !current}
						<!-- bgTint stays on every row — hover and "you are here" layer over it. -->
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
									<!-- Status as text too — dot color alone fails color-blind and reduced-motion users. -->
									<span class="status-label" style="color: {config.color}"
										>{config.label.toUpperCase()}</span
									>
									{#if current}
										<span class="here-badge">you are here</span>
									{/if}
								</div>
								<div class="dock-row-secondary">
									<span class="project" title={session.cwd}>
										<FolderOpen size={13} strokeWidth={2} />
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
			class:expanded
			onclick={() => (expanded = !expanded)}
			aria-expanded={expanded}
			aria-label={`${sessions.length} live sessions${waitingCount ? `, ${waitingCount} waiting on you` : ''}`}
		>
			<Radio size={16} strokeWidth={2} />
			<span class="dock-count">{sessions.length} live</span>
			{#if waitingCount > 0}
				<span class="dock-waiting">
					<span class="waiting-dot"></span>
					{waitingCount} waiting
				</span>
			{/if}
			<span class="dock-chevron"><ChevronUp size={16} strokeWidth={2} /></span>
		</button>
	</div>
{/if}

<style>
	.dock {
		position: fixed;
		right: var(--spacing-5);
		bottom: var(--spacing-5);
		/* Below modal scrims (50) so dialogs dim it; the header (50) never overlaps it. */
		z-index: 40;
		display: flex;
		flex-direction: column;
		align-items: flex-end;
		gap: var(--spacing-2);
		/* Grows from its bottom-right anchor — centre scaling reads as diagonal drift. */
		transform-origin: bottom right;
	}

	@media (max-width: 480px) {
		.dock {
			right: var(--spacing-4);
			bottom: var(--spacing-4);
		}
	}

	/* Inverted surface so the launcher never reads as another card, in either theme. */
	.dock-pill {
		display: inline-flex;
		align-items: center;
		gap: var(--spacing-2);
		min-height: 44px;
		padding: 0 var(--spacing-3) 0 var(--spacing-4);
		border: none;
		border-radius: 999px;
		background: var(--text-primary);
		color: var(--bg-base);
		box-shadow: var(--shadow-lg);
		font-size: 14px;
		font-weight: 600;
		cursor: pointer;
		transition:
			transform var(--duration-fast),
			box-shadow var(--duration-fast);
	}

	.dock-pill:hover {
		transform: translateY(-1px);
		box-shadow: var(--shadow-elevated), var(--shadow-lg);
	}

	.dock-pill:active {
		transform: translateY(0);
	}

	.dock-pill:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 3px;
	}

	.dock-count {
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
	}

	/* The one state that earns colour: a session blocked on you. */
	.dock-waiting {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		padding: 3px 10px 3px 8px;
		border-radius: 999px;
		background: var(--info);
		color: var(--bg-base);
		font-size: 13px;
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
	}

	.waiting-dot {
		width: 7px;
		height: 7px;
		border-radius: 50%;
		background: currentColor;
		animation: dock-pulse 2s ease infinite;
	}

	.dock-chevron {
		display: inline-flex;
		opacity: 0.7;
		transition: transform var(--duration-fast);
	}

	.dock-pill.expanded .dock-chevron {
		transform: rotate(180deg);
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
		width: min(400px, calc(100vw - 2 * var(--spacing-4)));
		max-height: 75vh;
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
		padding: 10px 15px;
		border-bottom: 1px solid var(--border-subtle);
		background: var(--bg-muted);
	}

	.dock-panel-title {
		display: inline-flex;
		align-items: center;
		gap: 7px;
		font-size: 14px;
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
		gap: 10px;
		padding: 10px 15px;
		border-bottom: 1px solid var(--border-subtle);
		background-color: var(--row-tint, transparent);
		transition: background-color var(--duration-fast);
	}

	.dock-row:last-child {
		border-bottom: none;
	}

	/* Hover layers over the status wash — a row keeps its meaning under the pointer. */
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
		width: 9px;
		height: 9px;
		border-radius: 50%;
		flex-shrink: 0;
		margin-top: 6px;
	}

	.status-dot.pulse {
		animation: dock-pulse 2s ease infinite;
	}

	.dock-row-info {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}

	.dock-row-primary {
		display: flex;
		align-items: center;
		min-width: 0;
		gap: 7px;
	}

	/* Names are body text; accent is reserved for marking where you are. */
	.dock-row-name {
		font-size: 15px;
		color: var(--text-primary);
		font-weight: 500;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.dock-row.current .dock-row-name {
		color: var(--accent);
	}

	.status-label {
		flex-shrink: 0;
		font-size: 11px;
		font-weight: 600;
		letter-spacing: 0.5px;
	}

	/* The most useful marker in the list, so it reads as one. */
	.here-badge {
		flex-shrink: 0;
		padding: 1px 6px;
		border-radius: var(--radius-sm);
		font-size: 11px;
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
		gap: 10px;
		font-size: 14px;
		color: var(--text-muted);
	}

	.project {
		display: flex;
		align-items: center;
		gap: 5px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.duration {
		flex-shrink: 0;
		font-variant-numeric: tabular-nums;
		/* --text-faint fails AA at this size. */
		color: var(--text-muted);
	}

	.dock-row-actions {
		position: relative;
		z-index: 1;
		display: flex;
		align-items: center;
		gap: 5px;
		flex-shrink: 0;
	}

	@media (prefers-reduced-motion: reduce) {
		.waiting-dot,
		.status-dot.pulse {
			animation: none;
		}

		.dock-pill,
		.dock-chevron {
			transition: none;
		}

		.dock-pill:hover {
			transform: none;
		}
	}
</style>
