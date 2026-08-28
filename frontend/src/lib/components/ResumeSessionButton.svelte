<script lang="ts">
	import { Check, Play, X } from 'lucide-svelte';
	import { API_BASE } from '$lib/config';
	import { copyToClipboard } from '$lib/utils';

	let { sessionUuid }: { sessionUuid: string } = $props();

	const IDLE_TITLE =
		'Resume this session: opens a terminal, cds into the project, and runs claude --resume. ' +
		'If the session is still running, its terminal is focused instead. Alt-click to copy the command.';
	const FETCH_TIMEOUT_MS = 15_000;

	let busy = $state(false);
	let feedback = $state<'idle' | 'ok' | 'err' | 'copied'>('idle');
	let title = $state(IDLE_TITLE);
	let announcement = $state('');
	let resetTimeout: ReturnType<typeof setTimeout> | null = null;
	let abort: AbortController | null = null;
	let destroyed = false;

	$effect(() => () => {
		destroyed = true;
		if (resetTimeout) clearTimeout(resetTimeout);
		abort?.abort();
	});

	function scheduleReset(delay = 2000) {
		if (resetTimeout) clearTimeout(resetTimeout);
		resetTimeout = setTimeout(() => {
			feedback = 'idle';
			title = IDLE_TITLE;
			announcement = '';
		}, delay);
	}

	async function handleClick(event: MouseEvent) {
		// Sits inside the card's stretched link — never navigate on click.
		event.preventDefault();
		event.stopPropagation();
		if (busy) return;

		// Escape hatch: alt-click keeps the old copy-the-command behavior.
		if (event.altKey) {
			await copyToClipboard(`claude --resume ${sessionUuid}`);
			feedback = 'copied';
			scheduleReset(700);
			return;
		}

		busy = true;
		abort = new AbortController();
		const abortTimer = setTimeout(() => abort?.abort(), FETCH_TIMEOUT_MS);
		try {
			const res = await fetch(`${API_BASE}/sessions/${sessionUuid}/resume-in-terminal`, {
				method: 'POST',
				signal: abort.signal
			});
			const data = await res.json().catch(() => null);
			feedback = res.ok && data?.ok === true ? 'ok' : 'err';
			title = data?.detail || (res.ok ? title : 'The resume request failed.');
		} catch {
			feedback = 'err';
			title = 'Could not reach the API to resume this session.';
		} finally {
			clearTimeout(abortTimer);
			if (!destroyed) {
				busy = false;
				announcement =
					feedback === 'ok'
						? 'Session opened in terminal'
						: 'Could not resume the session';
				scheduleReset();
			}
		}
	}
</script>

<button
	type="button"
	onclick={handleClick}
	disabled={busy}
	aria-label="Resume this session in a terminal"
	class="resume-btn"
	class:ok={feedback === 'ok'}
	class:err={feedback === 'err'}
	{title}
>
	{#if feedback === 'ok'}
		<Check size={10} strokeWidth={2} />
	{:else if feedback === 'err'}
		<X size={10} strokeWidth={2} />
	{:else}
		<Play size={10} strokeWidth={2} />
	{/if}
	<span class="resume-label">
		{#if busy}
			opening…
		{:else if feedback === 'ok'}
			opened!
		{:else if feedback === 'err'}
			failed
		{:else if feedback === 'copied'}
			copied!
		{:else}
			resume
		{/if}
	</span>
	<span class="sr-only" aria-live="polite">{announcement}</span>
</button>

<style>
	/* Matches the card's badge pills (Desktop / model chips). */
	.resume-btn {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		padding: 2px 8px;
		border: 1px solid var(--border);
		border-radius: 999px;
		background: var(--bg-muted);
		color: var(--text-secondary);
		cursor: pointer;
		/* Stay clickable above the card's stretched link. */
		position: relative;
		z-index: 1;
		transition:
			color var(--duration-fast),
			border-color var(--duration-fast);
	}

	.resume-btn:hover:not(:disabled) {
		color: var(--accent);
		border-color: var(--accent);
	}

	.resume-btn:disabled {
		opacity: 0.6;
		cursor: wait;
	}

	.resume-btn.ok {
		color: var(--success);
		border-color: var(--success);
	}

	.resume-btn.err {
		color: var(--error);
		border-color: var(--error);
	}

	.resume-label {
		font-family: var(--font-mono, monospace);
		font-weight: 500;
		font-size: 11px;
		/* Reserve width so resume → opening…/opened! doesn't shift neighbors. */
		min-width: 3.6em;
		text-align: left;
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
