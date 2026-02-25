<script lang="ts">
	import { page } from '$app/stores';
	import {
		FileText,
		Copy,
		Check,
		Eye,
		Code,
		Clock,
		HardDrive,
		ChevronRight
	} from 'lucide-svelte';
	import { marked } from 'marked';
	import DOMPurify from 'isomorphic-dompurify';
	import { formatDistanceToNow } from 'date-fns';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';

	interface SkillContent {
		name: string;
		path: string;
		type: 'file';
		content: string;
		size_bytes: number;
		modified_at: string;
	}

	interface PageData {
		plugin_id: string | undefined;
		path: string | undefined;
		skill: SkillContent | null;
		error: string | null;
	}

	let { data }: { data: PageData } = $props();

	let copied = $state(false);
	let viewMode = $state<'code' | 'preview'>('preview');

	function copyToClipboard() {
		if (data.skill?.content) {
			navigator.clipboard.writeText(data.skill.content);
			copied = true;
			setTimeout(() => (copied = false), 2000);
		}
	}

	function formatSize(bytes: number): string {
		if (bytes === 0) return '0 B';
		const k = 1024;
		const sizes = ['B', 'KB', 'MB', 'GB'];
		const i = Math.floor(Math.log(bytes) / Math.log(k));
		return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
	}

	let renderedContent = $state('');

	$effect(() => {
		if (data.skill?.content) {
			const parsed = marked.parse(data.skill.content);
			if (parsed instanceof Promise) {
				parsed.then((html) => (renderedContent = DOMPurify.sanitize(html)));
			} else {
				renderedContent = DOMPurify.sanitize(parsed);
			}
		}
	});

	// Build breadcrumbs
	const filename = (data.path || '').split('/').pop() || '';
	const breadcrumbs = [
		{ label: 'Dashboard', href: '/' },
		{ label: 'Plugins', href: '/plugins' },
		{
			label: data.plugin_id || '',
			href: `/plugins/${encodeURIComponent(data.plugin_id || '')}`
		},
		{ label: 'Skills', href: `/plugins/${encodeURIComponent(data.plugin_id || '')}` },
		{ label: filename }
	];
</script>

<div class="space-y-6">
	<PageHeader title={filename} icon={FileText} {breadcrumbs} />

	{#if data.error}
		<div class="p-8 bg-red-500/10 text-red-500 rounded-xl text-center border border-red-500/20">
			<p class="text-lg font-medium">{data.error}</p>
		</div>
	{:else if data.skill}
		<div class="space-y-6">
			<div class="flex items-center justify-between">
				<div class="flex items-center gap-3 text-xs text-[var(--text-muted)]">
					<span class="flex items-center gap-1">
						<HardDrive size={12} />
						{formatSize(data.skill.size_bytes)}
					</span>
					<span class="flex items-center gap-1">
						<Clock size={12} />
						Last modified {formatDistanceToNow(new Date(data.skill.modified_at))} ago
					</span>
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

					<button
						onclick={copyToClipboard}
						class="p-2 text-[var(--text-muted)] hover:bg-[var(--bg-subtle)] rounded-lg transition-colors"
						title="Copy content"
					>
						{#if copied}
							<Check size={20} class="text-green-500" />
						{:else}
							<Copy size={20} />
						{/if}
					</button>
				</div>
			</div>

			<div
				class="bg-[var(--bg-base)] rounded-xl border border-[var(--border)] shadow-sm overflow-hidden min-h-[600px]"
			>
				{#if viewMode === 'code'}
					<div
						class="border-b border-[var(--border)] px-4 py-2 bg-[var(--bg-subtle)] flex items-center justify-between"
					>
						<span
							class="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider"
							>Read-Only View</span
						>
					</div>
					<div
						class="w-full h-[600px] p-6 font-mono text-sm bg-[var(--bg-base)] text-[var(--text-primary)] overflow-auto whitespace-pre-wrap"
					>
						{data.skill.content}
					</div>
				{:else}
					<div class="border-b border-[var(--border)] px-4 py-2 bg-[var(--bg-subtle)]">
						<span
							class="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider"
							>Preview</span
						>
					</div>
					<div
						class="p-8 markdown-preview max-w-none prose prose-slate dark:prose-invert"
					>
						{@html renderedContent}
					</div>
				{/if}
			</div>
		</div>
	{/if}
</div>
