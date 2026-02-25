<script lang="ts">
	import SkeletonBox from './SkeletonBox.svelte';
	import SkeletonText from './SkeletonText.svelte';

	interface Props {
		class?: string;
	}

	let { class: className = '' }: Props = $props();
</script>

<!-- Matches SessionCard.svelte structure -->
<div
	class="
		flex flex-col h-full
		bg-[var(--bg-subtle)]
		border border-l-[3px] border-[var(--border)]
		rounded-[var(--radius-md)]
		overflow-hidden
		{className}
	"
	style="border-left-color: var(--text-faint);"
>
	<!-- HEADER ZONE -->
	<div class="p-4 pb-3 pl-5">
		<div class="flex items-start gap-3">
			<!-- Model Icon -->
			<SkeletonBox width="32px" height="32px" rounded="lg" />

			<div class="flex-1 min-w-0">
				<div class="flex items-center justify-between gap-2 mb-0.5">
					<!-- Session Slug -->
					<SkeletonText width="120px" size="sm" />
					<!-- Timestamp -->
					<SkeletonText width="50px" size="xs" />
				</div>

				<!-- Branch Badge -->
				<div class="flex items-center gap-1.5">
					<SkeletonBox width="12px" height="12px" rounded="sm" />
					<SkeletonText width="90px" size="xs" />
				</div>
			</div>
		</div>
	</div>

	<!-- BODY ZONE -->
	<div class="px-4 pb-4 pl-5 flex-grow">
		<div class="bg-[var(--bg-muted)] px-2 py-1.5 rounded-md">
			<SkeletonText lines={2} size="sm" />
		</div>
	</div>

	<!-- FOOTER ZONE -->
	<div class="px-4 py-2.5 pl-5 border-t border-[var(--border)] flex items-center justify-between">
		<!-- Stats Group -->
		<div class="flex items-center gap-3">
			<SkeletonBox width="40px" height="16px" rounded="sm" />
			<SkeletonBox width="50px" height="16px" rounded="sm" />
			<SkeletonBox width="35px" height="16px" rounded="sm" />
		</div>

		<!-- Model Badge -->
		<SkeletonBox width="70px" height="24px" rounded="full" />
	</div>
</div>
