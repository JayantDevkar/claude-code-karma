<script lang="ts">
	import { Flame, TrendingUp, Activity } from 'lucide-svelte';
	import { type UsageTier, tierConfigs } from '$lib/utils';

	interface Props {
		tier: UsageTier;
	}

	let { tier }: Props = $props();
	let config = $derived(tierConfigs[tier]);

	const icons = {
		'very-high': Flame,
		high: TrendingUp,
		medium: Activity,
		low: Activity
	} as const;
	let TierIcon = $derived(icons[tier]);
</script>

{#if tier !== 'low'}
	<div
		class="flex items-center gap-1 px-2 py-1 rounded-full transition-all duration-300"
		style="background-color: {config.bg};"
		title="{config.label} usage tier"
	>
		<TierIcon size={12} strokeWidth={2.5} style="color: {config.iconColor};" />
		<span class="text-xs font-semibold" style="color: {config.iconColor};">
			{config.label}
		</span>
	</div>
{/if}
