<script lang="ts">
	import { Handle, Position, type NodeProps } from '@xyflow/svelte';
	import { metaFor, fillFor, shapeSpec } from './kinds';
	import type { WorkflowNode } from './types';

	let { data, selected }: NodeProps = $props();

	const node = $derived(data.node as WorkflowNode);
	const threadTitle = $derived(data.threadTitle as string | undefined);
	const open = $derived(data.open as (id: string) => void);
	const meta = $derived(metaFor(node.kind));

	const dims = $derived(
		node.tier === 1 ? { w: 188, h: 66 } : node.tier === 2 ? { w: 72, h: 72 } : { w: 62, h: 44 }
	);
	const glyphSize = $derived(Math.min(dims.w, dims.h) - 8);
	const spec = $derived(shapeSpec(meta.shape, dims.w / 2, dims.h / 2, glyphSize));
	const initialSize = $derived(node.tier === 3 ? 12 : meta.initial.length > 1 ? 13 : 18);

	function titleLines(s: string, per = 24): string[] {
		if (s.length <= per) return [s];
		let cut = s.lastIndexOf(' ', per);
		if (cut < 8) cut = per;
		let rest = s.slice(cut).trim();
		if (rest.length > per) rest = rest.slice(0, per - 1) + '…';
		return [s.slice(0, cut), rest];
	}

	function activate(e: KeyboardEvent) {
		if (e.key === 'Enter' || e.key === ' ') {
			e.preventDefault();
			open(node.id);
		}
	}

	const HANDLES = [
		{ id: 'l-t', type: 'target', position: Position.Left },
		{ id: 'l-s', type: 'source', position: Position.Left },
		{ id: 'r-t', type: 'target', position: Position.Right },
		{ id: 'r-s', type: 'source', position: Position.Right },
		{ id: 't-t', type: 'target', position: Position.Top },
		{ id: 't-s', type: 'source', position: Position.Top },
		{ id: 'b-t', type: 'target', position: Position.Bottom },
		{ id: 'b-s', type: 'source', position: Position.Bottom }
	] as const;
</script>

<div
	class="wf-node"
	class:is-selected={selected}
	class:is-superseded={node.status === 'superseded'}
	style="width: {dims.w}px; height: {dims.h}px;"
	role="button"
	tabindex="0"
	aria-label={`${node.label}: ${node.title}`}
	onclick={() => open(node.id)}
	onkeydown={activate}
>
	{#each HANDLES as h (h.id)}
		<Handle id={h.id} type={h.type} position={h.position} class="wf-handle" />
	{/each}

	<svg
		width={dims.w}
		height={dims.h}
		viewBox={`0 0 ${dims.w} ${dims.h}`}
		class="wf-shape"
		style="--ring: {meta.color}"
	>
		{#if node.tier === 1}
			<rect
				x="2"
				y="2"
				width={dims.w - 4}
				height={dims.h - 4}
				rx="12"
				fill={fillFor(node.kind)}
				stroke={meta.color}
				stroke-width="2"
				vector-effect="non-scaling-stroke"
			/>
			<circle
				cx="18"
				cy="18"
				r="11"
				fill="#ffffff"
				stroke={meta.color}
				stroke-width="1.75"
				vector-effect="non-scaling-stroke"
			/>
			<text
				x="18"
				y="18"
				text-anchor="middle"
				dominant-baseline="central"
				font-size="11"
				font-weight="700"
				fill={meta.color}>{meta.initial}</text
			>
			{#each titleLines(threadTitle ?? node.title) as line, i (i)}
				<text
					x={dims.w / 2 + 8}
					y={dims.h / 2 -
						(titleLines(threadTitle ?? node.title).length === 2 ? 7 : 0) +
						i * 14}
					text-anchor="middle"
					dominant-baseline="central"
					font-size="11.5"
					font-weight="600"
					fill="var(--text-primary)">{line}</text
				>
			{/each}
		{:else}
			{#if spec.el === 'circle'}
				<circle
					{...spec.attrs}
					fill={fillFor(node.kind)}
					stroke={meta.color}
					stroke-width="2"
					vector-effect="non-scaling-stroke"
				/>
			{:else if spec.el === 'rect'}
				<rect
					{...spec.attrs}
					fill={fillFor(node.kind)}
					stroke={meta.color}
					stroke-width="2"
					vector-effect="non-scaling-stroke"
				/>
			{:else}
				<polygon
					{...spec.attrs}
					fill={fillFor(node.kind)}
					stroke={meta.color}
					stroke-width="2"
					vector-effect="non-scaling-stroke"
				/>
			{/if}
			<text
				x={dims.w / 2}
				y={dims.h / 2}
				text-anchor="middle"
				dominant-baseline="central"
				font-size={initialSize}
				font-weight="700"
				fill={meta.color}>{meta.initial}</text
			>
		{/if}
	</svg>

	<span class="wf-caption" class:is-strong={selected}>{node.label}</span>
</div>

<style>
	.wf-node {
		position: relative;
		cursor: pointer;
		outline: none;
	}
	.wf-shape {
		display: block;
		overflow: visible;
		transition: filter 120ms ease;
	}
	.wf-node:hover .wf-shape {
		filter: brightness(1.04) drop-shadow(0 1px 2px rgb(15 23 42 / 0.12));
	}
	/* accent ring that hugs the real silhouette of any shape */
	.wf-node.is-selected .wf-shape {
		filter: drop-shadow(0 0 1.5px var(--accent)) drop-shadow(0 0 1.5px var(--accent))
			drop-shadow(0 0 6px color-mix(in srgb, var(--accent) 55%, transparent));
	}
	.wf-node:focus-visible .wf-shape {
		filter: drop-shadow(0 0 1.5px var(--accent)) drop-shadow(0 0 1.5px var(--accent));
	}
	.wf-node.is-superseded .wf-shape {
		opacity: 0.62;
	}
	.wf-caption {
		position: absolute;
		top: 100%;
		left: 50%;
		transform: translateX(-50%);
		margin-top: 4px;
		font-size: 10px;
		line-height: 1;
		white-space: nowrap;
		color: var(--text-muted);
		pointer-events: none;
	}
	.wf-caption.is-strong {
		color: var(--accent);
		font-weight: 600;
	}
	:global(.wf-handle) {
		opacity: 0;
		pointer-events: none;
	}
</style>
