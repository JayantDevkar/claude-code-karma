<script lang="ts">
	import { Hourglass, Ban, CloudOff } from 'lucide-svelte';
	import { endedByLabel, type EndedBy } from '$lib/utils/endedBy';
	import { getNow } from '$lib/stores/clock.svelte';

	interface Props {
		endedBy?: EndedBy | null;
		resetsAt?: string | null;
		size?: 'sm' | 'md';
	}

	let { endedBy = null, resetsAt = null, size = 'sm' }: Props = $props();

	let info = $derived(endedByLabel(endedBy, resetsAt, getNow()));
	let iconSize = $derived(size === 'md' ? 12 : 10);
	let textClass = $derived(size === 'md' ? 'text-xs' : 'text-[11px]');
	let color = $derived(
		info?.tone === 'warning'
			? 'var(--warning)'
			: info?.tone === 'error'
				? 'var(--error)'
				: 'var(--text-muted)'
	);
</script>

{#if info}
	<div
		class="flex items-center gap-1 px-2 py-0.5 rounded-full border max-w-full min-w-0"
		style="color: {color}; background: color-mix(in srgb, {color} 12%, transparent); border-color: color-mix(in srgb, {color} 35%, transparent);"
		title="{info.label}. {info.tooltip}"
	>
		{#if endedBy === 'limit'}
			<Hourglass size={iconSize} strokeWidth={2} aria-hidden="true" class="shrink-0" />
		{:else if endedBy === 'refusal'}
			<Ban size={iconSize} strokeWidth={2} aria-hidden="true" class="shrink-0" />
		{:else}
			<CloudOff size={iconSize} strokeWidth={2} aria-hidden="true" class="shrink-0" />
		{/if}
		<span class="font-medium {textClass} truncate min-w-0">{info.label}</span>
	</div>
{/if}
