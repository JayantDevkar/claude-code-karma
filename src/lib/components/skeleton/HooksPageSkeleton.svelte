<script lang="ts">
	import SkeletonBox from './SkeletonBox.svelte';
	import SkeletonText from './SkeletonText.svelte';
	import SkeletonStatsCard from './SkeletonStatsCard.svelte';
</script>

<div class="space-y-8">
	<!-- Page Header -->
	<div>
		<div class="flex items-center gap-2 mb-2">
			<SkeletonText width="70px" size="xs" />
			<span class="text-[var(--text-muted)]">/</span>
			<SkeletonText width="50px" size="xs" />
		</div>
		<div class="flex items-center gap-4">
			<SkeletonBox width="48px" height="48px" rounded="lg" />
			<div>
				<SkeletonText width="80px" size="xl" class="mb-2" />
				<SkeletonText width="320px" size="sm" />
			</div>
		</div>
	</div>

	<!-- Hero Stats -->
	<div class="rounded-2xl p-8 border border-[var(--border)] bg-[var(--bg-subtle)]">
		<div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
			{#each Array(3) as _}
				<SkeletonStatsCard />
			{/each}
		</div>
	</div>

	<!-- View Toggle -->
	<div class="flex items-center justify-between">
		<div class="flex gap-1">
			<SkeletonBox width="120px" height="36px" rounded="lg" />
			<SkeletonBox width="100px" height="36px" rounded="lg" />
		</div>
	</div>

	<!-- Timeline items -->
	<div class="space-y-3">
		{#each Array(5) as _}
			<div class="flex items-center gap-3 p-4 border border-[var(--border)] rounded-lg">
				<SkeletonBox width="8px" height="8px" rounded="full" />
				<SkeletonText width="140px" size="sm" />
				<div class="flex-1"></div>
				<SkeletonBox width="60px" height="24px" rounded="md" />
				<SkeletonText width="30px" size="xs" />
			</div>
		{/each}
	</div>
</div>
