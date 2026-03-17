<script lang="ts">
	import SkeletonBox from './SkeletonBox.svelte';
	import SkeletonText from './SkeletonText.svelte';
	import SkeletonGlobalSessionCard from './SkeletonGlobalSessionCard.svelte';
	import SkeletonLiveSessionsSection from './SkeletonLiveSessionsSection.svelte';

	interface Props {
		viewMode?: 'list' | 'grid';
	}

	let { viewMode = 'list' }: Props = $props();

	const isGrid = $derived(viewMode === 'grid');
	const gridClass = $derived(
		isGrid
			? 'grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2'
			: 'grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3'
	);
</script>

<div>
	<!-- Breadcrumb -->
	<div class="mb-2">
		<SkeletonText width="120px" size="xs" />
	</div>

	<!-- Header -->
	<div class="mb-8 flex items-end justify-between">
		<div class="flex items-start gap-3">
			<!-- Icon -->
			<SkeletonBox width="40px" height="40px" rounded="lg" />
			<div>
				<SkeletonText width="100px" size="xl" class="mb-1" />
				<SkeletonText width="300px" size="sm" />
			</div>
		</div>

		<!-- Compact Stats -->
		<div class="flex items-center gap-4">
			<SkeletonBox width="80px" height="28px" rounded="md" />
		</div>
	</div>

	<!-- Search and Filters -->
	<div class="mb-6 flex flex-col sm:flex-row gap-2">
		<!-- Search Bar -->
		<SkeletonBox width="100%" height="36px" rounded="md" class="flex-1" />
		<!-- Project Filter -->
		<SkeletonBox width="150px" height="36px" rounded="md" />
		<!-- View Toggle -->
		<SkeletonBox width="80px" height="36px" rounded="md" />
	</div>

	<!-- LIVE NOW Section -->
	<SkeletonLiveSessionsSection />

	<!-- Day-based Groups -->
	<div class="space-y-8">
		<!-- Today Group -->
		<div>
			<div class="flex items-center gap-2 mb-4">
				<SkeletonText width="50px" size="sm" />
				<SkeletonText width="30px" size="xs" />
			</div>
			<div class={gridClass}>
				{#each Array(3) as _}
					<SkeletonGlobalSessionCard compact={isGrid} />
				{/each}
			</div>
		</div>

		<!-- This Week Group -->
		<div>
			<div class="flex items-center gap-2 mb-4">
				<SkeletonText width="80px" size="sm" />
				<SkeletonText width="30px" size="xs" />
			</div>
			<div class={gridClass}>
				{#each Array(3) as _}
					<SkeletonGlobalSessionCard compact={isGrid} />
				{/each}
			</div>
		</div>

		<!-- Older Group -->
		<div>
			<div class="flex items-center gap-2 mb-4">
				<SkeletonText width="50px" size="sm" />
				<SkeletonText width="30px" size="xs" />
			</div>
			<div class={gridClass}>
				{#each Array(2) as _}
					<SkeletonGlobalSessionCard compact={isGrid} />
				{/each}
			</div>
		</div>
	</div>
</div>
