<script lang="ts">
	import { Copy, CheckCircle } from 'lucide-svelte';
	import { copyToClipboard } from '$lib/utils';

	let { code, label = 'Share this with teammates to let them join:' }: { code: string; label?: string } = $props();

	let copied = $state(false);

	async function handleCopy() {
		const ok = await copyToClipboard(code);
		if (ok) {
			copied = true;
			setTimeout(() => (copied = false), 2000);
		}
	}
</script>

<div class="space-y-2">
	{#if label}
		<p class="text-sm text-[var(--text-secondary)]">{label}</p>
	{/if}
	<div
		class="flex items-center gap-2 p-3 rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)]"
	>
		<code
			class="flex-1 text-xs font-mono text-[var(--text-primary)] break-all select-all leading-relaxed"
		>
			{code}
		</code>
		<button
			onclick={handleCopy}
			class="shrink-0 p-2 rounded-md hover:bg-[var(--bg-muted)] text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
			title="Copy to clipboard"
		>
			{#if copied}
				<CheckCircle size={16} class="text-[var(--success)]" />
			{:else}
				<Copy size={16} />
			{/if}
		</button>
	</div>
</div>
