<script lang="ts">
	import { onMount } from 'svelte';
	import { browser } from '$app/environment';
	import { Activity, Zap, Database, Cpu, FolderOpen, Clock, BarChart3 } from 'lucide-svelte';
	import { goto } from '$app/navigation';
	import { page, navigating } from '$app/stores';
	import SkeletonBox from '$lib/components/skeleton/SkeletonBox.svelte';
	import SkeletonText from '$lib/components/skeleton/SkeletonText.svelte';
	import SkeletonStatsCard from '$lib/components/skeleton/SkeletonStatsCard.svelte';
	import { getChartColorPalette } from '$lib/components/charts/chartConfig';
	import TimeFilterDropdown from '$lib/components/TimeFilterDropdown.svelte';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import StatsGrid from '$lib/components/StatsGrid.svelte';
	import CollapsibleGroup from '$lib/components/ui/CollapsibleGroup.svelte';
	import type { AnalyticsFilterPeriod, StatItem } from '$lib/api-types';
	import {
		analyticsFilterOptions,
		getTimestampRangeForFilter,
		isHourBasedFilter,
		getAnalyticsFilterLabel,
		getUserChartColor,
		getUserChartLabel
	} from '$lib/utils';

	// Read filter directly from URL
	let selectedFilter = $derived.by((): AnalyticsFilterPeriod => {
		const filterParam = $page.url.searchParams.get('filter');
		if (filterParam && analyticsFilterOptions.some((o) => o.id === filterParam)) {
			return filterParam as AnalyticsFilterPeriod;
		}
		return 'all';
	});

	const handleFilterChange = (filter: AnalyticsFilterPeriod) => {
		const url = new URL($page.url);
		const range = getTimestampRangeForFilter(filter);

		// Always include timezone offset for accurate local date grouping
		if (browser) {
			url.searchParams.set('tz_offset', new Date().getTimezoneOffset().toString());
		}

		if (filter === 'all') {
			url.searchParams.delete('filter');
			url.searchParams.delete('start_ts');
			url.searchParams.delete('end_ts');
		} else {
			url.searchParams.set('filter', filter);
			if (range) {
				url.searchParams.set('start_ts', range.start.toString());
				url.searchParams.set('end_ts', range.end.toString());
			}
		}

		if (browser) {
			window.location.href = url.toString();
		} else {
			goto(url.toString(), { keepFocus: true });
		}
	};

	interface Analytics {
		total_sessions: number;
		total_tokens: number;
		total_input_tokens: number;
		total_output_tokens: number;
		total_duration_seconds: number;
		estimated_cost_usd: number;
		models_used: Record<string, number>;
		cache_hit_rate: number;
		tools_used: Record<string, number>;
		sessions_by_date: Record<string, number>;
		sessions_by_date_by_user?: Record<string, Record<string, number>>;
		user_names?: Record<string, string>;
		projects_active: number;
		temporal_heatmap: number[][];
		peak_hours: number[];
		models_categorized: Record<string, number>;
		time_distribution: {
			morning_pct: number;
			afternoon_pct: number;
			evening_pct: number;
			night_pct: number;
			dominant_period: string;
		};
	}

	let { data } = $props();

	// Default analytics object to prevent SSR errors when data is undefined
	const defaultAnalytics: Analytics = {
		total_sessions: 0,
		total_tokens: 0,
		total_input_tokens: 0,
		total_output_tokens: 0,
		total_duration_seconds: 0,
		estimated_cost_usd: 0,
		models_used: {},
		cache_hit_rate: 0,
		tools_used: {},
		sessions_by_date: {},
		projects_active: 0,
		temporal_heatmap: [],
		peak_hours: [],
		models_categorized: {},
		time_distribution: {
			morning_pct: 0,
			afternoon_pct: 0,
			evening_pct: 0,
			night_pct: 0,
			dominant_period: ''
		}
	};

	// Merge actual data with defaults to ensure all properties exist
	let analytics = $derived.by(() => {
		const rawAnalytics = data.analytics as unknown as Analytics | undefined;
		if (!rawAnalytics) return defaultAnalytics;

		return {
			...defaultAnalytics,
			...rawAnalytics,
			time_distribution: {
				...defaultAnalytics.time_distribution,
				...(rawAnalytics.time_distribution ?? {})
			}
		};
	});

	let hasMultiUser = $derived(
		!!analytics.sessions_by_date_by_user &&
		Object.keys(analytics.sessions_by_date_by_user).length > 1
	);

	// --- Helpers ---
	const formatK = (n: number) => {
		if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
		if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
		return n.toString();
	};

	const formatCurrency = (n: number) =>
		new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n);

	// --- Date Processing ---
	let sortedDates = $derived(Object.keys(analytics.sessions_by_date).sort());

	// Stats - context-aware based on filter
	let last30Days = $derived(sortedDates.slice(-30));

	// For hour-based filters, show sessions per hour; for day-based, show per day
	let avgDisplay = $derived.by(() => {
		const numDays = sortedDates.length;
		const totalSessions = analytics.total_sessions;

		if (numDays === 0 || totalSessions === 0) {
			return { value: '0', unit: '/day' };
		}

		// For single-day (hour-based) filters, calculate per-hour rate
		if (isHourBasedFilter(selectedFilter)) {
			const hours = parseInt(selectedFilter) || 6;
			const perHour = (totalSessions / hours).toFixed(1);
			return { value: perHour, unit: '/hour' };
		}

		// For multi-day filters, show per-day average
		const perDay = (totalSessions / numDays).toFixed(1);
		return { value: perDay, unit: '/day' };
	});

	// Legacy movingAvg for backward compatibility
	let movingAvg = $derived(
		last30Days.length > 0
			? (
					last30Days.reduce((sum, d) => sum + (analytics.sessions_by_date[d] || 0), 0) /
					last30Days.length
				).toFixed(1)
			: '0'
	);

	let tokensPerSession = $derived(
		analytics.total_sessions > 0
			? Math.round(analytics.total_tokens / analytics.total_sessions)
			: 0
	);

	// Sparkline
	let sparklineData = $derived(
		sortedDates.slice(-14).map((d) => analytics.sessions_by_date[d] || 0)
	);
	let sparkMax = $derived(Math.max(...sparklineData, 1));

	// --- Model Distribution ---
	// Use models_categorized if it has data, otherwise fall back to models_used
	let modelsData = $derived(() => {
		const categorized = analytics.models_categorized;
		const used = analytics.models_used;
		// Check for non-empty objects (empty {} is truthy but has no keys)
		if (categorized && Object.keys(categorized).length > 0) return categorized;
		if (used && Object.keys(used).length > 0) return used;
		return {};
	});

	let modelDist = $derived(
		Object.entries(modelsData())
			.filter(([_, count]) => count > 0)
			.sort((a, b) => b[1] - a[1])
			.map(([name, count]) => {
				const total = Object.values(modelsData()).reduce((a, b) => a + b, 0);
				return { name, count, perc: total > 0 ? (count / total) * 100 : 0 };
			})
			.filter((m) => m.perc >= 2)
	); // Hide <2%

	const getModelColor = (name: string) => {
		const lower = name.toLowerCase();
		if (lower.includes('opus')) return 'var(--model-opus)';
		if (lower.includes('sonnet')) return 'var(--model-sonnet)';
		if (lower.includes('haiku')) return 'var(--model-haiku)';
		return '#14b8a6'; // Teal for 'Other' models
	};

	// --- Cache ---
	let cacheHitPercent = $derived((analytics.cache_hit_rate * 100).toFixed(1));

	// --- Cost ---
	let costPerSession = $derived(
		analytics.total_sessions ? analytics.estimated_cost_usd / analytics.total_sessions : 0
	);

	// Format peak hours array (e.g., [9, 10, 11]) to readable range "9am-12pm"
	const formatPeakHours = (hours: number[]) => {
		if (!hours || hours.length === 0) return '—';
		const sorted = [...hours].sort((a, b) => a - b);
		const start = sorted[0];
		const end = sorted[sorted.length - 1] + 1; // +1 because it's the *end* of the hour
		const formatHour = (h: number) => {
			const hour12 = h % 12 || 12;
			const ampm = h < 12 ? 'am' : 'pm';
			return `${hour12}${ampm}`;
		};
		return `${formatHour(start)}–${formatHour(end % 24)}`;
	};

	// Calculate absolute hours from percentage based on total duration
	const formatHoursFromPct = (pct: number) => {
		const totalHours = analytics.total_duration_seconds / 3600;
		const hours = (pct / 100) * totalHours;
		return hours >= 1 ? `${hours.toFixed(0)}h` : `${(hours * 60).toFixed(0)}m`;
	};

	// Format date string (YYYY-MM-DD) without timezone shift
	// Using T12:00:00 to avoid day boundary issues in any timezone
	const formatDateLabel = (dateStr: string): string => {
		const d = new Date(dateStr + 'T12:00:00');
		return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
	};

	// --- Hero Stats ---
	let stats = $derived<StatItem[]>([
		{
			title: 'Total Sessions',
			value: analytics.total_sessions.toLocaleString(),
			icon: Activity,
			color: 'purple'
		},
		{
			title: 'Total Cost',
			value: formatCurrency(analytics.estimated_cost_usd),
			icon: Zap,
			color: 'green'
		},
		{
			title: 'Cache Hit Rate',
			value: `${cacheHitPercent}%`,
			icon: Database,
			color: 'blue'
		}
	]);

	let isPageLoading = $derived(!!$navigating && $navigating.to?.route.id === '/analytics');

	// --- Collapsible Group State ---
	const groupKeys = ['velocity', 'efficiency', 'rhythm'] as const;
	let expandedGroups = $state<Set<string>>(new Set(groupKeys));

	function toggleGroup(key: string) {
		if (expandedGroups.has(key)) {
			expandedGroups.delete(key);
		} else {
			expandedGroups.add(key);
		}
		expandedGroups = new Set(expandedGroups);
	}

	// Chart
	let chartCanvas: HTMLCanvasElement;
	let chartInstance = $state<any>(null);

	$effect(() => {
		if (chartInstance && sortedDates) {
			const newLabels = sortedDates.map((date) => formatDateLabel(date));
			chartInstance.data.labels = newLabels;

			if (hasMultiUser && analytics.sessions_by_date_by_user) {
				const userIds = Object.keys(analytics.sessions_by_date_by_user);
				const sorted = userIds.filter(id => id !== '_local').sort();
				if (userIds.includes('_local')) sorted.unshift('_local');

				// Update each dataset's data
				sorted.forEach((userId, i) => {
					if (chartInstance.data.datasets[i]) {
						chartInstance.data.datasets[i].data = sortedDates.map(
							date => analytics.sessions_by_date_by_user![userId]?.[date] ?? 0
						);
					}
				});
			} else {
				const newCounts = sortedDates.map((date) => analytics.sessions_by_date[date]);
				chartInstance.data.datasets[0].data = newCounts;
			}
			chartInstance.update();
		}
	});

	onMount(async () => {
		const Chart = (await import('chart.js/auto')).default;
		const colors = getChartColorPalette();
		const style = getComputedStyle(document.documentElement);
		const textMuted = style.getPropertyValue('--text-muted').trim() || '#94a3b8';
		const textPrimary = style.getPropertyValue('--text-primary').trim() || '#0f172a';
		const border = style.getPropertyValue('--border').trim() || 'rgba(0,0,0,0.08)';

		const labels = sortedDates.map((date) => formatDateLabel(date));

		if (hasMultiUser) {
			// Build sorted user list: _local first, then remotes alphabetically
			const userIds = Object.keys(analytics.sessions_by_date_by_user!);
			const sorted = userIds.filter(id => id !== '_local').sort();
			if (userIds.includes('_local')) sorted.unshift('_local');

			const datasets = sorted.map(userId => ({
				label: getUserChartLabel(userId, analytics.user_names),
				data: sortedDates.map(date => analytics.sessions_by_date_by_user![userId]?.[date] ?? 0),
				backgroundColor: getUserChartColor(userId),
				hoverBackgroundColor: getUserChartColor(userId),
				borderRadius: 3,
				barThickness: 'flex' as const,
				maxBarThickness: 14
			}));

			chartInstance = new Chart(chartCanvas, {
				type: 'bar',
				data: { labels, datasets },
				options: {
					responsive: true,
					maintainAspectRatio: false,
					plugins: {
						legend: {
							display: true,
							position: 'top',
							align: 'end',
							labels: {
								boxWidth: 8,
								boxHeight: 8,
								usePointStyle: true,
								pointStyle: 'circle',
								font: { size: 10 },
								color: textMuted,
								padding: 12
							}
						},
						tooltip: {
							backgroundColor: textPrimary,
							padding: 10,
							cornerRadius: 6,
							mode: 'index'
						}
					},
					scales: {
						y: {
							beginAtZero: true,
							stacked: true,
							grid: { color: border },
							ticks: { display: false }
						},
						x: {
							stacked: true,
							grid: { display: false },
							ticks: {
								font: { size: 10 },
								color: textMuted,
								maxTicksLimit: 8,
								maxRotation: 0
							}
						}
					}
				}
			});
		} else {
			// Original single-dataset behavior
			const sessionCounts = sortedDates.map((date) => analytics.sessions_by_date[date]);
			chartInstance = new Chart(chartCanvas, {
				type: 'bar',
				data: {
					labels,
					datasets: [
						{
							label: 'Sessions',
							data: sessionCounts,
							backgroundColor: textMuted,
							hoverBackgroundColor: colors[0],
							borderRadius: 3,
							barThickness: 'flex',
							maxBarThickness: 14
						}
					]
				},
				options: {
					responsive: true,
					maintainAspectRatio: false,
					plugins: {
						legend: { display: false },
						tooltip: {
							backgroundColor: textPrimary,
							padding: 10,
							cornerRadius: 6,
							displayColors: false
						}
					},
					scales: {
						y: { beginAtZero: true, grid: { color: border }, ticks: { display: false } },
						x: {
							grid: { display: false },
							ticks: {
								font: { size: 10 },
								color: textMuted,
								maxTicksLimit: 8,
								maxRotation: 0
							}
						}
					}
				}
			});
		}
	});
</script>

<div class="space-y-6">
	{#if isPageLoading}
		<div class="space-y-6" role="status" aria-busy="true" aria-label="Loading...">
			<!-- Page Header skeleton -->
			<div class="flex items-start justify-between">
				<div>
					<div class="flex items-center gap-2 mb-2">
						<SkeletonText width="70px" size="xs" />
						<span class="text-[var(--text-muted)]">/</span>
						<SkeletonText width="80px" size="xs" />
					</div>
					<div class="flex items-center gap-4">
						<SkeletonBox width="48px" height="48px" rounded="lg" />
						<div>
							<SkeletonText width="120px" size="xl" class="mb-2" />
							<SkeletonText width="260px" size="sm" />
						</div>
					</div>
				</div>
				<SkeletonBox width="140px" height="36px" rounded="md" />
			</div>

			<!-- Hero Stats skeleton (3 cols) -->
			<div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
				{#each Array(3) as _}
					<SkeletonStatsCard />
				{/each}
			</div>

			<!-- Velocity group skeleton -->
			<div class="border border-[var(--border)] rounded-[var(--radius-lg)] overflow-hidden bg-[var(--bg-base)]">
				<div class="flex items-center gap-3 px-4 py-4">
					<SkeletonBox width="32px" height="32px" rounded="md" />
					<SkeletonText width="100px" size="sm" />
					<div class="flex-1"></div>
					<SkeletonText width="80px" size="xs" />
				</div>
				<div class="border-t border-[var(--border)] p-4">
					<SkeletonBox height="160px" rounded="lg" />
				</div>
			</div>

			<!-- Efficiency group skeleton -->
			<div class="border border-[var(--border)] rounded-[var(--radius-lg)] overflow-hidden bg-[var(--bg-base)]">
				<div class="flex items-center gap-3 px-4 py-4">
					<SkeletonBox width="32px" height="32px" rounded="md" />
					<SkeletonText width="100px" size="sm" />
					<div class="flex-1"></div>
					<SkeletonText width="80px" size="xs" />
				</div>
				<div class="border-t border-[var(--border)] p-4">
					<div class="grid grid-cols-1 lg:grid-cols-4 gap-4">
						{#each Array(4) as _}
							<SkeletonBox height="120px" rounded="lg" />
						{/each}
					</div>
				</div>
			</div>

			<!-- Rhythm group skeleton -->
			<div class="border border-[var(--border)] rounded-[var(--radius-lg)] overflow-hidden bg-[var(--bg-base)]">
				<div class="flex items-center gap-3 px-4 py-4">
					<SkeletonBox width="32px" height="32px" rounded="md" />
					<SkeletonText width="80px" size="sm" />
					<div class="flex-1"></div>
					<SkeletonText width="80px" size="xs" />
				</div>
				<div class="border-t border-[var(--border)] p-4 space-y-3">
					{#each Array(4) as _}
						<div class="flex items-center gap-3">
							<SkeletonText width="80px" size="xs" />
							<SkeletonBox height="6px" rounded="full" class="flex-1" />
							<SkeletonText width="80px" size="xs" />
						</div>
					{/each}
				</div>
			</div>
		</div>
	{:else}
	<!-- Page Header with Breadcrumb -->
	<PageHeader
		title="Analytics"
		icon={BarChart3}
		iconColor="--nav-green"
		breadcrumbs={[{ label: 'Dashboard', href: '/' }, { label: 'Analytics' }]}
		subtitle="Your coding patterns and AI collaboration"
	>
		{#snippet headerRight()}
			<TimeFilterDropdown {selectedFilter} onFilterChange={handleFilterChange} />
		{/snippet}
	</PageHeader>

	<!-- Hero Stats Row -->
	<StatsGrid {stats} columns={3} />

	<!-- Group 1: Velocity — Activity bar chart -->
	<CollapsibleGroup
		title="Velocity"
		open={expandedGroups.has('velocity')}
		onOpenChange={() => toggleGroup('velocity')}
	>
		{#snippet icon()}
			<div class="p-1.5 bg-[var(--bg-subtle)] rounded-md">
				<Activity size={14} class="text-[var(--text-muted)]" />
			</div>
		{/snippet}
		{#snippet metadata()}
			<div class="flex items-center gap-3 text-xs text-[var(--text-muted)]">
				<span
					>Avg: <span class="font-mono text-[var(--text-secondary)]"
						>{avgDisplay.value}</span
					>{avgDisplay.unit}</span
				>
				<span class="hidden sm:flex items-end gap-0.5 h-6">
					{#each sparklineData as val, i}
						<span
							class="inline-block w-1 rounded-sm"
							style="height: {Math.max(
								4,
								(val / sparkMax) * 100
							)}%; background-color: var(--accent); opacity: {0.3 +
								(i / sparklineData.length) * 0.7};"
						></span>
					{/each}
				</span>
			</div>
		{/snippet}

		<div class="space-y-4">
			<!-- Token context row -->
			<div class="flex gap-3 text-xs text-[var(--text-muted)]">
				<span
					><span class="font-mono text-[var(--text-secondary)]"
						>{formatK(analytics.total_tokens)}</span
					> tokens</span
				>
				<span>•</span>
				<span
					><span class="font-mono text-[var(--text-secondary)]"
						>{(analytics.total_duration_seconds / 3600).toFixed(0)}</span
					>h</span
				>
				<span>•</span>
				<span
					><span class="font-mono text-[var(--text-secondary)]"
						>{formatK(tokensPerSession)}</span
					> tokens/sess</span
				>
			</div>

			<!-- Bar chart -->
			<div class="h-40 w-full">
				<canvas bind:this={chartCanvas}></canvas>
			</div>
		</div>
	</CollapsibleGroup>

	<!-- Group 2: Efficiency — Cache, Projects, Compute DNA -->
	<CollapsibleGroup
		title="Efficiency"
		open={expandedGroups.has('efficiency')}
		onOpenChange={() => toggleGroup('efficiency')}
	>
		{#snippet icon()}
			<div class="p-1.5 bg-[var(--bg-subtle)] rounded-md">
				<Zap size={14} class="text-[var(--text-muted)]" />
			</div>
		{/snippet}
		{#snippet metadata()}
			<span class="text-xs text-[var(--text-muted)] tabular-nums">
				{getAnalyticsFilterLabel(selectedFilter)}
			</span>
		{/snippet}

		<div class="grid grid-cols-1 lg:grid-cols-4 gap-4">
			<!-- Cache Card -->
			<div class="p-5 bg-[var(--bg-subtle)] border border-[var(--border)] rounded-lg">
				<div class="flex items-center justify-between mb-3">
					<div class="flex items-center gap-2">
						<Database size={14} class="text-[var(--text-muted)]" />
						<span
							class="text-[11px] font-medium uppercase tracking-wider text-[var(--text-muted)]"
							>Cache</span
						>
					</div>
					{#if analytics.cache_hit_rate > 0.85}
						<span
							class="px-1.5 py-0.5 bg-[var(--success-subtle)] rounded text-[10px] font-medium text-[var(--success)]"
						>
							Excellent
						</span>
					{/if}
				</div>
				<div class="flex items-baseline gap-1.5 mb-3">
					<span
						class="text-xl font-semibold font-mono tabular-nums text-[var(--text-primary)]"
						>{cacheHitPercent}%</span
					>
					<span class="text-xs text-[var(--text-muted)]">hit rate</span>
				</div>
				<div
					class="relative w-full h-1.5 bg-[var(--bg-muted)] rounded-full overflow-hidden"
				>
					<div
						class="absolute top-0 left-0 h-full rounded-full bg-[var(--accent)]"
						style="width: {analytics.cache_hit_rate * 100}%"
					></div>
				</div>
			</div>

			<!-- Projects Card -->
			<div class="p-5 bg-[var(--bg-subtle)] border border-[var(--border)] rounded-lg">
				<div class="flex items-center justify-between mb-3">
					<div class="flex items-center gap-2">
						<FolderOpen size={14} class="text-[var(--text-muted)]" />
						<span
							class="text-[11px] font-medium uppercase tracking-wider text-[var(--text-muted)]"
							>Projects</span
						>
					</div>
				</div>
				<div class="flex items-baseline gap-1.5">
					<span
						class="text-xl font-semibold font-mono tabular-nums text-[var(--text-primary)]"
					>
						{analytics.projects_active}
					</span>
					<span class="text-xs text-[var(--text-muted)]">worked on</span>
				</div>
			</div>

			<!-- Compute DNA Card -->
			<div
				class="lg:col-span-2 p-5 bg-[var(--bg-subtle)] border border-[var(--border)] rounded-lg"
			>
				<div class="flex items-center gap-2 mb-3">
					<Cpu size={14} class="text-[var(--text-muted)]" />
					<span
						class="text-[11px] font-medium uppercase tracking-wider text-[var(--text-muted)]"
						>Compute DNA</span
					>
				</div>
				<div class="w-full flex h-5 rounded overflow-hidden mb-3">
					{#each modelDist as model}
						<div
							class="h-full"
							style="width: {model.perc}%; background-color: {getModelColor(
								model.name
							)};"
							title="{model.name}: {model.perc.toFixed(0)}%"
						></div>
					{/each}
				</div>
				<div class="flex flex-wrap gap-3 text-xs">
					{#each modelDist as model}
						<div class="flex items-center gap-1">
							<div
								class="w-2 h-2 rounded-full"
								style="background-color: {getModelColor(model.name)}"
							></div>
							<span class="text-[var(--text-secondary)]">{model.name}</span>
							<span class="text-[var(--text-muted)] font-mono"
								>{model.perc.toFixed(0)}%</span
							>
						</div>
					{/each}
				</div>
			</div>
		</div>
	</CollapsibleGroup>

	<!-- Group 3: Rhythm — Time Distribution -->
	<CollapsibleGroup
		title="Rhythm"
		open={expandedGroups.has('rhythm')}
		onOpenChange={() => toggleGroup('rhythm')}
	>
		{#snippet icon()}
			<div class="p-1.5 bg-[var(--bg-subtle)] rounded-md">
				<Clock size={14} class="text-[var(--text-muted)]" />
			</div>
		{/snippet}
		{#snippet metadata()}
			<div class="flex items-center gap-4 text-[11px] text-[var(--text-muted)]">
				<span>
					Peak: <span class="font-mono text-[var(--text-secondary)]"
						>{formatPeakHours(analytics.peak_hours)}</span
					>
				</span>
			</div>
		{/snippet}

		<div class="space-y-2.5">
			<!-- Morning -->
			<div class="flex items-center gap-3">
				<span class="text-[11px] text-[var(--text-muted)] w-20 shrink-0">06:00–12:00</span>
				<div
					class="relative flex-1 h-1.5 bg-[var(--bg-muted)] rounded-full overflow-hidden"
				>
					<div
						class="absolute top-0 left-0 h-full bg-[var(--accent)] rounded-full"
						style="width: {analytics.time_distribution.morning_pct}%"
					></div>
				</div>
				<span class="text-[11px] font-mono text-[var(--text-secondary)] w-20 text-right">
					{formatHoursFromPct(analytics.time_distribution.morning_pct)} ({analytics.time_distribution.morning_pct.toFixed(
						0
					)}%)
				</span>
			</div>

			<!-- Afternoon -->
			<div class="flex items-center gap-3">
				<span class="text-[11px] text-[var(--text-muted)] w-20 shrink-0">12:00–18:00</span>
				<div
					class="relative flex-1 h-1.5 bg-[var(--bg-muted)] rounded-full overflow-hidden"
				>
					<div
						class="absolute top-0 left-0 h-full bg-[var(--accent)] rounded-full"
						style="width: {analytics.time_distribution.afternoon_pct}%"
					></div>
				</div>
				<span class="text-[11px] font-mono text-[var(--text-secondary)] w-20 text-right">
					{formatHoursFromPct(analytics.time_distribution.afternoon_pct)} ({analytics.time_distribution.afternoon_pct.toFixed(
						0
					)}%)
				</span>
			</div>

			<!-- Evening -->
			<div class="flex items-center gap-3">
				<span class="text-[11px] text-[var(--text-muted)] w-20 shrink-0">18:00–24:00</span>
				<div
					class="relative flex-1 h-1.5 bg-[var(--bg-muted)] rounded-full overflow-hidden"
				>
					<div
						class="absolute top-0 left-0 h-full bg-[var(--accent)] rounded-full"
						style="width: {analytics.time_distribution.evening_pct}%"
					></div>
				</div>
				<span class="text-[11px] font-mono text-[var(--text-secondary)] w-20 text-right">
					{formatHoursFromPct(analytics.time_distribution.evening_pct)} ({analytics.time_distribution.evening_pct.toFixed(
						0
					)}%)
				</span>
			</div>

			<!-- Night -->
			<div class="flex items-center gap-3">
				<span class="text-[11px] text-[var(--text-muted)] w-20 shrink-0">00:00–06:00</span>
				<div
					class="relative flex-1 h-1.5 bg-[var(--bg-muted)] rounded-full overflow-hidden"
				>
					<div
						class="absolute top-0 left-0 h-full bg-[var(--accent)] rounded-full"
						style="width: {analytics.time_distribution.night_pct}%"
					></div>
				</div>
				<span class="text-[11px] font-mono text-[var(--text-secondary)] w-20 text-right">
					{formatHoursFromPct(analytics.time_distribution.night_pct)} ({analytics.time_distribution.night_pct.toFixed(
						0
					)}%)
				</span>
			</div>

			<!-- Footer -->
			<div
				class="mt-3 pt-2 border-t border-[var(--border)] flex items-center gap-4 text-[11px] text-[var(--text-muted)]"
			>
				<span
					>Total: <span class="font-mono text-[var(--text-secondary)]"
						>{(analytics.total_duration_seconds / 3600).toFixed(0)}h</span
					></span
				>
			</div>
		</div>
	</CollapsibleGroup>
	{/if}
</div>
