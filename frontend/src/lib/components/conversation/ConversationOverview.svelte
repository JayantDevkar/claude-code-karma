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
		Monitor,
		Globe
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
	import {
		formatDuration,
		formatTokens,
		isRemoteSession,
		getTeamMemberColor
	} from '$lib/utils';
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

<div class="space-y-6 animate-fade-in">
	<!-- Initial Prompt -->
	{#if entity.initial_prompt}
		<ExpandablePrompt
			prompt={entity.initial_prompt}
			imageAttachments={entity.initial_prompt_images}
		/>
	{/if}

	<!-- Continuation Session Indicator (sessions only) -->
	{#if isMainSession(entity) && entity.is_continuation_marker}
		<div
			class="
				p-4 pl-5
				bg-[var(--nav-gray-subtle)]
				border border-[var(--nav-gray)]/30
				border-l-[3px] border-l-[var(--nav-gray)]
				rounded-lg
			"
		>
			<div class="flex items-center gap-3">
				<div class="p-2 rounded-lg bg-[var(--nav-gray)]/10">
					<Activity size={20} strokeWidth={2} class="text-[var(--nav-gray)]" />
				</div>
				<div>
					<h3 class="text-sm font-medium text-[var(--text-primary)]">
						Session Continuation Marker
					</h3>
					<p class="text-xs text-[var(--text-muted)] mt-0.5">
						This session was continued in a new session. This file contains {entity.file_snapshot_count ||
							0} file backup checkpoints tracking file changes for undo/redo functionality.
					</p>
				</div>
			</div>
			{#if entity.message_type_breakdown}
				<div class="mt-3 flex items-center gap-4 text-xs text-[var(--text-muted)]">
					<span
						>Snapshots: <span class="font-mono text-[var(--text-secondary)]"
							>{entity.message_type_breakdown.file_history_snapshot || 0}</span
						></span
					>
					<span
						>Summaries: <span class="font-mono text-[var(--text-secondary)]"
							>{entity.message_type_breakdown.summary || 0}</span
						></span
					>
				</div>
			{/if}

			<!-- View Continuation Link -->
			{#if continuationLoading}
				<div class="mt-3 text-xs text-[var(--text-muted)]">
					Loading continuation session...
				</div>
			{:else if continuationSession}
				<!-- Always use UUID for continuation links - they share slugs with parent session -->
				<a
					href="/projects/{continuationSession.project_encoded_name}/{continuationSession.session_uuid.slice(
						0,
						8
					)}"
					class="
						mt-3 inline-flex items-center gap-1.5
						px-3 py-1.5
						text-xs font-medium
						rounded-md border
						bg-[var(--accent-subtle)] border-[var(--accent)]/40 text-[var(--accent)]
						hover:bg-[var(--accent)]/20 hover:border-[var(--accent)]/60
						transition-colors
					"
				>
					<ExternalLink size={14} strokeWidth={2} />
					View Continuation Session
				</a>
			{:else if continuationError}
				<div class="mt-3 text-xs text-[var(--text-muted)] italic">
					Could not find the continuation session
				</div>
			{/if}
		</div>
	{/if}

	<!-- Project Context (sessions only - summaries from PREVIOUS sessions) -->
	{#if isMainSession(entity) && entity.project_context_summaries && entity.project_context_summaries.length > 0}
		{@const needsExpansion = entity.project_context_summaries.length > MAX_CONTEXT_PREVIEW}
		{@const displayedSummaries = isContextExpanded
			? entity.project_context_summaries
			: entity.project_context_summaries.slice(0, MAX_CONTEXT_PREVIEW)}
		<div
			class="
				p-4 pl-5
				bg-[var(--bg-subtle)]
				border border-[var(--border)]
				border-l-[3px] border-l-[var(--accent)]
				rounded-lg
			"
		>
			<div class="flex items-center gap-2 mb-2">
				<div class="p-1.5 rounded-md bg-[var(--accent)]/10">
					<Sparkles size={14} strokeWidth={2} class="text-[var(--accent)]" />
				</div>
				<h3 class="text-sm font-medium text-[var(--text-primary)]">Project Context</h3>
				<span class="text-xs text-[var(--text-muted)]"> (from previous sessions) </span>
				{#if needsExpansion}
					<span class="text-xs text-[var(--text-muted)]">
						&middot; {entity.project_context_summaries.length} summaries
					</span>
				{/if}
			</div>

			<Collapsible.Root open={isContextExpanded}>
				<div class="space-y-1.5">
					{#each displayedSummaries as summary, i}
						<p
							class="text-sm text-[var(--text-secondary)] leading-relaxed {i === 0
								? ''
								: 'border-t border-[var(--border)]/50 pt-1.5'}"
						>
							{summary}
						</p>
					{/each}
				</div>
			</Collapsible.Root>

			{#if needsExpansion}
				<div class="flex justify-center mt-3">
					<button
						onclick={() => (isContextExpanded = !isContextExpanded)}
						class="
							p-1.5
							text-[var(--accent)]
							hover:bg-[var(--accent-subtle)]
							rounded-full
							transition-colors
							focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]
						"
						aria-expanded={isContextExpanded}
						aria-label={isContextExpanded ? 'Collapse context' : 'Expand context'}
					>
						{#if isContextExpanded}
							<ChevronUp size={18} strokeWidth={2.5} />
						{:else}
							<ChevronDown size={18} strokeWidth={2.5} />
						{/if}
					</button>
				</div>
			{/if}
		</div>
	{/if}

	<!-- Additional Session Titles (only show if there are multiple titles beyond the header) -->
	{#if isMainSession(entity) && entity.session_titles && entity.session_titles.length > 1}
		<div
			class="
				p-4 pl-5
				bg-[var(--nav-teal-subtle)]
				border border-[var(--nav-teal)]/30
				border-l-[3px] border-l-[var(--nav-teal)]
				rounded-lg
			"
		>
			<div class="flex items-center gap-2 mb-2">
				<div class="p-1.5 rounded-md bg-[var(--nav-teal)]/10">
					<Tag size={14} strokeWidth={2} class="text-[var(--nav-teal)]" />
				</div>
				<h3 class="text-sm font-medium text-[var(--text-primary)]">
					Additional Titles ({entity.session_titles.length - 1})
				</h3>
			</div>
			<div class="space-y-1.5">
				{#each entity.session_titles.slice(1) as title}
					<p class="text-sm text-[var(--text-secondary)] leading-relaxed">
						{title}
					</p>
				{/each}
			</div>
		</div>
	{/if}

	<!-- Session Compaction Indicator (sessions only - TRUE compaction events) -->
	{#if isMainSession(entity) && entity.was_compacted}
		{@const compactionEvents = entity.compaction_summaries || []}
		{@const hasEvents = compactionEvents.length > 0}
		<div
			class="
				p-4 pl-5
				bg-[var(--nav-orange-subtle)]
				border border-[var(--nav-orange)]/30
				border-l-[3px] border-l-[var(--nav-orange)]
				rounded-lg
			"
		>
			<div class="flex items-center gap-2 mb-2">
				<div class="p-1.5 rounded-md bg-[var(--nav-orange)]/10">
					<Zap size={14} strokeWidth={2} class="text-[var(--nav-orange)]" />
				</div>
				<h3 class="text-sm font-medium text-[var(--text-primary)]">Context Compacted</h3>
				<span class="text-xs text-[var(--text-muted)]">
					({entity.compaction_summary_count || 1} time{(entity.compaction_summary_count ||
						1) > 1
						? 's'
						: ''})
				</span>
			</div>

			{#if hasEvents}
				<div class="space-y-3">
					{#each compactionEvents as event, i}
						<div
							class="flex flex-col gap-1.5 {i > 0
								? 'border-t border-[var(--nav-orange)]/20 pt-3'
								: ''}"
						>
							<!-- Compaction metadata -->
							<div class="flex items-center gap-3 text-xs">
								<span class="text-[var(--nav-orange)]/60 shrink-0">#{i + 1}</span>
								{#if typeof event === 'object' && event.trigger}
									<span
										class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-[var(--nav-orange)]/10 text-[var(--nav-orange)]"
									>
										{#if event.trigger === 'auto'}
											<Zap size={10} />
											Auto
										{:else}
											Manual
										{/if}
									</span>
								{/if}
								{#if typeof event === 'object' && event.pre_tokens}
									<span class="text-[var(--text-muted)]">
										{formatTokens(event.pre_tokens)} tokens before
									</span>
								{/if}
							</div>
							<!-- Summary text -->
							{#if typeof event === 'string'}
								<p class="text-sm text-[var(--text-secondary)] leading-relaxed">
									{event}
								</p>
							{:else if event.summary}
								<p class="text-sm text-[var(--text-secondary)] leading-relaxed">
									{event.summary}
								</p>
							{/if}
						</div>
					{/each}
				</div>
			{:else}
				<p class="text-sm text-[var(--text-muted)] italic">
					Context was compacted to manage conversation length
				</p>
			{/if}
		</div>
	{/if}

	<!-- Session Chain View (shows related sessions) -->
	{#if sessionChain && sessionChain.total_sessions > 1}
		<SessionChainView chain={sessionChain} {projectEncoded} />
	{/if}

	<!-- Info Cards Grid -->
	<div class="grid grid-cols-2 md:grid-cols-4 gap-3">
		<!-- Messages Card -->
		<StatsCard
			title="Messages"
			value={entity.message_count}
			icon={MessageSquare}
			color="blue"
		/>

		<!-- Duration Card -->
		<StatsCard
			title="Duration"
			value={formatDuration(entity.duration_seconds)}
			icon={Clock}
			color="orange"
		/>

		<!-- Session: Model Card / Agent: Tool Calls Card -->
		{#if isMainSession(entity)}
			<div
				class="p-4 bg-[var(--bg-subtle)] border border-[var(--border)] rounded-lg hover-lift"
			>
				<div class="text-[11px] uppercase tracking-wide text-[var(--text-muted)] mb-2">
					Model
				</div>
				<div class="flex items-center gap-2 flex-wrap">
					{#if entity.models_used?.length}
						{#each entity.models_used as model}
							<ModelBadge modelName={model} />
						{/each}
					{:else}
						<span class="text-sm text-[var(--text-muted)]">-</span>
					{/if}
					{#if isMainSession(entity) && isRemoteSession(entity) && entity.remote_user_id}
						{@const teamColor = getTeamMemberColor(entity.remote_user_id)}
						<div
							class="flex items-center gap-1 px-2 py-0.5 rounded-full border {teamColor.badge} text-xs"
							title="Remote session from {entity.remote_user_id}"
						>
							<Globe size={12} strokeWidth={2} class={teamColor.text} />
							<span class="font-medium {teamColor.text}">{entity.remote_user_id}</span>
						</div>
					{/if}
					{#if entity.session_source === 'desktop'}
						<div
							class="flex items-center gap-1 px-2 py-0.5 rounded-full border bg-[var(--bg-muted)] text-[var(--text-secondary)] border-[var(--border)] text-xs"
							title="Claude Desktop session"
						>
							<Monitor size={12} strokeWidth={2} />
							<span class="font-medium">Desktop</span>
						</div>
					{/if}
				</div>
			</div>
		{:else}
			<StatsCard title="Tool Calls" value={totalToolCalls} icon={Wrench} color="green" />
		{/if}

		<!-- Git Branch Card -->
		<div class="p-4 bg-[var(--bg-subtle)] border border-[var(--border)] rounded-lg hover-lift">
			<div class="text-[11px] uppercase tracking-wide text-[var(--text-muted)] mb-2">
				Git Branch
			</div>
			<div class="flex items-center gap-2 flex-wrap">
				{#if entity.git_branches?.length}
					{#each entity.git_branches as branch}
						<span
							class="inline-flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md border bg-[var(--nav-purple-subtle)] text-[var(--nav-purple)] border-[var(--nav-purple)]/40"
						>
							<GitBranch size={14} />
							{branch}
						</span>
					{/each}
				{:else}
					<span class="text-sm text-[var(--text-muted)]">-</span>
				{/if}
			</div>
		</div>
	</div>

	<!-- Working Directories -->
	{#if entity.working_directories?.length}
		<div
			class="
				p-4 pl-5
				bg-[var(--bg-subtle)]
				border border-[var(--border)]
				border-l-[3px] border-l-[var(--nav-teal)]
				rounded-lg
				w-full
			"
		>
			<div class="flex items-center gap-2 mb-3">
				<div class="p-1.5 rounded-md bg-[var(--nav-teal-subtle)]">
					<Folder size={14} strokeWidth={2} class="text-[var(--nav-teal)]" />
				</div>
				<h3 class="text-sm font-medium text-[var(--text-primary)]">Working Directories</h3>
			</div>
			<div class="space-y-1.5">
				{#each entity.working_directories as dir}
					<div
						class="
							flex items-center gap-2
							px-2.5 py-1.5
							bg-[var(--bg-muted)]
							rounded-md
							group
						"
					>
						<span class="text-[var(--nav-teal)]/60 text-xs">></span>
						<p
							class="font-mono text-xs text-[var(--text-secondary)] group-hover:text-[var(--text-primary)] transition-colors break-all"
							title={dir}
						>
							{dir}
						</p>
					</div>
				{/each}
			</div>
		</div>
	{/if}

	<!-- Tools Summary -->
	{#if toolsArray.length > 0}
		<div
			class="
				p-4 pl-5
				bg-[var(--bg-subtle)]
				border border-[var(--border)]
				border-l-[3px] border-l-[var(--nav-green)]
				rounded-lg
			"
		>
			<div class="flex items-center gap-2 mb-3">
				<div class="p-1.5 rounded-md bg-[var(--nav-green-subtle)]">
					<Wrench size={14} strokeWidth={2} class="text-[var(--nav-green)]" />
				</div>
				<h3 class="text-sm font-medium text-[var(--text-primary)]">
					Tools Used
					<span class="ml-1.5 text-xs font-normal text-[var(--text-muted)]">
						({totalToolCalls} calls)
					</span>
				</h3>
			</div>
			<div class="flex flex-wrap gap-2">
				{#each toolsArray.toSorted((a, b) => b.count - a.count) as tool}
					<span
						class="
							inline-flex items-center gap-1.5
							px-2.5 py-1.5 text-xs font-medium
							rounded-md border
							bg-[var(--bg-muted)] border-[var(--border)]
							hover:border-[var(--nav-green)]/40 hover:bg-[var(--nav-green-subtle)]
							transition-colors
						"
					>
						<span class="text-[var(--text-primary)]">{tool.tool_name}</span>
						<span class="text-[var(--nav-green)] font-semibold">x{tool.count}</span>
					</span>
				{/each}
			</div>
		</div>
	{/if}
</div>
