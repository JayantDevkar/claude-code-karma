<script lang="ts">
	import SkeletonBox from './SkeletonBox.svelte';
	import SkeletonText from './SkeletonText.svelte';
</script>

<div class="space-y-6">
	<!-- Page Header -->
	<div>
		<div class="flex items-center gap-2 mb-2">
			<SkeletonText width="70px" size="xs" />
			<span class="text-[var(--text-muted)]">/</span>
			<SkeletonText width="60px" size="xs" />
		</div>
		<div class="flex items-center gap-4 mb-6 pb-6 border-b border-[var(--border)]">
			<SkeletonBox width="48px" height="48px" rounded="lg" />
			<div>
				<SkeletonText width="120px" size="xl" class="mb-2" />
				<SkeletonText width="220px" size="sm" />
			</div>
		</div>
	</div>

	<!-- Summary bar -->
	<div class="flex items-center gap-4">
		<SkeletonText width="80px" size="sm" />
		<SkeletonText width="60px" size="sm" />
	</div>

	<!-- Members grid -->
	<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
		{#each Array(4) as _}
			<div class="flex items-center gap-4 p-4 rounded-lg border border-[var(--border)]">
				<SkeletonBox width="44px" height="44px" rounded="full" />
				<div class="flex-1">
					<SkeletonText width="120px" size="sm" class="mb-1.5" />
					<SkeletonText width="100px" size="xs" />
				</div>
			</div>
		{/each}
	</div>
</div>
