<script lang="ts">
	import { Check, SquareArrowOutUpRight, Terminal, X } from 'lucide-svelte';
	import { API_BASE } from '$lib/config';

	let { sessionId, variant = 'icon' }: { sessionId: string; variant?: 'icon' | 'label' } =
		$props();

	const IDLE_TITLE = 'Bring the terminal window running this session to the front';
	const FETCH_TIMEOUT_MS = 10_000;
	let busy = $state(false);
	let feedback = $state<'idle' | 'ok' | 'err'>('idle');
	let title = $state(IDLE_TITLE);
	let announcement = $state('');
	let resetTimeout: ReturnType<typeof setTimeout> | null = null;
	let abort: AbortController | null = null;

	$effect(() => () => {
		if (resetTimeout) clearTimeout(resetTimeout);
		abort?.abort();
	});

	async function focusTerminal(event: MouseEvent) {
		// Sits above stretched row links (z-index below) — never navigate on click.
		event.preventDefault();
		event.stopPropagation();
		if (busy) return;
		busy = true;
		abort = new AbortController();
		const abortTimer = setTimeout(() => abort?.abort(), FETCH_TIMEOUT_MS);
		try {
			const res = await fetch(`${API_BASE}/live-sessions/${sessionId}/focus-terminal`, {
				method: 'POST',
				signal: abort.signal
			});
			const data = await res.json().catch(() => null);
			feedback = res.ok && data?.focused === true ? 'ok' : 'err';
			if (data?.detail) title = data.detail;
		} catch {
			feedback = 'err';
			title = 'Could not reach the API to focus the terminal.';
		} finally {
			clearTimeout(abortTimer);
			busy = false;
			announcement = feedback === 'ok' ? 'Terminal focused' : 'Could not focus the terminal';
			if (resetTimeout) clearTimeout(resetTimeout);
			resetTimeout = setTimeout(() => {
				feedback = 'idle';
				title = IDLE_TITLE;
				announcement = '';
			}, 2000);
		}
	}
</script>

<button
	type="button"
	onclick={focusTerminal}
	disabled={busy}
	aria-label="Focus this session's terminal window"
	class="focus-btn {variant}"
	class:ok={feedback === 'ok'}
	class:err={feedback === 'err'}
	{title}
>
	{#if feedback === 'ok'}
		<Check size={12} strokeWidth={2} />
	{:else if feedback === 'err'}
		<X size={12} strokeWidth={2} />
	{:else if variant === 'icon'}
		<Terminal size={12} strokeWidth={1.75} />
	{:else}
		<SquareArrowOutUpRight size={11} strokeWidth={2} />
	{/if}
	{#if variant === 'label'}
		{#if feedback === 'ok'}
			<span>opened!</span>
		{:else if feedback === 'err'}
			<span>failed</span>
		{:else}
			<span>terminal</span>
		{/if}
	{/if}
	<span class="sr-only" aria-live="polite">{announcement}</span>
</button>

<style>
	.focus-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 4px;
		border: 1px solid transparent;
		border-radius: var(--radius-md);
		background: transparent;
		color: var(--text-muted);
		cursor: pointer;
		flex-shrink: 0;
		/* Stay clickable above stretched row links. */
		position: relative;
		z-index: 1;
		transition:
			color var(--duration-fast),
			background var(--duration-fast),
			border-color var(--duration-fast);
	}

	.focus-btn.label {
		padding: 4px 8px;
		font-size: 12px;
		/* Reserve width so terminal → opened!/failed doesn't shift neighbors. */
		min-width: 5.5rem;
	}

	/* Teal chip — ties into the "$ live-sessions" terminal motif (see agent-badge). */
	.focus-btn.icon {
		padding: 4px;
		color: var(--nav-teal, #0891b2);
		background: var(--nav-teal-subtle, rgba(8, 145, 178, 0.1));
	}

	.focus-btn:hover:not(:disabled) {
		color: var(--accent);
		border-color: var(--border);
	}

	.focus-btn.icon:hover:not(:disabled) {
		color: var(--nav-teal, #0891b2);
		border-color: var(--nav-teal, #0891b2);
	}

	/* Rows already hover to --bg-muted; only the label variant adds its own bg. */
	.focus-btn.label:hover:not(:disabled) {
		background: var(--bg-muted);
	}

	.focus-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.focus-btn.ok {
		color: var(--success);
	}

	.focus-btn.err {
		color: var(--error);
	}

	.focus-btn.icon.ok {
		background: var(--success-subtle);
	}

	.focus-btn.icon.err {
		background: var(--error-subtle);
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
