<script lang="ts">
	import { Search, Sparkles, Info, TrendingUp, ChevronRight } from 'lucide-svelte';
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import { navigating } from '$app/stores';
	import { replaceState, beforeNavigate } from '$app/navigation';
	import { tick } from 'svelte';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import StackedAreaChart from '$lib/components/charts/StackedAreaChart.svelte';
	import {
		getSubagentColorVars,
		getPluginColorVars,
		getSubagentTypeDisplayName
	} from '$lib/utils';
	import { API_BASE } from '$lib/config';
	import type { AgentUsageSummary, UsageTrendResponse } from '$lib/api-types';

	let { data } = $props();

	function initParam(key: string, fallback: string): string {
		if (browser) return new URLSearchParams(window.location.search).get(key) ?? fallback;
		return fallback;
	}

	let activeView = $state<'overview' | 'analytics'>(
		(initParam('view', 'overview') as 'overview' | 'analytics')
	);
	let searchQuery = $state(initParam('search', ''));
	let selectedFilter = $state<'all' | 'plugin' | 'custom' | 'builtin' | 'project'>(
		(initParam('filter', 'all') as 'all' | 'plugin' | 'custom' | 'builtin' | 'project')
	);
	let selectedCategory = $state<string | null>(null); // null = all categories

	$effect(() => {
		if (!browser) return;
		const v = activeView;
		const f = selectedFilter;
		const s = searchQuery;
		tick().then(() => {
			const url = new URL(window.location.href);
			if (v !== 'overview') url.searchParams.set('view', v);
			else url.searchParams.delete('view');
			if (f !== 'all') url.searchParams.set('filter', f);
			else url.searchParams.delete('filter');
			if (s.trim()) url.searchParams.set('search', s.trim());
			else url.searchParams.delete('search');
			replaceState(url.toString(), {});
		});
	});

	// ── Base data ──────────────────────────────────────────────────────────────
	let allAgents = $derived<AgentUsageSummary[]>(data.usage.agents || []);

	// ── Grouping ───────────────────────────────────────────────────────────────
	interface AgentGroup {
		key: string;
		label: string;
		agents: AgentUsageSummary[];
		pluginName: string | null;
		category: string;
	}

	let groupedAgents = $derived.by<AgentGroup[]>(() => {
		const groups = new Map<string, AgentGroup>();
		for (const agent of allAgents) {
			let key: string, label: string, pluginName: string | null = null, category: string;
			if (agent.category === 'builtin') {
				key = 'builtin'; label = 'Built-in Agents'; category = 'builtin';
			} else if (agent.category === 'plugin' && agent.plugin_source) {
				key = `plugin:${agent.plugin_source}`; label = agent.plugin_source; pluginName = agent.plugin_source; category = 'plugin';
			} else if (agent.category === 'custom') {
				key = 'custom'; label = 'Custom Agents'; category = 'custom';
			} else if (agent.category === 'project') {
				key = 'project'; label = 'Project Agents'; category = 'project';
			} else {
				key = 'other'; label = 'Other Agents'; category = 'unknown';
			}
			if (!groups.has(key)) groups.set(key, { key, label, agents: [], pluginName, category });
			groups.get(key)!.agents.push(agent);
		}
		return Array.from(groups.values());
	});

	// ── Left panel: sorted by total_runs desc ─────────────────────────────────
	let leftPanelGroups = $derived.by(() => {
		return [...groupedAgents]
			.filter(g => {
				if (selectedFilter === 'builtin') return g.category === 'builtin';
				if (selectedFilter === 'plugin') return g.category === 'plugin';
				if (selectedFilter === 'custom') return g.category === 'custom';
				if (selectedFilter === 'project') return g.category === 'project';
				return true;
			})
			.sort((a, b) => {
				const aTotal = a.agents.reduce((sum, ag) => sum + ag.total_runs, 0);
				const bTotal = b.agents.reduce((sum, ag) => sum + ag.total_runs, 0);
				return bTotal - aTotal;
			});
	});

	// ── Stats ──────────────────────────────────────────────────────────────────
	let totalRuns = $derived(allAgents.reduce((sum, a) => sum + a.total_runs, 0));
	let activeAgentsCount = $derived(allAgents.filter(a => a.total_runs > 0).length);
	let totalAgentsCount = $derived(allAgents.length);
	let unusedCount = $derived(allAgents.filter(a => a.total_runs === 0).length);

	let grandTotalRuns = $derived(totalRuns > 0 ? totalRuns : 1);

	// ── Right panel: filtered + sorted ────────────────────────────────────────
	let rightPanelAgents = $derived.by(() => {
		let agents = allAgents.filter(a => a.total_runs > 0);

		const cat = selectedCategory;
		if (cat !== null) {
			agents = agents.filter(a => {
				if (cat.startsWith('plugin:')) {
					return a.category === 'plugin' && a.plugin_source === cat.slice(7);
				}
				return a.category === cat;
			});
		}

		if (selectedFilter === 'builtin') agents = agents.filter(a => a.category === 'builtin');
		else if (selectedFilter === 'plugin') agents = agents.filter(a => a.category === 'plugin');
		else if (selectedFilter === 'custom') agents = agents.filter(a => a.category === 'custom');
		else if (selectedFilter === 'project') agents = agents.filter(a => a.category === 'project');

		if (searchQuery.trim()) {
			const q = searchQuery.toLowerCase();
			agents = agents.filter(a =>
				a.agent_name.toLowerCase().includes(q) ||
				a.subagent_type.toLowerCase().includes(q) ||
				(a.plugin_source && a.plugin_source.toLowerCase().includes(q))
			);
		}

		return agents.slice().sort((a, b) => b.total_runs - a.total_runs);
	});

	let globalMax = $derived(
		rightPanelAgents.length > 0 ? Math.max(...rightPanelAgents.map(a => a.total_runs), 1) : 1
	);

	// ── Analytics derived ─────────────────────────────────────────────────────
	let analyticsTotalRuns = $derived(rightPanelAgents.reduce((sum, a) => sum + a.total_runs, 0));
	let analyticsTotalCost = $derived(rightPanelAgents.reduce((sum, a) => sum + a.total_cost_usd, 0));

	// ── Insight banner ────────────────────────────────────────────────────────
	let insightText = $derived.by(() => {
		if (rightPanelAgents.length === 0) return null;
		const top = rightPanelAgents[0];
		const topName = getSubagentTypeDisplayName(top.subagent_type);
		const topReach = rightPanelAgents.slice().sort((a, b) => b.projects_used_in.length - a.projects_used_in.length)[0];
		const topReachName = topReach ? getSubagentTypeDisplayName(topReach.subagent_type) : null;
		if (topReachName && topReachName !== topName) {
			return {
				bold: `${topName} leads all runs`,
				rest: ` · ${topReachName} spans ${topReach.projects_used_in.length} project${topReach.projects_used_in.length !== 1 ? 's' : ''} · ${rightPanelAgents.length} active agents total`
			};
		}
		return {
			bold: `${rightPanelAgents.length} active agents`,
			rest: ` · ${topName} leads with ${top.total_runs} runs across ${top.projects_used_in.length} project${top.projects_used_in.length !== 1 ? 's' : ''}`
		};
	});

	// ── Project reach panel ───────────────────────────────────────────────────
	let projectReachAgents = $derived(
		rightPanelAgents.slice().sort((a, b) => b.projects_used_in.length - a.projects_used_in.length).slice(0, 8)
	);
	let projectReachMax = $derived(projectReachAgents.length > 0 ? projectReachAgents[0].projects_used_in.length : 1);

	// ── Trend chart state ─────────────────────────────────────────────────────
	let trendRange = $state<'7d' | '30d' | '90d'>('90d');
	let trendData = $state<UsageTrendResponse | null>(null);
	let trendLoading = $state(false);
	let trendRangeUserOverride = $state(false);

	const periodMap: Record<'7d' | '30d' | '90d', string> = { '7d': 'week', '30d': 'month', '90d': 'quarter' };

	$effect(() => {
		if (!browser || activeView !== 'analytics') return;
		trendLoading = true;
		const url = new URL(`${API_BASE}/agents/usage/trend`);
		url.searchParams.set('period', periodMap[trendRange]);
		fetch(url)
			.then(r => r.json())
			.then(d => {
				trendData = d;
				if (!trendRangeUserOverride) {
					const total = (d as UsageTrendResponse)?.total ?? 0;
					if (total === 0 && trendRange === '90d') trendRange = '30d';
					else if (total === 0 && trendRange === '30d') trendRange = '7d';
				}
			})
			.catch(() => {})
			.finally(() => { trendLoading = false; });
	});

	// ── getGroupFor for StackedAreaChart ──────────────────────────────────────
	function getGroupFor(itemName: string): { key: string; label: string; color: string } | null {
		const agent = allAgents.find(a => a.subagent_type === itemName);
		if (!agent) return null;
		if (agent.category === 'plugin' && agent.plugin_source) {
			const colors = getPluginColorVars(agent.plugin_source);
			return { key: `plugin:${agent.plugin_source}`, label: agent.plugin_source, color: colors.color };
		}
		const colors = getSubagentColorVars(agent.subagent_type);
		const label = agent.category === 'builtin' ? 'built-in' : agent.category === 'custom' ? 'custom' : agent.category === 'project' ? 'project' : 'other';
		return { key: agent.category, label, color: colors.color };
	}

	// ── Helpers ────────────────────────────────────────────────────────────────
	function shortDate(ts: string | null): string {
		if (!ts) return '—';
		const date = new Date(ts);
		const diffMs = Date.now() - date.getTime();
		const diffMins = Math.floor(diffMs / 60000);
		const diffHours = Math.floor(diffMins / 60);
		const diffDays = Math.floor(diffHours / 24);
		if (diffMins < 1) return 'now';
		if (diffMins < 60) return `${diffMins}m`;
		if (diffHours < 24) return `${diffHours}h`;
		if (diffDays < 7) return `${diffDays}d`;
		return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
	}

	function getCategoryBadge(agent: AgentUsageSummary): string {
		if (agent.category === 'plugin' && agent.plugin_source) return agent.plugin_source;
		if (agent.category === 'builtin') return 'built-in';
		if (agent.category === 'custom') return 'custom';
		if (agent.category === 'project') return 'project';
		return agent.category;
	}

	function getAgentColors(agent: AgentUsageSummary) {
		if (agent.category === 'plugin' && agent.plugin_source) return getPluginColorVars(agent.plugin_source);
		return getSubagentColorVars(agent.subagent_type);
	}

	let coverageOpen = $state(false);

	function toggleCategory(group: AgentGroup) {
		const key = group.pluginName ? `plugin:${group.pluginName}` : group.category;
		if (selectedCategory === key) selectedCategory = null;
		else selectedCategory = key;
	}

	// ── Available filter chips (only categories with data) ────────────────────
	let availableFilters = $derived.by(() => {
		const cats = new Set(allAgents.map(a => a.category));
		const filters: { val: 'all' | 'plugin' | 'custom' | 'builtin' | 'project'; lbl: string }[] = [
			{ val: 'all', lbl: 'All' }
		];
		if (cats.has('plugin')) filters.push({ val: 'plugin', lbl: 'Plugin' });
		if (cats.has('custom')) filters.push({ val: 'custom', lbl: 'Custom' });
		if (cats.has('builtin')) filters.push({ val: 'builtin', lbl: 'Built-in' });
		if (cats.has('project')) filters.push({ val: 'project', lbl: 'Project' });
		return filters;
	});

	// ── Scroll save/restore when navigating to agent detail ───────────────────
	const SCROLL_KEY = 'agents_scroll';

	beforeNavigate(({ to }) => {
		if (!browser) return;
		if (to?.route.id?.startsWith('/agents/')) {
			sessionStorage.setItem(SCROLL_KEY, String(window.scrollY));
		} else {
			sessionStorage.removeItem(SCROLL_KEY);
		}
	});

	onMount(() => {
		const saved = sessionStorage.getItem(SCROLL_KEY);
		if (saved !== null) {
			sessionStorage.removeItem(SCROLL_KEY);
			requestAnimationFrame(() => window.scrollTo({ top: Number(saved), behavior: 'instant' }));
		}
	});

	let isPageLoading = $derived(!!$navigating && $navigating.to?.route.id === '/agents');
</script>

{#if isPageLoading}
	<div class="-mx-6 -my-8 flex items-center justify-center" style="height: calc(100vh - 56px);">
		<div class="flex flex-col items-center gap-3">
			<div style="width: 32px; height: 32px; border: 2px solid var(--accent); border-top-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite;"></div>
			<span class="text-sm text-[var(--text-muted)]">Loading agents…</span>
		</div>
	</div>
{:else}

<!-- ── Full-bleed split-view container ────────────────────────────────────── -->
<div
	class="-mx-6 -my-8 flex flex-col"
	style="{activeView === 'overview' ? 'height: calc(100vh - 56px); overflow: hidden;' : ''}"
>

	<!-- ── Page Header ──────────────────────────────────────────────────────── -->
	<div class="flex-shrink-0" style="padding: 32px 24px 0; background: var(--bg-base);">
		<PageHeader
			title="Agents"
			iconName="agents"
			iconColor="--nav-purple"
			breadcrumbs={[{ label: 'Dashboard', href: '/' }, { label: 'Agents' }]}
			subtitle="How much are my agents really doing?"
		/>
	</div>

	<!-- Filter bar — always visible -->
	<div
		class="flex flex-shrink-0 items-center"
		style="padding: 8px 12px; gap: 10px; {activeView === 'analytics' ? 'position: sticky; top: 56px; z-index: 10; background: var(--bg-base); border-bottom: 1px solid var(--border-subtle);' : ''}"
	>
		<!-- Left group: view tabs — fixed width matching left panel -->
		<div
			class="flex rounded-lg p-0.5 flex-shrink-0"
			style="width: 280px; background: var(--bg-muted);"
			role="tablist"
			aria-label="View"
		>
			{#each ([['overview', 'Overview'], ['analytics', 'Analytics']] as const) as [val, lbl]}
				<button
					role="tab"
					aria-selected={activeView === val}
					onclick={() => activeView = val}
					class="flex-1 rounded-md transition-all"
					style="
						padding: 4px 8px;
						font-size: 11px;
						font-weight: {activeView === val ? '600' : '500'};
						color: {activeView === val ? 'var(--bg-base)' : 'var(--text-secondary)'};
						background: {activeView === val ? 'var(--text-primary)' : 'transparent'};
					"
				>{lbl}</button>
			{/each}
		</div>

		<!-- Right group: type chips + search -->
		<div class="flex items-center gap-2 flex-1">
			<div class="flex items-center gap-1.5">
				{#each availableFilters as { val, lbl }}
					<button
						onclick={() => { selectedFilter = val; selectedCategory = null; }}
						class="rounded-full transition-all"
						style="
							padding: 4px 12px;
							font-size: 11px;
							font-weight: {selectedFilter === val ? '600' : '500'};
							color: {selectedFilter === val ? 'var(--accent)' : 'var(--text-secondary)'};
							background: {selectedFilter === val ? 'var(--accent-muted)' : 'transparent'};
							border: {selectedFilter === val ? '1.5px solid var(--accent-subtle)' : '1px solid var(--border)'};
						"
					>{lbl}</button>
				{/each}
			</div>
			<div class="relative ml-auto">
				<Search class="absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" size={12} style="color: var(--text-faint);" />
				<input
					type="text"
					bind:value={searchQuery}
					aria-label="Search agents"
					placeholder="Search agents…"
					style="width: 180px; padding: 4px 10px 4px 26px; font-size: 12px; background: var(--bg-subtle); border: 1px solid var(--border); border-radius: 8px; color: var(--text-primary); outline: none;"
					data-search-input
				/>
			</div>
		</div>
	</div>

	{#if activeView === 'overview'}
	<!-- Split view -->
	<div class="flex flex-1 min-h-0 overflow-hidden" style="padding: 0 12px 12px; gap: 10px;">

		<!-- ── Left Panel: Agent Coverage ──────────────────────────────────── -->
		<div
			class="flex-shrink-0 flex flex-col"
			style="width: 280px; background: var(--bg-base); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; align-self: flex-start;"
		>
			<!-- Panel header — accordion trigger -->
			<button
				class="w-full text-left flex-shrink-0 transition-colors hover:bg-[var(--bg-subtle)]"
				style="border-bottom: 1px solid {coverageOpen ? 'var(--border-subtle)' : 'transparent'}; padding: 14px 16px 12px;"
				onclick={() => coverageOpen = !coverageOpen}
			>
				<div class="flex items-center justify-between mb-2">
					<span style="font-size: 10px; font-weight: 700; color: var(--accent); text-transform: uppercase; letter-spacing: 0.12em; font-family: 'JetBrains Mono', monospace;">
						Agent Coverage
					</span>
					<div style="color: var(--text-faint); transition: transform 0.2s; transform: rotate({coverageOpen ? 90 : 0}deg);">
						<ChevronRight size={13} />
					</div>
				</div>
				<!-- Stats: 3 columns -->
				<div class="flex items-center w-full">
					<div class="flex flex-col flex-1 items-center">
						<span style="font-size: 22px; font-weight: 700; font-family: 'JetBrains Mono', monospace; color: var(--text-primary); letter-spacing: -1px;">{totalRuns.toLocaleString()}</span>
						<span style="font-size: 9px; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.06em;">runs</span>
					</div>
					<div style="width: 1px; height: 32px; background: var(--border);"></div>
					<div class="flex flex-col flex-1 items-center">
						<span style="font-size: 22px; font-weight: 700; font-family: 'JetBrains Mono', monospace; color: var(--text-primary); letter-spacing: -1px;">{activeAgentsCount}<span style="font-size: 13px; font-weight: 500; color: var(--text-faint);">/{totalAgentsCount}</span></span>
						<span style="font-size: 9px; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.06em;">active</span>
					</div>
					{#if unusedCount > 0}
						<div style="width: 1px; height: 32px; background: var(--border);"></div>
						<div class="flex flex-col flex-1 items-center">
							<span style="font-size: 22px; font-weight: 700; font-family: 'JetBrains Mono', monospace; color: var(--nav-orange); letter-spacing: -1px;">{unusedCount}</span>
							<span style="font-size: 9px; color: var(--nav-orange); text-transform: uppercase; letter-spacing: 0.06em; opacity: 0.8;">unused</span>
						</div>
					{/if}
				</div>
			</button>

			<!-- Group rows — only when accordion is open -->
			{#if coverageOpen}
			<div class="flex-1 overflow-y-auto">
				{#each leftPanelGroups as group}
					{@const groupRuns = group.agents.reduce((sum, a) => sum + a.total_runs, 0)}
					{@const pct = grandTotalRuns > 0 ? Math.round((groupRuns / grandTotalRuns) * 100) : 0}
					{@const colors = group.pluginName ? getPluginColorVars(group.pluginName) : getSubagentColorVars(group.agents[0]?.subagent_type)}
					{@const isNeverUsed = groupRuns === 0}
					{@const catKey = group.pluginName ? `plugin:${group.pluginName}` : group.category}
					{@const isSelected = selectedCategory === catKey}
					<div
						role="button"
						tabindex="0"
						onclick={() => toggleCategory(group)}
						onkeydown={(e) => e.key === 'Enter' && toggleCategory(group)}
						class="border-b cursor-pointer group/row transition-colors"
						style="
							padding: 10px 20px;
							border-color: var(--border-subtle);
							background: {isSelected ? 'var(--accent-muted)' : 'transparent'};
							border-left: {isSelected ? '2px solid var(--accent)' : '2px solid transparent'};
							opacity: {isNeverUsed ? 0.45 : 1};
						"
					>
						<!-- Name row -->
						<div class="flex items-center justify-between gap-2" style="margin-bottom: 6px;">
							<span class="flex-1 min-w-0 truncate" style="font-size: 12px; font-weight: 600; color: var(--text-primary); font-family: 'JetBrains Mono', monospace;">
								{group.label}
							</span>
							<div class="flex items-center gap-1.5 flex-shrink-0">
								{#if groupRuns === grandTotalRuns && grandTotalRuns > 0}
									<TrendingUp size={10} style="color: var(--nav-orange);" />
								{/if}
								<span style="font-size: 12px; font-weight: 700; font-family: 'JetBrains Mono', monospace; color: {isNeverUsed ? 'var(--text-faint)' : pct >= 50 ? 'var(--text-secondary)' : 'var(--text-faint)'};">
									{pct}%
								</span>
							</div>
						</div>

						<!-- Bar + count -->
						<div class="flex items-center gap-2">
							<div class="flex-1" style="height: 3px; border-radius: 2px; background: var(--bg-muted); overflow: hidden;">
								{#if !isNeverUsed}
									<div style="height: 100%; border-radius: 2px; width: {pct}%; background: var(--accent); opacity: 0.5;"></div>
								{/if}
							</div>
							<span style="font-size: 10px; color: var(--text-faint); font-family: 'JetBrains Mono', monospace; flex-shrink: 0;">
								{groupRuns.toLocaleString()} runs
							</span>
						</div>
					</div>
				{/each}
			</div>

			<!-- Sort footer -->
			<div class="flex-shrink-0 border-t flex items-center justify-between" style="padding: 10px 16px; border-color: var(--border-subtle);">
				<span style="font-size: 10px; color: var(--text-faint);">Sorted by total runs</span>
				{#if selectedCategory !== null}
					<button onclick={() => selectedCategory = null} style="font-size: 10px; color: var(--accent); font-weight: 600;">
						Clear ×
					</button>
				{/if}
			</div>
			{/if}
		</div>

		<!-- ── Right Panel: Top Agents Leaderboard ─────────────────────────── -->
		<div class="flex-1 flex flex-col overflow-hidden min-w-0" style="background: var(--bg-base); border: 1px solid var(--border); border-radius: 12px;">

			<!-- Panel header -->
			<div
				class="flex-shrink-0 flex items-center justify-between border-b"
				style="padding: 14px 16px 12px; background: var(--bg-base); border-color: var(--border);"
			>
				<div>
					<div style="font-size: 10px; font-weight: 700; color: var(--accent); text-transform: uppercase; letter-spacing: 0.12em; font-family: 'JetBrains Mono', monospace; margin-bottom: 3px;">Top Agents</div>
					<div style="font-size: 11px; color: var(--text-faint);">
						{#if selectedCategory !== null}
							{rightPanelAgents.length} agents · {selectedCategory.startsWith('plugin:') ? selectedCategory.slice(7) : selectedCategory}
						{:else}
							{rightPanelAgents.length} active agents ranked by runs
						{/if}
					</div>
				</div>
			</div>

			<!-- Table container -->
			<div class="flex-1 overflow-y-auto">
				{#if rightPanelAgents.length === 0}
					<div class="flex flex-col items-center justify-center h-full gap-3">
						<Search size={36} style="color: var(--text-faint);" />
						<p style="font-size: 13px; color: var(--text-secondary); font-weight: 500;">No matching agents</p>
						<p style="font-size: 11px; color: var(--text-faint);">Try adjusting filters or search</p>
					</div>
				{:else}
					<!-- Column headers -->
					<div
						class="grid sticky top-0 border-b"
						style="background: var(--bg-base); border-color: var(--border); grid-template-columns: 32px 1fr 120px 100px 72px 80px; padding: 10px 12px 8px;"
					>
						<div style="font-size: 10px; color: var(--text-faint); letter-spacing: 0.06em; text-transform: uppercase; text-align: center;">#</div>
						<div style="font-size: 10px; color: var(--text-faint); letter-spacing: 0.06em; text-transform: uppercase;">Agent</div>
						<div style="font-size: 10px; color: var(--text-faint); letter-spacing: 0.06em; text-transform: uppercase;">Category</div>
						<div style="font-size: 10px; color: var(--text-faint); letter-spacing: 0.06em; text-transform: uppercase; padding: 0 8px;">Runs</div>
						<div style="font-size: 10px; color: var(--text-faint); letter-spacing: 0.06em; text-transform: uppercase; text-align: right;">Count</div>
						<div style="font-size: 10px; color: var(--text-faint); letter-spacing: 0.06em; text-transform: uppercase; text-align: right;">Cost</div>
					</div>

					<!-- Agent rows -->
					{#each rightPanelAgents as agent, i (agent.subagent_type)}
						{@const displayName = getSubagentTypeDisplayName(agent.subagent_type)}
						{@const barWidth = Math.round((agent.total_runs / globalMax) * 100)}
						{@const badge = getCategoryBadge(agent)}
						{@const colors = getAgentColors(agent)}
						{@const useColor = selectedFilter === 'plugin' && agent.category === 'plugin'}
						<a
							href="/agents/{encodeURIComponent(agent.subagent_type)}"
							class="grid border-b transition-colors hover:bg-[var(--bg-subtle)] no-underline"
							style="grid-template-columns: 32px 1fr 120px 100px 72px 80px; padding: 8px 12px; border-color: var(--border-subtle); align-items: center;"
						>
							<div style="font-size: 11px; color: var(--text-faint); font-family: 'JetBrains Mono', monospace; text-align: center;">{i + 1}</div>
							<div class="min-w-0 pr-3">
								<span class="truncate block" style="font-size: 13px; font-weight: 600; color: var(--text-primary); font-family: 'JetBrains Mono', monospace;" title={displayName}>{displayName}</span>
							</div>
							<div class="min-w-0">
								{#if useColor && agent.plugin_source}
									<span class="truncate block rounded" style="font-size: 10px; font-weight: 700; font-family: 'JetBrains Mono', monospace; padding: 2px 7px; color: var(--bg-base); background: {colors.color}; display: inline-block; max-width: 100%;" title={agent.plugin_source}>{agent.plugin_source}</span>
								{:else}
									<span class="truncate block" style="font-size: 11px; color: var(--text-secondary); font-family: 'JetBrains Mono', monospace;" title={badge}>{badge}</span>
								{/if}
							</div>
							<div style="padding: 0 8px;">
								<div style="background: var(--bg-muted); height: 4px; border-radius: 2px; overflow: hidden;">
									<div style="height: 100%; border-radius: 2px; width: {barWidth}%; background: {useColor ? colors.color : 'var(--accent)'}; opacity: 0.7;"></div>
								</div>
							</div>
							<div style="font-size: 13px; font-weight: 700; font-family: 'JetBrains Mono', monospace; text-align: right; color: {useColor ? colors.color : 'var(--text-primary)'};">{agent.total_runs}</div>
							<div style="font-size: 11px; font-weight: 500; color: var(--text-secondary); font-family: 'JetBrains Mono', monospace; text-align: right;">${agent.total_cost_usd < 0.01 ? agent.total_cost_usd.toFixed(4) : agent.total_cost_usd.toFixed(2)}</div>
						</a>
					{/each}
				{/if}
			</div>
		</div>

	</div>

	{:else}

	<!-- Analytics view -->
	<div style="padding: 18px 24px 64px; display: flex; flex-direction: column; gap: 14px;">

		<!-- Insight banner -->
		{#if insightText}
			<div class="flex items-center gap-3 rounded-lg" style="padding: 10px 16px; background: linear-gradient(135deg, var(--accent-muted), color-mix(in oklch, var(--accent-muted), var(--bg-subtle) 50%)); border: 1px solid var(--accent-subtle);">
				<Sparkles size={14} style="color: var(--accent); flex-shrink: 0;" />
				<span style="font-size: 12px; color: var(--text-primary); line-height: 1.5;">
					<strong>{insightText.bold}</strong>{insightText.rest}
				</span>
			</div>
		{/if}

		<!-- Stacked area chart -->
		<StackedAreaChart
			trendData={trendData}
			loading={trendLoading}
			range={trendRange}
			onRangeChange={(r) => { trendRangeUserOverride = true; trendRange = r; }}
			getGroupFor={getGroupFor}
			label="Agent Runs Over Time"
		/>

		<!-- Bottom 2-col row -->
		<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px; align-items: start;">

			<!-- Project Reach panel -->
			<div class="rounded-lg" style="padding: 16px 18px; background: var(--bg-base); border: 1px solid var(--border);">
				<div style="font-size: 10px; font-weight: 700; color: var(--accent); text-transform: uppercase; letter-spacing: 0.12em; font-family: 'JetBrains Mono', monospace; margin-bottom: 2px;">Project Reach</div>
				<div style="font-size: 11px; color: var(--text-faint); margin-bottom: 14px;">which agents span the most projects</div>

				{#if projectReachAgents.length === 0}
					<div style="color: var(--text-faint); font-size: 12px; padding: 12px 0;">No data</div>
				{:else}
					<!-- Column headers -->
					<div style="display: grid; grid-template-columns: 1fr 80px 44px; gap: 8px; padding: 0 4px; margin-bottom: 6px;">
						<div style="font-size: 9px; color: var(--text-faint); letter-spacing: 0.1em; text-transform: uppercase;">Agent</div>
						<div style="font-size: 9px; color: var(--text-faint); letter-spacing: 0.1em; text-transform: uppercase; text-align: center;">projects</div>
						<div style="font-size: 9px; color: var(--text-faint); letter-spacing: 0.1em; text-transform: uppercase; text-align: right;">count</div>
					</div>
					<div style="border-top: 1px solid var(--border-subtle); padding-top: 4px;">
						{#each projectReachAgents as agent}
							{@const colors = getAgentColors(agent)}
							{@const reach = agent.projects_used_in.length}
							{@const barPct = projectReachMax > 0 ? Math.round((reach / projectReachMax) * 100) : 0}
							{@const displayName = getSubagentTypeDisplayName(agent.subagent_type)}
							<a
								href="/agents/{encodeURIComponent(agent.subagent_type)}"
								class="no-underline"
								style="display: grid; grid-template-columns: 1fr 80px 44px; gap: 8px; align-items: center; padding: 5px 4px; border-radius: 4px; cursor: pointer;"
								onmouseenter={(e) => (e.currentTarget as HTMLElement).style.background = 'var(--bg-subtle)'}
								onmouseleave={(e) => (e.currentTarget as HTMLElement).style.background = 'transparent'}
							>
								<div class="flex items-center gap-1.5 min-w-0">
									<div style="width: 5px; height: 5px; border-radius: 50%; background: {colors.color}; flex-shrink: 0;"></div>
									<span class="truncate" style="font-size: 12px; font-weight: 600; color: var(--text-primary); font-family: 'JetBrains Mono', monospace;" title={displayName}>{displayName}</span>
								</div>
								<div style="background: var(--bg-muted); height: 5px; border-radius: 3px; overflow: hidden;">
									<div style="height: 100%; border-radius: 3px; width: {barPct}%; background: var(--accent);"></div>
								</div>
								<div style="font-size: 10px; font-weight: 700; color: {reach >= 3 ? 'var(--accent)' : 'var(--text-faint)'}; text-align: right; font-family: 'JetBrains Mono', monospace;">{reach}</div>
							</a>
						{/each}
					</div>
					<div style="margin-top: 10px; border-top: 1px solid var(--border-subtle); padding-top: 8px; font-size: 10px; color: var(--text-faint); line-height: 1.5;">
						Project count shows how many unique projects triggered each agent — high reach means it's woven into your workflow
					</div>
				{/if}
			</div>

			<!-- Real Cost panel -->
			{#if true}
				{@const top5 = rightPanelAgents.slice(0, 5)}
				{@const top5Cost = top5.reduce((s, a) => s + a.total_cost_usd, 0)}
				{@const costMax = top5.length > 0 ? top5[0].total_cost_usd : 1}
				{@const otherAgents = rightPanelAgents.slice(5)}
				{@const otherCost = otherAgents.reduce((s, a) => s + a.total_cost_usd, 0)}
			<div class="rounded-lg" style="padding: 16px 18px; background: var(--bg-base); border: 1px solid var(--border);">
				<div style="font-size: 10px; font-weight: 700; color: var(--accent); text-transform: uppercase; letter-spacing: 0.12em; font-family: 'JetBrains Mono', monospace; margin-bottom: 2px;">Real Cost</div>
				<div style="font-size: 11px; color: var(--text-faint); margin-bottom: 12px;">across {analyticsTotalRuns} runs this period</div>

				<!-- Hero total -->
				<div class="flex items-baseline gap-2" style="margin-bottom: 4px;">
					<span style="font-size: 32px; font-weight: 700; color: var(--text-primary); font-family: 'JetBrains Mono', monospace; letter-spacing: -1.5px;">${analyticsTotalCost < 0.01 ? analyticsTotalCost.toFixed(4) : analyticsTotalCost.toFixed(2)}</span>
					<span style="font-size: 12px; color: var(--text-faint);">total</span>
				</div>
				<div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 14px; font-family: 'JetBrains Mono', monospace;">
					${analyticsTotalRuns > 0 ? (analyticsTotalCost / analyticsTotalRuns).toFixed(4) : '0.0000'} per run avg
				</div>

				<!-- Column headers -->
				<div style="display: grid; grid-template-columns: 1fr 1fr 68px; gap: 10px; padding: 0 4px; margin-bottom: 6px;">
					<div style="font-size: 9px; color: var(--text-faint); letter-spacing: 0.1em; text-transform: uppercase;">Agent</div>
					<div style="font-size: 9px; color: var(--text-faint); letter-spacing: 0.1em; text-transform: uppercase;">Cost share</div>
					<div style="font-size: 9px; color: var(--text-faint); letter-spacing: 0.1em; text-transform: uppercase; text-align: right;">Cost</div>
				</div>

				{#each top5 as agent}
					{@const barPct = costMax > 0 ? Math.round((agent.total_cost_usd / costMax) * 100) : 0}
					{@const displayName = getSubagentTypeDisplayName(agent.subagent_type)}
					<a
						href="/agents/{encodeURIComponent(agent.subagent_type)}"
						class="no-underline"
						style="display: grid; grid-template-columns: 1fr 1fr 68px; gap: 10px; align-items: center; padding: 7px 4px; border-radius: 5px; cursor: pointer;"
						onmouseenter={(e) => (e.currentTarget as HTMLElement).style.background = 'color-mix(in oklch, var(--nav-orange) 6%, transparent)'}
						onmouseleave={(e) => (e.currentTarget as HTMLElement).style.background = 'transparent'}
					>
						<div class="truncate" style="font-size: 12px; font-weight: 600; color: var(--text-primary); font-family: 'JetBrains Mono', monospace;" title={displayName}>{displayName}</div>
						<div style="background: color-mix(in oklch, var(--nav-orange) 15%, transparent); height: 7px; border-radius: 4px; overflow: hidden;">
							<div style="background: var(--nav-orange); width: {barPct}%; height: 7px;"></div>
						</div>
						<div style="font-size: 12px; font-weight: 700; color: var(--text-primary); text-align: right; font-family: 'JetBrains Mono', monospace;">${agent.total_cost_usd < 0.01 ? agent.total_cost_usd.toFixed(4) : agent.total_cost_usd.toFixed(2)}</div>
					</a>
				{/each}

				{#if otherAgents.length > 0}
					{@const otherBarPct = costMax > 0 ? Math.round((otherCost / costMax) * 100) : 0}
					<div style="display: grid; grid-template-columns: 1fr 1fr 68px; gap: 10px; align-items: center; padding: 7px 4px; border-top: 1px dashed var(--border-subtle); margin-top: 2px;">
						<div style="font-size: 11px; color: var(--text-faint); font-style: italic;">{otherAgents.length} other agents</div>
						<div style="background: var(--bg-muted); height: 7px; border-radius: 4px; overflow: hidden;">
							<div style="background: var(--text-faint); width: {Math.min(otherBarPct, 100)}%; height: 7px; opacity: 0.5;"></div>
						</div>
						<div style="font-size: 12px; font-weight: 600; color: var(--text-faint); text-align: right; font-family: 'JetBrains Mono', monospace;">${otherCost < 0.01 ? otherCost.toFixed(4) : otherCost.toFixed(2)}</div>
					</div>
				{/if}

				<div style="margin-top: 12px; border-top: 1px solid var(--border-subtle); padding-top: 8px; font-size: 10px; color: var(--text-faint); line-height: 1.6;">
					Actual cost from Claude API usage data
				</div>
			</div>
			{/if}

		</div>

	</div>

	{/if}

</div>

{/if}
