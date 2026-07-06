<script lang="ts">
	import { onMount } from 'svelte';
	import { Copy, Check, ChevronLeft, ChevronRight, Zap, ExternalLink } from 'lucide-svelte';
	import { keyboardOverrides } from '$lib/stores/keyboardOverrides';
	import { marked } from 'marked';
	import DOMPurify from 'isomorphic-dompurify';
	import type { TimelineEvent } from '$lib/api-types';
	import { createTimelineLogic } from '$lib/utils/timelineLogic.svelte';
	import { groupIntoTurns, type TurnGroup } from '$lib/utils/groupIntoTurns';
	import { formatDate } from '$lib/utils';
	import TurnCard from './TurnCard.svelte';
	import TimelineMinimap from './TimelineMinimap.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import ToolCallDetail from './ToolCallDetail.svelte';
	import TodoUpdateDetail from './TodoUpdateDetail.svelte';
	import ImageAttachments from '$lib/components/ImageAttachments.svelte';
	import { markdownCopyButtons } from '$lib/actions/markdownCopyButtons';

	interface Props {
		events: TimelineEvent[];
		isLive?: boolean;
		isTailing?: boolean;
		onToggleTailing?: () => void;
		currentAgentId?: string | null;
		projectPath?: string | null;
		class?: string;
		searchQuery?: string;
		onSearchMatchCount?: (count: number) => void;
		onCurrentMatchChange?: (index: number) => void;
		projectEncoded?: string;
		sessionSlug?: string;
		sessionUuid?: string;
	}

	let {
		events,
		isLive = false,
		isTailing = false,
		onToggleTailing,
		currentAgentId = null,
		projectPath = null,
		class: className = '',
		searchQuery = '',
		onSearchMatchCount,
		onCurrentMatchChange,
		projectEncoded,
		sessionSlug,
		sessionUuid
	}: Props = $props();

	// ── Density toggle ────────────────────────────────────────────────
	type Density = 'compact' | 'normal' | 'expanded';
	let density = $state<Density>('normal');

	// ── Turn grouping ─────────────────────────────────────────────────
	const sessionStartTs = $derived(events[0]?.timestamp ?? new Date().toISOString());

	const turns = $derived(groupIntoTurns(events, sessionStartTs, isLive));

	// ── Search (simple turn-level filter) ─────────────────────────────
	// Keep createTimelineLogic for counts + search query state
	const timeline = createTimelineLogic(() => events, {
		isTailingGetter: () => isTailing,
		tailCount: 3,
		currentAgentIdGetter: () => currentAgentId
	});

	$effect(() => {
		if (searchQuery) timeline.setSearchQuery(searchQuery);
	});

	const activeSearch = $derived(timeline.searchQuery.trim().toLowerCase());

	const filteredTurns = $derived.by<TurnGroup[]>(() => {
		if (!activeSearch) return turns;
		return turns.filter((turn) => {
			const texts = [turn.prompt, turn.response, ...turn.workEvents]
				.flatMap((ev) =>
					ev
						? [
								ev.summary ?? '',
								ev.title ?? '',
								(ev.metadata?.full_content as string | undefined) ?? '',
								(ev.metadata?.full_text as string | undefined) ?? '',
								(ev.metadata?.full_thinking as string | undefined) ?? ''
							]
						: []
				)
				.join(' ')
				.toLowerCase();
			return texts.includes(activeSearch);
		});
	});

	// Notify parent of search match count
	$effect(() => { onSearchMatchCount?.(filteredTurns.length); });

	// ── Session stats ──────────────────────────────────────────────────
	const countPrompt = $derived(timeline.counts.prompt ?? 0);
	const countTool = $derived(timeline.counts.tool_call ?? 0);
	const countAgent = $derived(timeline.counts.subagent ?? 0);
	const countError = $derived(timeline.counts.error ?? 0);

	const sessionDuration = $derived.by(() => {
		if (events.length < 2) return '';
		const ms =
			new Date(events[events.length - 1].timestamp).getTime() -
			new Date(events[0].timestamp).getTime();
		if (ms <= 0) return '';
		const min = Math.floor(ms / 60000);
		return min > 0 ? `${min}m` : `${Math.floor((ms % 60000) / 1000)}s`;
	});

	// ── Popup ─────────────────────────────────────────────────────────
	let popupEvent = $state<TimelineEvent | null>(null);
	const isPopupOpen = $derived(popupEvent !== null);
	let isCopied = $state(false);
	let renderedPopupContent = $state('');

	$effect(() => {
		if (popupEvent) {
			const raw =
				(popupEvent.metadata?.full_content as string | undefined) ??
				(popupEvent.metadata?.full_thinking as string | undefined) ??
				(popupEvent.metadata?.full_text as string | undefined) ??
				(popupEvent.metadata?.result_content as string | undefined) ??
				popupEvent.summary ??
				'';
			const parsed = marked.parse(raw);
			if (parsed instanceof Promise) {
				parsed.then((html) => { renderedPopupContent = DOMPurify.sanitize(html); });
			} else {
				renderedPopupContent = DOMPurify.sanitize(parsed);
			}
		}
	});

	function openPopup(event: TimelineEvent) {
		popupEvent = event;
		isCopied = false;
	}
	function closePopup() {
		popupEvent = null;
		isCopied = false;
	}

	// Popup prev/next within all events
	function isExpandable(ev: TimelineEvent): boolean {
		return !!(
			ev.event_type === 'tool_call' ||
			ev.event_type === 'todo_update' ||
			ev.metadata?.full_content ||
			ev.metadata?.full_thinking ||
			ev.metadata?.full_text ||
			ev.metadata?.result_content ||
			(ev.summary && ev.summary.length > 100)
		);
	}

	const navigableEvents = $derived(events.filter(isExpandable));
	const popupNavIndex = $derived(
		popupEvent ? navigableEvents.findIndex((e) => e.id === popupEvent!.id) : -1
	);
	function navigatePrev() {
		if (popupNavIndex > 0) openPopup(navigableEvents[popupNavIndex - 1]);
	}
	function navigateNext() {
		if (popupNavIndex < navigableEvents.length - 1) openPopup(navigableEvents[popupNavIndex + 1]);
	}

	$effect(() => {
		if (!isPopupOpen) return;
		function onKeyDown(e: KeyboardEvent) {
			if (e.key === 'ArrowLeft') { e.preventDefault(); navigatePrev(); }
			else if (e.key === 'ArrowRight') { e.preventDefault(); navigateNext(); }
		}
		window.addEventListener('keydown', onKeyDown);
		return () => window.removeEventListener('keydown', onKeyDown);
	});

	// ── Tailing ───────────────────────────────────────────────────────
	let prevEventsLength = $state(0);
	let prevIsTailing = $state(false);
	let userScrollTimeout: ReturnType<typeof setTimeout> | null = null;
	let scrollRafId: number | null = null;
	let containerRef = $state<HTMLDivElement | null>(null);
	let timelineContentRef = $state<HTMLDivElement | null>(null);

	function setScrollTimeout(cb: () => void, delay: number) {
		if (userScrollTimeout) clearTimeout(userScrollTimeout);
		userScrollTimeout = setTimeout(cb, delay);
	}

	function scrollToLastTurn(behavior: ScrollBehavior = 'smooth') {
		const turnEls = timelineContentRef?.querySelectorAll('[data-turn-index]');
		if (turnEls && turnEls.length > 0) {
			turnEls[turnEls.length - 1].scrollIntoView({ behavior, block: 'end' });
		}
	}

	function scrollToTurnByIndex(turnIndex: number) {
		const el = timelineContentRef?.querySelector(`[data-turn-index="${turnIndex}"]`);
		if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
	}

	$effect(() => {
		const newEventsArrived = isTailing && events.length > prevEventsLength && timelineContentRef;
		const tailingJustEnabled = isTailing && !prevIsTailing && timelineContentRef;
		if (newEventsArrived) {
			if (scrollRafId) cancelAnimationFrame(scrollRafId);
			scrollRafId = requestAnimationFrame(() => { scrollToLastTurn('smooth'); scrollRafId = null; });
		} else if (tailingJustEnabled) {
			setScrollTimeout(() => scrollToLastTurn('smooth'), 100);
		}
		prevEventsLength = events.length;
		prevIsTailing = isTailing;
		return () => {
			if (scrollRafId) { cancelAnimationFrame(scrollRafId); scrollRafId = null; }
		};
	});

	// ── Mount ─────────────────────────────────────────────────────────
	onMount(() => {
		const unregisterCtrlK = keyboardOverrides.registerCtrlK(() => {
			const searchEl = containerRef?.querySelector<HTMLInputElement>('[data-timeline-search]');
			if (searchEl) { searchEl.focus({ preventScroll: true }); searchEl.select(); }
		});

		// J/K navigate between turns
		function handleJKNav(e: KeyboardEvent) {
			if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
			if (e.metaKey || e.ctrlKey || e.altKey) return;
			if (e.key !== 'j' && e.key !== 'k') return;
			if (isPopupOpen) return;

			const turnEls = Array.from(
				timelineContentRef?.querySelectorAll('[data-event-type="prompt"]') ?? []
			) as HTMLElement[];
			if (turnEls.length === 0) return;

			e.preventDefault();
			const scrollCenter = window.scrollY + window.innerHeight / 2;
			let nearestIdx = 0, nearestDist = Infinity;
			turnEls.forEach((el, idx) => {
				const rect = el.getBoundingClientRect();
				const mid = rect.top + window.scrollY + rect.height / 2;
				const dist = Math.abs(mid - scrollCenter);
				if (dist < nearestDist) { nearestDist = dist; nearestIdx = idx; }
			});
			const dir = e.key === 'j' ? 1 : -1;
			const target = Math.max(0, Math.min(nearestIdx + dir, turnEls.length - 1));
			turnEls[target].scrollIntoView({ behavior: 'smooth', block: 'start' });
		}

		window.addEventListener('keydown', handleJKNav);
		prevEventsLength = events.length;
		prevIsTailing = isTailing;

		let initTimeout: ReturnType<typeof setTimeout> | null = null;
		if (isTailing && timelineContentRef) {
			initTimeout = setTimeout(() => scrollToLastTurn('auto'), 200);
		}

		return () => {
			unregisterCtrlK();
			window.removeEventListener('keydown', handleJKNav);
			if (initTimeout) clearTimeout(initTimeout);
			if (userScrollTimeout) clearTimeout(userScrollTimeout);
			if (scrollRafId) cancelAnimationFrame(scrollRafId);
		};
	});
</script>

{#if events.length === 0}
	<p class="font-mono text-sm text-[var(--text-faint)] px-1 py-2">No events in this session</p>
{:else}
	<div class="relative {className}" bind:this={containerRef}>

		<!-- Search + density toggle header -->
		<div class="flex items-center gap-2 mb-3 px-1">
			<!-- Search input -->
			<div class="flex-1 flex items-center gap-2 border border-[var(--border)] rounded-sm px-2.5 py-1.5 bg-[var(--bg-subtle)] min-w-0">
				<span class="text-[13px] text-[var(--text-faint)] select-none shrink-0">⌕</span>
				<input
					type="text"
					placeholder="Search events..."
					value={timeline.searchQuery}
					oninput={(e) => timeline.setSearchQuery((e.target as HTMLInputElement).value)}
					data-timeline-search
					class="flex-1 bg-transparent border-none outline-none text-[12px] font-mono
						text-[var(--text-primary)] placeholder:text-[var(--text-faint)] min-w-0"
				/>
				{#if timeline.searchQuery}
					<span class="text-[10px] font-mono text-[var(--text-muted)] shrink-0">
						{filteredTurns.length} turn{filteredTurns.length !== 1 ? 's' : ''}
					</span>
					<button
						onclick={() => timeline.setSearchQuery('')}
						class="text-[var(--text-faint)] hover:text-[var(--text-primary)] transition-colors text-[11px] shrink-0"
						aria-label="Clear search"
					>✕</button>
				{:else}
					<span class="text-[10px] font-mono text-[var(--text-faint)] shrink-0">{events.length} events</span>
				{/if}
			</div>

			<!-- Density toggle -->
			<div class="flex border border-[var(--border)] rounded-sm overflow-hidden shrink-0">
				{#each (['compact', 'normal', 'expanded'] as Density[]) as d}
					<button
						type="button"
						onclick={() => (density = d)}
						class="px-2.5 py-1 text-[10px] font-mono transition-colors
							{density === d
								? 'bg-[var(--text-primary)] text-[var(--bg-base)]'
								: 'text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)]'}
							{d !== 'expanded' ? 'border-r border-[var(--border)]' : ''}"
					>
						{d === 'compact' ? 'Compact' : d === 'normal' ? 'Normal' : 'Expanded'}
					</button>
				{/each}
			</div>
		</div>

		<!-- Stats bar -->
		<div class="flex items-center flex-wrap gap-x-0 gap-y-0.5 text-[11px] font-mono mb-4 px-1">
			{#if countPrompt > 0}
				<span class="text-[var(--text-muted)]">
					<span class="text-[var(--text-primary)] opacity-80">{countPrompt}</span>&nbsp;turn{countPrompt !== 1 ? 's' : ''}
				</span>
			{/if}
			{#if countTool > 0}
				{#if countPrompt > 0}<span class="text-[var(--text-faint)] opacity-40 mx-2">·</span>{/if}
				<span class="text-[var(--text-muted)]">
					<span class="text-[var(--text-primary)] opacity-80">{countTool}</span>&nbsp;tools
				</span>
			{/if}
			{#if countAgent > 0}
				<span class="text-[var(--text-faint)] opacity-40 mx-2">·</span>
				<span class="text-[var(--text-muted)]">
					<span class="text-[var(--text-primary)] opacity-80">{countAgent}</span>&nbsp;agent{countAgent !== 1 ? 's' : ''}
				</span>
			{/if}
			{#if countError > 0}
				<span class="text-[var(--text-faint)] opacity-40 mx-2">·</span>
				<span class="text-[var(--error)] opacity-80">{countError}&nbsp;error{countError !== 1 ? 's' : ''}</span>
			{/if}
			{#if sessionDuration}
				<span class="text-[var(--text-faint)] opacity-40 mx-2">·</span>
				<span class="text-[var(--text-faint)] opacity-60">{sessionDuration}</span>
			{/if}
			<span class="text-[var(--text-faint)] opacity-25 mx-2">·</span>
			<span class="text-[var(--text-faint)] opacity-40 text-[10px]">J/K navigate turns</span>
		</div>

		<!-- Turn cards -->
		<div bind:this={timelineContentRef}>
			{#each filteredTurns as turn, i (turn.id)}
				<TurnCard
					{turn}
					{density}
					turnIndex={i}
					onOpenPopup={openPopup}
					{projectPath}
					{projectEncoded}
					{sessionSlug}
					{sessionUuid}
					searchQuery={activeSearch}
				/>
			{/each}

			{#if filteredTurns.length === 0 && activeSearch}
				<p class="text-[11px] font-mono text-[var(--text-faint)] text-center py-8">
					No turns match "{activeSearch}"
				</p>
			{/if}
		</div>

	</div>

	<!-- Minimap -->
	<TimelineMinimap turns={filteredTurns} onScrollTo={scrollToTurnByIndex} />
{/if}

<!-- Event Detail Popup -->
{#if popupEvent}
	<Modal
		open={isPopupOpen}
		onOpenChange={(open) => { if (!open) closePopup(); }}
		title={popupEvent.title}
		description={formatDate(popupEvent.timestamp)}
		maxWidth="xl"
	>
		{#snippet headerActions()}
			<button
				onclick={navigatePrev}
				disabled={popupNavIndex <= 0}
				class="rounded-md p-1 text-[var(--text-muted)] transition-colors hover:text-[var(--text-primary)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] disabled:opacity-30 disabled:cursor-not-allowed"
				aria-label="Previous event"
			>
				<ChevronLeft size={20} />
			</button>
			<span class="text-xs font-mono text-[var(--text-muted)] tabular-nums px-1 select-none">
				{popupNavIndex + 1} / {navigableEvents.length}
			</span>
			<button
				onclick={navigateNext}
				disabled={popupNavIndex >= navigableEvents.length - 1}
				class="rounded-md p-1 text-[var(--text-muted)] transition-colors hover:text-[var(--text-primary)] focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] disabled:opacity-30 disabled:cursor-not-allowed"
				aria-label="Next event"
			>
				<ChevronRight size={20} />
			</button>
		{/snippet}
		{#snippet titleSnippet()}
			{#if popupEvent?.event_type === 'skill_invocation'}
				{@const skillPath = popupEvent.title?.replace(/^Skill:\s*\/?/, '') ?? ''}
				{#if skillPath}
					<a
						href="/skills/{encodeURIComponent(skillPath)}"
						class="flex items-center gap-2 text-[var(--accent)] hover:text-[var(--accent)]/80 transition-colors no-underline group"
					>
						<Zap size={18} class="shrink-0" />
						<span>{popupEvent.title}</span>
						<ExternalLink size={14} class="opacity-50 group-hover:opacity-100 transition-opacity" />
					</a>
				{:else}
					{popupEvent.title}
				{/if}
			{:else if popupEvent?.metadata?.spawned_agent_id && projectEncoded && sessionSlug}
				{@const agentId = String(popupEvent.metadata.spawned_agent_id)}
				{@const agentType = popupEvent.metadata?.subagent_type ? String(popupEvent.metadata.subagent_type) : null}
				<a
					href="/projects/{projectEncoded}/{sessionSlug}/agents/{agentId}"
					class="flex items-center gap-2 text-[var(--text-primary)] hover:text-[var(--event-subagent)] transition-colors no-underline group"
				>
					<span>Spawn subagent{agentType ? ` — ${agentType}` : ''}</span>
					<span class="font-mono text-sm text-[var(--event-subagent)] opacity-70 group-hover:opacity-100">·&nbsp;{agentId.slice(0, 12)}</span>
					<ExternalLink size={13} class="opacity-40 group-hover:opacity-80 transition-opacity" />
				</a>
			{:else}
				{popupEvent?.title}
			{/if}
		{/snippet}

		<div class="max-h-[70vh] overflow-auto break-words">
			{#if popupEvent.event_type === 'tool_call'}
				<ToolCallDetail event={popupEvent} {projectPath} />
			{:else if popupEvent.event_type === 'todo_update'}
				{@const todos = Array.isArray(popupEvent.metadata?.todos) ? popupEvent.metadata.todos : []}
				<TodoUpdateDetail
					{todos}
					action={popupEvent.metadata?.action as 'set' | 'merge' | undefined}
					agentSlug={popupEvent.metadata?.agent_slug as string | undefined}
					isExpanded={true}
				/>
			{:else}
				<div class="rounded bg-[var(--bg-muted)]/50 p-3 relative">
					<button
						class="md-global-copy float-right ml-2 mb-2 p-1.5 rounded-md bg-[var(--bg-base)]
							border border-[var(--border)] text-[var(--text-muted)] shadow-sm
							hover:text-[var(--text-primary)] hover:border-[var(--accent)] transition-colors"
						data-tooltip={isCopied ? 'Copied!' : 'Copy entire response'}
						aria-label={isCopied ? 'Copied!' : 'Copy entire response'}
						onclick={(e) => {
							e.stopPropagation();
							const content =
								(popupEvent?.metadata?.full_content as string | undefined) ??
								(popupEvent?.metadata?.full_thinking as string | undefined) ??
								(popupEvent?.metadata?.full_text as string | undefined) ??
								(popupEvent?.metadata?.result_content as string | undefined) ??
								popupEvent?.summary ?? '';
							navigator.clipboard.writeText(content);
							isCopied = true;
							setTimeout(() => (isCopied = false), 2000);
						}}
					>
						{#if isCopied}
							<Check size={14} class="text-[var(--success)]" />
						{:else}
							<Copy size={14} />
						{/if}
					</button>
					{#if popupEvent.metadata?.image_attachments?.length}
						<ImageAttachments attachments={popupEvent.metadata.image_attachments} />
					{/if}
					<div class="markdown-preview text-sm" use:markdownCopyButtons={renderedPopupContent}>
						{@html renderedPopupContent}
					</div>
				</div>
			{/if}
		</div>
	</Modal>
{/if}
