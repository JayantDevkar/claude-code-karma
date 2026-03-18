<script lang="ts">
	import SkeletonBox from './SkeletonBox.svelte';
	import SkeletonText from './SkeletonText.svelte';
</script>

<div class="live-section mb-6">
	<!-- Header -->
	<div class="live-header">
		<div class="flex items-center gap-2">
			<div class="flex items-center gap-1.5">
				<!-- Chevron + Radio icon placeholders -->
				<SkeletonBox width="16px" height="16px" rounded="sm" />
				<SkeletonBox width="14px" height="14px" rounded="sm" />
				<span class="section-title">LIVE NOW</span>
			</div>
			<!-- Count badge -->
			<SkeletonBox width="80px" height="14px" rounded="sm" />
		</div>
		<!-- Pulse indicator -->
		<SkeletonBox width="8px" height="8px" rounded="full" />
	</div>

	<!-- Session rows -->
	<div class="live-content">
		<div class="sessions-list">
			{#each Array(3) as _}
				<div class="session-row">
					<!-- Status dot -->
					<SkeletonBox width="8px" height="8px" rounded="full" class="mt-1.5 shrink-0" />
					<!-- Session info -->
					<div class="session-info">
						<div class="flex items-center gap-3">
							<SkeletonText width="120px" size="sm" />
							<SkeletonBox width="50px" height="12px" rounded="sm" />
						</div>
						<div class="flex items-center justify-between mt-1">
							<SkeletonText width="80px" size="xs" />
							<SkeletonText width="40px" size="xs" />
						</div>
					</div>
				</div>
			{/each}
		</div>
	</div>
</div>

<style>
	.live-section {
		background: var(--bg-subtle);
		border: 1px solid var(--border);
		border-radius: var(--radius-md);
		overflow: hidden;
	}

	.live-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 12px 16px;
		background: var(--bg-muted);
	}

	.section-title {
		font-size: 11px;
		font-weight: 600;
		letter-spacing: 0.5px;
		color: var(--text-secondary);
	}

	.live-content {
		border-top: 1px solid var(--border-subtle);
	}

	.sessions-list {
		display: flex;
		flex-direction: column;
	}

	.session-row {
		display: flex;
		align-items: flex-start;
		gap: 12px;
		padding: 12px 16px;
		border-bottom: 1px solid var(--border-subtle);
	}

	.session-row:last-child {
		border-bottom: none;
	}

	.session-info {
		flex: 1;
		min-width: 0;
	}
</style>
