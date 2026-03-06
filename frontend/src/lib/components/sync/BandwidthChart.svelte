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
	import { registerChartDefaults, createResponsiveConfig } from '$lib/components/charts/chartConfig';

	Chart.register(LineController, LineElement, PointElement, LinearScale, CategoryScale, Filler, Tooltip);

	let {
		uploadData = [],
		downloadData = [],
		labels = []
	}: {
		uploadData: number[];
		downloadData: number[];
		labels: string[];
	} = $props();

	let canvas: HTMLCanvasElement;
	let chart: Chart | null = null;

	function formatBytes(value: number): string {
		if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)} MB/s`;
		if (value >= 1_000) return `${(value / 1_000).toFixed(1)} KB/s`;
		return `${value.toFixed(0)} B/s`;
	}

	function hexToRgba(hex: string, alpha: number): string {
		// Handle css variable resolved values like "#7c3aed" or "rgb(124, 58, 237)"
		if (hex.startsWith('rgb')) {
			const match = hex.match(/rgb\((\d+),\s*(\d+),\s*(\d+)\)/);
			if (match) {
				return `rgba(${match[1]}, ${match[2]}, ${match[3]}, ${alpha})`;
			}
		}
		const clean = hex.replace('#', '');
		const r = parseInt(clean.substring(0, 2), 16);
		const g = parseInt(clean.substring(2, 4), 16);
		const b = parseInt(clean.substring(4, 6), 16);
		if (isNaN(r) || isNaN(g) || isNaN(b)) return `rgba(128, 128, 128, ${alpha})`;
		return `rgba(${r}, ${g}, ${b}, ${alpha})`;
	}

	onMount(() => {
		registerChartDefaults();

		const uploadColor = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim();
		const downloadColor = getComputedStyle(document.documentElement).getPropertyValue('--info').trim();

		const responsiveConfig = createResponsiveConfig(false);

		chart = new Chart(canvas, {
			type: 'line',
			data: {
				labels: [...labels],
				datasets: [
					{
						label: 'Upload',
						data: [...uploadData],
						borderColor: uploadColor,
						backgroundColor: hexToRgba(uploadColor, 0.1),
						fill: true,
						tension: 0.3,
						pointRadius: 0,
						borderWidth: 1.5
					},
					{
						label: 'Download',
						data: [...downloadData],
						borderColor: downloadColor,
						backgroundColor: hexToRgba(downloadColor, 0.1),
						fill: true,
						tension: 0.3,
						pointRadius: 0,
						borderWidth: 1.5
					}
				]
			},
			options: {
				...responsiveConfig,
				plugins: {
					...responsiveConfig.plugins,
					legend: {
						display: false
					},
					tooltip: {
						...responsiveConfig.plugins.tooltip,
						callbacks: {
							label: (ctx) => `${ctx.dataset.label}: ${formatBytes(ctx.parsed.y ?? 0)}`
						}
					}
				},
				scales: {
					x: {
						display: false
					},
					y: {
						beginAtZero: true,
						grid: {
							color: 'rgba(128, 128, 128, 0.1)'
						},
						ticks: {
							color: 'var(--text-muted)',
							font: {
								family: 'JetBrains Mono, monospace',
								size: 10
							},
							callback: (value) => formatBytes(Number(value))
						}
					}
				}
			}
		});
	});

	$effect(() => {
		if (!chart) return;
		chart.data.labels = [...labels];
		chart.data.datasets[0].data = [...uploadData];
		chart.data.datasets[1].data = [...downloadData];
		chart.update('none');
	});

	onDestroy(() => {
		chart?.destroy();
	});
</script>

<div class="h-[120px] w-full">
	<canvas bind:this={canvas}></canvas>
</div>
