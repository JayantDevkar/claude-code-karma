<script lang="ts">
	import {
		Bot,
		Wrench,
		MessageSquare,
		ChevronDown,
		ChevronUp,
		Hash,
		Sparkles,
		Search,
		FileText,
		Terminal,
		Zap,
		ExternalLink,
		Clock,
		Check,
		AlertCircle,
		FileCode,
		Minimize2,
		MessageCircle
	} from 'lucide-svelte';
	import type { SubagentSummary, SubagentStatus } from '$lib/api-types';
	import {
		getSubagentColorVars,
		getSubagentTypeDisplayName,
		cleanAgentIdForDisplay,
		formatDuration,
		calculateSubagentDuration,
		truncate
	} from '$lib/utils';

	interface Props {
		subagent: SubagentSummary;
		class?: string;
		/** Encoded project name for navigation (optional - enables clickable navigation) */
		projectEncoded?: string;
		/** Session slug for navigation (optional - enables clickable navigation) */
		sessionSlug?: string;
		/** Live status from hooks (optional - for real-time status display) */
		status?: SubagentStatus;
		/** Start timestamp for duration calculation (optional) */
		started_at?: string;
		/** Completion timestamp (optional) */
		completed_at?: string | null;
		/** Path to subagent transcript JSONL (optional) */
		transcript_path?: string | null;
	}

	let {
		subagent,
		class: className = '',
		projectEncoded,
		sessionSlug,
		status,
		started_at,
		completed_at,
		transcript_path
	}: Props = $props();

	// Calculate running/completed duration
	let duration = $derived(calculateSubagentDuration(started_at, completed_at));

	// Status configuration
	const statusColors: Record<SubagentStatus, { color: string; label: string }> = {
		running: { color: 'var(--success)', label: 'Running' },
		completed: { color: 'var(--info)', label: 'Completed' },
		error: { color: 'var(--error)', label: 'Error' }
	};

	// Navigation is enabled if both projectEncoded and sessionSlug are provided
	let navigationEnabled = $derived(!!projectEncoded && !!sessionSlug);
	let agentHref = $derived(
		navigationEnabled
			? `/projects/${projectEncoded}/${sessionSlug}/agents/${subagent.agent_id}`
			: null
	);

	let isExpanded = $state(false);

	// Calculate tool stats
	let totalToolCalls = $derived(Object.values(subagent.tools_used).reduce((a, b) => a + b, 0));

	let allTools = $derived(Object.entries(subagent.tools_used).sort((a, b) => b[1] - a[1]));

	let topTools = $derived(allTools.slice(0, 5));
	let hasMoreTools = $derived(allTools.length > 5);

	// Check if content is expandable
	let hasExpandableContent = $derived(
		hasMoreTools || (subagent.initial_prompt && subagent.initial_prompt.length > 200)
	);

	// Get icon based on type (known types get specific icons, others get Bot)
	function getTypeIcon(type: string | null | undefined) {
		switch (type) {
			case 'Explore':
				return Search;
			case 'Plan':
				return FileText;
			case 'Bash':
				return Terminal;
			case 'Claude Tax':
				return Zap;
			// System agents (auto-spawned by Claude Code)
			case 'acompact':
				return Minimize2; // Context compaction/cleanup
			case 'aprompt_suggestion':
				return MessageCircle; // AI-powered suggestions
			default:
				return Bot;
		}
	}

	// Get colors from centralized utility (supports both known and custom types)
	let colorVars = $derived(getSubagentColorVars(subagent.subagent_type));
	let typeIcon = $derived(getTypeIcon(subagent.subagent_type));
	// Clean agent ID for display (removes system prefixes like "aprompt_suggestion-")
	let displayAgentId = $derived(cleanAgentIdForDisplay(subagent.agent_id));

	function handleClick(e: MouseEvent) {
		// Don't toggle if clicking on the navigation link
		if ((e.target as HTMLElement).closest('a')) {
			return;
		}
		if (hasExpandableContent) {
			isExpanded = !isExpanded;
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		// Don't toggle if pressing keys on the navigation link
		if ((e.target as HTMLElement).closest('a')) {
			return;
		}
		if (hasExpandableContent && (e.key === 'Enter' || e.key === ' ')) {
			e.preventDefault();
			isExpanded = !isExpanded;
		}
	}
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<div
	class="
		group rounded-lg border border-l-[3px] bg-[var(--bg-subtle)] transition-all duration-200
		border-[var(--border)]
		{hasExpandableContent ? 'cursor-pointer hover:shadow-md' : ''}
		{isExpanded ? 'shadow-md' : ''}
		{className}
	"
	style="border-left-color: {colorVars.color};"
	onclick={handleClick}
	onkeydown={handleKeydown}
	role={hasExpandableContent ? 'button' : undefined}
	tabindex={hasExpandableContent ? 0 : undefined}
	aria-expanded={hasExpandableContent ? isExpanded : undefined}
>
	<!-- Main card content -->
	<div class="p-4 pl-5">
		<!-- Header -->
		<div class="flex items-start gap-3">
			<!-- Icon with type-specific background -->
			<div
				class="flex h-8 w-8 items-center justify-center rounded-lg shrink-0 transition-colors"
				style="background-color: {colorVars.subtle};"
			>
				{#if typeIcon}
					{@const Icon = typeIcon}
					<Icon size={16} strokeWidth={2} style="color: {colorVars.color};" />
				{/if}
			</div>

			<div class="flex-1 min-w-0">
				<div class="flex items-center justify-between gap-2">
					<div class="flex items-center gap-2 min-w-0">
						{#if agentHref}
							<a
								href={agentHref}
								class="
									inline-flex items-center gap-1.5
									text-sm font-mono font-medium text-[var(--accent)]
									hover:text-[var(--accent-hover)] hover:underline
									transition-colors truncate
								"
								title={subagent.agent_id}
							>
								{displayAgentId}
								<ExternalLink
									size={12}
									strokeWidth={2}
									class="shrink-0 opacity-60"
								/>
							</a>
						{:else}
							<code
								class="text-sm font-mono font-medium text-[var(--accent)] truncate"
								title={subagent.agent_id}
							>
								{displayAgentId}
							</code>
						{/if}
						<!-- Status badge (when available from live status) -->
						{#if status}
							{@const statusStyle = statusColors[status]}
							<span
								class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium"
								style="background: color-mix(in srgb, {statusStyle.color} 15%, transparent); color: {statusStyle.color};"
							>
								{#if status === 'running'}
									<span
										class="w-1.5 h-1.5 rounded-full animate-pulse"
										style="background: {statusStyle.color};"
									></span>
								{:else if status === 'completed'}
									<Check size={10} strokeWidth={3} />
								{:else if status === 'error'}
									<AlertCircle size={10} strokeWidth={3} />
								{/if}
								{statusStyle.label}
							</span>
						{/if}
					</div>

					<!-- Duration & expand/collapse indicator -->
					<div class="flex items-center gap-2">
						{#if duration !== null}
							<span
								class="flex items-center gap-1 text-[10px] text-[var(--text-muted)]"
							>
								<Clock size={10} strokeWidth={2} />
								<span class="tabular-nums">{formatDuration(duration)}</span>
							</span>
						{/if}
						{#if hasExpandableContent}
							<div
								class="
									flex h-6 w-6 items-center justify-center rounded-full shrink-0 transition-colors
									text-[var(--text-muted)] group-hover:text-[var(--text-primary)] group-hover:bg-[var(--bg-muted)]
								"
							>
								{#if isExpanded}
									<ChevronUp size={16} strokeWidth={2} />
								{:else}
									<ChevronDown size={16} strokeWidth={2} />
								{/if}
							</div>
						{/if}
					</div>
				</div>

				<!-- Task description -->
				{#if subagent.initial_prompt}
					<p
						class="
							mt-1.5 text-sm text-[var(--text-secondary)] transition-all duration-200
							bg-[var(--bg-muted)] px-2 py-1 rounded-md
							{isExpanded ? 'whitespace-pre-wrap' : 'line-clamp-2'}
						"
					>
						{isExpanded
							? subagent.initial_prompt
							: truncate(subagent.initial_prompt, 200)}
					</p>
				{/if}
			</div>
		</div>

		<!-- Stats row -->
		<div class="mt-4 flex items-center gap-4 text-xs text-[var(--text-muted)]">
			<div class="flex items-center gap-1.5">
				<MessageSquare size={14} strokeWidth={2} />
				<span class="tabular-nums">{subagent.message_count} messages</span>
			</div>
			<div class="flex items-center gap-1.5">
				<Wrench size={14} strokeWidth={2} />
				<span class="tabular-nums">{totalToolCalls} tool calls</span>
			</div>
			{#if allTools.length > 0}
				<div class="flex items-center gap-1.5">
					<Hash size={14} strokeWidth={2} />
					<span class="tabular-nums">{allTools.length} unique</span>
				</div>
			{/if}
		</div>

		<!-- Tool pills - collapsed view -->
		{#if !isExpanded && topTools.length > 0}
			<div class="mt-3 flex flex-wrap gap-1.5">
				{#each topTools as [tool, count]}
					<span
						class="inline-flex items-center gap-1 rounded-md bg-[var(--bg-muted)] border border-[var(--border)] px-2 py-0.5 text-xs"
					>
						<span class="text-[var(--text-primary)]">{tool}</span>
						<span class="text-[var(--text-muted)] tabular-nums">×{count}</span>
					</span>
				{/each}
				{#if hasMoreTools}
					<span
						class="inline-flex items-center rounded-md bg-[var(--bg-muted)] border border-[var(--border)] px-2 py-0.5 text-xs text-[var(--text-muted)]"
					>
						+{allTools.length - 5} more
					</span>
				{/if}
			</div>
		{/if}
	</div>

	<!-- Expanded content -->
	<div
		class="
			grid transition-all duration-200 ease-in-out
			{isExpanded ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0'}
		"
	>
		<div class="overflow-hidden">
			<div class="border-t border-[var(--border)] px-4 pl-5 pb-4 pt-3">
				<!-- All tools section -->
				{#if allTools.length > 0}
					<div>
						<div
							class="flex items-center gap-1.5 text-xs font-medium text-[var(--text-primary)] mb-2"
						>
							<Sparkles size={14} strokeWidth={2} style="color: {colorVars.color};" />
							All Tools Used
						</div>
						<div class="flex flex-wrap gap-1.5">
							{#each allTools as [tool, count]}
								<span
									class="inline-flex items-center gap-1 rounded-md bg-[var(--bg-muted)] border border-[var(--border)] px-2.5 py-1 text-xs"
								>
									<span class="text-[var(--text-primary)] font-medium"
										>{tool}</span
									>
									<span class="text-[var(--text-muted)] tabular-nums"
										>×{count}</span
									>
								</span>
							{/each}
						</div>
					</div>
				{/if}

				<!-- Slug detail - only show if slug exists -->
				{#if subagent.slug}
					<div class="mt-4 flex items-center gap-2 text-xs">
						<span class="text-[var(--text-muted)]">Slug:</span>
						<code
							class="rounded bg-[var(--bg-muted)] px-1.5 py-0.5 font-mono text-[var(--text-primary)]"
						>
							{subagent.slug}
						</code>
					</div>
				{/if}

				<!-- Transcript link (when available) -->
				{#if transcript_path}
					<div class="mt-4 flex items-center gap-2 text-xs">
						<FileCode size={12} strokeWidth={2} class="text-[var(--text-muted)]" />
						<span class="text-[var(--text-muted)]">Transcript:</span>
						<code
							class="rounded bg-[var(--bg-muted)] px-1.5 py-0.5 font-mono text-[var(--text-primary)] text-[10px] truncate max-w-[200px]"
							title={transcript_path}
						>
							{transcript_path.split('/').pop()}
						</code>
					</div>
				{/if}
			</div>
		</div>
	</div>
</div>
