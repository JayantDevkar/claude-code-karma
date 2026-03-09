<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import {
		Chart,
		BarController,
		BarElement,
		LinearScale,
		CategoryScale,
		Tooltip,
		Legend
	} from 'chart.js';
	import { Activity, FolderGit2, Clock } from 'lucide-svelte';
	import type { MemberProfile, StatItem } from '$lib/api-types';
	import StatsGrid from '$lib/components/StatsGrid.svelte';
	import {
		registerChartDefaults,
		createResponsiveConfig,
		createCommonScaleConfig,
		getThemeColors
	} from '$lib/components/charts/chartConfig';
	import { getTeamMemberHexColor, formatRelativeTime, formatDate } from '$lib/utils';

	// Register Chart.js components
	Chart.register(BarController, BarElement, LinearScale, CategoryScale, Tooltip, Legend);

	interface Props {
		profile: MemberProfile;
	}

	let { profile }: Props = $props();

	let canvas: HTMLCanvasElement;
	let chart: Chart | null = null;

	// Aggregate session stats by date
	let dateTotals = $derived.by(() => {
		const totals = new Map<string, { sent: number; received: number }>();
		for (const stat of profile.session_stats) {
			const existing = totals.get(stat.date) ?? { sent: 0, received: 0 };
			existing.sent += stat.packaged;
			existing.received += stat.received;
			totals.set(stat.date, existing);
		}
		// Sort by date ascending
		return new Map([...totals.entries()].sort(([a], [b]) => a.localeCompare(b)));
	});

	// Flatten and deduplicate projects across all teams
	let projectList = $derived.by(() => {
		const projectMap = new Map<string, { encoded_name: string; name: string; session_count: number }>();
		for (const team of profile.teams) {
			for (const project of team.projects) {
				const existing = projectMap.get(project.encoded_name);
				if (existing) {
					existing.session_count += project.session_count;
				} else {
					projectMap.set(project.encoded_name, { ...project });
				}
			}
		}
		return [...projectMap.values()].sort((a, b) => b.session_count - a.session_count);
	});

	// Stats for StatsGrid
	let stats = $derived<StatItem[]>([
		{
			title: 'Sessions (Sent & Received)',
			value: profile.stats.total_sessions,
			description: '',
			icon: Activity,
			color: 'accent'
		},
		{
			title: 'Projects',
			value: profile.stats.total_projects,
			description: `across ${profile.teams.length} team${profile.teams.length !== 1 ? 's' : ''}`,
			icon: FolderGit2,
			color: 'green'
		},
		{
			title: 'Last Active',
			value: profile.stats.last_active
				? formatRelativeTime(profile.stats.last_active.replace(' ', 'T'))
				: 'Never',
			description: profile.stats.last_active
				? formatDate(profile.stats.last_active.replace(' ', 'T'))
				: '',
			icon: Clock,
			color: 'orange'
		}
	]);

	// Chart data derived from dateTotals
	let chartLabels = $derived([...dateTotals.keys()]);
	let chartSentData = $derived([...dateTotals.values()].map((t) => t.sent));
	let chartReceivedData = $derived([...dateTotals.values()].map((t) => t.received));

	let memberColor = $derived(getTeamMemberHexColor(profile.user_id));

	onMount(() => {
		registerChartDefaults();
	});

	onDestroy(() => {
		chart?.destroy();
	});

	// Create or update chart when canvas is available and data changes
	$effect(() => {
		if (!canvas || dateTotals.size === 0) return;

		const sentColor = memberColor;
		const receivedColor = memberColor + '66';

		if (!chart) {
			const colors = getThemeColors();
			const scaleConfig = createCommonScaleConfig();

			chart = new Chart(canvas, {
				type: 'bar',
				data: {
					labels: chartLabels,
					datasets: [
						{
							label: 'Sent',
							data: chartSentData,
							backgroundColor: sentColor,
							borderRadius: 4
						},
						{
							label: 'Received',
							data: chartReceivedData,
							backgroundColor: receivedColor,
							borderRadius: 4
						}
					]
				},
				options: {
					...createResponsiveConfig(),
					scales: scaleConfig,
					plugins: {
						...createResponsiveConfig().plugins,
						legend: {
							...createResponsiveConfig().plugins.legend,
							position: 'bottom'
						},
						tooltip: {
							...createResponsiveConfig().plugins.tooltip,
							backgroundColor: colors.bgBase,
							titleColor: colors.text,
							bodyColor: colors.textSecondary,
							borderColor: colors.border,
							borderWidth: 1,
							displayColors: true
						}
					}
				}
			});
		} else {
			chart.data.labels = chartLabels;
			chart.data.datasets[0].data = chartSentData;
			chart.data.datasets[0].backgroundColor = sentColor;
			chart.data.datasets[1].data = chartReceivedData;
			chart.data.datasets[1].backgroundColor = receivedColor;
			chart.update();
		}
	});
</script>

<div class="space-y-8">
	<!-- Stats Row -->
	<section>
		<StatsGrid {stats} columns={3} />
		{#if profile.stats.total_sessions === 0}
			<p class="text-xs text-[var(--text-muted)] mt-3 text-center">
				Appears after sync
			</p>
		{/if}
	</section>

	<!-- Sessions Over Time Chart -->
	{#if dateTotals.size > 0}
		<section>
			<div class="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)] p-4">
				<h3 class="text-sm font-medium text-[var(--text-primary)] mb-4">Sessions Over Time</h3>
				<div class="h-[200px]">
					<canvas bind:this={canvas}></canvas>
				</div>
			</div>
		</section>
	{/if}

	<!-- Projects Contributed To -->
	{#if projectList.length > 0}
		<section>
			<h2 class="text-sm font-semibold text-[var(--text-primary)] mb-3 uppercase tracking-wider">
				Projects Contributed To
			</h2>
			<div class="space-y-2">
				{#each projectList as project}
					<a
						href="/projects/{project.encoded_name}"
						class="flex items-center gap-3 p-3 rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)]
							hover:bg-[var(--bg-muted)] transition-colors"
					>
						<FolderGit2 size={16} class="text-[var(--text-muted)] shrink-0" />
						<span class="text-sm text-[var(--text-primary)] flex-1">{project.name}</span>
						<span class="text-xs text-[var(--text-muted)]">
							{project.session_count} session{project.session_count !== 1 ? 's' : ''}
						</span>
					</a>
				{/each}
			</div>
		</section>
	{/if}
</div>
