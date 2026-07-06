<script lang="ts">
	import { closeDrawer } from '$lib/stores/drawer';
	import { X } from 'lucide-svelte';

	interface Props {
		title: string;
		subtitle?: string;
		children: import('svelte').Snippet;
	}

	let { title, subtitle, children }: Props = $props();

	function onBackdropClick() { closeDrawer(); }

	function onKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') closeDrawer();
	}
</script>

<svelte:window onkeydown={onKeydown} />

<!-- Backdrop -->
<button
	type="button"
	class="fixed inset-0 z-40 bg-black/30 backdrop-blur-[1px] cursor-default"
	aria-label="Close drawer"
	onclick={onBackdropClick}
></button>

<!-- Drawer panel -->
<div
	class="fixed right-0 top-0 bottom-0 z-50 flex flex-col w-[520px] max-w-[95vw]
		bg-[var(--bg-base)] border-l border-[var(--border)]
		shadow-2xl"
	style="animation: slideIn 180ms cubic-bezier(0.16,1,0.3,1);"
>
	<!-- Header -->
	<div class="flex items-start justify-between gap-3 px-5 py-4 border-b border-[var(--border)]">
		<div class="min-w-0">
			<h2 class="font-mono text-sm font-semibold text-[var(--text-primary)] truncate">{title}</h2>
			{#if subtitle}
				<p class="font-mono text-xs text-[var(--text-faint)] mt-0.5 truncate">{subtitle}</p>
			{/if}
		</div>
		<button
			type="button"
			onclick={closeDrawer}
			class="shrink-0 p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-muted)] transition-colors"
			aria-label="Close"
		>
			<X size={16} strokeWidth={2} />
		</button>
	</div>

	<!-- Scrollable body -->
	<div class="flex-1 overflow-y-auto min-h-0">
		{@render children()}
	</div>
</div>

<style>
	@keyframes slideIn {
		from { transform: translateX(100%); opacity: 0.5; }
		to   { transform: translateX(0);    opacity: 1; }
	}
</style>
