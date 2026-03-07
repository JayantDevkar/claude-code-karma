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
	import { Plus, LayoutGrid, Save, Play, TextCursorInput, ChevronRight, Trash2 } from 'lucide-svelte';
	import type { WorkflowStep, WorkflowInput } from '$lib/api-types';
	import StepNode from './StepNode.svelte';
	import StepConfigPanel from './StepConfigPanel.svelte';
	import EdgeConfigPanel from './EdgeConfigPanel.svelte';
	import InputsPanel from './InputsPanel.svelte';
	import { getLayoutedElements } from './dagre-layout';

	let {
		initialNodes = [],
		initialEdges = [],
		initialSteps = [],
		initialInputs = [],
		workflowName = $bindable(''),
		workflowDescription = $bindable(''),
		workflowId,
		onsave,
		onrun,
		ondelete
	}: {
		initialNodes?: Node[];
		initialEdges?: Edge[];
		initialSteps?: WorkflowStep[];
		initialInputs?: WorkflowInput[];
		workflowName?: string;
		workflowDescription?: string;
		workflowId?: string;
		onsave: (data: {
			nodes: Node[];
			edges: Edge[];
			steps: WorkflowStep[];
			inputs: WorkflowInput[];
		}) => void;
		onrun?: () => void;
		ondelete?: () => void;
	} = $props();

	const nodeTypes = {
		step: StepNode
	};

	let nodes = $state.raw<Node[]>(initialNodes);
	let edges = $state.raw<Edge[]>(initialEdges);
	let steps = $state<WorkflowStep[]>(initialSteps);
	let inputs = $state<WorkflowInput[]>(initialInputs);
	let selectedStepId = $state<string | null>(null);
	let selectedEdgeId = $state<string | null>(null);
	let showInputsPanel = $state(false);
	let stepCounter = $state(
		initialSteps.reduce((max, s) => {
			const m = s.id.match(/^step_(\d+)$/);
			return m ? Math.max(max, parseInt(m[1])) : max;
		}, 0)
	);

	// Selection type: step, edge, or none
	type Selection = 'step' | 'edge' | 'inputs' | null;
	let panelMode = $derived.by<Selection>(() => {
		if (showInputsPanel) return 'inputs';
		if (selectedStepId) return 'step';
		if (selectedEdgeId) return 'edge';
		return null;
	});

	let selectedStep = $derived(steps.find((s) => s.id === selectedStepId) ?? null);
	let selectedEdge = $derived(edges.find((e) => e.id === selectedEdgeId) ?? null);

	function clearSelection() {
		selectedStepId = null;
		selectedEdgeId = null;
	}

	function onconnect(connection: Connection) {
		const newEdge: Edge = {
			id: `e-${connection.source}-${connection.target}`,
			source: connection.source!,
			target: connection.target!,
			sourceHandle: connection.sourceHandle,
			targetHandle: connection.targetHandle,
			animated: true,
			data: { condition: null }
		};
		edges = [...edges, newEdge];
	}

	function handleNodeClick({ node }: { node: Node; event: MouseEvent | TouchEvent }) {
		selectedEdgeId = null;
		showInputsPanel = false;
		selectedStepId = node.id;
	}

	function handleEdgeClick({ edge }: { edge: Edge; event: MouseEvent | TouchEvent }) {
		selectedStepId = null;
		showInputsPanel = false;
		selectedEdgeId = edge.id;
	}

	function handlePaneClick() {
		clearSelection();
		showInputsPanel = false;
	}

	function addStep() {
		stepCounter++;
		const id = `step_${stepCounter}`;
		const newStep: WorkflowStep = {
			id,
			label: null,
			prompt_template: '',
			model: 'sonnet',
			tools: ['Read', 'Edit'],
			max_turns: 10
		};

		const newNode: Node = {
			id,
			type: 'step',
			position: { x: 250, y: stepCounter * 120 },
			data: { label: null, model: 'sonnet', id, prompt_template: '', tools: ['Read', 'Edit'] }
		};

		steps = [...steps, newStep];
		nodes = [...nodes, newNode];
		selectedEdgeId = null;
		showInputsPanel = false;
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

	function deleteSelectedEdge() {
		if (!selectedEdgeId) return;
		edges = edges.filter((e) => e.id !== selectedEdgeId);
		selectedEdgeId = null;
	}

	function autoLayout() {
		const result = getLayoutedElements(nodes, edges, 'TB');
		nodes = result.nodes;
		edges = result.edges;
	}

	function syncNodeData() {
		nodes = nodes.map((node) => {
			const step = steps.find((s) => s.id === node.id);
			if (step) {
				return {
					...node,
					data: {
						...node.data,
						label: step.label,
						model: step.model,
						id: step.id,
						prompt_template: step.prompt_template,
						tools: step.tools
					}
				};
			}
			return node;
		});
	}

	function handleStepUpdate(updatedStep: WorkflowStep) {
		steps = steps.map((s) => (s.id === updatedStep.id ? updatedStep : s));
		syncNodeData();
	}

	function handleEdgeUpdate(updatedEdge: Edge) {
		edges = edges.map((e) => (e.id === updatedEdge.id ? updatedEdge : e));
	}

	function handleSave() {
		// Sync edge conditions into the edges array for serialization
		const edgesWithConditions = edges.map((e) => ({
			...e,
			data: e.data || {}
		}));
		onsave({ nodes, edges: edgesWithConditions, steps, inputs });
	}

	function toggleInputsPanel() {
		if (showInputsPanel) {
			showInputsPanel = false;
		} else {
			clearSelection();
			showInputsPanel = true;
		}
	}
</script>

<div class="editor-container">
	<!-- Toolbar -->
	<div class="toolbar">
		<div class="toolbar-left">
			<!-- Breadcrumbs (#8) -->
			<nav class="breadcrumbs" aria-label="Breadcrumb">
				<a href="/" class="crumb">Dashboard</a>
				<ChevronRight size={12} class="crumb-sep" />
				<a href="/workflows" class="crumb">Workflows</a>
				<ChevronRight size={12} class="crumb-sep" />
				<span class="crumb crumb-current">{workflowId ? 'Edit' : 'New'}</span>
			</nav>
			<div class="toolbar-divider"></div>
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
			<button
				class="toolbar-btn"
				class:btn-active={showInputsPanel}
				onclick={toggleInputsPanel}
				title="Manage Inputs"
			>
				<TextCursorInput size={14} />
				<span>Inputs</span>
				{#if inputs.length > 0}
					<span class="badge">{inputs.length}</span>
				{/if}
			</button>
			<button class="toolbar-btn" onclick={autoLayout} title="Auto Layout">
				<LayoutGrid size={14} />
				<span>Layout</span>
			</button>
			<button class="toolbar-btn btn-primary" onclick={handleSave} title="Save">
				<Save size={14} />
				<span>Save</span>
			</button>
			<!-- #9: Only show Run when workflow is saved -->
			{#if workflowId && onrun}
				<button class="toolbar-btn btn-accent" onclick={onrun} title="Run">
					<Play size={14} />
					<span>Run</span>
				</button>
			{/if}
			<!-- #5: Delete button (only on saved workflows) -->
			{#if workflowId && ondelete}
				<button class="toolbar-btn btn-danger" onclick={ondelete} title="Delete Workflow">
					<Trash2 size={14} />
				</button>
			{/if}
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
				onedgeclick={handleEdgeClick}
				onpaneclick={handlePaneClick}
				fitView
			>
				<Background />
				<Controls />
			</SvelteFlow>
		</div>

		{#if panelMode === 'step' && selectedStep}
			<StepConfigPanel
				bind:step={
					() => selectedStep!,
					(v) => handleStepUpdate(v)
				}
				ondelete={deleteSelectedStep}
			/>
		{:else if panelMode === 'edge' && selectedEdge}
			<EdgeConfigPanel
				bind:edge={
					() => selectedEdge!,
					(v) => handleEdgeUpdate(v)
				}
				ondelete={deleteSelectedEdge}
			/>
		{:else if panelMode === 'inputs'}
			<InputsPanel bind:inputs onclose={() => (showInputsPanel = false)} />
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
		align-items: center;
		gap: 8px;
		flex: 1;
		min-width: 0;
	}

	.toolbar-right {
		display: flex;
		gap: 6px;
		flex-shrink: 0;
	}

	/* Breadcrumbs */
	.breadcrumbs {
		display: flex;
		align-items: center;
		gap: 4px;
		flex-shrink: 0;
	}

	.crumb {
		font-size: 12px;
		color: var(--text-muted);
		text-decoration: none;
		transition: color 0.15s;
	}
	.crumb:hover {
		color: var(--accent);
	}
	.crumb-current {
		color: var(--text-primary);
		font-weight: 500;
	}
	.breadcrumbs :global(.crumb-sep) {
		color: var(--text-faint);
		flex-shrink: 0;
	}

	.toolbar-divider {
		width: 1px;
		height: 20px;
		background: var(--border);
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
		width: 180px;
		font-weight: 500;
	}

	.desc-input {
		flex: 1;
		min-width: 100px;
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

	.btn-active {
		border-color: var(--accent);
		background: var(--accent-subtle, rgba(124, 58, 237, 0.1));
		color: var(--accent);
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

	.btn-danger {
		color: var(--error, #ef4444);
		border-color: var(--border);
	}
	.btn-danger:hover {
		background: var(--error-subtle, rgba(239, 68, 68, 0.1));
		border-color: var(--error, #ef4444);
		color: var(--error, #ef4444);
	}

	.badge {
		font-size: 10px;
		font-weight: 600;
		background: var(--accent);
		color: white;
		padding: 0 5px;
		border-radius: 9999px;
		min-width: 16px;
		text-align: center;
		line-height: 16px;
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

	.canvas-area :global(.svelte-flow__edge.selected .svelte-flow__edge-path) {
		stroke: var(--accent);
		stroke-width: 3;
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
