<script lang="ts">
	import SkeletonBox from './SkeletonBox.svelte';
	import SkeletonText from './SkeletonText.svelte';
</script>

<div class="space-y-6">
	<!-- Breadcrumb -->
	<div class="flex items-center gap-2">
		<SkeletonText width="70px" size="xs" />
		<span class="text-[var(--text-muted)]">/</span>
		<SkeletonText width="60px" size="xs" />
		<span class="text-[var(--text-muted)]">/</span>
		<SkeletonText width="100px" size="xs" />
	</div>

	<!-- Profile header -->
	<div class="mb-6 pb-6 border-b border-[var(--border)]">
		<div class="flex items-start gap-4">
			<SkeletonBox width="48px" height="48px" rounded="lg" />
			<div class="flex-1">
				<div class="flex items-center gap-2.5 mb-2">
					<SkeletonText width="160px" size="xl" />
					<SkeletonBox width="32px" height="18px" rounded="full" />
					<SkeletonText width="50px" size="xs" />
				</div>
				<div class="flex items-center gap-3 mb-3">
					<SkeletonText width="90px" size="xs" />
					<SkeletonText width="140px" size="xs" />
				</div>
				<div class="flex items-center gap-2">
					{#each Array(4) as _}
						<SkeletonBox width="100px" height="28px" rounded="md" />
					{/each}
				</div>
			</div>
		</div>
	</div>

	<!-- Tabs -->
	<div class="flex justify-center">
		<SkeletonBox width="400px" height="42px" rounded="lg" />
	</div>

	<!-- Chart placeholder -->
	<div class="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)] p-4">
		<SkeletonText width="140px" size="sm" class="mb-4" />
		<SkeletonBox width="100%" height="200px" rounded="md" />
	</div>
</div>
