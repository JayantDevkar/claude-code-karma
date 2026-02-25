<script lang="ts">
	import type { TimelineGap } from '$lib/utils/timelineLogic.svelte';
	import type { TimelineEvent } from '$lib/api-types';
	import { Plus } from 'lucide-svelte';

	interface Props {
		gap: TimelineGap;
		onExpand: (ids: string[]) => void;
	}

	let { gap, onExpand }: Props = $props();

	const count = $derived(gap.events.length);

	// Helper to format event name
	function getEventName(e: TimelineEvent): string {
		if (e.event_type === 'tool_call') {
			const toolName = e.metadata?.tool_name || 'Tool';
			return `Tool ${toolName}`;
		}
		if (e.event_type === 'subagent_spawn') return 'Subagent';
		if (e.event_type === 'prompt') return 'Prompt';
		if (e.metadata?.result_status === 'error') return 'Error';
		return e.event_type.charAt(0).toUpperCase() + e.event_type.slice(1).replace('_', ' ');
	}

	function handleGapClick() {
		// "Nearest two" logic: Reveal first 2 and last 2 events
		// This is a good default for the "bulk" expand button
		const events = gap.events;
		if (events.length <= 4) {
			onExpand(events.map((e) => e.id));
		} else {
			const toReveal = [...events.slice(0, 2), ...events.slice(events.length - 2)];
			onExpand(toReveal.map((e) => e.id));
		}
	}

	function handleItemClick(e: MouseEvent, eventId: string) {
		e.stopPropagation();
		onExpand([eventId]);
	}
</script>

<div class="group relative flex gap-4 min-h-[32px]">
	<!-- Left Column (Rail) -->
	<div class="w-10 flex flex-col items-center shrink-0">
		<!-- Dashed Line through -->
		<div
			class="w-px h-full border-l border-dashed border-[var(--border)] absolute left-5 top-0 bottom-0 -ml-px"
		></div>

		<!-- Interactive Node -->
		<button
			onclick={handleGapClick}
			class="
				relative z-10 mt-1.5
				h-4 w-4
				rounded-full
				bg-[var(--bg-base)]
				border border-[var(--border)]
				flex items-center justify-center
				text-[var(--text-muted)]
				hover:border-[var(--accent)] hover:text-[var(--accent)] hover:scale-110
				transition-all duration-200
				cursor-pointer
			"
			title="Show context"
		>
			<Plus size={10} strokeWidth={3} />
		</button>
	</div>

	<!-- Content -->
	<div class="flex-1 py-1 min-w-0 flex items-start">
		<div
			class="
             flex flex-wrap items-center gap-x-1 gap-y-1
             text-xs text-[var(--text-muted)]
             text-left
        "
		>
			<button
				onclick={handleGapClick}
				class="font-medium bg-[var(--bg-subtle)] px-1.5 py-0.5 rounded text-[10px] border border-[var(--border)] hover:text-[var(--text-primary)] transition-colors mr-1"
			>
				hidden ({count})
			</button>

			{#each gap.events as event, i}
				<button
					onclick={(e) => handleItemClick(e, event.id)}
					class="
                        hover:text-[var(--text-primary)]
                        hover:underline decoration-dashed underline-offset-2
                        transition-colors
                        cursor-pointer
                    "
				>
					{getEventName(event)}
				</button>
				{#if i < gap.events.length - 1}
					<span class="opacity-40">,</span>
				{/if}
			{/each}
		</div>
	</div>
</div>
