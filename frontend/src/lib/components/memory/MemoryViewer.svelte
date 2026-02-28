<script lang="ts">
	import { marked } from 'marked';
	import DOMPurify from 'isomorphic-dompurify';
	import { formatDistanceToNow } from 'date-fns';
	import { Brain, BookOpen, Terminal, Loader2 } from 'lucide-svelte';
	import { API_BASE } from '$lib/config';
	import type { ProjectMemory } from '$lib/api-types';
	import Card from '$lib/components/ui/Card.svelte';

	interface Props {
		projectEncodedName: string;
	}

	let { projectEncodedName }: Props = $props();

	let memory: ProjectMemory | null = $state(null);
	let loading = $state(true);
	let error = $state(false);
	let renderedContent = $state('');

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

	// Fetch on mount and when project changes
	$effect(() => {
		if (projectEncodedName) {
			fetchMemory();
		}
	});

	// Render markdown when memory content changes
	$effect(() => {
		if (!memory?.content) {
			renderedContent = '';
			return;
		}
		const parsed = marked.parse(memory.content);
		if (parsed instanceof Promise) {
			parsed.then((html) => {
				renderedContent = DOMPurify.sanitize(html);
			});
		} else {
			renderedContent = DOMPurify.sanitize(parsed);
		}
	});

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
{:else if !memory?.exists}
	<!-- Empty state: no memory file yet -->
	<div class="space-y-6">
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
{:else}
	<!-- Memory content -->
	<div class="space-y-4">
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
							{memory.word_count.toLocaleString()} words · Updated {formatDate(memory.modified)}
						</p>
					</div>
				</div>
			</div>
		</Card>

		<!-- Markdown content -->
		<Card variant="default" padding="none">
			<div class="p-6 md:p-8 markdown-preview max-w-none prose prose-slate dark:prose-invert">
				{@html renderedContent}
			</div>
		</Card>

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
