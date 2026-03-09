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
		getThemeColors
	} from '$lib/components/charts/chartConfig';
	import { getTeamMemberHexColor, getUserChartLabel } from '$lib/utils';

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

	let canvas: HTMLCanvasElement;
	let chart: Chart | null = null;

	// Derived state
	let members = $derived(team.members ?? []);
	let projects = $derived(team.projects ?? []);
	let onlineCount = $derived(members.filter((m) => m.connected).length);
	let inSyncCount = $derived(projectStatuses.filter((p) => p.gap === 0).length);

	// Aggregate session stats by member
	let memberTotals = $derived.by(() => {
		const totals = new Map<string, { sent: number; received: number }>();
		for (const stat of sessionStats) {
			const existing = totals.get(stat.member_name) ?? { sent: 0, received: 0 };
			existing.sent += stat.packaged;
			existing.received += stat.received;
			totals.set(stat.member_name, existing);
		}
		return totals;
	});

	let totalSent = $derived(
		[...memberTotals.values()].reduce((sum, t) => sum + t.sent, 0)
	);
	let totalReceived = $derived(
		[...memberTotals.values()].reduce((sum, t) => sum + t.received, 0)
	);

	// Stats for StatsGrid
	let stats = $derived<StatItem[]>([
		{
			title: 'Members',
			value: `${onlineCount}/${members.length}`,
			description: 'online',
			icon: Users,
			color: 'green'
		},
		{
			title: 'Projects',
			value: `${inSyncCount}/${projects.length}`,
			description: 'in sync',
			icon: FolderSync,
			color: 'blue'
		},
		{
			title: 'Sessions Shared',
			value: totalSent + totalReceived,
			description: `${totalSent} sent / ${totalReceived} received`,
			icon: ArrowUpDown,
			color: 'accent'
		}
	]);

	// Chart data derived from memberTotals
	let chartLabels = $derived(
		[...memberTotals.keys()].map((name) => getUserChartLabel(name, userNames))
	);
	let chartMemberIds = $derived([...memberTotals.keys()]);
	let chartSentData = $derived(
		[...memberTotals.values()].map((t) => t.sent)
	);
	let chartReceivedData = $derived(
		[...memberTotals.values()].map((t) => t.received)
	);

	onMount(() => {
		if (memberTotals.size === 0) return;

		registerChartDefaults();
		const colors = getThemeColors();
		const scaleConfig = createCommonScaleConfig();

		const sentColors = chartMemberIds.map((id) => getTeamMemberHexColor(id));
		const receivedColors = chartMemberIds.map((id) => {
			const hex = getTeamMemberHexColor(id);
			return hex + '66'; // 40% opacity for lighter variant
		});

		chart = new Chart(canvas, {
			type: 'bar',
			data: {
				labels: chartLabels,
				datasets: [
					{
						label: 'Sent',
						data: chartSentData,
						backgroundColor: sentColors,
						borderRadius: 4
					},
					{
						label: 'Received',
						data: chartReceivedData,
						backgroundColor: receivedColors,
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
	});

	onDestroy(() => {
		chart?.destroy();
	});

	// Update chart when data changes
	$effect(() => {
		if (chart && memberTotals.size > 0) {
			const sentColors = chartMemberIds.map((id) => getTeamMemberHexColor(id));
			const receivedColors = chartMemberIds.map((id) => {
				const hex = getTeamMemberHexColor(id);
				return hex + '66';
			});

			chart.data.labels = chartLabels;
			chart.data.datasets[0].data = chartSentData;
			chart.data.datasets[0].backgroundColor = sentColors;
			chart.data.datasets[1].data = chartReceivedData;
			chart.data.datasets[1].backgroundColor = receivedColors;
			chart.update();
		}
	});
</script>

<div class="space-y-8">
	<!-- Join Code -->
	{#if joinCode}
		<section>
			<h2 class="text-sm font-semibold text-[var(--text-primary)] mb-3 uppercase tracking-wider">
				Join Code
			</h2>
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
				<h3 class="text-sm font-medium text-[var(--text-primary)] mb-4">Sessions by Member</h3>
				<div class="h-[200px]">
					<canvas bind:this={canvas}></canvas>
				</div>
			</div>
		</section>
	{/if}

	<!-- Danger Zone -->
	<section class="pt-4 border-t border-[var(--border)]">
		<h2 class="text-sm font-semibold text-[var(--error)] mb-3 uppercase tracking-wider">
			Danger Zone
		</h2>
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
				class="px-4 py-2 text-sm font-medium rounded-[var(--radius-md)] border border-[var(--error)]/30
					text-[var(--error)] hover:bg-[var(--error)]/10 transition-colors"
			>
				Leave Team
			</button>
		{/if}
	</section>
</div>
