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
	import { Play, Bot, Zap, Wrench, TrendingUp, Clock, Calendar } from 'lucide-svelte';
	import { formatDistanceToNow } from 'date-fns';
	import type { PluginUsageStats } from '$lib/api-types';
	import {
		registerChartDefaults,
		createResponsiveConfig,
		createCommonScaleConfig,
		chartColorPalette,
		getThemeColors
	} from '../charts/chartConfig';
	import SegmentedControl from '$lib/components/ui/SegmentedControl.svelte';

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
		usage: PluginUsageStats;
		pluginName: string;
		mcpServers?: string[];
	}

	let { usage, pluginName, mcpServers = [] }: Props = $props();

	// Agent/skill types in the DB use the short plugin name (before @), e.g.
	// "oh-my-claudecode:explore-medium" not "oh-my-claudecode@omc:explore-medium"
	let pluginShortName = $derived(pluginName.split('@')[0]);

	// --- Metric computations ---

	let totalRuns = $derived(
		usage.total_agent_runs + usage.total_skill_invocations + usage.total_mcp_tool_calls
	);

	let avgPerDay = $derived.by(() => {
		if (usage.trend.length === 0) return 0;
		const total = usage.trend.reduce(
			(sum, d) => sum + d.agent_runs + d.skill_invocations + d.mcp_tool_calls,
			0
		);
		return Math.round(total / usage.trend.length);
	});

	let lastActiveLabel = $derived.by(() => {
		if (!usage.last_used) return null;
		try {
			return formatDistanceToNow(new Date(usage.last_used)) + ' ago';
		} catch {
			return null;
		}
	});

	let firstUsedLabel = $derived.by(() => {
		if (!usage.first_used) return null;
		try {
			const d = new Date(usage.first_used);
			return d.toLocaleDateString('en-US', {
				month: 'short',
				day: 'numeric',
				year: 'numeric'
			});
		} catch {
			return null;
		}
	});

	// --- Top agents & skills with proportional bars ---

	let topAgents = $derived.by(() => {
		const entries = Object.entries(usage.by_agent)
			.sort(([, a], [, b]) => b - a)
			.slice(0, 5);
		const max = entries.length > 0 ? entries[0][1] : 1;
		return entries.map(([name, count]) => ({ name, count, pct: (count / max) * 100 }));
	});

	let topSkills = $derived.by(() => {
		const entries = Object.entries(usage.by_skill)
			.sort(([, a], [, b]) => b - a)
			.slice(0, 5);
		const max = entries.length > 0 ? entries[0][1] : 1;
		return entries.map(([name, count]) => ({ name, count, pct: (count / max) * 100 }));
	});

	let topMcpTools = $derived.by(() => {
		const entries = Object.entries(usage.by_mcp_tool ?? {})
			.sort(([, a], [, b]) => b - a)
			.slice(0, 5);
		const max = entries.length > 0 ? entries[0][1] : 1;
		return entries.map(([name, count]) => ({ name, count, pct: (count / max) * 100 }));
	});

	let hasUsage = $derived(
		usage.total_agent_runs > 0 ||
			usage.total_skill_invocations > 0 ||
			usage.total_mcp_tool_calls > 0
	);

	// --- Trend chart ---

	type RangeKey = '7d' | '30d' | '90d';
	let selectedRange = $state<RangeKey>('30d');

	const rangeOptions = [
		{ label: '7d', value: '7d' },
		{ label: '30d', value: '30d' },
		{ label: '90d', value: '90d' }
	];

	let filteredTrend = $derived.by(() => {
		const days = selectedRange === '7d' ? 7 : selectedRange === '30d' ? 30 : 90;
		const sorted = [...usage.trend].sort(
			(a, b) => new Date(a.date).getTime() - new Date(b.date).getTime()
		);
		return sorted.slice(-days);
	});

	let trendLabels = $derived(
		filteredTrend.map((d) => {
			const date = new Date(d.date + 'T00:00:00');
			return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
		})
	);

	let trendAgentData = $derived(filteredTrend.map((d) => d.agent_runs));
	let trendSkillData = $derived(filteredTrend.map((d) => d.skill_invocations));
	let trendMcpData = $derived(filteredTrend.map((d) => d.mcp_tool_calls));

	let canvas: HTMLCanvasElement;
	let chart: Chart | null = null;

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
						label: 'Agent Runs',
						data: trendAgentData,
						borderColor: chartColorPalette[0],
						backgroundColor: 'rgba(124, 58, 237, 0.15)',
						fill: true,
						tension: 0.4,
						pointRadius: filteredTrend.length <= 14 ? 3 : 0,
						pointHoverRadius: 5,
						pointBackgroundColor: chartColorPalette[0],
						pointBorderColor: colors.bgBase,
						pointBorderWidth: 2,
						order: 2
					},
					{
						label: 'Skill Invocations',
						data: trendSkillData,
						borderColor: chartColorPalette[2],
						backgroundColor: 'rgba(16, 185, 129, 0.15)',
						fill: true,
						tension: 0.4,
						pointRadius: filteredTrend.length <= 14 ? 3 : 0,
						pointHoverRadius: 5,
						pointBackgroundColor: chartColorPalette[2],
						pointBorderColor: colors.bgBase,
						pointBorderWidth: 2,
						order: 2
					},
					{
						label: 'MCP Tool Calls',
						data: trendMcpData,
						borderColor: chartColorPalette[4],
						backgroundColor: 'rgba(245, 158, 11, 0.15)',
						fill: true,
						tension: 0.4,
						pointRadius: filteredTrend.length <= 14 ? 3 : 0,
						pointHoverRadius: 5,
						pointBackgroundColor: chartColorPalette[4],
						pointBorderColor: colors.bgBase,
						pointBorderWidth: 2,
						order: 1
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
					legend: {
						display: false
					},
					tooltip: {
						...createResponsiveConfig().plugins.tooltip,
						backgroundColor: colors.bgBase,
						titleColor: colors.text,
						bodyColor: colors.textSecondary,
						borderColor: colors.border,
						borderWidth: 1,
						displayColors: true,
						callbacks: {
							footer: (items) => {
								const total = items.reduce(
									(sum, item) => sum + (item.raw as number),
									0
								);
								return `Total: ${total}`;
							}
						}
					}
				},
				scales: {
					...createCommonScaleConfig(),
					y: {
						...createCommonScaleConfig().y,
						stacked: true
					}
				}
			}
		});
	}

	onMount(() => {
		createChart();
	});

	onDestroy(() => {
		chart?.destroy();
	});

	// Rebuild chart when range or data changes
	$effect(() => {
		// Read reactive deps
		// eslint-disable-next-line @typescript-eslint/no-unused-expressions
		selectedRange;
		// eslint-disable-next-line @typescript-eslint/no-unused-expressions
		filteredTrend;

		if (chart && canvas) {
			chart.data.labels = trendLabels;
			chart.data.datasets[0].data = trendAgentData;
			chart.data.datasets[1].data = trendSkillData;
			if (chart.data.datasets[2]) {
				chart.data.datasets[2].data = trendMcpData;
			}
			// Toggle point visibility based on data density
			const showPoints = filteredTrend.length <= 14;
			for (const ds of chart.data.datasets) {
				// eslint-disable-next-line @typescript-eslint/no-explicit-any
				(ds as any).pointRadius = showPoints ? 3 : 0;
			}
			chart.update();
		}
	});
</script>

<div class="space-y-6">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<h3 class="text-sm font-semibold text-[var(--text-primary)]">Usage Analytics</h3>
		{#if firstUsedLabel}
			<span class="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
				<Calendar size={12} />
				Since {firstUsedLabel}
			</span>
		{/if}
	</div>

	{#if !hasUsage}
		<!-- Empty state -->
		<div
			class="text-center py-12 bg-[var(--bg-subtle)] rounded-xl border border-dashed border-[var(--border)]"
		>
			<TrendingUp size={32} class="mx-auto text-[var(--text-muted)] mb-3" />
			<p class="text-sm text-[var(--text-secondary)]">No usage data yet</p>
			<p class="text-xs text-[var(--text-muted)] mt-1">
				Usage analytics will appear once you start using this plugin
			</p>
		</div>
	{:else}
		<!-- Stats cards -->
		<div class="grid grid-cols-2 md:grid-cols-5 gap-4">
			<div class="bg-[var(--bg-subtle)] rounded-xl p-4">
				<div class="flex items-center gap-2 text-[var(--text-muted)] mb-2">
					<Bot size={14} />
					<span class="text-xs font-medium">Agent Runs</span>
				</div>
				<p class="text-2xl font-bold text-[var(--text-primary)] tabular-nums">
					{usage.total_agent_runs.toLocaleString()}
				</p>
			</div>

			<div class="bg-[var(--bg-subtle)] rounded-xl p-4">
				<div class="flex items-center gap-2 text-[var(--text-muted)] mb-2">
					<Zap size={14} />
					<span class="text-xs font-medium">Skill Invocations</span>
				</div>
				<p class="text-2xl font-bold text-[var(--text-primary)] tabular-nums">
					{usage.total_skill_invocations.toLocaleString()}
				</p>
			</div>

			<div class="bg-[var(--bg-subtle)] rounded-xl p-4">
				<div class="flex items-center gap-2 text-[var(--text-muted)] mb-2">
					<Wrench size={14} />
					<span class="text-xs font-medium">MCP Tools</span>
				</div>
				<p class="text-2xl font-bold text-[var(--text-primary)] tabular-nums">
					{usage.total_mcp_tool_calls.toLocaleString()}
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

		<!-- Activity Trend Chart -->
		{#if usage.trend.length > 0}
			<div class="bg-[var(--bg-subtle)] rounded-xl p-4">
				<div class="flex items-center justify-between mb-4">
					<div class="flex items-center gap-4">
						<h4 class="text-sm font-medium text-[var(--text-primary)]">
							Activity Trend
						</h4>
						<!-- Legend -->
						<div class="flex items-center gap-3 text-xs text-[var(--text-muted)]">
							<span class="flex items-center gap-1.5">
								<span
									class="inline-block w-2.5 h-2.5 rounded-sm"
									style="background-color: {chartColorPalette[0]};"
								></span>
								Agents
							</span>
							<span class="flex items-center gap-1.5">
								<span
									class="inline-block w-2.5 h-2.5 rounded-sm"
									style="background-color: {chartColorPalette[2]};"
								></span>
								Skills
							</span>
							<span class="flex items-center gap-1.5">
								<span
									class="inline-block w-2.5 h-2.5 rounded-sm"
									style="background-color: {chartColorPalette[4]};"
								></span>
								MCP Tools
							</span>
						</div>
					</div>
					<SegmentedControl options={rangeOptions} bind:value={selectedRange} size="sm" />
				</div>
				<div class="h-[200px]">
					<canvas bind:this={canvas}></canvas>
				</div>
			</div>
		{/if}

		<!-- Top Agents, Skills & MCP Tools -->
		<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
			<!-- Top Agents -->
			<div class="bg-[var(--bg-subtle)] rounded-xl p-4">
				<div class="flex items-center gap-2 mb-4">
					<Bot size={16} class="text-[var(--text-muted)]" />
					<h4 class="text-sm font-medium text-[var(--text-primary)]">Top Agents</h4>
				</div>
				{#if topAgents.length === 0}
					<p class="text-xs text-[var(--text-muted)] text-center py-4">No agent usage</p>
				{:else}
					<div class="space-y-3">
						{#each topAgents as { name, count, pct }, i}
							<div>
								<div class="flex items-center justify-between text-sm mb-1">
									<a
										href="/agents/{encodeURIComponent(
											pluginShortName + ':' + name
										)}"
										class="text-[var(--text-secondary)] hover:text-[var(--accent)] truncate flex-1 mr-2 text-xs font-medium"
									>
										{name}
									</a>
									<span
										class="text-[var(--text-muted)] tabular-nums text-xs flex-shrink-0"
										>{count.toLocaleString()}</span
									>
								</div>
								<div
									class="h-1.5 bg-[var(--bg-muted)] rounded-full overflow-hidden"
								>
									<div
										class="h-full rounded-full transition-all duration-500 ease-out"
										style="width: {pct}%; background-color: {chartColorPalette[0]}; opacity: {1 -
											i * 0.12};"
									></div>
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</div>

			<!-- Top Skills -->
			<div class="bg-[var(--bg-subtle)] rounded-xl p-4">
				<div class="flex items-center gap-2 mb-4">
					<Zap size={16} class="text-[var(--text-muted)]" />
					<h4 class="text-sm font-medium text-[var(--text-primary)]">Top Skills</h4>
				</div>
				{#if topSkills.length === 0}
					<p class="text-xs text-[var(--text-muted)] text-center py-4">No skill usage</p>
				{:else}
					<div class="space-y-3">
						{#each topSkills as { name, count, pct }, i}
							<div>
								<div class="flex items-center justify-between text-sm mb-1">
									<a
										href="/skills/{encodeURIComponent(
											pluginShortName + ':' + name
										)}"
										class="text-[var(--text-secondary)] hover:text-[var(--accent)] truncate flex-1 mr-2 text-xs font-medium"
									>
										{name}
									</a>
									<span
										class="text-[var(--text-muted)] tabular-nums text-xs flex-shrink-0"
										>{count.toLocaleString()}</span
									>
								</div>
								<div
									class="h-1.5 bg-[var(--bg-muted)] rounded-full overflow-hidden"
								>
									<div
										class="h-full rounded-full transition-all duration-500 ease-out"
										style="width: {pct}%; background-color: {chartColorPalette[2]}; opacity: {1 -
											i * 0.12};"
									></div>
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</div>

			<!-- Top MCP Tools -->
			<div class="bg-[var(--bg-subtle)] rounded-xl p-4">
				<div class="flex items-center gap-2 mb-4">
					<Wrench size={16} class="text-[var(--text-muted)]" />
					<h4 class="text-sm font-medium text-[var(--text-primary)]">Top MCP Tools</h4>
				</div>
				{#if topMcpTools.length === 0}
					<p class="text-xs text-[var(--text-muted)] text-center py-4">
						No MCP tool usage
					</p>
				{:else}
					<div class="space-y-3">
						{#each topMcpTools as { name, count, pct }, i}
							{@const serverName =
								mcpServers.length === 1
									? mcpServers[0]
									: mcpServers.find((s) => name.startsWith('mcp__' + s + '__')) ||
										mcpServers[0] ||
										''}
							<div>
								<div class="flex items-center justify-between text-sm mb-1">
									{#if serverName}
										<a
											href="/tools/{encodeURIComponent(
												serverName
											)}/{encodeURIComponent(name)}"
											class="text-[var(--text-secondary)] hover:text-[var(--accent)] truncate flex-1 mr-2 text-xs font-medium transition-colors"
										>
											{name}
										</a>
									{:else}
										<span
											class="text-[var(--text-secondary)] truncate flex-1 mr-2 text-xs font-medium"
										>
											{name}
										</span>
									{/if}
									<span
										class="text-[var(--text-muted)] tabular-nums text-xs flex-shrink-0"
										>{count.toLocaleString()}</span
									>
								</div>
								<div
									class="h-1.5 bg-[var(--bg-muted)] rounded-full overflow-hidden"
								>
									<div
										class="h-full rounded-full transition-all duration-500 ease-out"
										style="width: {pct}%; background-color: {chartColorPalette[4]}; opacity: {1 -
											i * 0.12};"
									></div>
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</div>
		</div>
	{/if}
</div>
