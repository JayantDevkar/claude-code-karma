<script lang="ts">
	import { goto } from '$app/navigation';
	import { openShellDrawer, openAgentDrawer, openDiffDrawer, openFileReadDrawer } from '$lib/stores/drawer';
	import {
		Brain,
		Terminal,
		FileText,
		FileEdit,
		Eye,
		Search,
		Wrench,
		MessageSquare,
		Bot,
		CheckSquare,
		Zap,
		ArrowRight,
		AlertCircle,
		Plug
	} from 'lucide-svelte';
	import type { TimelineEvent } from '$lib/api-types';
	import { marked } from 'marked';
	import DOMPurify from 'isomorphic-dompurify';

	function renderMd(text: string): string {
		const html = marked.parse(text, { async: false }) as string;
		return DOMPurify.sanitize(html);
	}

	interface Props {
		event: TimelineEvent;
		index: number;
		isFirst: boolean;
		isLast: boolean;
		sessionStartTime?: string;
		isHighlighted: boolean;
		hasActiveFilter: boolean;
		isExpanded: boolean;
		onToggleExpand: () => void;
		usePopup?: boolean;
		onOpenPopup?: () => void;
		currentAgentId?: string | null;
		projectPath?: string | null;
		onToggleHide?: () => void;
		searchQuery?: string;
		projectEncoded?: string;
		sessionSlug?: string;
		sessionUuid?: string;
		parentSessionUuid?: string;
		showTurnDivider?: boolean;
		turnNumber?: number;
	}

	let {
		event,
		index,
		sessionStartTime,
		isHighlighted,
		hasActiveFilter,
		onToggleExpand,
		usePopup = false,
		onOpenPopup,
		currentAgentId = null,
		onToggleHide,
		searchQuery = '',
		projectEncoded,
		sessionSlug,
		sessionUuid,
		parentSessionUuid,
		showTurnDivider = false,
		turnNumber = 1
	}: Props = $props();

	const isDimmed = $derived(hasActiveFilter && !isHighlighted);
	const toolName = $derived(event.metadata?.tool_name as string | undefined);
	const isAgentSpawn = $derived(!!event.metadata?.spawned_agent_id);
	const agentId = $derived(event.metadata?.spawned_agent_id as string | undefined);
	const agentType = $derived(event.metadata?.subagent_type as string | undefined);

	const isError = $derived(
		(event.metadata?.result_status as string | undefined) === 'error' ||
		(event.metadata?.is_error as boolean | undefined) === true
	);

	const hasExpandableContent = $derived(
		!isAgentSpawn && (
			event.event_type === 'tool_call' ||
			event.event_type === 'todo_update' ||
			!!event.metadata?.full_content ||
			!!event.metadata?.full_thinking ||
			!!event.metadata?.full_text ||
			!!event.metadata?.result_content ||
			(event.summary && event.summary.length > 100)
		)
	);

	const flatTitle = $derived.by(() => {
		const t = event.title || '';
		if (event.event_type === 'tool_call') {
			const colonIdx = t.indexOf(': ');
			if (colonIdx > 0) return t.slice(colonIdx + 2);
		}
		return t;
	});

	// Elapsed time from session start — shown in turn divider only
	const turnElapsed = $derived.by(() => {
		if (!showTurnDivider || !sessionStartTime || !event.timestamp) return '';
		const ms = new Date(event.timestamp).getTime() - new Date(sessionStartTime).getTime();
		if (ms <= 0) return '';
		const min = Math.floor(ms / 60000);
		const sec = Math.floor((ms % 60000) / 1000);
		return min > 0 ? `+${min}m ${sec}s` : `+${sec}s`;
	});

	function isShellTool(name: string | undefined) {
		return name === 'Bash' || name === 'Shell';
	}
	function isFileTool(name: string | undefined) {
		return name === 'Read' || name === 'Write' || name === 'Edit' ||
			name === 'MultiEdit' || name === 'StrReplace' || name === 'Glob' || name === 'Grep';
	}
	function hasToolNav() {
		return isShellTool(toolName) || isFileTool(toolName);
	}

	function getToolIcon(name: string | undefined) {
		if (!name) return Wrench;
		if (name === 'Bash' || name === 'Shell') return Terminal;
		if (name === 'Edit' || name === 'StrReplace' || name === 'MultiEdit') return FileEdit;
		if (name === 'Write') return FileText;
		if (name === 'Read') return Eye;
		if (name === 'Grep' || name === 'Glob') return Search;
		if (name.startsWith('mcp__')) return Plug;
		return Wrench;
	}

	// Hover preview content for file tools
	const previewLines = $derived.by((): string[] | null => {
		if (event.event_type !== 'tool_call') return null;
		const meta = event.metadata as Record<string, unknown> | undefined;
		if (!meta) return null;
		if (toolName === 'Read') {
			const content = String(meta.result_content ?? meta.content ?? '');
			if (!content.trim()) return null;
			return content.split('\n').slice(0, 10);
		}
		if (toolName === 'Write') {
			const content = String(meta.content ?? '');
			if (!content.trim()) return null;
			return content.split('\n').slice(0, 10);
		}
		if (toolName === 'Edit' || toolName === 'StrReplace' || toolName === 'MultiEdit') {
			const oldStr = String(meta.old_string ?? '');
			const newStr = String(meta.new_string ?? '');
			if (!oldStr && !newStr) return null;
			const lines: string[] = [];
			oldStr.split('\n').slice(0, 4).forEach((l) => lines.push(`- ${l}`));
			if (oldStr && newStr) lines.push('');
			newStr.split('\n').slice(0, 4).forEach((l) => lines.push(`+ ${l}`));
			return lines;
		}
		return null;
	});

	// Preview tooltip state
	let showPreview = $state(false);
	let previewX = $state(0);
	let previewY = $state(0);

	function handleToolMouseEnter(e: MouseEvent) {
		if (!previewLines?.length) return;
		const x = e.clientX + 16;
		const y = Math.max(8, Math.min(e.clientY - 20, window.innerHeight - 260));
		const adjustedX = x + 480 > window.innerWidth ? e.clientX - 496 : x;
		previewX = adjustedX;
		previewY = y;
		showPreview = true;
	}

	function handleToolMouseLeave() {
		showPreview = false;
	}

	function handleClick() {
		if (event.event_type === 'tool_call' && isShellTool(toolName)) {
			openShellDrawer(event, sessionUuid ?? '', projectEncoded ?? '');
			return;
		}
		if (event.event_type === 'tool_call' && isFileTool(toolName)) {
			const meta = event.metadata as Record<string, string> | undefined;
			if (toolName === 'Read') {
				const content = meta?.result_content ?? meta?.content ?? '';
				const path = meta?.path ?? event.title ?? '';
				openFileReadDrawer(path, content);
			} else if (toolName === 'Edit' || toolName === 'StrReplace' || toolName === 'MultiEdit') {
				const path = meta?.path ?? event.title ?? '';
				const oldStr = meta?.old_string ?? '';
				const newStr = meta?.new_string ?? '';
				openDiffDrawer(path, oldStr, newStr);
			} else if (toolName === 'Write') {
				const path = meta?.path ?? event.title ?? '';
				const content = meta?.content ?? '';
				openDiffDrawer(path, '', content);
			} else {
				// Grep / Glob — show results in read drawer if available
				const path = (meta?.path ?? meta?.pattern ?? event.title ?? '') as string;
				const content = (meta?.result_content ?? '') as string;
				if (content) {
					openFileReadDrawer(path, content);
				} else if (hasExpandableContent) {
					if (usePopup && onOpenPopup) onOpenPopup();
					else onToggleExpand();
				}
			}
			return;
		}
		if (isAgentSpawn && agentId) {
			openAgentDrawer(agentId, agentType ?? null, parentSessionUuid ?? sessionUuid ?? '', projectEncoded ?? '');
			return;
		}
		if (event.event_type === 'skill_invocation') {
			const skillPath = (event.title ?? '').replace(/^Skill:\s*\/?/, '');
			if (skillPath) { goto(`/skills/${encodeURIComponent(skillPath)}`); return; }
		}
		if (hasExpandableContent) {
			if (usePopup && onOpenPopup) onOpenPopup();
			else onToggleExpand();
		}
	}

	function highlightText(text: string, query: string): string {
		if (!query || !text) return escapeHtml(text);
		const safe = escapeHtml(text);
		const escaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
		return safe.replace(new RegExp(`(${escaped})`, 'gi'), '<mark class="search-highlight">$1</mark>');
	}

	function escapeHtml(t: string): string {
		return t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
	}
</script>

{#if showPreview && previewLines?.length}
	<!-- Hover preview: fixed-position, pointer-events-none so it doesn't interrupt hover -->
	<div
		class="fixed z-50 max-w-[480px] min-w-[240px]
			bg-[var(--bg-base)] border border-[var(--border)]
			rounded-md shadow-xl overflow-hidden"
		style="left: {previewX}px; top: {previewY}px; pointer-events: none;"
	>
		<div class="px-2.5 py-1 border-b border-[var(--border)]/50 flex items-center gap-1.5 bg-[var(--bg-subtle)]">
			<span class="text-[10px] font-mono text-[var(--text-faint)]">{toolName}</span>
			<span class="text-[var(--text-faint)] opacity-40">·</span>
			<span class="text-[10px] font-mono text-[var(--text-muted)] truncate">{flatTitle.split('/').at(-1) ?? flatTitle}</span>
		</div>
		<pre class="text-[11px] font-mono px-3 py-2 max-h-[220px] overflow-hidden leading-relaxed
			whitespace-pre text-[var(--text-secondary)]
			{(previewLines?.[0]?.startsWith('- ') || previewLines?.[0]?.startsWith('+ '))
				? '[&>*]:text-inherit'
				: ''}"
		>{#each previewLines ?? [] as line}<span
				class="{line.startsWith('- ') ? 'text-[var(--error)]' : line.startsWith('+ ') ? 'text-[var(--success)]' : ''}"
			>{line}</span>{'\n'}{/each}</pre>
	</div>
{/if}

{#if showTurnDivider}
	<div class="flex items-center gap-3 pt-4 pb-2 select-none" aria-hidden="true">
		<div class="h-px flex-1 bg-[var(--border)]/40"></div>
		<span class="text-[10px] font-mono text-[var(--text-faint)] uppercase tracking-widest px-1">
			Turn {turnNumber}{#if turnElapsed}<span class="opacity-50 not-uppercase tracking-normal ml-1.5">{turnElapsed}</span>{/if}
		</span>
		<div class="h-px flex-1 bg-[var(--border)]/40"></div>
	</div>
{/if}

<div
	data-event-index={index >= 0 ? index : undefined}
	class="text-sm leading-relaxed transition-opacity {isDimmed ? 'opacity-20 pointer-events-none' : ''}"
>

	{#if event.event_type === 'prompt'}
		<!-- User prompt: accent left border + bg, MessageSquare icon, J/K nav target -->
		<button
			type="button"
			data-event-type="prompt"
			class="flex items-start gap-2.5 w-full text-left px-3 py-2 mb-2
				bg-[var(--bg-base)] border border-[var(--border)]/40 border-l-2 border-l-[var(--accent)]
				rounded-sm hover:bg-[var(--bg-subtle)] transition-colors cursor-pointer"
			onclick={handleClick}
		>
			<MessageSquare size={13} class="text-[var(--accent)] shrink-0 mt-0.5" />
			<span class="flex-1 text-[var(--text-primary)] break-words leading-relaxed">
				{#if searchQuery}
					{@html highlightText(event.summary || event.title || '', searchQuery)}
				{:else}
					{event.summary || event.title || ''}
				{/if}
			</span>
		</button>

	{:else if isAgentSpawn}
		<!-- Agent spawn: checked before tool_call since metadata.spawned_agent_id can exist on tool_call events -->
		<button
			type="button"
			class="group flex items-center gap-2 w-full text-left px-2 py-1.5 mb-1 rounded-sm
				bg-[var(--event-subagent)]/5 border border-[var(--event-subagent)]/20
				hover:bg-[var(--event-subagent)]/10 transition-colors cursor-pointer"
			onclick={handleClick}
		>
			<Bot size={13} class="text-[var(--event-subagent)] shrink-0" />
			<span class="flex-1 text-xs text-[var(--event-subagent)] font-mono break-words">
				{#if searchQuery}
					{@html highlightText(
						`${agentType ?? 'subagent'}${agentId ? ' · ' + agentId.slice(0, 8) : ''}`,
						searchQuery
					)}
				{:else}
					{agentType ?? 'subagent'}
					{#if agentId}<span class="opacity-50 ml-1">· {agentId.slice(0, 8)}</span>{/if}
				{/if}
			</span>
			<ArrowRight
				size={11}
				class="opacity-25 group-hover:opacity-60 transition-opacity shrink-0 text-[var(--event-subagent)]"
			/>
		</button>

	{:else if event.event_type === 'thinking'}
		<!-- Thinking: Brain icon, faint italic -->
		<div class="flex items-start gap-2 px-1 py-0.5 mb-1">
			<Brain size={12} class="text-[var(--event-thinking)] opacity-40 shrink-0 mt-0.5" />
			<span class="flex-1 text-[var(--text-faint)] italic text-xs break-words">
				{event.summary ? event.summary : 'Thinking…'}
			</span>
		</div>

	{:else if event.event_type === 'tool_call'}
		<!-- Tool call: icon + tool name badge + path, red on error, arrow affordance, hover preview -->
		{@const ToolIconComp = isError ? AlertCircle : getToolIcon(toolName)}
		<button
			type="button"
			class="group flex items-center gap-1.5 w-full text-left px-1 py-0.5 mb-0.5 font-mono rounded-sm transition-colors
				{isError ? 'hover:bg-[var(--error)]/5' : 'hover:bg-[var(--event-tool)]/5'}
				{hasToolNav() || hasExpandableContent ? 'cursor-pointer' : 'cursor-default'}"
			onclick={handleClick}
			onmouseenter={handleToolMouseEnter}
			onmouseleave={handleToolMouseLeave}
		>
			<ToolIconComp
				size={12}
				class="shrink-0 {isError ? 'text-[var(--error)]' : 'text-[var(--event-tool)] opacity-50'}"
			/>
			{#if toolName}
				<span class="shrink-0 text-[10px] pr-1.5 mr-0.5 border-r
					{isError
						? 'text-[var(--error)]/60 border-[var(--error)]/20'
						: 'text-[var(--event-tool)]/50 border-[var(--event-tool)]/20'}">
					{toolName}
				</span>
			{/if}
			<span class="flex-1 text-xs break-words
				{isError ? 'text-[var(--error)]' : 'text-[var(--event-tool)]'}
				{hasToolNav() || hasExpandableContent ? 'group-hover:underline underline-offset-2' : ''}">
				{#if searchQuery}
					{@html highlightText(flatTitle, searchQuery)}
				{:else}
					{flatTitle}
				{/if}
			</span>
			{#if hasToolNav() || hasExpandableContent}
				<ArrowRight
					size={11}
					class="opacity-15 group-hover:opacity-50 transition-opacity shrink-0
						{isError ? 'text-[var(--error)]' : 'text-[var(--event-tool)]'}"
				/>
			{/if}
		</button>

	{:else if event.event_type === 'skill_invocation'}
		<!-- Skill: Zap icon, accent on hover -->
		<button
			type="button"
			class="group flex items-center gap-1.5 w-full text-left px-1 py-0.5 mb-0.5
				text-[var(--text-muted)] hover:text-[var(--accent)] transition-colors cursor-pointer"
			onclick={handleClick}
		>
			<Zap size={12} class="text-[var(--accent)] opacity-50 group-hover:opacity-100 shrink-0 transition-opacity" />
			<span class="flex-1 text-xs break-words group-hover:underline underline-offset-2">
				{#if searchQuery}
					{@html highlightText(flatTitle || event.title || '', searchQuery)}
				{:else}
					{flatTitle || event.title}
				{/if}
			</span>
			<ArrowRight size={11} class="opacity-15 group-hover:opacity-50 transition-opacity shrink-0" />
		</button>

	{:else if event.event_type === 'todo_update'}
		<!-- Todo: CheckSquare icon -->
		<button
			type="button"
			class="group flex items-center gap-1.5 w-full text-left px-1 py-0.5 mb-0.5
				text-[var(--text-muted)]
				{hasExpandableContent ? 'cursor-pointer hover:text-[var(--text-secondary)]' : 'cursor-default'}
				transition-colors"
			onclick={handleClick}
		>
			<CheckSquare size={12} class="opacity-50 shrink-0" />
			<span class="flex-1 text-xs break-words">
				{#if searchQuery}
					{@html highlightText(event.summary || event.title || '', searchQuery)}
				{:else}
					{event.summary || event.title || ''}
				{/if}
			</span>
		</button>

	{:else}
		<!-- Claude response and any unhandled event type: markdown rendered -->
		<button
			type="button"
			class="w-full text-left px-3 py-2 mb-2 rounded-sm
				bg-[var(--bg-subtle)] border border-[var(--border)]/30
				{hasExpandableContent ? 'cursor-pointer hover:bg-[var(--bg-muted)] transition-colors' : 'cursor-default'}"
			onclick={handleClick}
		>
			<div class="prose prose-sm max-w-none
				prose-p:my-1 prose-p:leading-relaxed
				prose-headings:text-[var(--text-primary)] prose-headings:font-semibold prose-headings:my-2
				prose-strong:text-[var(--text-primary)] prose-strong:font-semibold
				prose-code:text-[var(--accent)] prose-code:bg-[var(--bg-muted)] prose-code:px-1 prose-code:rounded prose-code:text-xs prose-code:font-mono
				prose-pre:bg-[var(--bg-muted)] prose-pre:rounded prose-pre:p-2 prose-pre:overflow-x-auto
				prose-ul:my-1 prose-ol:my-1 prose-li:my-0.5
				prose-a:text-[var(--accent)] prose-a:no-underline hover:prose-a:underline
				text-[var(--text-secondary)]">
				{@html renderMd(event.summary || event.title || '')}
			</div>
		</button>
	{/if}

</div>
