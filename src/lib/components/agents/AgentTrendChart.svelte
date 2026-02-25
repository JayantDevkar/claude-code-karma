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
		Tooltip
	} from 'chart.js';
	import {
		registerChartDefaults,
		createResponsiveConfig,
		createCommonScaleConfig,
		getThemeColors
	} from '$lib/components/charts/chartConfig';

	Chart.register(
		LineController,
		LineElement,
		PointElement,
		LinearScale,
		CategoryScale,
		Filler,
		Tooltip
	);

	interface TrendItem {
		date: string;
		count: number;
	}

	interface Props {
		trend: TrendItem[];
		cssColor?: string;
	}

	let { trend, cssColor = 'var(--accent)' }: Props = $props();

	let canvas: HTMLCanvasElement;
	let chart: Chart | null = null;

	let sortedTrend = $derived(
		[...trend].sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime())
	);

	let labels = $derived(
		sortedTrend.map((d) => {
			const date = new Date(d.date + 'T00:00:00');
			return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
		})
	);

	let dataPoints = $derived(sortedTrend.map((d) => d.count));

	function resolveColor(cssVar: string): string {
		if (cssVar.startsWith('#')) return cssVar;
		if (cssVar.startsWith('var(') && canvas) {
			const computed = getComputedStyle(canvas).getPropertyValue(
				cssVar.replace(/var\(([^)]+)\)/, '$1').trim()
			);
			return computed.trim() || '#7c3aed';
		}
		return '#7c3aed';
	}

	function hexToRgba(hex: string, alpha: number): string {
		const r = parseInt(hex.slice(1, 3), 16);
		const g = parseInt(hex.slice(3, 5), 16);
		const b = parseInt(hex.slice(5, 7), 16);
		return `rgba(${r}, ${g}, ${b}, ${alpha})`;
	}

	function createChart() {
		if (!canvas || sortedTrend.length === 0) return;
		chart?.destroy();
		registerChartDefaults();
		const colors = getThemeColors();
		const resolvedColor = resolveColor(cssColor);

		chart = new Chart(canvas, {
			type: 'line',
			data: {
				labels,
				datasets: [
					{
						label: 'Runs',
						data: dataPoints,
						borderColor: resolvedColor,
						backgroundColor: hexToRgba(resolvedColor, 0.15),
						fill: true,
						tension: 0.4,
						pointRadius: sortedTrend.length <= 14 ? 3 : 0,
						pointHoverRadius: 5,
						pointBackgroundColor: resolvedColor,
						pointBorderColor: colors.bgBase,
						pointBorderWidth: 2
					}
				]
			},
			options: {
				...createResponsiveConfig(),
				interaction: { mode: 'index', intersect: false },
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
		if (sortedTrend.length > 0) createChart();
	});

	onDestroy(() => {
		chart?.destroy();
	});

	$effect(() => {
		// eslint-disable-next-line @typescript-eslint/no-unused-expressions
		sortedTrend;
		if (canvas && sortedTrend.length > 0) {
			if (chart) {
				chart.data.labels = labels;
				chart.data.datasets[0].data = dataPoints;
				const showPoints = sortedTrend.length <= 14;
				// eslint-disable-next-line @typescript-eslint/no-explicit-any
				(chart.data.datasets[0] as any).pointRadius = showPoints ? 3 : 0;
				chart.update();
			} else {
				createChart();
			}
		}
	});
</script>

<div class="h-[200px]">
	<canvas bind:this={canvas}></canvas>
</div>
