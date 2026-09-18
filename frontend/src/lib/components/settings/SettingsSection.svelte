<script lang="ts">
	import type { Snippet } from 'svelte';
	import { ChevronDown } from 'lucide-svelte';
	import { slide } from 'svelte/transition';

	interface Props {
		title: string;
		children: Snippet;
		class?: string;
		open?: boolean;
		onToggle?: () => void;
	}

	let { title, children, class: className = '', open = false, onToggle }: Props = $props();
</script>

<div
	class="border border-[var(--border)] rounded-lg bg-[var(--bg-base)] overflow-hidden {className}"
>
	<button
		type="button"
		onclick={onToggle}
		aria-expanded={open}
		class="w-full flex items-center justify-between gap-2 px-5 py-3 bg-[var(--bg-subtle)] hover:bg-[var(--bg-muted)] text-left transition-colors {open
			? 'border-b border-[var(--border)]'
			: ''}"
	>
		<h2 class="text-xs font-medium text-[var(--text-secondary)] uppercase tracking-wider">
			{title}
		</h2>
		<ChevronDown
			size={14}
			class="text-[var(--text-muted)] transition-transform duration-200 shrink-0 {open
				? ''
				: '-rotate-90'}"
		/>
	</button>
	{#if open}
		<div class="divide-y divide-[var(--border)]" transition:slide={{ duration: 200 }}>
			{@render children()}
		</div>
	{/if}
</div>
