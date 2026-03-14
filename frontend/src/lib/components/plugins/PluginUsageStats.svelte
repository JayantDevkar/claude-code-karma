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
	import { Play, Bot, Zap, Wrench, Terminal, TrendingUp, Clock, Calendar } from 'lucide-svelte';
	import { formatDistanceToNow } from 'date-fns';
	import type { PluginUsageStats } from '$lib/api-types';
	import {
		registerChartDefaults,
		createResponsiveConfig,
		createCommonScaleConfig,
		chartColorPalette,
		getThemeColors,
		onThemeChange
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
		usage.total_agent_runs +
			usage.total_skill_invocations +
			usage.total_command_invocations +
			usage.total_mcp_tool_calls
	);

	let avgPerDay = $derived.by(() => {
		if (usage.trend.length === 0) return 0;
		const total = usage.trend.reduce(
			(sum, d) =>
				sum + d.agent_runs + d.skill_invocations + d.command_invocations + d.mcp_tool_calls,
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

	// --- Top agents, skills, commands & MCP tools with proportional bars ---

	let topAgents = $derived.by(() => {
		const entries = Object.entries(usage.by_agent ?? {})
			.sort(([, a], [, b]) => b - a)
			.slice(0, 5);
		const max = entries.length > 0 ? entries[0][1] : 1;
		return entries.map(([name, count]) => ({ name, count, pct: (count / max) * 100 }));
	});

	let topSkills = $derived.by(() => {
		const entries = Object.entries(usage.by_skill ?? {})
			.sort(([, a], [, b]) => b - a)
			.slice(0, 5);
		const max = entries.length > 0 ? entries[0][1] : 1;
		return entries.map(([name, count]) => ({ name, count, pct: (count / max) * 100 }));
	});

	let topCommands = $derived.by(() => {
		const entries = Object.entries(usage.by_command ?? {})
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
			usage.total_command_invocations > 0 ||
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

	let trendDates = $derived(filteredTrend.map((d) => d.date));

	// --- Per-item chart data ---

	// Agent colors: purple spectrum
	const agentColors = ['#7c3aed', '#8b5cf6', '#a78bfa', '#6d28d9', '#5b21b6', '#c4b5fd'];
	// Skill colors: green/teal spectrum
	const skillColors = ['#10b981', '#14b8a6', '#34d399', '#059669', '#047857', '#6ee7b7'];
	// Command colors: blue spectrum
	const commandColors = ['#3b82f6', '#60a5fa', '#93c5fd', '#2563eb', '#1d4ed8', '#bfdbfe'];
	// MCP colors: amber/orange spectrum
	const mcpColors = ['#f59e0b', '#f97316', '#fbbf24', '#d97706', '#ea580c', '#fcd34d'];

	interface ItemTrend {
		name: string;
		data: number[];
		color: string;
		category: 'agent' | 'skill' | 'command' | 'mcp';
	}

	let itemTrends = $derived.by((): ItemTrend[] => {
		const items: ItemTrend[] = [];

		// Top agents by total count
		const topAgentNames = Object.entries(usage.by_agent ?? {})
			.sort(([, a], [, b]) => b - a)
			.slice(0, 6)
			.map(([name]) => name);

		topAgentNames.forEach((name, i) => {
			const daily = usage.by_agent_daily?.[name] ?? {};
			const data = trendDates.map((date) => daily[date] ?? 0);
			// Only include if has any non-zero values in this range
			if (data.some((v) => v > 0)) {
				items.push({ name, data, color: agentColors[i % agentColors.length], category: 'agent' });
			}
		});

		// Top skills
		const topSkillNames = Object.entries(usage.by_skill ?? {})
			.sort(([, a], [, b]) => b - a)
			.slice(0, 6)
			.map(([name]) => name);

		topSkillNames.forEach((name, i) => {
			const daily = usage.by_skill_daily?.[name] ?? {};
			const data = trendDates.map((date) => daily[date] ?? 0);
			if (data.some((v) => v > 0)) {
				items.push({ name, data, color: skillColors[i % skillColors.length], category: 'skill' });
			}
		});

		// Top commands
		const topCommandNames = Object.entries(usage.by_command ?? {})
			.sort(([, a], [, b]) => b - a)
			.slice(0, 6)
			.map(([name]) => name);

		topCommandNames.forEach((name, i) => {
			const daily = usage.by_command_daily?.[name] ?? {};
			const data = trendDates.map((date) => daily[date] ?? 0);
			if (data.some((v) => v > 0)) {
				items.push({
					name,
					data,
					color: commandColors[i % commandColors.length],
					category: 'command'
				});
			}
		});

		// Top MCP tools
		const topMcpNames = Object.entries(usage.by_mcp_tool ?? {})
			.sort(([, a], [, b]) => b - a)
			.slice(0, 6)
			.map(([name]) => name);

		topMcpNames.forEach((name, i) => {
			const daily = usage.by_mcp_tool_daily?.[name] ?? {};
			const data = trendDates.map((date) => daily[date] ?? 0);
			if (data.some((v) => v > 0)) {
				items.push({ name, data, color: mcpColors[i % mcpColors.length], category: 'mcp' });
			}
		});

		return items;
	});

	// Legend items grouped by category
	let legendItems = $derived.by(() => {
		const groups: { category: string; icon: string; items: { name: string; color: string }[] }[] =
			[];

		const agents = itemTrends.filter((t) => t.category === 'agent');
		const skills = itemTrends.filter((t) => t.category === 'skill');
		const commands = itemTrends.filter((t) => t.category === 'command');
		const mcps = itemTrends.filter((t) => t.category === 'mcp');

		if (agents.length > 0) {
			groups.push({
				category: 'Agents',
				icon: 'bot',
				items: agents.map((t) => ({ name: t.name, color: t.color }))
			});
		}
		if (skills.length > 0) {
			groups.push({
				category: 'Skills',
				icon: 'zap',
				items: skills.map((t) => ({ name: t.name, color: t.color }))
			});
		}
		if (commands.length > 0) {
			groups.push({
				category: 'Commands',
				icon: 'terminal',
				items: commands.map((t) => ({ name: t.name, color: t.color }))
			});
		}
		if (mcps.length > 0) {
			groups.push({
				category: 'MCP Tools',
				icon: 'wrench',
				items: mcps.map((t) => ({ name: t.name, color: t.color }))
			});
		}

		return groups;
	});

	let canvas = $state<HTMLCanvasElement>();
	let chart: Chart | null = null;

	function createChart() {
		if (!canvas || filteredTrend.length === 0 || itemTrends.length === 0) return;

		chart?.destroy();

		registerChartDefaults();
		const colors = getThemeColors();
		const showPoints = filteredTrend.length <= 14;

		const datasets = itemTrends.map((item) => ({
			label: item.name,
			data: item.data,
			borderColor: item.color,
			backgroundColor: 'transparent',
			fill: false,
			tension: 0.4,
			borderWidth: 2,
			pointRadius: showPoints ? 3 : 0,
			pointHoverRadius: 5,
			pointBackgroundColor: item.color,
			pointBorderColor: colors.bgBase,
			pointBorderWidth: 2
		}));

		chart = new Chart(canvas, {
			type: 'line',
			data: {
				labels: trendLabels,
				datasets
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
						filter: (item) => (item.raw as number) > 0,
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
						stacked: false
					}
				}
			}
		});
	}

	let cleanupTheme: (() => void) | null = null;

	onMount(() => {
		createChart();
		cleanupTheme = onThemeChange(() => createChart());
	});

	onDestroy(() => {
		cleanupTheme?.();
		chart?.destroy();
	});

	// Rebuild chart when range or data changes
	$effect(() => {
		// Read reactive deps
		// eslint-disable-next-line @typescript-eslint/no-unused-expressions
		selectedRange;
		// eslint-disable-next-line @typescript-eslint/no-unused-expressions
		filteredTrend;
		// eslint-disable-next-line @typescript-eslint/no-unused-expressions
		itemTrends;

		if (canvas) {
			createChart();
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
		<div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
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
					<Terminal size={14} />
					<span class="text-xs font-medium">Commands</span>
				</div>
				<p class="text-2xl font-bold text-[var(--text-primary)] tabular-nums">
					{usage.total_command_invocations.toLocaleString()}
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
		{#if usage.trend.length > 0 && itemTrends.length > 0}
			<div class="bg-[var(--bg-subtle)] rounded-xl p-4">
				<div class="flex items-center justify-between mb-4">
					<h4 class="text-sm font-medium text-[var(--text-primary)]">Activity Trend</h4>
					<SegmentedControl options={rangeOptions} bind:value={selectedRange} size="sm" />
				</div>

				<!-- Grouped legend -->
				<div class="flex flex-wrap gap-x-6 gap-y-2 mb-4">
					{#each legendItems as group}
						<div class="flex items-center gap-2">
							<span class="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider"
								>{group.category}</span
							>
							<div class="flex items-center gap-2.5">
								{#each group.items as item}
									<span class="flex items-center gap-1 text-xs text-[var(--text-secondary)]">
										<span
											class="inline-block w-2 h-2 rounded-full"
											style="background-color: {item.color};"
										></span>
										{item.name}
									</span>
								{/each}
							</div>
						</div>
					{/each}
				</div>

				<div class="h-[220px]">
					<canvas bind:this={canvas}></canvas>
				</div>
			</div>
		{/if}

		<!-- Top Agents, Skills, Commands & MCP Tools -->
		<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
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
										style="width: {pct}%; background-color: {agentColors[i % agentColors.length]};"
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
										style="width: {pct}%; background-color: {skillColors[i % skillColors.length]};"
									></div>
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</div>

			<!-- Top Commands -->
			<div class="bg-[var(--bg-subtle)] rounded-xl p-4">
				<div class="flex items-center gap-2 mb-4">
					<Terminal size={16} class="text-[var(--text-muted)]" />
					<h4 class="text-sm font-medium text-[var(--text-primary)]">Top Commands</h4>
				</div>
				{#if topCommands.length === 0}
					<p class="text-xs text-[var(--text-muted)] text-center py-4">No command usage</p>
				{:else}
					<div class="space-y-3">
						{#each topCommands as { name, count, pct }, i}
							<div>
								<div class="flex items-center justify-between text-sm mb-1">
									<a
										href="/commands/{encodeURIComponent(
											pluginShortName + ':' + name
										)}"
										class="text-[var(--text-secondary)] hover:text-[var(--accent)] truncate flex-1 mr-2 text-xs font-medium transition-colors"
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
										style="width: {pct}%; background-color: {commandColors[i % commandColors.length]};"
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
										style="width: {pct}%; background-color: {mcpColors[i % mcpColors.length]};"
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
