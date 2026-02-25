<script lang="ts">
	import type { Snippet } from 'svelte';
	import { Loader2 } from 'lucide-svelte';

	interface Props {
		title: string;
		description?: string;
		hint?: string;
		saving?: boolean;
		success?: string | null;
		control: Snippet;
		class?: string;
	}

	let {
		title,
		description,
		hint,
		saving = false,
		success = null,
		control,
		class: className = ''
	}: Props = $props();
</script>

<div class="p-5 flex items-start justify-between gap-6 {className}">
	<div class="space-y-1.5 max-w-lg">
		<div class="flex items-center gap-2">
			<h3 class="text-sm font-medium text-[var(--text-primary)]">{title}</h3>
			{#if saving}
				<Loader2 size={12} class="animate-spin text-[var(--text-muted)]" />
			{/if}
			{#if success}
				<span
					class="text-xs text-green-600 dark:text-green-500 font-medium animate-fade-in"
				>
					{success}
				</span>
			{/if}
		</div>
		{#if description}
			<p class="text-[13px] leading-relaxed text-[var(--text-secondary)]">
				{description}
			</p>
		{/if}
		{#if hint}
			<p class="text-xs text-[var(--text-muted)]">{hint}</p>
		{/if}
	</div>
	<div class="flex items-center gap-3 shrink-0 pt-0.5">
		{@render control()}
	</div>
</div>
