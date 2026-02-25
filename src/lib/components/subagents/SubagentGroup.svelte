<script lang="ts">
	import { ChevronDown, ChevronRight, Bot, Users, Activity } from 'lucide-svelte';
	import type { SubagentSummary, SubagentState } from '$lib/api-types';
	import SubagentCard from './SubagentCard.svelte';
	import SubagentTypeBadge from './SubagentTypeBadge.svelte';

	interface Props {
		type: string;
		agents: SubagentSummary[];
		defaultExpanded?: boolean;
		/** Encoded project name for navigation (optional - enables clickable navigation) */
		projectEncoded?: string;
		/** Session slug for navigation (optional - enables clickable navigation) */
		sessionSlug?: string;
		/** Live subagent states from hooks (optional - for real-time status) */
		liveSubagents?: Record<string, SubagentState>;
	}

	let {
		type,
		agents,
		defaultExpanded = false,
		projectEncoded,
		sessionSlug,
		liveSubagents = {}
	}: Props = $props();

	// Count running agents in this group (guard against null liveSubagents)
	let runningCount = $derived(
		agents.filter((a) => liveSubagents?.[a.agent_id]?.status === 'running').length
	);

	let isExpanded = $state<boolean | null>(null);
	let isOther = $derived(type === 'Other');

	// Use defaultExpanded on first render, then track state
	let effectiveExpanded = $derived(isExpanded === null ? defaultExpanded : isExpanded);

	// Group agents into pairs for proper expand behavior
	let agentPairs = $derived(
		agents.reduce<SubagentSummary[][]>((pairs, agent, i) => {
			if (i % 2 === 0) pairs.push([agent]);
			else pairs[pairs.length - 1].push(agent);
			return pairs;
		}, [])
	);

	function toggle() {
		isExpanded = !effectiveExpanded;
	}
</script>

<div class="rounded-lg border border-[var(--border)] bg-[var(--bg-base)]/50 overflow-hidden">
	<!-- Group header -->
	<button
		onclick={toggle}
		class="
			flex w-full items-center gap-3 px-4 py-3 text-left transition-colors
			hover:bg-[var(--bg-muted)]/50
			{effectiveExpanded ? 'border-b border-[var(--border)]' : ''}
		"
	>
		<!-- Chevron -->
		<div class="flex h-5 w-5 items-center justify-center text-[var(--text-muted)]">
			{#if effectiveExpanded}
				<ChevronDown size={16} strokeWidth={2} />
			{:else}
				<ChevronRight size={16} strokeWidth={2} />
			{/if}
		</div>

		<!-- Type badge or "Other" label -->
		{#if isOther}
			<span
				class="inline-flex items-center gap-1.5 rounded-full bg-[var(--bg-muted)] px-2.5 py-1 text-xs font-medium text-[var(--text-muted)]"
			>
				<Bot size={12} strokeWidth={2} />
				Other
			</span>
		{:else}
			<SubagentTypeBadge {type} size="md" />
		{/if}

		<!-- Agent count -->
		<span class="flex items-center gap-1 text-xs text-[var(--text-muted)]">
			<Users size={12} strokeWidth={2} />
			{agents.length} agent{agents.length !== 1 ? 's' : ''}
		</span>

		<!-- Running count indicator -->
		{#if runningCount > 0}
			<span
				class="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-[var(--success)]/10 text-[var(--success)]"
			>
				<Activity size={10} strokeWidth={2.5} class="animate-pulse" />
				{runningCount} running
			</span>
		{/if}

		<!-- Spacer -->
		<div class="flex-1"></div>

		<!-- Collapsed preview -->
		{#if !effectiveExpanded}
			<span class="text-xs text-[var(--text-muted)]/70"> Click to expand </span>
		{/if}
	</button>

	<!-- Collapsible content -->
	<div
		class="
			grid transition-all duration-200 ease-in-out
			{effectiveExpanded ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0'}
		"
	>
		<div class="overflow-hidden">
			<div class="p-4 flex flex-col gap-4">
				{#each agentPairs as pair, pairIndex (pairIndex)}
					<div class="subagent-pair grid gap-4 lg:grid-cols-2 items-start">
						{#each pair as subagent (subagent.agent_id)}
							{@const liveState = liveSubagents[subagent.agent_id]}
							<div class="subagent-card-wrapper">
								<SubagentCard
									{subagent}
									{projectEncoded}
									{sessionSlug}
									status={liveState?.status}
									started_at={liveState?.started_at}
									completed_at={liveState?.completed_at}
									transcript_path={liveState?.transcript_path}
								/>
							</div>
						{/each}
					</div>
				{/each}
			</div>
		</div>
	</div>
</div>

<style>
	/* Expanded card behavior within pairs */
	/* Using :global() because aria-expanded is on a child component */
	@media (min-width: 1024px) {
		/* Expanded card spans full width */
		.subagent-card-wrapper:global(:has([aria-expanded='true'])) {
			grid-column: span 2;
			order: -1; /* Always move expanded card to the top of its pair */
		}
	}
</style>
