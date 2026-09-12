<script lang="ts">
	import '@xyflow/svelte/dist/style.css';
	import {
		SvelteFlow,
		Background,
		BackgroundVariant,
		Controls,
		MiniMap,
		Panel,
		type Node,
		type Edge
	} from '@xyflow/svelte';
	import { untrack } from 'svelte';
	import { ChevronDown } from 'lucide-svelte';
	import type { WorkflowThread } from './types';
	import { buildGraph } from './flow-build';
	import { TIER_ROWS, TIER_NAMES, metaFor } from './kinds';
	import NodeGlyph from './NodeGlyph.svelte';
	import WorkflowNode from './WorkflowNode.svelte';

	interface Props {
		threads: WorkflowThread[];
		selectedId: string | null;
		onselect: (id: string) => void;
		onbackgroundclick?: () => void;
	}

	let { threads, selectedId, onselect, onbackgroundclick }: Props = $props();

	const nodeTypes = { wf: WorkflowNode };

	// Build the graph once; Svelte Flow owns node/edge state after that so drags
	// stick. The parent remounts this component (keyed on project) if data swaps.
	const initial = untrack(() => buildGraph(threads, onselect));
	let nodes = $state.raw<Node[]>(initial.nodes);
	let edges = $state.raw<Edge[]>(initial.edges);

	// Mirror the current selection onto node.selected so the ring follows a
	// programmatic change (e.g. the drawer's "supersedes" jump). Read `nodes`
	// untracked and only write when something actually changed, otherwise the
	// effect would retrigger itself on every run (new array each map()).
	$effect(() => {
		const sel = selectedId;
		const current = untrack(() => nodes);
		if (current.some((n) => Boolean(n.selected) !== (n.id === sel))) {
			nodes = current.map((n) =>
				Boolean(n.selected) === (n.id === sel) ? n : { ...n, selected: n.id === sel }
			);
		}
	});

	let legendOpen = $state(true);

	function nodeColor(n: Node): string {
		const kind = (n.data as { node?: { kind?: string } })?.node?.kind ?? 'process';
		return metaFor(kind).color;
	}
</script>

<div class="wf-canvas">
	<SvelteFlow
		bind:nodes
		bind:edges
		{nodeTypes}
		fitView
		fitViewOptions={{ padding: 0.2 }}
		minZoom={0.2}
		maxZoom={2}
		nodesConnectable={false}
		colorMode="light"
		defaultEdgeOptions={{ type: 'smoothstep', style: 'stroke: #cbd5e1; stroke-width: 1.5;' }}
		onnodeclick={({ node }) => onselect(node.id)}
		onpaneclick={() => onbackgroundclick?.()}
	>
		<Background
			variant={BackgroundVariant.Dots}
			gap={24}
			size={1.4}
			bgColor="#ffffff"
			patternColor="#dfe5ec"
		/>
		<Controls showLock={false} />
		<MiniMap pannable zoomable {nodeColor} nodeStrokeWidth={2} />

		<Panel position="top-left">
			<div class="wf-legend">
				<button
					class="wf-legend-head"
					onclick={() => (legendOpen = !legendOpen)}
					aria-expanded={legendOpen}
				>
					<span>Legend</span>
					<ChevronDown
						class="h-3.5 w-3.5 transition-transform {legendOpen ? '' : '-rotate-90'}"
					/>
				</button>
				{#if legendOpen}
					<div class="wf-legend-body">
						{#each TIER_ROWS as row, tier (tier)}
							<div class="wf-legend-tier">
								<span class="wf-legend-tier-name">{TIER_NAMES[tier]}</span>
								<div class="wf-legend-chips">
									{#each row as kind (kind)}
										{@const meta = metaFor(kind)}
										<span class="wf-legend-chip" title={meta.gloss}>
											<NodeGlyph {kind} size={15} />
											{meta.word}
										</span>
									{/each}
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</div>
		</Panel>
	</SvelteFlow>
</div>

<style>
	.wf-canvas {
		position: absolute;
		inset: 0;
	}
	.wf-canvas :global(.svelte-flow) {
		background: #ffffff;
	}
	/* Strip Svelte Flow's default node chrome so only our own shape shows —
	   the default box was the "border on top and bottom only" artefact. */
	.wf-canvas :global(.svelte-flow__node) {
		font-family: inherit;
		background: transparent;
		border: none;
		border-radius: 0;
		box-shadow: none;
		padding: 0;
		width: auto;
		color: var(--text-primary);
	}
	.wf-canvas :global(.svelte-flow__node.selected),
	.wf-canvas :global(.svelte-flow__node:focus),
	.wf-canvas :global(.svelte-flow__node:focus-visible) {
		box-shadow: none;
		outline: none;
	}
	.wf-canvas :global(.svelte-flow__handle) {
		opacity: 0;
		border: none;
		min-width: 1px;
		min-height: 1px;
		width: 1px;
		height: 1px;
	}
	.wf-canvas :global(.svelte-flow__edge-textbg) {
		fill: #ffffff;
	}
	.wf-canvas :global(.svelte-flow__edge-text) {
		fill: var(--text-muted);
		font-size: 9px;
	}

	.wf-legend {
		width: 190px;
		border: 1px solid var(--border);
		border-radius: 8px;
		background: color-mix(in srgb, var(--bg-subtle) 92%, transparent);
		backdrop-filter: blur(6px);
		box-shadow: var(--shadow-sm, 0 1px 2px rgb(0 0 0 / 0.05));
		overflow: hidden;
	}
	.wf-legend-head {
		display: flex;
		width: 100%;
		align-items: center;
		justify-content: space-between;
		padding: 6px 10px;
		font-size: 10px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--text-secondary);
	}
	.wf-legend-body {
		padding: 4px 10px 8px;
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.wf-legend-tier-name {
		display: block;
		font-size: 8.5px;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--text-faint);
		margin-bottom: 2px;
	}
	.wf-legend-chips {
		display: flex;
		flex-wrap: wrap;
		gap: 3px 6px;
	}
	.wf-legend-chip {
		display: inline-flex;
		align-items: center;
		gap: 3px;
		font-size: 10.5px;
		color: var(--text-secondary);
	}
</style>
