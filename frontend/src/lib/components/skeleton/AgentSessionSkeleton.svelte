<script lang="ts">
	import SkeletonBox from './SkeletonBox.svelte';
	import SkeletonText from './SkeletonText.svelte';
	import SkeletonStatsCard from './SkeletonStatsCard.svelte';
</script>

<div class="space-y-6">
	<!-- Agent Header with colored background (mimics ConversationHeader for agents) -->
	<div
		class="rounded-lg p-4 -mx-4 mb-4"
		style="background: var(--subagent-explore-subtle); border: 1px solid color-mix(in srgb, var(--subagent-explore) 20%, transparent);"
	>
		<div class="space-y-4">
			<!-- Breadcrumb -->
			<div class="mb-2">
				<SkeletonText width="350px" size="xs" />
			</div>

			<!-- Agent Header Row -->
			<div class="flex items-start justify-between">
				<div class="flex-1">
					<div class="flex items-center gap-3 mb-2">
						<!-- Agent ID title -->
						<SkeletonText width="120px" size="lg" />
						<!-- Type badge -->
						<SkeletonBox width="80px" height="26px" rounded="full" />
					</div>
					<!-- Subtitle (agent type) -->
					<SkeletonText width="100px" size="sm" />
					<!-- Metadata (date, duration) -->
					<div class="flex items-center gap-4 mt-2">
						<div class="flex items-center gap-1.5">
							<SkeletonBox width="14px" height="14px" rounded="sm" />
							<SkeletonText width="140px" size="xs" />
						</div>
						<div class="flex items-center gap-1.5">
							<SkeletonBox width="14px" height="14px" rounded="sm" />
							<SkeletonText width="60px" size="xs" />
						</div>
					</div>
				</div>
				<!-- Status badge placeholder -->
				<SkeletonBox width="70px" height="26px" rounded="full" />
			</div>

			<!-- Back to Session link -->
			<SkeletonBox width="140px" height="32px" rounded="md" />
		</div>
	</div>

	<!-- Tabs -->
	<div
		class="flex items-center justify-center gap-1 p-1 bg-[var(--bg-subtle)] rounded-lg w-fit mx-auto border border-[var(--border)]"
	>
		{#each Array(6) as _}
			<SkeletonBox width="90px" height="32px" rounded="md" />
		{/each}
	</div>

	<!-- Overview Content (default tab) -->
	<div class="space-y-6">
		<!-- Context Summary Card -->
		<div class="p-4 bg-[var(--bg-subtle)] border border-[var(--border)] rounded-lg">
			<SkeletonText width="140px" size="sm" class="mb-3" />
			<div class="space-y-2">
				{#each Array(3) as _}
					<SkeletonText width="100%" size="sm" />
				{/each}
			</div>
		</div>

		<!-- Stats Grid -->
		<div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
			{#each Array(5) as _}
				<SkeletonStatsCard />
			{/each}
		</div>

		<!-- Tools Summary -->
		<div class="grid gap-6 lg:grid-cols-2">
			<!-- Tool Usage Table -->
			<div class="p-4 bg-[var(--bg-base)] border border-[var(--border)] rounded-lg">
				<SkeletonText width="100px" size="sm" class="mb-4" />
				<div class="space-y-2">
					{#each Array(5) as _}
						<div
							class="flex items-center justify-between py-2 border-b border-[var(--border)] last:border-0"
						>
							<SkeletonText width="120px" size="sm" />
							<SkeletonBox width="40px" height="20px" rounded="sm" />
						</div>
					{/each}
				</div>
			</div>

			<!-- Tools Chart placeholder -->
			<div class="p-4 bg-[var(--bg-base)] border border-[var(--border)] rounded-lg">
				<SkeletonText width="80px" size="sm" class="mb-4" />
				<div class="flex items-center justify-center h-48">
					<SkeletonBox width="180px" height="180px" rounded="full" />
				</div>
			</div>
		</div>
	</div>
</div>
