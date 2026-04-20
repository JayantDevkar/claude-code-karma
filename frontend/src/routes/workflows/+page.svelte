<script lang="ts">
	import type { Workflow } from '$lib/api-types';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import { GitBranch, Plus, Layers, Zap } from 'lucide-svelte';

	let { data } = $props();
	let workflows: Workflow[] = $derived(data.workflows);
</script>

<div>
	<PageHeader
		title="Workflows"
		icon={GitBranch}
		iconColor="--accent"
		breadcrumbs={[{ label: 'Dashboard', href: '/' }, { label: 'Workflows' }]}
		subtitle="Automated Claude Code pipelines"
	>
		{#snippet headerRight()}
			<div class="flex items-center gap-3">
				<div
					class="flex items-center gap-1.5 px-2 py-1 rounded-md bg-[var(--bg-subtle)] border border-[var(--border-subtle)] text-xs"
				>
					<span class="text-[var(--text-muted)] font-medium">Total</span>
					<span class="text-[var(--text-primary)] font-semibold">{workflows.length}</span>
				</div>
				<a
					href="/workflows/new"
					class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-[var(--accent)] text-white rounded-[6px] hover:opacity-90 transition-opacity"
				>
					<Plus size={14} strokeWidth={2} />
					New Workflow
				</a>
			</div>
		{/snippet}
	</PageHeader>

	{#if workflows.length === 0}
		<div class="text-center py-16">
			<div
				class="inline-flex items-center justify-center w-16 h-16 bg-[var(--bg-muted)] rounded-lg mb-4"
			>
				<Layers size={28} class="text-[var(--text-faint)]" />
			</div>
			<h3 class="text-base font-semibold text-[var(--text-primary)] mb-2">No workflows yet</h3>
			<p class="text-sm font-medium text-[var(--text-muted)] mb-4">
				Create your first automated Claude Code pipeline
			</p>
			<a
				href="/workflows/new"
				class="inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium bg-[var(--accent)] text-white rounded-lg hover:opacity-90 transition-opacity"
			>
				<Plus size={14} />
				Create Workflow
			</a>
		</div>
	{:else}
		<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
			{#each workflows as wf (wf.id)}
				<a
					href="/workflows/{wf.id}"
					class="block p-4 rounded-xl border border-[var(--border)] bg-[var(--bg-subtle)] hover:border-[var(--accent)] transition-colors group"
				>
					<div class="flex items-start justify-between gap-2 mb-2">
						<h3
							class="font-semibold text-sm text-[var(--text-primary)] group-hover:text-[var(--accent)] transition-colors truncate"
						>
							{wf.name}
						</h3>
						<Zap size={14} class="text-[var(--text-faint)] shrink-0 mt-0.5" />
					</div>
					{#if wf.description}
						<p class="text-xs text-[var(--text-secondary)] mb-3 line-clamp-2">
							{wf.description}
						</p>
					{/if}
					<div class="flex items-center gap-3 text-xs text-[var(--text-muted)]">
						<span class="inline-flex items-center gap-1">
							<Layers size={11} />
							{wf.steps.length} step{wf.steps.length !== 1 ? 's' : ''}
						</span>
						{#if wf.inputs.length > 0}
							<span>{wf.inputs.length} input{wf.inputs.length !== 1 ? 's' : ''}</span>
						{/if}
					</div>
				</a>
			{/each}
		</div>
	{/if}
</div>
