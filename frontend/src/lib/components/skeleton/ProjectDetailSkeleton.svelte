<script lang="ts">
	import SkeletonBox from './SkeletonBox.svelte';
	import SkeletonText from './SkeletonText.svelte';
	import SkeletonStatsCard from './SkeletonStatsCard.svelte';
	import SkeletonSessionCard from './SkeletonSessionCard.svelte';
</script>

<div>
	<!-- Breadcrumb -->
	<div class="mb-2">
		<SkeletonText width="200px" size="xs" />
	</div>

	<!-- Header -->
	<div class="mb-6">
		<SkeletonText width="250px" size="xl" class="mb-2" />
		<SkeletonText width="350px" size="sm" />
	</div>

	<!-- Stats Grid -->
	<div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-6">
		{#each Array(5) as _}
			<SkeletonStatsCard />
		{/each}
	</div>

	<!-- Tabs -->
	<div class="flex items-center gap-2 mb-6 border-b border-[var(--border)]">
		{#each Array(5) as _, i}
			<SkeletonBox
				width={i === 0 ? '90px' : '80px'}
				height="36px"
				rounded="sm"
				class="mb-[-1px]"
			/>
		{/each}
	</div>

	<!-- Session Cards Grid -->
	<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
		{#each Array(6) as _}
			<SkeletonSessionCard />
		{/each}
	</div>
</div>
