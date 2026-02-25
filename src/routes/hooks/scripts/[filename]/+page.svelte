<script lang="ts">
	import {
		FileCode,
		Copy,
		Check,
		ExternalLink,
		FolderSymlink,
		Hash,
		AlertTriangle
	} from 'lucide-svelte';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import { getHookSourceColorVars } from '$lib/utils';

	let { data } = $props();

	let detail = $derived(data.detail);
	let script = $derived(detail.script);
	let sourceColors = $derived(getHookSourceColorVars(detail.source_type, script.source_name));

	// Language display names
	const languageLabels: Record<string, string> = {
		python: 'Python',
		node: 'Node.js',
		shell: 'Shell',
		bash: 'Shell'
	};

	let languageLabel = $derived(languageLabels[script.language] || script.language);

	function formatBytes(bytes: number): string {
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}

	// Copy button state
	let copied = $state(false);

	async function copyCode() {
		if (!detail.content) return;
		try {
			await navigator.clipboard.writeText(detail.content);
			copied = true;
			setTimeout(() => (copied = false), 2000);
		} catch {
			// Clipboard API not available
		}
	}

	// Format modified date
	let modifiedLabel = $derived(
		detail.modified_at
			? new Date(detail.modified_at).toLocaleDateString('en-US', {
					year: 'numeric',
					month: 'short',
					day: 'numeric',
					hour: '2-digit',
					minute: '2-digit'
				})
			: null
	);
</script>

<svelte:head>
	<title>{data.filename} - Hook Script - Claude Karma</title>
</svelte:head>

<div class="max-w-5xl mx-auto">
	<PageHeader
		title={script.filename}
		icon={FileCode}
		iconColorRaw={sourceColors}
		breadcrumbs={[
			{ label: 'Dashboard', href: '/' },
			{ label: 'Hooks', href: '/hooks' },
			{ label: script.filename }
		]}
		subtitle={script.full_path || undefined}
		metadata={[
			...(script.is_symlink && script.symlink_target
				? [{ icon: FolderSymlink, text: script.symlink_target }]
				: []),
			...(detail.line_count ? [{ icon: Hash, text: `${detail.line_count} lines` }] : []),
			...(detail.size_bytes ? [{ text: formatBytes(detail.size_bytes) }] : []),
			...(modifiedLabel ? [{ text: `Modified ${modifiedLabel}` }] : [])
		]}
	>
		{#snippet badges()}
			<Badge variant="slate">{languageLabel}</Badge>
			<Badge variant="slate">{detail.source_type}</Badge>
			<Badge variant="slate"
				>{script.registrations} registration{script.registrations !== 1 ? 's' : ''}</Badge
			>
		{/snippet}
	</PageHeader>

	<!-- Event Types -->
	{#if script.event_types.length > 0}
		<section class="mb-8">
			<h2
				class="text-sm font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-3"
			>
				Event Types
			</h2>
			<div class="flex flex-wrap gap-2">
				{#each script.event_types as eventType}
					<a
						href="/hooks/{encodeURIComponent(eventType)}"
						class="
							inline-flex items-center gap-1.5
							px-3 py-1.5
							text-xs font-medium
							rounded-lg
							bg-[var(--bg-muted)] text-[var(--text-secondary)]
							hover:bg-[var(--nav-amber-subtle)] hover:text-[var(--nav-amber)]
							border border-transparent hover:border-[var(--nav-amber)]
							transition-colors
						"
					>
						{eventType}
						<ExternalLink size={10} />
					</a>
				{/each}
			</div>
		</section>
	{/if}

	<!-- Source Code -->
	<section>
		<div
			class="
				border border-[#30363d]
				rounded-xl
				overflow-hidden
				bg-[#0d1117]
			"
		>
			<!-- Code Header -->
			<div
				class="
					flex items-center justify-between
					px-4 py-3
					border-b border-[#30363d]
					bg-[#161b22]
				"
			>
				<div class="flex items-center gap-2 text-sm text-[#8b949e]">
					<FileCode size={14} />
					<span class="font-mono text-xs">{script.filename}</span>
				</div>
				{#if detail.content}
					<button
						onclick={copyCode}
						class="
							flex items-center gap-1.5
							px-3 py-1.5
							text-xs font-medium
							rounded-lg
							text-[#8b949e]
							hover:text-[#e6edf3]
							hover:bg-[#30363d]
							transition-colors
						"
					>
						{#if copied}
							<Check size={12} class="text-green-500" />
							<span class="text-green-500">Copied</span>
						{:else}
							<Copy size={12} />
							<span>Copy</span>
						{/if}
					</button>
				{/if}
			</div>

			<!-- Code Content -->
			{#if detail.error === 'file_not_found'}
				<div class="p-8">
					<EmptyState
						icon={AlertTriangle}
						title="Script file not found"
						description="The file at {script.full_path ||
							'unknown path'} could not be found. It may have been moved or deleted."
					/>
				</div>
			{:else if detail.error === 'file_too_large'}
				<div class="p-8">
					<EmptyState
						icon={AlertTriangle}
						title="File too large to display"
						description="This script exceeds the 500KB display limit ({detail.size_bytes
							? formatBytes(detail.size_bytes)
							: 'unknown size'})."
					/>
				</div>
			{:else if detail.error === 'binary_file'}
				<div class="p-8">
					<EmptyState
						icon={AlertTriangle}
						title="Binary file"
						description="This file contains binary content that cannot be displayed as text."
					/>
				</div>
			{:else if data.highlightedHtml}
				<div class="shiki-container overflow-x-auto">
					{@html data.highlightedHtml}
				</div>
			{:else if detail.content}
				<pre
					class="p-4 overflow-x-auto text-sm font-mono text-[#e6edf3] leading-relaxed">{detail.content}</pre>
			{:else}
				<div class="p-8">
					<EmptyState
						icon={FileCode}
						title="No content available"
						description="Unable to load the script content."
					/>
				</div>
			{/if}
		</div>
	</section>
</div>

<style>
	/* Shiki code block styling */
	.shiki-container :global(pre) {
		margin: 0;
		padding: 1rem 1.25rem;
		overflow-x: auto;
		font-family:
			'JetBrains Mono', ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace;
		font-size: 0.8125rem;
		line-height: 1.7;
		tab-size: 4;
	}

	.shiki-container :global(pre code) {
		font-family: inherit;
	}

	.shiki-container :global(.line) {
		display: inline-block;
		width: 100%;
	}

	/* Force dark background for code block in both themes */
	.shiki-container :global(pre.shiki) {
		background-color: #0d1117 !important;
	}
</style>
