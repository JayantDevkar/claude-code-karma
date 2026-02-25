<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { ChevronDown, ChevronUp, Cable } from 'lucide-svelte';
	import { Chart, DoughnutController, ArcElement, Legend, Tooltip } from 'chart.js';
	import { parseMcpTool } from '$lib/utils/mcp';
	import {
		registerChartDefaults,
		createResponsiveConfig,
		chartColorPalette,
		getChartColor,
		getThemeColors
	} from './chartConfig';

	// Register Chart.js components
	Chart.register(DoughnutController, ArcElement, Legend, Tooltip);

	interface Props {
		toolsUsed: Record<string, number>;
		class?: string;
		initialLimit?: number;
	}

	let { toolsUsed, class: className = '', initialLimit = 6 }: Props = $props();

	let canvas: HTMLCanvasElement;
	let chart: Chart | null = null;
	let showAll = $state(false);

	// Sort entries by count descending
	let allEntries = $derived(Object.entries(toolsUsed).sort((a, b) => b[1] - a[1]));
	let hasMore = $derived(allEntries.length > initialLimit);
	let hiddenCount = $derived(allEntries.length - initialLimit);

	// Calculate "Others" aggregation for chart when collapsed
	let chartData = $derived.by(() => {
		if (showAll || !hasMore) {
			return {
				labels: allEntries.map(([name]) => name),
				data: allEntries.map(([, count]) => count),
				colors: allEntries.map((_, i) => getChartColor(i))
			};
		}

		const visible = allEntries.slice(0, initialLimit);
		const hidden = allEntries.slice(initialLimit);
		const othersSum = hidden.reduce((sum, [, count]) => sum + count, 0);

		return {
			labels: [...visible.map(([name]) => name), `+${hiddenCount} others`],
			data: [...visible.map(([, count]) => count), othersSum],
			colors: [...visible.map((_, i) => getChartColor(i)), '#9ca3af']
		};
	});

	// Total for percentage calculation
	let total = $derived(allEntries.reduce((sum, [, count]) => sum + count, 0));

	onMount(() => {
		registerChartDefaults();
		const colors = getThemeColors();

		chart = new Chart(canvas, {
			type: 'doughnut',
			data: {
				labels: chartData.labels,
				datasets: [
					{
						data: chartData.data,
						backgroundColor: chartData.colors,
						borderColor: colors.bgBase,
						borderWidth: 2
					}
				]
			},
			options: {
				...createResponsiveConfig(),
				plugins: {
					...createResponsiveConfig().plugins,
					legend: {
						display: false // We'll use custom legend
					},
					tooltip: {
						...createResponsiveConfig().plugins.tooltip,
						backgroundColor: colors.bgBase,
						titleColor: colors.text,
						bodyColor: colors.textSecondary,
						borderColor: colors.border,
						borderWidth: 1,
						callbacks: {
							label: (context) => {
								const value = context.raw as number;
								const percentage = ((value / total) * 100).toFixed(1);
								return `${value} calls (${percentage}%)`;
							}
						}
					}
				},
				cutout: '65%'
			}
		});
	});

	onDestroy(() => {
		chart?.destroy();
	});

	// Update chart when data changes
	$effect(() => {
		if (chart) {
			chart.data.labels = chartData.labels;
			chart.data.datasets[0].data = chartData.data;
			chart.data.datasets[0].backgroundColor = chartData.colors;
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
	<h3 class="text-sm font-medium text-[var(--text-primary)] mb-4">Tool Distribution</h3>

	<div class="flex flex-col gap-4">
		<!-- Doughnut Chart -->
		<div class="h-[180px] flex items-center justify-center">
			<canvas bind:this={canvas}></canvas>
		</div>

		<!-- Custom Legend -->
		<div class="space-y-1.5">
			{#each showAll ? allEntries : allEntries.slice(0, initialLimit) as [name, count], i}
				{@const mcp = parseMcpTool(name)}
				<div class="flex items-center gap-2 group">
					<span
						class="w-2.5 h-2.5 rounded-full flex-shrink-0"
						style="background-color: {getChartColor(i)}"
					></span>
					{#if mcp}
						<span class="flex items-center gap-1 truncate flex-1 min-w-0">
							<a
								href="/tools/{encodeURIComponent(mcp.server)}"
								class="inline-flex items-center gap-0.5 px-1 py-0.5 rounded text-[9px] font-medium bg-[var(--nav-teal)]/10 text-[var(--nav-teal)] hover:bg-[var(--nav-teal)]/20 transition-colors flex-shrink-0"
								title="View {mcp.server} in MCP Tools"
							>
								<Cable size={9} />
								{mcp.server}
							</a>
							<span
								class="text-xs text-[var(--text-secondary)] truncate"
								title={name}
							>
								{mcp.shortName}
							</span>
						</span>
					{:else}
						<span
							class="text-xs text-[var(--text-secondary)] truncate flex-1"
							title={name}
						>
							{name}
						</span>
					{/if}
					<span class="text-xs font-mono text-[var(--text-muted)] tabular-nums">
						{count}
					</span>
					<span class="text-xs text-[var(--text-muted)] tabular-nums w-12 text-right">
						{((count / total) * 100).toFixed(0)}%
					</span>
				</div>
			{/each}

			<!-- Show More / Show Less -->
			{#if hasMore}
				<button
					onclick={() => (showAll = !showAll)}
					class="
						flex items-center gap-1.5 w-full pt-2 mt-1
						text-xs text-[var(--text-muted)] hover:text-[var(--text-secondary)]
						border-t border-[var(--border)]
						transition-colors cursor-pointer
					"
				>
					{#if showAll}
						<ChevronUp size={14} />
						<span>Show less</span>
					{:else}
						<ChevronDown size={14} />
						<span>Show {hiddenCount} more tools</span>
					{/if}
				</button>
			{/if}
		</div>
	</div>
</div>
