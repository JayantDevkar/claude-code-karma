<script lang="ts">
	import {
		Search,
		Zap,
		Sparkles,
		Info,
		TrendingUp,
		LayoutGrid,
		LayoutList,
		ChevronRight
	} from 'lucide-svelte';
	import { tick, onMount } from 'svelte';
	import { navigating } from '$app/stores';
	import { browser } from '$app/environment';
	import { replaceState, beforeNavigate } from '$app/navigation';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import KarmaIcon from '$lib/components/icons/Icon.svelte';
	import StackedAreaChart from '$lib/components/charts/StackedAreaChart.svelte';
	import { getCommandCategoryColorVars, getCommandCategoryLabel, getPluginColorVars } from '$lib/utils';
	import { API_BASE } from '$lib/config';
	import type { CommandUsage, UsageTrendResponse } from '$lib/api-types';

	let { data } = $props();

	function initParam(key: string, fallback: string): string {
		if (browser) return new URLSearchParams(window.location.search).get(key) ?? fallback;
		return fallback;
	}

	let activeView = $state<'overview' | 'analytics'>(
		(initParam('view', 'overview') as 'overview' | 'analytics')
	);
	let searchQuery = $state(initParam('search', ''));
	let selectedFilter = $state<'all' | 'builtin' | 'plugin' | 'user'>(
		(initParam('filter', 'all') as 'all' | 'builtin' | 'plugin' | 'user')
	);
	let selectedGroup = $state<string | null>(null);
	let commandsView = $state<'list' | 'grid'>('list');

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
	let allCommands = $derived<CommandUsage[]>(data.usage || []);

	// ── Grouping ───────────────────────────────────────────────────────────────
	interface CommandGroup {
		key: string;
		label: string;
		commands: CommandUsage[];
		pluginName: string | null;
		category: string;
	}

	let groupedCommands = $derived.by<CommandGroup[]>(() => {
		const groups = new Map<string, CommandGroup>();
		for (const cmd of allCommands) {
			const cat = cmd.category ?? 'user_command';
			let key: string, label: string, pluginName: string | null = null, category: string;
			if (cat === 'builtin_command') {
				key = 'builtin_command'; label = 'Built-in Commands'; category = 'builtin_command';
			} else if ((cat === 'plugin_command' || cat === 'plugin_skill') && cmd.plugin) {
				key = `plugin:${cmd.plugin}`; label = cmd.plugin; pluginName = cmd.plugin; category = 'plugin_command';
			} else if (cat === 'user_command') {
				key = 'user_command'; label = 'User Commands'; category = 'user_command';
			} else if (cat === 'custom_skill') {
				key = 'custom_skill'; label = 'Custom'; category = 'custom_skill';
			} else if (cat === 'bundled_skill') {
				key = 'bundled_skill'; label = 'Bundled'; category = 'bundled_skill';
			} else {
				key = cat; label = getCommandCategoryLabel(cat); pluginName = null; category = cat;
			}
			if (!groups.has(key)) groups.set(key, { key, label, commands: [], pluginName, category });
			groups.get(key)!.commands.push(cmd);
		}
		return Array.from(groups.values());
	});

	// ── Left panel: sorted by total uses desc ─────────────────────────────────
	let leftPanelGroups = $derived.by(() => {
		return [...groupedCommands]
			.filter(g => {
				if (selectedFilter === 'builtin') return g.category === 'builtin_command';
				if (selectedFilter === 'plugin') return g.category === 'plugin_command';
				if (selectedFilter === 'user') return g.category === 'user_command' || g.category === 'custom_skill';
				return true;
			})
			.sort((a, b) => {
				const aTotal = a.commands.reduce((sum, c) => sum + c.count, 0);
				const bTotal = b.commands.reduce((sum, c) => sum + c.count, 0);
				return bTotal - aTotal;
			});
	});

	// ── Stats ──────────────────────────────────────────────────────────────────
	let totalUses = $derived(allCommands.reduce((sum, c) => sum + c.count, 0));
	let activeCommandsCount = $derived(allCommands.filter(c => c.count > 0).length);
	let totalCommandsCount = $derived(allCommands.length);
	let neverUsedCount = $derived(allCommands.filter(c => c.count === 0).length);
	let globalMax = $derived(
		allCommands.length > 0 ? Math.max(...allCommands.map(c => c.count), 1) : 1
	);

	// ── Right panel: active commands, filtered + sorted ───────────────────────
	let rightPanelCommands = $derived.by(() => {
		let commands = allCommands.filter(c => c.count > 0);

		if (selectedGroup !== null) {
			const grp = groupedCommands.find(g => g.key === selectedGroup);
			if (grp) commands = commands.filter(c => grp.commands.some(gc => gc.name === c.name));
		}

		if (selectedFilter === 'builtin') commands = commands.filter(c => c.category === 'builtin_command');
		else if (selectedFilter === 'plugin') commands = commands.filter(c => c.category === 'plugin_command' || c.category === 'plugin_skill');
		else if (selectedFilter === 'user') commands = commands.filter(c => c.category === 'user_command' || c.category === 'custom_skill');

		if (searchQuery.trim()) {
			const q = searchQuery.toLowerCase();
			commands = commands.filter(c =>
				c.name.toLowerCase().includes(q) ||
				(c.description && c.description.toLowerCase().includes(q)) ||
				(c.plugin && c.plugin.toLowerCase().includes(q))
			);
		}

		return commands.slice().sort((a, b) => b.count - a.count);
	});

	// ── Analytics derived ─────────────────────────────────────────────────────
	let analyticsTotalUses = $derived(rightPanelCommands.reduce((sum, c) => sum + c.count, 0));
	let trendRange = $state<'7d' | '30d' | '90d'>('90d');
	let trendData = $state<UsageTrendResponse | null>(null);
	let trendLoading = $state(false);
	let trendRangeUserOverride = $state(false);

	const periodMap: Record<'7d' | '30d' | '90d', string> = { '7d': 'week', '30d': 'month', '90d': 'quarter' };

	$effect(() => {
		if (!browser || activeView !== 'analytics') return;
		trendLoading = true;
		const url = new URL(`${API_BASE}/commands/usage/trend`);
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

	// ── Session reach ─────────────────────────────────────────────────────────
	let sessionReachCommands = $derived(
		rightPanelCommands.slice().sort((a, b) => (b.session_count ?? 0) - (a.session_count ?? 0)).slice(0, 8)
	);
	let sessionReachMax = $derived(sessionReachCommands.length > 0 ? (sessionReachCommands[0].session_count ?? 1) : 1);

	// ── Insight banner ────────────────────────────────────────────────────────
	let insightText = $derived.by(() => {
		if (rightPanelCommands.length === 0) return null;
		const top = rightPanelCommands[0];
		const topSession = sessionReachCommands[0];
		return {
			active: rightPanelCommands.length,
			topName: top.name,
			topCount: top.count,
			topBySessionName: topSession?.name ?? top.name,
			topBySessionCount: topSession?.session_count ?? 0
		};
	});

	// ── Color helpers ──────────────────────────────────────────────────────────
	function getGroupColors(group: CommandGroup) {
		if (group.pluginName) return getPluginColorVars(group.pluginName);
		return getCommandCategoryColorVars(group.category);
	}

	function getCmdColors(cmd: CommandUsage) {
		const cat = cmd.category ?? 'user_command';
		if ((cat === 'plugin_command' || cat === 'plugin_skill') && cmd.plugin) return getPluginColorVars(cmd.plugin);
		return getCommandCategoryColorVars(cat);
	}

	function getSourceBadgeLabel(cmd: CommandUsage): string {
		const cat = cmd.category ?? 'user_command';
		if (cmd.plugin) return cmd.plugin;
		return getCommandCategoryLabel(cat);
	}

	// ── getGroupFor for StackedAreaChart ──────────────────────────────────────
	function getGroupFor(name: string): { key: string; label: string; color: string } | null {
		const cmd = allCommands.find(c => c.name === name);
		if (!cmd) return null;
		const cat = cmd.category ?? 'user_command';
		if ((cat === 'plugin_command' || cat === 'plugin_skill') && cmd.plugin) {
			const colors = getPluginColorVars(cmd.plugin);
			return { key: `plugin:${cmd.plugin}`, label: cmd.plugin, color: colors.color };
		}
		const colors = getCommandCategoryColorVars(cat);
		return { key: cat, label: getCommandCategoryLabel(cat), color: colors.color };
	}

	// ── Compact date helper ───────────────────────────────────────────────────
	function shortDate(ts: string | null | undefined): string {
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

	let coverageOpen = $state(false);

	function toggleGroup(group: CommandGroup) {
		const key = group.key;
		if (selectedGroup === key) selectedGroup = null;
		else selectedGroup = key;
	}

	// ── Scroll save/restore ───────────────────────────────────────────────────
	const SCROLL_KEY = 'commands_scroll';

	beforeNavigate(({ to }) => {
		if (!browser) return;
		if (to?.route.id?.startsWith('/commands/')) {
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

	let isPageLoading = $derived(!!$navigating && $navigating.to?.route.id === '/commands');
</script>

{#if isPageLoading}
	<div class="-mx-6 -my-8 flex items-center justify-center" style="height: calc(100vh - 56px);">
		<div class="flex flex-col items-center gap-3">
			<Zap size={32} class="text-[var(--accent)] animate-pulse" />
			<span class="text-sm text-[var(--text-muted)]">Loading commands…</span>
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
			title="Commands"
			iconName="commands"
			iconColor="--nav-red"
			breadcrumbs={[{ label: 'Dashboard', href: '/' }, { label: 'Commands' }]}
			subtitle="Which commands are pulling their weight?"
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
				{#each ([['all', 'All'], ['builtin', 'Built-in'], ['plugin', 'Plugin'], ['user', 'User']] as const) as [val, lbl]}
					<button
						onclick={() => selectedFilter = val}
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
					aria-label="Search commands"
					placeholder="Search commands…"
					style="width: 180px; padding: 4px 10px 4px 26px; font-size: 12px; background: var(--bg-subtle); border: 1px solid var(--border); border-radius: 8px; color: var(--text-primary); outline: none;"
					data-search-input
				/>
			</div>
		</div>
	</div>

	{#if activeView === 'overview'}
	<!-- Split view -->
	<div class="flex flex-1 min-h-0 overflow-hidden" style="padding: 0 12px 12px; gap: 10px;">

		<!-- ── Left Panel: Source Coverage ────────────────────────────────────── -->
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
					<span style="font-size: 10px; font-weight: 700; color: var(--nav-red); text-transform: uppercase; letter-spacing: 0.12em; font-family: 'JetBrains Mono', monospace;">
						Source Coverage
					</span>
					<div style="color: var(--text-faint); transition: transform 0.2s; transform: rotate({coverageOpen ? 90 : 0}deg);">
						<ChevronRight size={13} />
					</div>
				</div>
				<!-- Stats: fill full width -->
				<div class="flex items-center w-full">
					<div class="flex flex-col flex-1 items-center">
						<span style="font-size: 22px; font-weight: 700; font-family: 'JetBrains Mono', monospace; color: var(--text-primary); letter-spacing: -1px;">{totalUses.toLocaleString()}</span>
						<span style="font-size: 9px; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.06em;">uses</span>
					</div>
					<div style="width: 1px; height: 32px; background: var(--border);"></div>
					<div class="flex flex-col flex-1 items-center">
						<span style="font-size: 22px; font-weight: 700; font-family: 'JetBrains Mono', monospace; color: var(--text-primary); letter-spacing: -1px;">{activeCommandsCount}<span style="font-size: 13px; font-weight: 500; color: var(--text-faint);">/{totalCommandsCount}</span></span>
						<span style="font-size: 9px; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.06em;">active</span>
					</div>
					{#if neverUsedCount > 0}
						<div style="width: 1px; height: 32px; background: var(--border);"></div>
						<div class="flex flex-col flex-1 items-center">
							<span style="font-size: 22px; font-weight: 700; font-family: 'JetBrains Mono', monospace; color: var(--nav-orange); letter-spacing: -1px;">{neverUsedCount}</span>
							<span style="font-size: 9px; color: var(--nav-orange); text-transform: uppercase; letter-spacing: 0.06em; opacity: 0.8;">unused</span>
						</div>
					{/if}
				</div>
			</button>

			<!-- Group rows — only when accordion is open -->
			{#if coverageOpen}
			<div class="flex-1 overflow-y-auto">
				{#each leftPanelGroups as group}
					{@const colors = getGroupColors(group)}
					{@const groupTotal = group.commands.reduce((sum, c) => sum + c.count, 0)}
					{@const pct = totalUses > 0 ? Math.round((groupTotal / totalUses) * 100) : 0}
					{@const isSelected = selectedGroup === group.key}
					<div
						role="button"
						tabindex="0"
						onclick={() => toggleGroup(group)}
						onkeydown={(e) => e.key === 'Enter' && toggleGroup(group)}
						class="border-b cursor-pointer group/row transition-colors"
						style="
							padding: 10px 20px;
							border-color: var(--border-subtle);
							background: {isSelected ? 'var(--accent-muted)' : 'transparent'};
							border-left: {isSelected ? '2px solid var(--accent)' : '2px solid transparent'};
						"
					>
						<!-- Name row -->
						<div class="flex items-center justify-between gap-2" style="margin-bottom: 6px;">
							<span class="flex-1 min-w-0 truncate" style="font-size: 12px; font-weight: 600; color: var(--text-primary); font-family: 'JetBrains Mono', monospace;">
								{group.label}
							</span>
							<div class="flex items-center gap-1.5 flex-shrink-0">
								{#if groupTotal === Math.max(...leftPanelGroups.map(g => g.commands.reduce((s, c) => s + c.count, 0)))}
									<TrendingUp size={10} style="color: var(--nav-orange);" />
								{/if}
								<span style="font-size: 12px; font-weight: 700; font-family: 'JetBrains Mono', monospace; color: var(--text-secondary);">
									{pct}%
								</span>
							</div>
						</div>

						<!-- Bar + count -->
						<div class="flex items-center gap-2">
							<div class="flex-1" style="height: 3px; border-radius: 2px; background: var(--bg-muted); overflow: hidden;">
								<div style="height: 100%; border-radius: 2px; width: {pct}%; background: {colors.color}; opacity: 0.6;"></div>
							</div>
							<span style="font-size: 10px; color: var(--text-faint); font-family: 'JetBrains Mono', monospace; flex-shrink: 0;">
								{groupTotal.toLocaleString()}
							</span>
						</div>
					</div>
				{/each}
			</div>

			<!-- Footer -->
			<div class="flex-shrink-0 border-t flex items-center justify-between" style="padding: 10px 16px; border-color: var(--border-subtle);">
				<span style="font-size: 10px; color: var(--text-faint);">Sorted by total uses</span>
				{#if selectedGroup !== null}
					<button onclick={() => selectedGroup = null} style="font-size: 10px; color: var(--accent); font-weight: 600;">
						Clear ×
					</button>
				{/if}
			</div>
			{/if}
		</div>

		<!-- ── Right Panel: Top Commands Leaderboard ───────────────────────────── -->
		<div class="flex-1 flex flex-col overflow-hidden min-w-0" style="background: var(--bg-base); border: 1px solid var(--border); border-radius: 12px;">

			<!-- Panel header -->
			<div
				class="flex-shrink-0 flex items-center justify-between border-b"
				style="padding: 14px 16px 12px; background: var(--bg-base); border-color: var(--border);"
			>
				<div>
					<div style="font-size: 10px; font-weight: 700; color: var(--nav-red); text-transform: uppercase; letter-spacing: 0.12em; font-family: 'JetBrains Mono', monospace; margin-bottom: 3px;">Top Commands</div>
					<div style="font-size: 11px; color: var(--text-faint);">
						{#if selectedGroup !== null}
							{@const grp = leftPanelGroups.find(g => g.key === selectedGroup)}
							{rightPanelCommands.length} commands · {grp?.label ?? selectedGroup}
						{:else}
							{rightPanelCommands.length} active commands ranked by usage
						{/if}
					</div>
				</div>

				<!-- List/Grid toggle -->
				<div class="flex rounded-md overflow-hidden" style="border: 1px solid var(--border);">
					<button
						onclick={() => commandsView = 'list'}
						style="padding: 5px 8px; background: {commandsView === 'list' ? 'var(--bg-muted)' : 'transparent'}; color: {commandsView === 'list' ? 'var(--text-primary)' : 'var(--text-faint)'}; display: flex; align-items: center;"
						title="List view"
					><LayoutList size={13} /></button>
					<button
						onclick={() => commandsView = 'grid'}
						style="padding: 5px 8px; background: {commandsView === 'grid' ? 'var(--bg-muted)' : 'transparent'}; color: {commandsView === 'grid' ? 'var(--text-primary)' : 'var(--text-faint)'}; display: flex; align-items: center; border-left: 1px solid var(--border);"
						title="Grid view"
					><LayoutGrid size={13} /></button>
				</div>
			</div>

			<!-- Table container -->
			<div class="flex-1 overflow-y-auto">
				{#if rightPanelCommands.length === 0}
					<div class="flex flex-col items-center justify-center h-full gap-3">
						<Search size={36} style="color: var(--text-faint);" />
						<p style="font-size: 13px; color: var(--text-secondary); font-weight: 500;">No matching commands</p>
						<p style="font-size: 11px; color: var(--text-faint);">Try adjusting filters or search</p>
					</div>
				{:else if commandsView === 'list'}
					<!-- Column headers -->
					<div
						class="grid sticky top-0 border-b"
						style="background: var(--bg-base); border-color: var(--border); grid-template-columns: 32px 1fr 160px 100px 56px 64px 72px; padding: 10px 12px 8px;"
					>
						<div style="font-size: 10px; color: var(--text-faint); letter-spacing: 0.06em; text-transform: uppercase; text-align: center;">#</div>
						<div style="font-size: 10px; color: var(--text-faint); letter-spacing: 0.06em; text-transform: uppercase;">Command</div>
						<div style="font-size: 10px; color: var(--text-faint); letter-spacing: 0.06em; text-transform: uppercase;">Source</div>
						<div style="font-size: 10px; color: var(--text-faint); letter-spacing: 0.06em; text-transform: uppercase; padding: 0 8px;">Usage</div>
						<div style="font-size: 10px; color: var(--text-faint); letter-spacing: 0.06em; text-transform: uppercase; text-align: right;">Uses</div>
						<div style="font-size: 10px; color: var(--text-faint); letter-spacing: 0.06em; text-transform: uppercase; text-align: right;">Sessions</div>
						<div style="font-size: 10px; color: var(--text-faint); letter-spacing: 0.06em; text-transform: uppercase; text-align: right;">Last used</div>
					</div>

					<!-- Command rows -->
					{#each rightPanelCommands as cmd, i (cmd.name)}
						{@const displayName = '/' + cmd.name}
						{@const barWidth = Math.round((cmd.count / globalMax) * 100)}
						{@const sourceBadge = getSourceBadgeLabel(cmd)}
						{@const colors = getCmdColors(cmd)}
						{@const cat = cmd.category ?? 'user_command'}
						{@const useColor = selectedFilter === 'plugin' && (cat === 'plugin_command' || cat === 'plugin_skill')}
						<a
							href="/commands/{encodeURIComponent(cmd.name)}"
							class="grid border-b transition-colors hover:bg-[var(--bg-subtle)] no-underline"
							style="grid-template-columns: 32px 1fr 160px 100px 56px 64px 72px; padding: 8px 12px; border-color: var(--border-subtle); align-items: center;"
						>
							<div style="font-size: 11px; color: var(--text-faint); font-family: 'JetBrains Mono', monospace; text-align: center;">{i + 1}</div>
							<div class="min-w-0 pr-3">
								<span class="truncate block" style="font-size: 13px; font-weight: 600; color: var(--text-primary); font-family: 'JetBrains Mono', monospace;" title={displayName}>{displayName}</span>
							</div>
							<div class="min-w-0">
								{#if useColor && cmd.plugin}
									<span class="truncate block rounded" style="font-size: 10px; font-weight: 700; font-family: 'JetBrains Mono', monospace; padding: 2px 7px; color: var(--bg-base); background: {colors.color}; display: inline-block; max-width: 100%;" title={cmd.plugin}>{cmd.plugin}</span>
								{:else}
									<span class="truncate block" style="font-size: 11px; color: var(--text-secondary); font-family: 'JetBrains Mono', monospace;" title={sourceBadge}>{sourceBadge}</span>
								{/if}
							</div>
							<div style="padding: 0 8px;">
								<div style="background: var(--bg-muted); height: 4px; border-radius: 2px; overflow: hidden;">
									<div style="height: 100%; border-radius: 2px; width: {barWidth}%; background: {useColor ? colors.color : 'var(--nav-red)'}; opacity: 0.7;"></div>
								</div>
							</div>
							<div style="font-size: 13px; font-weight: 700; font-family: 'JetBrains Mono', monospace; text-align: right; color: {useColor ? colors.color : 'var(--text-primary)'};">{cmd.count}</div>
							<div style="font-size: 12px; color: var(--text-secondary); font-family: 'JetBrains Mono', monospace; text-align: right;">{cmd.session_count ?? 0}</div>
							<div style="font-size: 11px; font-weight: 500; color: var(--text-secondary); font-family: 'JetBrains Mono', monospace; text-align: right;">{shortDate(cmd.last_used)}</div>
						</a>
					{/each}
				{:else}
					<!-- Grid view -->
					<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 8px; padding: 12px;">
						{#each rightPanelCommands as cmd, i (cmd.name)}
							{@const displayName = '/' + cmd.name}
							{@const barWidth = Math.round((cmd.count / globalMax) * 100)}
							{@const sourceBadge = getSourceBadgeLabel(cmd)}
							{@const colors = getCmdColors(cmd)}
							{@const cat = cmd.category ?? 'user_command'}
							{@const useColor = selectedFilter === 'plugin' && (cat === 'plugin_command' || cat === 'plugin_skill')}
							<a
								href="/commands/{encodeURIComponent(cmd.name)}"
								class="flex flex-col no-underline rounded-lg transition-all"
								style="padding: 14px 14px 12px; gap: 6px;
									border: 1px solid {useColor ? colors.subtle : 'var(--border-subtle)'};
									background: {useColor ? colors.subtle : 'var(--bg-subtle)'};"
								onmouseenter={(e) => { (e.currentTarget as HTMLElement).style.borderColor = useColor ? colors.color : 'var(--border)'; (e.currentTarget as HTMLElement).style.background = useColor ? colors.subtle : 'var(--bg-base)'; }}
								onmouseleave={(e) => { (e.currentTarget as HTMLElement).style.borderColor = useColor ? colors.subtle : 'var(--border-subtle)'; (e.currentTarget as HTMLElement).style.background = useColor ? colors.subtle : 'var(--bg-subtle)'; }}
							>
								<!-- Count — hero -->
								<div style="font-size: 28px; font-weight: 800; font-family: 'JetBrains Mono', monospace; letter-spacing: -1px; line-height: 1;
									color: {useColor ? colors.color : 'var(--nav-red)'};">
									{cmd.count}
								</div>

								<!-- Command name -->
								<div class="min-w-0" style="margin-top: 2px;">
									<span class="block truncate" style="font-size: 12px; font-weight: 600; color: var(--text-primary); font-family: 'JetBrains Mono', monospace;" title={displayName}>{displayName}</span>
								</div>

								<!-- Bar -->
								<div style="background: var(--bg-muted); height: 3px; border-radius: 2px; overflow: hidden; margin-top: 4px;">
									<div style="height: 100%; border-radius: 2px; width: {barWidth}%; background: {useColor ? colors.color : 'var(--nav-red)'}; opacity: 0.7;"></div>
								</div>

								<!-- Footer: source · last used -->
								<div class="flex items-center justify-between" style="margin-top: 2px; gap: 4px;">
									{#if useColor && cmd.plugin}
										<span
											class="truncate rounded"
											style="font-size: 10px; font-weight: 700; font-family: 'JetBrains Mono', monospace; padding: 2px 7px; color: var(--bg-base); background: {colors.color}; flex-shrink: 1; min-width: 0;"
											title={cmd.plugin}
										>{cmd.plugin}</span>
									{:else}
										<span style="font-size: 10px; color: var(--text-secondary); font-family: 'JetBrains Mono', monospace;" class="truncate">{sourceBadge}</span>
									{/if}
									<span class="flex items-center gap-1 flex-shrink-0" style="color: var(--text-faint);">
										<svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
										<span style="font-size: 10px; font-weight: 500; font-family: 'JetBrains Mono', monospace;">{shortDate(cmd.last_used)}</span>
									</span>
								</div>
							</a>
						{/each}
					</div>
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
					<strong>{insightText.active} active commands</strong> · /{insightText.topName} leads with {insightText.topCount} uses · /{insightText.topBySessionName} spans {insightText.topBySessionCount} sessions
				</span>
			</div>
		{/if}

		<!-- Stacked area chart -->
		<div class="rounded-lg" style="padding: 16px 18px; background: var(--bg-base); border: 1px solid var(--border);">
			<StackedAreaChart
				{trendData}
				loading={trendLoading}
				range={trendRange}
				onRangeChange={(r) => { trendRangeUserOverride = true; trendRange = r; }}
				{getGroupFor}
				label="Command Uses Over Time"
			/>
		</div>

		<!-- Bottom row: Session Reach + Cost -->
		<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px; align-items: start;">

			<!-- Session Reach panel -->
			<div class="rounded-lg" style="padding: 16px 18px; background: var(--bg-base); border: 1px solid var(--border);">
				<div style="font-size: 10px; font-weight: 700; color: var(--accent); text-transform: uppercase; letter-spacing: 0.12em; font-family: 'JetBrains Mono', monospace; margin-bottom: 2px;">Session Reach</div>
				<div style="font-size: 11px; color: var(--text-faint); margin-bottom: 14px;">which commands are embedded in your workflow</div>

				{#if sessionReachCommands.length === 0}
					<div style="color: var(--text-faint); font-size: 12px; padding: 12px 0;">No data</div>
				{:else}
					<!-- Column headers -->
					<div style="display: grid; grid-template-columns: 1fr 80px 44px; gap: 8px; padding: 0 4px; margin-bottom: 6px;">
						<div style="font-size: 9px; color: var(--text-faint); letter-spacing: 0.1em; text-transform: uppercase;">Command</div>
						<div style="font-size: 9px; color: var(--text-faint); letter-spacing: 0.1em; text-transform: uppercase; text-align: center;">sessions</div>
						<div style="font-size: 9px; color: var(--text-faint); letter-spacing: 0.1em; text-transform: uppercase; text-align: right;">reach</div>
					</div>
					<div style="border-top: 1px solid var(--border-subtle); padding-top: 4px;">
						{#each sessionReachCommands as cmd}
							{@const colors = getCmdColors(cmd)}
							{@const sessions = cmd.session_count ?? 0}
							{@const barPct = Math.round((sessions / sessionReachMax) * 100)}
							{@const reachPct = analyticsTotalUses > 0 ? Math.round((sessions / analyticsTotalUses) * 100) : 0}
							<a
								href="/commands/{encodeURIComponent(cmd.name)}"
								class="no-underline"
								style="display: grid; grid-template-columns: 1fr 80px 44px; gap: 8px; align-items: center; padding: 5px 4px; border-radius: 4px; cursor: pointer;"
								onmouseenter={(e) => (e.currentTarget as HTMLElement).style.background = 'var(--bg-subtle)'}
								onmouseleave={(e) => (e.currentTarget as HTMLElement).style.background = 'transparent'}
							>
								<div class="flex items-center gap-1.5 min-w-0">
									<div style="width: 5px; height: 5px; border-radius: 50%; background: {colors.color}; flex-shrink: 0;"></div>
									<span class="truncate" style="font-size: 12px; font-weight: 600; color: var(--text-primary); font-family: 'JetBrains Mono', monospace;" title={'/' + cmd.name}>/{cmd.name}</span>
								</div>
								<div style="background: var(--bg-muted); height: 5px; border-radius: 3px; overflow: hidden;">
									<div style="height: 100%; border-radius: 3px; width: {barPct}%; background: var(--accent);"></div>
								</div>
								<div style="font-size: 10px; font-weight: 700; color: {reachPct >= 30 ? 'var(--accent)' : 'var(--text-faint)'}; text-align: right; font-family: 'JetBrains Mono', monospace;">{sessions}</div>
							</a>
						{/each}
					</div>
					<div style="margin-top: 10px; border-top: 1px solid var(--border-subtle); padding-top: 8px; font-size: 10px; color: var(--text-faint); line-height: 1.5;">
						Sessions count how many unique conversations used each command — a high count means it's woven into your day-to-day
					</div>
				{/if}
			</div>

			<!-- Cost estimation panel -->
			{#if true}
				{@const avgTokens = 500}
				{@const pricePerMTok = 3.00}
				{@const top5 = rightPanelCommands.slice(0, 5)}
				{@const top5Total = top5.reduce((s, c) => s + c.count, 0)}
				{@const allTotal = analyticsTotalUses}
				{@const costMax = top5.length > 0 ? top5[0].count : 1}
				{@const otherCount = allTotal - top5Total}
				{@const estTotalCost = (allTotal * avgTokens * pricePerMTok) / 1_000_000}
				{@const perInv = allTotal > 0 ? (estTotalCost / allTotal) : 0}
			<div class="rounded-lg" style="padding: 16px 18px; background: var(--bg-base); border: 1px solid var(--border);">
				<div style="font-size: 10px; font-weight: 700; color: var(--accent); text-transform: uppercase; letter-spacing: 0.12em; font-family: 'JetBrains Mono', monospace; margin-bottom: 2px;">Estimated Cost</div>
				<div style="font-size: 11px; color: var(--text-faint); margin-bottom: 12px;">across {allTotal} uses this period</div>

				<!-- Hero total -->
				<div class="flex items-baseline gap-2" style="margin-bottom: 4px;">
					<span style="font-size: 32px; font-weight: 700; color: var(--text-primary); font-family: 'JetBrains Mono', monospace; letter-spacing: -1.5px;">~${estTotalCost < 0.01 ? estTotalCost.toFixed(4) : estTotalCost.toFixed(2)}</span>
					<span style="font-size: 12px; color: var(--text-faint);">total</span>
				</div>
				<div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 14px; font-family: 'JetBrains Mono', monospace;">~${perInv.toFixed(4)} per use avg</div>

				<!-- Callout -->
				<div class="flex gap-2 rounded" style="padding: 7px 10px; margin-bottom: 14px; background: var(--nav-orange-subtle); border: 1px solid color-mix(in oklch, var(--nav-orange) 30%, transparent);">
					<Info size={12} style="color: var(--nav-orange); flex-shrink: 0; margin-top: 1px;" />
					<span style="font-size: 10px; color: var(--nav-orange); line-height: 1.5;">Using ~500 tokens/use avg · actual cost varies by model and command complexity</span>
				</div>

				<!-- Column headers -->
				<div style="display: grid; grid-template-columns: 1fr 1fr 40px 68px; gap: 10px; padding: 0 4px; margin-bottom: 6px;">
					<div style="font-size: 9px; color: var(--text-faint); letter-spacing: 0.1em; text-transform: uppercase;">Command</div>
					<div style="font-size: 9px; color: var(--text-faint); letter-spacing: 0.1em; text-transform: uppercase;">Cost share</div>
					<div style="font-size: 9px; color: var(--text-faint); letter-spacing: 0.1em; text-transform: uppercase; text-align: right;">%</div>
					<div style="font-size: 9px; color: var(--text-faint); letter-spacing: 0.1em; text-transform: uppercase; text-align: right;">Est. cost</div>
				</div>

				{#each top5 as cmd}
					{@const cmdCost = (cmd.count * avgTokens * pricePerMTok) / 1_000_000}
					{@const pct = allTotal > 0 ? Math.round((cmd.count / allTotal) * 100) : 0}
					{@const barPct = Math.round((cmd.count / costMax) * 100)}
					<a
						href="/commands/{encodeURIComponent(cmd.name)}"
						class="no-underline"
						style="display: grid; grid-template-columns: 1fr 1fr 40px 68px; gap: 10px; align-items: center; padding: 7px 4px; border-radius: 5px; cursor: pointer;"
						onmouseenter={(e) => (e.currentTarget as HTMLElement).style.background = 'color-mix(in oklch, var(--nav-orange) 6%, transparent)'}
						onmouseleave={(e) => (e.currentTarget as HTMLElement).style.background = 'transparent'}
					>
						<div class="truncate" style="font-size: 12px; font-weight: 600; color: var(--text-primary); font-family: 'JetBrains Mono', monospace;" title={'/' + cmd.name}>/{cmd.name}</div>
						<div style="background: color-mix(in oklch, var(--nav-orange) 15%, transparent); height: 7px; border-radius: 4px; overflow: hidden;">
							<div style="background: var(--nav-orange); width: {barPct}%; height: 7px;"></div>
						</div>
						<div style="font-size: 11px; color: var(--text-faint); text-align: right; font-family: 'JetBrains Mono', monospace;">{pct}%</div>
						<div style="font-size: 12px; font-weight: 700; color: var(--text-primary); text-align: right; font-family: 'JetBrains Mono', monospace;">~${cmdCost.toFixed(3)}</div>
					</a>
				{/each}

				{#if otherCount > 0}
					{@const otherCost = (otherCount * avgTokens * pricePerMTok) / 1_000_000}
					{@const otherPct = Math.round((otherCount / allTotal) * 100)}
					{@const otherBarPct = Math.round((otherCount / costMax) * 100)}
					<div style="display: grid; grid-template-columns: 1fr 1fr 40px 68px; gap: 10px; align-items: center; padding: 7px 4px; border-top: 1px dashed var(--border-subtle); margin-top: 2px;">
						<div style="font-size: 11px; color: var(--text-faint); font-style: italic;">{rightPanelCommands.length - 5} other commands</div>
						<div style="background: var(--bg-muted); height: 7px; border-radius: 4px; overflow: hidden;">
							<div style="background: var(--text-faint); width: {Math.min(otherBarPct, 100)}%; height: 7px; opacity: 0.5;"></div>
						</div>
						<div style="font-size: 11px; color: var(--text-faint); text-align: right; font-family: 'JetBrains Mono', monospace;">{otherPct}%</div>
						<div style="font-size: 12px; font-weight: 600; color: var(--text-faint); text-align: right; font-family: 'JetBrains Mono', monospace;">~${otherCost.toFixed(3)}</div>
					</div>
				{/if}

				<div style="margin-top: 12px; border-top: 1px solid var(--border-subtle); padding-top: 8px; font-size: 10px; color: var(--text-faint); line-height: 1.6;">
					~{avgTokens} tokens/use · Sonnet ${pricePerMTok}/MTok · actual cost varies by model &amp; command
				</div>
			</div>
			{/if}

		</div>

	</div>

	{/if}

</div>

{/if}
