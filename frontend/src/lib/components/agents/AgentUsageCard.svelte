<script lang="ts">
	import { Bot, Clock, DollarSign, Play, FolderOpen, Puzzle } from 'lucide-svelte';
	import { formatDistanceToNow } from 'date-fns';
	import { formatCost, getSubagentColorVars, getScopeColorVars } from '$lib/utils';
	import type { AgentUsageSummary } from '$lib/api-types';

	interface Props {
		agent: AgentUsageSummary;
		class?: string;
	}

	let { agent, class: className = '' }: Props = $props();

	// Category display labels
	const categoryLabels: Record<string, string> = {
		builtin: 'Built-in',
		plugin: 'Plugin',
		custom: 'Custom',
		project: 'Project'
	};

	let categoryLabel = $derived(categoryLabels[agent.category] || agent.category);

	// Get consistent colors based on subagent_type (matches session/subagent views)
	let colorVars = $derived(getSubagentColorVars(agent.subagent_type));

	// Scope-aware colors for the category badge
	let badgeColors = $derived(
		agent.category === 'project'
			? getScopeColorVars('project')
			: agent.category === 'custom'
				? getScopeColorVars('user')
				: colorVars
	);

	// Format last used as relative time
	let lastUsedFormatted = $derived(
		agent.last_used ? formatDistanceToNow(new Date(agent.last_used)) + ' ago' : 'Never'
	);

	// Build link to agent detail page
	let detailHref = $derived(`/agents/${encodeURIComponent(agent.subagent_type)}`);
</script>

<a
	href={detailHref}
	class="
		group block
		bg-[var(--bg-base)]
		border border-[var(--border)]
		rounded-xl
		p-6
		shadow-sm hover:shadow-xl hover:-translate-y-1
		transition-all duration-300
		relative overflow-hidden
		focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2
		{className}
	"
	style="border-left: 4px solid {colorVars.color};"
	data-list-item
>
	<!-- Header row: Icon + Name + Category Badge -->
	<div class="flex items-start justify-between mb-5">
		<div
			class="p-3 rounded-xl transition-all duration-300 group-hover:scale-110"
			style="background-color: {colorVars.subtle}; color: {colorVars.color};"
		>
			<Bot size={22} strokeWidth={2.5} />
		</div>
		<span
			class="px-2.5 py-1 rounded-full text-[10px] font-semibold uppercase tracking-wider"
			style="background-color: {badgeColors.subtle}; color: {badgeColors.color};"
		>
			{categoryLabel}
		</span>
	</div>

	<!-- Agent name -->
	<h3
		class="text-lg font-bold text-[var(--text-primary)] mb-2 truncate pr-4 tracking-tight group-hover:text-[var(--accent)] transition-colors"
	>
		{agent.agent_name}
	</h3>

	<!-- Plugin source if applicable -->
	{#if agent.plugin_source}
		<div class="mb-4">
			<a
				href="/plugins/{encodeURIComponent(agent.plugin_source)}"
				class="
					inline-flex items-center gap-1.5 px-2 py-1
					text-[10px] font-medium
					text-[var(--text-muted)] hover:text-[var(--accent)]
					bg-[var(--bg-subtle)] hover:bg-[var(--accent-subtle)]
					rounded-full
					transition-colors
				"
				onclick={(e) => e.stopPropagation()}
				title="View plugin: {agent.plugin_source}"
			>
				<Puzzle size={10} />
				<span class="truncate max-w-[140px]">{agent.plugin_source}</span>
			</a>
		</div>
	{:else}
		<div class="mb-4"></div>
	{/if}

	<!-- Stats with progress indicators -->
	<div class="space-y-3 mb-4">
		<!-- Runs stat with progress bar -->
		<div>
			<div class="flex items-center justify-between mb-1.5">
				<div class="flex items-center gap-2 text-xs text-[var(--text-muted)]">
					<Play size={12} />
					<span class="font-medium">Runs</span>
				</div>
				<span class="text-sm font-semibold text-[var(--text-primary)] tabular-nums">
					{agent.total_runs.toLocaleString()}
				</span>
			</div>
			<div class="h-1.5 bg-[var(--bg-subtle)] rounded-full overflow-hidden">
				<div
					class="h-full rounded-full transition-all duration-300"
					style="width: {Math.min(
						(agent.total_runs / 100) * 100,
						100
					)}%; background-color: {colorVars.color};"
				></div>
			</div>
		</div>

		<!-- Cost stat -->
		<div class="flex items-center justify-between text-xs">
			<div class="flex items-center gap-2 text-[var(--text-muted)]">
				<DollarSign size={12} />
				<span class="font-medium">Total Cost</span>
			</div>
			<span class="text-sm font-semibold text-[var(--text-primary)] tabular-nums">
				{formatCost(agent.total_cost_usd)}
			</span>
		</div>
	</div>

	<!-- Footer row: Last used + Projects count -->
	<div
		class="flex items-center justify-between text-xs text-[var(--text-muted)] pt-4 border-t border-[var(--border-subtle)]"
	>
		<span class="flex items-center gap-1.5">
			<Clock size={12} />
			<span>{lastUsedFormatted}</span>
		</span>
		<span class="flex items-center gap-1.5">
			<FolderOpen size={12} />
			<span
				>{agent.projects_used_in.length} project{agent.projects_used_in.length !== 1
					? 's'
					: ''}</span
			>
		</span>
	</div>
</a>
