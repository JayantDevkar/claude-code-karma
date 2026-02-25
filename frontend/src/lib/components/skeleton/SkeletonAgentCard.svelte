<script lang="ts">
	import SkeletonBox from './SkeletonBox.svelte';
	import SkeletonText from './SkeletonText.svelte';
</script>

<!-- Matches AgentUsageCard.svelte structure -->
<div
	class="
		bg-[var(--bg-base)]
		border border-[var(--border)]
		rounded-xl
		p-6
		border-l-4 border-l-[var(--border)]
	"
>
	<!-- Header row: Icon + Category Badge -->
	<div class="flex items-start justify-between mb-5">
		<SkeletonBox width="52px" height="52px" rounded="lg" />
		<SkeletonBox width="70px" height="24px" rounded="full" />
	</div>

	<!-- Agent name -->
	<SkeletonText width="140px" size="lg" class="mb-2" />

	<!-- Plugin source placeholder -->
	<div class="mb-4">
		<SkeletonText width="100px" size="xs" />
	</div>

	<!-- Stats with progress bar -->
	<div class="space-y-3 mb-4">
		<!-- Runs stat -->
		<div>
			<div class="flex items-center justify-between mb-1.5">
				<SkeletonText width="50px" size="xs" />
				<SkeletonText width="40px" size="sm" />
			</div>
			<SkeletonBox width="100%" height="6px" rounded="full" />
		</div>

		<!-- Cost stat -->
		<div class="flex items-center justify-between">
			<SkeletonText width="70px" size="xs" />
			<SkeletonText width="50px" size="sm" />
		</div>
	</div>

	<!-- Footer row -->
	<div class="flex items-center justify-between pt-4 border-t border-[var(--border-subtle)]">
		<SkeletonText width="90px" size="xs" />
		<SkeletonText width="70px" size="xs" />
	</div>
</div>
