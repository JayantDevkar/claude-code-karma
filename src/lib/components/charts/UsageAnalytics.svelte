<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import {
		Chart,
		LineController,
		LineElement,
		PointElement,
		LinearScale,
		CategoryScale,
		Filler,
		Legend,
		Tooltip
	} from 'chart.js';
	import { TrendingUp, Clock, Calendar } from 'lucide-svelte';
	import { formatDistanceToNow } from 'date-fns';
	import type { UsageTrendResponse } from '$lib/api-types';
	import {
		registerChartDefaults,
		createResponsiveConfig,
		createCommonScaleConfig,
		chartColorPalette,
		getThemeColors
	} from './chartConfig';
	import SegmentedControl from '$lib/components/ui/SegmentedControl.svelte';
	import { API_BASE } from '$lib/config';

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
		/** Chart line color index from chartColorPalette */
		colorIndex?: number;
		/** Link prefix for item names (e.g. "/skills/" or "/agents/usage/") */
		itemLinkPrefix?: string;
		/** Custom link generator function — overrides itemLinkPrefix when provided */
		itemLinkFn?: (name: string) => string;
		/** Custom display name formatter for items */
		itemDisplayFn?: (name: string) => string;
	}

	let {
		endpoint,
		projectEncodedName,
		itemLabel = 'Items',
		colorIndex = 0,
		itemLinkPrefix,
		itemLinkFn,
		itemDisplayFn
	}: Props = $props();

	let data = $state<UsageTrendResponse | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);

	type RangeKey = '7d' | '30d' | '90d';
	let selectedRange = $state<RangeKey>('30d');

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

	// Derived computations
	let hasData = $derived(data !== null && data.total > 0);

	let topItems = $derived.by(() => {
		if (!data) return [];
		const entries = Object.entries(data.by_item)
			.sort(([, a], [, b]) => b - a)
			.slice(0, 8);
		const max = entries.length > 0 ? entries[0][1] : 1;
		return entries.map(([name, count]) => ({ name, count, pct: (count / max) * 100 }));
	});

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
		if (!data || data.trend.length === 0) return 0;
		const total = data.trend.reduce((sum, d) => sum + d.count, 0);
		return Math.round((total / data.trend.length) * 10) / 10;
	});

	// Chart
	let filteredTrend = $derived.by(() => {
		if (!data) return [];
		return [...data.trend].sort(
			(a, b) => new Date(a.date).getTime() - new Date(b.date).getTime()
		);
	});

	let trendLabels = $derived(
		filteredTrend.map((d) => {
			const date = new Date(d.date + 'T00:00:00');
			return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
		})
	);

	let trendData = $derived(filteredTrend.map((d) => d.count));

	let canvas: HTMLCanvasElement;
	let chart: Chart | null = null;
	const lineColor = chartColorPalette[colorIndex % chartColorPalette.length];

	function hexToRgba(hex: string, alpha: number): string {
		const r = parseInt(hex.slice(1, 3), 16);
		const g = parseInt(hex.slice(3, 5), 16);
		const b = parseInt(hex.slice(5, 7), 16);
		return `rgba(${r}, ${g}, ${b}, ${alpha})`;
	}

	function createChart() {
		if (!canvas || filteredTrend.length === 0) return;

		chart?.destroy();
		registerChartDefaults();
		const colors = getThemeColors();

		chart = new Chart(canvas, {
			type: 'line',
			data: {
				labels: trendLabels,
				datasets: [
					{
						label: itemLabel,
						data: trendData,
						borderColor: lineColor,
						backgroundColor: hexToRgba(lineColor, 0.15),
						fill: true,
						tension: 0.4,
						pointRadius: filteredTrend.length <= 14 ? 3 : 0,
						pointHoverRadius: 5,
						pointBackgroundColor: lineColor,
						pointBorderColor: colors.bgBase,
						pointBorderWidth: 2
					}
				]
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
						displayColors: true
					}
				},
				scales: createCommonScaleConfig()
			}
		});
	}

	onMount(() => {
		if (hasData) createChart();
	});

	onDestroy(() => {
		chart?.destroy();
	});

	// Rebuild chart when data changes
	$effect(() => {
		// eslint-disable-next-line @typescript-eslint/no-unused-expressions
		filteredTrend;

		if (canvas && filteredTrend.length > 0) {
			if (chart) {
				chart.data.labels = trendLabels;
				chart.data.datasets[0].data = trendData;
				const showPoints = filteredTrend.length <= 14;
				// eslint-disable-next-line @typescript-eslint/no-explicit-any
				(chart.data.datasets[0] as any).pointRadius = showPoints ? 3 : 0;
				chart.update();
			} else {
				createChart();
			}
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
			<p class="text-sm text-[var(--text-secondary)]">No usage data yet</p>
			<p class="text-xs text-[var(--text-muted)] mt-1">
				Usage analytics will appear once {itemLabel.toLowerCase()} are used in this project
			</p>
		</div>
	{:else if data}
		<!-- Stats row -->
		<div class="grid grid-cols-3 gap-4">
			<div class="bg-[var(--bg-subtle)] rounded-xl p-4">
				<div class="flex items-center gap-2 text-[var(--text-muted)] mb-2">
					<TrendingUp size={14} />
					<span class="text-xs font-medium">Total</span>
				</div>
				<p class="text-2xl font-bold text-[var(--text-primary)] tabular-nums">
					{data.total.toLocaleString()}
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
					<div class="flex items-center gap-3">
						<h4 class="text-sm font-medium text-[var(--text-primary)]">
							Activity Trend
						</h4>
						<span class="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
							<span
								class="inline-block w-2.5 h-2.5 rounded-sm"
								style="background-color: {lineColor};"
							></span>
							{itemLabel}
						</span>
					</div>
					<SegmentedControl options={rangeOptions} bind:value={selectedRange} size="sm" />
				</div>
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
					{#each topItems as { name, count, pct }, i}
						{@const displayName = itemDisplayFn ? itemDisplayFn(name) : name}
						<div>
							<div class="flex items-center justify-between text-sm mb-1">
								{#if itemLinkFn}
									<a
										href={itemLinkFn(name)}
										class="text-[var(--text-secondary)] hover:text-[var(--accent)] truncate flex-1 mr-2 text-xs font-medium"
									>
										{displayName}
									</a>
								{:else if itemLinkPrefix}
									<a
										href="{itemLinkPrefix}{encodeURIComponent(name)}"
										class="text-[var(--text-secondary)] hover:text-[var(--accent)] truncate flex-1 mr-2 text-xs font-medium"
									>
										{displayName}
									</a>
								{:else}
									<span
										class="text-[var(--text-secondary)] truncate flex-1 mr-2 text-xs font-medium"
									>
										{displayName}
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
									style="width: {pct}%; background-color: {lineColor}; opacity: {1 -
										i * 0.08};"
								></div>
							</div>
						</div>
					{/each}
				</div>
			</div>
		{/if}
	{/if}
</div>
