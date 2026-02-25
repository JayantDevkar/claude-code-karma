<script lang="ts">
	import {
		Calendar,
		Clock,
		ArrowLeft,
		Bot,
		Search,
		FileText,
		Terminal,
		Zap,
		RefreshCw,
		Minimize2,
		MessageCircle,
		Monitor
	} from 'lucide-svelte';
	import { fade } from 'svelte/transition';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import type {
		ConversationEntity,
		LiveSessionSummary,
		LiveSessionStatus,
		SubagentStatus
	} from '$lib/api-types';
	import { isSubagentSession, isMainSession } from '$lib/api-types';
	import {
		formatDateFull,
		formatDuration,
		formatTokens,
		getProjectName,
		getSubagentColorVars,
		getSubagentTypeDisplayName,
		cleanAgentIdForDisplay,
		getEffectiveSubagentType,
		getSessionDisplayName,
		sessionHasTitle
	} from '$lib/utils';

	interface Props {
		entity: ConversationEntity;
		encodedName: string;
		sessionSlug: string;
		projectPath?: string;
		parentSessionSlug?: string;
		liveStatus?: LiveSessionSummary | null;
		isRefreshing?: boolean;
	}

	let {
		entity,
		encodedName,
		sessionSlug,
		projectPath,
		parentSessionSlug,
		liveStatus,
		isRefreshing = false
	}: Props = $props();

	// Debounced refresh indicator - ensures minimum visibility duration
	const MIN_DISPLAY_MS = 600;
	let showRefreshIndicator = $state(false);
	let hideTimeout: ReturnType<typeof setTimeout> | null = null;
	let showStartTime: number | null = null;

	$effect(() => {
		if (isRefreshing) {
			// Clear any pending hide
			if (hideTimeout) {
				clearTimeout(hideTimeout);
				hideTimeout = null;
			}
			showRefreshIndicator = true;
			showStartTime = Date.now();
		} else if (showRefreshIndicator) {
			// Calculate remaining time to meet minimum display
			const elapsed = showStartTime ? Date.now() - showStartTime : 0;
			const remaining = Math.max(0, MIN_DISPLAY_MS - elapsed);

			hideTimeout = setTimeout(() => {
				showRefreshIndicator = false;
				showStartTime = null;
			}, remaining);
		}

		return () => {
			if (hideTimeout) {
				clearTimeout(hideTimeout);
			}
		};
	});

	// Status configuration for live sessions
	const statusConfig: Record<
		LiveSessionStatus,
		{ color: string; label: string; pulse: boolean }
	> = {
		starting: { color: 'var(--nav-purple)', label: 'starting', pulse: true },
		active: { color: 'var(--success)', label: 'active', pulse: true },
		idle: { color: 'var(--warning)', label: 'idle', pulse: false },
		waiting: { color: 'var(--info)', label: 'waiting', pulse: false },
		stopped: { color: 'var(--text-muted)', label: 'stopped', pulse: false },
		stale: { color: 'var(--error)', label: 'stale', pulse: false },
		ended: { color: 'var(--text-faint)', label: 'ended', pulse: false }
	};

	// Status configuration for subagents (independent from parent session)
	const subagentStatusConfig: Record<
		SubagentStatus,
		{ color: string; label: string; pulse: boolean }
	> = {
		running: { color: 'var(--success)', label: 'running', pulse: true },
		completed: { color: 'var(--info)', label: 'completed', pulse: false },
		error: { color: 'var(--error)', label: 'error', pulse: false }
	};

	// Derive subagent's own status from parent session's liveStatus.subagents
	let subagentLiveStatus = $derived.by(() => {
		if (!isSubagentSession(entity) || !liveStatus) return null;
		const agentId = entity.agent_id;
		// Look up this subagent's status in the parent's subagents dict
		const agentState = liveStatus.subagents?.[agentId];
		return agentState || null;
	});

	// Derive values based on entity type
	// Title: prioritize session_titles[0] → slug → uuid
	// For subagents, clean the agent ID for display (removes system prefixes)
	let title = $derived.by(() => {
		if (isSubagentSession(entity)) {
			return cleanAgentIdForDisplay(entity.agent_id);
		}
		return getSessionDisplayName(
			entity.session_titles,
			entity.slug,
			entity.uuid,
			entity.chain_title
		);
	});

	// Check if we have a session title (to show slug as badge)
	let hasSessionTitle = $derived(
		!isSubagentSession(entity) && sessionHasTitle(entity.session_titles, entity.chain_title)
	);

	// Effective subagent type - use API value or infer from agent_id for system agents
	let effectiveSubagentType = $derived.by(() => {
		if (!isSubagentSession(entity)) return null;
		return getEffectiveSubagentType(entity.subagent_type, entity.agent_id);
	});

	let subtitle = $derived.by(() => {
		if (isSubagentSession(entity)) {
			return getSubagentTypeDisplayName(effectiveSubagentType);
		}
		return `#${entity.uuid?.slice(0, 8)}`;
	});

	let breadcrumbs = $derived.by(() => {
		const base = [
			{ label: 'Dashboard', href: '/' },
			{ label: 'Projects', href: '/projects' },
			{
				label: getProjectName(projectPath || ''),
				href: `/projects/${encodedName}`
			}
		];

		if (isSubagentSession(entity)) {
			return [
				...base,
				{
					label: parentSessionSlug || sessionSlug,
					href: `/projects/${encodedName}/${sessionSlug}`
				},
				{ label: `Agent ${entity.agent_id}` }
			];
		}

		return [...base, { label: entity.slug || entity.uuid?.slice(0, 8) || 'Session' }];
	});

	let metadata = $derived.by(() => {
		const items: { icon: typeof Calendar; text: string; class: string }[] = [];

		const startTime = isSubagentSession(entity) ? entity.start_time : entity.start_time;
		const duration = entity.duration_seconds;

		if (startTime) {
			items.push({ icon: Calendar, text: formatDateFull(startTime), class: 'font-mono' });
		}
		if (duration) {
			items.push({ icon: Clock, text: formatDuration(duration), class: 'font-mono' });
		}

		return items;
	});

	// Subagent type badge (only for subagents)
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

	let colorVars = $derived(
		isSubagentSession(entity) ? getSubagentColorVars(effectiveSubagentType) : null
	);
	let typeIcon = $derived(isSubagentSession(entity) ? getTypeIcon(effectiveSubagentType) : null);
</script>

<!-- Agent Session Header with colored background -->
{#if isSubagentSession(entity) && colorVars}
	<div
		class="rounded-lg p-4 -mx-4 mb-4"
		style="background: {colorVars.subtle}; border: 1px solid color-mix(in srgb, {colorVars.color} 20%, transparent);"
	>
		<div class="space-y-4">
			<!-- Header Row -->
			<PageHeader {title} {breadcrumbs} {subtitle} {metadata} class="mb-0">
				{#snippet badges()}
					{#if effectiveSubagentType && typeIcon}
						{@const TypeIconComponent = typeIcon}
						<a
							href="/agents/{encodeURIComponent(
								effectiveSubagentType
							)}?tab=history&project={encodeURIComponent(encodedName)}"
							class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full transition-opacity hover:opacity-80"
							style="background: color-mix(in srgb, {colorVars.color} 15%, white); border: 1px solid color-mix(in srgb, {colorVars.color} 40%, transparent);"
							title="View all sessions using {getSubagentTypeDisplayName(
								effectiveSubagentType
							)}"
						>
							<TypeIconComponent
								size={14}
								strokeWidth={2}
								style="color: {colorVars.color}"
							/>
							<span class="text-xs font-medium" style="color: {colorVars.color}">
								{getSubagentTypeDisplayName(effectiveSubagentType)}
							</span>
						</a>
					{/if}
				{/snippet}
				{#snippet headerRight()}
					<div class="flex items-center gap-2">
						{#if showRefreshIndicator}
							<div
								class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[var(--info)]/10 border border-[var(--info)]/30"
								title="Syncing live data..."
								transition:fade={{ duration: 200 }}
							>
								<RefreshCw
									size={12}
									strokeWidth={2.5}
									class="text-[var(--info)] animate-spin"
								/>
								<span class="text-xs font-medium text-[var(--info)]">
									Syncing
								</span>
							</div>
						{/if}
						<!-- Show subagent's own status (running/completed/error), not parent session's -->
						{#if subagentLiveStatus}
							{@const config = subagentStatusConfig[subagentLiveStatus.status]}
							<div
								class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full"
								style="background: color-mix(in srgb, {config.color} 10%, transparent); border: 1px solid color-mix(in srgb, {config.color} 30%, transparent);"
								title="Agent status (independent from parent session)"
							>
								<span
									class="w-2 h-2 rounded-full"
									class:animate-pulse={config.pulse}
									style="background: {config.color}"
								></span>
								<span
									class="text-xs font-medium uppercase tracking-wide"
									style="color: {config.color}"
								>
									{config.label}
								</span>
							</div>
						{/if}
					</div>
				{/snippet}
			</PageHeader>

			<!-- Navigation Links -->
			<div class="flex items-center gap-2">
				<a
					href="/projects/{encodedName}/{sessionSlug}?tab=agents"
					class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium rounded-md border transition-colors hover:opacity-90"
					style="background: color-mix(in srgb, {colorVars.color} 10%, white); border-color: color-mix(in srgb, {colorVars.color} 30%, transparent); color: {colorVars.color};"
				>
					<ArrowLeft size={16} strokeWidth={2} />
					Back to Session
				</a>
				{#if effectiveSubagentType}
					<a
						href="/agents/{encodeURIComponent(
							effectiveSubagentType
						)}?tab=history&project={encodeURIComponent(encodedName)}"
						class="inline-flex items-center gap-2 px-3 py-1.5 text-sm font-medium rounded-md border transition-colors hover:opacity-90"
						style="background: color-mix(in srgb, {colorVars.color} 10%, white); border-color: color-mix(in srgb, {colorVars.color} 30%, transparent); color: {colorVars.color};"
					>
						<Bot size={16} strokeWidth={2} />
						All {getSubagentTypeDisplayName(effectiveSubagentType)} Sessions
					</a>
				{/if}
			</div>
		</div>
	</div>
{:else}
	<!-- Regular Session Header -->
	<div class="space-y-4">
		<PageHeader {title} {breadcrumbs} {subtitle} {metadata} class="mb-0">
			{#snippet badges()}
				<!-- Badges Container - keeps slug and compaction badges side by side -->
				<div class="flex items-center gap-2 flex-wrap">
					<!-- Slug Badge (show slug when title is displayed as header) -->
					{#if hasSessionTitle && entity.slug}
						<div
							class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[var(--bg-muted)] border border-[var(--border)]"
							title="Session slug: {entity.slug}"
						>
							<span class="text-xs font-mono text-[var(--text-muted)]">
								{entity.slug}
							</span>
						</div>
					{/if}
					<!-- Compaction Badge (if session was compacted) -->
					{#if isMainSession(entity) && entity.was_compacted}
						{@const compactionCount = entity.compaction_summary_count || 1}
						{@const lastCompaction =
							entity.compaction_summaries?.[entity.compaction_summaries.length - 1]}
						{@const trigger =
							typeof lastCompaction === 'object' ? lastCompaction?.trigger : null}
						{@const preTokens =
							typeof lastCompaction === 'object' ? lastCompaction?.pre_tokens : null}
						<div
							class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[var(--nav-orange-subtle)] border border-[var(--nav-orange)]/30"
							title="Context was compacted {compactionCount} time{compactionCount > 1
								? 's'
								: ''}{trigger ? ` (${trigger})` : ''}{preTokens
								? ` - ${formatTokens(preTokens)} tokens before`
								: ''}"
						>
							<Zap size={12} strokeWidth={2} class="text-[var(--nav-orange)]" />
							<span class="text-xs font-medium text-[var(--nav-orange)]">
								{#if trigger === 'auto'}
									Auto Compacted
								{:else if trigger === 'manual'}
									Compacted
								{:else}
									Compacted
								{/if}
								{#if compactionCount > 1}
									<span class="opacity-70">×{compactionCount}</span>
								{/if}
							</span>
						</div>
					{/if}
					<!-- Desktop Badge (if session is from Claude Desktop) -->
					{#if isMainSession(entity) && entity.session_source === 'desktop'}
						<div
							class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[var(--bg-muted)] border border-[var(--border)]"
							title="Claude Desktop session"
						>
							<Monitor
								size={12}
								strokeWidth={2}
								class="text-[var(--text-secondary)]"
							/>
							<span class="text-xs font-medium text-[var(--text-secondary)]"
								>Desktop</span
							>
						</div>
					{/if}
				</div>
			{/snippet}
			{#snippet headerRight()}
				<div class="flex items-center gap-2">
					{#if showRefreshIndicator}
						<div
							class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[var(--info)]/10 border border-[var(--info)]/30"
							title="Syncing live data..."
							transition:fade={{ duration: 200 }}
						>
							<RefreshCw
								size={12}
								strokeWidth={2.5}
								class="text-[var(--info)] animate-spin"
							/>
							<span class="text-xs font-medium text-[var(--info)]"> Syncing </span>
						</div>
					{/if}
					{#if liveStatus && liveStatus.status !== 'ended'}
						{@const config = statusConfig[liveStatus.status]}
						<div
							class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full"
							style="background: color-mix(in srgb, {config.color} 10%, transparent); border: 1px solid color-mix(in srgb, {config.color} 30%, transparent);"
						>
							<span
								class="w-2 h-2 rounded-full"
								class:animate-pulse={config.pulse}
								style="background: {config.color}"
							></span>
							<span
								class="text-xs font-medium uppercase tracking-wide"
								style="color: {config.color}"
							>
								{config.label}
							</span>
						</div>
					{/if}
				</div>
			{/snippet}
		</PageHeader>
	</div>
{/if}
