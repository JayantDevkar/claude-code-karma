<script lang="ts">
	import { onMount } from 'svelte';
	import { page } from '$app/stores';
	import {
		FileText,
		Loader2,
		Copy,
		Check,
		Eye,
		Code,
		Clock,
		HardDrive,
		Puzzle,
		ExternalLink
	} from 'lucide-svelte';
	import { marked } from 'marked';
	import DOMPurify from 'isomorphic-dompurify';
	import { formatDistanceToNow } from 'date-fns';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import { API_BASE } from '$lib/config';

	interface Breadcrumb {
		label: string;
		href?: string;
	}

	interface SkillContent {
		name: string;
		path: string;
		type: 'file';
		content: string;
		size_bytes: number;
		modified_at: string;
	}

	let path = $derived($page.params.path ?? '');
	let skill = $state<SkillContent | null>(null);
	let content = $state('');
	let loading = $state(true);
	let error = $state<string | null>(null);
	let copied = $state(false);
	let viewMode = $state<'code' | 'preview'>('preview');

	// Detect plugin skills (path contains ':' like "oh-my-claudecode:autopilot")
	let isPluginSkill = $derived(path.includes(':'));
	let pluginName = $derived(isPluginSkill ? path.split(':')[0] : null);

	// Build breadcrumbs dynamically based on path
	let breadcrumbs = $derived.by((): Breadcrumb[] => {
		const crumbs: Breadcrumb[] = [
			{ label: 'Dashboard', href: '/' },
			{ label: 'Skills', href: '/skills' }
		];

		// If plugin skill, add plugin breadcrumb linking to plugin page
		if (isPluginSkill && pluginName) {
			crumbs.push({ label: pluginName, href: '/plugins/' + encodeURIComponent(pluginName) });
			crumbs.push({ label: path.split(':').slice(1).join(':') });
		} else {
			const parts = path.split('/');
			// Add intermediate path segments (folders)
			for (let i = 0; i < parts.length - 1; i++) {
				const partialPath = parts.slice(0, i + 1).join('/');
				crumbs.push({
					label: parts[i],
					href: `/skills?path=${partialPath}`
				});
			}
			// Add the final file name (no href = current page)
			if (parts.length > 0) {
				crumbs.push({ label: parts[parts.length - 1] });
			}
		}

		return crumbs;
	});

	onMount(async () => {
		if (path) fetchSkill();
	});

	async function fetchSkill() {
		try {
			const url = new URL(`${API_BASE}/skills/content`);
			url.searchParams.set('path', path);

			const res = await fetch(url);
			if (res.status === 404) {
				error = 'Skill not found';
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

	function formatSize(bytes: number): string {
		if (bytes === 0) return '0 B';
		const k = 1024;
		const sizes = ['B', 'KB', 'MB', 'GB'];
		const i = Math.floor(Math.log(bytes) / Math.log(k));
		return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
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

<div class="max-w-4xl mx-auto space-y-6">
	<!-- Page Header with Breadcrumb -->
	<PageHeader
		title={path.split('/').pop() || 'Skill'}
		icon={FileText}
		{breadcrumbs}
		metadata={skill
			? [
					{ icon: HardDrive, text: formatSize(skill.size_bytes) },
					{
						icon: Clock,
						text: `Last modified ${formatDistanceToNow(new Date(skill.modified_at))} ago`
					}
				]
			: []}
	>
		{#snippet headerRight()}
			<div class="flex items-center gap-3">
				<div
					class="bg-[var(--bg-muted)] p-1 rounded-lg flex items-center border border-[var(--border)]"
				>
					<button
						class="flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition-all {viewMode ===
						'preview'
							? 'bg-[var(--bg-base)] text-[var(--text-primary)] shadow-sm'
							: 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'}"
						onclick={() => (viewMode = 'preview')}
					>
						<Eye size={16} />
						Preview
					</button>
					<button
						class="flex items-center gap-2 px-3 py-1.5 rounded-md text-sm font-medium transition-all {viewMode ===
						'code'
							? 'bg-[var(--bg-base)] text-[var(--text-primary)] shadow-sm'
							: 'text-[var(--text-muted)] hover:text-[var(--text-secondary)]'}"
						onclick={() => (viewMode = 'code')}
					>
						<Code size={16} />
						Code
					</button>
				</div>

				<div class="h-6 w-px bg-[var(--border)] mx-1"></div>

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
		{/snippet}
	</PageHeader>

	<!-- Plugin badge -->
	{#if isPluginSkill && pluginName}
		<div
			class="bg-[var(--bg-base)] rounded-xl border border-[var(--border)] shadow-[var(--shadow-sm)] p-4"
		>
			<a
				href="/plugins/{encodeURIComponent(pluginName)}"
				class="
					inline-flex items-center gap-2 px-4 py-2
					text-sm font-medium
					text-[var(--nav-purple)] hover:text-[var(--text-primary)]
					bg-[var(--nav-purple-subtle)] hover:bg-[var(--nav-purple-subtle)]
					border border-[var(--nav-purple)]/20
					rounded-lg
					transition-colors
				"
			>
				<Puzzle size={16} />
				<span>{pluginName}</span>
				<ExternalLink size={12} class="opacity-60" />
			</a>
		</div>
	{/if}

	{#if error}
		<div
			class="p-4 bg-[var(--error-subtle)] text-[var(--error)] rounded-lg text-sm border border-[var(--error)]/30"
		>
			{error}
		</div>
	{:else if loading}
		<div class="flex items-center justify-center py-20">
			<Loader2 class="animate-spin text-[var(--text-faint)]" size={32} />
		</div>
	{:else}
		<div
			class="bg-[var(--bg-base)] rounded-xl border border-[var(--border)] shadow-[var(--shadow-sm)] overflow-hidden min-h-[600px]"
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
				<div class="p-8 markdown-preview max-w-none prose prose-slate">
					{@html renderedContent}
				</div>
			{/if}
		</div>
	{/if}
</div>
