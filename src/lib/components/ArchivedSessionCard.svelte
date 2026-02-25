<script lang="ts">
	import { MessageSquare, HelpCircle } from 'lucide-svelte';
	import ArchivedPromptCard from './ArchivedPromptCard.svelte';
	import { Modal } from '$lib/components/ui';
	import type { ArchivedSession } from '$lib/api-types';

	interface Props {
		session: ArchivedSession;
		showProject?: boolean;
		projectName?: string;
	}

	let { session, showProject = false, projectName = '' }: Props = $props();
	let modalOpen = $state(false);

	// Check if this card is expandable (has at least 1 prompt)
	let isExpandable = $derived(session.prompt_count >= 1);

	function formatDateRange(dateRange: { start: string; end: string }): string {
		const start = new Date(dateRange.start);
		const end = new Date(dateRange.end);

		const startStr = start.toLocaleDateString('en-US', {
			month: 'short',
			day: 'numeric'
		});

		// If same day, just show one date
		if (start.toDateString() === end.toDateString()) {
			return startStr;
		}

		const endStr = end.toLocaleDateString('en-US', {
			month: 'short',
			day: 'numeric'
		});

		return `${startStr} - ${endStr}`;
	}

	function formatSessionId(sessionId: string, isOrphan: boolean): string {
		if (isOrphan) {
			return 'Unknown Session';
		}
		return sessionId.slice(0, 8);
	}

	function handleToggle() {
		if (isExpandable) {
			modalOpen = true;
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (isExpandable && (e.key === 'Enter' || e.key === ' ')) {
			e.preventDefault();
			modalOpen = true;
		}
	}

	function handleModalOpenChange(isOpen: boolean) {
		modalOpen = isOpen;
	}

	// Build modal title and subtitle with proper hierarchy
	const modalTitle = $derived(() => {
		// Primary: Project name (if available), otherwise date range
		if (showProject && projectName) {
			return projectName;
		}
		return formatDateRange(session.date_range);
	});

	const modalSubtitle = $derived(() => {
		const parts = [];

		// If project name is shown in title, add date range to subtitle
		if (showProject && projectName) {
			parts.push(formatDateRange(session.date_range));
		}

		// Always add prompt count
		parts.push(`${session.prompt_count} ${session.prompt_count === 1 ? 'prompt' : 'prompts'}`);

		return parts.join(' • ');
	});
</script>

<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<div
	class="
		group
		flex flex-col
		h-full
		bg-[var(--bg-base)]
		border border-[var(--border)]
		rounded-[var(--radius-md)]
		transition-all
		hover:border-[var(--border-hover)]
		hover:shadow-sm
		overflow-hidden
		opacity-80
		hover:opacity-100
		{isExpandable ? 'cursor-pointer' : ''}
	"
	style="
		transition-duration: var(--duration-fast);
		transition-timing-function: var(--ease);
	"
	onclick={handleToggle}
	onkeydown={handleKeydown}
	role={isExpandable ? 'button' : undefined}
	tabindex={isExpandable ? 0 : undefined}
>
	<!-- HEADER ZONE: Session ID + Date Range + Expand Icon -->
	<div class="p-4 pb-3 shrink-0">
		<!-- Top Row: Session ID + Date -->
		<div class="flex items-start justify-between gap-3 mb-1">
			<!-- Left: Session ID -->
			<div class="flex items-center min-w-0 flex-1">
				<!-- Session ID or "Unknown Session" -->
				<span
					class="text-base font-semibold font-mono truncate leading-tight {session.is_orphan
						? 'text-[var(--text-muted)] italic'
						: 'text-[var(--text-secondary)]'}"
				>
					{#if session.is_orphan}
						<span class="flex items-center gap-1.5">
							<HelpCircle
								size={14}
								strokeWidth={2}
								class="text-[var(--text-faint)]"
							/>
							Unknown Session
						</span>
					{:else}
						{formatSessionId(session.session_id, session.is_orphan)}
					{/if}
				</span>
			</div>

			<!-- Right: Date Range -->
			<div class="flex items-center shrink-0">
				<span class="text-xs text-[var(--text-muted)]">
					{formatDateRange(session.date_range)}
				</span>
			</div>
		</div>

		<!-- Project Name (when shown) -->
		{#if showProject && projectName}
			<div class="mt-1">
				<span class="text-xs text-[var(--text-muted)] font-mono">
					{projectName}
				</span>
			</div>
		{/if}
	</div>

	<!-- BODY ZONE: First prompt preview -->
	<div class="px-4 pb-3 flex-1">
		<p
			class="text-sm text-[var(--text-secondary)] leading-relaxed bg-[var(--bg-muted)] px-3 py-2 rounded-md line-clamp-2"
		>
			{session.first_prompt_preview}
		</p>
	</div>

	<!-- FOOTER ZONE: Prompt count (shrink-0 keeps at bottom) -->
	<div
		class="px-4 py-3 bg-[rgba(184,84,80,0.06)] border-t border-[rgba(184,84,80,0.15)] flex items-center justify-between shrink-0 mt-auto"
	>
		<!-- Left: Prompt count -->
		<div class="flex items-center gap-1.5 text-xs text-[#B85450]">
			<MessageSquare size={13} strokeWidth={2} />
			<span class="font-mono font-medium">{session.prompt_count}</span>
			<span>{session.prompt_count === 1 ? 'prompt' : 'prompts'}</span>
		</div>

		<!-- Right: View hint for expandable cards -->
		{#if isExpandable}
			<span class="text-xs text-[#B85450]/70"> Click to view all </span>
		{/if}
	</div>
</div>

<!-- Modal for viewing all prompts -->
<Modal
	open={modalOpen}
	onOpenChange={handleModalOpenChange}
	title={modalTitle()}
	description={modalSubtitle()}
	maxWidth="lg"
>
	<div class="space-y-3 max-h-[60vh] overflow-y-auto">
		{#each session.prompts as prompt}
			<ArchivedPromptCard {prompt} compact />
		{/each}
	</div>
</Modal>
