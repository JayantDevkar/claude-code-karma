<script lang="ts">
	import type { SyncTeamProject } from '$lib/api-types';
	import { getTeamMemberHexColor, getUserChartLabel, LOCAL_USER_HEX } from '$lib/utils';

	interface Props {
		project: SyncTeamProject;
		userNames?: Record<string, string>;
		class?: string;
	}

	let { project, userNames, class: className }: Props = $props();

	interface Segment {
		name: string;
		count: number;
		color: string;
		pct: number;
	}

	let segments = $derived.by(() => {
		const result: Segment[] = [];
		const total =
			project.local_count +
			Object.values(project.received_counts).reduce((sum, n) => sum + n, 0);

		if (total === 0) return result;

		// Local user segment
		if (project.local_count > 0) {
			result.push({
				name: 'You',
				count: project.local_count,
				color: LOCAL_USER_HEX,
				pct: Math.max(2, (project.local_count / total) * 100)
			});
		}

		// Remote member segments
		for (const [memberId, count] of Object.entries(project.received_counts)) {
			if (count > 0) {
				result.push({
					name: getUserChartLabel(memberId, userNames),
					count,
					color: getTeamMemberHexColor(memberId),
					pct: Math.max(2, (count / total) * 100)
				});
			}
		}

		return result;
	});
</script>

{#if segments.length > 0}
	<div class={className}>
		<!-- Stacked bar -->
		<div class="flex h-2 rounded-full overflow-hidden bg-[var(--bg-muted)]">
			{#each segments as segment (segment.name)}
				<div
					style="width: {segment.pct}%; background-color: {segment.color};"
					title="{segment.name}: {segment.count}"
				></div>
			{/each}
		</div>

		<!-- Legend -->
		<div class="flex flex-wrap gap-x-3 gap-y-1 mt-1.5">
			{#each segments as segment (segment.name)}
				<span class="flex items-center gap-1 text-[11px] text-[var(--text-muted)]">
					<span
						class="inline-block w-2 h-2 rounded-full shrink-0"
						style="background-color: {segment.color};"
					></span>
					{segment.name} ({segment.count})
				</span>
			{/each}
		</div>
	</div>
{/if}
