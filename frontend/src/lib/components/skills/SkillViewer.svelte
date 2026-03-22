<script lang="ts">
	import { onMount } from 'svelte';
	import { FileText, Loader2, Copy, Check, Eye, Code, Clock, HardDrive } from 'lucide-svelte';
	import { marked } from 'marked';
	import DOMPurify from 'isomorphic-dompurify';
	import { markdownCopyButtons } from '$lib/actions/markdownCopyButtons';
	import { formatDistanceToNow } from 'date-fns';
	import { API_BASE } from '$lib/config';
	import { formatFileSize } from '$lib/utils';

	interface SkillContent {
		name: string;
		path: string;
		type: 'file';
		content: string;
		size_bytes: number;
		modified_at: string;
	}

	interface Props {
		path: string;
		projectEncodedName?: string;
	}

	let { path, projectEncodedName }: Props = $props();

	let skill = $state<SkillContent | null>(null);
	let content = $state('');
	let loading = $state(true);
	let error = $state<string | null>(null);
	let copied = $state(false);
	let viewMode = $state<'code' | 'preview'>('preview');

	onMount(async () => {
		if (path) fetchSkill();
	});

	async function fetchSkill() {
		loading = true;
		error = null;
		try {
			const url = new URL(`${API_BASE}/skills/content`);
			url.searchParams.set('path', path);
			if (projectEncodedName) url.searchParams.set('project', projectEncodedName);

			const res = await fetch(url);
			if (res.status === 404) {
				error = 'Skill not found';
				loading = false;
				return;
			}
			if (!res.ok) throw new Error('Failed to fetch skill content');
			const data = await res.json();
			skill = data;
			content = data.content;
		} catch (e: any) {
			error = e.message;
		} finally {
			loading = false;
		}
	}

	function copyToClipboard() {
		navigator.clipboard.writeText(content);
		copied = true;
		setTimeout(() => (copied = false), 2000);
	}

	let renderedContent = $state('');

	$effect(() => {
		const parsed = marked.parse(content || '');
		if (parsed instanceof Promise) {
			parsed.then((html) => (renderedContent = DOMPurify.sanitize(html)));
		} else {
			renderedContent = DOMPurify.sanitize(parsed);
		}
	});
</script>

<div class="space-y-6">
	<div class="flex items-center justify-between">
		<div class="space-y-1 min-w-0">
			<div class="flex items-center gap-2">
				<FileText size={20} class="text-blue-500 flex-shrink-0" />
				<h1
					class="text-xl font-semibold tracking-tight text-[var(--text-primary)] truncate"
				>
					{path.split('/').pop()}
				</h1>
			</div>

			{#if skill}
				<div class="flex items-center gap-3 text-xs text-[var(--text-muted)] pt-1">
					<span class="flex items-center gap-1">
						<HardDrive size={12} />
						{formatFileSize(skill.size_bytes)}
					</span>
					<span class="flex items-center gap-1">
						<Clock size={12} />
						Last modified {formatDistanceToNow(new Date(skill.modified_at))} ago
					</span>
				</div>
			{/if}
		</div>

		<div class="flex items-center gap-3">
			<div
				class="bg-[var(--bg-subtle)] p-1 rounded-lg flex items-center border border-[var(--border)]"
			>
				<button
					class="flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition-all {viewMode ===
					'preview'
						? 'bg-[var(--bg-base)] text-[var(--text-primary)] shadow-sm'
						: 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'}"
					onclick={() => (viewMode = 'preview')}
				>
					<Eye size={16} />
					Preview
				</button>
				<button
					class="flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition-all {viewMode ===
					'code'
						? 'bg-[var(--bg-base)] text-[var(--text-primary)] shadow-sm'
						: 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'}"
					onclick={() => (viewMode = 'code')}
				>
					<Code size={16} />
					Code
				</button>
			</div>

			<div class="h-6 w-px bg-[var(--border)] mx-1"></div>

			<button
				onclick={copyToClipboard}
				class="inline-flex items-center gap-2 px-3 py-1.5 bg-[var(--bg-subtle)] text-[var(--text-secondary)] font-medium rounded-lg hover:bg-[var(--bg-muted)] transition-all active:scale-95 text-sm border border-[var(--border)]"
				title="Copy to clipboard"
			>
				{#if copied}
					<Check size={16} class="text-green-500" />
					Copied
				{:else}
					<Copy size={16} />
					Copy
				{/if}
			</button>
		</div>
	</div>

	{#if error}
		<div class="p-4 bg-red-500/10 text-red-500 rounded-lg text-sm border border-red-500/20">
			{error}
		</div>
	{:else if loading}
		<div class="flex items-center justify-center py-20">
			<Loader2 class="animate-spin text-[var(--text-muted)]" size={32} />
		</div>
	{:else}
		<div
			class="bg-[var(--bg-base)] rounded-xl border border-[var(--border)] shadow-sm overflow-hidden min-h-[600px]"
		>
			{#if viewMode === 'code'}
				<div
					class="border-b border-[var(--border)] px-4 py-2 bg-[var(--bg-subtle)] flex items-center justify-between"
				>
					<span
						class="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider"
						>Source</span
					>
				</div>
				<pre
					class="w-full h-[600px] p-6 font-mono text-sm bg-[var(--bg-base)] text-[var(--text-primary)] overflow-auto whitespace-pre-wrap">{content}</pre>
			{:else}
				<div class="border-b border-[var(--border)] px-4 py-2 bg-[var(--bg-subtle)]">
					<span
						class="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider"
						>Preview</span
					>
				</div>
				<div class="p-8 markdown-preview max-w-none prose prose-slate dark:prose-invert" use:markdownCopyButtons={renderedContent}>
					{@html renderedContent}
				</div>
			{/if}
		</div>
	{/if}
</div>
