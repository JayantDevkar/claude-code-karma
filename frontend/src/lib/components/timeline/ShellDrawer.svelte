<script lang="ts">
	import { onMount } from 'svelte';
	import { API_BASE } from '$lib/config';
	import type { TimelineEvent } from '$lib/api-types';
	import { ExternalLink } from 'lucide-svelte';

	interface Props {
		event: TimelineEvent;
		sessionUuid: string;
		encodedName: string;
	}

	let { event, sessionUuid }: Props = $props();

	// Parse command from tool_input
	const toolInput = $derived.by(() => {
		try { return JSON.parse(String(event.metadata?.tool_input ?? '{}')); }
		catch { return {}; }
	});
	const command = $derived(
		(toolInput.command as string | undefined) ||
		(toolInput.cmd as string | undefined) ||
		'(no command)'
	);

	// Output — prefer stored result_content, else fetch
	let output = $state<string | null>(event.metadata?.result_content as string ?? null);
	let loading = $state(output == null);
	let fetchError = $state(false);

	onMount(async () => {
		if (output != null) { loading = false; return; }
		// Try to fetch tool result via session tools endpoint
		try {
			const r = await fetch(`${API_BASE}/sessions/${sessionUuid}/tools`);
			if (!r.ok) throw new Error();
			const tools = await r.json() as { tool_use_id?: string; result?: string; tool_name?: string; input?: unknown }[];
			// Match by command text since we don't have tool_use_id easily
			const match = tools.find(t =>
				t.tool_name === 'Bash' &&
				JSON.stringify(t.input).includes(command.slice(0, 40).replace(/[.*+?^${}()|[\]\\]/g, '\\$&').slice(0, 30))
			);
			output = match?.result ?? null;
		} catch {
			fetchError = true;
		} finally {
			loading = false;
		}
	});

	// Split output into lines for display
	const lines = $derived((output ?? '').split('\n'));
	const isError = $derived(
		typeof event.metadata?.is_error === 'boolean'
			? event.metadata.is_error
			: (output ?? '').toLowerCase().includes('error:') || (output ?? '').startsWith('Error')
	);
</script>

<div class="flex flex-col h-full font-mono text-sm">
	<!-- Command block -->
	<div class="px-5 py-4 border-b border-[var(--border)]/60 bg-[var(--bg-subtle)]">
		<div class="flex items-center gap-2 mb-2">
			<span class="text-[var(--text-faint)] text-xs">$</span>
			<span class="text-[var(--text-primary)] font-semibold whitespace-pre-wrap break-all leading-relaxed">{command}</span>
		</div>
		<a
			href="/shells"
			class="inline-flex items-center gap-1 text-xs text-[var(--text-faint)] hover:text-[var(--accent)] transition-colors"
		>
			<ExternalLink size={11} strokeWidth={2} />
			View all shells
		</a>
	</div>

	<!-- Output -->
	<div class="flex-1 overflow-y-auto px-5 py-4">
		{#if loading}
			<div class="flex items-center gap-2 text-[var(--text-faint)] italic">
				<span class="animate-pulse">▊</span>
				<span>Loading output…</span>
			</div>
		{:else if fetchError && output == null}
			<p class="text-[var(--text-faint)] italic">Output not available — run this session to capture it.</p>
		{:else if output == null || output.trim() === ''}
			<p class="text-[var(--text-faint)] italic">(no output)</p>
		{:else}
			<div class="space-y-0 {isError ? 'text-[var(--error)]' : 'text-[var(--text-secondary)]'}">
				{#each lines as line, i (i)}
					<div class="leading-relaxed whitespace-pre-wrap break-all min-h-[1.5em]">{line}</div>
				{/each}
			</div>
		{/if}
	</div>
</div>
