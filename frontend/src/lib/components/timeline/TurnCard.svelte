<script lang="ts">
	import { marked } from 'marked';
	import DOMPurify from 'isomorphic-dompurify';
	import { markdownCopyButtons } from '$lib/actions/markdownCopyButtons';
	import type { TimelineEvent } from '$lib/api-types';
	import type { TurnGroup } from '$lib/utils/groupIntoTurns';

	interface Props {
		turn: TurnGroup;
		density: 'compact' | 'normal' | 'expanded';
		turnIndex: number;
		onOpenPopup: (event: TimelineEvent) => void;
		projectPath?: string | null;
		projectEncoded?: string;
		sessionSlug?: string;
		sessionUuid?: string;
		searchQuery?: string;
	}

	let {
		turn,
		density,
		turnIndex,
		onOpenPopup,
		projectPath = null,
		projectEncoded,
		sessionSlug,
		sessionUuid,
		searchQuery = ''
	}: Props = $props();

	let workExpanded = $state(false);
	let responseExpanded = $state(false);

	$effect(() => {
		const d = density;
		workExpanded = d === 'expanded';
		// The response is the payload of a turn — open unless the user asks for compact
		responseExpanded = d !== 'compact';
	});

	// Prompt text
	const promptText = $derived(
		(turn.prompt.metadata?.full_content as string | undefined) ??
			(turn.prompt.metadata?.full_text as string | undefined) ??
			turn.prompt.summary ??
			turn.prompt.title ??
			''
	);

	// Highlight search query in text
	function highlight(text: string): string {
		if (!searchQuery || !text) return text;
		const escaped = searchQuery.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
		return text.replace(new RegExp(escaped, 'gi'), (m) => `<mark>${m}</mark>`);
	}

	const highlightedPrompt = $derived(highlight(promptText));

	// Turn offset from session start
	const turnOffsetStr = $derived.by(() => {
		const ms = turn.turnOffsetMs;
		if (ms <= 0) return '+0:00';
		const h = Math.floor(ms / 3600000);
		const m = Math.floor((ms % 3600000) / 60000);
		const s = Math.floor((ms % 60000) / 1000);
		if (h > 0) return `+${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
		return `+${m}m ${String(s).padStart(2, '0')}s`;
	});

	// Elapsed time for this turn
	const elapsedStr = $derived.by(() => {
		const ms = turn.elapsedMs;
		if (ms <= 0) return '';
		const min = Math.floor(ms / 60000);
		const sec = Math.floor((ms % 60000) / 1000);
		return min > 0 ? `+${min}m ${sec}s` : `+${sec}s`;
	});

	// Clock time for prompt
	const clockStr = $derived.by(() => {
		try {
			const d = new Date(turn.prompt.timestamp);
			return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
		} catch {
			return '';
		}
	});

	// Response content
	const responseRaw = $derived(
		(turn.response?.metadata?.full_content as string | undefined) ??
			(turn.response?.metadata?.full_text as string | undefined) ??
			turn.response?.summary ??
			''
	);

	let renderedResponse = $state('');
	$effect(() => {
		const content = responseRaw;
		if (!content || density === 'compact') { renderedResponse = ''; return; }
		const result = marked.parse(content);
		if (result instanceof Promise) {
			result.then((html) => { renderedResponse = DOMPurify.sanitize(html); });
		} else {
			renderedResponse = DOMPurify.sanitize(result);
		}
	});

	const responseLineCount = $derived(responseRaw.split('\n').length);
	const showExpander = $derived(responseRaw.length > 280 || responseLineCount > 5);

	let isCopied = $state(false);
	function copyResponse() {
		navigator.clipboard.writeText(responseRaw);
		isCopied = true;
		setTimeout(() => (isCopied = false), 2000);
	}

	// Image attachments
	const imageAttachments = $derived(
		(turn.prompt.metadata?.image_attachments as Array<{ media_type: string; data: string }> | undefined) ?? []
	);

	// ── Event row helpers ──────────────────────────────────────────────

	function getRowBadge(ev: TimelineEvent): string {
		if (ev.event_type === 'thinking') return 'Think';
		if (ev.event_type === 'todo_update') return 'Todo';
		if (ev.event_type === 'skill_invocation') return 'Skill';
		if (ev.event_type === 'subagent_spawn') return '⊕ Agent';
		if (ev.event_type === 'command_invocation' || ev.event_type === 'builtin_command') {
			const name = (ev.metadata?.command_name as string | undefined) ?? ev.title ?? 'Cmd';
			return name.replace(/^\//, '');
		}
		if (ev.event_type === 'tool_call') {
			if (ev.metadata?.spawned_agent_id) return '⊕ Agent';
			const name = (ev.metadata?.tool_name as string | undefined) ?? '';
			if (name.startsWith('mcp__')) return name.split('__').slice(0, 2).join('__');
			return name || 'Tool';
		}
		return ev.event_type;
	}

	function getRowPath(ev: TimelineEvent): string {
		if (ev.event_type === 'thinking') {
			const tokens = ev.metadata?.thinking_tokens as number | undefined;
			if (tokens) return `● stored · ${tokens.toLocaleString()} tokens`;
			const full = ev.metadata?.full_thinking as string | undefined;
			if (full) return `● stored · ${full.length} chars`;
			return '○ not recorded';
		}
		if (ev.event_type === 'todo_update') {
			const todos = ev.metadata?.todos as unknown[] | undefined;
			const action = ev.metadata?.action as string | undefined;
			const prefix = action ? `${action} · ` : '';
			return todos
				? `${prefix}${todos.length} task${todos.length !== 1 ? 's' : ''}`
				: (ev.summary ?? '');
		}
		if (ev.event_type === 'skill_invocation') {
			return ev.title?.replace(/^Skill:\s*\/?/, '') ?? ev.summary ?? '';
		}
		if (ev.event_type === 'subagent_spawn' || ev.metadata?.spawned_agent_id) {
			const agentType = (ev.metadata?.subagent_type as string | undefined) ?? '';
			const prompt = ev.summary ?? '';
			const short = prompt.slice(0, 60) + (prompt.length > 60 ? '...' : '');
			return agentType ? `${agentType} · "${short}"` : `"${short}"`;
		}
		if (ev.event_type === 'command_invocation' || ev.event_type === 'builtin_command') {
			return ev.summary ?? ev.title ?? '';
		}
		// For tool_call: strip leading "ToolName: " from title
		const title = ev.title ?? ev.summary ?? '';
		// Strip project path prefix for cleaner display
		if (projectPath) {
			const stripped = title.replace(projectPath.replace(/\/$/, '') + '/', '');
			if (stripped !== title) return stripped;
		}
		return title.replace(/^[A-Za-z]+:\s*/, '');
	}

	function getDiffStat(ev: TimelineEvent): string | null {
		const name = ev.metadata?.tool_name as string | undefined;
		if (!name) return null;
		if (name === 'MultiEdit') {
			const count = ev.metadata?.count as number | undefined;
			return count ? `${count} hunks` : null;
		}
		if (name === 'Edit' || name === 'StrReplace') {
			const oldStr = ev.metadata?.old_string as string | undefined;
			const newStr = ev.metadata?.new_string as string | undefined;
			if (!oldStr && !newStr) return null;
			const removed = (oldStr ?? '').split('\n').length;
			const added = (newStr ?? '').split('\n').length;
			return `+${added} −${removed}`;
		}
		return null;
	}

	function getExitCode(ev: TimelineEvent): { label: string; isError: boolean } | null {
		const name = ev.metadata?.tool_name as string | undefined;
		if (name !== 'Bash' && name !== 'Shell') return null;
		const isErr =
			ev.metadata?.result_status === 'error' ||
			(ev.metadata?.is_error as boolean | undefined) === true;
		return { label: isErr ? 'exit 1' : 'exit 0', isError: !!isErr };
	}

	function getMatchCount(ev: TimelineEvent): string | null {
		const name = ev.metadata?.tool_name as string | undefined;
		if (name !== 'Grep' && name !== 'Glob') return null;
		const count = ev.metadata?.count as number | undefined;
		if (count !== undefined) {
			return `${count} ${name === 'Grep' ? 'match' : 'file'}${count !== 1 ? 'es' : ''}`;
		}
		return null;
	}

	function getRowOffset(ev: TimelineEvent): string {
		const ms = Math.max(
			0,
			new Date(ev.timestamp).getTime() - new Date(turn.prompt.timestamp).getTime()
		);
		const h = Math.floor(ms / 3600000);
		const m = Math.floor((ms % 3600000) / 60000);
		const s = Math.floor((ms % 60000) / 1000);
		if (h > 0) return `+${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
		return `+0:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
	}

	function isAgentEv(ev: TimelineEvent) {
		return ev.event_type === 'subagent_spawn' || !!ev.metadata?.spawned_agent_id;
	}
	function isThinkEv(ev: TimelineEvent) {
		return ev.event_type === 'thinking';
	}
	function isErrEv(ev: TimelineEvent) {
		return (
			ev.metadata?.result_status === 'error' ||
			(ev.metadata?.is_error as boolean | undefined) === true
		);
	}

	// Skill variant: prompt is a skill invocation
	const isSkillPrompt = $derived(
		turn.prompt.event_type === 'skill_invocation' ||
			(turn.prompt.metadata?.command_name as string | undefined) !== undefined
	);
</script>

<div
	class="border border-[var(--border)] rounded-sm overflow-hidden mb-2"
	data-turn-index={turnIndex}
>
	<!-- ① PROMPT ZONE -->
	<div
		class="flex items-start gap-2 px-3 py-2.5
			{isSkillPrompt
				? 'border-l-[3px] border-dashed border-[var(--border)]'
				: 'border-l-[3px] border-[var(--accent)]'}
			{density !== 'compact' && (turn.workEvents.length > 0 || turn.response || turn.isLive)
				? 'border-b border-[var(--border)]/40'
				: ''}"
		data-event-type="prompt"
	>
		<div class="flex-1 min-w-0">
			<p
				class="text-sm leading-relaxed font-sans max-w-[72ch] whitespace-pre-wrap text-[var(--text-primary)]
					{density === 'compact' ? 'truncate whitespace-nowrap' : ''}"
			>
				{#if searchQuery && promptText.toLowerCase().includes(searchQuery.toLowerCase())}
					{@html highlightedPrompt}
				{:else}
					{promptText}
				{/if}
			</p>
			{#if imageAttachments.length > 0 && density !== 'compact'}
				<div class="mt-1.5 flex gap-1.5 flex-wrap">
					<span
						class="inline-flex items-center h-[18px] px-1.5 border border-[var(--border)] rounded-sm
						text-[9px] font-mono text-[var(--text-muted)] bg-[var(--bg-subtle)]"
					>
						⊕ {imageAttachments.length} image{imageAttachments.length !== 1 ? 's' : ''}
					</span>
				</div>
			{/if}
		</div>
		<div class="text-right text-[10px] font-mono shrink-0 pl-3 select-none leading-snug">
			{#if density === 'compact'}
				<span class="text-[var(--text-faint)] opacity-70">T{turn.turnNumber}</span>
				{#if turn.hasErrors}<span class="text-[var(--error)] ml-1">!</span>{/if}
				{#if elapsedStr}<span class="text-[var(--text-faint)] ml-1">· {elapsedStr.replace('+', '')}</span>{/if}
			{:else}
				<span class="text-[var(--text-muted)]">Turn {turn.turnNumber}</span>
				{#if clockStr}<span class="text-[var(--text-faint)]"> · {clockStr}</span>{/if}
				<br />
				<span class="text-[var(--text-faint)] opacity-60">{turnOffsetStr}</span>
			{/if}
		</div>
	</div>

	<!-- ② WORK ZONE -->
	{#if density !== 'compact' && turn.workEvents.length > 0}
		<div class="bg-[var(--bg-subtle)] px-3 py-2 border-b border-[var(--border)]/40">
			<!-- Header: toggle + chips + elapsed -->
			<div class="flex items-center gap-1.5 flex-wrap min-h-[24px]">
				<button
					type="button"
					onclick={() => (workExpanded = !workExpanded)}
					class="w-[16px] h-[16px] border border-[var(--border)] bg-[var(--bg-base)] rounded-sm
						flex items-center justify-center text-[8px] font-mono text-[var(--text-muted)]
						hover:border-[var(--accent)] hover:text-[var(--accent)] transition-colors shrink-0"
					aria-label={workExpanded ? 'Collapse work' : 'Expand work'}
				>
					{workExpanded ? '▼' : '▶'}
				</button>

				{#each turn.toolChips as chip}
					<span
						class="inline-flex items-center h-[18px] px-1.5 rounded-sm text-[9px] font-mono whitespace-nowrap shrink-0
							{chip.isAgent ? 'border-[1.5px]' : 'border'}
							{chip.hasError
								? 'border-dashed border-[var(--error)]/50 text-[var(--error)]'
								: chip.isAgent
									? 'border-[var(--text-muted)] text-[var(--text-primary)]'
									: chip.isThinking
										? 'border-[var(--border)]/60 text-[var(--text-faint)]'
										: 'border-[var(--border)] text-[var(--text-muted)]'}
							bg-[var(--bg-base)]"
					>
						{chip.label}{#if chip.count > 1}<span class="opacity-50 ml-0.5">×{chip.count}</span>{/if}{#if chip.hasError}<span class="ml-0.5">!</span>{/if}
					</span>
				{/each}

				<span
					class="ml-auto text-[10px] font-mono shrink-0
						{turn.hasErrors ? 'text-[var(--error)]' : 'text-[var(--text-faint)]'}"
				>
					{#if turn.isLive}
						<span class="text-[var(--text-primary)]">running...</span>
					{:else if turn.hasErrors}
						! {turn.errorCount} error{turn.errorCount !== 1 ? 's' : ''} · {elapsedStr}
					{:else if elapsedStr}
						{elapsedStr}
					{/if}
				</span>
			</div>

			<!-- Expanded event rows -->
			{#if workExpanded}
				<div class="mt-2 flex flex-col gap-[2px]">
					{#each turn.workEvents as ev}
						{@const badge = getRowBadge(ev)}
						{@const path = getRowPath(ev)}
						{@const diffStat = getDiffStat(ev)}
						{@const exitCode = getExitCode(ev)}
						{@const matchCount = getMatchCount(ev)}
						{@const offset = getRowOffset(ev)}
						{@const isAgent = isAgentEv(ev)}
						{@const isThink = isThinkEv(ev)}
						{@const isErr = isErrEv(ev)}
						<!-- svelte-ignore a11y_click_events_have_key_events a11y_no_static_element_interactions -->
						<div
							class="flex items-center gap-1.5 px-2 py-1 border rounded-sm cursor-pointer
								transition-colors text-[10px] font-mono
								{isThink
									? 'bg-[var(--bg-subtle)] border-[var(--border)]/40'
									: 'bg-[var(--bg-base)] border-[var(--border)]'}
								{isErr ? 'border-[var(--error)]/30' : ''}
								hover:bg-[var(--bg-subtle)]"
							onclick={() => onOpenPopup(ev)}
							role="button"
							tabindex="0"
							onkeydown={(e) => {
								if (e.key === 'Enter') onOpenPopup(ev);
							}}
						>
							<!-- Badge -->
							<span
								class="px-1.5 py-[1px] border rounded-sm shrink-0 text-[9px] whitespace-nowrap
									{isAgent
										? 'bg-[var(--text-primary)] border-[var(--text-primary)] text-[var(--bg-base)]'
										: isThink
											? 'border-[var(--border)]/60 bg-transparent text-[var(--text-faint)]'
											: isErr
												? 'border-[var(--error)]/40 bg-[var(--error)]/5 text-[var(--error)]'
												: 'border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text-primary)]'}"
							>
								{badge}
							</span>

							<!-- Path / content -->
							<span
								class="flex-1 min-w-0 overflow-hidden text-ellipsis whitespace-nowrap
									{isThink
										? 'italic text-[var(--text-faint)]'
										: isErr
											? 'text-[var(--text-muted)]'
											: 'text-[var(--text-muted)]'}"
							>
								{path}
							</span>

							<!-- Diff stat | exit code | match count -->
							{#if diffStat}
								<span
									class="px-1.5 py-[1px] border border-[var(--border)] rounded-sm bg-[var(--bg-subtle)] text-[var(--text-muted)] shrink-0"
								>
									{diffStat}
								</span>
							{:else if exitCode}
								<span
									class="px-1.5 py-[1px] rounded-sm shrink-0
										{exitCode.isError
											? 'bg-[var(--text-primary)] text-[var(--bg-base)]'
											: 'border border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text-muted)]'}"
								>
									{exitCode.label}
								</span>
							{:else if matchCount}
								<span class="text-[var(--text-faint)] shrink-0">{matchCount}</span>
							{/if}

							<!-- Offset timestamp -->
							<span class="text-[var(--text-faint)] shrink-0 ml-0.5 opacity-70">{offset}</span>
						</div>
					{/each}
				</div>
			{/if}
		</div>
	{/if}

	<!-- ③ RESPONSE ZONE -->
	{#if density !== 'compact' && turn.response && renderedResponse}
		<div class="px-3 py-2.5 bg-[var(--bg-base)]">
			<div
				class="markdown-preview text-[15px] max-w-[72ch] text-[var(--text-secondary)] leading-relaxed transition-all
					{!responseExpanded ? 'overflow-hidden' : ''}"
				style={!responseExpanded ? 'max-height: 6rem;' : ''}
				use:markdownCopyButtons={responseExpanded ? renderedResponse : ''}
			>
				{@html renderedResponse}
			</div>

			<!-- Footer: line count + show more + copy + open -->
			<div
				class="flex items-center gap-2 mt-2 pt-1.5 border-t border-[var(--border)]/30
					text-[10px] font-mono text-[var(--text-faint)]"
			>
				{#if showExpander}
					<span>{responseLineCount} lines</span>
					<button
						class="px-1.5 py-[1px] border border-[var(--border)] rounded-sm bg-[var(--bg-subtle)]
							text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
						onclick={() => (responseExpanded = !responseExpanded)}
					>
						{responseExpanded ? 'show less' : 'show more'}
					</button>
				{/if}

				<div class="ml-auto flex gap-1.5">
					<button
						class="px-1.5 py-[1px] border border-[var(--border)] rounded-sm bg-[var(--bg-subtle)]
							text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
						onclick={copyResponse}
					>
						{isCopied ? '✓' : 'copy'}
					</button>
					<button
						class="px-1.5 py-[1px] border border-[var(--border)] rounded-sm bg-[var(--bg-subtle)]
							text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
						onclick={() => onOpenPopup(turn.response!)}
						aria-label="Open full response"
					>
						↗
					</button>
				</div>
			</div>
		</div>
	{/if}

	<!-- Live indicator (when no response yet) -->
	{#if turn.isLive && density !== 'compact'}
		<div
			class="flex items-center gap-2 px-3 py-2 bg-[var(--bg-subtle)] border-t border-[var(--border)]/40"
		>
			<div
				class="w-[7px] h-[7px] border-[1.5px] border-[var(--text-muted)] rounded-full bg-[var(--bg-base)] shrink-0"
			></div>
			<span class="text-[10px] font-mono text-[var(--text-primary)]"
				>Claude is working · tailing enabled</span
			>
			<span class="ml-auto text-[10px] font-mono text-[var(--text-faint)]">auto-scroll on</span>
		</div>
	{/if}
</div>
