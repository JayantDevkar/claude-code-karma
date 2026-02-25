<script lang="ts">
	import SkeletonBox from './SkeletonBox.svelte';
	import SkeletonText from './SkeletonText.svelte';
</script>

<!-- Plan Card Skeleton - matches PlanCard.svelte structure -->
<div
	class="group relative flex flex-col p-4 bg-[var(--bg-subtle)] border border-[var(--border)] rounded-lg"
>
	<!-- Header with icon and title -->
	<div class="flex items-start gap-3 mb-3">
		<SkeletonBox width="32px" height="32px" rounded="md" />
		<div class="flex-1 min-w-0">
			<SkeletonText width="70%" size="sm" class="mb-1.5" />
			<SkeletonText width="50%" size="xs" />
		</div>
	</div>

	<!-- Preview text -->
	<div class="mb-3">
		<SkeletonText width="100%" size="xs" class="mb-1" />
		<SkeletonText width="85%" size="xs" />
	</div>

	<!-- Footer with metadata -->
	<div
		class="flex items-center justify-between mt-auto pt-2 border-t border-[var(--border-subtle)]"
	>
		<div class="flex items-center gap-3">
			<SkeletonText width="60px" size="xs" />
			<SkeletonText width="45px" size="xs" />
		</div>
		<SkeletonBox width="80px" height="20px" rounded="full" />
	</div>
</div>
