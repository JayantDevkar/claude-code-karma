<script lang="ts">
	import { Copy, CheckCircle, Share2 } from 'lucide-svelte';
	import { copyToClipboard } from '$lib/utils';

	let { code, label = 'Share this code with teammates to let them join:' }: { code: string; label?: string } = $props();

	let copied = $state(false);

	async function handleCopy() {
		const ok = await copyToClipboard(code);
		if (ok) {
			copied = true;
			setTimeout(() => (copied = false), 2000);
		}
	}
</script>

<div class="rounded-xl border border-[var(--accent)]/25 bg-gradient-to-br from-[var(--accent)]/5 to-transparent p-5">
	<div class="flex items-start gap-3 mb-4">
		<div class="p-2 rounded-lg bg-[var(--accent)]/10">
			<Share2 size={18} class="text-[var(--accent)]" />
		</div>
		<div>
			<h3 class="text-sm font-semibold text-[var(--text-primary)]">Invite Teammates</h3>
			{#if label}
				<p class="text-xs text-[var(--text-muted)] mt-0.5">{label}</p>
			{/if}
		</div>
	</div>
	<div class="flex items-center gap-3">
		<div class="flex-1 px-4 py-3 rounded-lg bg-[var(--bg-base)] border border-[var(--border)] font-mono text-base text-[var(--text-primary)] tracking-wider select-all text-center">
			{code}
		</div>
		<button
			onclick={handleCopy}
			class="shrink-0 flex items-center gap-2 px-4 py-3 rounded-lg font-medium text-sm transition-colors
				{copied
					? 'bg-[var(--success)]/15 text-[var(--success)] border border-[var(--success)]/25'
					: 'bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)]'}"
			title="Copy to clipboard"
			aria-label="Copy join code to clipboard"
		>
			{#if copied}
				<CheckCircle size={16} />
				Copied
			{:else}
				<Copy size={16} />
				Copy
			{/if}
		</button>
	</div>
</div>
