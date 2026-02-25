<script lang="ts">
	import SkeletonBox from './SkeletonBox.svelte';
	import SkeletonText from './SkeletonText.svelte';
</script>

<div class="max-w-[1400px] mx-auto">
	<!-- Header -->
	<div class="flex items-center gap-3 mb-6">
		<SkeletonBox width="48px" height="48px" rounded="lg" />
		<div>
			<SkeletonText width="100px" size="lg" class="mb-2" />
			<SkeletonText width="300px" size="sm" />
		</div>
	</div>

	<!-- Search Bar -->
	<div class="max-w-md mb-6">
		<SkeletonBox height="44px" rounded="md" />
	</div>

	<!-- Stats Summary -->
	<div class="flex gap-4 mb-6">
		<SkeletonBox width="150px" height="32px" rounded="md" />
		<SkeletonBox width="150px" height="32px" rounded="md" />
	</div>

	<!-- Archived Groups (Accordion style) -->
	<div class="space-y-3">
		{#each Array(4) as _}
			<div class="border border-[var(--border)] rounded-lg overflow-hidden">
				<!-- Group Header -->
				<div class="flex items-center gap-3 p-4 bg-[var(--bg-subtle)]">
					<SkeletonBox width="20px" height="20px" rounded="sm" />
					<SkeletonText width="250px" size="sm" />
					<div class="flex-1"></div>
					<SkeletonBox width="60px" height="20px" rounded="full" />
				</div>

				<!-- Group Items (collapsed appearance) -->
				<div class="p-4 bg-[var(--bg-base)] border-t border-[var(--border)]">
					<div class="space-y-2">
						{#each Array(2) as _}
							<div class="flex items-center gap-3 py-2">
								<SkeletonBox width="16px" height="16px" rounded="sm" />
								<SkeletonText width="80%" size="sm" />
								<SkeletonText width="60px" size="xs" />
							</div>
						{/each}
					</div>
				</div>
			</div>
		{/each}
	</div>
</div>
