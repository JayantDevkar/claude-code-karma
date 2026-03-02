<script lang="ts">
	import {
		SvelteFlow,
		Background,
		Controls,
		type Node,
		type Edge,
		type Connection
	} from '@xyflow/svelte';
	import '@xyflow/svelte/dist/style.css';
	import { Plus, LayoutGrid, Save, Play } from 'lucide-svelte';
	import type { WorkflowStep, WorkflowInput } from '$lib/api-types';
	import StepNode from './StepNode.svelte';
	import StepConfigPanel from './StepConfigPanel.svelte';
	import { getLayoutedElements } from './dagre-layout';

	let {
		initialNodes = [],
		initialEdges = [],
		initialSteps = [],
		initialInputs = [],
		workflowName = $bindable(''),
		workflowDescription = $bindable(''),
		onsave,
		onrun
	}: {
		initialNodes?: Node[];
		initialEdges?: Edge[];
		initialSteps?: WorkflowStep[];
		initialInputs?: WorkflowInput[];
		workflowName?: string;
		workflowDescription?: string;
		onsave: (data: {
			nodes: Node[];
			edges: Edge[];
			steps: WorkflowStep[];
			inputs: WorkflowInput[];
		}) => void;
		onrun: () => void;
	} = $props();

	const nodeTypes = {
		step: StepNode
	};

	let nodes = $state.raw<Node[]>(initialNodes);
	let edges = $state.raw<Edge[]>(initialEdges);
	let steps = $state<WorkflowStep[]>(initialSteps);
	let inputs = $state<WorkflowInput[]>(initialInputs);
	let selectedStepId = $state<string | null>(null);
	let stepCounter = $state(initialSteps.length);

	let selectedStep = $derived(steps.find((s) => s.id === selectedStepId) ?? null);

	function onconnect(connection: Connection) {
		const newEdge: Edge = {
			id: `e-${connection.source}-${connection.target}`,
			source: connection.source!,
			target: connection.target!,
			sourceHandle: connection.sourceHandle,
			targetHandle: connection.targetHandle,
			animated: true
		};
		edges = [...edges, newEdge];
	}

	function handleNodeClick({ node }: { node: Node; event: MouseEvent | TouchEvent }) {
		selectedStepId = node.id;
	}

	function addStep() {
		stepCounter++;
		const id = `step_${stepCounter}`;
		const newStep: WorkflowStep = {
			id,
			prompt_template: '',
			model: 'sonnet',
			tools: ['Read', 'Edit'],
			max_turns: 10,
			condition: null
		};

		const newNode: Node = {
			id,
			type: 'step',
			position: { x: 250, y: stepCounter * 100 },
			data: { label: id, model: 'sonnet', id }
		};

		steps = [...steps, newStep];
		nodes = [...nodes, newNode];
		selectedStepId = id;
	}

	function deleteSelectedStep() {
		if (!selectedStepId) return;
		const stepId = selectedStepId;
		steps = steps.filter((s) => s.id !== stepId);
		nodes = nodes.filter((n) => n.id !== stepId);
		edges = edges.filter((e) => e.source !== stepId && e.target !== stepId);
		selectedStepId = null;
	}

	function autoLayout() {
		const result = getLayoutedElements(nodes, edges, 'TB');
		nodes = result.nodes;
		edges = result.edges;
	}

	function syncNodeData() {
		// Keep node data in sync with step data
		nodes = nodes.map((node) => {
			const step = steps.find((s) => s.id === node.id);
			if (step) {
				return {
					...node,
					data: { ...node.data, label: step.id, model: step.model, id: step.id }
				};
			}
			return node;
		});
	}

	function handleStepUpdate(updatedStep: WorkflowStep) {
		steps = steps.map((s) => (s.id === updatedStep.id ? updatedStep : s));
		syncNodeData();
	}

	function handleSave() {
		onsave({ nodes, edges, steps, inputs });
	}
</script>

<div class="editor-container">
	<!-- Toolbar -->
	<div class="toolbar">
		<div class="toolbar-left">
			<input
				type="text"
				bind:value={workflowName}
				placeholder="Workflow name"
				class="toolbar-input name-input"
			/>
			<input
				type="text"
				bind:value={workflowDescription}
				placeholder="Description (optional)"
				class="toolbar-input desc-input"
			/>
		</div>
		<div class="toolbar-right">
			<button class="toolbar-btn" onclick={addStep} title="Add Step">
				<Plus size={14} />
				<span>Add Step</span>
			</button>
			<button class="toolbar-btn" onclick={autoLayout} title="Auto Layout">
				<LayoutGrid size={14} />
				<span>Layout</span>
			</button>
			<button class="toolbar-btn btn-primary" onclick={handleSave} title="Save">
				<Save size={14} />
				<span>Save</span>
			</button>
			<button class="toolbar-btn btn-accent" onclick={onrun} title="Run">
				<Play size={14} />
				<span>Run</span>
			</button>
		</div>
	</div>

	<!-- Canvas + Config Panel -->
	<div class="editor-body">
		<div class="canvas-area">
			<SvelteFlow
				bind:nodes
				bind:edges
				{nodeTypes}
				{onconnect}
				onnodeclick={handleNodeClick}
				fitView
			>
				<Background />
				<Controls />
			</SvelteFlow>
		</div>

		{#if selectedStep}
			<StepConfigPanel
				bind:step={
					() => selectedStep!,
					(v) => handleStepUpdate(v)
				}
				ondelete={deleteSelectedStep}
			/>
		{/if}
	</div>
</div>

<style>
	.editor-container {
		display: flex;
		flex-direction: column;
		height: 100%;
		border: 1px solid var(--border);
		border-radius: 8px;
		overflow: hidden;
		background: var(--bg-base);
	}

	.toolbar {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 8px 12px;
		border-bottom: 1px solid var(--border);
		background: var(--bg-subtle);
		gap: 12px;
		flex-wrap: wrap;
	}

	.toolbar-left {
		display: flex;
		gap: 8px;
		flex: 1;
		min-width: 0;
	}

	.toolbar-right {
		display: flex;
		gap: 6px;
		flex-shrink: 0;
	}

	.toolbar-input {
		padding: 5px 10px;
		border-radius: 4px;
		border: 1px solid var(--border);
		background: var(--bg-base);
		font-size: 13px;
		color: var(--text-primary);
	}

	.toolbar-input:focus {
		outline: none;
		border-color: var(--accent);
	}

	.name-input {
		width: 200px;
		font-weight: 500;
	}

	.desc-input {
		flex: 1;
		min-width: 120px;
	}

	.toolbar-btn {
		display: flex;
		align-items: center;
		gap: 4px;
		padding: 5px 10px;
		border-radius: 4px;
		border: 1px solid var(--border);
		background: var(--bg-base);
		color: var(--text-secondary);
		font-size: 12px;
		cursor: pointer;
		transition:
			border-color 0.15s ease,
			background 0.15s ease;
		white-space: nowrap;
	}

	.toolbar-btn:hover {
		border-color: var(--accent);
		color: var(--text-primary);
	}

	.btn-primary {
		background: var(--accent);
		color: white;
		border-color: var(--accent);
	}

	.btn-primary:hover {
		opacity: 0.9;
	}

	.btn-accent {
		background: #10b981;
		color: white;
		border-color: #10b981;
	}

	.btn-accent:hover {
		opacity: 0.9;
	}

	.editor-body {
		display: flex;
		flex: 1;
		min-height: 0;
	}

	.canvas-area {
		flex: 1;
		min-width: 0;
	}

	/* Override SvelteFlow styles to match our design system */
	.canvas-area :global(.svelte-flow) {
		background: var(--bg-base);
	}

	.canvas-area :global(.svelte-flow__edge-path) {
		stroke: var(--border);
		stroke-width: 2;
	}

	.canvas-area :global(.svelte-flow__edge.animated .svelte-flow__edge-path) {
		stroke: var(--accent);
	}

	.canvas-area :global(.svelte-flow__controls) {
		border: 1px solid var(--border);
		border-radius: 6px;
		overflow: hidden;
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
	}

	.canvas-area :global(.svelte-flow__controls-button) {
		background: var(--bg-subtle);
		border-bottom: 1px solid var(--border);
		color: var(--text-secondary);
	}

	.canvas-area :global(.svelte-flow__controls-button:hover) {
		background: var(--bg-muted);
	}

	.canvas-area :global(.svelte-flow__background pattern circle) {
		fill: var(--border);
	}
</style>
