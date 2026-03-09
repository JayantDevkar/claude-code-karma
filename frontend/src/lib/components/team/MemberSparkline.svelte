<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import {
		Chart,
		LineController,
		LineElement,
		PointElement,
		LinearScale,
		CategoryScale
	} from 'chart.js';

	Chart.register(LineController, LineElement, PointElement, LinearScale, CategoryScale);

	interface Props {
		data: number[];
		color: string;
		class?: string;
	}

	let { data, color, class: className = '' }: Props = $props();

	let canvas: HTMLCanvasElement;
	let chart: Chart | null = null;

	onMount(() => {
		chart = new Chart(canvas, {
			type: 'line',
			data: {
				labels: data.map((_, i) => String(i)),
				datasets: [
					{
						data,
						borderColor: color,
						backgroundColor: color + '20',
						fill: true,
						tension: 0.4,
						pointRadius: 0,
						borderWidth: 1.5
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				plugins: { legend: { display: false }, tooltip: { enabled: false } },
				scales: {
					x: { display: false },
					y: { display: false, beginAtZero: true }
				}
			}
		});
	});

	onDestroy(() => {
		chart?.destroy();
	});

	$effect(() => {
		if (chart && data) {
			chart.data.labels = data.map((_, i) => String(i));
			chart.data.datasets[0].data = data;
			chart.update();
		}
	});
</script>

<div class="w-20 h-8 {className}">
	<canvas bind:this={canvas}></canvas>
</div>
