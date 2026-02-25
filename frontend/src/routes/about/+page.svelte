<script lang="ts">
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import { BookOpen, FileText, Loader2 } from 'lucide-svelte';
	import { renderMarkdownEffect } from '$lib/utils';
	import { API_BASE } from '$lib/config';

	let { data } = $props();

	// State
	let selectedDoc = $state<string>('');
	let docContent = $state('');
	let renderedHtml = $state('');
	let isLoading = $state(false);
	let contentError = $state<string | null>(null);

	// Initialize selectedDoc when data loads
	$effect(() => {
		if (!selectedDoc && data.docs?.[0]?.path) {
			selectedDoc = data.docs[0].path;
		}
	});

	// Fetch doc content when selection changes
	$effect(() => {
		if (!selectedDoc) return;

		isLoading = true;
		contentError = null;

		fetch(`${API_BASE}/docs/about/content?path=${encodeURIComponent(selectedDoc)}`)
			.then((res) => {
				if (!res.ok) throw new Error('Failed to load document');
				return res.json();
			})
			.then((data) => {
				docContent = data.content;
			})
			.catch((err) => {
				contentError = err.message;
				docContent = '';
			})
			.finally(() => {
				isLoading = false;
			});
	});

	// Render markdown when content changes
	$effect(() => {
		if (docContent) {
			renderMarkdownEffect(docContent, {}, (html) => {
				renderedHtml = html;
			});
		} else {
			renderedHtml = '';
		}
	});

	let selectedTitle = $derived(
		data.docs?.find((d: any) => d.path === selectedDoc)?.title ?? 'Overview'
	);
</script>

<div class="space-y-6">
	<PageHeader
		title="About"
		icon={BookOpen}
		iconColor="--nav-red"
		breadcrumbs={[{ label: 'Dashboard', href: '/' }, { label: 'About' }]}
		subtitle="Documentation & guides for Claude Karma"
	/>

	{#if data.error}
		<div
			class="p-4 rounded-lg bg-[var(--bg-error,rgba(239,68,68,0.1))] border border-[var(--border-error,rgba(239,68,68,0.3))] text-[var(--text-error,#ef4444)]"
		>
			<p class="text-sm">Failed to load documentation: {data.error}</p>
			<p class="text-xs mt-1 opacity-70">Make sure the API is running on port 8000.</p>
		</div>
	{:else}
		<div class="flex gap-6">
			<!-- Sidebar: Doc Navigation -->
			<nav class="w-56 shrink-0">
				<div class="sticky top-4 space-y-1">
					{#each data.docs as doc}
						<button
							class="w-full text-left px-3 py-2 rounded-md text-sm transition-colors {selectedDoc ===
							doc.path
								? 'bg-[var(--bg-muted)] text-[var(--text-primary)] font-medium'
								: 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)]'}"
							onclick={() => (selectedDoc = doc.path)}
						>
							<div class="flex items-center gap-2">
								<FileText size={14} class="shrink-0 opacity-60" />
								<span>{doc.title}</span>
							</div>
						</button>
					{/each}
				</div>
			</nav>

			<!-- Content Area -->
			<div class="flex-1 min-w-0">
				{#if isLoading}
					<div class="flex items-center justify-center py-16">
						<Loader2 size={24} class="animate-spin text-[var(--text-muted)]" />
					</div>
				{:else if contentError}
					<div
						class="p-4 rounded-lg bg-[var(--bg-subtle)] border border-[var(--border)] text-[var(--text-secondary)]"
					>
						<p class="text-sm">Failed to load document: {contentError}</p>
					</div>
				{:else if renderedHtml}
					<div class="markdown-content">
						{@html renderedHtml}
					</div>
				{:else}
					<div class="text-center py-16 text-[var(--text-muted)]">
						<p>Select a document from the sidebar.</p>
					</div>
				{/if}
			</div>
		</div>
	{/if}
</div>

<style>
	.markdown-content :global(h1) {
		font-size: 1.75rem;
		font-weight: 700;
		color: var(--text-primary);
		margin-bottom: 1rem;
		padding-bottom: 0.75rem;
		border-bottom: 1px solid var(--border);
	}

	.markdown-content :global(h2) {
		font-size: 1.35rem;
		font-weight: 600;
		color: var(--text-primary);
		margin-top: 2rem;
		margin-bottom: 0.75rem;
	}

	.markdown-content :global(h3) {
		font-size: 1.1rem;
		font-weight: 600;
		color: var(--text-primary);
		margin-top: 1.5rem;
		margin-bottom: 0.5rem;
	}

	.markdown-content :global(p) {
		color: var(--text-secondary);
		line-height: 1.7;
		margin-bottom: 1rem;
	}

	.markdown-content :global(ul),
	.markdown-content :global(ol) {
		color: var(--text-secondary);
		padding-left: 1.5rem;
		margin-bottom: 1rem;
	}

	.markdown-content :global(li) {
		margin-bottom: 0.35rem;
		line-height: 1.6;
	}

	.markdown-content :global(code) {
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.85em;
		padding: 0.15em 0.4em;
		background: var(--bg-muted);
		border-radius: var(--radius-sm);
		color: var(--accent);
	}

	.markdown-content :global(pre) {
		background: var(--bg-muted);
		border: 1px solid var(--border);
		border-radius: var(--radius-md);
		padding: 1rem;
		overflow-x: auto;
		margin-bottom: 1rem;
	}

	.markdown-content :global(pre code) {
		background: none;
		padding: 0;
		font-size: 0.85rem;
		color: var(--text-primary);
	}

	.markdown-content :global(table) {
		width: 100%;
		border-collapse: collapse;
		margin-bottom: 1rem;
		font-size: 0.875rem;
	}

	.markdown-content :global(th) {
		text-align: left;
		padding: 0.5rem 0.75rem;
		border-bottom: 2px solid var(--border);
		color: var(--text-primary);
		font-weight: 600;
	}

	.markdown-content :global(td) {
		padding: 0.5rem 0.75rem;
		border-bottom: 1px solid var(--border);
		color: var(--text-secondary);
	}

	.markdown-content :global(tr:hover td) {
		background: var(--bg-subtle);
	}

	.markdown-content :global(a) {
		color: var(--accent);
		text-decoration: none;
	}

	.markdown-content :global(a:hover) {
		text-decoration: underline;
	}

	.markdown-content :global(blockquote) {
		border-left: 3px solid var(--accent);
		padding-left: 1rem;
		margin-left: 0;
		margin-bottom: 1rem;
		color: var(--text-muted);
		font-style: italic;
	}

	.markdown-content :global(hr) {
		border: none;
		border-top: 1px solid var(--border);
		margin: 2rem 0;
	}

	.markdown-content :global(strong) {
		color: var(--text-primary);
		font-weight: 600;
	}
</style>
