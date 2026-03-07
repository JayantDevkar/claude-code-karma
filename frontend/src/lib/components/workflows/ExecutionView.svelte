<script lang="ts">
	import {
		SvelteFlow,
		Background,
		Controls,
		type Node,
		type Edge,
		type NodeTypes
	} from '@xyflow/svelte';
	import '@xyflow/svelte/dist/style.css';

	import StepNode from './StepNode.svelte';
	import { getLayoutedElements } from './dagre-layout';
	import { statusColors } from './constants';
	import type { WorkflowRun, WorkflowRunStep } from '$lib/api-types';

	let { run, graphNodes, graphEdges }: { run: WorkflowRun; graphNodes: any[]; graphEdges: any[] } =
		$props();

	const nodeTypes: NodeTypes = {
		step: StepNode
	};

	let selectedStepId = $state<string | null>(null);

	let stepMap = $derived(
		new Map<string, WorkflowRunStep>(run.steps.map((s) => [s.step_id, s]))
	);

	let selectedStep = $derived(selectedStepId ? stepMap.get(selectedStepId) ?? null : null);

	let layouted = $derived.by(() => {
		const flowNodes: Node[] = graphNodes.map((gn) => {
			const runStep = stepMap.get(gn.id);
			const status = runStep?.status ?? 'pending';
			return {
				id: gn.id,
				type: 'step',
				position: { x: 0, y: 0 },
				data: {
					label: gn.data?.label ?? gn.id,
					model: gn.data?.model ?? null
				},
				style: `border: 2px solid ${statusColors[status]}; border-radius: 6px;`
			};
		});

		const flowEdges: Edge[] = graphEdges.map((ge) => ({
			id: `${ge.source}-${ge.target}`,
			source: ge.source,
			target: ge.target,
			animated: stepMap.get(ge.source)?.status === 'running'
		}));

		return getLayoutedElements(flowNodes, flowEdges);
	});

	let nodes = $state.raw<Node[]>([]);
	let edges = $state.raw<Edge[]>([]);

	$effect(() => {
		nodes = layouted.nodes;
		edges = layouted.edges;
	});

	function handleNodeClick({ node }: { node: Node; event: MouseEvent | TouchEvent }) {
		selectedStepId = selectedStepId === node.id ? null : node.id;
	}

	function formatTime(iso: string | null): string {
		if (!iso) return '--';
		return new Date(iso).toLocaleString();
	}
</script>

<div class="execution-container">
	<div class="status-bar">
		<div class="status-bar-left">
			<span class="run-id font-mono">{run.id.slice(0, 8)}</span>
			<span
				class="status-badge"
				style="background-color: {statusColors[run.status]}"
			>
				{run.status}
			</span>
			{#if run.started_at}
				<span class="started-time">{formatTime(run.started_at)}</span>
			{/if}
		</div>
		{#if run.error}
			<span class="run-error">{run.error}</span>
		{/if}
	</div>

	<div class="main-content">
		<div class="flow-container">
			<SvelteFlow
				bind:nodes
				bind:edges
				{nodeTypes}
				nodesDraggable={false}
				nodesConnectable={false}
				onnodeclick={handleNodeClick}
				fitView
			>
				<Background />
				<Controls />
			</SvelteFlow>
		</div>

		{#if selectedStep}
			<div class="side-panel">
				<div class="panel-header">
					<h3 class="panel-title">{selectedStepId}</h3>
					<button class="panel-close" aria-label="Close panel" onclick={() => (selectedStepId = null)}>&times;</button>
				</div>

				<div class="panel-section">
					<div class="panel-label">Status</div>
					<span
						class="status-badge"
						style="background-color: {statusColors[selectedStep.status]}"
					>
						{selectedStep.status}
					</span>
				</div>

				{#if selectedStep.started_at}
					<div class="panel-section">
						<div class="panel-label">Started</div>
						<div class="panel-value">{formatTime(selectedStep.started_at)}</div>
					</div>
				{/if}

				{#if selectedStep.completed_at}
					<div class="panel-section">
						<div class="panel-label">Completed</div>
						<div class="panel-value">{formatTime(selectedStep.completed_at)}</div>
					</div>
				{/if}

				{#if selectedStep.session_id}
					<div class="panel-section">
						<div class="panel-label">Session</div>
						<a href="/sessions/{selectedStep.session_id}" class="session-link">
							{selectedStep.session_id.slice(0, 12)}...
						</a>
					</div>
				{/if}

				{#if selectedStep.error}
					<div class="panel-section">
						<div class="panel-label">Error</div>
						<div class="error-text">{selectedStep.error}</div>
					</div>
				{/if}

				{#if selectedStep.output}
					<div class="panel-section">
						<div class="panel-label">Output</div>
						<pre class="output-text">{selectedStep.output}</pre>
					</div>
				{/if}
			</div>
		{/if}
	</div>
</div>

<style>
	.execution-container {
		display: flex;
		flex-direction: column;
		height: 100%;
	}

	.status-bar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 8px 16px;
		border-bottom: 1px solid var(--border);
		background: var(--bg-subtle);
		gap: 12px;
		flex-shrink: 0;
	}

	.status-bar-left {
		display: flex;
		align-items: center;
		gap: 10px;
	}

	.run-id {
		font-size: 13px;
		color: var(--text-primary);
		font-weight: 600;
	}

	.status-badge {
		font-size: 10px;
		padding: 2px 8px;
		border-radius: 9999px;
		color: white;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}

	.started-time {
		font-size: 12px;
		color: var(--text-muted);
	}

	.run-error {
		font-size: 12px;
		color: #ef4444;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		max-width: 400px;
	}

	.main-content {
		display: flex;
		flex: 1;
		min-height: 0;
	}

	.flow-container {
		flex: 1;
		min-width: 0;
	}

	.side-panel {
		width: 300px;
		border-left: 1px solid var(--border);
		background: var(--bg-subtle);
		overflow-y: auto;
		flex-shrink: 0;
	}

	.panel-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 12px 16px;
		border-bottom: 1px solid var(--border);
	}

	.panel-title {
		font-size: 14px;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
	}

	.panel-close {
		background: none;
		border: none;
		color: var(--text-muted);
		font-size: 18px;
		cursor: pointer;
		padding: 0 4px;
		line-height: 1;
	}

	.panel-close:hover {
		color: var(--text-primary);
	}

	.panel-section {
		padding: 10px 16px;
		border-bottom: 1px solid var(--border);
	}

	.panel-label {
		font-size: 11px;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin-bottom: 4px;
	}

	.panel-value {
		font-size: 13px;
		color: var(--text-secondary);
	}

	.session-link {
		font-size: 13px;
		color: var(--accent);
		text-decoration: none;
		font-family: 'JetBrains Mono', monospace;
	}

	.session-link:hover {
		text-decoration: underline;
	}

	.error-text {
		font-size: 12px;
		color: #ef4444;
		white-space: pre-wrap;
		word-break: break-word;
	}

	.output-text {
		font-size: 12px;
		color: var(--text-secondary);
		white-space: pre-wrap;
		word-break: break-word;
		margin: 0;
		font-family: 'JetBrains Mono', monospace;
		max-height: 200px;
		overflow-y: auto;
	}
</style>
