<script lang="ts">
	import { untrack } from 'svelte';
	import { Copy, Check } from 'lucide-svelte';
	import { marked } from 'marked';
	import type { TimelineEvent } from '$lib/api-types';
	import ImageAttachments from '$lib/components/ImageAttachments.svelte';
	import { markdownCopyButtons } from '$lib/actions/markdownCopyButtons';
	import { highlightHtmlContent, highlightPlainText } from '$lib/utils/highlight';
	import { sanitizeEventHtml } from '$lib/utils/sanitizeEventHtml';
	import { getEventSections } from './timeline-display';

	interface Props {
		event: TimelineEvent;
		searchQuery?: string;
	}

	let { event, searchQuery = '' }: Props = $props();

	let isCopied = $state(false);

	// A body can be hundreds of thousands of characters; lay out only the start until asked.
	const RENDER_LIMIT = 6000;

	let showAllFor = $state<string | null>(null);
	const showAll = $derived(showAllFor === event.id);

	const fullSections = $derived(getEventSections(event));
	const hiddenChars = $derived(
		fullSections.reduce((sum, s) => sum + Math.max(0, s.content.length - RENDER_LIMIT), 0)
	);

	function capContent(content: string): string {
		if (content.length <= RENDER_LIMIT) return content;
		// Cut at a line break when one is near, so a line is not split mid-way.
		const lineEnd = content.lastIndexOf('\n', RENDER_LIMIT);
		return content.slice(0, lineEnd > RENDER_LIMIT * 0.8 ? lineEnd : RENDER_LIMIT);
	}

	const sections = $derived(
		showAll || hiddenChars === 0
			? fullSections
			: fullSections.map((s) =>
					s.format === 'link' ? s : { ...s, content: capContent(s.content) }
				)
	);

	// Live polling replaces the event object every second; only re-parse when the text changes.
	const contentKey = $derived(
		sections.map((s) => `${s.format}:${s.keepBreaks ? 1 : 0}:${s.content}`).join('\u0000')
	);
	const parsedHtml = $derived.by<string[]>(() => {
		void contentKey;
		return untrack(() =>
			sections.map((s) =>
				s.format === 'markdown'
					? sanitizeEventHtml(
							marked.parse(s.content, { async: false, breaks: s.keepBreaks === true })
						)
					: ''
			)
		);
	});
	const renderedHtml = $derived(
		parsedHtml.map((html) => (searchQuery ? highlightHtmlContent(html, searchQuery) : html))
	);

	function copyAll(e: MouseEvent) {
		e.stopPropagation();
		navigator.clipboard.writeText(fullSections.map((s) => s.content).join('\n\n'));
		isCopied = true;
		setTimeout(() => (isCopied = false), 2000);
	}
</script>

<div class="rounded bg-[var(--bg-muted)]/50 p-3 relative">
	<button
		class="
			md-global-copy
			float-right
			ml-2 mb-2
			p-1.5
			rounded-md
			bg-[var(--bg-base)]
			border border-[var(--border)]
			text-[var(--text-muted)]
			shadow-sm
			hover:text-[var(--text-primary)] hover:border-[var(--accent)]
			transition-colors
		"
		data-tooltip={isCopied ? 'Copied!' : 'Copy content'}
		aria-label={isCopied ? 'Copied!' : 'Copy content'}
		onclick={copyAll}
	>
		{#if isCopied}
			<Check size={14} class="text-[var(--success)]" />
		{:else}
			<Copy size={14} />
		{/if}
	</button>
	{#if event.metadata?.image_attachments?.length}
		<ImageAttachments attachments={event.metadata.image_attachments} />
	{/if}
	{#each sections as section, i (i)}
		{#if section.label}
			<h4 class="mb-1 text-xs font-medium text-[var(--text-secondary)] {i > 0 ? 'mt-4' : ''}">
				{section.label}
			</h4>
		{/if}
		{#if section.format === 'markdown'}
			<div class="markdown-preview text-sm" use:markdownCopyButtons={renderedHtml[i]}>
				{@html renderedHtml[i]}
			</div>
		{:else if section.format === 'link'}
			<a
				href={section.content}
				target="_blank"
				rel="noopener noreferrer"
				class="break-all text-sm text-[var(--accent)] hover:underline"
				onclick={(e) => e.stopPropagation()}
			>
				{section.content}
			</a>
		{:else}
			<pre
				class="overflow-x-auto whitespace-pre-wrap break-words rounded border border-[var(--border)] bg-[var(--bg-base)] p-2.5 font-mono text-xs text-[var(--text-primary)]">{#if searchQuery}{@html highlightPlainText(
						section.content,
						searchQuery
					)}{:else}{section.content}{/if}</pre>
		{/if}
	{/each}
	{#if hiddenChars > 0 && !showAll}
		<div class="mt-3 flex flex-wrap items-center gap-2 text-xs text-[var(--text-muted)]">
			<span>Showing the first part. {hiddenChars.toLocaleString()} more characters.</span>
			<button
				type="button"
				class="rounded-md border border-[var(--border)] bg-[var(--bg-base)] px-2 py-1 font-medium text-[var(--text-primary)] hover:border-[var(--accent)]"
				onclick={(e) => {
					e.stopPropagation();
					showAllFor = event.id;
				}}
			>
				Show all
			</button>
		</div>
	{/if}
</div>
