<script lang="ts">
	import SkeletonBox from './SkeletonBox.svelte';
	import SkeletonText from './SkeletonText.svelte';
</script>

<div>
	<!-- Breadcrumb -->
	<div class="mb-2">
		<SkeletonText width="100px" size="xs" />
	</div>

	<!-- Header -->
	<div class="mb-8 flex items-end justify-between">
		<div>
			<SkeletonText width="120px" size="xl" class="mb-1" />
			<SkeletonText width="200px" size="sm" />
		</div>

		<!-- Compact Stats -->
		<div class="flex items-center gap-4">
			{#each Array(3) as _}
				<SkeletonBox width="90px" height="28px" rounded="md" />
			{/each}
		</div>
	</div>

	<!-- Search and Filters -->
	<div class="mb-6 flex flex-col sm:flex-row gap-2">
		<SkeletonBox width="100%" height="36px" rounded="md" class="flex-1" />
		<SkeletonBox width="150px" height="36px" rounded="md" />
		<SkeletonBox width="120px" height="36px" rounded="md" />
	</div>

	<!-- Project Tree Groups -->
	<div class="space-y-4">
		{#each Array(3) as _}
			<!-- Group Header -->
			<div
				class="flex items-center gap-3 p-3 bg-[var(--bg-subtle)] border border-[var(--border)] rounded-lg"
			>
				<SkeletonBox width="24px" height="24px" rounded="md" />
				<SkeletonText width="200px" size="sm" />
				<div class="flex-1"></div>
				<SkeletonBox width="50px" height="20px" rounded="full" />
			</div>

			<!-- Project Cards Grid -->
			<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 pl-4">
				{#each Array(3) as _}
					<SkeletonBox height="140px" rounded="md" />
				{/each}
			</div>
		{/each}
	</div>
</div>
