<script lang="ts">
	import {
		Search,
		Sparkles,
		Info,
		TrendingUp,
		ChevronRight
	} from 'lucide-svelte';
	import { tick } from 'svelte';
	import { navigating } from '$app/stores';
	import { browser } from '$app/environment';
	import { replaceState } from '$app/navigation';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import { getServerColorVars, getToolItemChartHex } from '$lib/utils/mcp';
	import { API_BASE } from '$lib/config';
	import type { UsageTrendResponse, McpServer, McpToolSummary } from '$lib/api-types';

	let { data } = $props();

	function initParam(key: string, fallback: string): string {
		if (browser) return new URLSearchParams(window.location.search).get(key) ?? fallback;
		return fallback;
	}

	let activeView = $state<'overview' | 'analytics'>(
		(initParam('view', 'overview') as 'overview' | 'analytics')
	);
	let searchQuery = $state(initParam('search', ''));
	let selectedFilter = $state<'all' | 'builtin' | 'plugin' | 'standalone'>(
		(initParam('filter', 'all') as 'all' | 'builtin' | 'plugin' | 'standalone')
	);
	let selectedServer = $state<string | null>(null);

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

	// ── Derived data ───────────────────────────────────────────────────────────
	let allServers = $derived(data.overview.servers ?? []);
	let totalCalls = $derived(data.overview.total_calls);

	// Left panel: servers sorted by total_calls desc, filtered by chip
	let leftPanelServers = $derived.by(() => {
		let servers = allServers;
		if (selectedFilter === 'builtin') servers = servers.filter(s => s.source === 'builtin');
		else if (selectedFilter === 'plugin') servers = servers.filter(s => s.source === 'plugin');
		else if (selectedFilter === 'standalone') servers = servers.filter(s => s.source === 'standalone');
		return [...servers].sort((a, b) => b.total_calls - a.total_calls);
	});

	// All tools flattened from all servers
	interface FlatTool {
		tool: McpToolSummary;
		server: McpServer;
	}

	let allToolsFlat = $derived.by<FlatTool[]>(() => {
		const out: FlatTool[] = [];
		for (const server of allServers) {
			for (const tool of server.tools) {
				out.push({ tool, server });
			}
		}
		return out.sort((a, b) => b.tool.calls - a.tool.calls);
	});

	// Right panel tools, filtered by server selection + filter chips + search
	let rightPanelTools = $derived.by<FlatTool[]>(() => {
		let tools = allToolsFlat;

		if (selectedServer !== null) {
			tools = tools.filter(t => t.server.name === selectedServer);
		}

		if (selectedFilter === 'builtin') tools = tools.filter(t => t.server.source === 'builtin');
		else if (selectedFilter === 'plugin') tools = tools.filter(t => t.server.source === 'plugin');
		else if (selectedFilter === 'standalone') tools = tools.filter(t => t.server.source === 'standalone');

		if (searchQuery.trim()) {
			const q = searchQuery.toLowerCase();
			tools = tools.filter(t =>
				t.tool.name.toLowerCase().includes(q) ||
				t.server.display_name.toLowerCase().includes(q)
			);
		}

		return tools;
	});

	let globalMax = $derived(
		rightPanelTools.length > 0 ? Math.max(...rightPanelTools.map(t => t.tool.calls), 1) : 1
	);

	// ── Analytics data ─────────────────────────────────────────────────────────
	let trendRange = $state<'7d' | '30d' | '90d'>('90d');
	let trendData = $state<UsageTrendResponse | null>(null);
	let trendLoading = $state(false);
	let trendRangeUserOverride = $state(false);

	const periodMap: Record<'7d' | '30d' | '90d', string> = { '7d': 'week', '30d': 'month', '90d': 'quarter' };

	$effect(() => {
		if (!browser || activeView !== 'analytics') return;
		trendLoading = true;
		const url = new URL(`${API_BASE}/tools/usage/trend`);
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

	// Build lookup: tool full_name → { serverName, displayName, color }
	let toolServerMap = $derived.by(() => {
		const map = new Map<string, { serverName: string; displayName: string; color: string }>();
		for (const server of allServers) {
			const { color } = getServerColorVars(server.name, server.plugin_name);
			for (const tool of server.tools) {
				map.set(tool.full_name, { serverName: server.name, displayName: server.display_name, color });
			}
		}
		return map;
	});

	// Rebuild daily totals for the trend chart
	let trendPoints = $derived.by(() => {
		if (!trendData) return [];
		return [...trendData.trend].sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());
	});

	// ── Stacked chart helpers ─────────────────────────────────────────────────
	function catmullRomPath(pts: {x: number, y: number}[]): string {
		if (pts.length < 2) return '';
		let d = `M ${pts[0].x.toFixed(1)},${pts[0].y.toFixed(1)}`;
		for (let i = 0; i < pts.length - 1; i++) {
			const p0 = pts[Math.max(0, i - 1)];
			const p1 = pts[i];
			const p2 = pts[i + 1];
			const p3 = pts[Math.min(pts.length - 1, i + 2)];
			const cp1x = p1.x + (p2.x - p0.x) / 6;
			const cp1y = p1.y + (p2.y - p0.y) / 6;
			const cp2x = p2.x - (p3.x - p1.x) / 6;
			const cp2y = p2.y - (p3.y - p1.y) / 6;
			d += ` C ${cp1x.toFixed(1)},${cp1y.toFixed(1)} ${cp2x.toFixed(1)},${cp2y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`;
		}
		return d;
	}

	function stackedAreaPath(topPts: {x:number,y:number}[], botPts: {x:number,y:number}[] | null, baseY: number): { line: string; area: string } {
		const line = catmullRomPath(topPts);
		if (!botPts) {
			const last = topPts[topPts.length - 1];
			const first = topPts[0];
			return { line, area: `${line} L ${last.x.toFixed(1)},${baseY} L ${first.x.toFixed(1)},${baseY} Z` };
		}
		const revBot = [...botPts].reverse();
		const revLine = catmullRomPath(revBot);
		const revFirst = revBot[0];
		return { line, area: `${line} L ${revFirst.x.toFixed(1)},${revFirst.y.toFixed(1)} ${revLine.replace(/^M [^C]*C/, 'C')} Z` };
	}

	let stackedChartData = $derived.by(() => {
		if (!trendData?.trend_by_item || trendPoints.length === 0) return null;
		const dates = trendPoints.map(p => p.date);
		const cX1 = 48, cX2 = 892, cY1 = 8, cY2 = 156;
		const cW = cX2 - cX1, cH = cY2 - cY1;

		// Group trend_by_item by server
		const groupMap = new Map<string, { label: string; color: string; counts: number[] }>();
		for (const [toolName, toolPts] of Object.entries(trendData.trend_by_item)) {
			const serverInfo = toolServerMap.get(toolName);
			if (!serverInfo) continue;
			const key = serverInfo.serverName;
			const color = serverInfo.color;
			if (!groupMap.has(key)) groupMap.set(key, { label: serverInfo.displayName, color, counts: new Array(dates.length).fill(0) });
			const ptMap = new Map(toolPts.map(p => [p.date, p.count]));
			const g = groupMap.get(key)!;
			dates.forEach((d, i) => { g.counts[i] += ptMap.get(d) ?? 0; });
		}

		const groups = [...groupMap.values()].sort((a, b) =>
			b.counts.reduce((s, v) => s + v, 0) - a.counts.reduce((s, v) => s + v, 0)
		);
		if (groups.length === 0) return null;

		const dailyTotals = dates.map((_, i) => groups.reduce((s, g) => s + g.counts[i], 0));
		const yMax = Math.max(...dailyTotals, 1);
		const xi = (i: number) => cX1 + (i / Math.max(dates.length - 1, 1)) * cW;
		const yv = (v: number) => cY2 - (v / yMax) * cH;

		const cumulative = new Array(dates.length).fill(0);
		const layers = groups.map((g, idx) => {
			const prevCum = [...cumulative];
			dates.forEach((_, i) => { cumulative[i] += g.counts[i]; });
			const topPts = dates.map((_, i) => ({ x: xi(i), y: yv(cumulative[i]) }));
			const botPts = idx === 0 ? null : dates.map((_, i) => ({ x: xi(i), y: yv(prevCum[i]) }));
			const { line, area } = stackedAreaPath(topPts, botPts, cY2);
			return { ...g, topPts, line, area, gradId: `mcpsg${idx}` };
		});

		const peakIdx = dailyTotals.reduce((mi, v, i) => v > dailyTotals[mi] ? i : mi, 0);
		const totalInv = dailyTotals.reduce((s, v) => s + v, 0);
		const xIdxs = dates.length <= 7 ? dates.map((_, i) => i)
			: [0, Math.floor(dates.length * 0.25), Math.floor(dates.length * 0.5), Math.floor(dates.length * 0.75), dates.length - 1];

		return {
			layers,
			groups,
			dates,
			dailyTotals,
			peakX: xi(peakIdx),
			peakY: yv(dailyTotals[peakIdx]),
			peakVal: dailyTotals[peakIdx],
			peakDate: new Date(dates[peakIdx] + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
			totalInv,
			avgPerDay: (totalInv / dates.length).toFixed(1),
			yMax,
			yTicks: [1, 0.67, 0.33, 0].map(f => ({ y: cY2 - f * cH, val: Math.round(yMax * f) })),
			xLabels: xIdxs.map(i => ({
				x: xi(i),
				label: new Date(dates[i] + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
				anchor: (i === 0 ? 'start' : i === dates.length - 1 ? 'end' : 'middle') as 'start' | 'end' | 'middle'
			})),
			xi,
			cX1, cX2, cY1, cY2
		};
	});

	// ── Chart tooltip state ───────────────────────────────────────────────────
	let chartHoverIdx = $state<number | null>(null);
	let chartSvgEl = $state<SVGSVGElement | null>(null);

	function handleChartMouseMove(e: MouseEvent) {
		if (!stackedChartData || !chartSvgEl) return;
		const rect = chartSvgEl.getBoundingClientRect();
		const scaleX = 900 / rect.width;
		const mx = (e.clientX - rect.left) * scaleX;
		const { dates, xi, cX1, cX2 } = stackedChartData;
		if (mx < cX1 - 10 || mx > cX2 + 10) { chartHoverIdx = null; return; }
		let best = 0, bestDist = Infinity;
		dates.forEach((_, i) => { const d = Math.abs(xi(i) - mx); if (d < bestDist) { bestDist = d; best = i; } });
		chartHoverIdx = best;
	}

	let tooltipData = $derived.by(() => {
		if (chartHoverIdx === null || !stackedChartData) return null;
		const i = chartHoverIdx;
		const date = new Date(stackedChartData.dates[i] + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
		const total = stackedChartData.dailyTotals[i];
		const rows = stackedChartData.layers
			.filter(l => l.counts[i] > 0)
			.map(l => ({ label: l.label, count: l.counts[i], color: l.color }))
			.sort((a, b) => b.count - a.count);
		return { date, total, rows, x: stackedChartData.xi(i) };
	});

	// ── Session reach (analytics left panel) ─────────────────────────────────
	let sessionReachServers = $derived(
		[...allServers].sort((a, b) => b.session_count - a.session_count).slice(0, 8)
	);
	let sessionReachMax = $derived(sessionReachServers.length > 0 ? sessionReachServers[0].session_count : 1);

	// ── Top by volume (analytics right panel) ────────────────────────────────
	let topByVolume = $derived(
		[...allServers].sort((a, b) => b.total_calls - a.total_calls).slice(0, 5)
	);
	let volumeMax = $derived(topByVolume.length > 0 ? topByVolume[0].total_calls : 1);

	// ── Insight banner ────────────────────────────────────────────────────────
	let topServer = $derived.by(() => {
		if (allServers.length === 0) return null;
		return [...allServers].sort((a, b) => b.total_calls - a.total_calls)[0];
	});

	let insightText = $derived.by(() => {
		if (!topServer) return null;
		const serverCount = data.overview.total_servers;
		const toolCount = data.overview.total_tools;
		return {
			bold: `${serverCount} server${serverCount !== 1 ? 's' : ''} · ${toolCount} tool${toolCount !== 1 ? 's' : ''}`,
			rest: ` · ${topServer.display_name} leads with ${topServer.total_calls.toLocaleString()} calls`
		};
	});

	// ── Accordion state ────────────────────────────────────────────────────────
	let coverageOpen = $state(false);

	let isPageLoading = $derived(!!$navigating && $navigating.to?.route.id === '/mcp');
</script>

{#if isPageLoading}
	<div class="-mx-6 -my-8 flex items-center justify-center" style="height: calc(100vh - 56px);">
		<div class="flex flex-col items-center gap-3">
			<div style="width: 28px; height: 28px; border: 2px solid var(--accent); border-top-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite;"></div>
			<span class="text-sm text-[var(--text-muted)]">Loading MCP tools…</span>
		</div>
	</div>
{:else}

<!-- ── Full-bleed split-view container ────────────────────────────────────── -->
<div
	class="-mx-6 -my-8 flex flex-col"
	style="{activeView === 'overview' ? 'height: calc(100vh - 56px); overflow: hidden;' : ''}"
>

	<!-- ── Page Header ──────────────────────────────────────────────────────── -->
	<div class="flex-shrink-0" style="padding: 0 24px; background: var(--bg-base);">
		<PageHeader
			title="MCP Tools"
			iconName="tools"
			iconColor="--nav-indigo"
			breadcrumbs={[{ label: 'Dashboard', href: '/' }, { label: 'MCP Tools' }]}
			subtitle="Which tools is Claude actually reaching for?"
		/>
	</div>

	<!-- ── Filter bar — always visible ─────────────────────────────────────── -->
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

		<!-- Right group: source chips + search -->
		<div class="flex items-center gap-2 flex-1">
			<div class="flex items-center gap-1.5">
				{#each ([['all', 'All'], ['builtin', 'Built-in'], ['plugin', 'Plugin'], ['standalone', 'Standalone']] as const) as [val, lbl]}
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
					aria-label="Search tools"
					placeholder="Search tools…"
					style="width: 180px; padding: 4px 10px 4px 26px; font-size: 12px; background: var(--bg-subtle); border: 1px solid var(--border); border-radius: 8px; color: var(--text-primary); outline: none;"
					data-search-input
				/>
			</div>
		</div>
	</div>

	{#if activeView === 'overview'}
	<!-- Split view -->
	<div class="flex flex-1 min-h-0 overflow-hidden" style="padding: 0 12px 12px; gap: 10px;">

		<!-- ── Left Panel: Server Coverage ────────────────────────────────────── -->
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
						Server Coverage
					</span>
					<div style="color: var(--text-faint); transition: transform 0.2s; transform: rotate({coverageOpen ? 90 : 0}deg);">
						<ChevronRight size={13} />
					</div>
				</div>
				<!-- Stats row: 3 columns -->
				<div class="flex items-center w-full">
					<div class="flex flex-col flex-1 items-center">
						<span style="font-size: 22px; font-weight: 700; font-family: 'JetBrains Mono', monospace; color: var(--text-primary); letter-spacing: -1px;">{data.overview.total_calls.toLocaleString()}</span>
						<span style="font-size: 9px; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.06em;">calls</span>
					</div>
					<div style="width: 1px; height: 32px; background: var(--border);"></div>
					<div class="flex flex-col flex-1 items-center">
						<span style="font-size: 22px; font-weight: 700; font-family: 'JetBrains Mono', monospace; color: var(--text-primary); letter-spacing: -1px;">{data.overview.total_servers}</span>
						<span style="font-size: 9px; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.06em;">servers</span>
					</div>
					<div style="width: 1px; height: 32px; background: var(--border);"></div>
					<div class="flex flex-col flex-1 items-center">
						<span style="font-size: 22px; font-weight: 700; font-family: 'JetBrains Mono', monospace; color: var(--text-primary); letter-spacing: -1px;">{data.overview.total_tools}</span>
						<span style="font-size: 9px; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.06em;">tools</span>
					</div>
				</div>
			</button>

			<!-- Server rows — only when accordion is open -->
			{#if coverageOpen}
			<div class="flex-1 overflow-y-auto">
				{#each leftPanelServers as server}
					{@const colors = getServerColorVars(server.name, server.plugin_name)}
					{@const pct = totalCalls > 0 ? Math.round((server.total_calls / totalCalls) * 100) : 0}
					{@const isSelected = selectedServer === server.name}
					{@const isTop = leftPanelServers[0]?.name === server.name}
					<div
						role="button"
						tabindex="0"
						onclick={() => selectedServer = isSelected ? null : server.name}
						onkeydown={(e) => e.key === 'Enter' && (selectedServer = isSelected ? null : server.name)}
						class="border-b cursor-pointer transition-colors"
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
								{server.display_name}
							</span>
							<div class="flex items-center gap-1.5 flex-shrink-0">
								{#if isTop}
									<TrendingUp size={10} style="color: var(--nav-orange);" />
								{/if}
								<span style="font-size: 12px; font-weight: 700; font-family: 'JetBrains Mono', monospace; color: {pct > 0 ? 'var(--text-secondary)' : 'var(--text-faint)'};">
									{pct}%
								</span>
							</div>
						</div>
						<!-- Bar + count -->
						<div class="flex items-center gap-2">
							<div class="flex-1" style="height: 3px; border-radius: 2px; background: var(--bg-muted); overflow: hidden;">
								{#if server.total_calls > 0}
									<div style="height: 100%; border-radius: 2px; width: {pct}%; background: {colors.color}; opacity: 0.7;"></div>
								{/if}
							</div>
							<span style="font-size: 10px; color: var(--text-faint); font-family: 'JetBrains Mono', monospace; flex-shrink: 0;">
								{server.total_calls.toLocaleString()}
							</span>
						</div>
					</div>
				{/each}
			</div>

			<!-- Footer -->
			<div class="flex-shrink-0 border-t flex items-center justify-between" style="padding: 10px 16px; border-color: var(--border-subtle);">
				<span style="font-size: 10px; color: var(--text-faint);">Sorted by calls</span>
				{#if selectedServer !== null}
					<button onclick={() => selectedServer = null} style="font-size: 10px; color: var(--accent); font-weight: 600;">
						Clear ×
					</button>
				{/if}
			</div>
			{/if}
		</div>

		<!-- ── Right Panel: Top Tools Leaderboard ──────────────────────────────── -->
		<div class="flex-1 flex flex-col overflow-hidden min-w-0" style="background: var(--bg-base); border: 1px solid var(--border); border-radius: 12px;">

			<!-- Panel header -->
			<div
				class="flex-shrink-0 flex items-center justify-between border-b"
				style="padding: 14px 16px 12px; background: var(--bg-base); border-color: var(--border);"
			>
				<div>
					<div style="font-size: 10px; font-weight: 700; color: var(--accent); text-transform: uppercase; letter-spacing: 0.12em; font-family: 'JetBrains Mono', monospace; margin-bottom: 3px;">Top Tools</div>
					<div style="font-size: 11px; color: var(--text-faint);">
						{#if selectedServer !== null}
							{@const srv = allServers.find(s => s.name === selectedServer)}
							{rightPanelTools.length} tools · {srv?.display_name ?? selectedServer}
						{:else}
							{rightPanelTools.length} tools ranked by usage
						{/if}
					</div>
				</div>
			</div>

			<!-- Table container -->
			<div class="flex-1 overflow-y-auto">
				{#if rightPanelTools.length === 0}
					<div class="flex flex-col items-center justify-center h-full gap-3">
						<Search size={36} style="color: var(--text-faint);" />
						<p style="font-size: 13px; color: var(--text-secondary); font-weight: 500;">No matching tools</p>
						<p style="font-size: 11px; color: var(--text-faint);">Try adjusting filters or search</p>
					</div>
				{:else}
					<!-- Column headers -->
					<div
						class="grid sticky top-0 border-b"
						style="background: var(--bg-base); border-color: var(--border); grid-template-columns: 32px 1fr 160px 100px 56px 64px; padding: 10px 12px 8px;"
					>
						<div style="font-size: 10px; color: var(--text-faint); letter-spacing: 0.06em; text-transform: uppercase; text-align: center;">#</div>
						<div style="font-size: 10px; color: var(--text-faint); letter-spacing: 0.06em; text-transform: uppercase;">Tool</div>
						<div style="font-size: 10px; color: var(--text-faint); letter-spacing: 0.06em; text-transform: uppercase;">Server</div>
						<div style="font-size: 10px; color: var(--text-faint); letter-spacing: 0.06em; text-transform: uppercase; padding: 0 8px;">Calls</div>
						<div style="font-size: 10px; color: var(--text-faint); letter-spacing: 0.06em; text-transform: uppercase; text-align: right;">Calls</div>
						<div style="font-size: 10px; color: var(--text-faint); letter-spacing: 0.06em; text-transform: uppercase; text-align: right;">Sessions</div>
					</div>

					<!-- Tool rows -->
					{#each rightPanelTools as { tool, server }, i (tool.full_name)}
						{@const colors = getServerColorVars(server.name, server.plugin_name)}
						{@const barWidth = Math.round((tool.calls / globalMax) * 100)}
						{@const useColor = selectedFilter === 'plugin' && server.source === 'plugin'}
						<a
							href="/mcp/{encodeURIComponent(server.name)}/{encodeURIComponent(tool.name)}"
							class="grid border-b transition-colors hover:bg-[var(--bg-subtle)] no-underline"
							style="grid-template-columns: 32px 1fr 160px 100px 56px 64px; padding: 8px 12px; border-color: var(--border-subtle); align-items: center;"
						>
							<div style="font-size: 11px; color: var(--text-faint); font-family: 'JetBrains Mono', monospace; text-align: center;">{i + 1}</div>
							<div class="min-w-0 pr-3">
								<span class="truncate block" style="font-size: 13px; font-weight: 600; color: var(--text-primary); font-family: 'JetBrains Mono', monospace;" title={tool.name}>{tool.name}</span>
							</div>
							<div class="min-w-0">
								{#if useColor}
									<span class="truncate block rounded" style="font-size: 10px; font-weight: 700; font-family: 'JetBrains Mono', monospace; padding: 2px 7px; color: var(--bg-base); background: {colors.color}; display: inline-block; max-width: 100%;" title={server.display_name}>{server.display_name.length > 14 ? server.display_name.slice(0, 13) + '…' : server.display_name}</span>
								{:else}
									<span class="truncate block" style="font-size: 11px; color: var(--text-secondary); font-family: 'JetBrains Mono', monospace;" title={server.display_name}>{server.display_name.length > 18 ? server.display_name.slice(0, 17) + '…' : server.display_name}</span>
								{/if}
							</div>
							<div style="padding: 0 8px;">
								<div style="background: var(--bg-muted); height: 4px; border-radius: 2px; overflow: hidden;">
									<div style="height: 100%; border-radius: 2px; width: {barWidth}%; background: {useColor ? colors.color : 'var(--accent)'}; opacity: 0.7;"></div>
								</div>
							</div>
							<div style="font-size: 13px; font-weight: 700; font-family: 'JetBrains Mono', monospace; text-align: right; color: {useColor ? colors.color : 'var(--text-primary)'};">{tool.calls}</div>
							<div style="font-size: 12px; color: var(--text-secondary); font-family: 'JetBrains Mono', monospace; text-align: right;">{tool.session_count}</div>
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
		<div class="rounded-lg" style="padding: 16px 18px; background: var(--bg-base); border: 1px solid var(--border);">
			<!-- Header -->
			<div class="flex items-start justify-between" style="margin-bottom: 12px;">
				<div>
					<div style="font-size: 10px; font-weight: 700; color: var(--accent); text-transform: uppercase; letter-spacing: 0.12em; font-family: 'JetBrains Mono', monospace; margin-bottom: 5px;">Tool Calls Over Time</div>
					{#if stackedChartData}
						<div class="flex items-center gap-4">
							<span style="font-size: 11px; color: var(--text-faint); font-family: 'JetBrains Mono', monospace;"><span style="font-weight: 700; color: var(--text-primary);">{stackedChartData.totalInv}</span> total</span>
							<span style="font-size: 11px; color: var(--text-faint); font-family: 'JetBrains Mono', monospace;"><span style="font-weight: 700; color: var(--text-primary);">{stackedChartData.avgPerDay}</span>/day avg</span>
							<span style="font-size: 11px; color: var(--text-faint); font-family: 'JetBrains Mono', monospace;">peak <span style="font-weight: 700; color: var(--text-primary);">{stackedChartData.peakVal}</span> on {stackedChartData.peakDate}</span>
						</div>
					{/if}
				</div>
				<div class="flex items-center gap-3">
					<!-- Legend -->
					{#if stackedChartData}
						<div class="flex items-center gap-2">
							{#each stackedChartData.groups.slice(0, 4) as g}
								<div class="flex items-center gap-1.5">
									<div style="width: 8px; height: 8px; border-radius: 2px; background: {g.color}; flex-shrink: 0;"></div>
									<span style="font-size: 10px; color: var(--text-faint);" class="truncate" title={g.label}>{g.label.length > 12 ? g.label.slice(0, 11) + '…' : g.label}</span>
								</div>
							{/each}
							{#if stackedChartData.groups.length > 4}
								<span style="font-size: 10px; color: var(--text-faint);">+{stackedChartData.groups.length - 4} more</span>
							{/if}
						</div>
					{/if}
					<!-- Range tabs -->
					<div class="flex overflow-hidden rounded" style="border: 1px solid var(--border);">
						{#each (['7d', '30d', '90d'] as const) as r}
							<button
								onclick={() => { trendRangeUserOverride = true; trendRange = r; }}
								style="padding: 4px 10px; font-size: 11px; font-weight: {trendRange === r ? '700' : '500'}; font-family: 'JetBrains Mono', monospace; background: {trendRange === r ? 'var(--accent-muted)' : 'var(--bg-subtle)'}; color: {trendRange === r ? 'var(--accent)' : 'var(--text-faint)'}; {r !== '90d' ? 'border-right: 1px solid var(--border);' : ''}"
							>{r}</button>
						{/each}
					</div>
				</div>
			</div>

			<!-- SVG stacked area chart -->
			{#if trendLoading && !trendData}
				<div style="height: 188px; display: flex; align-items: center; justify-content: center;">
					<div style="width: 18px; height: 18px; border: 2px solid var(--accent); border-top-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite;"></div>
				</div>
			{:else if !stackedChartData}
				<div style="height: 188px; display: flex; align-items: center; justify-content: center; color: var(--text-faint); font-size: 13px;">No data for this period</div>
			{:else}
				<div style="position: relative;">
					<svg
						bind:this={chartSvgEl}
						viewBox="0 0 900 188"
						style="width: 100%; height: 188px; display: block; overflow: visible; cursor: crosshair;"
						onmousemove={handleChartMouseMove}
						onmouseleave={() => chartHoverIdx = null}
					>
						<defs>
							{#each stackedChartData.layers as layer}
								<linearGradient id={layer.gradId} x1="0" y1="0" x2="0" y2="1">
									<stop offset="0%" stop-color={layer.color} stop-opacity="0.22" />
									<stop offset="100%" stop-color={layer.color} stop-opacity="0.03" />
								</linearGradient>
							{/each}
						</defs>

						<!-- Gridlines -->
						{#each stackedChartData.yTicks as tick}
							<line x1={stackedChartData.cX1} y1={tick.y} x2={stackedChartData.cX2} y2={tick.y} stroke="var(--border)" stroke-width="0.5" />
							<text x={stackedChartData.cX1 - 5} y={tick.y + 3} text-anchor="end" font-size="9" fill="var(--text-faint)" font-family="JetBrains Mono, monospace">{tick.val}</text>
						{/each}
						<line x1={stackedChartData.cX1} y1={stackedChartData.cY2} x2={stackedChartData.cX2} y2={stackedChartData.cY2} stroke="var(--border)" stroke-width="1" />

						<!-- Area fills -->
						{#each stackedChartData.layers as layer}
							<path d={layer.area} fill="url(#{layer.gradId})" />
						{/each}

						<!-- Top lines per layer -->
						{#each stackedChartData.layers as layer, i}
							<path d={layer.line} fill="none" stroke={layer.color}
								stroke-width={i === stackedChartData.layers.length - 1 ? 2 : 1.5}
								stroke-opacity={i === 0 ? 0.5 : 0.8}
								stroke-dasharray={i === 0 ? '3 3' : 'none'}
							/>
						{/each}

						<!-- Hover crosshair -->
						{#if chartHoverIdx !== null}
							{@const hx = stackedChartData.xi(chartHoverIdx)}
							<line x1={hx} y1={stackedChartData.cY1} x2={hx} y2={stackedChartData.cY2} stroke="var(--text-faint)" stroke-width="1" stroke-dasharray="3 2" opacity="0.6" />
							{#each stackedChartData.layers as layer}
								{@const cumY = layer.topPts?.[chartHoverIdx]?.y}
								{#if cumY !== undefined && layer.counts[chartHoverIdx] > 0}
									<circle cx={hx} cy={cumY} r="3.5" fill={layer.color} stroke="var(--bg-base)" stroke-width="1.5" />
								{/if}
							{/each}
						{/if}

						<!-- Peak annotation -->
						{#if chartHoverIdx !== stackedChartData.peakX}
							<circle cx={stackedChartData.peakX} cy={stackedChartData.peakY} r="4" fill="var(--accent)" stroke="var(--bg-base)" stroke-width="2" />
							<text x={stackedChartData.peakX} y={stackedChartData.peakY - 10} text-anchor="middle" font-size="10" fill="var(--accent)" font-family="JetBrains Mono, monospace" font-weight="bold">peak · {stackedChartData.peakVal}</text>
						{/if}

						<!-- X-axis labels -->
						{#each stackedChartData.xLabels as xl}
							<text x={xl.x} y="184" text-anchor={xl.anchor} font-size="9" fill="var(--text-faint)" font-family="JetBrains Mono, monospace">{xl.label}</text>
						{/each}
					</svg>

					<!-- Tooltip -->
					{#if tooltipData && chartHoverIdx !== null}
						{@const svgWidth = chartSvgEl?.getBoundingClientRect().width ?? 900}
						{@const tipX = (tooltipData.x / 900) * svgWidth}
						{@const flipLeft = tipX > svgWidth * 0.65}
						<div
							style="
								position: absolute;
								top: 0;
								left: {tipX}px;
								transform: translate({flipLeft ? 'calc(-100% - 10px)' : '10px'}, 4px);
								pointer-events: none;
								z-index: 20;
								background: var(--bg-base);
								border: 1px solid var(--border);
								border-radius: 8px;
								padding: 9px 12px;
								min-width: 150px;
								box-shadow: 0 4px 16px rgba(0,0,0,0.18);
							"
						>
							<div class="flex items-baseline justify-between gap-4" style="margin-bottom: 7px;">
								<span style="font-size: 11px; font-weight: 700; color: var(--text-primary); font-family: 'JetBrains Mono', monospace;">{tooltipData.date}</span>
								<span style="font-size: 11px; font-weight: 700; color: var(--accent); font-family: 'JetBrains Mono', monospace;">{tooltipData.total}</span>
							</div>
							{#if tooltipData.rows.length > 0}
								<div style="border-top: 1px solid var(--border-subtle); padding-top: 6px; display: flex; flex-direction: column; gap: 4px;">
									{#each tooltipData.rows as row}
										<div class="flex items-center justify-between gap-3">
											<div class="flex items-center gap-1.5 min-w-0">
												<div style="width: 7px; height: 7px; border-radius: 2px; background: {row.color}; flex-shrink: 0;"></div>
												<span class="truncate" style="font-size: 10px; color: var(--text-secondary); font-family: 'JetBrains Mono', monospace;" title={row.label}>{row.label.length > 16 ? row.label.slice(0, 15) + '…' : row.label}</span>
											</div>
											<span style="font-size: 10px; font-weight: 600; color: var(--text-primary); font-family: 'JetBrains Mono', monospace; flex-shrink: 0;">{row.count}</span>
										</div>
									{/each}
								</div>
							{:else}
								<div style="font-size: 10px; color: var(--text-faint); padding-top: 4px;">No activity</div>
							{/if}
						</div>
					{/if}
				</div>
			{/if}
		</div>

		<!-- Bottom row: Session Reach + Top by Volume -->
		<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px; align-items: start;">

			<!-- Session Reach panel -->
			<div class="rounded-lg" style="padding: 16px 18px; background: var(--bg-base); border: 1px solid var(--border);">
				<div style="font-size: 10px; font-weight: 700; color: var(--accent); text-transform: uppercase; letter-spacing: 0.12em; font-family: 'JetBrains Mono', monospace; margin-bottom: 2px;">Session Reach</div>
				<div style="font-size: 11px; color: var(--text-faint); margin-bottom: 14px;">which servers appear across most sessions</div>

				{#if sessionReachServers.length === 0}
					<div style="color: var(--text-faint); font-size: 12px; padding: 12px 0;">No data</div>
				{:else}
					<!-- Column headers -->
					<div style="display: grid; grid-template-columns: 1fr 80px 44px; gap: 8px; padding: 0 4px; margin-bottom: 6px;">
						<div style="font-size: 9px; color: var(--text-faint); letter-spacing: 0.1em; text-transform: uppercase;">Server</div>
						<div style="font-size: 9px; color: var(--text-faint); letter-spacing: 0.1em; text-transform: uppercase; text-align: center;">sessions</div>
						<div style="font-size: 9px; color: var(--text-faint); letter-spacing: 0.1em; text-transform: uppercase; text-align: right;">count</div>
					</div>
					<div style="border-top: 1px solid var(--border-subtle); padding-top: 4px;">
						{#each sessionReachServers as server}
							{@const colors = getServerColorVars(server.name, server.plugin_name)}
							{@const barPct = Math.round((server.session_count / sessionReachMax) * 100)}
							<a
								href="/mcp/{encodeURIComponent(server.name)}"
								class="no-underline"
								style="display: grid; grid-template-columns: 1fr 80px 44px; gap: 8px; align-items: center; padding: 5px 4px; border-radius: 4px; cursor: pointer;"
								onmouseenter={(e) => (e.currentTarget as HTMLElement).style.background = 'var(--bg-subtle)'}
								onmouseleave={(e) => (e.currentTarget as HTMLElement).style.background = 'transparent'}
							>
								<div class="flex items-center gap-1.5 min-w-0">
									<div style="width: 5px; height: 5px; border-radius: 50%; background: {colors.color}; flex-shrink: 0;"></div>
									<span class="truncate" style="font-size: 12px; font-weight: 600; color: var(--text-primary); font-family: 'JetBrains Mono', monospace;" title={server.display_name}>{server.display_name}</span>
								</div>
								<div style="background: var(--bg-muted); height: 5px; border-radius: 3px; overflow: hidden;">
									<div style="height: 100%; border-radius: 3px; width: {barPct}%; background: var(--accent);"></div>
								</div>
								<div style="font-size: 10px; font-weight: 700; color: var(--text-faint); text-align: right; font-family: 'JetBrains Mono', monospace;">{server.session_count}</div>
							</a>
						{/each}
					</div>
					<div style="margin-top: 10px; border-top: 1px solid var(--border-subtle); padding-top: 8px; font-size: 10px; color: var(--text-faint); line-height: 1.5;">
						Sessions count unique conversations that triggered each server's tools
					</div>
				{/if}
			</div>

			<!-- Top by Volume panel -->
			<div class="rounded-lg" style="padding: 16px 18px; background: var(--bg-base); border: 1px solid var(--border);">
				<div style="font-size: 10px; font-weight: 700; color: var(--accent); text-transform: uppercase; letter-spacing: 0.12em; font-family: 'JetBrains Mono', monospace; margin-bottom: 2px;">Top by Volume</div>
				<div style="font-size: 11px; color: var(--text-faint); margin-bottom: 14px;">across {data.overview.total_calls.toLocaleString()} total calls this period</div>

				{#if topByVolume.length === 0}
					<div style="color: var(--text-faint); font-size: 12px; padding: 12px 0;">No data</div>
				{:else}
					<!-- Column headers -->
					<div style="display: grid; grid-template-columns: 1fr 1fr 40px; gap: 10px; padding: 0 4px; margin-bottom: 6px;">
						<div style="font-size: 9px; color: var(--text-faint); letter-spacing: 0.1em; text-transform: uppercase;">Server</div>
						<div style="font-size: 9px; color: var(--text-faint); letter-spacing: 0.1em; text-transform: uppercase;">Call share</div>
						<div style="font-size: 9px; color: var(--text-faint); letter-spacing: 0.1em; text-transform: uppercase; text-align: right;">Calls</div>
					</div>

					{#each topByVolume as server}
						{@const colors = getServerColorVars(server.name, server.plugin_name)}
						{@const pct = totalCalls > 0 ? Math.round((server.total_calls / totalCalls) * 100) : 0}
						{@const barPct = Math.round((server.total_calls / volumeMax) * 100)}
						<a
							href="/mcp/{encodeURIComponent(server.name)}"
							class="no-underline"
							style="display: grid; grid-template-columns: 1fr 1fr 40px; gap: 10px; align-items: center; padding: 7px 4px; border-radius: 5px; cursor: pointer;"
							onmouseenter={(e) => (e.currentTarget as HTMLElement).style.background = 'color-mix(in oklch, var(--nav-indigo) 6%, transparent)'}
							onmouseleave={(e) => (e.currentTarget as HTMLElement).style.background = 'transparent'}
						>
							<div class="truncate" style="font-size: 12px; font-weight: 600; color: var(--text-primary); font-family: 'JetBrains Mono', monospace;" title={server.display_name}>{server.display_name}</div>
							<div style="background: color-mix(in oklch, var(--nav-indigo) 15%, transparent); height: 7px; border-radius: 4px; overflow: hidden;">
								<div style="background: {colors.color}; width: {barPct}%; height: 7px;"></div>
							</div>
							<div style="font-size: 12px; font-weight: 700; color: var(--text-primary); text-align: right; font-family: 'JetBrains Mono', monospace;">{server.total_calls.toLocaleString()}</div>
						</a>
					{/each}

					<div style="margin-top: 12px; border-top: 1px solid var(--border-subtle); padding-top: 8px; font-size: 10px; color: var(--text-faint); line-height: 1.6;">
						Main vs subagent calls distribution shown above
					</div>
				{/if}
			</div>

		</div>

	</div>

	{/if}

</div>

{/if}
