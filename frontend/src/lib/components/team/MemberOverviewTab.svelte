<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import {
		Chart,
		LineController,
		LineElement,
		PointElement,
		Filler,
		LinearScale,
		CategoryScale,
		Tooltip
	} from 'chart.js';
	import { FolderGit2, ArrowUp, ArrowDown, Clock, ChevronRight } from 'lucide-svelte';
	import type { MemberProfile } from '$lib/api-types';
	import {
		registerChartDefaults,
		createResponsiveConfig,
		createCommonScaleConfig,
		getThemeColors,
		onThemeChange
	} from '$lib/components/charts/chartConfig';
	import { formatRelativeTime } from '$lib/utils';
	import { formatSyncEvent } from '$lib/utils/sync-events';

	Chart.register(LineController, LineElement, PointElement, Filler, LinearScale, CategoryScale, Tooltip);

	interface Props {
		profile: MemberProfile;
	}

	let { profile }: Props = $props();

	let canvas = $state<HTMLCanvasElement | null>(null);
	let chart: Chart | null = null;

	// Resolved at mount from CSS custom properties set by parent page
	let memberColor = $state('#7c3aed');
	let receivedColor = $state('#3b82f6');

	// Split sent vs received by date
	let dateSplit = $derived.by(() => {
		const sent = new Map<string, number>();
		const received = new Map<string, number>();
		for (const stat of profile.session_stats) {
			sent.set(stat.date, (sent.get(stat.date) ?? 0) + stat.packaged);
			received.set(stat.date, (received.get(stat.date) ?? 0) + stat.received);
		}
		const allDates = [...new Set([...sent.keys(), ...received.keys()])].sort();
		return {
			labels: allDates,
			sent: allDates.map((d) => sent.get(d) ?? 0),
			received: allDates.map((d) => received.get(d) ?? 0)
		};
	});

	let hasChartData = $derived(dateSplit.labels.length > 0);

	// Flatten and deduplicate projects, sorted by session_count descending
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

	let maxProjectSessions = $derived(
		projectList.length > 0 ? Math.max(...projectList.map((p) => p.session_count)) : 1
	);

	// Recent activity — first 5 events
	let recentActivity = $derived(profile.activity.slice(0, 5));

	let themeVersion = $state(0);
	let cleanupTheme: (() => void) | null = null;

	onMount(() => {
		registerChartDefaults();
		// Resolve CSS custom properties from parent scope
		const el = canvas?.closest('[style*="--member-color"]') ?? document.documentElement;
		const styles = getComputedStyle(el);
		const mc = styles.getPropertyValue('--member-color').trim();
		const ic = styles.getPropertyValue('--info').trim();
		if (mc) memberColor = mc;
		if (ic) receivedColor = ic;
		cleanupTheme = onThemeChange(() => {
			chart?.destroy();
			chart = null;
			registerChartDefaults();
			// Re-resolve theme-dependent color
			const ic = getComputedStyle(document.documentElement).getPropertyValue('--info').trim();
			if (ic) receivedColor = ic;
			themeVersion++;
		});
	});

	onDestroy(() => {
		cleanupTheme?.();
		chart?.destroy();
	});

	$effect(() => {
		void themeVersion; // re-run on theme change
		if (!canvas || !hasChartData) return;

		const colors = getThemeColors();
		const scaleConfig = createCommonScaleConfig();

		if (!chart) {
			chart = new Chart(canvas, {
				type: 'line',
				data: {
					labels: dateSplit.labels,
					datasets: [
						{
							label: 'Sent',
							data: dateSplit.sent,
							borderColor: memberColor,
							backgroundColor: memberColor + '18',
							fill: true,
							tension: 0.3,
							pointRadius: 3,
							pointHoverRadius: 5,
							pointBackgroundColor: memberColor,
							borderWidth: 2
						},
						{
							label: 'Received',
							data: dateSplit.received,
							borderColor: receivedColor,
							backgroundColor: receivedColor + '10',
							fill: true,
							tension: 0.3,
							pointRadius: 2,
							pointHoverRadius: 4,
							pointBackgroundColor: receivedColor,
							borderWidth: 1.5,
							borderDash: [4, 3]
						}
					]
				},
				options: {
					...createResponsiveConfig(),
					scales: scaleConfig,
					plugins: {
						...createResponsiveConfig().plugins,
						legend: {
							display: true,
							position: 'top',
							align: 'end',
							labels: {
								boxWidth: 12,
								boxHeight: 2,
								padding: 16,
								usePointStyle: false,
								font: { size: 11 },
								color: colors.textSecondary
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
			chart.data.labels = dateSplit.labels;
			chart.data.datasets[0].data = dateSplit.sent;
			chart.data.datasets[1].data = dateSplit.received;
			(chart.data.datasets[0] as any).borderColor = memberColor;
			(chart.data.datasets[0] as any).backgroundColor = memberColor + '18';
			(chart.data.datasets[0] as any).pointBackgroundColor = memberColor;
			(chart.data.datasets[1] as any).borderColor = receivedColor;
			(chart.data.datasets[1] as any).backgroundColor = receivedColor + '10';
			(chart.data.datasets[1] as any).pointBackgroundColor = receivedColor;
			chart.update();
		}
	});
</script>

<div class="space-y-6">

	<!-- ── 1. Sent vs Received Chart ──────────────────────────────────── -->
	{#if hasChartData}
		<section class="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)] p-4">
			<div class="flex items-center justify-between mb-4">
				<h3 class="text-sm font-medium text-[var(--text-primary)]">Session Activity</h3>
				<div class="flex items-center gap-4 text-xs text-[var(--text-muted)]">
					<span class="flex items-center gap-1.5">
						<ArrowUp size={11} class="text-[var(--member-color)]" />
						<strong class="text-[var(--text-primary)]">{profile.stats.sessions_sent}</strong> sent
					</span>
					<span class="flex items-center gap-1.5">
						<ArrowDown size={11} class="text-[var(--info)]" />
						<strong class="text-[var(--text-primary)]">{profile.stats.sessions_received}</strong> received
					</span>
				</div>
			</div>
			<div class="h-[200px]">
				<canvas bind:this={canvas}></canvas>
			</div>
		</section>
	{:else}
		<section class="rounded-lg border border-dashed border-[var(--border)] bg-[var(--bg-subtle)] p-8 text-center">
			<p class="text-sm text-[var(--text-muted)]">No session activity data yet</p>
		</section>
	{/if}

	<!-- ── 2. Project Contributions (proportional bars) ───────────────── -->
	{#if projectList.length > 0}
		<section>
			<h2 class="text-xs font-semibold text-[var(--text-muted)] mb-3 uppercase tracking-wider">
				Projects
			</h2>
			<div class="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)] divide-y divide-[var(--border-subtle)]">
				{#each projectList as project, i (project.encoded_name)}
					{@const pct = maxProjectSessions > 0 ? (project.session_count / maxProjectSessions) * 100 : 0}
					<a
						href="/projects/{project.encoded_name}"
						class="flex items-center gap-3 px-4 py-3 hover:bg-[var(--member-color-wash)] transition-colors group relative overflow-hidden"
					>
						<!-- Proportional background bar -->
						<div
							class="absolute inset-y-0 left-0 bg-[var(--member-color)] opacity-[0.04] transition-all"
							style="width: {pct}%;"
						></div>

						<!-- Rank indicator -->
						<span class="text-xs font-mono text-[var(--text-faint)] w-5 text-right shrink-0 relative z-10">
							{i + 1}
						</span>

						<FolderGit2 size={14} class="text-[var(--member-color)] shrink-0 relative z-10 opacity-60" />

						<span class="text-sm text-[var(--text-primary)] flex-1 truncate relative z-10 group-hover:text-[var(--member-color)] transition-colors">
							{project.name}
						</span>

						<!-- Session count + mini bar -->
						<div class="flex items-center gap-2.5 shrink-0 relative z-10">
							<div class="w-16 h-1.5 rounded-full bg-[var(--bg-muted)] overflow-hidden hidden sm:block">
								<div
									class="h-full rounded-full bg-[var(--member-color)] transition-all"
									style="width: {pct}%;"
								></div>
							</div>
							<span class="text-xs font-medium tabular-nums text-[var(--text-secondary)] min-w-[3ch] text-right">
								{project.session_count}
							</span>
						</div>
					</a>
				{/each}
			</div>
		</section>
	{/if}

	<!-- ── 3. Recent Activity (mini feed) ─────────────────────────────── -->
	{#if recentActivity.length > 0}
		<section>
			<div class="flex items-center justify-between mb-3">
				<h2 class="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
					Recent Activity
				</h2>
				{#if profile.activity.length > 5}
					<a
						href="?tab=activity"
						class="text-xs text-[var(--member-color)] hover:underline flex items-center gap-0.5"
					>
						View all
						<ChevronRight size={12} />
					</a>
				{/if}
			</div>
			<div class="rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)] divide-y divide-[var(--border-subtle)]">
				{#each recentActivity as event (event.id)}
					<div class="flex items-center justify-between gap-3 px-4 py-2.5">
						<p class="text-xs text-[var(--text-secondary)] truncate flex-1">
							{formatSyncEvent(event)}
						</p>
						<span class="text-[11px] text-[var(--text-faint)] shrink-0 whitespace-nowrap flex items-center gap-1">
							<Clock size={10} />
							{formatRelativeTime(event.created_at)}
						</span>
					</div>
				{/each}
			</div>
		</section>
	{/if}

</div>
