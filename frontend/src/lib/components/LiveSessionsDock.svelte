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

	// Waiting rows first so the panel opens on what the pill announces; the stable sort keeps API order within each group.
	const sessions = $derived(
		[...visibleLiveSessions($liveSessionsFeed)].sort(
			(a, b) => Number(b.status === 'waiting') - Number(a.status === 'waiting')
		)
	);

	// Only "waiting" (blocked on you) earns motion — pulsing for merely-busy trains you to ignore it.
	const waitingCount = $derived(sessions.filter((s) => s.status === 'waiting').length);
	const waitingAnnouncement = $derived(
		waitingCount
			? `${waitingCount} ${waitingCount === 1 ? 'session' : 'sessions'} waiting on you`
			: ''
	);

	const shown = $derived(!hidden && sessions.length > 0);

	// app.css pads the footer clear of the pill while this is set; client-only, so SSR renders without it.
	$effect(() => {
		if (!shown) return;
		const root = document.documentElement;
		root.dataset.liveDock = 'true';
		return () => delete root.dataset.liveDock;
	});

	let expanded = $state(false);
	let container: HTMLDivElement | undefined = $state();
	let pill: HTMLButtonElement | undefined = $state();

	function collapse() {
		const focusInDock = !!container?.contains(document.activeElement);
		expanded = false;
		// The panel unmounts on collapse, so focus inside it would fall to <body>.
		if (focusInDock || document.activeElement === document.body) pill?.focus();
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape' && expanded && !e.defaultPrevented) collapse();
	}

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

<svelte:window onkeydown={handleKeydown} />

{#if shown}
	<!-- Pill before panel in the DOM so Tab after opening reaches the panel; column-reverse keeps the panel above. -->
	<div class="dock" bind:this={container} transition:scale={{ duration: 150, start: 0.9 }}>
		<button
			bind:this={pill}
			class="dock-pill"
			class:expanded
			class:attention={waitingCount > 0}
			onclick={() => (expanded = !expanded)}
			aria-expanded={expanded}
			aria-controls={expanded ? 'live-sessions-dock-panel' : undefined}
		>
			<span class="dock-icon" aria-hidden="true"><Radio size={16} strokeWidth={2} /></span>
			{#if waitingCount > 0}
				<span class="waiting-dot" aria-hidden="true"></span>
				<span class="dock-waiting"
					>{waitingCount} waiting<span class="sr-only">{' on you,'}</span></span
				>
				<span class="dock-sep" aria-hidden="true">·</span>
			{/if}
			<span class="dock-count"
				>{sessions.length} live<span class="sr-only"
					>{sessions.length === 1 ? ' session' : ' sessions'}</span
				></span
			>
			<span class="dock-chevron" aria-hidden="true"
				><ChevronUp size={16} strokeWidth={2} /></span
			>
		</button>

		{#if expanded}
			<div
				id="live-sessions-dock-panel"
				class="dock-panel"
				transition:scale={{ duration: 140, start: 0.94, opacity: 0 }}
			>
				<div class="dock-panel-header">
					<span class="dock-panel-title">
						<Radio size={15} strokeWidth={2} class="text-[var(--success)]" />
						Live sessions
					</span>
					<button class="dock-close" onclick={collapse} aria-label="Close live sessions">
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
	</div>
{/if}

<!-- Mounted outside the block so it exists before the first change; it only re-announces when the waiting count changes. -->
<span class="sr-only" role="status">{waitingAnnouncement}</span>

<style>
	.dock {
		position: fixed;
		right: var(--spacing-5);
		bottom: var(--spacing-5);
		/* Below modal scrims (50) so dialogs dim it; the header (50) never overlaps it. */
		z-index: 40;
		display: flex;
		flex-direction: column-reverse;
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

	/* Quiet while sessions just run; the whole pill escalates only when one is blocked on you. */
	.dock-pill {
		position: relative;
		display: inline-flex;
		align-items: center;
		gap: var(--spacing-2);
		min-height: 44px;
		padding: 0 var(--spacing-3) 0 var(--spacing-4);
		/* A real border, even when transparent, keeps the edge in forced-colors mode. */
		border: 1px solid var(--border-hover);
		border-radius: 999px;
		background: var(--bg-base);
		color: var(--text-primary);
		box-shadow: var(--shadow-elevated), var(--shadow-lg);
		font-size: 14px;
		font-weight: 600;
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
		cursor: pointer;
		transition:
			transform var(--duration-fast),
			border-color var(--duration-fast),
			background-color var(--duration-fast),
			color var(--duration-fast),
			box-shadow var(--duration-fast);
	}

	.dock-pill:hover {
		border-color: var(--accent);
		transform: translateY(-1px);
	}

	.dock-pill:active {
		transform: translateY(0);
	}

	.dock-pill:focus-visible {
		outline: var(--focus-ring-width) solid var(--focus-ring-color);
		outline-offset: var(--focus-ring-offset);
	}

	.dock-pill.attention {
		border-color: transparent;
		background: var(--info);
		color: var(--bg-base);
	}

	.dock-pill.attention:hover {
		border-color: transparent;
		box-shadow:
			0 0 0 3px var(--info-subtle),
			var(--shadow-elevated),
			var(--shadow-lg);
	}

	.dock-icon {
		display: inline-flex;
		color: var(--success);
	}

	.dock-pill.attention .dock-icon {
		color: inherit;
	}

	.dock-pill.attention .dock-count {
		font-weight: 500;
	}

	.dock-sep {
		opacity: 0.7;
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

	/* Phones: the waiting state keeps only "N waiting"; the live count stays in the accessible name. */
	@media (max-width: 480px) {
		.dock-pill.attention .dock-sep {
			display: none;
		}

		.dock-pill.attention .dock-count {
			position: absolute;
			width: 1px;
			height: 1px;
			margin: -1px;
			overflow: hidden;
			clip-path: inset(50%);
		}
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
		/* 24px target (36px on touch); the negative margin keeps the header at its old height. */
		min-width: 24px;
		min-height: 24px;
		margin: -2px;
		border: none;
		background: transparent;
		color: var(--text-muted);
		cursor: pointer;
		padding: 2px;
		border-radius: var(--radius-sm);
	}

	@media (pointer: coarse) {
		.dock-close {
			min-width: 36px;
			min-height: 36px;
			margin: -8px;
		}
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
