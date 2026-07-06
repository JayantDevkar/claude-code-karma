<script lang="ts">
	import { onMount } from 'svelte';
	import type { TurnGroup } from '$lib/utils/groupIntoTurns';

	interface Props {
		turns: TurnGroup[];
		onScrollTo: (turnIndex: number) => void;
	}

	let { turns, onScrollTo }: Props = $props();

	let scrollRatio = $state(0);
	let viewportRatio = $state(1);

	// Compute cumulative event counts for proportional positioning
	const totalEvents = $derived(turns.reduce((sum, t) => sum + t.totalEventCount, 0));

	interface TurnSegment {
		y: number;   // 0-100
		h: number;   // 0-100
		hasError: boolean;
		hasResponse: boolean;
		isLive: boolean;
		turnIndex: number;
	}

	const segments = $derived.by<TurnSegment[]>(() => {
		if (totalEvents === 0) return [];
		const result: TurnSegment[] = [];
		let cumulative = 0;
		for (let i = 0; i < turns.length; i++) {
			const t = turns[i];
			const y = (cumulative / totalEvents) * 100;
			const h = Math.max((t.totalEventCount / totalEvents) * 100, 1.5);
			result.push({
				y,
				h,
				hasError: t.hasErrors,
				hasResponse: t.response != null,
				isLive: t.isLive,
				turnIndex: i
			});
			cumulative += t.totalEventCount;
		}
		return result;
	});

	// Outcome coloring: the strip reads as a health bar of the session.
	function getColor(seg: TurnSegment): string {
		if (seg.hasError) return 'var(--error)';
		if (seg.isLive) return 'var(--accent)';
		if (seg.hasResponse) return 'var(--success)';
		return 'var(--text-faint)';
	}

	function getOpacity(seg: TurnSegment): number {
		if (seg.hasError) return 0.9;
		if (seg.isLive) return 0.8;
		if (seg.hasResponse) return 0.55;
		return 0.4;
	}

	onMount(() => {
		function update() {
			const el = document.documentElement;
			const maxScroll = el.scrollHeight - el.clientHeight;
			scrollRatio = maxScroll > 0 ? el.scrollTop / maxScroll : 0;
			viewportRatio = el.scrollHeight > 0 ? el.clientHeight / el.scrollHeight : 1;
		}
		window.addEventListener('scroll', update, { passive: true });
		window.addEventListener('resize', update, { passive: true });
		update();
		return () => {
			window.removeEventListener('scroll', update);
			window.removeEventListener('resize', update);
		};
	});
</script>

{#if turns.length > 3}
	<div
		class="fixed right-2 z-10"
		style="top: 56px; bottom: 8px; width: 12px; pointer-events: none;"
		aria-hidden="true"
	>
		<svg
			class="w-full h-full"
			style="pointer-events: auto; display: block;"
			viewBox="0 0 12 100"
			preserveAspectRatio="none"
			xmlns="http://www.w3.org/2000/svg"
		>
			{#each segments as seg}
				<!-- svelte-ignore a11y_click_events_have_key_events a11y_interactive_supports_focus -->
				<rect
					x="2"
					y={seg.y}
					width="8"
					height={Math.max(seg.h - 0.5, 1)}
					rx="0.5"
					fill={getColor(seg)}
					opacity={getOpacity(seg)}
					onclick={() => onScrollTo(seg.turnIndex)}
					class="cursor-pointer"
					role="button"
					tabindex="0"
					onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') onScrollTo(seg.turnIndex); }}
					aria-label="Jump to turn {seg.turnIndex + 1}"
				/>
				<!-- Prompt tick: neutral boundary marker at each turn start -->
				<rect
					x="0.5"
					y={seg.y}
					width="11"
					height="0.6"
					fill="var(--text-muted)"
					opacity="0.7"
					style="pointer-events: none;"
				/>
			{/each}
			<!-- Viewport indicator -->
			<rect
				x="0.5"
				y={scrollRatio * 100}
				width="11"
				height={Math.max(viewportRatio * 100, 2)}
				fill="none"
				stroke="var(--text-faint)"
				stroke-width="0.8"
				opacity="0.3"
				style="pointer-events: none;"
			/>
		</svg>
	</div>
{/if}
