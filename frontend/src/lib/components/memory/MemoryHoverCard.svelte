<script lang="ts">
	import { formatDistanceToNow } from 'date-fns';
	import type { MemoryFileMeta } from '$lib/api-types';
	import { badgeClass, badgeLabel } from './memoryTypeBadge';

	interface Props {
		file: MemoryFileMeta | null;
		anchorRect: DOMRect | null;
	}

	let { file, anchorRect }: Props = $props();

	// Card dimensions used for viewport-flip math
	const CARD_WIDTH = 320;
	const CARD_OFFSET = 8;
	// Estimated card height (matches the rendered content's typical extent).
	// Used only to decide whether to flip above the anchor when there's not
	// enough room below.
	const ESTIMATED_CARD_HEIGHT = 160;

	// Compute absolute screen position. Default below the anchor; flip above if
	// there's not enough room below.
	const position = $derived.by(() => {
		if (!anchorRect) return null;

		const viewportWidth = typeof window !== 'undefined' ? window.innerWidth : 1024;
		const viewportHeight = typeof window !== 'undefined' ? window.innerHeight : 768;

		// Horizontally: align to the left of the anchor, but clamp to viewport.
		let left = anchorRect.left;
		if (left + CARD_WIDTH > viewportWidth - 8) {
			left = Math.max(8, viewportWidth - CARD_WIDTH - 8);
		}
		left = Math.max(8, left);

		// Vertically: prefer below; flip above if not enough room.
		const spaceBelow = viewportHeight - anchorRect.bottom;
		const spaceAbove = anchorRect.top;
		let top: number;
		if (spaceBelow >= ESTIMATED_CARD_HEIGHT + CARD_OFFSET || spaceBelow >= spaceAbove) {
			top = anchorRect.bottom + CARD_OFFSET;
		} else {
			top = Math.max(8, anchorRect.top - ESTIMATED_CARD_HEIGHT - CARD_OFFSET);
		}

		return { left, top };
	});

	function formatRelative(dateStr: string): string {
		try {
			return formatDistanceToNow(new Date(dateStr), { addSuffix: true });
		} catch {
			return dateStr;
		}
	}
</script>

{#if file && position}
	<div
		role="tooltip"
		class="memory-hover-card fixed z-50 pointer-events-none rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)] shadow-xl"
		style="left: {position.left}px; top: {position.top}px; width: {CARD_WIDTH}px;"
		data-testid="memory-hover-card"
	>
		<div class="px-3.5 py-3 space-y-2">
			<div class="flex items-center justify-between gap-2">
				<span class={badgeClass(file.type)} data-testid="hover-card-badge">
					{badgeLabel(file.type)}
				</span>
				<span class="text-[10px] text-[var(--text-muted)]">
					{formatRelative(file.modified)}
				</span>
			</div>
			<div class="text-sm font-semibold text-[var(--text-primary)] leading-snug">
				{file.name}
			</div>
			{#if file.description}
				<p class="text-xs text-[var(--text-secondary)] leading-relaxed line-clamp-3">
					{file.description}
				</p>
			{/if}
			<div class="flex items-center justify-between pt-1.5 border-t border-[var(--border)]">
				<span class="text-[10px] text-[var(--text-muted)]">
					{file.word_count.toLocaleString()} words
				</span>
				<span class="text-[10px] text-[var(--text-muted)] font-mono truncate ml-2 max-w-[160px]">
					{file.filename}
				</span>
			</div>
		</div>
	</div>
{/if}

<style>
	.memory-hover-card :global(.line-clamp-3) {
		display: -webkit-box;
		-webkit-line-clamp: 3;
		line-clamp: 3;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}
</style>
