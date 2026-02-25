<script lang="ts">
	import SkeletonBox from './SkeletonBox.svelte';
	import SkeletonText from './SkeletonText.svelte';
	import SkeletonStatsCard from './SkeletonStatsCard.svelte';
</script>

<div>
	<!-- Breadcrumb -->
	<div class="mb-4">
		<SkeletonText width="300px" size="xs" />
	</div>

	<!-- Session Header -->
	<div class="mb-6">
		<div class="flex items-center gap-3 mb-2">
			<SkeletonBox width="12px" height="12px" rounded="full" />
			<SkeletonText width="150px" size="lg" />
		</div>
		<SkeletonText width="400px" size="sm" />
	</div>

	<!-- Context Summaries -->
	<div class="mb-6 p-4 bg-[var(--bg-subtle)] border border-[var(--border)] rounded-lg">
		<SkeletonText width="120px" size="sm" class="mb-3" />
		<div class="space-y-2">
			{#each Array(3) as _}
				<SkeletonText width="100%" size="sm" />
			{/each}
		</div>
	</div>

	<!-- Stats Cards -->
	<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 mb-6">
		{#each Array(6) as _}
			<SkeletonStatsCard />
		{/each}
	</div>

	<!-- Tabs -->
	<div class="flex items-center gap-2 mb-6 border-b border-[var(--border)]">
		{#each Array(5) as _}
			<SkeletonBox width="80px" height="36px" rounded="sm" class="mb-[-1px]" />
		{/each}
	</div>

	<!-- Timeline Events -->
	<div class="space-y-3">
		{#each Array(5) as _}
			<div
				class="flex gap-4 p-4 bg-[var(--bg-base)] border border-[var(--border)] rounded-lg"
			>
				<SkeletonBox width="32px" height="32px" rounded="md" />
				<div class="flex-1">
					<SkeletonText width="200px" size="sm" class="mb-2" />
					<SkeletonText lines={2} size="xs" />
				</div>
				<SkeletonText width="60px" size="xs" />
			</div>
		{/each}
	</div>
</div>
