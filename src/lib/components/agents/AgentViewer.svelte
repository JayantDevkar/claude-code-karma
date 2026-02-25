<script lang="ts">
	import { onMount } from 'svelte';
	import { Bot, Loader2, Check, Eye, Code, Clock, HardDrive, Copy, Layers } from 'lucide-svelte';
	import { marked } from 'marked';
	import DOMPurify from 'isomorphic-dompurify';
	import { formatDistanceToNow } from 'date-fns';
	import { API_BASE } from '$lib/config';
	import { formatFileSize } from '$lib/utils';

	interface AgentDetail {
		name: string;
		content: string;
		size_bytes: number;
		modified_at: string;
	}

	interface Props {
		name: string;
		projectEncodedName?: string;
	}

	let { name, projectEncodedName }: Props = $props();

	let agent = $state<AgentDetail | null>(null);
	let content = $state('');
	let loading = $state(true);
	let error = $state<string | null>(null);
	let copied = $state(false);
	let viewMode = $state<'code' | 'preview'>('preview');

	onMount(async () => {
		fetchAgent();
	});

	async function fetchAgent() {
		loading = true;
		error = null;
		try {
			const url = new URL(`${API_BASE}/agents/${name}`);
			if (projectEncodedName) url.searchParams.set('project', projectEncodedName);

			const res = await fetch(url);
			if (res.status === 404) {
				error = 'Agent not found';
				loading = false;
				return;
			}
			if (!res.ok) throw new Error('Failed to fetch agent');
			const data = await res.json();
			agent = data;
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
		<div class="space-y-1">
			<div class="flex items-center gap-2">
				<Bot size={24} class="text-[var(--accent)]" />
				<h1 class="text-2xl font-semibold tracking-tight text-[var(--text-primary)]">
					{name}
				</h1>
			</div>
			{#if agent && agent.size_bytes > 0}
				<div class="flex items-center gap-3 text-xs text-[var(--text-muted)] pt-1">
					<span class="flex items-center gap-1">
						<HardDrive size={12} />
						{formatFileSize(agent.size_bytes)}
					</span>
					<span class="flex items-center gap-1">
						<Clock size={12} />
						Last modified {formatDistanceToNow(new Date(agent.modified_at))} ago
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

			<a
				href="/agents/{encodeURIComponent(name)}{projectEncodedName
					? `?tab=history&project=${encodeURIComponent(projectEncodedName)}`
					: ''}"
				class="inline-flex items-center gap-2 px-4 py-2 bg-[var(--accent)] text-white font-medium rounded-lg hover:bg-[var(--accent-hover)] transition-all active:scale-95"
				title="View usage stats and sessions for this agent"
			>
				<Layers size={18} />
				View Sessions
			</a>

			<button
				onclick={copyToClipboard}
				class="inline-flex items-center gap-2 px-4 py-2 bg-[var(--bg-subtle)] text-[var(--text-secondary)] font-medium rounded-lg hover:bg-[var(--bg-muted)] transition-all active:scale-95 border border-[var(--border)]"
				title="Copy to clipboard"
			>
				{#if copied}
					<Check size={18} class="text-green-500" />
					Copied!
				{:else}
					<Copy size={18} />
					Copy
				{/if}
			</button>
		</div>
	</div>

	{#if error}
		<div class="p-4 bg-red-500/10 text-red-500 rounded-lg text-sm border border-red-500/20">
			{error}
		</div>
	{/if}

	{#if loading}
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
				<div
					class="border-b border-[var(--border)] px-4 py-2 bg-[var(--bg-subtle)] flex items-center justify-between"
				>
					<span
						class="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider"
						>Preview</span
					>
				</div>
				<div class="p-8 markdown-preview max-w-none prose prose-slate dark:prose-invert">
					{@html renderedContent}
				</div>
			{/if}
		</div>
	{/if}
</div>
