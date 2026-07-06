<script lang="ts">
	import {
		Terminal,
		FileText,
		FileEdit,
		Eye,
		Search,
		Wrench,
		Plug,
		ChevronRight,
		ChevronDown
	} from 'lucide-svelte';
	import type { TimelineEvent } from '$lib/api-types';
	import TimelineEventCard from './TimelineEventCard.svelte';

	interface Props {
		events: TimelineEvent[];
		toolCount: number;
		isExpanded: boolean;
		onToggle: () => void;
		onOpenPopup: (event: TimelineEvent) => void;
		sessionUuid?: string;
		projectEncoded?: string;
		sessionSlug?: string;
		projectPath?: string | null;
		searchQuery?: string;
		currentAgentId?: string | null;
	}

	let {
		events,
		toolCount,
		isExpanded,
		onToggle,
		onOpenPopup,
		sessionUuid,
		projectEncoded,
		sessionSlug,
		projectPath = null,
		searchQuery = '',
		currentAgentId = null
	}: Props = $props();

	function getToolIcon(name: string) {
		if (name === 'Bash' || name === 'Shell') return Terminal;
		if (name === 'Edit' || name === 'StrReplace' || name === 'MultiEdit') return FileEdit;
		if (name === 'Write') return FileText;
		if (name === 'Read') return Eye;
		if (name === 'Grep' || name === 'Glob') return Search;
		if (name.startsWith('mcp__')) return Plug;
		return Wrench;
	}

	const toolSummary = $derived.by(() => {
		const counts = new Map<string, number>();
		for (const e of events) {
			if (e.event_type === 'tool_call') {
				const name = (e.metadata?.tool_name as string) ?? 'Tool';
				counts.set(name, (counts.get(name) ?? 0) + 1);
			}
		}
		return Array.from(counts.entries()).sort((a, b) => b[1] - a[1]);
	});
</script>

<!-- Cluster header row -->
<button
	type="button"
	onclick={onToggle}
	class="group flex items-center gap-2 w-full text-left px-1 py-1.5 mb-0.5 rounded-sm
		hover:bg-[var(--bg-subtle)] transition-colors cursor-pointer"
>
	{#if isExpanded}
		<ChevronDown size={11} class="text-[var(--text-faint)] opacity-50 shrink-0" />
	{:else}
		<ChevronRight size={11} class="text-[var(--text-faint)] opacity-50 shrink-0" />
	{/if}
	<span class="text-[10px] font-mono text-[var(--text-muted)] shrink-0">
		{toolCount} tools
	</span>
	<div class="flex items-center gap-1 flex-wrap min-w-0">
		{#each toolSummary as [name, count]}
			{@const IconComp = getToolIcon(name)}
			<span
				class="inline-flex items-center gap-0.5 px-1.5 py-0.5
				text-[9px] font-mono
				bg-[var(--event-tool)]/8 border border-[var(--event-tool)]/15 rounded
				text-[var(--event-tool)]/70 shrink-0"
			>
				<IconComp size={9} />
				<span class="ml-0.5"
					>{name}{#if count > 1}<span class="opacity-50 ml-0.5">×{count}</span>{/if}</span
				>
			</span>
		{/each}
	</div>
</button>

<!-- Expanded tool call events — only tool_calls, skip thinking rows -->
{#if isExpanded}
	<div class="pl-3 border-l border-[var(--border)]/30 ml-1.5 mb-1">
		{#each events as evt}
			{#if evt.event_type === 'tool_call'}
				<TimelineEventCard
					event={evt}
					index={-1}
					isFirst={false}
					isLast={false}
					isHighlighted={true}
					hasActiveFilter={false}
					isExpanded={false}
					onToggleExpand={() => {}}
					usePopup={true}
					onOpenPopup={() => onOpenPopup(evt)}
					{currentAgentId}
					{projectPath}
					{searchQuery}
					{projectEncoded}
					{sessionSlug}
					{sessionUuid}
				/>
			{/if}
		{/each}
	</div>
{/if}
