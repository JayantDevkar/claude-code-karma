<script lang="ts">
	import { SquareArrowOutUpRight } from 'lucide-svelte';
	import { API_BASE } from '$lib/config';

	let { sessionId, variant = 'icon' }: { sessionId: string; variant?: 'icon' | 'label' } =
		$props();

	const IDLE_TITLE = 'Bring the terminal window running this session to the front';
	let busy = $state(false);
	let feedback = $state<'idle' | 'ok' | 'err'>('idle');
	let title = $state(IDLE_TITLE);
	let resetTimeout: ReturnType<typeof setTimeout> | null = null;

	async function focusTerminal(event: MouseEvent) {
		// Rows embed this button inside <a> — never navigate on click.
		event.preventDefault();
		event.stopPropagation();
		if (busy) return;
		busy = true;
		try {
			const res = await fetch(`${API_BASE}/live-sessions/${sessionId}/focus-terminal`, {
				method: 'POST'
			});
			const data = await res.json().catch(() => null);
			feedback = res.ok && data?.focused === true ? 'ok' : 'err';
			if (data?.detail) title = data.detail;
		} catch {
			feedback = 'err';
			title = 'Could not reach the API to focus the terminal.';
		} finally {
			busy = false;
			if (resetTimeout) clearTimeout(resetTimeout);
			resetTimeout = setTimeout(() => {
				feedback = 'idle';
				title = IDLE_TITLE;
			}, 2000);
		}
	}
</script>

<button
	type="button"
	onclick={focusTerminal}
	disabled={busy}
	aria-label="Open the terminal window running this session"
	class="focus-btn {variant}"
	class:ok={feedback === 'ok'}
	class:err={feedback === 'err'}
	{title}
>
	<SquareArrowOutUpRight size={11} strokeWidth={2} />
	{#if variant === 'label'}
		{#if feedback === 'ok'}
			<span>opened!</span>
		{:else if feedback === 'err'}
			<span>failed</span>
		{:else}
			<span>terminal</span>
		{/if}
	{/if}
</button>

<style>
	.focus-btn {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		border: 1px solid transparent;
		border-radius: var(--radius-md, 6px);
		background: transparent;
		color: var(--text-muted);
		cursor: pointer;
		flex-shrink: 0;
		transition:
			color var(--duration-fast, 120ms),
			background var(--duration-fast, 120ms),
			border-color var(--duration-fast, 120ms);
	}

	.focus-btn.label {
		padding: 4px 8px;
		font-size: 12px;
	}

	.focus-btn.icon {
		padding: 3px;
	}

	.focus-btn:hover:not(:disabled) {
		color: var(--accent);
		background: var(--bg-muted);
		border-color: var(--border);
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
</style>
