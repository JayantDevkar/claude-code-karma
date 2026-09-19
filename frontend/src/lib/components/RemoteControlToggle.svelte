<script lang="ts">
	import {
		RadioTower,
		ArrowUpRight,
		LoaderCircle,
		Check,
		X,
		HelpCircle,
		Clock,
		SquareArrowOutUpRight
	} from 'lucide-svelte';
	import { API_BASE } from '$lib/config';
	import type {
		LiveSessionStatus,
		RemoteControlState,
		RemoteControlToggleResult
	} from '$lib/api-types';

	let {
		sessionId,
		remoteControl = null,
		sessionStatus
	}: {
		sessionId: string;
		remoteControl?: RemoteControlState | null;
		sessionStatus: LiveSessionStatus;
	} = $props();

	const FETCH_TIMEOUT_MS = 20_000;
	const COOLDOWN_MS = 1200;
	const STAGED_TIMEOUT_MS = 15_000;
	const MENU_TIMEOUT_MS = 40_000; // "go finish it in your terminal" — give more room
	// The backend types /remote-control at any status except these: a dialog is
	// open (its trailing Enter could answer it), no REPL yet, or the process is
	// gone. During a tool run the slash command simply queues.
	const BLOCKED = new Set<LiveSessionStatus>(['waiting', 'starting', 'ended']);
	const CLAUDE_URL = /^https:\/\/claude\.ai\//i;

	let busy = $state(false); // request in flight or cooldown
	let staged = $state(false); // keys sent, waiting for the transcript to catch up
	let menuOpen = $state(false); // "off" click: the disconnect menu is open in the terminal
	let stagedBaseline = $state<string>('');
	let feedback = $state<'idle' | 'ok' | 'err' | 'retry'>('idle');
	let detailOverride = $state<string | null>(null);
	let announcement = $state('');
	let timers: ReturnType<typeof setTimeout>[] = [];
	let abort: AbortController | null = null;
	let destroyed = false;

	const rcState = $derived(remoteControl?.state ?? 'unknown');
	const isOn = $derived(rcState === 'on');
	const isUnknown = $derived(rcState === 'unknown');
	const safeUrl = $derived(
		remoteControl?.url && CLAUDE_URL.test(remoteControl.url) ? remoteControl.url : null
	);
	// Can the user click the toggle right now?
	const canToggle = $derived(
		!BLOCKED.has(sessionStatus) && !isUnknown && !busy && !staged && !menuOpen
	);
	// Visual mode drives the whole component's look.
	const mode = $derived(
		busy
			? 'busy'
			: menuOpen
				? 'menu'
				: staged
					? 'staged'
					: feedback !== 'idle'
						? feedback
						: rcState
	);

	// Clear the pending states as soon as the polled state moves off what it
	// was at send time (i.e. the user finished it in their terminal).
	$effect(() => {
		if ((staged || menuOpen) && rcState !== stagedBaseline) {
			staged = false;
			menuOpen = false;
		}
	});

	$effect(() => () => {
		destroyed = true;
		timers.forEach(clearTimeout);
		abort?.abort();
	});

	function later(fn: () => void, ms: number) {
		timers.push(setTimeout(fn, ms));
	}

	const disabledReason = $derived.by(() => {
		if (isUnknown)
			return "Karma can't read this session's Remote Control state — use /remote-control in the terminal.";
		if (BLOCKED.has(sessionStatus))
			return sessionStatus === 'waiting'
				? 'Answer the open prompt first, then toggle Remote Control.'
				: sessionStatus === 'starting'
					? 'Session is still starting up — try again in a moment.'
					: 'Session has ended.';
		return '';
	});

	const title = $derived.by(() => {
		if (detailOverride) return detailOverride;
		if (disabledReason) return disabledReason;
		if (staged) return 'Sent /remote-control — waiting for the session to confirm…';
		return isOn
			? 'Remote Control is on — reachable at claude.ai/code and in the Claude app. Click to open the disconnect menu in this session’s terminal.'
			: 'Turn on Remote Control: types /remote-control into this session’s terminal so you can pick it up on your phone.';
	});

	async function toggle(event: MouseEvent) {
		event.preventDefault();
		event.stopPropagation();
		if (!canToggle) return;

		const desired = isOn ? 'off' : 'on';
		busy = true;
		feedback = 'idle';
		detailOverride = null;
		abort = new AbortController();
		const abortTimer = setTimeout(() => abort?.abort(), FETCH_TIMEOUT_MS);
		try {
			const res = await fetch(`${API_BASE}/live-sessions/${sessionId}/remote-control`, {
				method: 'POST',
				headers: { 'content-type': 'application/json', 'x-karma-rc': '1' },
				body: JSON.stringify({ desired }),
				signal: abort.signal
			});
			const data: (RemoteControlToggleResult & { detail?: string }) | null = await res
				.json()
				.catch(() => null);

			if (res.ok && data) {
				detailOverride = data.detail ?? null;
				if (data.confirmed || data.state === desired) {
					feedback = 'ok';
					announcement = `Remote Control ${data.state}`;
					later(() => (feedback = 'idle'), 2500);
				} else if (data.method === 'menu-open') {
					// "off" click: the disconnect menu is open in the terminal —
					// the user finishes it there; our poll flips the pill to off.
					stagedBaseline = rcState;
					menuOpen = true;
					announcement = 'Disconnect menu opened in your terminal';
					later(() => (menuOpen = false), MENU_TIMEOUT_MS);
				} else if (data.sent) {
					stagedBaseline = rcState;
					staged = true;
					announcement = 'Sent — waiting for the session to confirm';
					later(() => (staged = false), STAGED_TIMEOUT_MS);
				} else {
					feedback = 'err';
					announcement = 'Could not toggle Remote Control';
					later(() => (feedback = 'idle'), 4000);
				}
			} else if (res.status === 409) {
				// Transient: session went busy between poll and click, or another
				// toggle is running, or state unreadable. Retryable, not broken.
				feedback = 'retry';
				detailOverride = data?.detail ?? 'Session is busy — try again in a moment.';
				announcement = 'Session busy — try again';
				later(() => (feedback = 'idle'), 4000);
			} else {
				feedback = 'err';
				detailOverride = data?.detail ?? `Toggle failed (${res.status}).`;
				announcement = 'Could not toggle Remote Control';
				later(() => (feedback = 'idle'), 4000);
			}
		} catch (e) {
			if (e instanceof Error && e.name === 'AbortError' && destroyed) return;
			feedback = 'err';
			detailOverride = 'Could not reach the API to toggle Remote Control.';
			later(() => (feedback = 'idle'), 4000);
		} finally {
			clearTimeout(abortTimer);
			if (!destroyed) later(() => (busy = false), COOLDOWN_MS);
		}
	}

	const reasonId = `rc-reason-${Math.random().toString(36).slice(2, 8)}`;
</script>

<span class="rc rc-{mode}" class:rc-locked={!canToggle}>
	<button
		type="button"
		class="rc-toggle"
		onclick={toggle}
		disabled={!canToggle}
		aria-disabled={!canToggle}
		role={isUnknown ? undefined : 'switch'}
		aria-checked={isUnknown ? undefined : isOn}
		aria-label="Toggle Remote Control for this session"
		aria-describedby={disabledReason ? reasonId : undefined}
		{title}
	>
		<span class="rc-icon" aria-hidden="true">
			{#if mode === 'busy' || mode === 'staged'}
				<LoaderCircle size={12} strokeWidth={2} class="rc-spin" />
			{:else if mode === 'menu'}
				<SquareArrowOutUpRight size={12} strokeWidth={2.25} />
			{:else if mode === 'ok'}
				<Check size={12} strokeWidth={2.5} />
			{:else if mode === 'retry'}
				<Clock size={12} strokeWidth={2.25} />
			{:else if mode === 'err'}
				<X size={12} strokeWidth={2.5} />
			{:else if mode === 'unknown'}
				<HelpCircle size={12} strokeWidth={2} />
			{:else}
				<RadioTower size={12} strokeWidth={2} />
			{/if}
		</span>
		<span class="rc-label">remote</span>
	</button>

	{#if isOn && safeUrl}
		<a
			class="rc-open"
			href={safeUrl}
			target="_blank"
			rel="noopener noreferrer"
			title="Open this session on claude.ai/code"
			aria-label="Open this session on claude.ai/code"
		>
			<ArrowUpRight size={12} strokeWidth={2.25} />
		</a>
	{/if}

	<span id={reasonId} class="sr-only">{disabledReason}</span>
	<span class="sr-only" aria-live="polite">{announcement}</span>
</span>

<style>
	.rc {
		display: inline-flex;
		align-items: stretch;
		border: 1px solid transparent;
		border-radius: var(--radius-md);
		overflow: hidden;
		background: transparent;
		position: relative;
		z-index: 1;
		transition:
			border-color var(--duration-fast) var(--ease),
			background-color var(--duration-fast) var(--ease);
	}

	.rc-toggle,
	.rc-open {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		padding: 4px 8px;
		font-size: 12px;
		line-height: 1;
		color: var(--text-muted);
		background: transparent;
		border: 0;
		cursor: pointer;
		transition:
			color var(--duration-fast) var(--ease),
			background-color var(--duration-fast) var(--ease);
	}

	.rc-icon {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 12px;
		height: 12px;
	}

	.rc-label {
		font-weight: 500;
		letter-spacing: 0.01em;
	}

	/* --- OFF: quiet ghost, matches the neighbouring "terminal" button --- */
	.rc-off:not(.rc-locked):hover {
		border-color: var(--border);
		background: var(--bg-muted);
	}

	/* --- ON: enclosed violet pill holding the open segment + its divider --- */
	.rc-on {
		border-color: color-mix(in srgb, var(--accent) 34%, transparent);
		background: var(--accent-subtle);
	}
	.rc-on .rc-toggle {
		color: var(--accent);
	}
	.rc-open {
		padding: 4px 6px;
		border-left: 1px solid color-mix(in srgb, var(--accent) 24%, transparent);
		color: var(--accent);
	}
	.rc-on .rc-toggle:not(:disabled):hover,
	.rc-open:hover {
		background: color-mix(in srgb, var(--accent) 12%, transparent);
		color: var(--accent);
	}

	/* --- PENDING (busy / staged / menu) + RETRY (409): amber, legible, never dimmed --- */
	.rc-busy,
	.rc-staged,
	.rc-menu,
	.rc-retry {
		border-color: color-mix(in srgb, var(--warning) 34%, transparent);
		background: color-mix(in srgb, var(--warning) 10%, transparent);
	}
	.rc-busy .rc-toggle,
	.rc-staged .rc-toggle,
	.rc-menu .rc-toggle,
	.rc-retry .rc-toggle {
		color: var(--warning);
	}

	/* --- UNKNOWN: outlined, not passable for "off" --- */
	.rc-unknown {
		border-color: color-mix(in srgb, var(--warning) 30%, transparent);
		border-style: dashed;
	}
	.rc-unknown .rc-toggle {
		color: var(--warning);
	}

	/* --- transient result colours --- */
	.rc-ok .rc-toggle {
		color: var(--success);
	}
	.rc-err {
		border-color: color-mix(in srgb, var(--error) 34%, transparent);
	}
	.rc-err .rc-toggle {
		color: var(--error);
	}

	/* Disabled toggle: no dimming of the pill — only the cursor + no hover. */
	.rc-toggle:disabled {
		cursor: not-allowed;
	}

	.rc-toggle:focus-visible,
	.rc-open:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: -2px;
	}

	:global(.rc-spin) {
		animation: rc-rotate 0.7s linear infinite;
	}
	@keyframes rc-rotate {
		to {
			transform: rotate(360deg);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		:global(.rc-spin) {
			animation-duration: 1.6s;
		}
	}

	.sr-only {
		position: absolute;
		width: 1px;
		height: 1px;
		padding: 0;
		margin: -1px;
		overflow: hidden;
		clip: rect(0, 0, 0, 0);
		white-space: nowrap;
		border: 0;
	}
</style>
