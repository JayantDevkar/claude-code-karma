<script lang="ts">
	import { goto } from '$app/navigation';
	import { API_BASE } from '$lib/config';
	import WorkflowEditor from '$lib/components/workflows/WorkflowEditor.svelte';
	import type { WorkflowStep, WorkflowInput } from '$lib/api-types';
	import type { Node, Edge } from '@xyflow/svelte';

	let workflowName = $state('');
	let workflowDescription = $state('');

	async function handleSave(data: {
		nodes: Node[];
		edges: Edge[];
		steps: WorkflowStep[];
		inputs: WorkflowInput[];
	}) {
		try {
			const resp = await fetch(`${API_BASE}/workflows`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					name: workflowName || 'Untitled Workflow',
					description: workflowDescription || null,
					graph: { nodes: data.nodes, edges: data.edges },
					steps: data.steps,
					inputs: data.inputs
				})
			});
			if (!resp.ok) {
				const err = await resp.text();
				alert(`Failed to save workflow: ${err}`);
				return;
			}
			const wf = await resp.json();
			goto(`/workflows/${wf.id}`);
		} catch (e) {
			alert(`Error saving workflow: ${e instanceof Error ? e.message : 'Network error'}`);
		}
	}
</script>

<div class="h-[calc(100vh-3.5rem)]">
	<WorkflowEditor
		bind:workflowName
		bind:workflowDescription
		onsave={handleSave}
		onrun={() => {}}
	/>
</div>
