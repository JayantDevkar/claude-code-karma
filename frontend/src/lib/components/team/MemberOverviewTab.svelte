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
	import { FolderGit2 } from 'lucide-svelte';
	import type { MemberProfile } from '$lib/api-types';
	import {
		registerChartDefaults,
		createResponsiveConfig,
		createCommonScaleConfig,
		getThemeColors
	} from '$lib/components/charts/chartConfig';
	import { getTeamMemberHexColor } from '$lib/utils';

	// Register Chart.js components
	Chart.register(BarController, BarElement, LinearScale, CategoryScale, Tooltip, Legend);

	interface Props {
		profile: MemberProfile;
	}

	let { profile }: Props = $props();

	let canvas: HTMLCanvasElement;
	let chart: Chart | null = null;

	// Build incoming lookup: date → count
	let incomingByDate = $derived.by(() => {
		const map = new Map<string, number>();
		for (const stat of profile.incoming_stats ?? []) {
			map.set(stat.date, (map.get(stat.date) ?? 0) + stat.incoming);
		}
		return map;
	});

	// Aggregate session stats by date: out (this member) + in (from others)
	let dateTotals = $derived.by(() => {
		// Collect all dates from both sources
		const allDates = new Set<string>();
		for (const stat of profile.session_stats) allDates.add(stat.date);
		for (const stat of profile.incoming_stats ?? []) allDates.add(stat.date);

		const totals = new Map<string, { out: number; in: number }>();
		for (const date of allDates) {
			totals.set(date, { out: 0, in: incomingByDate.get(date) ?? 0 });
		}
		for (const stat of profile.session_stats) {
			const existing = totals.get(stat.date)!;
			existing.out += stat.packaged + stat.received;
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

	// Chart data derived from dateTotals
	let chartLabels = $derived([...dateTotals.keys()]);
	let chartOutData = $derived([...dateTotals.values()].map((t) => t.out));
	let chartInData = $derived([...dateTotals.values()].map((t) => t.in));

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

		if (!chart) {
			const colors = getThemeColors();
			const scaleConfig = createCommonScaleConfig();

			chart = new Chart(canvas, {
				type: 'bar',
				data: {
					labels: chartLabels,
					datasets: [
						{
							label: 'Out',
							data: chartOutData,
							backgroundColor: memberColor,
							borderRadius: 4
						},
						{
							label: 'In',
							data: chartInData,
							backgroundColor: memberColor + '30',
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
							position: 'bottom',
							labels: {
								boxWidth: 12,
								padding: 16,
								font: { size: 11 }
							}
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
			chart.data.datasets[0].data = chartOutData;
			chart.data.datasets[0].backgroundColor = memberColor;
			chart.data.datasets[1].data = chartInData;
			chart.data.datasets[1].backgroundColor = memberColor + '30';
			chart.update();
		}
	});
</script>

<div class="space-y-6">
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
