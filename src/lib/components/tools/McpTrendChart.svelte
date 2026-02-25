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
		Tooltip,
		Legend
	} from 'chart.js';
	import type { McpServerTrend } from '$lib/api-types';
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
		Tooltip,
		Legend
	);

	interface Props {
		trend: McpServerTrend[];
		accentColor?: string;
	}

	let { trend, accentColor = '#14b8a6' }: Props = $props();

	const subagentColor = '#8b5cf6';

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

	let mainDataPoints = $derived(sortedTrend.map((d) => d.main_calls ?? d.calls));
	let subDataPoints = $derived(sortedTrend.map((d) => d.subagent_calls ?? 0));
	let hasSubagentData = $derived(subDataPoints.some((v) => v > 0));

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
		const showPoints = sortedTrend.length <= 14;

		const datasets = [
			{
				label: hasSubagentData ? 'Main' : 'Calls',
				data: mainDataPoints,
				borderColor: accentColor,
				backgroundColor: hexToRgba(accentColor, 0.15),
				fill: true,
				tension: 0.4,
				pointRadius: showPoints ? 3 : 0,
				pointHoverRadius: 5,
				pointBackgroundColor: accentColor,
				pointBorderColor: colors.bgBase,
				pointBorderWidth: 2
			}
		];

		if (hasSubagentData) {
			datasets.push({
				label: 'Subagent',
				data: subDataPoints,
				borderColor: subagentColor,
				backgroundColor: hexToRgba(subagentColor, 0.1),
				fill: true,
				tension: 0.4,
				pointRadius: showPoints ? 3 : 0,
				pointHoverRadius: 5,
				pointBackgroundColor: subagentColor,
				pointBorderColor: colors.bgBase,
				pointBorderWidth: 2
			});
		}

		chart = new Chart(canvas, {
			type: 'line',
			data: { labels, datasets },
			options: {
				...createResponsiveConfig(),
				interaction: { mode: 'index', intersect: false },
				plugins: {
					...createResponsiveConfig().plugins,
					legend: { display: hasSubagentData },
					tooltip: {
						...createResponsiveConfig().plugins.tooltip,
						backgroundColor: colors.bgBase,
						titleColor: colors.text,
						bodyColor: colors.textSecondary,
						borderColor: colors.border,
						borderWidth: 1,
						displayColors: true,
						callbacks: {
							afterBody: (items) => {
								const idx = items[0]?.dataIndex;
								if (idx !== undefined && sortedTrend[idx]) {
									const d = sortedTrend[idx];
									const lines = [];
									if (hasSubagentData) {
										lines.push(`Total: ${(d.main_calls ?? 0) + (d.subagent_calls ?? 0)}`);
									}
									lines.push(`${d.sessions} sessions`);
									return lines.join('\n');
								}
								return '';
							}
						}
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
				chart.data.datasets[0].data = mainDataPoints;
				if (chart.data.datasets[1]) {
					chart.data.datasets[1].data = subDataPoints;
				}
				const showPoints = sortedTrend.length <= 14;
				// eslint-disable-next-line @typescript-eslint/no-explicit-any
				(chart.data.datasets[0] as any).pointRadius = showPoints ? 3 : 0;
				if (chart.data.datasets[1]) {
					// eslint-disable-next-line @typescript-eslint/no-explicit-any
					(chart.data.datasets[1] as any).pointRadius = showPoints ? 3 : 0;
				}
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
