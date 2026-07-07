<script lang="ts">
	import { Brain, FolderOpen, Search, FileText, BookOpen } from 'lucide-svelte';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';

	interface MemoryProjectRow {
		encoded: string;
		label: string;
		path: string;
		note_count: number;
		has_index: boolean;
	}

	let { data } = $props();
	const allProjects = $derived((data.projects ?? []) as MemoryProjectRow[]);

	let query = $state('');

	const filtered = $derived(
		allProjects.filter((p) => {
			const q = query.trim().toLowerCase();
			if (!q) return true;
			return p.label.toLowerCase().includes(q) || p.path.toLowerCase().includes(q);
		})
	);

	function memoryHref(p: MemoryProjectRow): string {
		return `/projects/${p.encoded}?tab=memory`;
	}
</script>

<svelte:head>
	<title>Memory · Claude Code Karma</title>
</svelte:head>

<div class="memory-page">
	<PageHeader
		title="Memory"
		iconName="memory"
		iconColor="--nav-blue"
		subtitle="Browse each project's persistent memory"
	/>

	{#if allProjects.length > 0}
		<div class="stats">
			<div class="stat">
				<span class="stat-value">{data.totalProjects}</span>
				<span class="stat-label">projects with memory</span>
			</div>
			<div class="stat-divider"></div>
			<div class="stat">
				<span class="stat-value">{data.totalNotes}</span>
				<span class="stat-label">total notes</span>
			</div>
		</div>
	{/if}

	{#if allProjects.length === 0}
		<div class="state">
			No projects have memory yet (<code>~/.claude/projects/&lt;project&gt;/memory/</code>).
		</div>
	{:else}
		<div class="search">
			<Search size={15} strokeWidth={2} />
			<input type="text" placeholder="Search projects…" bind:value={query} />
		</div>

		{#if filtered.length === 0}
			<div class="state">No projects match "{query}".</div>
		{:else}
			<div class="grid">
				{#each filtered as project (project.encoded)}
					<a class="card" href={memoryHref(project)}>
						<!-- Header -->
						<div class="card-header">
							<div class="card-icon">
								<FolderOpen size={20} strokeWidth={2} />
							</div>
							<div class="card-title-wrap">
								<span class="card-name">{project.label}</span>
								<span class="card-path">{project.path}</span>
							</div>
						</div>

						<!-- Footer -->
						<div class="card-footer">
							<span class="footer-stat">
								<FileText size={13} strokeWidth={2} />
								{project.note_count} note{project.note_count === 1 ? '' : 's'}
							</span>
							{#if project.has_index}
								<span class="badge-index">
									<BookOpen size={11} /> index
								</span>
							{/if}
						</div>
					</a>
				{/each}
			</div>
		{/if}
	{/if}
</div>

<style>
	.memory-page {
		max-width: 1100px;
		margin: 0 auto;
		padding: 0 16px;
	}

	/* Stats */
	.stats {
		display: flex;
		align-items: center;
		gap: 20px;
		padding: 14px 18px;
		background: var(--bg-subtle);
		border: 1px solid var(--border);
		border-radius: 10px;
		margin-bottom: 16px;
	}

	.stat {
		display: flex;
		align-items: baseline;
		gap: 6px;
	}

	.stat-value {
		font-size: 18px;
		font-weight: 700;
		color: var(--text-primary);
		font-variant-numeric: tabular-nums;
	}

	.stat-label {
		font-size: 12px;
		color: var(--text-muted);
	}

	.stat-divider {
		width: 1px;
		height: 20px;
		background: var(--border);
	}

	/* Search */
	.state {
		padding: 32px 16px;
		text-align: center;
		color: var(--text-muted);
		font-size: 14px;
	}

	.state code {
		font-family: var(--font-mono);
		font-size: 12px;
		background: var(--bg-muted);
		padding: 1px 5px;
		border-radius: 4px;
	}

	.search {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 9px 12px;
		margin-bottom: 16px;
		background: var(--bg-subtle);
		border: 1px solid var(--border);
		border-radius: 8px;
		color: var(--text-muted);
	}

	.search input {
		flex: 1;
		border: none;
		background: transparent;
		outline: none;
		color: var(--text-primary);
		font-size: 14px;
		font-family: var(--font-sans);
	}

	/* Grid */
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
		gap: 12px;
	}

	/* Card — matches ProjectCard default variant */
	.card {
		display: flex;
		flex-direction: column;
		gap: 0;
		background: var(--bg-subtle);
		border: 1px solid var(--border);
		border-left: 3px solid var(--nav-blue);
		border-radius: 10px;
		padding: 16px 16px 0;
		text-decoration: none;
		transition:
			box-shadow 120ms,
			border-color 120ms;
	}

	.card:hover {
		box-shadow: 0 4px 16px -6px rgba(0, 0, 0, 0.12);
	}

	.card:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.card-header {
		display: flex;
		align-items: flex-start;
		gap: 12px;
		margin-bottom: 12px;
	}

	.card-icon {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 40px;
		height: 40px;
		border-radius: 8px;
		background: var(--nav-blue-subtle);
		color: var(--nav-blue);
		flex-shrink: 0;
	}

	.card-title-wrap {
		display: flex;
		flex-direction: column;
		min-width: 0;
		flex: 1;
	}

	.card-name {
		font-size: 13.5px;
		font-weight: 600;
		font-family: var(--font-mono);
		color: var(--accent);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		line-height: 1.3;
		margin-bottom: 2px;
	}

	.card-path {
		font-size: 11px;
		font-family: var(--font-mono);
		color: var(--text-muted);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	/* Footer */
	.card-footer {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
		padding: 10px 0;
		border-top: 1px solid var(--border);
		margin-top: auto;
	}

	.footer-stat {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		font-size: 12px;
		color: var(--text-muted);
	}

	.badge-index {
		display: inline-flex;
		align-items: center;
		gap: 3px;
		font-size: 10.5px;
		font-weight: 500;
		color: var(--accent);
		background: var(--accent-muted);
		padding: 2px 7px;
		border-radius: 99px;
	}
</style>
