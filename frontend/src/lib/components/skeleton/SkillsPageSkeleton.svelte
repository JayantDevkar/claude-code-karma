<script lang="ts">
	import SkeletonBox from './SkeletonBox.svelte';
	import SkeletonText from './SkeletonText.svelte';
	import SkeletonStatsCard from './SkeletonStatsCard.svelte';
	import SkeletonSkillCard from './SkeletonSkillCard.svelte';
</script>

<div class="space-y-8">
	<!-- Page Header -->
	<div>
		<!-- Breadcrumb -->
		<div class="flex items-center gap-2 mb-2">
			<SkeletonText width="70px" size="xs" />
			<span class="text-[var(--text-muted)]">/</span>
			<SkeletonText width="50px" size="xs" />
		</div>
		<!-- Title and subtitle -->
		<div class="flex items-center gap-4">
			<SkeletonBox width="48px" height="48px" rounded="lg" />
			<div>
				<SkeletonText width="80px" size="xl" class="mb-2" />
				<SkeletonText width="340px" size="sm" />
			</div>
		</div>
	</div>

	<!-- Hero Stats Section with Gradient Background -->
	<div
		class="relative overflow-hidden rounded-2xl p-8 border border-[var(--border)]"
		style="background: linear-gradient(135deg, rgba(124, 58, 237, 0.02) 0%, rgba(124, 58, 237, 0.06) 100%);"
	>
		<!-- Decorative blur elements -->
		<div
			class="absolute -top-24 -right-24 w-96 h-96 bg-violet-500/5 rounded-full blur-3xl pointer-events-none"
		></div>
		<div
			class="absolute -bottom-24 -left-24 w-64 h-64 bg-blue-500/3 rounded-full blur-3xl pointer-events-none"
		></div>

		<!-- Stats Grid -->
		<div class="relative grid grid-cols-1 sm:grid-cols-3 gap-4">
			{#each Array(3) as _}
				<SkeletonStatsCard />
			{/each}
		</div>
	</div>

	<!-- View Tabs -->
	<div class="flex items-center gap-4">
		<div class="flex gap-1">
			{#each Array(2) as _}
				<SkeletonBox width="140px" height="36px" rounded="lg" />
			{/each}
		</div>
	</div>

	<!-- Filters Row -->
	<div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
		<!-- Type Filter (segmented control) -->
		<div class="flex gap-1">
			{#each Array(3) as _}
				<SkeletonBox width="70px" height="36px" rounded="lg" />
			{/each}
		</div>

		<!-- Search and Expand/Collapse Controls -->
		<div class="flex items-center gap-3 w-full sm:w-auto">
			<!-- Search Input -->
			<SkeletonBox width="256px" height="40px" rounded="lg" />
			<!-- Expand/Collapse Toggle -->
			<SkeletonBox width="120px" height="40px" rounded="lg" />
		</div>
	</div>

	<!-- Grouped Skill Cards -->
	<div class="space-y-4">
		{#each Array(2) as _, groupIndex}
			<div
				class="border border-[var(--border)] rounded-[var(--radius-lg)] overflow-hidden bg-[var(--bg-base)]"
			>
				<!-- Group header -->
				<div class="flex items-center gap-3 px-4 py-4">
					<SkeletonBox width="16px" height="16px" rounded="sm" />
					<SkeletonBox width="32px" height="32px" rounded="md" />
					<SkeletonText width="140px" size="sm" />
					<div class="flex-1"></div>
					<SkeletonText width="60px" size="xs" />
				</div>

				<!-- Group content (only for first group) -->
				{#if groupIndex === 0}
					<div class="border-t border-[var(--border)] p-4">
						<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
							{#each Array(6) as _}
								<SkeletonSkillCard />
							{/each}
						</div>
					</div>
				{/if}
			</div>
		{/each}
	</div>
</div>
