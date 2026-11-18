<script lang="ts">
	import type { TimelineEvent } from '$lib/api-types';
	import { highlightPlainText } from '$lib/utils/highlight';
	import ActorBadge from './ActorBadge.svelte';
	import MessageRoute from './MessageRoute.svelte';
	import { getDisplayTitle, getEventBadges, type EventBadge } from './timeline-display';

	/** Title plus sender of an event. The card and the popup both render this, so they cannot disagree. */
	interface Props {
		event: TimelineEvent;
		currentAgentId?: string | null;
		/** Builds a link to an agent of this session, or null when the route is unknown */
		agentHref?: (agentId: string) => string | null;
		/** Link to the parent session, on an agent's page */
		mainSessionHref?: string | null;
		searchQuery?: string;
		titleClass?: string;
	}

	let {
		event,
		currentAgentId = null,
		agentHref,
		mainSessionHref = null,
		searchQuery = '',
		titleClass = 'font-medium text-[var(--text-primary)]'
	}: Props = $props();

	const displayTitle = $derived(getDisplayTitle(event));
	const badges = $derived(getEventBadges(event, currentAgentId));
	const trailingBadges = $derived(
		[badges.actor, badges.sender, badges.spawned, badges.taskAgent].filter(
			(b): b is EventBadge => b !== null
		)
	);
</script>

{#snippet badge(b: EventBadge)}
	<ActorBadge
		label={b.label}
		secondary={b.secondary}
		kind={b.kind}
		colors={b.colors}
		prefix={b.prefix}
		href={b.agentId && agentHref
			? agentHref(b.agentId)
			: b.isMainSession
				? mainSessionHref
				: null}
		title={b.title}
		{searchQuery}
	/>
{/snippet}

{#if event.event_type === 'message'}
	<!-- The route line is the title: who sent it and to whom -->
	<MessageRoute {event} {currentAgentId} {agentHref} {mainSessionHref} {searchQuery} />
{:else if badges.idle}
	{@render badge(badges.idle)}
	<span class={titleClass}>is idle</span>
{:else}
	<span class="min-w-0 {titleClass} [overflow-wrap:anywhere]">
		{#if searchQuery}{@html highlightPlainText(
				displayTitle,
				searchQuery
			)}{:else}{displayTitle}{/if}
	</span>
{/if}

{#each trailingBadges as b (b.title)}
	{@render badge(b)}
{/each}
