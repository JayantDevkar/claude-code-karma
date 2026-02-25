<script lang="ts">
	import SkeletonBox from './SkeletonBox.svelte';
	import SkeletonText from './SkeletonText.svelte';

	interface Props {
		class?: string;
	}

	let { class: className = '' }: Props = $props();
</script>

<div
	class="
		block
		bg-[var(--bg-base)]
		border border-[var(--border)]
		rounded-xl
		p-6
		shadow-sm
		relative overflow-hidden
		{className}
	"
	role="status"
	aria-label="Loading plugin..."
>
	<!-- Header row: Icon + Badge -->
	<div class="flex items-start justify-between mb-5">
		<SkeletonBox width="46px" height="46px" rounded="lg" />
		<SkeletonBox width="70px" height="24px" rounded="full" />
	</div>

	<!-- Plugin name -->
	<SkeletonText width="80%" size="lg" class="mb-2" />

	<!-- Description placeholder -->
	<SkeletonText lines={2} size="xs" class="mb-4" />

	<!-- Stats grid -->
	<div class="grid grid-cols-2 gap-3 mb-4">
		<SkeletonText width="90px" size="xs" />
		<SkeletonText width="80px" size="xs" />
		<SkeletonText width="85px" size="xs" />
		<SkeletonText width="75px" size="xs" />
	</div>

	<!-- Footer row -->
	<div
		class="flex items-center justify-between text-xs text-[var(--text-muted)] pt-4 border-t border-[var(--border-subtle)]"
	>
		<SkeletonText width="100px" size="xs" />
		<SkeletonBox width="60px" height="20px" rounded="sm" />
	</div>
</div>
