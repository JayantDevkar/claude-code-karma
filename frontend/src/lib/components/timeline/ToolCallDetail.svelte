<script lang="ts">
	import { Copy, Check, AlertCircle, CheckCircle2 } from 'lucide-svelte';
	import { marked } from 'marked';
	import DOMPurify from 'isomorphic-dompurify';
	import type { TimelineEvent } from '$lib/api-types';
	import { formatDisplayPath } from '$lib/utils';

	interface Props {
		event: TimelineEvent;
		projectPath?: string | null;
		class?: string;
	}

	let { event, projectPath = null, class: className = '' }: Props = $props();

	let copiedSection = $state<string | null>(null);
	let renderedPlanHtml = $state('');

	// Extract tool metadata
	const toolName = $derived(event.metadata?.tool_name as string | undefined);
	const hasResult = $derived(event.metadata?.has_result === true);
	const resultContent = $derived(event.metadata?.result_content as string | undefined);
	const resultStatus = $derived(event.metadata?.result_status as string | undefined);

	// Parse input from metadata
	const input = $derived.by<Record<string, unknown>>(() => {
		const skipKeys = [
			'tool_name',
			'tool_id',
			'has_result',
			'result_content',
			'result_status',
			'result_timestamp',
			'result_parsed',
			'spawned_agent_id',
			'spawned_agent_slug',
			'is_spawn_task',
			'subagent_type'
		];

		const result: Record<string, unknown> = {};
		if (event.metadata) {
			for (const [key, value] of Object.entries(event.metadata)) {
				if (!skipKeys.includes(key) && value != null) {
					result[key] = value;
				}
			}
		}

		// Fallback: parse summary as file path or command
		if (Object.keys(result).length === 0 && event.summary) {
			if (toolName === 'Read' || toolName === 'Write') {
				result.file_path = event.summary;
			} else if (toolName === 'Bash' || toolName === 'Shell') {
				result.command = event.summary;
			} else {
				result.content = event.summary;
			}
		}

		return result;
	});

	// Parse plan markdown when ExitPlanMode detected
	$effect(() => {
		if (toolName === 'ExitPlanMode') {
			const raw = String(input.plan || input.content || '');
			const parsed = marked.parse(raw);
			if (parsed instanceof Promise) {
				parsed.then((html) => {
					renderedPlanHtml = DOMPurify.sanitize(html);
				});
			} else {
				renderedPlanHtml = DOMPurify.sanitize(parsed);
			}
		}
	});

	function hasValue(val: unknown): boolean {
		return val != null && val !== '';
	}

	async function copyToClipboard(text: string, section: string) {
		await navigator.clipboard.writeText(text);
		copiedSection = section;
		setTimeout(() => (copiedSection = null), 2000);
	}
</script>

<div class="border-t border-[var(--border)] pt-3 space-y-4 {className}">
	<!-- Input Section -->
	<div>
		<h4 class="text-[10px] font-medium text-[var(--text-muted)] uppercase tracking-wide mb-2">
			Input
		</h4>

		<!-- Read Tool -->
		{#if toolName === 'Read'}
			<div
				class="font-mono text-sm bg-[var(--bg-muted)] rounded-[var(--radius-md)] p-3 flex items-center justify-between gap-2"
			>
				<div title={String(input.file_path || '')}>
					<span class="text-[var(--event-prompt)]">Reading:</span>
					<span class="text-[var(--text-primary)] ml-1"
						>{formatDisplayPath(String(input.file_path || ''), projectPath)}</span
					>
					{#if input.offset != null && input.limit != null}
						<span class="text-[var(--text-muted)]">
							(lines {input.offset}-{Number(input.offset) + Number(input.limit)})
						</span>
					{/if}
				</div>
				{#if hasValue(input.file_path)}
					<button
						onclick={(e) => {
							e.stopPropagation();
							copyToClipboard(String(input.file_path), 'file_path');
						}}
						class="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors"
						title="Copy path"
					>
						{#if copiedSection === 'file_path'}
							<Check size={14} class="text-[var(--success)]" />
						{:else}
							<Copy size={14} />
						{/if}
					</button>
				{/if}
			</div>

			<!-- Write Tool -->
		{:else if toolName === 'Write'}
			<div class="space-y-2">
				<div
					class="font-mono text-sm bg-[var(--bg-muted)] rounded-[var(--radius-md)] p-3 flex items-center justify-between gap-2"
				>
					<div title={String(input.file_path || '')}>
						<span class="text-[var(--success)]">Creating:</span>
						<span class="text-[var(--text-primary)] ml-1"
							>{formatDisplayPath(String(input.file_path || ''), projectPath)}</span
						>
					</div>
					{#if hasValue(input.file_path)}
						<button
							onclick={(e) => {
								e.stopPropagation();
								copyToClipboard(String(input.file_path), 'file_path');
							}}
							class="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors"
							title="Copy path"
						>
							{#if copiedSection === 'file_path'}
								<Check size={14} class="text-[var(--success)]" />
							{:else}
								<Copy size={14} />
							{/if}
						</button>
					{/if}
				</div>
				{#if hasValue(input.content)}
					{@const content = String(input.content)}
					<div
						class="rounded-[var(--radius-md)] border border-[var(--border)] p-3 relative"
					>
						<div class="flex items-center justify-between gap-2 mb-2">
							<h5
								class="text-[10px] font-medium text-[var(--text-muted)] uppercase tracking-wide"
							>
								Content
							</h5>
							<button
								onclick={(e) => {
									e.stopPropagation();
									copyToClipboard(content, 'write_content');
								}}
								class="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors"
								title="Copy content"
							>
								{#if copiedSection === 'write_content'}
									<Check size={14} class="text-[var(--success)]" />
								{:else}
									<Copy size={14} />
								{/if}
							</button>
						</div>
						<pre
							class="font-mono text-xs whitespace-pre-wrap break-words text-[var(--text-secondary)]">{content}</pre>
					</div>
				{/if}
			</div>

			<!-- Edit/StrReplace Tool -->
		{:else if toolName === 'Edit' || toolName === 'StrReplace'}
			<div class="space-y-2">
				<div
					class="font-mono text-sm bg-[var(--bg-muted)] rounded-[var(--radius-md)] p-3 flex items-center justify-between gap-2"
				>
					<div title={String(input.file_path || '')}>
						<span class="text-[var(--event-thinking)]">Editing:</span>
						<span class="text-[var(--text-primary)] ml-1"
							>{formatDisplayPath(String(input.file_path || ''), projectPath)}</span
						>
					</div>
					{#if hasValue(input.file_path)}
						<button
							onclick={(e) => {
								e.stopPropagation();
								copyToClipboard(String(input.file_path), 'file_path');
							}}
							class="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors"
							title="Copy path"
						>
							{#if copiedSection === 'file_path'}
								<Check size={14} class="text-[var(--success)]" />
							{:else}
								<Copy size={14} />
							{/if}
						</button>
					{/if}
				</div>

				<!-- Original (old_string) -->
				{#if hasValue(input.old_string)}
					{@const content = String(input.old_string)}
					<div
						class="rounded-[var(--radius-md)] border border-red-500/20 bg-red-500/5 p-3 relative"
					>
						<div class="flex items-center justify-between gap-2 mb-2">
							<h5
								class="text-[10px] font-medium text-red-400 uppercase tracking-wide"
							>
								Original
							</h5>
							<button
								onclick={(e) => {
									e.stopPropagation();
									copyToClipboard(content, 'old_string');
								}}
								class="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors"
								title="Copy original"
							>
								{#if copiedSection === 'old_string'}
									<Check size={14} class="text-[var(--success)]" />
								{:else}
									<Copy size={14} />
								{/if}
							</button>
						</div>
						<pre
							class="font-mono text-xs whitespace-pre-wrap break-words text-red-300">{content}</pre>
					</div>
				{/if}

				<!-- Replacement (new_string) -->
				{#if hasValue(input.new_string)}
					{@const content = String(input.new_string)}
					<div
						class="rounded-[var(--radius-md)] border border-green-500/20 bg-green-500/5 p-3 relative"
					>
						<div class="flex items-center justify-between gap-2 mb-2">
							<h5
								class="text-[10px] font-medium text-green-400 uppercase tracking-wide"
							>
								Replacement
							</h5>
							<button
								onclick={(e) => {
									e.stopPropagation();
									copyToClipboard(content, 'new_string');
								}}
								class="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors"
								title="Copy replacement"
							>
								{#if copiedSection === 'new_string'}
									<Check size={14} class="text-[var(--success)]" />
								{:else}
									<Copy size={14} />
								{/if}
							</button>
						</div>
						<pre
							class="font-mono text-xs whitespace-pre-wrap break-words text-green-300">{content}</pre>
					</div>
				{/if}
			</div>

			<!-- Bash/Shell Tool -->
		{:else if toolName === 'Bash' || toolName === 'Shell'}
			<div
				class="font-mono text-sm bg-[var(--bg-muted)] rounded-[var(--radius-md)] p-3 flex items-center justify-between gap-2"
			>
				<pre class="text-[var(--event-tool)] overflow-x-auto flex-1">$ {input.command ||
						''}</pre>
				{#if hasValue(input.command)}
					<button
						onclick={(e) => {
							e.stopPropagation();
							copyToClipboard(String(input.command), 'command');
						}}
						class="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors shrink-0"
						title="Copy command"
					>
						{#if copiedSection === 'command'}
							<Check size={14} class="text-[var(--success)]" />
						{:else}
							<Copy size={14} />
						{/if}
					</button>
				{/if}
			</div>

			<!-- Glob Tool -->
		{:else if toolName === 'Glob'}
			<div class="font-mono text-sm bg-[var(--bg-muted)] rounded-[var(--radius-md)] p-3">
				<span class="text-[var(--event-subagent)]">Pattern:</span>
				<span class="text-[var(--text-primary)] ml-1">{input.pattern || ''}</span>
				{#if hasValue(input.path)}
					<span class="text-[var(--text-muted)]" title={String(input.path)}>
						in {formatDisplayPath(String(input.path), projectPath)}</span
					>
				{/if}
			</div>

			<!-- Grep Tool -->
		{:else if toolName === 'Grep'}
			<div
				class="font-mono text-sm bg-[var(--bg-muted)] rounded-[var(--radius-md)] p-3 space-y-1"
			>
				<div>
					<span class="text-[var(--event-subagent)]">Pattern:</span>
					<span class="text-[var(--text-primary)] ml-1">{input.pattern || ''}</span>
				</div>
				{#if hasValue(input.path)}
					<div title={String(input.path)}>
						<span class="text-[var(--text-muted)]">In:</span>
						<span class="text-[var(--text-primary)] ml-1"
							>{formatDisplayPath(String(input.path), projectPath)}</span
						>
					</div>
				{/if}
				{#if hasValue(input.include)}
					<div>
						<span class="text-[var(--text-muted)]">Include:</span>
						<span class="text-[var(--text-primary)] ml-1">{input.include}</span>
					</div>
				{/if}
			</div>

			<!-- Task Tool -->
		{:else if toolName === 'Task'}
			<div class="space-y-2">
				{#if hasValue(input.description)}
					<div
						class="font-mono text-sm bg-[var(--bg-muted)] rounded-[var(--radius-md)] p-3"
					>
						<span class="text-[var(--event-subagent)]">Task:</span>
						<span class="text-[var(--text-primary)] ml-1">{input.description}</span>
					</div>
				{/if}
				{#if hasValue(input.prompt)}
					{@const content = String(input.prompt)}
					<div
						class="rounded-[var(--radius-md)] border border-[var(--border)] p-3 relative"
					>
						<div class="flex items-center justify-between gap-2 mb-2">
							<h5
								class="text-[10px] font-medium text-[var(--text-muted)] uppercase tracking-wide"
							>
								Prompt
							</h5>
							<button
								onclick={(e) => {
									e.stopPropagation();
									copyToClipboard(content, 'task_prompt');
								}}
								class="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors"
								title="Copy prompt"
							>
								{#if copiedSection === 'task_prompt'}
									<Check size={14} class="text-[var(--success)]" />
								{:else}
									<Copy size={14} />
								{/if}
							</button>
						</div>
						<pre
							class="font-mono text-xs whitespace-pre-wrap break-words text-[var(--text-secondary)]">{content}</pre>
					</div>
				{/if}
			</div>

			<!-- ExitPlanMode Tool -->
		{:else if toolName === 'ExitPlanMode'}
			{@const planContent = String(input.plan || input.content || '')}
			<div class="space-y-0">
				<!-- Plan header bar -->
				<div
					class="flex items-center justify-between gap-3 rounded-t-[var(--radius-md)] bg-[var(--event-plan-subtle)] px-4 py-2.5 border border-[var(--event-plan)]/20"
				>
					<div class="flex items-center gap-2">
						<div
							class="flex h-6 w-6 items-center justify-center rounded bg-[var(--event-plan)]/20"
						>
							<svg
								class="h-3.5 w-3.5 text-[var(--event-plan)]"
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								stroke-width="2"
								stroke-linecap="round"
								stroke-linejoin="round"
							>
								<polygon points="3 6 9 3 15 6 21 3 21 18 15 21 9 18 3 21" />
								<line x1="9" y1="3" x2="9" y2="18" />
								<line x1="15" y1="6" x2="15" y2="21" />
							</svg>
						</div>
						<span
							class="text-xs font-semibold uppercase tracking-wider text-[var(--event-plan)]"
						>
							Plan Output
						</span>
					</div>
					<button
						onclick={(e) => {
							e.stopPropagation();
							copyToClipboard(planContent, 'plan');
						}}
						class="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors"
						title="Copy plan"
					>
						{#if copiedSection === 'plan'}
							<Check size={14} class="text-[var(--success)]" />
						{:else}
							<Copy size={14} />
						{/if}
					</button>
				</div>

				<!-- Plan content with rendered markdown -->
				<div
					class="rounded-b-[var(--radius-md)] border border-t-0 border-[var(--event-plan)]/10 bg-[var(--bg-muted)]/40 px-5 py-4"
				>
					<div class="markdown-preview text-sm leading-relaxed">
						{@html renderedPlanHtml}
					</div>
				</div>
			</div>

			<!-- WebSearch Tool -->
		{:else if toolName === 'WebSearch'}
			<div class="font-mono text-sm bg-[var(--bg-muted)] rounded-[var(--radius-md)] p-3">
				<span class="text-[var(--event-prompt)]">Search:</span>
				<span class="text-[var(--text-primary)] ml-1">{input.query || ''}</span>
			</div>

			<!-- WebFetch Tool -->
		{:else if toolName === 'WebFetch'}
			<div
				class="font-mono text-sm bg-[var(--bg-muted)] rounded-[var(--radius-md)] p-3 flex items-center justify-between gap-2"
			>
				<div class="overflow-hidden">
					<span class="text-[var(--event-prompt)]">Fetching:</span>
					<span class="text-[var(--text-primary)] ml-1 break-all">{input.url || ''}</span>
				</div>
				{#if hasValue(input.url)}
					<button
						onclick={(e) => {
							e.stopPropagation();
							copyToClipboard(String(input.url), 'url');
						}}
						class="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors shrink-0"
						title="Copy URL"
					>
						{#if copiedSection === 'url'}
							<Check size={14} class="text-[var(--success)]" />
						{:else}
							<Copy size={14} />
						{/if}
					</button>
				{/if}
			</div>

			<!-- Default: JSON display -->
		{:else}
			{@const content = JSON.stringify(input, null, 2)}
			<div class="rounded-[var(--radius-md)] border border-[var(--border)] p-3 relative">
				<div class="flex items-center justify-between gap-2 mb-2">
					<h5
						class="text-[10px] font-medium text-[var(--text-muted)] uppercase tracking-wide"
					>
						Parameters
					</h5>
					<button
						onclick={(e) => {
							e.stopPropagation();
							copyToClipboard(content, 'default_input');
						}}
						class="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors"
						title="Copy input"
					>
						{#if copiedSection === 'default_input'}
							<Check size={14} class="text-[var(--success)]" />
						{:else}
							<Copy size={14} />
						{/if}
					</button>
				</div>
				<pre
					class="font-mono text-xs whitespace-pre-wrap break-words text-[var(--text-secondary)]">{content}</pre>
			</div>
		{/if}
	</div>

	<!-- Result Section -->
	{#if hasResult && resultContent}
		{@const content =
			typeof resultContent === 'string'
				? resultContent
				: JSON.stringify(resultContent, null, 2)}
		{@const isError = resultStatus === 'error'}
		{@const maxLength = 1000}
		{@const truncated = content.length > maxLength}
		<div>
			<div class="flex items-center gap-2 mb-2">
				<h4
					class="text-[10px] font-medium text-[var(--text-muted)] uppercase tracking-wide"
				>
					Result
				</h4>
				<span
					class="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium
					{isError
						? 'bg-[var(--error-subtle)] text-[var(--error)]'
						: 'bg-[var(--success-subtle)] text-[var(--success)]'}"
				>
					{#if isError}
						<AlertCircle size={10} />
						error
					{:else}
						<CheckCircle2 size={10} />
						success
					{/if}
				</span>
			</div>
			<div
				class="relative rounded-[var(--radius-md)] border p-3
				{isError
					? 'bg-[var(--error-subtle)]/30 border-[var(--error)]/20'
					: 'bg-[var(--bg-muted)] border-[var(--border)]'}"
			>
				<pre
					class="font-mono text-xs whitespace-pre-wrap break-words text-[var(--text-secondary)]">{truncated
						? content.slice(0, maxLength) + '\n...'
						: content}</pre>
				{#if truncated}
					<div class="absolute bottom-2 right-2">
						<span
							class="text-xs text-[var(--text-muted)] bg-[var(--bg-base)]/80 px-2 py-1 rounded"
						>
							{Math.round(content.length / 1024)}KB total
						</span>
					</div>
				{/if}
				<button
					onclick={(e) => {
						e.stopPropagation();
						copyToClipboard(content, 'result');
					}}
					class="absolute top-2 right-2 p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors"
					title="Copy result"
				>
					{#if copiedSection === 'result'}
						<Check size={14} class="text-[var(--success)]" />
					{:else}
						<Copy size={14} />
					{/if}
				</button>
			</div>
		</div>
	{/if}
</div>
