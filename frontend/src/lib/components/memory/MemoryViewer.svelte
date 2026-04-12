<script lang="ts">
	import { formatDistanceToNow } from 'date-fns';
	import { Brain, BookOpen, Terminal, Loader2 } from 'lucide-svelte';
	import { API_BASE } from '$lib/config';
	import type { ProjectMemory, MemoryFileMeta } from '$lib/api-types';
	import Card from '$lib/components/ui/Card.svelte';
	import MemoryIndex from './MemoryIndex.svelte';
	import MemoryOrphanList from './MemoryOrphanList.svelte';
	import MemoryHoverCard from './MemoryHoverCard.svelte';
	import MemoryFilePanel from './MemoryFilePanel.svelte';

	interface Props {
		projectEncodedName: string;
	}

	let { projectEncodedName }: Props = $props();

	let memory = $state<ProjectMemory | null>(null);
	let loading = $state(true);
	let error = $state(false);

	// Hover/select state
	let selectedFilename = $state<string | null>(null);
	let hoveredFilename = $state<string | null>(null);
	let hoverAnchorRect = $state<DOMRect | null>(null);
	let hoverTimer: ReturnType<typeof setTimeout> | null = null;

	const HOVER_DELAY_MS = 150;

	// Derived: lookup table for hovered file
	const hoveredFile = $derived.by<MemoryFileMeta | null>(() => {
		if (!hoveredFilename || !memory) return null;
		return memory.files.find((f) => f.filename === hoveredFilename) ?? null;
	});

	// Derived: orphan files (those not linked from the index)
	const orphanFiles = $derived.by<MemoryFileMeta[]>(() => {
		if (!memory) return [];
		return memory.files.filter((f) => !f.linked_from_index);
	});

	async function fetchMemory() {
		loading = true;
		error = false;
		try {
			const res = await fetch(`${API_BASE}/projects/${projectEncodedName}/memory`);
			if (!res.ok) throw new Error('Failed to fetch');
			memory = await res.json();
		} catch {
			error = true;
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		if (projectEncodedName) {
			fetchMemory();
		}
	});

	function handleLinkHover(filename: string, rect: DOMRect) {
		// Always update the anchor rect immediately so the popover follows the
		// element if the user re-hovers a different link.
		hoverAnchorRect = rect;
		if (hoverTimer) clearTimeout(hoverTimer);
		hoverTimer = setTimeout(() => {
			hoveredFilename = filename;
		}, HOVER_DELAY_MS);
	}

	function handleLinkLeave() {
		if (hoverTimer) {
			clearTimeout(hoverTimer);
			hoverTimer = null;
		}
		hoveredFilename = null;
		hoverAnchorRect = null;
	}

	function handleLinkSelect(filename: string) {
		// Opening the panel implicitly clears the hover popover
		if (hoverTimer) {
			clearTimeout(hoverTimer);
			hoverTimer = null;
		}
		hoveredFilename = null;
		selectedFilename = filename;
	}

	function handlePanelClose() {
		selectedFilename = null;
	}

	function formatDate(dateStr: string): string {
		try {
			return formatDistanceToNow(new Date(dateStr), { addSuffix: true });
		} catch {
			return dateStr;
		}
	}
</script>

{#if loading}
	<div class="flex items-center justify-center py-20">
		<Loader2 size={24} class="animate-spin text-[var(--text-muted)]" />
	</div>
{:else if error}
	<Card variant="default" padding="md">
		<div class="text-center py-10">
			<Brain size={32} class="mx-auto mb-3 text-[var(--text-muted)]" />
			<p class="text-sm text-[var(--text-muted)]">Failed to load project memory.</p>
		</div>
	</Card>
{:else if memory && !memory.index.exists && memory.files.length === 0}
	<!-- Empty state: no MEMORY.md and no children -->
	<div class="space-y-6" data-testid="memory-empty-state">
		<Card variant="default" padding="none">
			<div class="px-6 py-12 text-center">
				<div
					class="w-14 h-14 rounded-2xl bg-[var(--bg-subtle)] border border-[var(--border)] flex items-center justify-center mx-auto mb-4"
				>
					<Brain size={26} class="text-[var(--text-muted)]" />
				</div>
				<h3 class="text-base font-semibold text-[var(--text-primary)] mb-2">
					No Project Memory Yet
				</h3>
				<p class="text-sm text-[var(--text-muted)] max-w-md mx-auto leading-relaxed">
					Claude Code hasn't saved any memory for this project yet. Memory files store
					persistent context — patterns, conventions, and decisions — that Claude remembers
					across sessions.
				</p>
			</div>
		</Card>

		<!-- How to use section -->
		<Card variant="default" padding="none">
			<div class="px-6 py-4 border-b border-[var(--border)]">
				<div class="flex items-center gap-2.5">
					<Terminal size={16} class="text-[var(--accent)]" />
					<h4 class="text-sm font-semibold text-[var(--text-primary)]">
						How to Create Project Memory
					</h4>
				</div>
			</div>
			<div class="px-6 py-4 space-y-3">
				<p class="text-sm text-[var(--text-secondary)] leading-relaxed">
					Use the <code
						class="px-1.5 py-0.5 rounded bg-[var(--bg-muted)] text-[var(--accent)] text-xs font-mono"
						>/memory</code
					>
					command in any Claude Code session to update this project's memory. Claude will save
					key patterns, architectural decisions, and conventions it discovers.
				</p>
				<div
					class="rounded-lg bg-[var(--bg-subtle)] border border-[var(--border)] px-4 py-3 font-mono text-xs text-[var(--text-secondary)]"
				>
					<span class="text-[var(--text-muted)]">$</span> claude
					<span class="text-[var(--text-muted)]">›</span>
					<span class="text-[var(--accent)]">/memory</span>
				</div>
				<p class="text-xs text-[var(--text-muted)]">
					You can also ask Claude to "remember this" or "save to memory" during any session.
				</p>
			</div>
		</Card>
	</div>
{:else if memory && !memory.index.exists && memory.files.length > 0}
	<!-- Children present but no index — render orphan-only layout -->
	<div class="space-y-4" data-testid="memory-orphans-only">
		<Card variant="default" padding="none">
			<div class="px-6 py-4 flex items-center gap-3">
				<div class="p-2 rounded-lg bg-[var(--accent-subtle)]">
					<Brain size={18} class="text-[var(--accent)]" />
				</div>
				<div>
					<h3 class="text-sm font-semibold text-[var(--text-primary)]">
						Orphan memory files
					</h3>
					<p class="text-xs text-[var(--text-muted)]">
						{memory.files.length} file{memory.files.length === 1 ? '' : 's'} present, no MEMORY.md index
					</p>
				</div>
			</div>
		</Card>
		<MemoryOrphanList
			files={memory.files}
			onLinkHover={handleLinkHover}
			onLinkLeave={handleLinkLeave}
			onLinkSelect={handleLinkSelect}
		/>
	</div>
{:else if memory && memory.index.exists}
	<!-- Index + (optional) orphans layout -->
	<div class="space-y-4" data-testid="memory-loaded">
		<!-- Header card with metadata -->
		<Card variant="default" padding="none">
			<div class="px-6 py-4 flex items-center justify-between">
				<div class="flex items-center gap-3">
					<div class="p-2 rounded-lg bg-[var(--accent-subtle)]">
						<Brain size={18} class="text-[var(--accent)]" />
					</div>
					<div>
						<h3 class="text-sm font-semibold text-[var(--text-primary)]">MEMORY.md</h3>
						<p class="text-xs text-[var(--text-muted)]">
							{memory.index.word_count.toLocaleString()} words · Updated {formatDate(
								memory.index.modified
							)}
							{#if memory.files.length > 0}
								· {memory.files.length} linked file{memory.files.length === 1 ? '' : 's'}
							{/if}
						</p>
					</div>
				</div>
			</div>
		</Card>

		<!-- Markdown content -->
		<Card variant="default" padding="none">
			<MemoryIndex
				content={memory.index.content}
				files={memory.files}
				onLinkHover={handleLinkHover}
				onLinkLeave={handleLinkLeave}
				onLinkSelect={handleLinkSelect}
			/>
		</Card>

		<!-- Orphan files (collapsed by default) -->
		<MemoryOrphanList
			files={orphanFiles}
			onLinkHover={handleLinkHover}
			onLinkLeave={handleLinkLeave}
			onLinkSelect={handleLinkSelect}
		/>

		<!-- How to update hint -->
		<div
			class="flex items-start gap-3 rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)] px-4 py-3"
		>
			<BookOpen size={16} class="text-[var(--text-muted)] mt-0.5 shrink-0" />
			<p class="text-xs text-[var(--text-muted)] leading-relaxed">
				Use <code
					class="px-1 py-0.5 rounded bg-[var(--bg-muted)] text-[var(--accent)] font-mono"
					>/memory</code
				> in a Claude Code session to update this project's memory. Claude saves patterns, decisions,
				and conventions it discovers across sessions.
			</p>
		</div>
	</div>
{/if}

<!-- Hover popover (overlays) -->
<MemoryHoverCard file={hoveredFile} anchorRect={hoverAnchorRect} />

<!-- Side panel (overlays) -->
<MemoryFilePanel
	filename={selectedFilename}
	{projectEncodedName}
	onClose={handlePanelClose}
/>
