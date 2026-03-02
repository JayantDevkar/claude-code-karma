<script lang="ts">
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import { Activity } from 'lucide-svelte';
	import { statusColors } from '$lib/components/workflows/constants';

	let { data } = $props();
</script>

<div>
	<PageHeader
		title="Runs: {data.workflow.name}"
		icon={Activity}
		iconColor="--accent"
		breadcrumbs={[
			{ label: 'Dashboard', href: '/' },
			{ label: 'Workflows', href: '/workflows' },
			{ label: data.workflow.name, href: `/workflows/${data.workflow.id}` },
			{ label: 'Runs' }
		]}
		subtitle="Execution history"
	/>

	{#if data.runs.length === 0}
		<div class="text-center py-16">
			<div
				class="inline-flex items-center justify-center w-16 h-16 bg-[var(--bg-muted)] rounded-lg mb-4"
			>
				<Activity size={28} class="text-[var(--text-faint)]" />
			</div>
			<h3 class="text-base font-semibold text-[var(--text-primary)] mb-2">No runs yet</h3>
			<p class="text-sm font-medium text-[var(--text-muted)]">
				Run this workflow to see execution history
			</p>
		</div>
	{:else}
		<div class="space-y-2">
			{#each data.runs as run (run.id)}
				<a
					href="/workflows/{data.workflow.id}/runs/{run.id}"
					class="block p-3 rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)] hover:border-[var(--accent)] transition-colors"
				>
					<div class="flex items-center gap-3">
						<span class="font-mono text-sm text-[var(--text-primary)]">{run.id.slice(0, 8)}</span>
						<span
							class="text-[10px] px-2 py-0.5 rounded-full text-white font-medium"
							style="background-color: {statusColors[run.status] || '#6b7280'}"
						>
							{run.status}
						</span>
						{#if run.started_at}
							<span class="text-xs text-[var(--text-muted)]"
								>{new Date(run.started_at).toLocaleString()}</span
							>
						{/if}
						{#if run.error}
							<span class="text-xs text-red-400 truncate flex-1">{run.error}</span>
						{/if}
					</div>
				</a>
			{/each}
		</div>
	{/if}
</div>
