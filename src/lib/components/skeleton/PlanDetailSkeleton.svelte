<script lang="ts">
	import SkeletonBox from './SkeletonBox.svelte';
	import SkeletonText from './SkeletonText.svelte';
</script>

<div class="space-y-6">
	<!-- Breadcrumb -->
	<div class="mb-2">
		<div class="flex items-center gap-2">
			<SkeletonText width="70px" size="xs" />
			<SkeletonText width="10px" size="xs" />
			<SkeletonText width="50px" size="xs" />
			<SkeletonText width="10px" size="xs" />
			<SkeletonText width="120px" size="xs" />
		</div>
	</div>

	<!-- Page Header -->
	<div class="flex items-start justify-between gap-4 mb-6">
		<div class="flex items-center gap-4">
			<SkeletonBox width="48px" height="48px" rounded="lg" />
			<div>
				<SkeletonText width="250px" size="xl" class="mb-2" />
				<SkeletonText width="180px" size="sm" />
			</div>
		</div>
		<SkeletonBox width="100px" height="32px" rounded="md" />
	</div>

	<!-- Related Sessions Card -->
	<div class="p-4 bg-[var(--bg-subtle)] border border-[var(--border)] rounded-lg">
		<div class="flex items-center gap-2 mb-3">
			<SkeletonBox width="16px" height="16px" rounded="sm" />
			<SkeletonText width="120px" size="sm" />
		</div>
		<div class="flex flex-wrap gap-2">
			<SkeletonBox width="140px" height="32px" rounded="lg" />
			<SkeletonBox width="120px" height="32px" rounded="lg" />
			<SkeletonBox width="110px" height="32px" rounded="lg" />
		</div>
	</div>

	<!-- Plan Content Card -->
	<div class="bg-[var(--bg-subtle)] border border-[var(--border)] rounded-lg overflow-hidden">
		<div class="p-6 md:p-8">
			<!-- Markdown content skeleton -->
			<div class="space-y-6">
				<!-- Heading 2 -->
				<SkeletonText width="40%" size="lg" class="mb-4" />

				<!-- Paragraph -->
				<div class="space-y-2">
					<SkeletonText width="100%" size="sm" />
					<SkeletonText width="95%" size="sm" />
					<SkeletonText width="88%" size="sm" />
				</div>

				<!-- Heading 3 -->
				<SkeletonText width="30%" size="base" class="mt-6 mb-3" />

				<!-- List items -->
				<div class="space-y-2 pl-4">
					<div class="flex items-start gap-2">
						<SkeletonBox width="6px" height="6px" rounded="full" class="mt-2" />
						<SkeletonText width="85%" size="sm" />
					</div>
					<div class="flex items-start gap-2">
						<SkeletonBox width="6px" height="6px" rounded="full" class="mt-2" />
						<SkeletonText width="75%" size="sm" />
					</div>
					<div class="flex items-start gap-2">
						<SkeletonBox width="6px" height="6px" rounded="full" class="mt-2" />
						<SkeletonText width="80%" size="sm" />
					</div>
				</div>

				<!-- Code block -->
				<SkeletonBox width="100%" height="100px" rounded="md" class="mt-4" />

				<!-- Another heading -->
				<SkeletonText width="35%" size="base" class="mt-6 mb-3" />

				<!-- More content -->
				<div class="space-y-2">
					<SkeletonText width="100%" size="sm" />
					<SkeletonText width="92%" size="sm" />
					<SkeletonText width="70%" size="sm" />
				</div>
			</div>
		</div>
	</div>
</div>
