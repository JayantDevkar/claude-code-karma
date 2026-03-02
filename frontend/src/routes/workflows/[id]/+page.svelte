<script lang="ts">
	import { goto } from '$app/navigation';
	import { API_BASE } from '$lib/config';
	import WorkflowEditor from '$lib/components/workflows/WorkflowEditor.svelte';
	import type { Workflow, WorkflowStep, WorkflowInput } from '$lib/api-types';
	import type { Node, Edge } from '@xyflow/svelte';

	let { data } = $props();
	let workflow: Workflow = $derived(data.workflow);

	let workflowName = $state(workflow.name);
	let workflowDescription = $state(workflow.description || '');

	async function handleSave(editorData: {
		nodes: Node[];
		edges: Edge[];
		steps: WorkflowStep[];
		inputs: WorkflowInput[];
	}) {
		try {
			const resp = await fetch(`${API_BASE}/workflows/${workflow.id}`, {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					name: workflowName,
					description: workflowDescription || null,
					graph: { nodes: editorData.nodes, edges: editorData.edges },
					steps: editorData.steps,
					inputs: editorData.inputs
				})
			});
			if (!resp.ok) {
				const err = await resp.text();
				alert(`Failed to save workflow: ${err}`);
				return;
			}
			alert('Workflow saved successfully');
		} catch (e) {
			alert(`Error saving workflow: ${e instanceof Error ? e.message : 'Network error'}`);
		}
	}

	async function handleRun() {
		try {
			const resp = await fetch(`${API_BASE}/workflows/${workflow.id}/run`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ input_values: {} })
			});
			if (!resp.ok) {
				const err = await resp.text();
				alert(`Failed to run workflow: ${err}`);
				return;
			}
			const run = await resp.json();
			goto(`/workflows/${workflow.id}/runs/${run.id}`);
		} catch (e) {
			alert(`Error running workflow: ${e instanceof Error ? e.message : 'Network error'}`);
		}
	}
</script>

<div class="h-[calc(100vh-3.5rem)]">
	<WorkflowEditor
		initialNodes={workflow.graph.nodes}
		initialEdges={workflow.graph.edges}
		initialSteps={workflow.steps}
		initialInputs={workflow.inputs}
		bind:workflowName
		bind:workflowDescription
		onsave={handleSave}
		onrun={handleRun}
	/>
</div>
