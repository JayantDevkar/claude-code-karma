<script lang="ts">
	import { browser } from '$app/environment';
	import { goto } from '$app/navigation';
	import { page, navigating } from '$app/stores';
	import TimeFilterDropdown from '$lib/components/TimeFilterDropdown.svelte';
	import type { AnalyticsFilterPeriod } from '$lib/api-types';
	import { analyticsFilterOptions, getTimestampRangeForFilter } from '$lib/utils';

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

	let topProjects = $derived(data.topProjects ?? []);

	// --- Formatters ---
	function formatTokens(n: number): { value: string; unit: string } {
		if (n >= 1e12) return { value: (n / 1e12).toFixed(1), unit: 'T' };
		if (n >= 1e9) return { value: (n / 1e9).toFixed(1), unit: 'B' };
		if (n >= 1e6) return { value: (n / 1e6).toFixed(1), unit: 'M' };
		if (n >= 1e3) return { value: (n / 1e3).toFixed(1), unit: 'K' };
		return { value: n.toString(), unit: '' };
	}

	function formatTokensShort(n: number): string {
		if (n >= 1e12) return (n / 1e12).toFixed(1) + 'T';
		if (n >= 1e9) return (n / 1e9).toFixed(1) + 'B';
		if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
		if (n >= 1e3) return (n / 1e3).toFixed(1) + 'K';
		return n.toString();
	}

	function formatDate(dateStr: string): string {
		if (!dateStr) return '';
		const d = new Date(dateStr + 'T12:00:00');
		return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
	}

function projectDisplayName(p: { path: string; display_name?: string }): string {
		if (p.display_name) return p.display_name;
		return p.path.split('/').filter(Boolean).pop() ?? p.path;
	}

	// --- Derived values ---
	let sortedDates = $derived(Object.keys(analytics.sessions_by_date).sort());

	let numDays = $derived(Math.max(sortedDates.length, 1));

	let totalHours = $derived(analytics.total_duration_seconds / 3600);

	let avgHoursPerDay = $derived(totalHours / numDays);

	let daysEquivalent = $derived(Math.round(totalHours / 24));

	let avgSessionsPerDay = $derived((analytics.total_sessions / numDays).toFixed(1));

	let subscriptionMultiple = $derived(Math.round(analytics.estimated_cost_usd / 20));

	let avgTokensPerSession = $derived(
		analytics.total_sessions > 0 ? analytics.total_tokens / analytics.total_sessions : 0
	);

	let cacheHitPercent = $derived((analytics.cache_hit_rate * 100).toFixed(1));

	let firstSessionDate = $derived(sortedDates[0] ? formatDate(sortedDates[0]) : '');

	let peakDay = $derived.by(() => {
		let maxCount = 0;
		let maxDate = '';
		for (const [date, count] of Object.entries(analytics.sessions_by_date)) {
			if ((count as number) > maxCount) {
				maxCount = count as number;
				maxDate = date;
			}
		}
		return { date: maxDate, count: maxCount };
	});

	// Token breakdown: raw input, cache tokens (all non-input/output), output
	let cacheTokens = $derived(
		Math.max(0, analytics.total_tokens - analytics.total_input_tokens - analytics.total_output_tokens)
	);
	let totalInputSide = $derived(analytics.total_tokens - analytics.total_output_tokens);

	// Heatmap
	type HeatmapDay = { date: string; count: number };
	type HeatmapMonthLabel = { label: string; weekIndex: number };
	type TooltipState = { x: number; y: number; day: HeatmapDay } | null;

	// Cell size constants (px)
	const CELL = 15;
	const GAP = 3;
	const STRIDE = CELL + GAP; // 18px per column

	function heatmapColor(count: number): string {
		if (count === 0) return 'var(--bg-muted)';
		if (count <= 2) return '#ddd6fe';
		if (count <= 6) return '#c084fc';
		if (count <= 12) return '#a855f7';
		return 'var(--accent)';
	}

	const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
	const VISIBLE_DOW = new Set([1, 3, 5]); // Mon, Wed, Fri

	// Year filter state
	let availableYears = $derived.by(() => {
		const byDate = analytics.sessions_by_date;
		const years = new Set<number>();
		for (const date of Object.keys(byDate)) {
			years.add(parseInt(date.slice(0, 4)));
		}
		return [...years].sort((a, b) => b - a); // descending
	});

	let selectedYear = $state<number>(0); // 0 = unset, will default to latest year

	let activeYear = $derived(selectedYear || availableYears[0] || new Date().getFullYear());

	let heatmapData = $derived.by(() => {
		const byDate = analytics.sessions_by_date;
		const year = activeYear;

		if (!year) return { days: [] as HeatmapDay[], totalWeeks: 0, monthLabels: [] as HeatmapMonthLabel[] };

		// Start: Sunday on or before Jan 1 of the selected year
		const jan1 = new Date(`${year}-01-01T12:00:00`);
		const startDate = new Date(jan1);
		startDate.setDate(jan1.getDate() - jan1.getDay());

		// End: Saturday on or after Dec 31 of the selected year (always full year)
		const dec31 = new Date(`${year}-12-31T12:00:00`);
		const endDate = new Date(dec31);
		endDate.setDate(dec31.getDate() + (6 - dec31.getDay()));

		// Build flat list of all calendar days (Sun→Sat columns)
		const days: HeatmapDay[] = [];
		const cur = new Date(startDate);
		while (cur <= endDate) {
			const yr = cur.getFullYear();
			const mo = String(cur.getMonth() + 1).padStart(2, '0');
			const dy = String(cur.getDate()).padStart(2, '0');
			const dateStr = `${yr}-${mo}-${dy}`;
			days.push({ date: dateStr, count: byDate[dateStr] || 0 });
			cur.setDate(cur.getDate() + 1);
		}

		const totalWeeks = Math.ceil(days.length / 7);

		// Month labels: first week column where each month appears
		const monthLabels: HeatmapMonthLabel[] = [];
		const seenMonths = new Set<string>();

		for (let wi = 0; wi < totalWeeks; wi++) {
			for (let dow = 0; dow < 7; dow++) {
				const idx = wi * 7 + dow;
				if (idx >= days.length) break;
				const monthKey = days[idx].date.slice(0, 7);
				if (!seenMonths.has(monthKey)) {
					seenMonths.add(monthKey);
					const d = new Date(days[idx].date + 'T12:00:00');
					// Only show month labels for days within the selected year
					if (d.getFullYear() === year) {
						monthLabels.push({
							label: d.toLocaleDateString('en-US', { month: 'short' }),
							weekIndex: wi
						});
					}
				}
			}
		}

		return { days, totalWeeks, monthLabels };
	});

	// Tooltip
	let tooltip = $state<TooltipState>(null);

	function showTooltip(e: MouseEvent, day: HeatmapDay) {
		const cell = e.currentTarget as HTMLElement;
		const container = cell.closest('.heatmap-grid-area') as HTMLElement;
		if (!container) return;
		const cellRect = cell.getBoundingClientRect();
		const containerRect = container.getBoundingClientRect();
		tooltip = {
			x: cellRect.left - containerRect.left + CELL / 2,
			y: cellRect.top - containerRect.top,
			day
		};
	}

	function hideTooltip() {
		tooltip = null;
	}

	function tooltipLabel(day: HeatmapDay): string {
		const d = new Date(day.date + 'T12:00:00');
		const dateLabel = d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
		if (day.count === 0) return `No sessions — ${dateLabel}`;
		const estTokens = avgTokensPerSession > 0 ? Math.round(avgTokensPerSession * day.count) : 0;
		const tokStr = estTokens > 0 ? `  ·  ~${formatTokensShort(estTokens)} tokens` : '';
		return `${day.count} session${day.count !== 1 ? 's' : ''}${tokStr} — ${dateLabel}`;
	}

	// Model mix
	let modelColors: Record<string, string> = {
		Opus: '#a855f7',
		Sonnet: '#c084fc',
		Haiku: '#e9d5ff',
		Other: '#7c3aed'
	};

	let modelMix = $derived.by(() => {
		const cats = analytics.models_categorized;
		const total = Object.values(cats).reduce((a, b) => a + b, 0);
		if (total === 0) return [];
		return Object.entries(cats)
			.map(([model, count]) => ({
				model,
				count,
				percentage: Math.round((count / total) * 100)
			}))
			.sort((a, b) => b.count - a.count);
	});

	let isPageLoading = $derived(!!$navigating && $navigating.to?.route.id === '/analytics');

	// Tokens formatted
	let tokensFormatted = $derived(formatTokens(analytics.total_tokens));
	let hoursDisplay = $derived(
		totalHours >= 1000
			? { value: (totalHours / 1000).toFixed(1), unit: 'Kh' }
			: { value: Math.round(totalHours).toLocaleString(), unit: 'h' }
	);

	// Pre-computed for template
	let totalTokensFormatted = $derived(formatTokens(analytics.total_tokens));

	let tokenCachePct = $derived(
		analytics.total_tokens > 0 ? (cacheTokens / analytics.total_tokens) * 100 : 0
	);
	let tokenInputPct = $derived(
		analytics.total_tokens > 0 ? (analytics.total_input_tokens / analytics.total_tokens) * 100 : 0
	);
	let tokenOutputPct = $derived(
		analytics.total_tokens > 0
			? (analytics.total_output_tokens / analytics.total_tokens) * 100
			: 0
	);

	let topProjectsMaxSessions = $derived(topProjects[0]?.session_count ?? 1);
</script>

<div class="max-w-[1100px] mx-auto" style="-webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale;">
	{#if isPageLoading}
		<div class="space-y-5 animate-pulse">
			<div class="h-24 rounded-lg bg-[var(--bg-muted)]"></div>
			<div class="grid grid-cols-4 gap-[10px]">
				{#each Array(4) as _}
					<div class="h-28 rounded-lg bg-[var(--bg-muted)]"></div>
				{/each}
			</div>
			<div class="h-48 rounded-lg bg-[var(--bg-muted)]"></div>
			<div class="h-40 rounded-lg bg-[var(--bg-muted)]"></div>
			<div class="grid grid-cols-2 gap-[10px]">
				<div class="h-48 rounded-lg bg-[var(--bg-muted)]"></div>
				<div class="h-48 rounded-lg bg-[var(--bg-muted)]"></div>
			</div>
		</div>
	{:else}
		<!-- Page Header -->
		<div class="mb-3">
			<!-- Breadcrumb -->
			<div class="flex items-center gap-[5px] mb-[9px]">
				<span style="font-size: 13px; color: var(--text-primary);">Dashboard</span>
				<span style="font-size: 13px; color: var(--text-faint);">/</span>
				<span style="font-size: 13px; font-weight: 600; color: var(--text-primary);">Analytics</span>
			</div>

			<div class="flex items-end justify-between">
				<div>
					<h1 style="font-size: 25px; font-weight: 700; color: var(--text-primary); letter-spacing: -0.02em; line-height: 1.2;">
						Your head has been in the Claude
					</h1>
					{#if firstSessionDate}
						<p class="font-mono mt-1" style="font-size: 13px; color: var(--text-faint);">
							since {firstSessionDate}
						</p>
					{/if}
				</div>
				<TimeFilterDropdown {selectedFilter} onFilterChange={handleFilterChange} />
			</div>
		</div>

		<div class="flex flex-col" style="gap: 20px;">
			<!-- Section 1: How much? -->
			<div>
				<div class="font-mono mb-2" style="font-size: 13px; font-weight: 700; color: var(--accent); text-transform: uppercase; letter-spacing: 0.12em;">
					How much?
				</div>
				<div class="grid gap-[10px]" style="grid-template-columns: repeat(4, 1fr);">
					<!-- Time card -->
					<div class="rounded-lg" style="background: var(--bg-base); border: 1px solid var(--border); padding: 16px 18px;">
						<div style="font-size: 12px; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.07em; margin-bottom: 9px;">
							Time
						</div>
						<div class="font-mono flex items-baseline gap-1" style="line-height: 1;">
							<span style="font-size: 30px; font-weight: 700; color: var(--text-primary); letter-spacing: -1px;">
								{hoursDisplay.value}
							</span>
							<span style="font-size: 15px; font-weight: 500; color: var(--text-muted); letter-spacing: 0;">
								{hoursDisplay.unit}
							</span>
						</div>
						<div style="font-size: 13px; color: var(--text-muted); margin-top: 7px;">
							avg {avgHoursPerDay.toFixed(1)} hours / day
						</div>
						<div style="font-size: 12px; color: var(--text-faint); margin-top: 2px;">
							{daysEquivalent} days equivalent
						</div>
					</div>

					<!-- Tokens card -->
					<div class="rounded-lg" style="background: var(--bg-base); border: 1px solid var(--border); padding: 16px 18px;">
						<div style="font-size: 12px; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.07em; margin-bottom: 9px;">
							Tokens
						</div>
						<div class="font-mono flex items-baseline gap-1" style="line-height: 1;">
							<span style="font-size: 30px; font-weight: 700; color: var(--text-primary); letter-spacing: -1px;">
								{tokensFormatted.value}
							</span>
							<span style="font-size: 15px; font-weight: 500; color: var(--text-muted); letter-spacing: 0;">
								{tokensFormatted.unit}
							</span>
						</div>
						<div style="font-size: 13px; color: var(--text-muted); margin-top: 7px;">
							{cacheHitPercent}% served from cache
						</div>
						<div style="font-size: 12px; color: var(--text-faint); margin-top: 2px;">
							~{formatTokensShort(Math.round(avgTokensPerSession))} per session avg
						</div>
					</div>

					<!-- Sessions card -->
					<div class="rounded-lg" style="background: var(--bg-base); border: 1px solid var(--border); padding: 16px 18px;">
						<div style="font-size: 12px; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.07em; margin-bottom: 9px;">
							Sessions
						</div>
						<div class="font-mono flex items-baseline gap-1" style="line-height: 1;">
							<span style="font-size: 30px; font-weight: 700; color: var(--text-primary); letter-spacing: -1px;">
								{analytics.total_sessions.toLocaleString()}
							</span>
						</div>
						<div style="font-size: 13px; color: var(--text-muted); margin-top: 7px;">
							avg {avgSessionsPerDay} / day
						</div>
						<div style="font-size: 12px; color: var(--text-faint); margin-top: 2px;">
							across {analytics.projects_active} projects
						</div>
					</div>

					<!-- Value card (accent) -->
					<div class="rounded-lg" style="background: var(--accent-muted); border: 1.5px solid var(--accent-subtle); padding: 16px 18px;">
						<div style="font-size: 12px; color: var(--accent); font-weight: 600; text-transform: uppercase; letter-spacing: 0.07em; margin-bottom: 9px;">
							Value
						</div>
						<div class="font-mono flex items-baseline gap-1" style="line-height: 1;">
							<span style="font-size: 30px; font-weight: 700; color: var(--text-primary); letter-spacing: -1px;">
								${Math.round(analytics.estimated_cost_usd).toLocaleString()}
							</span>
						</div>
						<div style="font-size: 13px; color: var(--text-muted); margin-top: 7px;">
							API-equivalent usage
						</div>
						{#if subscriptionMultiple > 1}
							<div
								class="inline-flex items-center mt-[7px]"
								style="background: linear-gradient(135deg, #a855f7, var(--accent)); border-radius: 20px; padding: 2px 9px;"
							>
								<span style="font-size: 12px; font-weight: 700; color: #ffffff; letter-spacing: 0.02em;">
									{subscriptionMultiple}× your $20/mo
								</span>
							</div>
						{/if}
					</div>
				</div>
			</div>

			<!-- Section 2: How often? (Activity Heatmap) -->
			<div>
				<div class="font-mono mb-2" style="font-size: 13px; font-weight: 700; color: var(--accent); text-transform: uppercase; letter-spacing: 0.12em;">
					How often?
				</div>
				<div class="rounded-lg" style="background: var(--bg-base); border: 1px solid var(--border); padding: 16px 18px;">
					<!-- Card header -->
					<div class="flex items-baseline justify-between" style="margin-bottom: 16px;">
						<span style="font-size: 13px; font-weight: 600; color: var(--text-primary);">Activity</span>
						<span class="font-mono" style="font-size: 13px; color: var(--text-faint);">
							avg {avgSessionsPerDay} sessions / day{peakDay.count > 0 ? ` · peak ${peakDay.count} on ${formatDate(peakDay.date)}` : ''}
						</span>
					</div>

					{#if heatmapData.days.length > 0}
						<!-- Main heatmap row: day labels + grid + year filter -->
						<div class="flex items-start" style="gap: 8px;">
							<!-- Day labels column -->
							<div class="flex flex-col shrink-0" style="gap: {GAP}px; padding-top: 22px;">
								{#each DAY_NAMES as name, i}
									<div
										class="font-mono"
										style="height: {CELL}px; line-height: {CELL}px; font-size: 12px; color: {VISIBLE_DOW.has(i) ? 'var(--text-faint)' : 'transparent'};"
									>{name}</div>
								{/each}
							</div>

							<!-- Grid area with tooltip container -->
							<div class="heatmap-grid-area" style="flex: 1; min-width: 0; overflow-x: auto; position: relative;">
								<!-- Month labels row -->
								<div style="position: relative; height: 18px; margin-bottom: 4px; min-width: {heatmapData.totalWeeks * STRIDE}px;">
									{#each heatmapData.monthLabels as ml}
										<span
											class="font-mono"
											style="position: absolute; top: 0; left: {ml.weekIndex * STRIDE}px; font-size: 12px; color: var(--accent); white-space: nowrap;"
										>{ml.label}</span>
									{/each}
								</div>

								<!-- Cell grid — fixed square cells, scrolls if needed -->
								<div
									style="display: grid; grid-template-rows: repeat(7, {CELL}px); grid-auto-flow: column; grid-auto-columns: {CELL}px; gap: {GAP}px; width: fit-content;"
								>
									{#each heatmapData.days as day}
										<div
											role="img"
											aria-label={tooltipLabel(day)}
											style="width: {CELL}px; height: {CELL}px; border-radius: 2px; background: {heatmapColor(day.count)}; cursor: {day.count > 0 ? 'pointer' : 'default'};"
											onmouseenter={(e) => showTooltip(e, day)}
											onmouseleave={hideTooltip}
										></div>
									{/each}
								</div>

								<!-- Tooltip -->
								{#if tooltip}
									<div
										class="font-mono"
										style="
											position: absolute;
											left: {tooltip.x}px;
											top: {tooltip.y - 36}px;
											transform: translateX(-50%);
											background: var(--text-primary);
											color: var(--bg-base);
											font-size: 12px;
											padding: 4px 8px;
											border-radius: 5px;
											white-space: nowrap;
											pointer-events: none;
											z-index: 10;
											box-shadow: 0 2px 8px rgba(0,0,0,0.2);
										"
									>
										{tooltipLabel(tooltip.day)}
									</div>
								{/if}
							</div>

							<!-- Year filter buttons (right side) -->
							{#if availableYears.length > 1}
								<div class="flex flex-col shrink-0" style="gap: 4px; padding-top: 22px;">
									{#each availableYears as yr}
										<button
											type="button"
											onclick={() => (selectedYear = yr)}
											class="font-mono"
											style="
												font-size: 15px;
												font-weight: {activeYear === yr ? '700' : '400'};
												color: {activeYear === yr ? 'var(--accent)' : 'var(--text-faint)'};
												background: {activeYear === yr ? 'var(--accent-muted)' : 'transparent'};
												border: 1px solid {activeYear === yr ? 'var(--accent-subtle)' : 'transparent'};
												border-radius: 4px;
												padding: 2px 7px;
												cursor: pointer;
												transition: color 0.15s, background 0.15s;
											"
										>{yr}</button>
									{/each}
								</div>
							{/if}
						</div>

						<!-- Legend -->
						<div class="flex items-center justify-end" style="gap: 5px; margin-top: 12px;">
							<span style="font-size: 12px; color: var(--text-faint); margin-right: 2px;">Less</span>
							<div style="width: {CELL}px; height: {CELL}px; border-radius: 2px; background: var(--bg-muted); border: 1px solid var(--border);"></div>
							<div style="width: {CELL}px; height: {CELL}px; border-radius: 2px; background: #ddd6fe;"></div>
							<div style="width: {CELL}px; height: {CELL}px; border-radius: 2px; background: #c084fc;"></div>
							<div style="width: {CELL}px; height: {CELL}px; border-radius: 2px; background: #a855f7;"></div>
							<div style="width: {CELL}px; height: {CELL}px; border-radius: 2px; background: var(--accent);"></div>
							<span style="font-size: 12px; color: var(--text-faint); margin-left: 2px;">More</span>
						</div>
					{:else}
						<div style="color: var(--text-faint); font-size: 12px; padding: 24px 0; text-align: center;">
							No session data available
						</div>
					{/if}
				</div>
			</div>

			<!-- Section 3: How intensely? -->
			<div>
				<div class="font-mono mb-2" style="font-size: 13px; font-weight: 700; color: var(--accent); text-transform: uppercase; letter-spacing: 0.12em;">
					How intensely?
				</div>
				<div class="grid gap-[10px]" style="grid-template-columns: 1fr 2fr;">
					<!-- Left: Token Consumption Summary -->
					<div class="rounded-lg" style="background: var(--bg-base); border: 1px solid var(--border); padding: 16px 18px;">
						<div style="font-size: 12px; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.07em; margin-bottom: 9px;">
							Token consumption
						</div>
						<div class="font-mono flex items-baseline gap-1 mb-3" style="line-height: 1;">
							<span style="font-size: 30px; font-weight: 700; color: var(--text-primary); letter-spacing: -1px;">
								{totalTokensFormatted.value}
							</span>
							<span style="font-size: 15px; font-weight: 500; color: var(--text-muted);">{totalTokensFormatted.unit}</span>
						</div>

						<div class="flex flex-col" style="gap: 8px;">
							<div class="flex items-center justify-between">
								<span style="font-size: 13px; color: var(--text-muted);">Input tokens</span>
								<span class="font-mono" style="font-size: 13px; color: var(--text-primary); font-weight: 500;">
									{formatTokensShort(totalInputSide)}
								</span>
							</div>
							<div class="flex items-center justify-between">
								<span style="font-size: 13px; color: var(--text-muted);">Output tokens</span>
								<span class="font-mono" style="font-size: 13px; color: var(--text-primary); font-weight: 500;">
									{formatTokensShort(analytics.total_output_tokens)}
								</span>
							</div>
							<div style="height: 1px; background: var(--border); margin: 2px 0;"></div>
							<div class="flex items-center justify-between">
								<span style="font-size: 13px; color: var(--text-secondary); font-weight: 500;">Cache efficiency</span>
								<span class="font-mono" style="font-size: 13px; color: var(--accent); font-weight: 700;">
									{cacheHitPercent}%
								</span>
							</div>
						</div>
					</div>

					<!-- Right: Where Tokens Go -->
					<div class="rounded-lg" style="background: var(--bg-base); border: 1px solid var(--border); padding: 16px 18px;">
						<div style="font-size: 12px; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.07em; margin-bottom: 9px;">
							Where tokens go
						</div>

						{#if analytics.total_tokens > 0}
							<!-- Stacked bar -->
							<div class="flex mb-4" style="height: 16px; border-radius: 5px; overflow: hidden; gap: 1px;">
								{#if tokenCachePct > 0}
									<div
										style="flex: {tokenCachePct}; background: var(--accent-subtle); border: 1px solid var(--accent-subtle);"
										title="Cached: {tokenCachePct.toFixed(1)}%"
									></div>
								{/if}
								{#if tokenInputPct > 0}
									<div
										style="flex: {tokenInputPct}; background: #a855f7;"
										title="Uncached input: {tokenInputPct.toFixed(1)}%"
									></div>
								{/if}
								{#if tokenOutputPct > 0}
									<div
										style="flex: {tokenOutputPct}; background: var(--accent);"
										title="Output: {tokenOutputPct.toFixed(1)}%"
									></div>
								{/if}
							</div>

							<!-- Legend -->
							<div class="flex flex-col" style="gap: 9px;">
								<div class="flex items-center gap-2">
									<div style="width: 10px; height: 10px; border-radius: 2px; background: var(--accent-subtle); border: 1px solid var(--accent-subtle); flex-shrink: 0;"></div>
									<span style="font-size: 13px; color: var(--text-muted); flex: 1;">Cached input</span>
									<span class="font-mono" style="font-size: 13px; color: var(--text-primary); font-weight: 500;">
										{formatTokensShort(cacheTokens)}
									</span>
									<span class="font-mono" style="font-size: 13px; color: var(--text-faint); width: 40px; text-align: right;">
										{tokenCachePct.toFixed(1)}%
									</span>
								</div>
								<div class="flex items-center gap-2">
									<div style="width: 10px; height: 10px; border-radius: 2px; background: #a855f7; flex-shrink: 0;"></div>
									<span style="font-size: 13px; color: var(--text-muted); flex: 1;">Uncached input</span>
									<span class="font-mono" style="font-size: 13px; color: var(--text-primary); font-weight: 500;">
										{formatTokensShort(analytics.total_input_tokens)}
									</span>
									<span class="font-mono" style="font-size: 13px; color: var(--text-faint); width: 40px; text-align: right;">
										{tokenInputPct.toFixed(1)}%
									</span>
								</div>
								<div class="flex items-center gap-2">
									<div style="width: 10px; height: 10px; border-radius: 2px; background: var(--accent); flex-shrink: 0;"></div>
									<span style="font-size: 13px; color: var(--text-muted); flex: 1;">Output</span>
									<span class="font-mono" style="font-size: 13px; color: var(--text-primary); font-weight: 500;">
										{formatTokensShort(analytics.total_output_tokens)}
									</span>
									<span class="font-mono" style="font-size: 13px; color: var(--text-faint); width: 40px; text-align: right;">
										{tokenOutputPct.toFixed(1)}%
									</span>
								</div>
							</div>

							<div style="height: 1px; background: var(--border); margin: 12px 0 8px;"></div>
							<p style="font-size: 13px; color: var(--text-faint); line-height: 1.5; font-style: italic;">
								{cacheHitPercent}% of tokens were cached — you build on context, not prompts from scratch.
							</p>
						{:else}
							<div style="color: var(--text-faint); font-size: 12px;">No token data available</div>
						{/if}
					</div>
				</div>
			</div>

			<!-- Section 4: Bottom Row — Projects + Models -->
			<div class="grid gap-[10px]" style="grid-template-columns: 1fr 1fr; padding-bottom: 48px;">
				<!-- Left: What are you building? -->
				<div class="rounded-lg" style="background: var(--bg-base); border: 1px solid var(--border); padding: 16px 18px;">
					<div class="font-mono mb-3" style="font-size: 13px; font-weight: 700; color: var(--accent); text-transform: uppercase; letter-spacing: 0.12em;">
						What are you building?
					</div>
					<div class="flex items-baseline mb-4" style="gap: 6px;">
						<span class="font-mono" style="font-size: 28px; font-weight: 700; color: var(--text-primary); letter-spacing: -0.5px;">
							{analytics.projects_active}
						</span>
						<span style="font-size: 12px; color: var(--text-muted);">
							projects · {analytics.total_sessions.toLocaleString()} sessions total
						</span>
					</div>

					{#if topProjects.length > 0}
						<div class="flex flex-col" style="gap: 10px;">
							{#each topProjects as project, i}
								<div>
									<div class="flex items-center justify-between mb-1" style="gap: 8px;">
										<div class="flex items-center gap-2" style="min-width: 0;">
											<span class="font-mono" style="font-size: 12px; font-weight: 600; color: var(--accent); width: 16px; text-align: right; flex-shrink: 0;">
												{i + 1}
											</span>
											<span style="font-size: 13px; color: var(--text-primary); font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
												{projectDisplayName(project)}
											</span>
										</div>
										<span class="font-mono" style="font-size: 12px; color: var(--text-muted); flex-shrink: 0;">
											{project.session_count}
										</span>
									</div>
									<div style="height: 6px; background: var(--bg-muted); border-radius: 3px; overflow: hidden; margin-left: 24px;">
										<div style="background: linear-gradient(90deg, var(--accent), #a855f7); border-radius: 3px; height: 100%; width: {(project.session_count / topProjectsMaxSessions) * 100}%;"></div>
									</div>
								</div>
							{/each}
						</div>
						{#if analytics.projects_active > 5}
							<div style="font-size: 12px; color: var(--text-faint); margin-top: 14px; padding-top: 12px; border-top: 1px solid var(--border);">
								Showing top 5 of {analytics.projects_active} projects
							</div>
						{/if}
					{:else}
						<div style="color: var(--text-faint); font-size: 12px;">No project data available</div>
					{/if}
				</div>

				<!-- Right: Which models? -->
				<div class="rounded-lg" style="background: var(--bg-base); border: 1px solid var(--border); padding: 16px 18px;">
					<div class="font-mono mb-3" style="font-size: 13px; font-weight: 700; color: var(--accent); text-transform: uppercase; letter-spacing: 0.12em;">
						Which models?
					</div>

					{#if modelMix.length > 0}
						<!-- Stacked model bar -->
						<div class="flex mb-4" style="height: 14px; border-radius: 5px; overflow: hidden; gap: 1px;">
							{#each modelMix as m}
								<div
									style="flex: {m.percentage}; background: {modelColors[m.model] ?? 'var(--accent)'};"
									title="{m.model}: {m.percentage}%"
								></div>
							{/each}
						</div>

						<!-- Model legend -->
						<div class="flex flex-col" style="gap: 9px;">
							{#each modelMix as m}
								<div class="flex items-center gap-2">
									<div
										style="width: 10px; height: 10px; border-radius: 2px; background: {modelColors[m.model] ?? 'var(--accent)'}; flex-shrink: 0;"
									></div>
									<span class="font-mono" style="font-size: 13px; color: var(--text-secondary); flex: 1;">
										{m.model.toLowerCase()}
									</span>
									<span class="font-mono" style="font-size: 13px; color: var(--text-muted); text-align: right; white-space: nowrap;">
										{m.count} sessions
									</span>
									<span class="font-mono" style="font-size: 13px; color: var(--text-faint); width: 38px; text-align: right;">
										{m.percentage}%
									</span>
								</div>
							{/each}
						</div>
					{:else}
						<div style="color: var(--text-faint); font-size: 12px;">No model data available</div>
					{/if}
				</div>
			</div>
		</div>
	{/if}
</div>
