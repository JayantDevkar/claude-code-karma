<script lang="ts">
	import { invalidateAll } from '$app/navigation';
	import ExecutionView from '$lib/components/workflows/ExecutionView.svelte';

	let { data } = $props();

	$effect(() => {
		if (data.run.status === 'pending' || data.run.status === 'running') {
			const interval = setInterval(() => invalidateAll(), 3000);
			return () => clearInterval(interval);
		}
	});
</script>

<div class="h-[calc(100vh-3.5rem)]">
	<ExecutionView
		run={data.run}
		graphNodes={data.workflow.graph.nodes}
		graphEdges={data.workflow.graph.edges}
	/>
</div>
