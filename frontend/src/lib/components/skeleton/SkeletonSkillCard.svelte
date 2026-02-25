<script lang="ts">
	import SkeletonBox from './SkeletonBox.svelte';
	import SkeletonText from './SkeletonText.svelte';
</script>

<!-- Matches SkillUsageCard.svelte structure -->
<div
	class="
		bg-[var(--bg-base)]
		border border-[var(--border)]
		rounded-xl
		p-6
		border-l-4 border-l-[var(--border)]
	"
>
	<!-- Header row: Icon + Badge -->
	<div class="flex items-start justify-between mb-5">
		<SkeletonBox width="52px" height="52px" rounded="lg" />
		<SkeletonBox width="60px" height="24px" rounded="full" />
	</div>

	<!-- Skill name -->
	<SkeletonText width="140px" size="lg" class="mb-2" />

	<!-- Plugin source placeholder (matches mb-4 spacing) -->
	<div class="mb-4">
		<SkeletonText width="120px" size="xs" />
	</div>

	<!-- Usage stat with progress bar -->
	<div class="space-y-3">
		<div>
			<div class="flex items-center justify-between mb-1.5">
				<SkeletonText width="50px" size="xs" />
				<SkeletonText width="40px" size="sm" />
			</div>
			<SkeletonBox width="100%" height="6px" rounded="full" />
		</div>
	</div>
</div>
