<script lang="ts">
	import SkeletonBox from './SkeletonBox.svelte';
	import SkeletonText from './SkeletonText.svelte';
</script>

<div class="space-y-6">
	<!-- Page Header -->
	<div>
		<!-- Breadcrumb -->
		<div class="flex items-center gap-2 mb-2">
			<SkeletonText width="70px" size="xs" />
			<span class="text-[var(--text-muted)]">/</span>
			<SkeletonText width="70px" size="xs" />
		</div>
		<!-- Title + badges -->
		<div class="flex items-start justify-between gap-4">
			<div class="flex items-center gap-4">
				<SkeletonBox width="48px" height="48px" rounded="lg" />
				<div>
					<SkeletonText width="120px" size="xl" class="mb-2" />
					<SkeletonText width="260px" size="sm" />
				</div>
			</div>
			<!-- Badge pills -->
			<div class="flex items-center gap-2 mt-1">
				<SkeletonBox width="90px" height="26px" rounded="full" />
				<SkeletonBox width="90px" height="26px" rounded="full" />
				<SkeletonBox width="90px" height="26px" rounded="full" />
			</div>
		</div>
	</div>

	<!-- Filters Row: search + segmented control -->
	<div class="flex flex-col sm:flex-row items-start sm:items-center gap-4">
		<SkeletonBox width="100%" height="38px" rounded="lg" class="flex-1" />
		<div class="flex gap-1">
			<SkeletonBox width="56px" height="36px" rounded="lg" />
			<SkeletonBox width="70px" height="36px" rounded="lg" />
			<SkeletonBox width="100px" height="36px" rounded="lg" />
		</div>
	</div>

	<!-- Archived project groups -->
	<div class="space-y-3">
		{#each Array(4) as _}
			<div class="bg-[var(--bg-base)] border border-[var(--border)] rounded-xl p-4">
				<!-- Project header -->
				<div class="flex items-center justify-between mb-3">
					<div class="flex items-center gap-2">
						<SkeletonBox width="16px" height="16px" rounded="sm" />
						<SkeletonText width="160px" size="base" />
					</div>
					<div class="flex items-center gap-3">
						<SkeletonText width="80px" size="xs" />
						<SkeletonText width="70px" size="xs" />
					</div>
				</div>
				<!-- Prompt rows -->
				<div class="space-y-2 pl-6">
					{#each Array(3) as _}
						<div class="flex items-start gap-3 py-2 border-t border-[var(--border)]">
							<SkeletonBox width="14px" height="14px" rounded="sm" class="mt-0.5 flex-shrink-0" />
							<div class="flex-1 min-w-0">
								<SkeletonText width="90%" size="sm" class="mb-1" />
								<SkeletonText width="60%" size="xs" />
							</div>
							<SkeletonText width="50px" size="xs" class="flex-shrink-0" />
						</div>
					{/each}
				</div>
			</div>
		{/each}
	</div>
</div>
