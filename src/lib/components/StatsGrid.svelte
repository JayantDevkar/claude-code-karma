<script lang="ts">
	import type { Component } from 'svelte';
	import type { StatItem } from '$lib/api-types';
	import StatsCard from './StatsCard.svelte';

	interface Props {
		stats: StatItem[];
		columns?: 2 | 3 | 4 | 5;
		class?: string;
	}

	let { stats, columns = 4, class: className = '' }: Props = $props();

	// Responsive column classes based on the columns prop
	const columnClasses: Record<number, string> = {
		2: 'grid-cols-1 sm:grid-cols-2',
		3: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-3',
		4: 'grid-cols-1 sm:grid-cols-2 lg:grid-cols-4',
		5: 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-5'
	};
</script>

<div class="grid gap-3 stagger-children {columnClasses[columns]} {className}">
	{#each stats as stat}
		<StatsCard
			title={stat.title}
			value={stat.value}
			description={stat.description}
			icon={stat.icon}
			color={stat.color}
			tokenIn={stat.tokenIn}
			tokenOut={stat.tokenOut}
		/>
	{/each}
</div>
