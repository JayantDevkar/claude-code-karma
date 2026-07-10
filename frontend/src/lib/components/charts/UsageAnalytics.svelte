<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import {
		Chart,
		type ChartDataset,
		LineController,
		LineElement,
		PointElement,
		LinearScale,
		CategoryScale,
		Filler,
		Legend,
		Tooltip
	} from 'chart.js';
	import { TrendingUp, Clock, Calendar, ChevronDown, ChevronUp } from 'lucide-svelte';
	import { formatDistanceToNow } from 'date-fns';
	import type { UsageTrendResponse } from '$lib/api-types';
	import {
		registerChartDefaults,
		createResponsiveConfig,
		createCommonScaleConfig,
		getThemeColors,
		onThemeChange
	} from './chartConfig';
	import SegmentedControl from '$lib/components/ui/SegmentedControl.svelte';
	import { API_BASE } from '$lib/config';
	import { getUserChartColor, getUserChartLabel } from '$lib/utils';

	Chart.register(
		LineController,
		LineElement,
		PointElement,
		LinearScale,
		CategoryScale,
		Filler,
		Legend,
		Tooltip
	);

	interface Props {
		/** API endpoint path, e.g. "/skills/usage/trend" or "/agents/usage/trend" */
		endpoint: string;
		/** Optional project filter */
		projectEncodedName?: string;
		/** Label for items (e.g. "Skills" or "Agents") */
		itemLabel?: string;
		/** Function that returns a hex color for an item name (for Chart.js canvas) */
		colorFn?: (itemName: string) => string;
		/** Link prefix for item names (e.g. "/skills/" or "/agents/usage/") */
		itemLinkPrefix?: string;
		/** Custom link generator function — overrides itemLinkPrefix when provided */
		itemLinkFn?: (name: string) => string;
		/** Custom display name formatter for items */
		itemDisplayFn?: (name: string) => string;
		/** Optional filter to exclude items (return true to exclude) */
		excludeItemFn?: (name: string) => boolean;
	}

	const OTHERS_COLOR = '#9ca3af'; // gray-400

	let {
		endpoint,
		projectEncodedName,
		itemLabel = 'Items',
		colorFn = () => '#7c3aed',
		itemLinkPrefix,
		itemLinkFn,
		itemDisplayFn,
		excludeItemFn
	}: Props = $props();

	let data = $state<UsageTrendResponse | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let expanded = $state(false);

	type RangeKey = '7d' | '30d' | '90d';
	let selectedRange = $state<RangeKey>('30d');

	type ViewMode = 'by-item' | 'by-user';
	let viewMode = $state<ViewMode>('by-item');

	const rangeOptions = [
		{ label: '7d', value: '7d' },
		{ label: '30d', value: '30d' },
		{ label: '90d', value: '90d' }
	];

	const periodMap: Record<RangeKey, string> = {
		'7d': 'week',
		'30d': 'month',
		'90d': 'quarter'
	};

	async function fetchTrend(range: RangeKey) {
		loading = true;
		error = null;
		try {
			const url = new URL(`${API_BASE}${endpoint}`);
			url.searchParams.set('period', periodMap[range]);
			if (projectEncodedName) url.searchParams.set('project', projectEncodedName);

			const res = await fetch(url);
			if (!res.ok) throw new Error('Failed to fetch usage trend');
			data = await res.json();
		} catch (e: any) {
			error = e.message;
			console.warn(`Failed to fetch ${endpoint}:`, e.message);
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		fetchTrend(selectedRange);
	});

	// Derived computations — filter items through excludeItemFn
	let filteredByItem = $derived.by(() => {
		if (!data) return {};
		if (!excludeItemFn) return data.by_item;
		return Object.fromEntries(
			Object.entries(data.by_item).filter(([name]) => !excludeItemFn(name))
		);
	});

	let filteredTotal = $derived(
		Object.values(filteredByItem).reduce((sum, count) => sum + count, 0)
	);

	let hasData = $derived(data !== null && filteredTotal > 0);

	let hasUserData = $derived(
		data !== null &&
		data.trend_by_user !== undefined &&
		Object.keys(data.trend_by_user).length > 1
	);

	const DEFAULT_VISIBLE = 5;
	const EXPANDED_VISIBLE = 10;

	let visibleCount = $derived(expanded ? EXPANDED_VISIBLE : DEFAULT_VISIBLE);

	// Shared sorted top-N item names — consumed by topItems, legendItems, and chartDatasets
	let topItemNames = $derived(
		Object.entries(filteredByItem)
			.sort(([, a], [, b]) => b - a)
			.slice(0, visibleCount)
			.map(([name]) => name)
	);

	let topItems = $derived.by(() => {
		const max = topItemNames.length > 0 ? filteredByItem[topItemNames[0]] : 1;
		return topItemNames.map((name) => {
			const count = filteredByItem[name];
			return {
				name,
				count,
				pct: (count / max) * 100,
				color: colorFn(name)
			};
		});
	});

	let hasMoreItems = $derived(
		Object.keys(filteredByItem).length > DEFAULT_VISIBLE
	);

	let lastActiveLabel = $derived.by(() => {
		if (!data?.last_used) return null;
		try {
			return formatDistanceToNow(new Date(data.last_used)) + ' ago';
		} catch {
			return null;
		}
	});

	let firstUsedLabel = $derived.by(() => {
		if (!data?.first_used) return null;
		try {
			const d = new Date(data.first_used);
			return d.toLocaleDateString('en-US', {
				month: 'short',
				day: 'numeric',
				year: 'numeric'
			});
		} catch {
			return null;
		}
	});

	let avgPerDay = $derived.by(() => {
		if (!filteredTrend.length) return 0;
		return Math.round((filteredTotal / filteredTrend.length) * 10) / 10;
	});

	// Filter trend_by_item through excludeItemFn
	let filteredTrendByItem = $derived.by(() => {
		if (!data?.trend_by_item) return {};
		if (!excludeItemFn) return data.trend_by_item;
		return Object.fromEntries(
			Object.entries(data.trend_by_item).filter(([name]) => !excludeItemFn(name))
		);
	});

	// Chart data — recompute aggregate trend from filtered items when excluding
	let filteredTrend = $derived.by(() => {
		if (!data) return [];
		const sorted = [...data.trend].sort(
			(a, b) => new Date(a.date).getTime() - new Date(b.date).getTime()
		);
		if (!excludeItemFn || !data.trend_by_item) return sorted;

		// Rebuild daily totals from only filtered items
		const dailyTotals = new Map<string, number>();
		for (const points of Object.values(filteredTrendByItem)) {
			for (const p of points) {
				dailyTotals.set(p.date, (dailyTotals.get(p.date) ?? 0) + p.count);
			}
		}
		return sorted.map((d) => ({ date: d.date, count: dailyTotals.get(d.date) ?? 0 }));
	});

	let trendLabels = $derived(
		filteredTrend.map((d) => {
			const date = new Date(d.date + 'T00:00:00');
			return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
		})
	);

	function hexToRgba(hex: string, alpha: number): string {
		const r = parseInt(hex.slice(1, 3), 16);
		const g = parseInt(hex.slice(3, 5), 16);
		const b = parseInt(hex.slice(5, 7), 16);
		return `rgba(${r}, ${g}, ${b}, ${alpha})`;
	}

	// Build chart datasets from trend_by_item
	let chartDatasets = $derived.by(() => {
		if (!data || !filteredTrend.length) return [];

		const trendByItem = filteredTrendByItem;
		const dateLabels = filteredTrend.map((d) => d.date);
		const showPoints = filteredTrend.length <= 14;

		// Pre-build date maps once — shared by per-item lines and Others computation
		const dateMaps = new Map(
			topItemNames.map((name) => {
				const points = trendByItem[name] ?? [];
				return [name, new Map(points.map((t: { date: string; count: number }) => [t.date, t.count]))] as const;
			})
		);

		const datasets: ChartDataset<'line'>[] = [];

		// Per-item lines
		for (const itemName of topItemNames) {
			const dateMap = dateMaps.get(itemName)!;
			const itemData = dateLabels.map((d) => dateMap.get(d) ?? 0);
			const hex = colorFn(itemName);

			datasets.push({
				label: itemDisplayFn ? itemDisplayFn(itemName) : itemName,
				data: itemData,
				borderColor: hex,
				backgroundColor: hexToRgba(hex, 0.08),
				fill: false,
				tension: 0.4,
				pointRadius: showPoints ? 2.5 : 0,
				pointHoverRadius: 4,
				pointBackgroundColor: hex,
				borderWidth: 2
			});
		}

		// "Others" line: aggregate trend minus top items
		if (Object.keys(filteredByItem).length > visibleCount) {
			const topTotals = dateLabels.map((date) =>
				topItemNames.reduce((s, n) => s + (dateMaps.get(n)!.get(date) ?? 0), 0)
			);
			const othersData = filteredTrend.map((d, i) => Math.max(0, d.count - topTotals[i]));
			const hasOthers = othersData.some((v) => v > 0);

			if (hasOthers) {
				datasets.push({
					label: 'Others',
					data: othersData,
					borderColor: OTHERS_COLOR,
					backgroundColor: hexToRgba(OTHERS_COLOR, 0.05),
					fill: false,
					tension: 0.4,
					pointRadius: 0,
					pointHoverRadius: 3,
					pointBackgroundColor: OTHERS_COLOR,
					borderWidth: 1.5,
					segment: { borderDash: () => [4, 3] }
				});
			}
		}

		return datasets;
	});

	// Per-user chart datasets
	let userChartDatasets = $derived.by(() => {
		if (!data?.trend_by_user || !filteredTrend.length) return [];

		const trendByUser = data.trend_by_user;
		const dateLabels = filteredTrend.map(d => d.date);
		const showPoints = filteredTrend.length <= 14;

		// Sort users: _local first, then remotes alphabetically
		const userIds = Object.keys(trendByUser);
		const sorted = userIds.filter(id => id !== '_local').sort();
		if (userIds.includes('_local')) sorted.unshift('_local');

		const datasets: ChartDataset<'line'>[] = [];

		for (const userId of sorted) {
			const points = trendByUser[userId] ?? [];
			const dateMap = new Map(points.map(p => [p.date, p.count]));
			const userData = dateLabels.map(d => dateMap.get(d) ?? 0);
			const hex = getUserChartColor(userId);
			const isLocal = userId === '_local';

			datasets.push({
				label: getUserChartLabel(userId, data.user_names),
				data: userData,
				borderColor: hex,
				backgroundColor: hexToRgba(hex, isLocal ? 0.08 : 0.03),
				fill: isLocal,
				tension: 0.4,
				pointRadius: showPoints ? 2.5 : 0,
				pointHoverRadius: 4,
				pointBackgroundColor: hex,
				borderWidth: isLocal ? 2 : 1.5
			});
		}

		return datasets;
	});

	// Per-user top items (sorted by total usage)
	let userTopItems = $derived.by(() => {
		if (!data?.trend_by_user) return [];
		const trendByUser = data.trend_by_user;
		const userIds = Object.keys(trendByUser);
		const sorted = userIds.filter(id => id !== '_local').sort();
		if (userIds.includes('_local')) sorted.unshift('_local');

		const items = sorted.map(userId => {
			const total = (trendByUser[userId] ?? []).reduce((sum, p) => sum + p.count, 0);
			return { name: userId, count: total };
		});

		const max = items.length > 0 ? Math.max(...items.map(i => i.count), 1) : 1;
		return items.map(item => ({
			name: getUserChartLabel(item.name, data?.user_names),
			count: item.count,
			pct: (item.count / max) * 100,
			color: getUserChartColor(item.name)
		}));
	});

	// Per-user legend items
	let userLegendItems = $derived.by(() => {
		if (!data?.trend_by_user) return [];
		const userIds = Object.keys(data.trend_by_user);
		const sorted = userIds.filter(id => id !== '_local').sort();
		if (userIds.includes('_local')) sorted.unshift('_local');
		return sorted.map(userId => ({
			name: getUserChartLabel(userId, data?.user_names),
			color: getUserChartColor(userId)
		}));
	});

	// Legend items for the mini legend — derived from shared topItemNames
	let legendItems = $derived.by(() => {
		if (!data) return [];
		const items = topItemNames.map((name) => ({
			name: itemDisplayFn ? itemDisplayFn(name) : name,
			color: colorFn(name)
		}));

		if (Object.keys(filteredByItem).length > visibleCount) {
			items.push({ name: 'Others', color: OTHERS_COLOR });
		}
		return items;
	});

	let canvas = $state<HTMLCanvasElement>();
	let chart: Chart | null = null;

	function createChart() {
		const activeDatasets = viewMode === 'by-user' ? userChartDatasets : chartDatasets;
		if (!canvas || filteredTrend.length === 0 || activeDatasets.length === 0) return;

		chart?.destroy();
		registerChartDefaults();
		const colors = getThemeColors();

		chart = new Chart(canvas, {
			type: 'line',
			data: {
				labels: trendLabels,
				datasets: activeDatasets
			},
			options: {
				...createResponsiveConfig(),
				interaction: {
					mode: 'index',
					intersect: false
				},
				plugins: {
					...createResponsiveConfig().plugins,
					legend: { display: false },
					tooltip: {
						...createResponsiveConfig().plugins.tooltip,
						backgroundColor: colors.bgBase,
						titleColor: colors.text,
						bodyColor: colors.textSecondary,
						borderColor: colors.border,
						borderWidth: 1,
						displayColors: true,
						filter: (item) => item.raw !== 0
					}
				},
				scales: createCommonScaleConfig()
			}
		});
	}

	let cleanupTheme: (() => void) | null = null;

	onMount(() => {
		if (hasData) createChart();
		cleanupTheme = onThemeChange(() => createChart());
	});

	onDestroy(() => {
		cleanupTheme?.();
		chart?.destroy();
	});

	// Rebuild chart when datasets, filter, or view mode changes
	$effect(() => {
		const activeDatasets = viewMode === 'by-user' ? userChartDatasets : chartDatasets;
		const hasDatasets = activeDatasets.length > 0;

		if (canvas && hasDatasets) {
			if (chart) {
				chart.data.labels = trendLabels;
				chart.data.datasets = activeDatasets;
				chart.update();
			} else {
				createChart();
			}
		} else if (chart) {
			chart.destroy();
			chart = null;
		}
	});
</script>

<div class="space-y-5">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<h3 class="text-sm font-semibold text-[var(--text-primary)]">
			{itemLabel} Usage Analytics
		</h3>
		{#if firstUsedLabel}
			<span class="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
				<Calendar size={12} />
				Since {firstUsedLabel}
			</span>
		{/if}
	</div>

	<!-- Range selector — always visible so users can switch ranges even when current range has no data -->
	{#if !loading || data}
		<div class="flex justify-end gap-2">
			<SegmentedControl options={rangeOptions} bind:value={selectedRange} size="sm" />
		</div>
	{/if}

	{#if loading && !data}
		<div class="flex items-center justify-center py-12">
			<div
				class="w-6 h-6 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin"
			></div>
		</div>
	{:else if !hasData}
		<div
			class="text-center py-10 bg-[var(--bg-subtle)] rounded-xl border border-dashed border-[var(--border)]"
		>
			<TrendingUp size={28} class="mx-auto text-[var(--text-muted)] mb-2" />
			<p class="text-sm text-[var(--text-secondary)]">No usage data for this period</p>
			<p class="text-xs text-[var(--text-muted)] mt-1">
				Try a different time range, or usage will appear once {itemLabel.toLowerCase()} are used
			</p>
		</div>
	{:else if data}
		<!-- Stats row -->
		<div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
			<div class="bg-[var(--bg-subtle)] rounded-xl p-4">
				<div class="flex items-center gap-2 text-[var(--text-muted)] mb-2">
					<TrendingUp size={14} />
					<span class="text-xs font-medium">Total</span>
				</div>
				<p class="text-2xl font-bold text-[var(--text-primary)] tabular-nums">
					{filteredTotal.toLocaleString()}
				</p>
			</div>

			<div class="bg-[var(--bg-subtle)] rounded-xl p-4">
				<div class="flex items-center gap-2 text-[var(--text-muted)] mb-2">
					<TrendingUp size={14} />
					<span class="text-xs font-medium">Avg / Day</span>
				</div>
				<p class="text-2xl font-bold text-[var(--text-primary)] tabular-nums">
					{avgPerDay}
				</p>
			</div>

			<div class="bg-[var(--bg-subtle)] rounded-xl p-4">
				<div class="flex items-center gap-2 text-[var(--text-muted)] mb-2">
					<Clock size={14} />
					<span class="text-xs font-medium">Last Active</span>
				</div>
				<p
					class="text-[var(--text-primary)] font-bold tabular-nums"
					class:text-2xl={!lastActiveLabel || lastActiveLabel.length <= 10}
					class:text-base={lastActiveLabel && lastActiveLabel.length > 10}
				>
					{lastActiveLabel || '--'}
				</p>
			</div>
		</div>

		<!-- Trend chart -->
		{#if data.trend.length > 0}
			<div class="bg-[var(--bg-subtle)] rounded-xl p-4">
				<div class="flex items-center justify-between mb-4">
					<h4 class="text-sm font-medium text-[var(--text-primary)]">
						Activity Trend
					</h4>
					{#if hasUserData}
						<label class="flex items-center gap-2 cursor-pointer select-none">
							<span class="text-xs text-[var(--text-muted)]">By user</span>
							<button
								type="button"
								role="switch"
								aria-checked={viewMode === 'by-user'}
								aria-label="Toggle per-user view"
								onclick={() => (viewMode = viewMode === 'by-user' ? 'by-item' : 'by-user')}
								class="relative inline-flex h-5 w-9 items-center rounded-full transition-colors duration-200
									{viewMode === 'by-user' ? 'bg-[var(--accent)]' : 'bg-[var(--bg-muted)] border border-[var(--border)]'}"
							>
								<span
									class="inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform duration-200
										{viewMode === 'by-user' ? 'translate-x-[18px]' : 'translate-x-[3px]'}"
								></span>
							</button>
						</label>
					{/if}
				</div>
				<!-- Mini legend -->
				{#if legendItems.length > 0}
					<div class="flex flex-wrap gap-x-4 gap-y-1 mb-3">
						{#each viewMode === 'by-user' ? userLegendItems : legendItems as item}
							<span class="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
								<span
									class="inline-block w-2 h-2 rounded-full flex-shrink-0"
									style="background-color: {item.color};"
								></span>
								<span class="truncate max-w-[120px]">{item.name}</span>
							</span>
						{/each}
					</div>
				{/if}
				<div class="h-[200px]">
					<canvas bind:this={canvas}></canvas>
				</div>
			</div>
		{/if}

		<!-- Top items bar chart -->
		{#if topItems.length > 0}
			<div class="bg-[var(--bg-subtle)] rounded-xl p-4">
				<h4 class="text-sm font-medium text-[var(--text-primary)] mb-4">
					Top {itemLabel}
				</h4>
				<div class="space-y-3">
					{#each viewMode === 'by-user' ? userTopItems : topItems as { name, count, pct, color }, i}
						{@const displayName = viewMode === 'by-user' ? name : itemDisplayFn ? itemDisplayFn(name) : name}
						{@const href = viewMode === 'by-user' ? null : itemLinkFn ? itemLinkFn(name) : itemLinkPrefix ? `${itemLinkPrefix}${encodeURIComponent(name)}` : null}
						<div>
							<div class="flex items-center justify-between text-sm mb-1">
								{#snippet dotLabel()}
									<span
										class="inline-block w-2 h-2 rounded-full mr-1.5 align-middle flex-shrink-0"
										style="background-color: {color};"
									></span>
									{displayName}
								{/snippet}
								{#if href}
									<a
										{href}
										class="text-[var(--text-secondary)] hover:text-[var(--accent)] truncate flex-1 mr-2 text-xs font-medium"
									>
										{@render dotLabel()}
									</a>
								{:else}
									<span
										class="text-[var(--text-secondary)] truncate flex-1 mr-2 text-xs font-medium"
									>
										{@render dotLabel()}
									</span>
								{/if}
								<span
									class="text-[var(--text-muted)] tabular-nums text-xs flex-shrink-0"
									>{count.toLocaleString()}</span
								>
							</div>
							<div class="h-1.5 bg-[var(--bg-muted)] rounded-full overflow-hidden">
								<div
									class="h-full rounded-full transition-all duration-500 ease-out"
									style="width: {pct}%; background-color: {color};"
								></div>
							</div>
						</div>
					{/each}
				</div>

				<!-- Show More / Show Less toggle -->
				{#if hasMoreItems}
					<button
						onclick={() => (expanded = !expanded)}
						class="flex items-center gap-1 mt-4 mx-auto text-xs text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors"
					>
						{#if expanded}
							<ChevronUp size={14} />
							Show less
						{:else}
							<ChevronDown size={14} />
							Show more
						{/if}
					</button>
				{/if}
			</div>
		{/if}
	{/if}
</div>
