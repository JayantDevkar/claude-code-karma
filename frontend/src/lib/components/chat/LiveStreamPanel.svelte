<script lang="ts">
	import { marked } from 'marked';
	import DOMPurify from 'isomorphic-dompurify';
	import type { LiveEvent } from './types';

	interface Props {
		events: LiveEvent[];
		visible: boolean;
	}

	let { events, visible }: Props = $props();

	function renderMarkdown(text: string): string {
		const html = marked.parse(text, { async: false }) as string;
		return DOMPurify.sanitize(html);
	}

	// Parse tool args for rich summary text
	function parseArgs(content: string): Record<string, unknown> {
		try { return JSON.parse(content); } catch { return {}; }
	}

	function toolSummary(name: string, content: string): string {
		const args = parseArgs(content);
		switch (name) {
			case 'Bash': {
				const cmd = (args.command as string | undefined) ?? '';
				const first = cmd.split('\n')[0].trim();
				return first.length > 60 ? first.slice(0, 57) + '…' : first || 'Ran shell command';
			}
			case 'Read': {
				const p = (args.file_path as string | undefined) ?? '';
				return 'Read ' + (p.split('/').pop() || 'file');
			}
			case 'Write': {
				const p = (args.file_path as string | undefined) ?? '';
				return 'Wrote ' + (p.split('/').pop() || 'file');
			}
			case 'Edit':
			case 'MultiEdit': {
				const p = (args.file_path as string | undefined) ?? '';
				return 'Edited ' + (p.split('/').pop() || 'file');
			}
			case 'Glob': return 'Listed files';
			case 'Grep': {
				const pat = (args.pattern as string | undefined) ?? '';
				return 'Searched ' + (pat.length > 30 ? pat.slice(0, 27) + '…' : pat || 'pattern');
			}
			case 'WebFetch': {
				const url = (args.url as string | undefined) ?? '';
				try { return 'Fetched ' + new URL(url).hostname; } catch { return 'Fetched URL'; }
			}
			case 'WebSearch': {
				const q = (args.query as string | undefined) ?? '';
				return 'Searched ' + (q.length > 40 ? q.slice(0, 37) + '…' : q || 'web');
			}
			case 'Task':       return 'Launched subagent';
			case 'TodoWrite':  return 'Updated todos';
			case 'TodoRead':   return 'Read todos';
			default:           return `${name}`;
		}
	}

	// Only show tool_result if it's an error; otherwise the tool_call summary is enough
	let displayEvents = $derived(
		events.filter(ev => ev.type !== 'tool_result' || ev.is_error)
	);

	// Split response text into paragraph-ish blocks for bullet rendering
	function paragraphs(text: string): string[] {
		return text.split(/\n{2,}/).map(p => p.trim()).filter(Boolean);
	}

	let bottomEl: HTMLDivElement | undefined = $state();
	$effect(() => {
		if (events.length && bottomEl) {
			bottomEl.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
		}
	});
</script>

{#if visible && events.length > 0}
	<div class="mt-3 mb-1 text-sm leading-relaxed select-text">
		{#each displayEvents as ev (ev.id)}

			{#if ev.type === 'user_prompt'}
				<!-- User message: dark full-width strip like terminal input bar -->
				<div class="flex items-start gap-2.5 px-3 py-2 my-1 font-mono bg-[var(--bg-muted)] rounded-sm border-l-2 border-[var(--accent)]/50">
					<span class="text-[var(--accent)] shrink-0 leading-relaxed">›</span>
					<span class="text-[var(--text-primary)] flex-1 whitespace-pre-wrap break-words">{ev.content}</span>
				</div>

			{:else if ev.type === 'thinking'}
				<!-- Thinking: asterisk prefix, muted italic -->
				<div class="px-1 py-0.5 font-mono text-[var(--text-faint)] italic">
					<span class="not-italic opacity-50 mr-1.5">✳</span>Thinking…
				</div>

			{:else if ev.type === 'tool_call'}
				<!-- Tool summary: muted, one line -->
				<div class="flex items-center gap-1 px-1 py-0.5 font-mono text-[var(--text-faint)]">
					<span class="opacity-40 mr-0.5 text-xs">⎿</span>{toolSummary(ev.tool_name ?? '', ev.content)}
				</div>

			{:else if ev.type === 'tool_result' && ev.is_error}
				<!-- Error result only -->
				<div class="flex items-start gap-1.5 px-1 py-0.5 pl-5 font-mono text-[var(--error)]">
					<span class="shrink-0">✗</span>
					<span class="opacity-80 truncate">{ev.content.split('\n')[0]}</span>
				</div>

			{:else if ev.type === 'response_text'}
				<!-- Claude response: bullet prefix per block, readable sans prose -->
				{#each paragraphs(ev.content) as para}
					<div class="flex items-start gap-2 px-1 py-0.5">
						<span class="text-[var(--text-muted)] shrink-0 mt-px leading-relaxed">•</span>
						<div class="stream-prose flex-1 min-w-0 font-sans text-[var(--text-secondary)]">{@html renderMarkdown(para)}</div>
					</div>
				{/each}
			{/if}

		{/each}
		<div bind:this={bottomEl}></div>
	</div>
{/if}

<style>
	/* Compact prose for streamed markdown — tighter than .markdown-preview */
	.stream-prose :global(p) { margin: 0; }
	.stream-prose :global(p + p) { margin-top: 0.375rem; }
	.stream-prose :global(strong) { color: var(--text-primary); font-weight: 600; }
	.stream-prose :global(em) { font-style: italic; }
	.stream-prose :global(a) { color: var(--accent); text-decoration: underline; text-underline-offset: 2px; }
	.stream-prose :global(h1),
	.stream-prose :global(h2),
	.stream-prose :global(h3),
	.stream-prose :global(h4) { color: var(--text-primary); font-weight: 600; font-size: 0.875rem; margin: 0.5rem 0 0.25rem; }
	.stream-prose :global(ul),
	.stream-prose :global(ol) { margin: 0.25rem 0; padding-left: 1.25rem; }
	.stream-prose :global(ul) { list-style: disc outside; }
	.stream-prose :global(ol) { list-style: decimal outside; }
	.stream-prose :global(li) { margin: 0.125rem 0; }
	.stream-prose :global(code) { font-family: var(--font-mono); font-size: 0.75rem; background: var(--bg-muted); border: 1px solid var(--border-subtle); padding: 0.0625rem 0.25rem; border-radius: 0.25rem; color: var(--text-primary); }
	.stream-prose :global(pre) { background: var(--bg-subtle); border: 1px solid var(--border); border-radius: 0.5rem; padding: 0.625rem; margin: 0.375rem 0; overflow-x: auto; }
	.stream-prose :global(pre code) { background: transparent; border: none; padding: 0; display: block; }
	.stream-prose :global(blockquote) { border-left: 2px solid var(--accent); padding-left: 0.625rem; color: var(--text-muted); margin: 0.375rem 0; }
</style>
