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
		getThemeColors
	} from './chartConfig';

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

	interface Props {
		sessionsByDate: Record<string, number>;
		class?: string;
	}

	let { sessionsByDate, class: className = '' }: Props = $props();

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

		const formatLocalDate = (dateKey: string): string => {
			const [year, month, day] = dateKey.split('-').map(Number);
			const date = new Date(year, month - 1, day);
			return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
		};

		const formatLocalDateFull = (dateKey: string): string => {
			const [year, month, day] = dateKey.split('-').map(Number);
			const date = new Date(year, month - 1, day);
			return date.toLocaleDateString('en-US', {
				month: 'short',
				day: 'numeric',
				year: 'numeric'
			});
		};

		const getLocalDateKey = (d: Date): string => {
			const year = d.getFullYear();
			const month = String(d.getMonth() + 1).padStart(2, '0');
			const day = String(d.getDate()).padStart(2, '0');
			return `${year}-${month}-${day}`;
		};

		const minDateKey = dateKeys[0];
		const maxDateKey = dateKeys[dateKeys.length - 1];
		const isSingleDay = minDateKey === maxDateKey;

		const labels: string[] = [];
		const data: number[] = [];

		// For single day, add padding day before to center the point
		if (isSingleDay) {
			const [year, month, day] = minDateKey.split('-').map(Number);
			const prevDate = new Date(year, month - 1, day - 1);
			labels.push(formatLocalDate(getLocalDateKey(prevDate)));
			data.push(0);
		}

		// Fill all dates between min and max (including gaps)
		const [minYear, minMonth, minDay] = minDateKey.split('-').map(Number);
		const [maxYear, maxMonth, maxDay] = maxDateKey.split('-').map(Number);

		let currentDate = new Date(minYear, minMonth - 1, minDay);
		const endDate = new Date(maxYear, maxMonth - 1, maxDay);

		while (currentDate <= endDate) {
			const dateKey = getLocalDateKey(currentDate);
			labels.push(formatLocalDate(dateKey));
			data.push(byDate[dateKey] || 0);
			currentDate = new Date(currentDate.getTime() + 24 * 60 * 60 * 1000);
		}

		// For single day, add padding day after to center the point
		if (isSingleDay) {
			const [year, month, day] = maxDateKey.split('-').map(Number);
			const nextDate = new Date(year, month - 1, day + 1);
			labels.push(formatLocalDate(getLocalDateKey(nextDate)));
			data.push(0);
		}

		const dateRange = isSingleDay
			? formatLocalDateFull(minDateKey)
			: `${formatLocalDateFull(minDateKey)} - ${formatLocalDateFull(maxDateKey)}`;

		return { labels, data, dateRange };
	}

	// Compute derived values for template
	let chartData = $derived(buildChartData(sessionsByDate));

	onMount(() => {
		registerChartDefaults();
		const { labels, data } = chartData;

		// Get resolved theme colors
		const colors = getThemeColors();

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
					legend: {
						display: false
					},
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
	});

	onDestroy(() => {
		chart?.destroy();
	});

	// Update chart when data changes
	$effect(() => {
		if (chart && sessionsByDate) {
			const { labels, data } = chartData;
			chart.data.labels = labels;
			chart.data.datasets[0].data = data;
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
