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
		getThemeColors
	} from '$lib/components/charts/chartConfig';
	import { getTeamMemberHexColor, getUserChartLabel } from '$lib/utils';
	import { API_BASE } from '$lib/config';
	import type { SyncEvent, TeamSessionStat, SyncTeamMember } from '$lib/api-types';
	import TeamActivityFeed from './TeamActivityFeed.svelte';

	// Register Chart.js components
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
		teamName: string;
		activity: SyncEvent[];
		sessionStats: TeamSessionStat[];
		members?: SyncTeamMember[];
		userNames?: Record<string, string>;
	}

	let { teamName, activity, sessionStats, members = [], userNames }: Props = $props();

	// Period selector
	const periods = [
		{ label: '7d', days: 7 },
		{ label: '30d', days: 30 },
		{ label: '90d', days: 90 },
		{ label: 'All', days: 365 }
	];

	let selectedPeriod = $state(30);
	let loadedStats = $state<TeamSessionStat[]>([]);

	let activeStats = $derived(loadedStats.length > 0 ? loadedStats : sessionStats);

	let allMembers = $derived(
		[...new Set(activeStats.map((s) => s.member_name))].sort()
	);

	let visibleMembers = $state(new Set<string>());

	// Initialize visibleMembers when allMembers changes
	$effect(() => {
		if (allMembers.length > 0 && visibleMembers.size === 0) {
			visibleMembers = new Set(allMembers);
		}
	});

	// Fetch session stats when period changes
	async function fetchStats(days: number) {
		try {
			const res = await fetch(
				`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/session-stats?days=${days}`
			);
			if (res.ok) {
				const data = await res.json();
				loadedStats = data.stats ?? [];
				// Reset visible members so the effect re-initializes
				visibleMembers = new Set<string>();
			}
		} catch {
			// Silently fail — keep existing data
		}
	}

	function selectPeriod(days: number) {
		selectedPeriod = days;
		fetchStats(days);
	}

	// Date utilities
	function formatLocalDate(dateKey: string): string {
		const [year, month, day] = dateKey.split('-').map(Number);
		const date = new Date(year, month - 1, day);
		return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
	}

	function fillDateRange(dateKeys: string[]): string[] {
		if (dateKeys.length === 0) return [];

		const sorted = [...dateKeys].sort();
		const result: string[] = [];

		const [minY, minM, minD] = sorted[0].split('-').map(Number);
		const [maxY, maxM, maxD] = sorted[sorted.length - 1].split('-').map(Number);
		let cur = new Date(minY, minM - 1, minD);
		const end = new Date(maxY, maxM - 1, maxD);
		while (cur <= end) {
			const year = cur.getFullYear();
			const month = String(cur.getMonth() + 1).padStart(2, '0');
			const day = String(cur.getDate()).padStart(2, '0');
			result.push(`${year}-${month}-${day}`);
			cur = new Date(cur.getTime() + 86400000);
		}

		return result;
	}

	// Chart data preparation
	let chartInput = $derived.by(() => {
		// Aggregate activeStats into byDateMember (only visible members)
		const byDateMember: Record<string, Record<string, number>> = {};
		const allDateKeys = new Set<string>();

		for (const stat of activeStats) {
			if (!visibleMembers.has(stat.member_name)) continue;
			allDateKeys.add(stat.date);
			if (!byDateMember[stat.date]) byDateMember[stat.date] = {};
			byDateMember[stat.date][stat.member_name] =
				(byDateMember[stat.date][stat.member_name] || 0) + stat.packaged + stat.received;
		}

		const filledDates = fillDateRange([...allDateKeys]);
		const labels = filledDates.map(formatLocalDate);

		const members = [...visibleMembers].sort();
		const datasets = members.map((member) => {
			const hex = getTeamMemberHexColor(member);
			return {
				label: getUserChartLabel(member, userNames),
				data: filledDates.map((d) => byDateMember[d]?.[member] ?? 0),
				borderColor: hex,
				backgroundColor: 'transparent',
				fill: false,
				tension: 0.4,
				pointRadius: 3,
				pointBackgroundColor: hex,
				borderWidth: 2
			};
		});

		return { labels, datasets };
	});

	let canvas: HTMLCanvasElement;
	let chart: Chart | null = null;

	function toggleMember(member: string) {
		const next = new Set(visibleMembers);
		if (next.has(member)) {
			next.delete(member);
		} else {
			next.add(member);
		}
		visibleMembers = next;
	}

	onMount(() => {
		registerChartDefaults();
	});

	onDestroy(() => {
		chart?.destroy();
	});

	// Create or update chart when canvas becomes available and data changes
	$effect(() => {
		if (!canvas) return;
		if (!chart) {
			const colors = getThemeColors();
			chart = new Chart(canvas, {
				type: 'line',
				data: {
					labels: chartInput.labels,
					datasets: chartInput.datasets
				},
				options: {
					...createResponsiveConfig(),
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
							mode: 'index',
							intersect: false
						}
					},
					scales: createCommonScaleConfig()
				}
			});
		} else {
			chart.data.labels = chartInput.labels;
			chart.data.datasets = chartInput.datasets;
			chart.update();
		}
	});
</script>

<div class="space-y-6">
	<!-- Chart section (only shown when there's data) -->
	{#if activeStats.length > 0}
		<div class="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)] p-4">
			<!-- Header with period selector -->
			<div class="flex items-center justify-between mb-4">
				<h3 class="text-sm font-medium text-[var(--text-primary)]">Sessions Over Time</h3>
				<div class="flex items-center gap-1">
					{#each periods as period}
						<button
							class="px-2.5 py-1 text-xs font-medium rounded-full {selectedPeriod === period.days
								? 'bg-[var(--accent)] text-white'
								: 'text-[var(--text-secondary)] hover:bg-[var(--bg-muted)]'}"
							onclick={() => selectPeriod(period.days)}
						>
							{period.label}
						</button>
					{/each}
				</div>
			</div>

			<!-- Chart -->
			<div class="h-[220px]">
				<canvas bind:this={canvas}></canvas>
			</div>

			<!-- Member filter chips -->
			{#if allMembers.length > 0}
				<div class="border-t border-[var(--border)] mt-4 pt-3 flex flex-wrap gap-2">
					{#each allMembers as member}
						{@const hex = getTeamMemberHexColor(member)}
						{@const active = visibleMembers.has(member)}
						<button
							class="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-full border transition-opacity {active
								? 'opacity-100'
								: 'opacity-50 border-[var(--border)] text-[var(--text-muted)]'}"
							style={active ? `border-color: ${hex}; color: ${hex}` : ''}
							onclick={() => toggleMember(member)}
						>
							<span
								class="w-2 h-2 rounded-full shrink-0"
								style="background-color: {hex}"
							></span>
							{getUserChartLabel(member, userNames)}
						</button>
					{/each}
				</div>
			{/if}
		</div>
	{/if}

	<!-- Activity feed -->
	<TeamActivityFeed events={activity} {teamName} {members} />
</div>
