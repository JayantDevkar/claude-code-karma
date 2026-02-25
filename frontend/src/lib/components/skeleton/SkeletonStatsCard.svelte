<script lang="ts">
	import SkeletonBox from './SkeletonBox.svelte';
	import SkeletonText from './SkeletonText.svelte';

	interface Props {
		showIcon?: boolean;
		class?: string;
	}

	let { showIcon = true, class: className = '' }: Props = $props();
</script>

<!-- Matches StatsCard.svelte structure -->
<div
	class="
		p-4
		bg-[var(--bg-subtle)]
		border border-[var(--border)]
		rounded-[var(--radius-lg)]
		{className}
	"
>
	<!-- Label at top -->
	<SkeletonText width="80px" size="xs" class="mb-2" />

	<!-- Icon + Value -->
	<div class="flex items-center gap-3">
		{#if showIcon}
			<SkeletonBox width="40px" height="40px" rounded="md" />
		{/if}
		<div class="flex-1 min-w-0">
			<SkeletonText width="60px" size="xl" />
		</div>
	</div>
</div>
