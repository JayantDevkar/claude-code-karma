<script lang="ts">
	import { browser } from '$app/environment';
	import { Collapsible } from 'bits-ui';
	import {
		MessageSquare,
		Clock,
		Wrench,
		Activity,
		Sparkles,
		GitBranch,
		Folder,
		ChevronDown,
		ChevronUp,
		ExternalLink,
		Zap,
		Tag,
		Monitor
	} from 'lucide-svelte';
	import StatsCard from '$lib/components/StatsCard.svelte';
	import ExpandablePrompt from '$lib/components/ExpandablePrompt.svelte';
	import ModelBadge from '$lib/components/ModelBadge.svelte';
	import SessionChainView from '$lib/components/SessionChainView.svelte';
	import type {
		ConversationEntity,
		ToolUsage,
		ContinuationSessionInfo,
		SessionChain,
		CompactionSummary
	} from '$lib/api-types';
	import { isSubagentSession, isMainSession } from '$lib/api-types';
	import { projectHrefFromSession } from '$lib/utils/project-url';
	import { formatDuration, formatTokens } from '$lib/utils';
	import { API_BASE } from '$lib/config';

	interface Props {
		entity: ConversationEntity;
		toolsArray: ToolUsage[];
		totalToolCalls: number;
		projectEncoded: string;
		// Continuation session linking (sessions only)
		continuationSession?: ContinuationSessionInfo | null;
		continuationLoading?: boolean;
		continuationError?: string | null;
	}

	let {
		entity,
		toolsArray,
		totalToolCalls,
		projectEncoded,
		continuationSession = null,
		continuationLoading = false,
		continuationError = null
	}: Props = $props();

	// Session context (summaries) expansion state
	let isContextExpanded = $state(false);
	const MAX_CONTEXT_PREVIEW = 3;

	// Session chain state
	let sessionChain = $state<SessionChain | null>(null);

	// Fetch session chain only when the session actually belongs to one
	$effect(() => {
		if (!browser) return;
		if (!entity || isSubagentSession(entity) || entity.has_chain === false) {
			sessionChain = null;
			return;
		}

		const uuid = entity.uuid;

		fetch(`${API_BASE}/sessions/${uuid}/chain`)
			.then((res) => {
				if (!res.ok) throw new Error('Failed to fetch chain');
				return res.json();
			})
			.then((data: SessionChain) => {
				sessionChain = data;
			})
			.catch(() => {
				sessionChain = null;
			});
	});
</script>

<div class="flex flex-col gap-3 animate-fade-in">

	<!-- Branch (Messages/Duration/Model removed — already in session hero) -->
	{#if entity.git_branches?.length}
		<div class="flex items-center gap-2.5 rounded-lg px-3 py-2.5 bg-[var(--bg-base)] border border-[var(--border)]/60">
			<GitBranch size={14} strokeWidth={2} class="text-violet-400 shrink-0" />
			<div class="min-w-0 overflow-hidden">
				<div class="text-[10px] uppercase tracking-wide text-[var(--text-muted)] leading-none mb-0.5">Branch</div>
				<div class="text-xs font-medium text-[var(--text-primary)] truncate">{entity.git_branches[0]}</div>
			</div>
		</div>
	{/if}

	<!-- ── Initial Prompt ── -->
	{#if entity.initial_prompt}
		<ExpandablePrompt
			prompt={entity.initial_prompt}
			imageAttachments={isMainSession(entity) ? entity.initial_prompt_images : undefined}
		/>
	{/if}

	<!-- ── Continuation marker ── -->
	{#if isMainSession(entity) && entity.is_continuation_marker}
		<div class="rounded-lg border-l-2 border-l-[var(--nav-gray)] border border-[var(--nav-gray)]/20 bg-[var(--nav-gray-subtle)] px-3 py-2.5">
			<div class="flex items-center gap-2 mb-1">
				<Activity size={13} strokeWidth={2} class="text-[var(--nav-gray)]" />
				<span class="text-xs font-medium text-[var(--text-primary)]">Continuation Marker</span>
			</div>
			<p class="text-xs text-[var(--text-muted)]">{entity.file_snapshot_count || 0} file checkpoints</p>
			{#if continuationSession}
				<a
					href={projectHrefFromSession(continuationSession, `/${continuationSession.session_uuid.slice(0, 8)}`)}
					class="mt-2 inline-flex items-center gap-1 text-xs font-medium text-[var(--accent)] hover:underline"
				>
					<ExternalLink size={12} strokeWidth={2} /> View continuation
				</a>
			{/if}
		</div>
	{/if}

	<!-- ── Project Context ── -->
	{#if isMainSession(entity) && entity.project_context_summaries && entity.project_context_summaries.length > 0}
		{@const needsExpansion = entity.project_context_summaries.length > MAX_CONTEXT_PREVIEW}
		{@const displayedSummaries = isContextExpanded ? entity.project_context_summaries : entity.project_context_summaries.slice(0, MAX_CONTEXT_PREVIEW)}
		<div class="rounded-lg border-l-2 border-l-[var(--accent)] border border-[var(--border)]/60 bg-[var(--bg-base)] px-3 py-2.5">
			<div class="flex items-center gap-2 mb-2">
				<Sparkles size={13} strokeWidth={2} class="text-[var(--accent)]" />
				<span class="text-xs font-medium text-[var(--text-primary)]">Project Context</span>
				<span class="text-[10px] text-[var(--text-muted)] ml-auto">{entity.project_context_summaries.length} summaries</span>
			</div>
			<div class="space-y-1.5">
				{#each displayedSummaries as summary, i}
					<p class="text-xs text-[var(--text-secondary)] leading-relaxed {i > 0 ? 'border-t border-[var(--border)]/40 pt-1.5' : ''}">{summary}</p>
				{/each}
			</div>
			{#if needsExpansion}
				<button onclick={() => (isContextExpanded = !isContextExpanded)} class="mt-2 text-xs text-[var(--accent)] hover:underline flex items-center gap-1">
					{#if isContextExpanded}<ChevronUp size={12} /> Less{:else}<ChevronDown size={12} /> {entity.project_context_summaries.length - MAX_CONTEXT_PREVIEW} more{/if}
				</button>
			{/if}
		</div>
	{/if}

	<!-- ── Compaction ── -->
	{#if isMainSession(entity) && entity.was_compacted}
		{@const compactionEvents = entity.compaction_summaries || []}
		<div class="rounded-lg border-l-2 border-l-[var(--nav-orange)] border border-[var(--nav-orange)]/20 bg-[var(--nav-orange-subtle)] px-3 py-2.5">
			<div class="flex items-center gap-2 mb-1.5">
				<Zap size={13} strokeWidth={2} class="text-[var(--nav-orange)]" />
				<span class="text-xs font-medium text-[var(--text-primary)]">Context Compacted</span>
				<span class="text-[10px] text-[var(--text-muted)] ml-auto">{entity.compaction_summary_count || 1}×</span>
			</div>
			{#each compactionEvents as event, i}
				<div class="{i > 0 ? 'border-t border-[var(--nav-orange)]/20 pt-2 mt-2' : ''}">
					{#if typeof event === 'object' && event.pre_tokens}
						<span class="text-[10px] text-[var(--text-muted)]">{formatTokens(event.pre_tokens)} tokens</span>
					{/if}
					<p class="text-xs text-[var(--text-secondary)] leading-relaxed mt-0.5">
						{typeof event === 'string' ? event : event.summary || ''}
					</p>
				</div>
			{/each}
		</div>
	{/if}

	<!-- ── Additional Titles ── -->
	{#if isMainSession(entity) && entity.session_titles && entity.session_titles.length > 1}
		<div class="rounded-lg border-l-2 border-l-[var(--nav-teal)] border border-[var(--nav-teal)]/20 bg-[var(--nav-teal-subtle)] px-3 py-2.5">
			<div class="flex items-center gap-2 mb-1.5">
				<Tag size={13} strokeWidth={2} class="text-[var(--nav-teal)]" />
				<span class="text-xs font-medium text-[var(--text-primary)]">Titles ({entity.session_titles.length - 1})</span>
			</div>
			<div class="space-y-1">
				{#each entity.session_titles.slice(1) as title}
					<p class="text-xs text-[var(--text-secondary)]">{title}</p>
				{/each}
			</div>
		</div>
	{/if}

	<!-- ── Session Chain ── -->
	{#if sessionChain && sessionChain.total_sessions > 1}
		<SessionChainView chain={sessionChain} {projectEncoded} />
	{/if}

	<!-- ── Working Directories ── -->
	{#if entity.working_directories?.length}
		<div class="rounded-lg border border-[var(--border)]/60 bg-[var(--bg-base)] px-3 py-2.5">
			<div class="flex items-center gap-2 mb-2">
				<Folder size={13} strokeWidth={2} class="text-[var(--nav-teal)]" />
				<span class="text-xs font-medium text-[var(--text-primary)]">Working Directories</span>
			</div>
			<div class="space-y-1">
				{#each entity.working_directories as dir}
					<p class="font-mono text-[11px] text-[var(--text-secondary)] break-all leading-relaxed" title={dir}>{dir}</p>
				{/each}
			</div>
		</div>
	{/if}

	<!-- ── Tools Summary ── -->
	{#if toolsArray.length > 0}
		<div class="rounded-lg border border-[var(--border)]/60 bg-[var(--bg-base)] px-3 py-2.5">
			<div class="flex items-center gap-2 mb-2">
				<Wrench size={13} strokeWidth={2} class="text-[var(--nav-green)]" />
				<span class="text-xs font-medium text-[var(--text-primary)]">Tools Used</span>
				<span class="text-[10px] text-[var(--text-muted)] ml-auto">{totalToolCalls} calls</span>
			</div>
			<div class="flex flex-wrap gap-1.5">
				{#each toolsArray.toSorted((a, b) => b.count - a.count) as tool}
					<span class="inline-flex items-center gap-1 px-2 py-1 text-[11px] font-medium rounded-md border bg-[var(--bg-subtle)] border-[var(--border)]/60 text-[var(--text-primary)]">
						{tool.tool_name}<span class="text-[var(--nav-green)] font-semibold">×{tool.count}</span>
					</span>
				{/each}
			</div>
		</div>
	{/if}
</div>
