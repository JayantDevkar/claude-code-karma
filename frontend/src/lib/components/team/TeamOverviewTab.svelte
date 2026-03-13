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
	import { Users, FolderSync, ArrowUpDown, AlertTriangle, Loader2 } from 'lucide-svelte';
	import type {
		SyncTeam,
		SyncProjectStatus,
		TeamSessionStat,
		StatItem
	} from '$lib/api-types';
	import JoinCodeCard from './JoinCodeCard.svelte';
	import StatsGrid from '$lib/components/StatsGrid.svelte';
	import {
		registerChartDefaults,
		createResponsiveConfig,
		createCommonScaleConfig,
		getThemeColors,
		onThemeChange
	} from '$lib/components/charts/chartConfig';
	import { getTeamMemberHexColor } from '$lib/utils';

	// Register Chart.js components
	Chart.register(BarController, BarElement, LinearScale, CategoryScale, Tooltip, Legend);

	interface Props {
		team: SyncTeam;
		teamName: string;
		joinCode: string | null;
		projectStatuses: SyncProjectStatus[];
		sessionStats: TeamSessionStat[];
		userNames?: Record<string, string>;
		onleave: () => void;
		deleteConfirm: boolean;
		deleting: boolean;
		deleteError: string | null;
		ondeleteconfirm: (v: boolean) => void;
		ondeleteerror: (v: string | null) => void;
	}

	let {
		team,
		teamName,
		joinCode,
		projectStatuses,
		sessionStats,
		userNames,
		onleave,
		deleteConfirm,
		deleting,
		deleteError,
		ondeleteconfirm,
		ondeleteerror
	}: Props = $props();

	let canvas = $state<HTMLCanvasElement>(undefined!);
	let chart: Chart | null = null;

	// Derived state
	let members = $derived(team.members ?? []);
	let projects = $derived(team.projects ?? []);
	let onlineCount = $derived(members.filter((m) => m.connected).length);
	let totalUnsyncedSessions = $derived(projectStatuses.reduce((sum, p) => sum + (p.gap ?? 0), 0));

	// Aggregate session stats by member: out = what they contributed
	let memberTotals = $derived.by(() => {
		const totals = new Map<string, number>();
		for (const stat of sessionStats) {
			const existing = totals.get(stat.member_name) ?? 0;
			totals.set(stat.member_name, existing + stat.packaged + stat.received);
		}
		return totals;
	});

	let totalSessions = $derived(
		[...memberTotals.values()].reduce((sum, t) => sum + t, 0)
	);

	// Stats for StatsGrid
	let stats = $derived<StatItem[]>([
		{
			title: 'Members (Online)',
			value: `${onlineCount}/${members.length}`,
			description: '',
			icon: Users,
			color: 'green'
		},
		{
			title: 'Unsynced Sessions',
			value: totalUnsyncedSessions,
			description: `across ${projects.length} project${projects.length !== 1 ? 's' : ''}`,
			icon: FolderSync,
			color: totalUnsyncedSessions === 0 ? 'green' : 'orange'
		},
		{
			title: 'Sessions Shared',
			value: totalSessions,
			description: `across ${members.length} member${members.length !== 1 ? 's' : ''}`,
			icon: ArrowUpDown,
			color: 'accent'
		}
	]);

	// Chart data: sessions contributed per member
	let chartMemberIds = $derived([...memberTotals.keys()]);
	let chartLabels = $derived(
		chartMemberIds.map((name) => userNames?.[name] ?? name)
	);
	let chartOutData = $derived(chartMemberIds.map((id) => memberTotals.get(id) ?? 0));

	let themeVersion = $state(0);
	let cleanupTheme: (() => void) | null = null;

	onMount(() => {
		registerChartDefaults();
		cleanupTheme = onThemeChange(() => {
			chart?.destroy();
			chart = null;
			registerChartDefaults();
			themeVersion++;
		});
	});

	onDestroy(() => {
		cleanupTheme?.();
		chart?.destroy();
	});

	// Create or update chart when canvas is available and data changes
	$effect(() => {
		void themeVersion; // re-run on theme change
		if (!canvas || memberTotals.size === 0) return;

		const barColors = chartMemberIds.map((id) => getTeamMemberHexColor(id));

		if (!chart) {
			const colors = getThemeColors();
			const scaleConfig = createCommonScaleConfig();

			chart = new Chart(canvas, {
				type: 'bar',
				data: {
					labels: chartLabels,
					datasets: [
						{
							label: 'Contributed',
							data: chartOutData,
							backgroundColor: barColors,
							borderRadius: 4
						}
					]
				},
				options: {
					...createResponsiveConfig(),
					scales: {
						...scaleConfig,
						x: {
							...scaleConfig.x,
							ticks: {
								...scaleConfig.x.ticks,
								maxRotation: 45,
								minRotation: 0
							}
						}
					},
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
					}
				}
			});
		} else {
			chart.data.labels = chartLabels;
			chart.data.datasets[0].data = chartOutData;
			chart.data.datasets[0].backgroundColor = barColors;
			chart.update();
		}
	});
</script>

<div class="space-y-8">
	<!-- Join Code -->
	{#if joinCode}
		<section>
			<JoinCodeCard code={joinCode} />
		</section>
	{/if}

	<!-- Stats Row -->
	<section>
		<StatsGrid {stats} columns={3} />
	</section>

	<!-- Sessions by Member Chart -->
	{#if memberTotals.size > 0}
		<section>
			<div class="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)] p-4">
				<h3 class="text-sm font-medium text-[var(--text-primary)] mb-4">Sessions Contributed</h3>
				<div class="h-[200px]">
					<canvas bind:this={canvas}></canvas>
				</div>
			</div>
		</section>
	{/if}

	<!-- Danger Zone (bottom, collapsible) -->
	<section class="mt-12">
		<details class="group" ontoggle={(e: Event) => { if (!(e.currentTarget as HTMLDetailsElement).open) { ondeleteconfirm(false); ondeleteerror(null); } }}>
			<summary class="flex items-center gap-2 cursor-pointer select-none text-xs text-[var(--text-muted)] hover:text-[var(--text-secondary)] transition-colors py-2">
				<span class="w-full border-t border-[var(--border)]/40"></span>
				<span class="shrink-0 flex items-center gap-1.5 uppercase tracking-wider font-medium">
					<AlertTriangle size={11} />
					Danger Zone
				</span>
				<span class="w-full border-t border-[var(--border)]/40"></span>
			</summary>
			<div class="pt-4">
				{#if deleteConfirm}
					<div class="space-y-2">
						<div class="flex items-center gap-3 p-4 rounded-lg border border-[var(--error)]/20 bg-[var(--error)]/5">
							<AlertTriangle size={16} class="text-[var(--error)] shrink-0" />
							<p class="text-sm text-[var(--text-primary)] flex-1">
								Leave team "{teamName}"? This will stop syncing with all members and clean up Syncthing folders.
							</p>
							<div class="flex items-center gap-2 shrink-0">
								<button
									onclick={onleave}
									disabled={deleting}
									class="px-3 py-1.5 text-xs font-medium rounded bg-[var(--error)] text-white hover:bg-[var(--error)]/80 transition-colors disabled:opacity-50"
								>
									{#if deleting}
										<Loader2 size={12} class="animate-spin" />
									{:else}
										Leave
									{/if}
								</button>
								<button
									onclick={() => { ondeleteconfirm(false); ondeleteerror(null); }}
									class="px-3 py-1.5 text-xs rounded text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition-colors"
								>
									Cancel
								</button>
							</div>
						</div>
						{#if deleteError}
							<p class="text-xs text-[var(--error)]" aria-live="polite">{deleteError}</p>
						{/if}
					</div>
				{:else}
					<button
						onclick={() => ondeleteconfirm(true)}
						class="px-4 py-2 text-sm font-medium rounded-[var(--radius-md)] border border-[var(--border)]
							text-[var(--text-muted)] hover:text-[var(--error)] hover:border-[var(--error)]/30 hover:bg-[var(--error)]/5 transition-colors"
					>
						Leave Team
					</button>
				{/if}
			</div>
		</details>
	</section>
</div>
