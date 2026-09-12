<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import { ArrowLeft, Loader2, Milestone } from 'lucide-svelte';
	import { API_BASE } from '$lib/config';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import WorkflowCanvas from '$lib/components/workflow/WorkflowCanvas.svelte';
	import WorkflowDrawer from '$lib/components/workflow/WorkflowDrawer.svelte';
	import type { WorkflowData, WorkflowNode } from '$lib/components/workflow/types';

	const projectId = $derived($page.params.project_id ?? '');

	let data = $state<WorkflowData | null>(null);
	let loading = $state(true);
	let notFound = $state(false);
	let error = $state(false);
	let selectedId = $state<string | null>(null);
	let mounted = $state(false);

	onMount(() => {
		mounted = true;
	});

	async function load(id: string) {
		loading = true;
		error = false;
		notFound = false;
		selectedId = null;
		try {
			const res = await fetch(`${API_BASE}/projects/${id}/workflow`);
			if (res.status === 404) {
				notFound = true;
				return;
			}
			if (!res.ok) throw new Error('failed');
			data = await res.json();
		} catch {
			error = true;
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		if (projectId) load(projectId);
	});

	const allNodes = $derived.by<WorkflowNode[]>(() => {
		if (!data) return [];
		return data.threads.flatMap((t) => [t.root, ...t.nodes]);
	});
	const selectedNode = $derived(allNodes.find((n) => n.id === selectedId) ?? null);

	const stats = $derived.by(() => {
		if (!data) return null;
		const sessions = new Set(allNodes.map((n) => n.session_id).filter(Boolean)).size;
		return { threads: data.threads.length, nodes: allNodes.length, sessions };
	});
</script>

<svelte:head>
	<title>Decision workflow</title>
</svelte:head>

<div class="wf-page">
	<!-- Slim top bar -->
	<header class="wf-topbar">
		<div class="flex min-w-0 items-center gap-3">
			<a
				href={`/projects/${projectId}`}
				class="inline-flex shrink-0 items-center gap-1.5 text-xs text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
			>
				<ArrowLeft class="h-3.5 w-3.5" />
				Back to project
			</a>
			<span class="h-4 w-px bg-[var(--border)]"></span>
			<h1 class="truncate text-sm font-semibold text-[var(--text-primary)]">
				Decision workflow
			</h1>
		</div>
		{#if stats}
			<p class="hidden shrink-0 text-xs text-[var(--text-muted)] sm:block">
				{stats.threads} threads · {stats.nodes} decisions · {stats.sessions} sessions
				{#if data?.period}· {data.period}{/if}
			</p>
		{/if}
	</header>

	<div class="wf-body">
		{#if loading || !mounted}
			<div class="flex h-full items-center justify-center text-[var(--text-muted)]">
				<Loader2 class="h-5 w-5 animate-spin" />
			</div>
		{:else if notFound}
			<EmptyState
				icon={Milestone}
				title="No workflow yet"
				description="No curated decisions exist for this project. Workflows are hand-curated for now — automated extraction is a later phase."
			/>
		{:else if error || !data}
			<EmptyState
				icon={Milestone}
				title="Couldn't load the workflow"
				description="The API request for this project's decision workflow failed."
			/>
		{:else}
			{#key projectId}
				<WorkflowCanvas
					threads={data.threads}
					{selectedId}
					onselect={(id) => (selectedId = id)}
					onbackgroundclick={() => (selectedId = null)}
				/>
			{/key}
		{/if}
	</div>
</div>

<WorkflowDrawer
	node={selectedNode}
	projectEncodedName={projectId}
	onclose={() => (selectedId = null)}
	onselectid={(id) => (selectedId = id)}
/>

<style>
	/* Full-bleed board below the app header (which is sticky, h-14 / 3.5rem). */
	.wf-page {
		position: fixed;
		inset: 3.5rem 0 0 0;
		display: flex;
		flex-direction: column;
		background: var(--bg-base);
		z-index: 20;
	}
	.wf-topbar {
		flex: none;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		height: 44px;
		padding: 0 1rem;
		border-bottom: 1px solid var(--border);
		background: var(--bg-subtle);
	}
	.wf-body {
		position: relative;
		flex: 1;
		min-height: 0;
	}
	@media (max-width: 640px) {
		.wf-page {
			inset: 0;
		}
	}
</style>
