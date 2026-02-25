<script lang="ts">
	import SkeletonBox from './SkeletonBox.svelte';
	import SkeletonText from './SkeletonText.svelte';
	import SkeletonStatsCard from './SkeletonStatsCard.svelte';
</script>

<div class="space-y-8">
	<!-- Page Header -->
	<div>
		<!-- Breadcrumb -->
		<div class="flex items-center gap-2 mb-2">
			<SkeletonText width="70px" size="xs" />
			<span class="text-[var(--text-muted)]">/</span>
			<SkeletonText width="50px" size="xs" />
			<span class="text-[var(--text-muted)]">/</span>
			<SkeletonText width="60px" size="xs" />
		</div>
		<!-- Title with icon and badge -->
		<div class="flex items-center gap-4">
			<SkeletonBox width="48px" height="48px" rounded="lg" />
			<div class="flex items-center gap-3">
				<SkeletonText width="120px" size="xl" />
				<SkeletonBox width="70px" height="24px" rounded="full" />
			</div>
		</div>
	</div>

	<!-- Hero Stats Row -->
	<div class="rounded-2xl p-8 border border-[var(--border)] bg-[var(--bg-subtle)]">
		<div class="grid grid-cols-2 sm:grid-cols-4 gap-4">
			{#each Array(4) as _}
				<SkeletonStatsCard />
			{/each}
		</div>
	</div>

	<!-- Tab Navigation -->
	<div class="flex items-center justify-between">
		<div class="flex gap-1">
			<SkeletonBox width="90px" height="36px" rounded="lg" />
			<SkeletonBox width="80px" height="36px" rounded="lg" />
		</div>
		<SkeletonText width="150px" size="sm" />
	</div>

	<!-- Content Grid -->
	<div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
		<!-- Tool Usage Card -->
		<div class="bg-[var(--bg-base)] border border-[var(--border)] rounded-xl p-6">
			<div class="flex items-center gap-2 mb-6">
				<SkeletonBox width="18px" height="18px" rounded="sm" />
				<SkeletonText width="120px" size="lg" />
			</div>
			<div class="space-y-3.5">
				{#each Array(4) as _}
					<div>
						<div class="flex items-center justify-between mb-2">
							<SkeletonText width="80px" size="sm" />
							<SkeletonText width="50px" size="sm" />
						</div>
						<SkeletonBox width="100%" height="8px" rounded="full" />
					</div>
				{/each}
			</div>
		</div>

		<!-- Projects Card -->
		<div class="bg-[var(--bg-base)] border border-[var(--border)] rounded-xl p-6">
			<div class="flex items-center gap-2 mb-6">
				<SkeletonBox width="18px" height="18px" rounded="sm" />
				<SkeletonText width="130px" size="lg" />
			</div>
			<div class="space-y-3.5">
				{#each Array(5) as _}
					<div>
						<div class="flex items-center justify-between mb-2">
							<SkeletonText width="100px" size="sm" />
							<SkeletonText width="60px" size="sm" />
						</div>
						<SkeletonBox width="100%" height="8px" rounded="full" />
					</div>
				{/each}
			</div>
		</div>

		<!-- Token Usage Card -->
		<div class="bg-[var(--bg-base)] border border-[var(--border)] rounded-xl p-6">
			<div class="flex items-center gap-2 mb-6">
				<SkeletonBox width="18px" height="18px" rounded="sm" />
				<SkeletonText width="100px" size="lg" />
			</div>
			<!-- Total tokens -->
			<div class="mb-6">
				<SkeletonText width="180px" size="xl" class="mb-1" />
				<SkeletonText width="140px" size="xs" />
			</div>
			<!-- Token bar -->
			<div class="mb-4">
				<SkeletonBox width="100%" height="16px" rounded="full" />
			</div>
			<!-- Legend -->
			<div class="grid grid-cols-2 gap-3">
				<div class="bg-[var(--bg-subtle)] rounded-lg p-2.5">
					<SkeletonText width="40px" size="xs" class="mb-1" />
					<SkeletonText width="80px" size="sm" />
				</div>
				<div class="bg-[var(--bg-subtle)] rounded-lg p-2.5">
					<SkeletonText width="45px" size="xs" class="mb-1" />
					<SkeletonText width="70px" size="sm" />
				</div>
			</div>
		</div>

		<!-- Activity Timeline Card -->
		<div class="bg-[var(--bg-base)] border border-[var(--border)] rounded-xl p-6">
			<div class="flex items-center gap-2 mb-6">
				<SkeletonBox width="18px" height="18px" rounded="sm" />
				<SkeletonText width="130px" size="lg" />
			</div>
			<div class="grid grid-cols-2 gap-4">
				<div class="bg-[var(--bg-subtle)] rounded-lg p-3">
					<SkeletonText width="60px" size="xs" class="mb-2" />
					<SkeletonText width="90px" size="sm" />
				</div>
				<div class="bg-[var(--bg-subtle)] rounded-lg p-3">
					<SkeletonText width="60px" size="xs" class="mb-2" />
					<SkeletonText width="100px" size="sm" />
				</div>
			</div>
		</div>
	</div>
</div>
