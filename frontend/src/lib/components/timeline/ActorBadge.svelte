<script lang="ts">
	import { Bot, SquareTerminal } from 'lucide-svelte';
	import type { ColorVars } from './timeline-display';
	import { highlightPlainText } from '$lib/utils/highlight';

	interface Props {
		label: string;
		/** Short id shown small after the label, for an agent labelled by its type */
		secondary?: string | null;
		/** agent: a subagent or teammate; session: another Claude session */
		kind?: 'agent' | 'session';
		colors: ColorVars;
		/** Short word before the name, e.g. "from" */
		prefix?: string;
		href?: string | null;
		/** Tooltip; defaults to the kind and the full name */
		title?: string;
		searchQuery?: string;
	}

	let {
		label,
		secondary = null,
		kind = 'agent',
		colors,
		prefix,
		href = null,
		title,
		searchQuery = ''
	}: Props = $props();

	const Icon = $derived(kind === 'session' ? SquareTerminal : Bot);
	const style = $derived(`color: ${colors.color}; background-color: ${colors.subtle};`);
	const fullName = $derived(secondary ? `${label} ${secondary}` : label);
	const tooltip = $derived(title ?? `${kind === 'session' ? 'Session' : 'Agent'}: ${fullName}`);
	// Names wrap rather than truncate: two agents must never read the same.
	const classes =
		'inline-flex max-w-full items-start gap-1 rounded-xl px-2 py-0.5 text-[11px] font-medium';
</script>

{#snippet body()}
	<Icon class="mt-[3px] h-3 w-3 shrink-0" aria-hidden="true" />
	{#if prefix}<span class="shrink-0 font-normal opacity-80">{prefix}</span>{/if}
	<span class="min-w-0 font-mono [overflow-wrap:anywhere]">
		{#if searchQuery}{@html highlightPlainText(label, searchQuery)}{:else}{label}{/if}
		{#if secondary}<span class="ml-0.5 text-[10px] font-normal opacity-75">{secondary}</span
			>{/if}
	</span>
{/snippet}

{#if href}
	<a
		{href}
		title={tooltip}
		{style}
		class="{classes} no-underline hover:underline"
		onclick={(e) => e.stopPropagation()}
		onkeydown={(e) => e.stopPropagation()}
	>
		{@render body()}
	</a>
{:else}
	<span title={tooltip} {style} class={classes}>
		{@render body()}
	</span>
{/if}
