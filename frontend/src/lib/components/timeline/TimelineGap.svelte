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

	function getEventName(e: TimelineEvent): string {
		if (e.event_type === 'tool_call') {
			const toolName = e.metadata?.tool_name || 'Tool';
			return String(toolName);
		}
		if (e.event_type === 'subagent_spawn') return 'Subagent';
		if (e.event_type === 'prompt') return 'Prompt';
		if (e.metadata?.result_status === 'error') return 'Error';
		return e.event_type.charAt(0).toUpperCase() + e.event_type.slice(1).replace('_', ' ');
	}

	function handleGapClick() {
		const events = gap.events;
		if (events.length <= 4) {
			onExpand(events.map((e) => e.id));
		} else {
			const toReveal = [...events.slice(0, 2), ...events.slice(events.length - 2)];
			onExpand(toReveal.map((e) => e.id));
		}
	}

	function handleGroupClick(e: MouseEvent, ids: string[]) {
		e.stopPropagation();
		onExpand(ids);
	}

	interface CompressedGroup {
		name: string;
		ids: string[];
		count: number;
	}

	const compressedEvents = $derived.by((): CompressedGroup[] => {
		const groups: CompressedGroup[] = [];
		for (const event of gap.events) {
			const name = getEventName(event);
			const last = groups[groups.length - 1];
			if (last && last.name === name) {
				last.ids.push(event.id);
				last.count++;
			} else {
				groups.push({ name, ids: [event.id], count: 1 });
			}
		}
		return groups;
	});
</script>

<!-- Gap: horizontal layout, no orphaned left rail -->
<div class="py-1.5 my-0.5 px-1">
	<div class="flex flex-wrap items-center gap-x-2 gap-y-1">
		<!-- Main expand button — min touch target 32px -->
		<button
			onclick={handleGapClick}
			class="inline-flex items-center gap-1.5
				min-h-[28px] px-2.5 py-1
				font-mono text-[10px] text-[var(--text-muted)]
				bg-[var(--bg-subtle)] border border-[var(--border)]
				rounded hover:border-[var(--accent)]/40 hover:text-[var(--text-primary)]
				transition-colors cursor-pointer"
			title="Show {count} collapsed events"
		>
			<Plus size={9} strokeWidth={3} />
			··· {count}
		</button>

		<!-- Compressed type groups -->
		<span class="text-[var(--text-faint)] text-[10px] opacity-50">—</span>
		{#each compressedEvents as group, i}
			<button
				onclick={(e) => handleGroupClick(e, group.ids)}
				class="text-[10px] text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:underline decoration-dashed underline-offset-2 transition-colors cursor-pointer"
			>
				{group.name}{#if group.count > 1}<span class="text-[var(--text-faint)] ml-0.5">({group.count})</span>{/if}
			</button>
			{#if i < compressedEvents.length - 1}
				<span class="text-[var(--text-faint)] opacity-40 text-[10px]">·</span>
			{/if}
		{/each}
	</div>
</div>
