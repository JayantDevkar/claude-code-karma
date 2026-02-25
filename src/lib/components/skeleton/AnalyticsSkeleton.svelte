<script lang="ts">
	import SkeletonBox from './SkeletonBox.svelte';
	import SkeletonText from './SkeletonText.svelte';
</script>

<div class="max-w-[1100px] mx-auto">
	<!-- Breadcrumb -->
	<div class="mb-2">
		<SkeletonText width="150px" size="xs" />
	</div>

	<!-- Header -->
	<div class="flex items-start justify-between mb-6">
		<div>
			<SkeletonText width="120px" size="xl" class="mb-2" />
			<SkeletonText width="250px" size="sm" />
		</div>
		<SkeletonBox width="140px" height="36px" rounded="md" />
	</div>

	<!-- Hero Row: Velocity + Cost -->
	<div class="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-4">
		<!-- Velocity Card (2 cols) -->
		<SkeletonBox height="180px" rounded="lg" class="lg:col-span-2" />
		<!-- Cost Card (1 col) -->
		<SkeletonBox height="180px" rounded="lg" />
	</div>

	<!-- Efficiency Row: 4 cards -->
	<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
		{#each Array(4) as _}
			<SkeletonBox height="140px" rounded="lg" />
		{/each}
	</div>

	<!-- Compute DNA Card (wide) -->
	<SkeletonBox height="200px" rounded="lg" class="mb-4" />

	<!-- Activity Timeline Chart -->
	<SkeletonBox height="280px" rounded="lg" class="mb-4" />

	<!-- Time Distribution -->
	<div class="p-6 bg-[var(--bg-base)] border border-[var(--border)] rounded-lg">
		<SkeletonText width="150px" size="base" class="mb-4" />
		<div class="space-y-3">
			{#each Array(4) as _}
				<div class="flex items-center gap-3">
					<SkeletonText width="80px" size="xs" />
					<SkeletonBox height="8px" rounded="full" class="flex-1" />
					<SkeletonText width="60px" size="xs" />
				</div>
			{/each}
		</div>
	</div>
</div>
