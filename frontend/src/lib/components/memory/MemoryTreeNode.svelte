<!--
  MemoryTreeNode — recursive node for the global memory tree. Folder nodes
  collapse/expand; a project leaf expands to the upstream MemoryViewer
  rendered inline (so the content is reused, not re-implemented). Part of the
  ADDITIVE memory explorer feature.
-->
<script lang="ts">
	import { ChevronRight, Folder, BookOpen, ExternalLink } from 'lucide-svelte';
	import MemoryViewer from '$lib/components/memory/MemoryViewer.svelte';
	import Self from '$lib/components/memory/MemoryTreeNode.svelte';
	import type { MemoryTreeNode } from '$lib/components/memory/memoryTree';

	let {
		node,
		depth = 0,
		forceOpen = false
	}: { node: MemoryTreeNode; depth?: number; forceOpen?: boolean } = $props();

	const isLeaf = $derived(node.project !== null && node.children.length === 0);
	let open = $state(false);

	const expanded = $derived(forceOpen || open);
	const indent = $derived(`padding-left: ${depth * 16 + 12}px;`);
</script>

<div class="node">
	<button class="row" style={indent} onclick={() => (open = !open)} aria-expanded={expanded}>
		<span class="caret" class:open={expanded} aria-hidden="true"
			><ChevronRight size={13} /></span
		>
		<Folder size={14} class="row-ico" />
		<span class="row-name" class:leaf={isLeaf}
			>{node.project ? node.project.label : node.name}</span
		>
		{#if node.project?.has_index}
			<span class="badge-index" title="MEMORY.md index"><BookOpen size={11} /></span>
		{/if}
		<span class="row-count">{node.noteTotal} note{node.noteTotal === 1 ? '' : 's'}</span>
	</button>

	{#if expanded}
		{#if node.project}
			<div class="viewer" style={`margin-left: ${depth * 16 + 26}px;`}>
				<a class="open-tab" href="/projects/{node.project.encoded}?tab=memory">
					Ouvrir l'onglet projet <ExternalLink size={11} />
				</a>
				<MemoryViewer projectEncodedName={node.project.encoded} />
			</div>
		{/if}
		{#each node.children as child (child.project?.encoded ?? child.name)}
			<Self node={child} depth={depth + 1} {forceOpen} />
		{/each}
	{/if}
</div>

<style>
	.node {
		display: flex;
		flex-direction: column;
	}

	.row {
		display: flex;
		align-items: center;
		gap: 8px;
		width: 100%;
		padding: 8px 12px;
		background: none;
		border: none;
		border-radius: 8px;
		cursor: pointer;
		text-align: left;
		min-width: 0;
	}

	.row:hover {
		background: var(--bg-subtle);
	}

	.caret {
		color: var(--text-faint);
		display: flex;
		align-items: center;
		transition: transform 0.15s;
		flex-shrink: 0;
	}

	.caret.open {
		transform: rotate(90deg);
	}

	:global(.row-ico) {
		color: var(--text-faint);
		flex-shrink: 0;
	}

	.row-name {
		font-size: 13px;
		color: var(--text-muted);
		font-family: var(--font-mono);
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.row-name.leaf {
		color: var(--text-primary);
		font-weight: 600;
		font-family: inherit;
	}

	.badge-index {
		display: inline-flex;
		align-items: center;
		color: var(--accent);
		flex-shrink: 0;
	}

	.row-count {
		font-family: var(--font-mono);
		font-size: 11px;
		color: var(--text-faint);
		background: var(--bg-muted);
		padding: 1px 8px;
		border-radius: 99px;
		flex-shrink: 0;
		margin-left: auto;
	}

	.viewer {
		margin-right: 12px;
		margin-bottom: 8px;
		padding-top: 4px;
	}

	.open-tab {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		font-size: 11.5px;
		color: var(--accent);
		margin-bottom: 8px;
		text-decoration: none;
	}

	.open-tab:hover {
		text-decoration: underline;
	}
</style>
