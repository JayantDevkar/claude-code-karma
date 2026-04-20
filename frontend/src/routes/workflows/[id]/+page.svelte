<script lang="ts">
	import { goto } from '$app/navigation';
	import { API_BASE } from '$lib/config';
	import { addToast } from '$lib/stores/toast.svelte';
	import WorkflowEditor from '$lib/components/workflows/WorkflowEditor.svelte';
	import RunWorkflowModal from '$lib/components/workflows/RunWorkflowModal.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import type { Workflow, WorkflowStep, WorkflowInput } from '$lib/api-types';
	import type { Node, Edge } from '@xyflow/svelte';

	let { data } = $props();
	let workflow: Workflow = $derived(data.workflow);

	let workflowName = $state(workflow.name);
	let workflowDescription = $state(workflow.description || '');

	// Run modal (#3)
	let showRunModal = $state(false);

	// Delete confirmation (#5)
	let showDeleteModal = $state(false);

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
				addToast(`Failed to save: ${err}`, 'error');
				return;
			}
			addToast('Workflow saved', 'success');
		} catch (e) {
			addToast(`Network error: ${e instanceof Error ? e.message : 'Unknown'}`, 'error');
		}
	}

	function handleRunClick() {
		// If workflow has inputs, show modal; otherwise run directly
		if (workflow.inputs.length > 0) {
			showRunModal = true;
		} else {
			executeRun({});
		}
	}

	async function executeRun(inputValues: Record<string, unknown>) {
		try {
			const resp = await fetch(`${API_BASE}/workflows/${workflow.id}/run`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ input_values: inputValues })
			});
			if (!resp.ok) {
				const err = await resp.text();
				addToast(`Failed to run: ${err}`, 'error');
				return;
			}
			const run = await resp.json();
			addToast('Workflow started', 'success');
			goto(`/workflows/${workflow.id}/runs/${run.id}`);
		} catch (e) {
			addToast(`Network error: ${e instanceof Error ? e.message : 'Unknown'}`, 'error');
		}
	}

	async function handleDelete() {
		try {
			const resp = await fetch(`${API_BASE}/workflows/${workflow.id}`, {
				method: 'DELETE'
			});
			if (!resp.ok) {
				const err = await resp.text();
				addToast(`Failed to delete: ${err}`, 'error');
				return;
			}
			addToast('Workflow deleted', 'success');
			goto('/workflows');
		} catch (e) {
			addToast(`Network error: ${e instanceof Error ? e.message : 'Unknown'}`, 'error');
		}
	}
</script>

<div class="h-[calc(100vh-3.5rem)]">
	<WorkflowEditor
		initialNodes={workflow.graph.nodes}
		initialEdges={workflow.graph.edges}
		initialSteps={workflow.steps}
		initialInputs={workflow.inputs}
		workflowId={workflow.id}
		bind:workflowName
		bind:workflowDescription
		onsave={handleSave}
		onrun={handleRunClick}
		ondelete={() => (showDeleteModal = true)}
	/>
</div>

<!-- Run modal with input form (#3) -->
<RunWorkflowModal bind:open={showRunModal} inputs={workflow.inputs} onrun={executeRun} />

<!-- Delete confirmation (#5) -->
<Modal
	open={showDeleteModal}
	onOpenChange={(v) => (showDeleteModal = v)}
	title="Delete Workflow"
	description="This action cannot be undone. All runs and history will be permanently deleted."
>
	{#snippet children()}
		<p class="text-sm text-[var(--text-secondary)]">
			Are you sure you want to delete <strong>{workflow.name}</strong>?
		</p>
	{/snippet}
	{#snippet footer()}
		<div class="flex justify-end gap-2">
			<button
				class="px-3 py-1.5 text-sm rounded-md border border-[var(--border)] bg-[var(--bg-base)] text-[var(--text-secondary)] hover:border-[var(--border-hover)]"
				onclick={() => (showDeleteModal = false)}
			>
				Cancel
			</button>
			<button
				class="px-3 py-1.5 text-sm rounded-md bg-[var(--error)] text-white hover:opacity-90"
				onclick={handleDelete}
			>
				Delete
			</button>
		</div>
	{/snippet}
</Modal>
