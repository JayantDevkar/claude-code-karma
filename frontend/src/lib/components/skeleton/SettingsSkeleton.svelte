<script lang="ts">
	import SkeletonBox from './SkeletonBox.svelte';
	import SkeletonText from './SkeletonText.svelte';
</script>

<div class="max-w-3xl mx-auto">
	<!-- Header -->
	<div class="mb-8">
		<SkeletonText width="100px" size="xl" class="mb-2" />
		<SkeletonText width="250px" size="sm" />
	</div>

	<!-- Settings Sections -->
	<div class="space-y-6">
		{#each Array(4) as _}
			<div class="p-6 bg-[var(--bg-base)] border border-[var(--border)] rounded-lg">
				<!-- Section Title -->
				<SkeletonText width="150px" size="base" class="mb-4" />

				<!-- Settings Items -->
				<div class="space-y-4">
					{#each Array(2) as _}
						<div
							class="flex items-center justify-between py-2 border-b border-[var(--border-subtle)]"
						>
							<div>
								<SkeletonText width="120px" size="sm" class="mb-1" />
								<SkeletonText width="200px" size="xs" />
							</div>
							<SkeletonBox width="100px" height="36px" rounded="md" />
						</div>
					{/each}
				</div>
			</div>
		{/each}
	</div>

	<!-- Raw JSON Section -->
	<div class="mt-6 p-6 bg-[var(--bg-subtle)] border border-[var(--border)] rounded-lg">
		<SkeletonText width="100px" size="sm" class="mb-3" />
		<SkeletonBox height="200px" rounded="md" />
	</div>
</div>
