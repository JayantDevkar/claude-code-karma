<script lang="ts">
	import {
		Webhook,
		FolderOpen,
		ShieldAlert,
		ChevronsUpDown,
		ChevronsDownUp,
		Puzzle
	} from 'lucide-svelte';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import StatsGrid from '$lib/components/StatsGrid.svelte';
	import SegmentedControl from '$lib/components/ui/SegmentedControl.svelte';
	import CollapsibleGroup from '$lib/components/ui/CollapsibleGroup.svelte';
	import HookEventNode from '$lib/components/hooks/HookEventNode.svelte';
	import HookScriptCard from '$lib/components/hooks/HookScriptCard.svelte';
	import type { StatItem, HookEventSummary } from '$lib/api-types';
	import { getHookSourceColorVars } from '$lib/utils';

	let { data } = $props();

	// View mode state
	let viewMode = $state<'timeline' | 'sources'>('timeline');

	// Stats for hero section
	let stats = $derived<StatItem[]>([
		{
			title: 'Sources',
			value: data.hooks.stats.total_sources.toLocaleString(),
			icon: FolderOpen,
			color: 'orange'
		},
		{
			title: 'Registrations',
			value: data.hooks.stats.total_registrations.toLocaleString(),
			icon: Webhook,
			color: 'blue'
		},
		{
			title: 'Can Block',
			value: data.hooks.stats.blocking_hooks.toLocaleString(),
			icon: ShieldAlert,
			color: 'orange'
		}
	]);

	// Phase ordering for timeline view
	const PHASE_ORDER = [
		'Session Lifecycle',
		'User Input',
		'Tool Lifecycle',
		'Agent Lifecycle',
		'Context & Permissions',
		'Session End',
		'Setup'
	];

	// Group events by phase
	interface PhaseGroup {
		phase: string;
		events: HookEventSummary[];
	}

	let eventsByPhase = $derived.by<PhaseGroup[]>(() => {
		const grouped = new Map<string, HookEventSummary[]>();

		for (const event of data.hooks.event_summaries) {
			const phase = event.phase || 'Other';
			if (!grouped.has(phase)) {
				grouped.set(phase, []);
			}
			grouped.get(phase)!.push(event);
		}

		// Sort by phase order
		const result: PhaseGroup[] = [];
		for (const phase of PHASE_ORDER) {
			if (grouped.has(phase)) {
				result.push({ phase, events: grouped.get(phase)! });
				grouped.delete(phase);
			}
		}

		// Add any remaining phases not in the order
		for (const [phase, events] of grouped.entries()) {
			result.push({ phase, events });
		}

		return result;
	});

	// Track expanded state for timeline events
	let expandedEvents = $state<Set<string>>(new Set());

	function toggleEvent(eventType: string) {
		if (expandedEvents.has(eventType)) {
			expandedEvents.delete(eventType);
		} else {
			expandedEvents.add(eventType);
		}
		expandedEvents = new Set(expandedEvents);
	}

	let allEventsExpanded = $derived(
		data.hooks.event_summaries.length > 0 &&
			data.hooks.event_summaries.every((e) => expandedEvents.has(e.event_type))
	);

	function expandAllEvents() {
		expandedEvents = new Set(data.hooks.event_summaries.map((e) => e.event_type));
	}

	function collapseAllEvents() {
		expandedEvents = new Set();
	}

	function toggleAllEvents() {
		if (allEventsExpanded) {
			collapseAllEvents();
		} else {
			expandAllEvents();
		}
	}

	// Track expanded state for source groups
	let expandedSources = $state<Set<string>>(new Set());

	function toggleSource(sourceId: string) {
		if (expandedSources.has(sourceId)) {
			expandedSources.delete(sourceId);
		} else {
			expandedSources.add(sourceId);
		}
		expandedSources = new Set(expandedSources);
	}

	let hasHooks = $derived(data.hooks.sources.length > 0 || data.hooks.event_summaries.length > 0);
</script>

<div class="space-y-8">
	<!-- Page Header -->
	<PageHeader
		title="Hooks"
		icon={Webhook}
		iconColor="--nav-amber"
		breadcrumbs={[{ label: 'Dashboard', href: '/' }, { label: 'Hooks' }]}
		subtitle="Hook scripts intercepting your Claude Code sessions"
	/>

	<!-- Hero Stats -->
	{#if hasHooks}
		<div
			class="relative overflow-hidden rounded-2xl p-8 border border-[var(--border)]"
			style="background: linear-gradient(135deg, rgba(217, 119, 6, 0.02) 0%, rgba(217, 119, 6, 0.06) 100%);"
		>
			<div
				class="absolute -top-24 -right-24 w-96 h-96 bg-orange-500/5 rounded-full blur-3xl pointer-events-none"
			></div>
			<div
				class="absolute -bottom-24 -left-24 w-64 h-64 bg-amber-500/3 rounded-full blur-3xl pointer-events-none"
			></div>
			<div class="relative">
				<StatsGrid {stats} columns={3} />
			</div>
		</div>
	{/if}

	<!-- View Switcher -->
	{#if hasHooks}
		<div class="flex items-center justify-between">
			<SegmentedControl
				options={[
					{ label: 'Event Timeline', value: 'timeline' },
					{ label: 'By Source', value: 'sources' }
				]}
				bind:value={viewMode}
			/>

			{#if viewMode === 'timeline' && data.hooks.event_summaries.length > 0}
				<button
					onclick={toggleAllEvents}
					class="
						flex items-center gap-1.5 px-3 py-2
						text-sm font-medium
						text-[var(--text-secondary)]
						hover:text-[var(--text-primary)]
						bg-[var(--bg-base)]
						border border-[var(--border)]
						rounded-lg
						transition-all
						hover:bg-[var(--bg-subtle)]
					"
					title={allEventsExpanded ? 'Collapse all events' : 'Expand all events'}
				>
					{#if allEventsExpanded}
						<ChevronsDownUp size={16} />
						<span>Collapse All</span>
					{:else}
						<ChevronsUpDown size={16} />
						<span>Expand All</span>
					{/if}
				</button>
			{/if}
		</div>
	{/if}

	<!-- Content Area -->
	{#if !hasHooks}
		<div
			class="text-center py-20 bg-[var(--bg-subtle)] rounded-2xl border border-dashed border-[var(--border)]"
		>
			<Webhook class="mx-auto text-[var(--text-muted)] mb-3" size={48} />
			<p class="text-[var(--text-secondary)] font-medium">No hooks found</p>
			<p class="text-sm text-[var(--text-muted)] mt-1">
				Hook scripts will appear here once you configure them
			</p>
		</div>
	{:else if viewMode === 'timeline'}
		<!-- Timeline View -->
		<div class="space-y-8">
			{#each eventsByPhase as phaseGroup}
				<div>
					<!-- Phase Header -->
					<h2
						class="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)] mb-4"
					>
						{phaseGroup.phase}
					</h2>

					<!-- Events in this phase -->
					<div class="space-y-0">
						{#each phaseGroup.events as event (event.event_type)}
							<HookEventNode
								{event}
								open={expandedEvents.has(event.event_type)}
								onToggle={() => toggleEvent(event.event_type)}
							/>
						{/each}
					</div>
				</div>
			{/each}
		</div>
	{:else}
		<!-- By Source View -->
		<div class="space-y-4">
			{#each data.hooks.sources as source (source.source_id)}
				{@const sourceColors = getHookSourceColorVars(
					source.source_type,
					source.source_name
				)}
				<CollapsibleGroup
					title={source.source_name}
					open={expandedSources.has(source.source_id)}
					onOpenChange={() => toggleSource(source.source_id)}
					accentColor={sourceColors.color}
				>
					{#snippet icon()}
						<div
							class="p-1.5 rounded-md"
							style="background-color: {sourceColors.subtle}; color: {sourceColors.color};"
						>
							{#if source.source_type === 'plugin'}
								<Puzzle size={14} />
							{:else}
								<FolderOpen size={14} />
							{/if}
						</div>
					{/snippet}
					{#snippet metadata()}
						<div class="flex items-center gap-3">
							<span class="text-xs text-[var(--text-muted)] tabular-nums">
								{source.total_registrations} registration{source.total_registrations !==
								1
									? 's'
									: ''}
							</span>
							<span class="text-xs text-[var(--text-muted)] tabular-nums">
								{source.event_types_covered.length} event type{source
									.event_types_covered.length !== 1
									? 's'
									: ''}
							</span>
							{#if source.blocking_hooks_count > 0}
								<span
									class="
										px-2 py-0.5
										text-[10px] font-semibold uppercase tracking-wider
										bg-red-500/10 text-red-600 dark:text-red-400
										rounded-full
									"
								>
									{source.blocking_hooks_count} blocking
								</span>
							{/if}
						</div>
					{/snippet}

					<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
						{#each source.scripts as script (script.filename)}
							<HookScriptCard
								{script}
								sourceType={source.source_type}
								sourceName={source.source_name}
							/>
						{/each}
					</div>
				</CollapsibleGroup>
			{/each}
		</div>
	{/if}
</div>
