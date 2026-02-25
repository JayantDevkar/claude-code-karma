<script lang="ts">
	import {
		GitBranch,
		ArrowRight,
		Zap,
		MessageSquare,
		ExternalLink,
		ChevronRight,
		Clock
	} from 'lucide-svelte';
	import type { SessionChain, SessionChainNode } from '$lib/api-types';

	interface Props {
		chain: SessionChain;
		projectEncoded: string;
		class?: string;
	}

	let { chain, projectEncoded, class: className = '' }: Props = $props();

	// Group nodes by depth for visual display
	let nodesByDepth = $derived(() => {
		const groups: Map<number, SessionChainNode[]> = new Map();
		for (const node of chain.nodes) {
			const depth = node.chain_depth;
			if (!groups.has(depth)) {
				groups.set(depth, []);
			}
			groups.get(depth)!.push(node);
		}
		return groups;
	});

	// Count how many sessions share each slug (for disambiguation)
	let slugCounts = $derived(() => {
		const counts: Map<string, number> = new Map();
		for (const node of chain.nodes) {
			if (node.slug) {
				counts.set(node.slug, (counts.get(node.slug) || 0) + 1);
			}
		}
		return counts;
	});

	// Check if a slug is ambiguous (shared by multiple sessions in chain)
	function isSlugAmbiguous(slug: string | undefined): boolean {
		if (!slug) return false;
		return (slugCounts().get(slug) || 0) > 1;
	}

	// Format relative time
	function formatRelativeTime(dateStr: string | undefined): string {
		if (!dateStr) return '';
		const date = new Date(dateStr);
		const now = new Date();
		const diffMs = now.getTime() - date.getTime();
		const diffMins = Math.floor(diffMs / 60000);
		const diffHours = Math.floor(diffMins / 60);
		const diffDays = Math.floor(diffHours / 24);

		if (diffMins < 60) return `${diffMins}m ago`;
		if (diffHours < 24) return `${diffHours}h ago`;
		if (diffDays < 7) return `${diffDays}d ago`;
		return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
	}

	// Format duration between start and end time
	function formatDuration(startStr: string | undefined, endStr: string | undefined): string {
		if (!startStr || !endStr) return '';
		const start = new Date(startStr);
		const end = new Date(endStr);
		const diffMs = end.getTime() - start.getTime();
		const diffMins = Math.floor(diffMs / 60000);
		const diffHours = Math.floor(diffMins / 60);

		if (diffMins < 60) return `${diffMins}m`;
		if (diffHours < 24) return `${diffHours}h ${diffMins % 60}m`;
		return `${Math.floor(diffHours / 24)}d ${diffHours % 24}h`;
	}

	// Get session URL - use UUID when slug is ambiguous (shared by multiple sessions)
	function getSessionUrl(node: SessionChainNode): string {
		// If slug is shared by multiple sessions in the chain, use UUID for disambiguation
		if (isSlugAmbiguous(node.slug)) {
			return `/projects/${projectEncoded}/${node.uuid.slice(0, 8)}`;
		}
		// Otherwise use slug (human-readable) or UUID prefix as fallback
		const identifier = node.slug || node.uuid.slice(0, 8);
		return `/projects/${projectEncoded}/${identifier}`;
	}

	// Get display identifier for a node (shows UUID prefix when slug is ambiguous)
	function getDisplayIdentifier(node: SessionChainNode): string {
		if (isSlugAmbiguous(node.slug)) {
			// Show both slug and UUID prefix for clarity
			return `${node.slug} (${node.uuid.slice(0, 8)})`;
		}
		return node.slug || node.uuid.slice(0, 8);
	}

	// Clean prompt text by removing command tags
	function cleanPromptText(text: string | undefined): string {
		if (!text) return '';
		// Remove <command-message>...</command-message>, <command-name>...</command-name>, <command-args>...</command-args>
		return text
			.replace(/<command-message>[^<]*<\/command-message>/g, '')
			.replace(/<command-name>[^<]*<\/command-name>/g, '')
			.replace(/<command-args>/g, '')
			.replace(/<\/command-args>/g, '')
			.replace(/<[^>]+>/g, '') // Remove any other tags
			.trim();
	}

	// Truncate text
	function truncate(text: string | undefined, maxLen: number): string {
		if (!text) return '';
		const cleaned = cleanPromptText(text);
		if (cleaned.length <= maxLen) return cleaned;
		return cleaned.slice(0, maxLen).trim() + '...';
	}
</script>

{#if chain.total_sessions > 1}
	<div class="session-chain {className}">
		<!-- Header -->
		<div class="flex items-center gap-2 mb-4">
			<div class="flex h-7 w-7 items-center justify-center rounded-lg bg-[var(--accent)]/10">
				<GitBranch size={14} class="text-[var(--accent)]" />
			</div>
			<div>
				<h3 class="text-sm font-semibold text-[var(--text-primary)]">Session Chain</h3>
				<p class="text-xs text-[var(--text-muted)]">
					{chain.total_sessions} related session{chain.total_sessions !== 1 ? 's' : ''}
					{#if chain.total_compactions > 0}
						&middot; {chain.total_compactions} compaction{chain.total_compactions !== 1
							? 's'
							: ''}
					{/if}
				</p>
			</div>
		</div>

		<!-- Chain Timeline -->
		<div class="chain-timeline">
			{#each chain.nodes as node, index (node.uuid)}
				<div
					class="chain-node"
					class:is-current={node.is_current}
					class:is-continuation-marker={node.is_continuation_marker}
				>
					<!-- Connector line (not for first node) -->
					{#if index > 0}
						<div class="connector">
							<div class="connector-line"></div>
							<ChevronRight size={14} class="connector-arrow" />
						</div>
					{/if}

					<!-- Node Card -->
					<a
						href={getSessionUrl(node)}
						class="node-card"
						class:current={node.is_current}
						title={node.slug || node.uuid}
					>
						<!-- Depth indicator (right side) -->
						{#if node.chain_depth > 0}
							<div class="depth-badge">
								<span class="text-[10px] font-semibold">
									+{node.chain_depth}
								</span>
							</div>
						{/if}

						<!-- Node content -->
						<div class="node-content">
							<!-- Header row -->
							<div class="flex items-center gap-2 mb-1">
								<code class="slug-text" title={node.uuid}>
									{getDisplayIdentifier(node)}
								</code>
								{#if node.is_current}
									<span class="current-badge"> Current </span>
								{/if}
								{#if node.was_compacted}
									<span title="Context was compacted">
										<Zap size={12} class="text-amber-500 flex-shrink-0" />
									</span>
								{/if}
							</div>

							<!-- Initial prompt preview -->
							{#if node.initial_prompt && !node.is_continuation_marker}
								<p class="prompt-preview">
									{truncate(node.initial_prompt, 80)}
								</p>
							{:else if node.is_continuation_marker}
								<p class="text-xs text-[var(--text-muted)] italic mb-2">
									Continuation marker
								</p>
							{/if}

							<!-- Stats row -->
							<div class="stats-row">
								<span class="stat-item">
									<MessageSquare size={10} />
									{node.message_count}
								</span>
								{#if node.start_time && node.end_time}
									<span class="stat-item" title="Session duration">
										<Clock size={10} />
										{formatDuration(node.start_time, node.end_time)}
									</span>
								{/if}
								{#if node.start_time}
									<span class="stat-item"
										>{formatRelativeTime(node.start_time)}</span
									>
								{/if}
								<ExternalLink size={10} class="ml-auto opacity-40" />
							</div>
						</div>
					</a>
				</div>
			{/each}
		</div>
	</div>
{/if}

<style>
	.session-chain {
		padding: 1rem;
		background: var(--bg-subtle);
		border: 1px solid var(--border);
		border-radius: 0.75rem;
	}

	.chain-timeline {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		align-items: stretch;
	}

	.chain-node {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	/* Improved connector with line and arrow */
	.connector {
		display: flex;
		align-items: center;
		position: relative;
	}

	.connector-line {
		width: 20px;
		height: 2px;
		background: var(--accent);
		border-radius: 1px;
		opacity: 0.5;
	}

	.connector :global(.connector-arrow) {
		color: var(--accent);
		margin-left: -4px;
		opacity: 0.8;
	}

	.node-card {
		position: relative;
		display: block;
		padding: 0.75rem;
		background: var(--bg-base);
		border: 1px solid var(--border);
		border-radius: 0.5rem;
		min-width: 200px;
		max-width: 280px;
		transition: all 0.15s ease;
		text-decoration: none;
	}

	.node-card:hover {
		border-color: var(--accent);
		box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
		transform: translateY(-1px);
	}

	.node-card.current {
		border-color: var(--accent);
		border-width: 2px;
		background: color-mix(in srgb, var(--accent) 5%, var(--bg-base));
	}

	/* Slug styling */
	.slug-text {
		font-size: 0.75rem;
		font-family: var(--font-mono, ui-monospace, monospace);
		color: var(--accent);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		max-width: 200px; /* Increased to accommodate slug + UUID prefix */
	}

	/* Current badge */
	.current-badge {
		display: inline-flex;
		align-items: center;
		padding: 0.125rem 0.375rem;
		border-radius: 0.25rem;
		font-size: 10px;
		font-weight: 600;
		background: color-mix(in srgb, var(--accent) 15%, transparent);
		color: var(--accent);
		flex-shrink: 0;
	}

	/* Depth badge - positioned on right side */
	.depth-badge {
		position: absolute;
		top: -0.5rem;
		right: 0.75rem;
		background: var(--accent);
		color: white;
		border-radius: 0.25rem;
		padding: 0 0.375rem;
		line-height: 1.4;
		font-weight: 600;
		box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
	}

	/* Prompt preview */
	.prompt-preview {
		font-size: 0.75rem;
		color: var(--text-secondary);
		line-height: 1.4;
		display: -webkit-box;
		-webkit-line-clamp: 2;
		-webkit-box-orient: vertical;
		overflow: hidden;
		margin-bottom: 0.5rem;
	}

	/* Stats row */
	.stats-row {
		display: flex;
		align-items: center;
		gap: 0.625rem;
		font-size: 10px;
		color: var(--text-muted);
	}

	.stat-item {
		display: flex;
		align-items: center;
		gap: 0.25rem;
	}

	.is-continuation-marker .node-card {
		opacity: 0.6;
		border-style: dashed;
	}

	.node-content {
		display: flex;
		flex-direction: column;
	}

	/* Mobile: Stack vertically */
	@media (max-width: 640px) {
		.chain-timeline {
			flex-direction: column;
		}

		.connector {
			transform: rotate(90deg);
			margin: 0.25rem 0;
		}

		.node-card {
			width: 100%;
			max-width: none;
		}

		.slug-text {
			max-width: none;
		}
	}
</style>
