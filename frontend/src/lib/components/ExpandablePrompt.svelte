<script lang="ts">
	import { marked } from 'marked';
	import DOMPurify from 'isomorphic-dompurify';
	import {
		ChevronDown,
		ChevronUp,
		MessageSquare,
		Terminal,
		Copy,
		Check,
		Maximize2
	} from 'lucide-svelte';
	import Modal from '$lib/components/ui/Modal.svelte';

	interface Props {
		prompt: string;
		previewLines?: number;
		class?: string;
	}

	let { prompt, previewLines = 8, class: className = '' }: Props = $props();

	let isExpanded = $state(false);
	let copied = $state(false);
	let modalOpen = $state(false);

	// Rendered markdown content - only render what's currently needed
	let renderedContent = $state('');

	// Extract command name from prompt (e.g., "/init", "/commit")
	function extractCommandName(text: string): string | null {
		const match = text.match(/<command-name>([^<]+)<\/command-name>/);
		return match ? match[1] : null;
	}

	// Clean prompt text by removing command tags (skill invocation metadata)
	function cleanPromptText(text: string): string {
		return text
			.replace(/<command-message>[^<]*<\/command-message>\s*/g, '')
			.replace(/<command-name>[^<]*<\/command-name>\s*/g, '')
			.replace(/<command-args>/g, '')
			.replace(/<\/command-args>/g, '')
			.trim();
	}

	// Format character count for display
	function formatCharCount(count: number): string {
		if (count >= 1000) {
			return `${(count / 1000).toFixed(1)}k`;
		}
		return count.toString();
	}

	// Extract command name if present
	const commandName = $derived(extractCommandName(prompt));

	// Clean the prompt for display
	const cleanedPrompt = $derived(cleanPromptText(prompt));

	// Check if this is a command-only prompt (no actual user text)
	const isCommandOnly = $derived(commandName && !cleanedPrompt);

	// Calculate content metrics
	const lines = $derived(cleanedPrompt.split('\n'));
	const charCount = $derived(cleanedPrompt.length);

	// Check if we have more lines than the preview limit
	const hasMoreLines = $derived(lines.length > previewLines);

	// Calculate preview text and how much would be hidden
	const previewText = $derived(
		hasMoreLines ? lines.slice(0, previewLines).join('\n') : cleanedPrompt
	);
	const hiddenChars = $derived(charCount - previewText.length);

	// Only show expand if there's SIGNIFICANT content hidden:
	// - Either: more lines AND at least 100 chars hidden (not just a few words)
	// - Or: total content is very long (> 800 chars)
	const needsExpansion = $derived((hasMoreLines && hiddenChars > 100) || charCount > 800);

	// Show full view button for very long prompts
	const showFullViewButton = $derived(charCount > 1000);

	// Determine which content to render based on expansion state
	// This avoids rendering both full and preview content on every change
	const contentToRender = $derived(isExpanded || modalOpen ? cleanedPrompt : previewText);

	// Single effect to render markdown - only renders what's needed
	$effect(() => {
		const parsed = marked.parse(contentToRender);
		if (parsed instanceof Promise) {
			parsed.then((html) => {
				renderedContent = DOMPurify.sanitize(html);
			});
		} else {
			renderedContent = DOMPurify.sanitize(parsed);
		}
	});

	// Copy to clipboard
	async function copyToClipboard() {
		try {
			await navigator.clipboard.writeText(cleanedPrompt);
			copied = true;
			setTimeout(() => {
				copied = false;
			}, 2000);
		} catch (err) {
			console.error('Failed to copy:', err);
		}
	}
</script>

{#if isCommandOnly}
	<!-- Command-only prompt (e.g., /init with no additional text) -->
	<div
		class="
			relative
			p-4 pl-5
			bg-[var(--bg-subtle)]
			border border-[var(--border)]
			border-l-[3px] border-l-[var(--nav-purple)]
			rounded-[var(--radius-lg)]
			{className}
		"
	>
		<div class="flex items-center gap-2">
			<div class="p-1.5 rounded-md bg-[var(--nav-purple-subtle)]">
				<Terminal size={14} strokeWidth={2} class="text-[var(--nav-purple)]" />
			</div>
			<h3 class="text-sm font-medium text-[var(--text-primary)]">Session Command</h3>
		</div>
		<div class="mt-2 flex items-center gap-2">
			<code
				class="px-2 py-1 bg-[var(--bg-muted)] rounded font-mono text-sm text-[var(--nav-purple)]"
			>
				{commandName}
			</code>
			<span class="text-xs text-[var(--text-muted)]">Session started via command</span>
		</div>
	</div>
{:else}
	<!-- Regular prompt with user text -->
	<div
		class="
			relative
			p-4 pl-5
			bg-[var(--bg-subtle)]
			border border-[var(--border)]
			border-l-[3px] border-l-[var(--accent)]
			rounded-[var(--radius-lg)]
			{className}
		"
	>
		<!-- Header with title, command badge, and action buttons -->
		<div class="flex items-center justify-between mb-3">
			<div class="flex items-center gap-2">
				<div class="p-1.5 rounded-md bg-[var(--accent-subtle)]">
					<MessageSquare size={14} strokeWidth={2} class="text-[var(--accent)]" />
				</div>
				<h3 class="text-sm font-medium text-[var(--text-primary)]">Initial Prompt</h3>
				{#if commandName}
					<code
						class="px-1.5 py-0.5 bg-[var(--bg-muted)] rounded font-mono text-xs text-[var(--text-muted)]"
					>
						{commandName}
					</code>
				{/if}
			</div>

			<!-- Action buttons -->
			<div class="flex items-center gap-1">
				{#if showFullViewButton}
					<button
						type="button"
						onclick={() => (modalOpen = true)}
						class="
							p-1.5 rounded-md
							text-[var(--text-muted)]
							hover:text-[var(--text-primary)]
							hover:bg-[var(--bg-muted)]
							transition-colors
						"
						title="Full view"
						aria-label="Open full view"
					>
						<Maximize2 size={14} />
					</button>
				{/if}
				<button
					type="button"
					onclick={copyToClipboard}
					class="
						p-1.5 rounded-md
						text-[var(--text-muted)]
						hover:text-[var(--text-primary)]
						hover:bg-[var(--bg-muted)]
						transition-colors
						{copied ? 'text-green-500' : ''}
					"
					title={copied ? 'Copied!' : 'Copy prompt'}
					aria-label={copied ? 'Copied to clipboard' : 'Copy prompt to clipboard'}
				>
					{#if copied}
						<Check size={14} />
					{:else}
						<Copy size={14} />
					{/if}
				</button>
			</div>
		</div>

		<!-- Markdown content -->
		<div class="bg-[var(--bg-muted)] px-3 py-2 rounded-md">
			<div
				class="markdown-preview text-sm prompt-content {!isExpanded && needsExpansion
					? 'prompt-preview'
					: ''}"
			>
				{@html renderedContent}
			</div>
		</div>

		<!-- Expand/Collapse button with character count -->
		{#if needsExpansion}
			<div class="flex justify-center mt-3">
				<button
					type="button"
					onclick={() => (isExpanded = !isExpanded)}
					class="
						flex items-center gap-1.5 px-3 py-1.5
						text-xs font-medium
						text-[var(--accent)]
						hover:bg-[var(--accent-subtle)]
						rounded-full
						transition-colors
						focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]
					"
					aria-expanded={isExpanded}
					aria-label={isExpanded ? 'Collapse prompt' : 'Expand prompt'}
				>
					{#if isExpanded}
						<ChevronUp size={14} strokeWidth={2.5} />
						<span>Show less</span>
					{:else}
						<ChevronDown size={14} strokeWidth={2.5} />
						<span>Show more ({formatCharCount(charCount)} chars)</span>
					{/if}
				</button>
			</div>
		{/if}
	</div>

	<!-- Full view modal for very long prompts -->
	<Modal bind:open={modalOpen} title="Initial Prompt" maxWidth="xl">
		{#snippet children()}
			<div class="flex justify-end mb-4">
				<button
					type="button"
					onclick={copyToClipboard}
					class="
						flex items-center gap-1.5 px-3 py-1.5
						text-xs font-medium rounded-md
						text-[var(--text-muted)]
						hover:text-[var(--text-primary)]
						hover:bg-[var(--bg-muted)]
						transition-colors
						{copied ? 'text-green-500' : ''}
					"
				>
					{#if copied}
						<Check size={14} />
						<span>Copied!</span>
					{:else}
						<Copy size={14} />
						<span>Copy</span>
					{/if}
				</button>
			</div>
			<div class="markdown-preview max-h-[70vh] overflow-y-auto pr-2 custom-scrollbar">
				{@html renderedContent}
			</div>
			<div class="mt-4 pt-3 border-t border-[var(--border)]">
				<span class="text-xs text-[var(--text-muted)]">
					{charCount.toLocaleString()} characters
				</span>
			</div>
		{/snippet}
	</Modal>
{/if}

<style>
	/* Limit height of preview and add fade effect - only applied when needsExpansion */
	.prompt-preview {
		max-height: 16em;
		overflow: hidden;
		position: relative;
	}

	.prompt-preview::after {
		content: '';
		position: absolute;
		bottom: 0;
		left: 0;
		right: 0;
		height: 4em;
		background: linear-gradient(to bottom, transparent, var(--bg-muted));
		pointer-events: none;
	}

	/* Override some markdown-preview styles for prompt context */
	.prompt-content :global(h1) {
		font-size: 1.25rem;
		margin-top: 1rem;
	}

	.prompt-content :global(h2) {
		font-size: 1.1rem;
		margin-top: 0.75rem;
	}

	.prompt-content :global(h3) {
		font-size: 1rem;
		margin-top: 0.5rem;
	}

	.prompt-content :global(p:first-child) {
		margin-top: 0;
	}

	.prompt-content :global(p:last-child) {
		margin-bottom: 0;
	}

	/* Custom scrollbar for modal */
	.custom-scrollbar::-webkit-scrollbar {
		width: 6px;
	}

	.custom-scrollbar::-webkit-scrollbar-track {
		background: var(--bg-subtle);
		border-radius: 3px;
	}

	.custom-scrollbar::-webkit-scrollbar-thumb {
		background: var(--border);
		border-radius: 3px;
	}

	.custom-scrollbar::-webkit-scrollbar-thumb:hover {
		background: var(--text-muted);
	}
</style>
