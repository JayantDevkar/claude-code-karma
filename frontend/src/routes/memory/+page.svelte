<script lang="ts">
	import {
		Brain,
		Search,
		FolderGit2,
		BookOpen,
		ArrowRight,
		LayoutGrid,
		FolderTree
	} from 'lucide-svelte';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import StatsGrid from '$lib/components/StatsGrid.svelte';
	import MemoryTreeNode from '$lib/components/memory/MemoryTreeNode.svelte';
	import { buildMemoryTree, type MemoryProjectRow } from '$lib/components/memory/memoryTree';

	let { data } = $props();

	let query = $state('');
	let view = $state<'cards' | 'tree'>('cards');

	const filtered = $derived.by(() => {
		const q = query.trim().toLowerCase();
		const rows = data.projects as MemoryProjectRow[];
		if (!q) return rows;
		return rows.filter(
			(p) => p.label.toLowerCase().includes(q) || p.path.toLowerCase().includes(q)
		);
	});

	const tree = $derived(buildMemoryTree(filtered));
	const searching = $derived(query.trim().length > 0);
</script>

<svelte:head>
	<title>Memory · Claude Karma</title>
</svelte:head>

<div class="page-wrap">
	<PageHeader
		title="Memory"
		subtitle="La mémoire Claude Code de tous tes projets. Vue d'ensemble en cartes, ou arbre par dossier — déplie un projet pour lire son contenu directement."
		icon={Brain}
		iconColor="--nav-purple"
		breadcrumbs={[{ label: 'Home', href: '/' }, { label: 'Memory' }]}
	/>

	<div class="stats-wrap">
		<StatsGrid
			columns={2}
			stats={[
				{
					title: 'Projets avec mémoire',
					value: data.totalProjects,
					icon: FolderGit2,
					color: 'blue'
				},
				{ title: 'Notes mémoire', value: data.totalNotes, icon: Brain, color: 'purple' }
			]}
		/>
	</div>

	<div class="toolbar">
		<div class="search-wrap">
			<span class="search-ico"><Search size={14} /></span>
			<input
				class="search-input"
				placeholder="Filtrer par projet ou chemin…"
				bind:value={query}
			/>
		</div>

		<div class="seg" role="tablist" aria-label="Mode d'affichage">
			<button
				class="seg-btn"
				class:on={view === 'cards'}
				onclick={() => (view = 'cards')}
				role="tab"
				aria-selected={view === 'cards'}
			>
				<LayoutGrid size={14} /> Cartes
			</button>
			<button
				class="seg-btn"
				class:on={view === 'tree'}
				onclick={() => (view = 'tree')}
				role="tab"
				aria-selected={view === 'tree'}
			>
				<FolderTree size={14} /> Arbre
			</button>
		</div>
	</div>

	{#if filtered.length === 0}
		<div class="empty">
			{#if data.totalProjects === 0}
				Aucun projet n'a encore de mémoire (<code
					>~/.claude/projects/&lt;projet&gt;/memory/</code
				>).
			{:else}
				Aucun projet ne correspond au filtre.
			{/if}
		</div>
	{:else if view === 'cards'}
		<div class="grid">
			{#each filtered as p (p.encoded)}
				<a class="card" href="/projects/{p.encoded}?tab=memory">
					<div class="card-top">
						<span class="card-ico"><FolderGit2 size={16} /></span>
						<span class="card-label">{p.label}</span>
					</div>
					<div class="card-meta">
						<span class="meta-item">
							<Brain size={13} />
							{p.note_count} note{p.note_count === 1 ? '' : 's'}
						</span>
						{#if p.has_index}
							<span class="meta-item index"><BookOpen size={13} /> index</span>
						{/if}
					</div>
					<div class="card-enc">{p.path}</div>
					<span class="card-go">Voir la mémoire <ArrowRight size={13} /></span>
				</a>
			{/each}
		</div>
	{:else}
		<div class="tree">
			{#each tree as node (node.project?.encoded ?? node.name)}
				<MemoryTreeNode {node} forceOpen={searching} />
			{/each}
		</div>
	{/if}
</div>

<style>
	.page-wrap {
		max-width: 1120px;
		margin: 0 auto;
		padding: 32px 32px 80px;
	}

	.stats-wrap {
		border-radius: 16px;
		padding: 24px;
		border: 1px solid var(--border);
		background: linear-gradient(
			135deg,
			rgba(var(--accent-rgb), 0.02) 0%,
			rgba(var(--accent-rgb), 0.06) 100%
		);
		margin-bottom: 22px;
	}

	.toolbar {
		display: flex;
		align-items: center;
		gap: 10px;
		margin-bottom: 16px;
	}

	.search-wrap {
		position: relative;
		display: flex;
		align-items: center;
		flex: 1;
	}

	.search-ico {
		position: absolute;
		left: 11px;
		color: var(--text-faint);
		pointer-events: none;
		display: flex;
	}

	.search-input {
		width: 100%;
		height: 36px;
		border: 1px solid var(--border-hover);
		border-radius: 8px;
		background: var(--bg-base);
		padding: 0 12px 0 34px;
		font-size: 13px;
		color: var(--text-primary);
		outline: none;
	}

	.search-input:focus {
		border-color: var(--accent);
		box-shadow: 0 0 0 3px var(--accent-muted);
	}

	.seg {
		display: inline-flex;
		border: 1px solid var(--border-hover);
		border-radius: 8px;
		overflow: hidden;
		flex-shrink: 0;
	}

	.seg-btn {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		height: 36px;
		padding: 0 12px;
		background: var(--bg-base);
		border: none;
		font-size: 12.5px;
		color: var(--text-muted);
		cursor: pointer;
	}

	.seg-btn:hover {
		background: var(--bg-subtle);
	}

	.seg-btn.on {
		background: var(--accent-muted);
		color: var(--accent);
		font-weight: 600;
	}

	.seg-btn + .seg-btn {
		border-left: 1px solid var(--border-hover);
	}

	/* ── Cards ─────────────────────────────────────────────────────────────── */
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
		gap: 12px;
	}

	.card {
		display: flex;
		flex-direction: column;
		gap: 10px;
		border: 1px solid var(--border);
		border-radius: 12px;
		background: var(--bg-base);
		padding: 16px;
		text-decoration: none;
		transition:
			border-color 0.15s,
			box-shadow 0.15s;
	}

	.card:hover {
		border-color: var(--border-hover);
		box-shadow: 0 6px 20px -10px var(--border-subtle);
	}

	.card-top {
		display: flex;
		align-items: center;
		gap: 9px;
		min-width: 0;
	}

	.card-ico {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 30px;
		height: 30px;
		border-radius: 8px;
		background: var(--accent-muted);
		color: var(--accent);
		flex-shrink: 0;
	}

	.card-label {
		font-size: 14px;
		font-weight: 600;
		color: var(--text-primary);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.card-meta {
		display: flex;
		align-items: center;
		gap: 12px;
	}

	.meta-item {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		font-size: 12.5px;
		color: var(--text-muted);
	}

	.meta-item.index {
		color: var(--accent);
	}

	.card-enc {
		font-family: var(--font-mono);
		font-size: 11px;
		color: var(--text-faint);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.card-go {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		font-size: 12.5px;
		font-weight: 500;
		color: var(--accent);
		margin-top: 2px;
	}

	/* ── Tree ──────────────────────────────────────────────────────────────── */
	.tree {
		border: 1px solid var(--border);
		border-radius: 12px;
		background: var(--bg-base);
		padding: 8px;
	}

	.empty {
		padding: 50px 20px;
		text-align: center;
		color: var(--text-muted);
		border: 1px dashed var(--border);
		border-radius: 12px;
		background: var(--bg-subtle);
		font-size: 13px;
	}

	.empty code {
		font-family: var(--font-mono);
		font-size: 12px;
		background: var(--bg-muted);
		padding: 0 5px;
		border-radius: 4px;
	}
</style>
