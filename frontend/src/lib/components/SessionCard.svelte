<script lang="ts">
	import { MessageSquare, Users, Clock, Sparkles, GitBranch, Monitor } from 'lucide-svelte';
	import type { SessionSummary, LiveSessionSummary } from '$lib/api-types';
	import { statusConfig } from '$lib/live-session-config';
	import {
		formatRelativeTime,
		formatDuration as formatDurationUtil,
		getModelDisplayName,
		getModelBadgeLabel,
		getModelColor,
		modelColorConfig,
		getSessionDisplayName,
		sessionHasTitle,
		getSessionDisplayPrompt
	} from '$lib/utils';
	import { getSessionUrlIdentifier } from '$lib/utils/sessionIdentifier';

	interface Props {
		session: SessionSummary;
		projectEncodedName: string;
		showBranch?: boolean; // Hide branch when inside branch accordion
		compact?: boolean; // Compact mode for grid view
		liveSession?: LiveSessionSummary | null; // Live session data for real-time status
		highlighted?: boolean;
	}

	let {
		session,
		projectEncodedName,
		showBranch = true,
		compact = false,
		liveSession = null,
		highlighted = false
	}: Props = $props();

	// Determine status (default to completed if not specified)
	const status = $derived(session.status || (session.duration_seconds ? 'completed' : 'active'));

	const modelColor = $derived(getModelColor(session.models_used));

	// Local formatDuration that returns null instead of '--' for card display
	function formatDuration(seconds?: number) {
		if (!seconds) return null;
		const result = formatDurationUtil(seconds);
		return result === '--' ? null : result;
	}

	const hasBranch = $derived(
		showBranch && session.git_branches && session.git_branches.length > 0
	);

	// Live session status handling
	const hasLiveStatus = $derived(liveSession !== null);
	const liveStatusConfig = $derived(
		liveSession && liveSession.status in statusConfig ? statusConfig[liveSession.status] : null
	);

	// Check if this is a recently ended session (within 45 min) - should use model colors
	const isRecentlyEnded = $derived(liveSession?.status === 'ended');

	// Background color:
	// - Active live status (not ended) → status tint
	// - Recently ended (≤45 min) → default bg (model-based)
	// - Old sessions (no live data) → faint gray tint
	const cardBackground = $derived(
		hasLiveStatus
			? isRecentlyEnded
				? 'var(--bg-subtle)' // Recently ended → default
				: (liveStatusConfig?.bgTint ?? 'var(--bg-subtle)') // Active → status tint
			: 'var(--status-ended-bg)' // Old → faint gray
	);

	// Left border color:
	// - Active live status (not ended) → status color
	// - Recently ended (≤45 min) → model color
	// - Old sessions → faint gray
	const leftBorderColor = $derived(
		hasLiveStatus
			? isRecentlyEnded
				? modelColorConfig[modelColor].border // Recently ended → model
				: (liveStatusConfig?.color ?? modelColorConfig[modelColor].border) // Active → status
			: 'var(--text-faint)' // Old → faint
	);

	// Ring color for live sessions (used for subtle ring highlight)
	const ringColor = $derived(liveStatusConfig?.color ?? 'var(--success)');

	// Use live stats when available, fallback to session data
	const displayDuration = $derived(liveSession?.duration_seconds ?? session.duration_seconds);
	const displayMessageCount = $derived(liveSession?.message_count ?? session.message_count);
	const displaySubagentCount = $derived(liveSession?.subagent_count ?? session.subagent_count);
	const displaySlug = $derived(liveSession?.slug ?? session.slug);

	// Session title display (shared logic from utils)
	const hasTitle = $derived(sessionHasTitle(session.session_titles, session.chain_title));
	const displayName = $derived(
		getSessionDisplayName(
			session.session_titles,
			displaySlug,
			session.uuid,
			session.chain_title
		)
	);
	const displayPrompt = $derived(
		getSessionDisplayPrompt(session.initial_prompt, session.session_titles)
	);

	// Determine URL identifier:
	// - If session is part of a chain (chain_info exists), use UUID to disambiguate
	// - Otherwise, use slug for human-readable URLs, or UUID prefix as fallback
	// Shared with last-opened-highlight comparisons via sessionIdentifier helper.
	const urlIdentifier = $derived(getSessionUrlIdentifier(session, liveSession));

	// Build live status text for accessibility
	const liveStatusText = $derived(
		hasLiveStatus && liveSession?.status ? `, status: ${liveSession.status}` : ''
	);
</script>

<a
	href="/projects/{projectEncodedName}/{urlIdentifier}"
	aria-label="Session {displayName}, {displayMessageCount} messages{liveStatusText}"
	class="
		flex flex-col h-full
		border border-l-[3px] border-[var(--border)]
		rounded-[var(--radius-md)]
		no-underline
		transition-all
		hover:shadow-md
		group
		focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]
		{hasLiveStatus && !isRecentlyEnded ? 'ring-1 ring-opacity-50' : ''}
		{highlighted ? 'session-highlight' : ''}
		overflow-hidden
	"
	style="
		background-color: {cardBackground};
		border-left-color: {leftBorderColor};
		{hasLiveStatus && !isRecentlyEnded ? `--tw-ring-color: ${ringColor};` : ''}
		transition-duration: var(--duration-fast);
		transition-timing-function: var(--ease);
	"
	data-list-item
>
	{#if compact}
		<!-- COMPACT MODE: Minimal layout for dense grid -->
		<div class="p-3 pl-4">
			<div class="flex items-center gap-2 mb-1.5">
				<!-- Model Icon (smaller) -->
				<div
					class="flex h-6 w-6 items-center justify-center rounded shrink-0"
					style="background-color: {modelColorConfig[modelColor].iconBg};"
				>
					<Sparkles
						size={12}
						strokeWidth={2}
						class={modelColorConfig[modelColor].sparkle}
					/>
				</div>

				<!-- Session Name (title → slug → uuid) -->
				<span
					class="text-xs font-medium truncate flex-1"
					class:text-[var(--accent)]={hasTitle}
					class:text-[var(--text-secondary)]={!hasTitle}
					class:italic={!hasTitle}
					class:font-mono={!hasTitle && !displaySlug}
				>
					{displayName}
				</span>

				<!-- Time: show "ended X ago" for recently ended, otherwise start time -->
				<span class="text-[10px] text-[var(--text-muted)] tabular-nums shrink-0">
					{#if isRecentlyEnded && liveSession?.updated_at}
						ended {formatRelativeTime(liveSession.updated_at)}
					{:else}
						{formatRelativeTime(session.start_time)}
					{/if}
				</span>
			</div>

			<!-- Branch + Key Stats -->
			<div class="flex items-center gap-2 text-[10px] text-[var(--text-muted)]">
				{#if hasBranch}
					<div class="flex items-center gap-1 truncate">
						<GitBranch size={10} strokeWidth={2} class="text-[var(--nav-teal)]" />
						<span class="truncate" title={session.git_branches[0]}
							>{session.git_branches[0]}</span
						>
					</div>
					<span class="text-[var(--text-faint)]">·</span>
				{/if}
				<div class="flex items-center gap-1">
					<MessageSquare size={10} strokeWidth={2} class="text-[var(--nav-blue)]" />
					<span class="tabular-nums">{displayMessageCount}</span>
				</div>
				{#if displaySubagentCount > 0}
					<div class="flex items-center gap-1">
						<Users size={10} strokeWidth={2} class="text-[var(--nav-purple)]" />
						<span class="tabular-nums">{displaySubagentCount}</span>
					</div>
				{/if}
			</div>

			{#if displayPrompt}
				<p class="text-[10px] text-[var(--text-muted)] truncate mt-1" title={displayPrompt}>
					{displayPrompt}
				</p>
			{/if}
			{#if session.session_source === 'desktop'}
				<div
					class="flex items-center gap-0.5 mt-1 text-[10px] text-[var(--text-muted)]"
					title="Claude Desktop session"
				>
					<Monitor size={10} strokeWidth={2} />
					<span>Desktop</span>
				</div>
			{/if}
		</div>
	{:else}
		<!-- FULL MODE: Original detailed layout -->
		<!-- HEADER ZONE: Primary identification -->
		<div class="p-4 pb-3 pl-5">
			<!-- Top Row: Icon + Name + Time -->
			<div class="flex items-start gap-3">
				<!-- Model Icon with colored background -->
				<div
					class="flex h-8 w-8 items-center justify-center rounded-lg shrink-0 transition-colors"
					style="background-color: {modelColorConfig[modelColor].iconBg};"
				>
					<Sparkles
						size={16}
						strokeWidth={2}
						class={modelColorConfig[modelColor].sparkle}
					/>
				</div>

				<div class="flex-1 min-w-0">
					<div class="flex items-center justify-between gap-2 mb-0.5">
						<!-- Session Name (title → slug → uuid) -->
						<div class="flex items-center gap-2 min-w-0">
							<span
								class="text-sm font-medium truncate"
								class:text-[var(--accent)]={hasTitle}
								class:text-[var(--text-secondary)]={!hasTitle}
								class:italic={!hasTitle}
								class:font-mono={!hasTitle && !displaySlug}
							>
								{displayName}
							</span>
						</div>

						<!-- Timestamp: show "ended X ago" for recently ended, otherwise "started X ago" -->
						<span class="text-xs text-[var(--text-muted)] tabular-nums shrink-0">
							{#if isRecentlyEnded && liveSession?.updated_at}
								ended {formatRelativeTime(liveSession.updated_at)}
							{:else}
								{formatRelativeTime(session.start_time)}
							{/if}
						</span>
					</div>

					<!-- Branch Badge (when showBranch is true) -->
					{#if hasBranch}
						<div class="flex items-center gap-1.5">
							<GitBranch size={12} strokeWidth={2} class="text-[var(--nav-teal)]" />
							<span class="text-xs font-medium text-[var(--text-secondary)] truncate">
								{session.git_branches[0]}
							</span>
						</div>
					{/if}
				</div>
			</div>
		</div>

		<!-- BODY ZONE: Context/prompt -->
		<div class="px-4 pb-4 pl-5 flex-grow">
			{#if displayPrompt}
				<p
					class="text-sm text-[var(--text-secondary)] leading-relaxed line-clamp-2 bg-[var(--bg-muted)] px-2 py-1.5 rounded-md"
				>
					{displayPrompt}
				</p>
			{:else}
				<p class="text-sm text-[var(--text-muted)] italic">No prompt recorded</p>
			{/if}
		</div>

		<!-- FOOTER ZONE: Stats row -->
		<div
			class="px-4 py-2.5 pl-5 border-t border-[var(--border)] flex items-center justify-between gap-3 text-xs text-[var(--text-muted)]"
		>
			<!-- Stats Group (compact: icon + number only) -->
			<div class="flex items-center gap-3">
				<!-- Messages -->
				<div class="flex items-center gap-1" title="{displayMessageCount} messages">
					<MessageSquare size={13} strokeWidth={2} class="text-[var(--nav-blue)]" />
					<span class="tabular-nums font-medium">{displayMessageCount}</span>
				</div>

				<!-- Duration (live-updated for active sessions) -->
				{#if formatDuration(displayDuration)}
					<div
						class="flex items-center gap-1"
						title="Duration: {formatDuration(displayDuration)}"
					>
						<Clock size={13} strokeWidth={2} class="text-[var(--nav-orange)]" />
						<span class="tabular-nums font-medium"
							>{formatDuration(displayDuration)}</span
						>
					</div>
				{/if}

				<!-- Subagents -->
				{#if displaySubagentCount > 0}
					<div class="flex items-center gap-1" title="{displaySubagentCount} agents">
						<Users size={13} strokeWidth={2} class="text-[var(--nav-purple)]" />
						<span class="tabular-nums font-medium">{displaySubagentCount}</span>
					</div>
				{/if}
			</div>

			<!-- Badges -->
			<div class="flex items-center gap-1.5 shrink-0">
				{#if session.session_source === 'desktop'}
					<div
						class="flex items-center gap-1 px-2 py-0.5 rounded-full border bg-[var(--bg-muted)] text-[var(--text-secondary)] border-[var(--border)]"
						title="Claude Desktop session"
					>
						<Monitor size={10} strokeWidth={2} />
						<span class="font-medium text-[11px]">Desktop</span>
					</div>
				{/if}
				<!-- Model Badge -->
				<div
					class="flex items-center gap-1 px-2 py-0.5 rounded-full border {modelColorConfig[
						modelColor
					].badge}"
				>
					<Sparkles
						size={10}
						strokeWidth={2}
						class={modelColorConfig[modelColor].sparkle}
					/>
					<span class="font-medium text-[var(--text-secondary)] text-[11px]"
						>{getModelBadgeLabel(session.models_used[0] || '')}</span
					>
				</div>
			</div>
		</div>
	{/if}
</a>
