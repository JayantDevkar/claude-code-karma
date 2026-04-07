<script lang="ts">
	import { marked } from 'marked';
	import DOMPurify from 'isomorphic-dompurify';
	import { markdownCopyButtons } from '$lib/actions/markdownCopyButtons';
	import { rewriteMemoryLinks } from '$lib/actions/rewriteMemoryLinks';
	import type { MemoryFileMeta } from '$lib/api-types';

	interface Props {
		content: string;
		files: MemoryFileMeta[];
		onLinkHover: (filename: string, rect: DOMRect) => void;
		onLinkLeave: () => void;
		onLinkSelect: (filename: string) => void;
	}

	let { content, files, onLinkHover, onLinkLeave, onLinkSelect }: Props = $props();

	let renderedContent = $state('');

	$effect(() => {
		if (!content) {
			renderedContent = '';
			return;
		}
		const parsed = marked.parse(content);
		if (parsed instanceof Promise) {
			parsed.then((html) => {
				renderedContent = DOMPurify.sanitize(html);
			});
		} else {
			renderedContent = DOMPurify.sanitize(parsed);
		}
	});
</script>

<div
	class="p-6 md:p-8 markdown-preview max-w-none prose prose-slate dark:prose-invert"
	data-testid="memory-index-content"
	use:markdownCopyButtons={renderedContent}
	use:rewriteMemoryLinks={{
		files,
		onHover: onLinkHover,
		onLeave: onLinkLeave,
		onSelect: onLinkSelect
	}}
>
	{@html renderedContent}
</div>

<style>
	/* In-app memory link styling — applied to <a> elements that the
	   rewriteMemoryLinks action has tagged. */
	div :global(a.memory-link) {
		color: var(--accent);
		text-decoration: underline;
		text-decoration-thickness: 1px;
		text-underline-offset: 2px;
		cursor: pointer;
		transition: background-color 120ms ease;
		padding: 0 2px;
		border-radius: 3px;
	}

	div :global(a.memory-link::after) {
		content: '↗';
		display: inline-block;
		margin-left: 2px;
		font-size: 0.85em;
		opacity: 0.5;
		transition: opacity 120ms ease;
	}

	div :global(a.memory-link:hover) {
		background-color: var(--accent-subtle);
	}

	div :global(a.memory-link:hover::after) {
		opacity: 1;
	}

	/* Broken memory link — points to *.md not in files[] */
	div :global(a.memory-link--broken) {
		color: var(--text-muted);
		text-decoration: underline dashed;
		text-decoration-thickness: 1px;
		text-underline-offset: 2px;
		cursor: default;
	}
</style>
