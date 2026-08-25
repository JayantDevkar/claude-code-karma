<script lang="ts">
	import { Copy, Check } from 'lucide-svelte';

	interface Props {
		text: string;
		title?: string;
		size?: number;
		class?: string;
	}

	let { text, title = 'Copy', size = 14, class: className = '' }: Props = $props();

	let copied = $state(false);

	async function handleCopy(e: MouseEvent) {
		e.stopPropagation();
		try {
			await navigator.clipboard.writeText(text);
			copied = true;
			setTimeout(() => (copied = false), 2000);
		} catch (err) {
			console.error('Copy to clipboard failed:', err);
		}
	}
</script>

<button
	type="button"
	onclick={handleCopy}
	class="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors shrink-0 {className}"
	title={copied ? 'Copied!' : title}
>
	{#if copied}
		<Check size={size} class="text-[var(--success)]" />
	{:else}
		<Copy size={size} />
	{/if}
</button>
