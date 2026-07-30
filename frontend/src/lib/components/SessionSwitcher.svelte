<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { Clock, Bot, Pause } from 'lucide-svelte';
	import { commandPalette } from '$lib/stores/commandPalette';
	import { sessionSwitcherStore } from '$lib/stores/sessionSwitcher';
	import { liveSessionsFeed } from '$lib/stores/liveSessionsFeed';
	import { statusConfig } from '$lib/live-session-config';
	import type { LiveSessionSummary } from '$lib/api-types';
	import {
		formatDuration,
		formatIdleTime,
		getProjectDisplayName,
		getSessionUrl,
		canNavigate,
		getDisplayName,
		matchesRoute
	} from '$lib/utils/live-session-display';

	// Cmd+B — both keys sit under the left hand, unlike Cmd+K.
	// (Cmd+E was tried first but Chrome on Mac reserves it at the browser-chrome
	// level — "search with selected text" — so the keydown never reaches page JS.
	// Cmd+B has no default Chrome/macOS binding.)
	const SWITCH_KEY = 'b';

	const sessions = $derived(
		$liveSessionsFeed.filter((s) => s.status !== 'ended' && s.transcript_exists !== false)
	);

	let isOpen = $state(false);
	let index = $state(0);

	// --- display-only derivations (no bearing on open/commit behaviour) ---

	// Tiles shrink as the roster grows so 2 and ~12 sessions both sit on one row.
	// +25% over the original 76/62/50 px, per Ayush's request to match the dock resize.
	const density = $derived(
		sessions.length <= 6
			? { tile: 95, gap: 15 }
			: sessions.length <= 10
				? { tile: 78, gap: 11 }
				: { tile: 63, gap: 8 }
	);

	const selected = $derived(sessions[index]);

	/** Two-letter project mark — the "app icon" identity of a tile. */
	function monogram(session: LiveSessionSummary): string {
		const name = getProjectDisplayName(session).replace(/[^a-zA-Z0-9]/g, '');
		return name.slice(0, 2).toUpperCase() || '··';
	}

	function openAt(startIndex: number) {
		isOpen = true;
		index = startIndex;
	}

	// Skip past whatever session we're already on, same as Cmd+Tab landing on
	// the "other" window first. Shared by the Cmd+B first-press and the
	// footer button (which has no "current session" of its own to skip via
	// held-key repeats, so it needs the same starting point).
	function openFromCurrent() {
		if (sessions.length === 0) return;
		const currentIdx = sessions.findIndex((s) => matchesRoute($page.url.pathname, s));
		openAt(currentIdx >= 0 ? (currentIdx + 1) % sessions.length : 0);
	}

	function advance() {
		if (sessions.length === 0) return;
		index = (index + 1) % sessions.length;
	}

	function commit() {
		const session = sessions[index];
		isOpen = false;
		sessionSwitcherStore.close();
		if (!session) return;
		// Route-only: focus-terminal raises the native Terminal window on top of
		// Chrome, which would steal focus the instant you land here and hide the
		// very page you just switched to. Terminal jump stays a deliberate,
		// separate action on the dock's own button.
		if (canNavigate(session)) goto(getSessionUrl(session, 'timeline'));
	}

	function cancel() {
		isOpen = false;
		sessionSwitcherStore.close();
	}

	// Opened via the footer button (mouse, no Cmd held) — sync from the store.
	$effect(() => {
		if ($sessionSwitcherStore.isOpen && !isOpen) {
			openFromCurrent();
		}
	});

	// Clicking the dimmed backdrop is the only way to cancel a mouse-opened
	// switcher — there's no Cmd being held to release.
	function handleBackdropClick(e: MouseEvent) {
		if (e.target === e.currentTarget) cancel();
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key.toLowerCase() === SWITCH_KEY && e.metaKey && !e.ctrlKey && !e.altKey) {
			if (commandPalette.getIsOpen()) return;
			if (sessions.length === 0) return;
			e.preventDefault();

			if (!isOpen) {
				openFromCurrent();
			} else {
				advance();
			}
			return;
		}

		if (isOpen && e.key === 'Escape') {
			e.preventDefault();
			cancel();
		}
	}

	function handleKeyup(e: KeyboardEvent) {
		if (isOpen && e.key === 'Meta') {
			commit();
		}
	}

	function handleBlur() {
		if (isOpen) cancel();
	}

	function handleVisibilityChange() {
		if (isOpen && document.hidden) cancel();
	}

	onMount(() => {
		liveSessionsFeed.start();
		window.addEventListener('keydown', handleKeydown);
		window.addEventListener('keyup', handleKeyup);
		window.addEventListener('blur', handleBlur);
		document.addEventListener('visibilitychange', handleVisibilityChange);
	});

	onDestroy(() => {
		liveSessionsFeed.stop();
		// onDestroy also fires during SSR teardown, where onMount never ran and
		// window/document don't exist — guard so that doesn't throw.
		if (typeof window === 'undefined') return;
		window.removeEventListener('keydown', handleKeydown);
		window.removeEventListener('keyup', handleKeyup);
		window.removeEventListener('blur', handleBlur);
		document.removeEventListener('visibilitychange', handleVisibilityChange);
	});
</script>

{#if isOpen}
	<!-- Escape is already handled globally by handleKeydown above; this click
	     handler is the mouse-only equivalent for a switcher opened without
	     Cmd held (via the footer button), so no separate keyboard handler
	     is needed on the element itself. -->
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<div
		class="switcher-overlay"
		role="dialog"
		aria-modal="true"
		aria-label="Live session switcher"
		tabindex="-1"
		onclick={handleBackdropClick}
	>
		<div
			class="switcher-frame"
			style="--n: {sessions.length}; --tile: {density.tile}px; --gap: {density.gap}px; --i: {index}"
		>
			<div class="strip-scroll">
				<div class="switcher-strip">
					<div class="strip-plate"></div>
					{#each sessions as session, i (session.session_id)}
						{@const config = statusConfig[session.status]}
						<div
							class="switcher-tile"
							class:selected={i === index}
							class:here={matchesRoute($page.url.pathname, session)}
							style="--tone: {config.color}"
							role="button"
							tabindex="0"
							aria-label={`Switch to ${getDisplayName(session)}`}
							onmouseenter={() => (index = i)}
							onclick={() => {
								index = i;
								commit();
							}}
							onkeydown={(e) => {
								if (e.key === 'Enter' || e.key === ' ') {
									e.preventDefault();
									index = i;
									commit();
								}
							}}
						>
							<div class="tile-art">
								<div class="tile-icon">
									<span class="tile-mark font-mono">{monogram(session)}</span>
								</div>
								<span class="tile-status" class:pulse={config.pulse}></span>
								{#if session.active_subagent_count > 0}
									<span class="tile-agents font-mono"
										>{session.active_subagent_count}</span
									>
								{/if}
							</div>
							<!-- Session name, not just the project monogram: two sessions in the
							     same repo would otherwise render as identical tiles. -->
							<span class="tile-label font-mono">{getDisplayName(session)}</span>
						</div>
					{/each}
				</div>
			</div>

			<div class="switcher-detail">
				{#if selected}
					{@const config = statusConfig[selected.status]}
					<!-- The tile label already shows the session id/slug — the big
					     readout should answer "which project", not repeat it. -->
					<div class="detail-name font-mono" aria-live="polite">
						{getProjectDisplayName(selected)}
					</div>
					<!-- Single line, never wrapping: a second line would grow the frame
					     mid-cycle and shift the tiles under the user's fingers. -->
					<div class="detail-meta">
						<span class="meta-status" style="--tone: {config.color}">
							<span class="meta-dot"></span>{config.label}
						</span>
						{#if selected.active_subagent_count > 0}
							<span class="meta-item accent"
								><Bot size={14} strokeWidth={2} />
								{selected.active_subagent_count}</span
							>
						{/if}
						<span class="meta-item"
							><Clock size={14} strokeWidth={2} />
							{formatDuration(selected.duration_seconds)}</span
						>
						{#if selected.idle_seconds >= 60}
							<span class="meta-item"
								><Pause size={14} strokeWidth={2} />
								{formatIdleTime(selected.idle_seconds)} idle</span
							>
						{/if}
					</div>
				{/if}
			</div>

			<div class="switcher-hint">
				<span>hold <kbd>⌘</kbd> — tap <kbd>B</kbd> to cycle, release to jump</span>
				<span class="hint-sep"></span>
				<span><kbd>esc</kbd> cancel</span>
			</div>
		</div>
	</div>
{/if}

<style>
	.switcher-overlay {
		position: fixed;
		inset: 0;
		/* Just under the command palette's 9998 — the palette wins if both open. */
		z-index: 9997;
		display: flex;
		align-items: center;
		justify-content: center;
		/* Same black as the command palette's scrim, lighter: this HUD is a
		   transient hold-to-cycle overlay, not a place you stop and work.
		   No backdrop-filter — a full-viewport blur is the one thing that could
		   make a keypress-triggered HUD arrive late, and it buys nothing under
		   a 42% wash. The frame keeps its own glass. */
		background: rgba(0, 0, 0, 0.42);
		animation: overlayIn 80ms linear;
	}

	/* --- HUD frame ------------------------------------------------------ */

	.switcher-frame {
		/* Sized from the tile roster so the panel never jitters as the
		   selected session's name changes length underneath it. */
		width: min(92vw, max(475px, calc(var(--n) * var(--tile) + (var(--n) - 1) * var(--gap) + 40px)));
		padding: 20px 20px 0;
		background: color-mix(in srgb, var(--bg-base) 82%, transparent);
		border: 1px solid var(--border);
		border-radius: calc(var(--radius-lg) * 2);
		backdrop-filter: blur(24px) saturate(180%);
		box-shadow:
			inset 0 1px 0 rgba(255, 255, 255, 0.07),
			0 2px 6px rgba(0, 0, 0, 0.18),
			0 32px 64px -16px rgba(0, 0, 0, 0.55);
		animation: hudIn 140ms cubic-bezier(0.2, 0.9, 0.3, 1);
	}

	.strip-scroll {
		overflow-x: auto;
		scrollbar-width: none;
	}

	.strip-scroll::-webkit-scrollbar {
		display: none;
	}

	.switcher-strip {
		position: relative;
		display: flex;
		gap: var(--gap);
		width: max-content;
		margin-inline: auto;
	}

	/* Single highlight that slides between cells — reads as one continuous
	   selection rather than N independently-animating tiles. */
	.strip-plate {
		position: absolute;
		/* Stretched rather than given a height, so it always covers the full
		   tile (art + label) without hardcoding the tile's computed height. */
		top: 0;
		bottom: 0;
		left: 0;
		width: var(--tile);
		border-radius: var(--radius-lg);
		background: var(--bg-muted);
		box-shadow: inset 0 0 0 1px var(--accent-subtle);
		transform: translateX(calc(var(--i) * (var(--tile) + var(--gap))));
		transition: transform 160ms cubic-bezier(0.22, 1, 0.36, 1);
	}

	/* --- tiles ---------------------------------------------------------- */

	.switcher-tile {
		position: relative;
		flex: none;
		width: var(--tile);
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 5px;
		padding: calc(var(--tile) * 0.11) 0 5px;
		cursor: pointer;
	}

	.switcher-tile:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
		border-radius: var(--radius-lg);
	}

	.tile-art {
		position: relative;
		width: calc(var(--tile) * 0.78);
		height: calc(var(--tile) * 0.78);
	}

	.tile-icon {
		width: 100%;
		height: 100%;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: var(--radius-lg);
		border: 1px solid color-mix(in srgb, var(--tone) 34%, var(--border));
		background: linear-gradient(
			155deg,
			color-mix(in srgb, var(--tone) 24%, var(--bg-subtle)),
			color-mix(in srgb, var(--tone) 7%, var(--bg-subtle))
		);
		box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.1);
		/* Unselected tiles stay readable — you pick a session by scanning the
		   whole roster, so dimming everything but the current selection defeats
		   the point. Selection is already carried by the plate, ring and scale. */
		opacity: 0.82;
		transform: scale(0.96);
		transition:
			opacity 110ms var(--ease),
			transform 130ms cubic-bezier(0.22, 1, 0.36, 1),
			box-shadow 110ms var(--ease);
	}

	.switcher-tile.selected .tile-icon {
		opacity: 1;
		transform: scale(1.04);
		box-shadow:
			inset 0 1px 0 rgba(255, 255, 255, 0.14),
			0 0 0 1.5px color-mix(in srgb, var(--tone) 55%, transparent),
			0 6px 16px -4px color-mix(in srgb, var(--tone) 45%, transparent);
	}

	.tile-mark {
		font-size: calc(var(--tile) * 0.3);
		font-weight: 600;
		letter-spacing: -0.02em;
		color: color-mix(in srgb, var(--tone) 65%, var(--text-primary));
	}

	/* Status badge, notification-dot style, overhanging the icon corner. */
	.tile-status {
		position: absolute;
		top: -3px;
		right: -3px;
		width: 11px;
		height: 11px;
		border-radius: 50%;
		background: var(--tone);
		border: 2px solid var(--bg-base);
		opacity: 0.55;
		transition: opacity 110ms var(--ease);
	}

	.switcher-tile.selected .tile-status {
		opacity: 1;
	}

	.tile-status.pulse {
		animation: badgePulse 2s ease infinite;
	}

	.tile-agents {
		position: absolute;
		bottom: -3px;
		right: -3px;
		min-width: 19px;
		height: 19px;
		padding: 0 4px;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 11px;
		font-weight: 600;
		line-height: 1;
		border-radius: 999px;
		background: var(--accent);
		color: var(--bg-base);
		border: 2px solid var(--bg-base);
		opacity: 0.55;
		transition: opacity 110ms var(--ease);
	}

	.switcher-tile.selected .tile-agents {
		opacity: 1;
	}

	.tile-label {
		max-width: 100%;
		font-size: 13px;
		line-height: 1.3;
		letter-spacing: -0.01em;
		color: var(--text-muted);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		transition: color 110ms var(--ease);
	}

	.switcher-tile.selected .tile-label {
		color: var(--text-primary);
		font-weight: 600;
	}

	/* Where you're standing right now — the tile Cmd+B skipped past. Carried by
	   the label's colour: a 2px faint dash under the tile was invisible. */
	.switcher-tile.here .tile-label {
		color: var(--accent);
	}

	.switcher-tile.selected.here .tile-label {
		color: var(--accent);
		font-weight: 600;
	}

	/* --- selected-session readout --------------------------------------- */

	.switcher-detail {
		min-height: 58px;
		padding-top: 15px;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 5px;
		text-align: center;
	}

	.detail-name {
		max-width: 100%;
		font-size: 18px;
		font-weight: 600;
		letter-spacing: -0.01em;
		color: var(--text-primary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.detail-meta {
		max-width: 100%;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-wrap: nowrap;
		gap: 10px;
		overflow: hidden;
		font-size: 14px;
		color: var(--text-muted);
	}

	.meta-status {
		display: inline-flex;
		align-items: center;
		flex: none;
		gap: 6px;
		white-space: nowrap;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.4px;
		font-size: 13px;
		color: var(--tone);
	}

	.meta-dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: var(--tone);
	}

	.meta-item {
		display: inline-flex;
		align-items: center;
		flex: none;
		gap: 5px;
		white-space: nowrap;
		font-variant-numeric: tabular-nums;
	}

	.meta-item.accent {
		color: var(--accent);
	}

	/* --- footer hint ---------------------------------------------------- */

	.switcher-hint {
		margin-top: 15px;
		padding: 10px 0;
		border-top: 1px solid var(--border-subtle);
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 10px;
		font-size: 14px;
		/* --text-faint at this size lands under AA; this line teaches the whole
		   interaction, so it gets the readable muted step instead. */
		color: var(--text-muted);
	}

	.hint-sep {
		width: 1px;
		height: 13px;
		background: var(--border);
	}

	.switcher-hint kbd {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-width: 23px;
		height: 23px;
		margin: 0 1px;
		padding: 0 6px;
		font-family: var(--font-sans);
		font-size: 13px;
		font-weight: 600;
		line-height: 1;
		background: var(--bg-muted);
		border: 1px solid var(--border);
		border-bottom-width: 2px;
		border-radius: var(--radius-sm);
		box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.08);
		color: var(--text-secondary);
	}

	@keyframes badgePulse {
		0%,
		100% {
			transform: scale(1);
		}
		50% {
			transform: scale(1.25);
		}
	}

	@keyframes overlayIn {
		from {
			opacity: 0;
		}
		to {
			opacity: 1;
		}
	}

	@keyframes hudIn {
		from {
			opacity: 0;
			transform: scale(0.96) translateY(6px);
		}
		to {
			opacity: 1;
			transform: none;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.switcher-overlay,
		.switcher-frame {
			animation: none;
		}

		.strip-plate,
		.tile-icon {
			transition: none;
		}

		.tile-status.pulse {
			animation: none;
		}
	}
</style>
