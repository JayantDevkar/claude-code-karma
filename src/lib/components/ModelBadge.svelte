<script lang="ts">
	import { Sparkles } from 'lucide-svelte';
	import { getModelDisplayName, getModelDisplayNameCompact } from '$lib/utils';

	interface Props {
		modelName: string;
		variant?: 'default' | 'compact';
		class?: string;
	}

	let { modelName, variant = 'default', class: className = '' }: Props = $props();

	const displayName = $derived(
		variant === 'compact'
			? getModelDisplayNameCompact(modelName)
			: getModelDisplayName(modelName)
	);

	// Color based on model family - using CSS variable tokens
	const colorClass = $derived.by(() => {
		if (modelName.includes('opus'))
			return 'bg-[var(--model-opus-subtle)] text-[var(--model-opus)] border-[var(--model-opus)]/40';
		if (modelName.includes('sonnet'))
			return 'bg-[var(--model-sonnet-subtle)] text-[var(--model-sonnet)] border-[var(--model-sonnet)]/40';
		if (modelName.includes('haiku'))
			return 'bg-[var(--model-haiku-subtle)] text-[var(--model-haiku)] border-[var(--model-haiku)]/40';
		return 'bg-[var(--bg-muted)] text-[var(--text-secondary)] border-[var(--border)]';
	});
</script>

{#if variant === 'compact'}
	<span
		class="
			inline-flex items-center gap-1
			px-1.5 py-0.5
			text-[10px] font-medium
			rounded
			border
			{colorClass}
			{className}
		"
	>
		{displayName}
	</span>
{:else}
	<span
		class="
			inline-flex items-center gap-1.5
			px-3 py-1.5
			text-sm font-medium
			rounded-md
			border
			{colorClass}
			{className}
		"
	>
		<Sparkles size={14} strokeWidth={2} />
		{displayName}
	</span>
{/if}
