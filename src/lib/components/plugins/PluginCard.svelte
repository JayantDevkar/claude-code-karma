<script lang="ts">
	import { Puzzle, Bot, Zap, Terminal, DollarSign, Clock, Package } from 'lucide-svelte';
	import { formatCost, getPluginColorVars } from '$lib/utils';
	import type { PluginSummary } from '$lib/api-types';

	interface Props {
		plugin: PluginSummary;
		usageLoaded?: boolean;
		class?: string;
	}

	let { plugin, usageLoaded = true, class: className = '' }: Props = $props();

	// Get consistent OKLCH colors based on plugin name
	let colorVars = $derived(getPluginColorVars(plugin.name));

	// Format days since update
	let updateLabel = $derived(
		plugin.days_since_update === 0
			? 'Updated today'
			: plugin.days_since_update === 1
				? 'Updated yesterday'
				: `Updated ${plugin.days_since_update}d ago`
	);

	// Build link to detail page
	let detailHref = $derived(`/plugins/${encodeURIComponent(plugin.name)}`);
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
	<!-- Header row: Icon + Name + Badge -->
	<div class="flex items-start justify-between mb-5">
		<div
			class="p-3 rounded-xl transition-all duration-300 group-hover:scale-110"
			style="background-color: {colorVars.subtle}; color: {colorVars.color};"
		>
			<Puzzle size={22} strokeWidth={2.5} />
		</div>
		<span
			class="px-2.5 py-1 rounded-full text-[10px] font-semibold uppercase tracking-wider"
			style="background-color: {plugin.is_official
				? 'rgba(34, 197, 94, 0.1)'
				: 'rgba(156, 163, 175, 0.1)'}; color: {plugin.is_official
				? 'rgb(34, 197, 94)'
				: 'rgb(156, 163, 175)'};"
		>
			{plugin.is_official ? 'Official' : 'Community'}
		</span>
	</div>

	<!-- Plugin name -->
	<h3
		class="text-lg font-bold text-[var(--text-primary)] mb-2 truncate pr-4 tracking-tight group-hover:text-[var(--accent)] transition-colors"
	>
		{plugin.name.split('@')[0]}
	</h3>

	<!-- Description if available -->
	{#if plugin.description}
		<p class="text-xs text-[var(--text-muted)] mb-4 line-clamp-2">
			{plugin.description}
		</p>
	{:else}
		<div class="mb-4"></div>
	{/if}

	<!-- Stats grid -->
	<div class="grid grid-cols-3 gap-3 mb-3">
		<div class="flex items-center gap-2 text-xs">
			<Bot size={14} class="text-[var(--text-muted)]" />
			<span class="text-[var(--text-secondary)]">{plugin.agent_count} agents</span>
		</div>
		<div class="flex items-center gap-2 text-xs">
			<Zap size={14} class="text-[var(--text-muted)]" />
			<span class="text-[var(--text-secondary)]">{plugin.skill_count} skills</span>
		</div>
		<div class="flex items-center gap-2 text-xs">
			<Terminal size={14} class="text-[var(--text-muted)]" />
			<span class="text-[var(--text-secondary)]">{plugin.command_count} cmds</span>
		</div>
	</div>
	<div class="grid grid-cols-2 gap-3 mb-4">
		<div class="flex items-center gap-2 text-xs">
			<Package size={14} class="text-[var(--text-muted)]" />
			{#if usageLoaded}
				<span class="text-[var(--text-secondary)]"
					>{plugin.total_runs.toLocaleString()} runs</span
				>
			{:else}
				<span class="inline-block w-12 h-3 bg-[var(--bg-muted)] rounded animate-pulse"
				></span>
			{/if}
		</div>
		<div class="flex items-center gap-2 text-xs">
			<DollarSign size={14} class="text-[var(--text-muted)]" />
			{#if usageLoaded}
				<span class="text-[var(--text-secondary)]"
					>{formatCost(plugin.estimated_cost_usd)}</span
				>
			{:else}
				<span class="inline-block w-12 h-3 bg-[var(--bg-muted)] rounded animate-pulse"
				></span>
			{/if}
		</div>
	</div>

	<!-- Footer row -->
	<div
		class="flex items-center justify-between text-xs text-[var(--text-muted)] pt-4 border-t border-[var(--border-subtle)]"
	>
		<span class="flex items-center gap-1.5">
			<Clock size={12} />
			<span>{updateLabel}</span>
		</span>
		<span class="font-mono text-[10px] bg-[var(--bg-subtle)] px-2 py-0.5 rounded">
			v{plugin.latest_version.substring(0, 7)}
		</span>
	</div>
</a>
