<script lang="ts">
	import { ChevronDown, ChevronRight, Folder } from 'lucide-svelte';
	import type { PlanWithContext } from '$lib/api-types';
	import PlanCard from './PlanCard.svelte';

	interface Props {
		projectName: string;
		projectEncoded: string;
		plans: PlanWithContext[];
		defaultExpanded?: boolean;
	}
	let { projectName, projectEncoded, plans, defaultExpanded = true }: Props = $props();

	let expanded = $state(defaultExpanded);
</script>

<div class="space-y-3">
	<button
		onclick={() => (expanded = !expanded)}
		class="flex items-center gap-2 w-full text-left group"
	>
		{#if expanded}
			<ChevronDown size={16} class="text-[var(--text-muted)]" />
		{:else}
			<ChevronRight size={16} class="text-[var(--text-muted)]" />
		{/if}
		<Folder size={16} class="text-[var(--accent)]" />
		<span class="font-medium text-[var(--text-primary)] group-hover:text-[var(--accent)]">
			{projectName}
		</span>
		<span class="text-xs text-[var(--text-muted)]">
			({plans.length} plan{plans.length !== 1 ? 's' : ''})
		</span>
	</button>

	{#if expanded}
		<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pl-6">
			{#each plans as plan (plan.slug)}
				<PlanCard {plan} />
			{/each}
		</div>
	{/if}
</div>
