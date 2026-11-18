<script lang="ts">
	import { ArrowRight, Bot, SquareTerminal } from 'lucide-svelte';
	import type { TimelineEvent } from '$lib/api-types';
	import { highlightPlainText } from '$lib/utils/highlight';
	import { getMessageRoute, type RouteParty } from './timeline-display';

	interface Props {
		event: TimelineEvent;
		currentAgentId?: string | null;
		/** Builds a link to an agent of this session, or null when the route is unknown */
		agentHref?: (agentId: string) => string | null;
		/** Link to the parent session, on an agent's page */
		mainSessionHref?: string | null;
		searchQuery?: string;
	}

	let {
		event,
		currentAgentId = null,
		agentHref,
		mainSessionHref = null,
		searchQuery = ''
	}: Props = $props();

	const route = $derived(getMessageRoute(event, currentAgentId));
</script>

{#snippet name(p: RouteParty)}
	<span class="[overflow-wrap:anywhere]">
		{#if searchQuery}{@html highlightPlainText(p.label, searchQuery)}{:else}{p.label}{/if}
		{#if p.secondary}<span class="ml-0.5 text-[11px] font-normal opacity-75">{p.secondary}</span
			>{/if}
	</span>
{/snippet}

{#snippet party(p: RouteParty)}
	{#if p.kind === 'self'}
		<span class="font-sans text-[var(--text-secondary)]">{p.label}</span>
	{:else}
		{@const href =
			p.agentId && agentHref
				? agentHref(p.agentId)
				: p.isMainSession
					? mainSessionHref
					: (p.sessionHref ?? null)}
		{@const Icon = p.kind === 'session' ? SquareTerminal : Bot}
		{@const fullName = p.secondary ? `${p.label} ${p.secondary}` : p.label}
		{@const kindLabel = p.kind === 'session' ? 'Session' : 'Agent'}
		<!-- items-start keeps the icon beside the first line when a long name wraps -->
		{#if href}
			<a
				{href}
				title="Open {kindLabel.toLowerCase()}: {fullName}"
				class="inline-flex min-w-0 items-start gap-1 no-underline hover:underline"
				style="color: {p.colors?.color}"
				onclick={(e) => e.stopPropagation()}
				onkeydown={(e) => e.stopPropagation()}
			>
				<Icon class="mt-[3px] h-3.5 w-3.5 shrink-0" aria-hidden="true" />
				{@render name(p)}
			</a>
		{:else}
			<span
				title="{kindLabel}: {fullName}"
				class="inline-flex min-w-0 items-start gap-1"
				style="color: {p.colors?.color}"
			>
				<Icon class="mt-[3px] h-3.5 w-3.5 shrink-0" aria-hidden="true" />
				{@render name(p)}
			</span>
		{/if}
	{/if}
{/snippet}

<span
	class="inline-flex min-w-0 flex-wrap items-start gap-x-1.5 gap-y-0.5 font-mono text-sm font-medium"
>
	<span class="sr-only">Message,</span>
	{@render party(route.from)}
	<ArrowRight class="mt-[3px] h-3.5 w-3.5 shrink-0 text-[var(--text-muted)]" aria-hidden="true" />
	<span class="sr-only">to</span>
	{@render party(route.to)}
</span>
