<script lang="ts">
	import {
		Copy,
		Check,
		AlertCircle,
		CheckCircle2,
		PlusCircle,
		RefreshCw,
		List,
		ClipboardList,
		ArrowRight,
		User,
		GitBranch,
		Plug,
		FolderOpen,
		Trash2,
		Map as MapIcon,
		ToggleLeft,
		MessageSquare,
		Zap,
		Search
	} from 'lucide-svelte';
	import { marked } from 'marked';
	import { markdownCopyButtons } from '$lib/actions/markdownCopyButtons';
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
			'subagent_type',
			'task_subject'
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

	// Task tool detection
	const isTaskTool = $derived(
		toolName === 'TaskCreate' ||
			toolName === 'TaskUpdate' ||
			toolName === 'TaskList' ||
			toolName === 'TaskGet'
	);

	// Task status color/label helpers
	function getTaskStatusColor(status: string): string {
		switch (status) {
			case 'completed':
				return 'bg-emerald-500/15 text-emerald-500 border-emerald-500/30';
			case 'in_progress':
				return 'bg-amber-500/15 text-amber-500 border-amber-500/30';
			case 'pending':
				return 'bg-zinc-500/15 text-zinc-400 border-zinc-500/30';
			case 'deleted':
				return 'bg-red-500/15 text-red-400 border-red-500/30';
			default:
				return 'bg-zinc-500/15 text-zinc-400 border-zinc-500/30';
		}
	}

	function getTaskStatusIcon(
		status: string
	): typeof CheckCircle2 | typeof RefreshCw | typeof AlertCircle {
		switch (status) {
			case 'completed':
				return CheckCircle2;
			case 'in_progress':
				return RefreshCw;
			default:
				return AlertCircle;
		}
	}

	// AskUserQuestion parsing
	const isAskUserQuestion = $derived(toolName === 'AskUserQuestion');

	interface ParsedQuestion {
		question: string;
		header?: string;
		multiSelect?: boolean;
		options: Array<{ label: string; description?: string }>;
	}

	const parsedQuestions = $derived.by<ParsedQuestion[]>(() => {
		if (!isAskUserQuestion) return [];
		const questions = input.questions;
		if (!Array.isArray(questions)) return [];
		return questions as ParsedQuestion[];
	});

	// Extract user answers from result_content or metadata answers field
	const userAnswers = $derived.by<Map<string, string>>(() => {
		const answers = new Map<string, string>();
		if (!isAskUserQuestion) return answers;

		// Try structured answers from metadata
		if (input.answers && typeof input.answers === 'object') {
			for (const [q, a] of Object.entries(input.answers as Record<string, string>)) {
				answers.set(q, a);
			}
			return answers;
		}

		// Parse from result_content using robust matching
		// Format: "question text"="answer text"
		// Question text may contain escaped quotes (\') and special chars
		if (resultContent) {
			// Strategy: for each question, find its answer in result_content
			// by looking for the question text (fuzzy) followed by "="answer"
			for (const q of parsedQuestions) {
				// Take first 40 chars of question as anchor (enough to be unique)
				const anchor = q.question.slice(0, 40).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
				// Match: "...anchor..."="answer"
				const pattern = new RegExp(`"[^"]*?${anchor}[^"]*?"="([^"]*?)"`, 's');
				const match = resultContent.match(pattern);
				if (match) {
					answers.set(q.question, match[1].trim());
				}
			}

			// Fallback: if no matches found, try the simple pattern
			if (answers.size === 0) {
				const pattern = /"([^"]+)"="([^"]+)"/g;
				let match;
				while ((match = pattern.exec(resultContent)) !== null) {
					answers.set(match[1], match[2]);
				}
			}
		}
		return answers;
	});

	// Extract user notes from result_content
	const userNotes = $derived.by<Map<string, string>>(() => {
		const notes = new Map<string, string>();
		if (!isAskUserQuestion || !resultContent) return notes;

		// Try structured annotations from metadata
		if (input.annotations && typeof input.annotations === 'object') {
			for (const [q, ann] of Object.entries(
				input.annotations as Record<string, { notes?: string }>
			)) {
				if (ann?.notes) notes.set(q, ann.notes);
			}
			return notes;
		}

		// Parse "user notes: ..." from result_content
		const notesMatch = resultContent.match(/user notes:\s*(.+?)(?:\.|$)/i);
		if (notesMatch) {
			// Associate with the last question
			if (parsedQuestions.length > 0) {
				notes.set(parsedQuestions[parsedQuestions.length - 1].question, notesMatch[1].trim());
			}
		}
		return notes;
	});

	function isSelectedAnswer(questionText: string, optionLabel: string): boolean {
		const answer = userAnswers.get(questionText);
		if (!answer) return false;
		return answer.toLowerCase().trim() === optionLabel.toLowerCase().trim();
	}

	/** Check if the user typed a custom "Other" answer that doesn't match any predefined option */
	function getCustomAnswer(q: ParsedQuestion): string | null {
		const answer = userAnswers.get(q.question);
		if (!answer) return null;
		const matchesAny = q.options.some(
			(o) => o.label.toLowerCase().trim() === answer.toLowerCase().trim()
		);
		return matchesAny ? null : answer;
	}

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
					{@const lineCount = content.replace(/\n$/, '').split('\n').length || 1}
					<div
						class="rounded-[var(--radius-md)] border border-[var(--border)] p-3 relative"
					>
						<div class="flex items-center justify-between gap-2 mb-2">
							<div class="flex items-center gap-2">
								<h5
									class="text-[10px] font-medium text-[var(--text-muted)] uppercase tracking-wide"
								>
									Content
								</h5>
								<span class="text-[10px] text-[var(--text-muted)]/60 tabular-nums">
									{lineCount} line{lineCount === 1 ? '' : 's'}
								</span>
							</div>
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
						<div class="max-h-80 overflow-y-auto">
							<pre
								class="font-mono text-xs whitespace-pre-wrap break-words text-[var(--text-secondary)]">{content}</pre>
						</div>
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
		{:else if toolName === 'Task' || toolName === 'Agent'}
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
					<div class="markdown-preview text-sm leading-relaxed" use:markdownCopyButtons={renderedPlanHtml}>
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

			<!-- Task Tools: TaskCreate, TaskUpdate, TaskGet, TaskList -->
		{:else if isTaskTool}
			{#if toolName === 'TaskCreate'}
				{@const subject = String(input.subject || '')}
				{@const description = String(input.description || '')}
				{@const activeForm = String(input.activeForm || '')}
				<div
					class="rounded-[var(--radius-md)] border border-emerald-500/20 bg-emerald-500/5 overflow-hidden"
				>
					<!-- Header -->
					<div
						class="flex items-center gap-2.5 px-4 py-2.5 bg-emerald-500/10 border-b border-emerald-500/15"
					>
						<PlusCircle size={15} class="text-emerald-500 shrink-0" />
						<span
							class="text-xs font-semibold uppercase tracking-wider text-emerald-500"
						>
							New Task
						</span>
					</div>
					<div class="p-4 space-y-3">
						<!-- Subject -->
						{#if subject}
							<p class="text-sm font-medium text-[var(--text-primary)] leading-snug">
								{subject}
							</p>
						{/if}
						<!-- Description -->
						{#if description}
							<p
								class="text-xs text-[var(--text-secondary)] leading-relaxed border-l-2 border-emerald-500/30 pl-3"
							>
								{description}
							</p>
						{/if}
						<!-- Active form -->
						{#if activeForm}
							<div class="flex items-center gap-2 text-xs text-[var(--text-muted)]">
								<RefreshCw size={11} class="animate-spin" />
								<span class="italic">{activeForm}</span>
							</div>
						{/if}
					</div>
				</div>
			{:else if toolName === 'TaskUpdate'}
				{@const taskId = String(input.taskId || '')}
				{@const status = String(input.status || '')}
				{@const subject = String(input.subject || '')}
				{@const taskSubject = String(event.metadata?.task_subject || '')}
				{@const description = String(input.description || '')}
				{@const owner = String(input.owner || '')}
				{@const activeForm = String(input.activeForm || '')}
				{@const addBlocks = (input.addBlocks as string[]) || []}
				{@const addBlockedBy = (input.addBlockedBy as string[]) || []}
				{@const hasChanges =
					subject || description || owner || activeForm || addBlocks.length > 0 || addBlockedBy.length > 0}
				<div
					class="rounded-[var(--radius-md)] border border-sky-500/20 bg-sky-500/5 overflow-hidden"
				>
					<!-- Header -->
					<div
						class="flex items-center justify-between gap-2.5 px-4 py-2.5 bg-sky-500/10 border-b border-sky-500/15"
					>
						<div class="flex flex-col gap-0.5 min-w-0">
							<div class="flex items-center gap-2.5">
								<RefreshCw size={15} class="text-sky-500 shrink-0" />
								<span
									class="text-xs font-semibold uppercase tracking-wider text-sky-500"
								>
									Update Task
								</span>
								{#if taskId}
									<span
										class="font-mono text-[10px] rounded bg-sky-500/15 px-1.5 py-0.5 text-sky-400"
									>
										#{taskId}
									</span>
								{/if}
							</div>
							{#if subject || taskSubject}
								<span class="text-xs text-[var(--text-secondary)] pl-6 truncate">
									{subject || taskSubject}
								</span>
							{/if}
						</div>
						{#if status}
							{@const StatusIcon = getTaskStatusIcon(status)}
							<span
								class="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold shrink-0 {getTaskStatusColor(
									status
								)}"
							>
								<StatusIcon size={10} />
								{status.replace('_', ' ')}
							</span>
						{/if}
					</div>
					<!-- Changes -->
					{#if hasChanges}
						<div class="p-4 space-y-2">
							{#if subject}
								<div class="flex items-start gap-2">
									<span
										class="shrink-0 text-[10px] font-medium uppercase tracking-wide text-[var(--text-muted)] w-16"
									>
										Rename to
									</span>
									<span class="text-sm text-[var(--text-primary)]">{subject}</span>
								</div>
							{/if}
							{#if description}
								<div class="flex items-start gap-2">
									<span
										class="shrink-0 text-[10px] font-medium uppercase tracking-wide text-[var(--text-muted)] w-16"
									>
										Desc
									</span>
									<span
										class="text-xs text-[var(--text-secondary)] leading-relaxed"
										>{description}</span
									>
								</div>
							{/if}
							{#if owner}
								<div class="flex items-center gap-2">
									<span
										class="shrink-0 text-[10px] font-medium uppercase tracking-wide text-[var(--text-muted)] w-16"
									>
										Owner
									</span>
									<span
										class="inline-flex items-center gap-1 text-xs text-[var(--text-primary)]"
									>
										<User size={11} class="text-[var(--text-muted)]" />
										{owner}
									</span>
								</div>
							{/if}
							{#if activeForm}
								<div class="flex items-center gap-2">
									<span
										class="shrink-0 text-[10px] font-medium uppercase tracking-wide text-[var(--text-muted)] w-16"
									>
										Spinner
									</span>
									<span class="text-xs italic text-[var(--text-muted)]"
										>{activeForm}</span
									>
								</div>
							{/if}
							{#if addBlocks.length > 0 || addBlockedBy.length > 0}
								<div class="flex items-center gap-3 flex-wrap pt-1">
									{#if addBlocks.length > 0}
										<span
											class="inline-flex items-center gap-1 text-[10px] text-orange-400"
										>
											<GitBranch size={10} />
											blocks: {addBlocks.join(', ')}
										</span>
									{/if}
									{#if addBlockedBy.length > 0}
										<span
											class="inline-flex items-center gap-1 text-[10px] text-orange-400"
										>
											<ArrowRight size={10} />
											blocked by: {addBlockedBy.join(', ')}
										</span>
									{/if}
								</div>
							{/if}
						</div>
					{/if}
				</div>
			{:else if toolName === 'TaskGet'}
				{@const taskId = String(input.taskId || '')}
				<div
					class="font-mono text-sm bg-[var(--bg-muted)] rounded-[var(--radius-md)] p-3 flex items-center gap-2.5"
				>
					<ClipboardList size={15} class="text-violet-400 shrink-0" />
					<span class="text-violet-400">Get task</span>
					{#if taskId}
						<span
							class="font-mono text-[10px] rounded bg-violet-500/15 px-1.5 py-0.5 text-violet-300"
						>
							#{taskId}
						</span>
					{/if}
				</div>
			{:else if toolName === 'TaskList'}
				<div
					class="font-mono text-sm bg-[var(--bg-muted)] rounded-[var(--radius-md)] p-3 flex items-center gap-2.5"
				>
					<List size={15} class="text-zinc-400 shrink-0" />
					<span class="text-zinc-400">List all tasks</span>
				</div>
			{/if}

			<!-- CallMcpTool / mcp__ prefixed tools -->
		{:else if toolName === 'CallMcpTool' || toolName?.startsWith('mcp__')}
			{@const isDirect = toolName !== 'CallMcpTool'}
			{@const nameParts = isDirect ? (toolName ?? '').split('__') : []}
			{@const server = String(input.server || (isDirect && nameParts.length >= 3 ? nameParts.slice(1, -1).join('__') : '') || '')}
			{@const mcpTool = String(input.tool || input.toolName || (isDirect && nameParts.length >= 2 ? nameParts[nameParts.length - 1] : '') || '')}
			{@const mcpArgs = (input.args && typeof input.args === 'object' ? input.args : isDirect ? input : null) as Record<string, unknown> | null}
			<div
				class="rounded-[var(--radius-md)] border border-purple-500/20 bg-purple-500/5 overflow-hidden"
			>
				<div
					class="flex items-center gap-2.5 px-4 py-2.5 bg-purple-500/10 border-b border-purple-500/15"
				>
					<Plug size={15} class="text-purple-400 shrink-0" />
					<span class="text-xs font-semibold uppercase tracking-wider text-purple-400">
						MCP Tool
					</span>
					{#if input.is_direct_mcp}
						<span class="text-[10px] rounded bg-purple-500/10 px-1.5 py-0.5 text-purple-400/60">
							direct
						</span>
					{/if}
				</div>
				<div class="px-4 py-3 flex items-center gap-3">
					{#if server}
						<span
							class="font-mono text-[10px] rounded-full bg-purple-500/15 px-2.5 py-1 text-purple-300 border border-purple-500/20"
						>
							{server}
						</span>
					{/if}
					{#if server && mcpTool}
						<ArrowRight size={12} class="text-purple-500/40" />
					{/if}
					{#if mcpTool}
						<span class="font-mono text-sm text-[var(--text-primary)]">{mcpTool}</span>
					{/if}
				</div>
				<!-- MCP tool arguments -->
				{#if mcpArgs && Object.keys(mcpArgs).length > 0}
					{@const argKeys = Object.keys(mcpArgs).filter((k) => mcpArgs[k] != null && k !== 'is_direct_mcp')}
					{#if argKeys.length > 0}
						<div class="px-4 pb-3 border-t border-purple-500/10">
							<div class="space-y-1.5 pt-2.5">
								{#each argKeys.slice(0, 8) as key}
									<div class="flex items-start gap-2">
										<span
											class="shrink-0 font-mono text-[10px] text-purple-400/60 min-w-[60px]"
										>
											{key}
										</span>
										<span
											class="font-mono text-xs text-[var(--text-secondary)] break-all"
										>
											{#if typeof mcpArgs[key] === 'string'}
												{String(mcpArgs[key]).length > 150
													? String(mcpArgs[key]).slice(0, 150) + '...'
													: mcpArgs[key]}
											{:else}
												{JSON.stringify(mcpArgs[key]).length > 150
													? JSON.stringify(mcpArgs[key]).slice(0, 150) + '...'
													: JSON.stringify(mcpArgs[key])}
											{/if}
										</span>
									</div>
								{/each}
								{#if argKeys.length > 8}
									<span class="text-[10px] text-[var(--text-muted)]">
										+{argKeys.length - 8} more params
									</span>
								{/if}
							</div>
						</div>
					{/if}
				{/if}
			</div>

			<!-- LS (List Directory) -->
		{:else if toolName === 'LS'}
			<div
				class="font-mono text-sm bg-[var(--bg-muted)] rounded-[var(--radius-md)] p-3 flex items-center justify-between gap-2"
			>
				<div class="flex items-center gap-2" title={String(input.path || '')}>
					<FolderOpen size={15} class="text-[var(--event-tool)] shrink-0" />
					<span class="text-[var(--event-tool)]">Listing:</span>
					<span class="text-[var(--text-primary)]">
						{formatDisplayPath(String(input.path || '.'), projectPath)}
					</span>
				</div>
			</div>

			<!-- Delete -->
		{:else if toolName === 'Delete'}
			<div
				class="font-mono text-sm bg-red-500/5 border border-red-500/20 rounded-[var(--radius-md)] p-3 flex items-center justify-between gap-2"
			>
				<div class="flex items-center gap-2" title={String(input.file_path || input.path || '')}>
					<Trash2 size={15} class="text-red-400 shrink-0" />
					<span class="text-red-400">Deleting:</span>
					<span class="text-[var(--text-primary)]">
						{formatDisplayPath(String(input.file_path || input.path || ''), projectPath)}
					</span>
				</div>
			</div>

			<!-- EnterPlanMode -->
		{:else if toolName === 'EnterPlanMode'}
			<div
				class="font-mono text-sm bg-[var(--event-plan-subtle)] border border-[var(--event-plan)]/20 rounded-[var(--radius-md)] p-3 flex items-center gap-2.5"
			>
				<MapIcon size={15} class="text-[var(--event-plan)] shrink-0" />
				<span class="text-[var(--event-plan)] font-semibold">Entering plan mode</span>
			</div>

			<!-- SwitchMode -->
		{:else if toolName === 'SwitchMode'}
			<div
				class="font-mono text-sm bg-[var(--bg-muted)] rounded-[var(--radius-md)] p-3 flex items-center gap-2.5"
			>
				<ToggleLeft size={15} class="text-[var(--event-thinking)] shrink-0" />
				<span class="text-[var(--event-thinking)]">Switch to</span>
				{#if input.target_mode}
					<span
						class="rounded bg-[var(--event-thinking)]/15 px-2 py-0.5 text-xs font-medium text-[var(--text-primary)]"
					>
						{input.target_mode}
					</span>
				{/if}
			</div>

			<!-- SendMessage -->
		{:else if toolName === 'SendMessage'}
			{@const recipient = String(input.recipient || input.target_agent_id || '')}
			{@const msgType = String(input.type || 'message')}
			{@const content = String(input.content || '')}
			{@const summary = String(input.summary || '')}
			<div
				class="rounded-[var(--radius-md)] border border-indigo-500/20 bg-indigo-500/5 overflow-hidden"
			>
				<div
					class="flex items-center justify-between gap-2.5 px-4 py-2.5 bg-indigo-500/10 border-b border-indigo-500/15"
				>
					<div class="flex items-center gap-2.5">
						<MessageSquare size={15} class="text-indigo-400 shrink-0" />
						<span class="text-xs font-semibold uppercase tracking-wider text-indigo-400">
							{msgType === 'broadcast' ? 'Broadcast' : msgType === 'shutdown_request' ? 'Shutdown Request' : 'Message'}
						</span>
					</div>
					{#if recipient}
						<span
							class="inline-flex items-center gap-1 font-mono text-[10px] rounded-full bg-indigo-500/15 px-2 py-0.5 text-indigo-300"
						>
							<ArrowRight size={10} />
							{recipient}
						</span>
					{/if}
				</div>
				{#if content}
					<div class="px-4 py-3">
						{#if summary}
							<p class="text-[10px] text-indigo-400/60 uppercase tracking-wide mb-1">
								{summary}
							</p>
						{/if}
						<p class="text-xs text-[var(--text-secondary)] leading-relaxed">
							{content.length > 200 ? content.slice(0, 200) + '...' : content}
						</p>
					</div>
				{/if}
			</div>

			<!-- Skill invocation -->
		{:else if toolName === 'Skill'}
			{@const skillName = String(input.skill || '')}
			{@const args = String(input.args || '')}
			<div
				class="font-mono text-sm bg-[var(--accent)]/5 border border-[var(--accent)]/20 rounded-[var(--radius-md)] p-3 flex items-center gap-2.5"
			>
				<Zap size={15} class="text-[var(--accent)] shrink-0" />
				<span class="text-[var(--accent)]">/{skillName}</span>
				{#if args}
					<span class="text-[var(--text-muted)] text-xs">{args}</span>
				{/if}
			</div>

			<!-- ToolSearch -->
		{:else if toolName === 'ToolSearch'}
			{@const query = String(input.query || '')}
			<div
				class="font-mono text-sm bg-[var(--bg-muted)] rounded-[var(--radius-md)] p-3 flex items-center gap-2.5"
			>
				<Search size={15} class="text-[var(--text-muted)] shrink-0" />
				<span class="text-[var(--text-muted)]">Searching tools:</span>
				<span class="text-[var(--text-primary)]">{query}</span>
			</div>

			<!-- SemanticSearch -->
		{:else if toolName === 'SemanticSearch'}
			<div
				class="font-mono text-sm bg-[var(--bg-muted)] rounded-[var(--radius-md)] p-3 flex items-center gap-2.5"
			>
				<Search size={15} class="text-[var(--event-subagent)] shrink-0" />
				<span class="text-[var(--event-subagent)]">Semantic search:</span>
				<span class="text-[var(--text-primary)]">{input.query || ''}</span>
			</div>

			<!-- AskUserQuestion: Formatted questions with options -->
		{:else if isAskUserQuestion && parsedQuestions.length > 0}
			<div class="space-y-4">
				{#each parsedQuestions as q, qIndex}
					<div class="rounded-[var(--radius-md)] border border-sky-500/20 bg-sky-500/5 p-4">
						<!-- Question header -->
						<div class="flex items-start gap-3 mb-3">
							<div
								class="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-sky-500/20 text-sky-500 text-xs font-bold mt-0.5"
							>
								{qIndex + 1}
							</div>
							<div class="flex-1 min-w-0">
								{#if q.header}
									<span
										class="inline-block rounded-full bg-sky-500/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-sky-500 mb-1.5"
									>
										{q.header}
									</span>
								{/if}
								<p class="text-sm font-medium text-[var(--text-primary)] leading-snug">
									{q.question}
								</p>
								{#if q.multiSelect}
									<span
										class="inline-block mt-1 text-[10px] text-[var(--text-muted)] italic"
									>
										Multiple selections allowed
									</span>
								{/if}
							</div>
						</div>

						<!-- Options -->
						<div class="ml-9 space-y-1.5">
							{#each q.options as option}
								{@const isSelected = isSelectedAnswer(q.question, option.label)}
								<div
									class="
										flex items-start gap-2.5 rounded-[var(--radius-md)] border px-3 py-2.5
										transition-all duration-150
										{isSelected
										? 'border-emerald-500/40 bg-emerald-500/10 shadow-sm shadow-emerald-500/5'
										: 'border-[var(--border)] bg-[var(--bg-base)]'}
									"
								>
									<!-- Selection indicator -->
									<div
										class="
											mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2
											transition-colors
											{isSelected
											? 'border-emerald-500 bg-emerald-500'
											: 'border-[var(--text-muted)]/30'}
										"
									>
										{#if isSelected}
											<svg
												class="h-2.5 w-2.5 text-white"
												viewBox="0 0 24 24"
												fill="none"
												stroke="currentColor"
												stroke-width="3"
												stroke-linecap="round"
												stroke-linejoin="round"
											>
												<polyline points="20 6 9 17 4 12" />
											</svg>
										{/if}
									</div>

									<div class="flex-1 min-w-0">
										<span
											class="
												text-sm font-medium
												{isSelected
												? 'text-emerald-600 dark:text-emerald-400'
												: 'text-[var(--text-primary)]'}
											"
										>
											{option.label}
										</span>
										{#if option.description}
											<p
												class="
													mt-0.5 text-xs leading-relaxed
													{isSelected
													? 'text-emerald-600/70 dark:text-emerald-400/70'
													: 'text-[var(--text-muted)]'}
												"
											>
												{option.description}
											</p>
										{/if}
									</div>

									{#if isSelected}
										<span
											class="shrink-0 rounded-full bg-emerald-500/20 px-2 py-0.5 text-[10px] font-semibold text-emerald-600 dark:text-emerald-400"
										>
											Selected
										</span>
									{/if}
								</div>
							{/each}

							<!-- Custom "Other" answer (doesn't match any predefined option) -->
							{#if getCustomAnswer(q)}
								<div
									class="flex items-start gap-2.5 rounded-[var(--radius-md)] border border-emerald-500/40 bg-emerald-500/10 shadow-sm shadow-emerald-500/5 px-3 py-2.5"
								>
									<div
										class="mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2 border-emerald-500 bg-emerald-500"
									>
										<svg
											class="h-2.5 w-2.5 text-white"
											viewBox="0 0 24 24"
											fill="none"
											stroke="currentColor"
											stroke-width="3"
											stroke-linecap="round"
											stroke-linejoin="round"
										>
											<polyline points="20 6 9 17 4 12" />
										</svg>
									</div>
									<div class="flex-1 min-w-0">
										<span
											class="text-[10px] font-semibold uppercase tracking-wider text-emerald-600 dark:text-emerald-400"
										>
											Custom Answer
										</span>
										<p
											class="mt-0.5 text-sm font-medium text-emerald-600 dark:text-emerald-400"
										>
											{getCustomAnswer(q)}
										</p>
									</div>
									<span
										class="shrink-0 rounded-full bg-emerald-500/20 px-2 py-0.5 text-[10px] font-semibold text-emerald-600 dark:text-emerald-400"
									>
										Selected
									</span>
								</div>
							{/if}

							<!-- User notes for this question (hide if same as custom answer) -->
							{#if userNotes.get(q.question) && userNotes.get(q.question) !== getCustomAnswer(q)}
								<div
									class="mt-2 rounded-[var(--radius-md)] border border-amber-500/20 bg-amber-500/5 px-3 py-2"
								>
									<span
										class="text-[10px] font-semibold uppercase tracking-wider text-amber-600 dark:text-amber-400"
									>
										User Note
									</span>
									<p class="mt-0.5 text-xs text-[var(--text-secondary)]">
										{userNotes.get(q.question)}
									</p>
								</div>
							{/if}
						</div>
					</div>
				{/each}
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
	{#if isAskUserQuestion && hasResult}
		<!-- AskUserQuestion: show a compact answered status instead of raw result -->
		<div>
			<div class="flex items-center gap-2">
				<h4
					class="text-[10px] font-medium text-[var(--text-muted)] uppercase tracking-wide"
				>
					Result
				</h4>
				<span
					class="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-600 dark:text-emerald-400"
				>
					<CheckCircle2 size={10} />
					Answered
				</span>
			</div>
		</div>
	{:else if hasResult && resultContent}
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
