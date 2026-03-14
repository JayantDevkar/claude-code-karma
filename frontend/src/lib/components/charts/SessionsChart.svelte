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
	import {
		registerChartDefaults,
		createResponsiveConfig,
		createCommonScaleConfig,
		chartColorPalette,
		getThemeColors,
		onThemeChange
	} from './chartConfig';
	import { getUserChartColor, getUserChartLabel } from '$lib/utils';

	// Register Chart.js components
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

	// Shared date utilities (used by buildChartData and multi-user paths)
	function getLocalDateKey(d: Date): string {
		const year = d.getFullYear();
		const month = String(d.getMonth() + 1).padStart(2, '0');
		const day = String(d.getDate()).padStart(2, '0');
		return `${year}-${month}-${day}`;
	}

	function formatLocalDate(dateKey: string): string {
		const [year, month, day] = dateKey.split('-').map(Number);
		const date = new Date(year, month - 1, day);
		return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
	}

	/** Fill all dates between min and max (with single-day padding) */
	function fillDateRange(dateKeys: string[]): string[] {
		if (dateKeys.length === 0) return [];

		const minDateKey = dateKeys[0];
		const maxDateKey = dateKeys[dateKeys.length - 1];
		const isSingleDay = minDateKey === maxDateKey;
		const result: string[] = [];

		if (isSingleDay) {
			const [y, m, d] = minDateKey.split('-').map(Number);
			result.push(getLocalDateKey(new Date(y, m - 1, d - 1)));
		}

		const [minY, minM, minD] = minDateKey.split('-').map(Number);
		const [maxY, maxM, maxD] = maxDateKey.split('-').map(Number);
		let cur = new Date(minY, minM - 1, minD);
		const end = new Date(maxY, maxM - 1, maxD);
		while (cur <= end) {
			result.push(getLocalDateKey(cur));
			cur = new Date(cur.getTime() + 86400000);
		}

		if (isSingleDay) {
			const [y, m, d] = maxDateKey.split('-').map(Number);
			result.push(getLocalDateKey(new Date(y, m - 1, d + 1)));
		}

		return result;
	}

	interface Props {
		sessionsByDate: Record<string, number>;
		sessionsByDateByUser?: Record<string, Record<string, number>>;
		userNames?: Record<string, string>;
		class?: string;
	}

	let { sessionsByDate, sessionsByDateByUser, userNames, class: className = '' }: Props = $props();

	let hasMultiUser = $derived(
		!!sessionsByDateByUser && Object.keys(sessionsByDateByUser).length > 1
	);

	let canvas: HTMLCanvasElement;
	let chart: Chart | null = null;

	// Build chart data from sessions_by_date dict (YYYY-MM-DD → count)
	function buildChartData(byDate: Record<string, number>): {
		labels: string[];
		data: number[];
		dateRange: string;
	} {
		const dateKeys = Object.keys(byDate).filter((k) => byDate[k] != null).sort();

		if (dateKeys.length === 0) {
			return { labels: [], data: [], dateRange: '' };
		}

		const formatLocalDateFull = (dateKey: string): string => {
			const [year, month, day] = dateKey.split('-').map(Number);
			const date = new Date(year, month - 1, day);
			return date.toLocaleDateString('en-US', {
				month: 'short',
				day: 'numeric',
				year: 'numeric'
			});
		};

		const allDates = fillDateRange(dateKeys);
		const labels = allDates.map(formatLocalDate);
		const data = allDates.map((d) => byDate[d] || 0);

		const minDateKey = dateKeys[0];
		const maxDateKey = dateKeys[dateKeys.length - 1];
		const isSingleDay = minDateKey === maxDateKey;

		const dateRange = isSingleDay
			? formatLocalDateFull(minDateKey)
			: `${formatLocalDateFull(minDateKey)} - ${formatLocalDateFull(maxDateKey)}`;

		return { labels, data, dateRange };
	}

	// Compute derived values for template
	let chartData = $derived(buildChartData(sessionsByDate));

	function createSessionChart() {
		chart?.destroy();
		chart = null;
		if (!canvas) return;

		registerChartDefaults();
		const { labels, data } = chartData;
		const colors = getThemeColors();

		if (hasMultiUser) {
			const userIds = Object.keys(sessionsByDateByUser!);
			const sorted = userIds.filter((id) => id !== '_local').sort();
			if (userIds.includes('_local')) sorted.unshift('_local');

			const dateKeys = Object.keys(sessionsByDate)
				.filter((k) => sessionsByDate[k] != null)
				.sort();
			const allDates = fillDateRange(dateKeys);
			const multiLabels = allDates.map(formatLocalDate);

			const datasets = sorted.map((userId) => {
				const isLocal = userId === '_local';
				const hex = getUserChartColor(userId);
				const userData = sessionsByDateByUser![userId] ?? {};
				return {
					label: getUserChartLabel(userId, userNames),
					data: allDates.map((d) => userData[d] ?? 0),
					borderColor: hex,
					backgroundColor: isLocal ? 'rgba(124, 58, 237, 0.1)' : 'transparent',
					fill: isLocal,
					tension: 0.4,
					pointRadius: 3,
					pointBackgroundColor: hex,
					pointBorderColor: colors.bgBase,
					pointBorderWidth: 2,
					borderWidth: isLocal ? 2 : 1.5
				};
			});

			chart = new Chart(canvas, {
				type: 'line',
				data: { labels: multiLabels, datasets },
				options: {
					...createResponsiveConfig(),
					plugins: {
						...createResponsiveConfig().plugins,
						legend: {
							display: true,
							position: 'top',
							align: 'end',
							labels: {
								boxWidth: 8,
								boxHeight: 8,
								usePointStyle: true,
								pointStyle: 'circle',
								font: { size: 10 },
								padding: 12
							}
						},
						tooltip: {
							...createResponsiveConfig().plugins.tooltip,
							backgroundColor: colors.bgBase,
							titleColor: colors.text,
							bodyColor: colors.textSecondary,
							borderColor: colors.border,
							borderWidth: 1,
							mode: 'index',
							intersect: false
						}
					},
					scales: createCommonScaleConfig()
				}
			});
		} else {
			chart = new Chart(canvas, {
				type: 'line',
				data: {
					labels,
					datasets: [
						{
							label: 'Sessions',
							data,
							borderColor: chartColorPalette[0],
							backgroundColor: 'rgba(124, 58, 237, 0.1)',
							fill: true,
							tension: 0.4,
							pointRadius: 4,
							pointBackgroundColor: chartColorPalette[0],
							pointBorderColor: colors.bgBase,
							pointBorderWidth: 2
						}
					]
				},
				options: {
					...createResponsiveConfig(),
					plugins: {
						...createResponsiveConfig().plugins,
						legend: { display: false },
						tooltip: {
							...createResponsiveConfig().plugins.tooltip,
							backgroundColor: colors.bgBase,
							titleColor: colors.text,
							bodyColor: colors.textSecondary,
							borderColor: colors.border,
							borderWidth: 1
						}
					},
					scales: createCommonScaleConfig()
				}
			});
		}
	}

	let cleanupTheme: (() => void) | null = null;

	onMount(() => {
		createSessionChart();
		cleanupTheme = onThemeChange(() => createSessionChart());
	});

	onDestroy(() => {
		cleanupTheme?.();
		chart?.destroy();
	});

	// Update chart when data changes
	$effect(() => {
		if (chart && sessionsByDate) {
			const { labels, data } = chartData;
			chart.data.labels = labels;

			if (hasMultiUser && sessionsByDateByUser) {
				const dateKeys = Object.keys(sessionsByDate)
					.filter((k) => sessionsByDate[k] != null)
					.sort();
				const allDates = fillDateRange(dateKeys);
				chart.data.labels = allDates.map(formatLocalDate);

				const userIds = Object.keys(sessionsByDateByUser);
				const sorted = userIds.filter((id) => id !== '_local').sort();
				if (userIds.includes('_local')) sorted.unshift('_local');

				sorted.forEach((userId, i) => {
					if (chart!.data.datasets[i]) {
						const userData = sessionsByDateByUser[userId] ?? {};
						chart!.data.datasets[i].data = allDates.map((d) => userData[d] ?? 0);
					}
				});
			} else {
				chart.data.datasets[0].data = data;
			}
			chart.update();
		}
	});
</script>

<div
	class="
		rounded-lg border border-[var(--border)]
		bg-[var(--bg-subtle)]
		p-4
		{className}
	"
>
	<div class="flex items-center justify-between mb-4">
		<h3 class="text-sm font-medium text-[var(--text-primary)]">Sessions Over Time</h3>
		{#if chartData.dateRange}
			<span class="text-xs text-[var(--text-muted)]">{chartData.dateRange}</span>
		{/if}
	</div>
	<div class="h-[200px]">
		<canvas bind:this={canvas}></canvas>
	</div>
</div>
