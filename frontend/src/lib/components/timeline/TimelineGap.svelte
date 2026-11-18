<script lang="ts">
	import type { TimelineGap } from '$lib/utils/timelineLogic.svelte';
	import { Plus } from 'lucide-svelte';
	import { GAP_LIST_LIMIT, getGapEventName, summarizeGap } from './timeline-gap';

	interface Props {
		gap: TimelineGap;
		onExpand: (ids: string[]) => void;
	}

	let { gap, onExpand }: Props = $props();

	const count = $derived(gap.events.length);
	// A long gap lists kinds with counts; naming hundreds of events one by one is unreadable.
	const summary = $derived(count > GAP_LIST_LIMIT ? summarizeGap(gap.events) : null);

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

	function reveal(e: MouseEvent, ids: string[]) {
		e.stopPropagation();
		onExpand(ids);
	}

	const itemClass =
		'max-w-full text-left [overflow-wrap:anywhere] hover:text-[var(--text-primary)] hover:underline decoration-dashed underline-offset-2 transition-colors cursor-pointer';
</script>

<div class="group relative flex gap-4 min-h-[32px]" data-gap-id={gap.id}>
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
			aria-label="Show the nearest hidden events"
			tabindex="-1"
		>
			<Plus size={10} strokeWidth={3} />
		</button>
	</div>

	<!-- Content -->
	<div class="flex-1 py-1 min-w-0 flex items-start">
		<div
			class="
             flex min-w-0 flex-wrap items-center gap-x-1.5 gap-y-1
             text-xs text-[var(--text-muted)]
             text-left
        "
		>
			<button
				onclick={handleGapClick}
				title="Show the nearest hidden events"
				data-gap-primary
				class="font-medium bg-[var(--bg-subtle)] px-1.5 py-0.5 rounded text-[10px] border border-[var(--border)] hover:text-[var(--text-primary)] transition-colors mr-1"
			>
				hidden ({count})
			</button>

			{#if summary}
				{#each summary.groups as group, i (group.key)}
					<!-- The comma sits against its item, not in a gap of its own -->
					<span class="inline-flex max-w-full items-baseline">
						<button
							onclick={(e) => reveal(e, group.ids)}
							title="Show these {group.count}"
							class={itemClass}
						>
							{group.count}
							{group.label}
						</button>{#if i < summary.groups.length - 1 || summary.otherKinds > 0}<span
								class="opacity-60">,</span
							>{/if}
					</span>
				{/each}
				{#if summary.otherKinds > 0}
					<span title="{summary.otherCount} more hidden events">
						and {summary.otherKinds} other {summary.otherKinds === 1 ? 'kind' : 'kinds'}
					</span>
				{/if}
			{:else}
				{#each gap.events as event, i (event.id)}
					<span class="inline-flex max-w-full items-baseline">
						<button onclick={(e) => reveal(e, [event.id])} class={itemClass}>
							{getGapEventName(event)}
						</button>{#if i < gap.events.length - 1}<span class="opacity-60">,</span
							>{/if}
					</span>
				{/each}
			{/if}
		</div>
	</div>
</div>
