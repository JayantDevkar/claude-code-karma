<script lang="ts">
	import type { UsageTrendResponse } from '$lib/api-types';

	type TrendRange = '7d' | '30d' | '90d';

	interface GroupInfo { key: string; label: string; color: string; }

	let {
		trendData = null,
		loading = false,
		range = '90d' as TrendRange,
		onRangeChange,
		getGroupFor,
		label = 'Invocations Over Time',
	}: {
		trendData: UsageTrendResponse | null;
		loading: boolean;
		range: TrendRange;
		onRangeChange: (r: TrendRange) => void;
		getGroupFor: (itemName: string) => GroupInfo | null;
		label?: string;
	} = $props();

	// ── Bezier helpers ─────────────────────────────────────────────────────────
	function catmullRom(pts: {x:number;y:number}[]): string {
		if (pts.length < 2) return '';
		let d = `M ${pts[0].x.toFixed(1)},${pts[0].y.toFixed(1)}`;
		for (let i = 0; i < pts.length - 1; i++) {
			const p0 = pts[Math.max(0, i - 1)];
			const p1 = pts[i];
			const p2 = pts[i + 1];
			const p3 = pts[Math.min(pts.length - 1, i + 2)];
			const cp1x = p1.x + (p2.x - p0.x) / 6;
			const cp1y = p1.y + (p2.y - p0.y) / 6;
			const cp2x = p2.x - (p3.x - p1.x) / 6;
			const cp2y = p2.y - (p3.y - p1.y) / 6;
			d += ` C ${cp1x.toFixed(1)},${cp1y.toFixed(1)} ${cp2x.toFixed(1)},${cp2y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`;
		}
		return d;
	}

	function stackedPaths(topPts: {x:number;y:number}[], botPts: {x:number;y:number}[] | null, baseY: number): { line: string; area: string } {
		const line = catmullRom(topPts);
		if (!botPts) {
			const last = topPts[topPts.length - 1];
			const first = topPts[0];
			return { line, area: `${line} L ${last.x.toFixed(1)},${baseY} L ${first.x.toFixed(1)},${baseY} Z` };
		}
		const revBot = [...botPts].reverse();
		const revLine = catmullRom(revBot);
		const revFirst = revBot[0];
		return { line, area: `${line} L ${revFirst.x.toFixed(1)},${revFirst.y.toFixed(1)} ${revLine.replace(/^M [^C]*C/, 'C')} Z` };
	}

	// ── Chart data ─────────────────────────────────────────────────────────────
	const cX1 = 48, cX2 = 892, cY1 = 8, cY2 = 156;
	const cW = cX2 - cX1, cH = cY2 - cY1;

	let chartData = $derived.by(() => {
		if (!trendData?.trend_by_item || !trendData.trend.length) return null;
		const dates = [...trendData.trend]
			.sort((a, b) => a.date.localeCompare(b.date))
			.map(p => p.date);

		// Group items into layers
		const groupMap = new Map<string, { label: string; color: string; counts: number[] }>();
		for (const [itemName, pts] of Object.entries(trendData.trend_by_item)) {
			const g = getGroupFor(itemName);
			if (!g) continue;
			if (!groupMap.has(g.key)) groupMap.set(g.key, { label: g.label, color: g.color, counts: new Array(dates.length).fill(0) });
			const ptMap = new Map(pts.map(p => [p.date, p.count]));
			const entry = groupMap.get(g.key)!;
			dates.forEach((d, i) => { entry.counts[i] += ptMap.get(d) ?? 0; });
		}

		const groups = [...groupMap.values()].sort((a, b) =>
			b.counts.reduce((s, v) => s + v, 0) - a.counts.reduce((s, v) => s + v, 0)
		);
		if (!groups.length) return null;

		const dailyTotals = dates.map((_, i) => groups.reduce((s, g) => s + g.counts[i], 0));
		const yMax = Math.max(...dailyTotals, 1);
		const xi = (i: number) => cX1 + (i / Math.max(dates.length - 1, 1)) * cW;
		const yv = (v: number) => cY2 - (v / yMax) * cH;

		const cumulative = new Array(dates.length).fill(0);
		const layers = groups.map((g, idx) => {
			const prevCum = [...cumulative];
			dates.forEach((_, i) => { cumulative[i] += g.counts[i]; });
			const topPts = dates.map((_, i) => ({ x: xi(i), y: yv(cumulative[i]) }));
			const botPts = idx === 0 ? null : dates.map((_, i) => ({ x: xi(i), y: yv(prevCum[i]) }));
			const { line, area } = stackedPaths(topPts, botPts, cY2);
			return { ...g, topPts, line, area, gradId: `sc${idx}` };
		});

		const peakIdx = dailyTotals.reduce((mi, v, i) => v > dailyTotals[mi] ? i : mi, 0);
		const totalInv = dailyTotals.reduce((s, v) => s + v, 0);
		const xIdxs = dates.length <= 7 ? dates.map((_, i) => i)
			: [0, Math.floor(dates.length * 0.25), Math.floor(dates.length * 0.5), Math.floor(dates.length * 0.75), dates.length - 1];
		const fmt = (d: string) => new Date(d + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

		return {
			layers, groups, dates, dailyTotals,
			peakX: xi(peakIdx), peakY: yv(dailyTotals[peakIdx]),
			peakVal: dailyTotals[peakIdx], peakDate: fmt(dates[peakIdx]),
			totalInv, avgPerDay: (totalInv / dates.length).toFixed(1),
			yTicks: [1, 0.67, 0.33, 0].map(f => ({ y: cY2 - f * cH, val: Math.round(yMax * f) })),
			xLabels: xIdxs.map(i => ({
				x: xi(i), label: fmt(dates[i]),
				anchor: (i === 0 ? 'start' : i === dates.length - 1 ? 'end' : 'middle') as 'start' | 'end' | 'middle'
			})),
			xi
		};
	});

	// ── Tooltip state ──────────────────────────────────────────────────────────
	let hoverIdx = $state<number | null>(null);
	let svgEl = $state<SVGSVGElement | null>(null);

	function onMouseMove(e: MouseEvent) {
		if (!chartData || !svgEl) return;
		const rect = svgEl.getBoundingClientRect();
		const mx = (e.clientX - rect.left) * (900 / rect.width);
		if (mx < cX1 - 10 || mx > cX2 + 10) { hoverIdx = null; return; }
		let best = 0, bestDist = Infinity;
		chartData.dates.forEach((_, i) => { const d = Math.abs(chartData!.xi(i) - mx); if (d < bestDist) { bestDist = d; best = i; } });
		hoverIdx = best;
	}

	let tooltip = $derived.by(() => {
		if (hoverIdx === null || !chartData) return null;
		const i = hoverIdx;
		const date = new Date(chartData.dates[i] + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
		const rows = chartData.layers.filter(l => l.counts[i] > 0).map(l => ({ label: l.label, count: l.counts[i], color: l.color })).sort((a, b) => b.count - a.count);
		return { date, total: chartData.dailyTotals[i], rows, svgX: chartData.xi(i) };
	});
</script>

<!-- Chart card -->
<div class="rounded-lg" style="padding: 16px 18px; background: var(--bg-base); border: 1px solid var(--border);">
	<!-- Header -->
	<div class="flex items-start justify-between" style="margin-bottom: 12px;">
		<div>
			<div style="font-size: 10px; font-weight: 700; color: var(--accent); text-transform: uppercase; letter-spacing: 0.12em; font-family: 'JetBrains Mono', monospace; margin-bottom: 5px;">{label}</div>
			{#if chartData}
				<div class="flex items-center gap-4">
					<span style="font-size: 11px; color: var(--text-faint); font-family: 'JetBrains Mono', monospace;"><span style="font-weight: 700; color: var(--text-primary);">{chartData.totalInv}</span> total</span>
					<span style="font-size: 11px; color: var(--text-faint); font-family: 'JetBrains Mono', monospace;"><span style="font-weight: 700; color: var(--text-primary);">{chartData.avgPerDay}</span>/day avg</span>
					<span style="font-size: 11px; color: var(--text-faint); font-family: 'JetBrains Mono', monospace;">peak <span style="font-weight: 700; color: var(--text-primary);">{chartData.peakVal}</span> on {chartData.peakDate}</span>
				</div>
			{/if}
		</div>
		<div class="flex items-center gap-3">
			{#if chartData}
				<div class="flex items-center gap-2">
					{#each chartData.groups.slice(0, 4) as g}
						<div class="flex items-center gap-1.5">
							<div style="width: 8px; height: 8px; border-radius: 2px; background: {g.color}; flex-shrink: 0;"></div>
							<span style="font-size: 10px; color: var(--text-faint);">{g.label.length > 12 ? g.label.slice(0, 11) + '…' : g.label}</span>
						</div>
					{/each}
					{#if chartData.groups.length > 4}
						<span style="font-size: 10px; color: var(--text-faint);">+{chartData.groups.length - 4} more</span>
					{/if}
				</div>
			{/if}
			<div class="flex overflow-hidden rounded" style="border: 1px solid var(--border);">
				{#each (['7d', '30d', '90d'] as const) as r}
					<button
						onclick={() => onRangeChange(r)}
						style="padding: 4px 10px; font-size: 11px; font-weight: {range === r ? '700' : '500'}; font-family: 'JetBrains Mono', monospace; background: {range === r ? 'var(--accent-muted)' : 'var(--bg-subtle)'}; color: {range === r ? 'var(--accent)' : 'var(--text-faint)'}; {r !== '90d' ? 'border-right: 1px solid var(--border);' : ''}"
					>{r}</button>
				{/each}
			</div>
		</div>
	</div>

	<!-- SVG -->
	{#if loading && !trendData}
		<div style="height: 188px; display: flex; align-items: center; justify-content: center;">
			<div style="width: 18px; height: 18px; border: 2px solid var(--accent); border-top-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite;"></div>
		</div>
	{:else if !chartData}
		<div style="height: 188px; display: flex; align-items: center; justify-content: center; color: var(--text-faint); font-size: 13px;">No data for this period</div>
	{:else}
		<div style="position: relative;">
			<svg
				bind:this={svgEl}
				viewBox="0 0 900 188"
				style="width: 100%; height: 188px; display: block; overflow: visible; cursor: crosshair;"
				onmousemove={onMouseMove}
				onmouseleave={() => hoverIdx = null}
			>
				<defs>
					{#each chartData.layers as layer}
						<linearGradient id={layer.gradId} x1="0" y1="0" x2="0" y2="1">
							<stop offset="0%" stop-color={layer.color} stop-opacity="0.22" />
							<stop offset="100%" stop-color={layer.color} stop-opacity="0.03" />
						</linearGradient>
					{/each}
				</defs>

				{#each chartData.yTicks as tick}
					<line x1={cX1} y1={tick.y} x2={cX2} y2={tick.y} stroke="var(--border)" stroke-width="0.5" />
					<text x={cX1 - 5} y={tick.y + 3} text-anchor="end" font-size="9" fill="var(--text-faint)" font-family="JetBrains Mono, monospace">{tick.val}</text>
				{/each}
				<line x1={cX1} y1={cY2} x2={cX2} y2={cY2} stroke="var(--border)" stroke-width="1" />

				{#each chartData.layers as layer}
					<path d={layer.area} fill="url(#{layer.gradId})" />
				{/each}
				{#each chartData.layers as layer, i}
					<path d={layer.line} fill="none" stroke={layer.color}
						stroke-width={i === chartData.layers.length - 1 ? 2 : 1.5}
						stroke-opacity={i === 0 ? 0.5 : 0.8}
						stroke-dasharray={i === 0 ? '3 3' : 'none'}
					/>
				{/each}

				{#if hoverIdx !== null}
					{@const hx = chartData.xi(hoverIdx)}
					<line x1={hx} y1={cY1} x2={hx} y2={cY2} stroke="var(--text-faint)" stroke-width="1" stroke-dasharray="3 2" opacity="0.6" />
					{#each chartData.layers as layer}
						{#if layer.counts[hoverIdx] > 0}
							<circle cx={hx} cy={layer.topPts[hoverIdx].y} r="3.5" fill={layer.color} stroke="var(--bg-base)" stroke-width="1.5" />
						{/if}
					{/each}
				{/if}

				<circle cx={chartData.peakX} cy={chartData.peakY} r="4" fill="var(--accent)" stroke="var(--bg-base)" stroke-width="2" />
				<text x={chartData.peakX} y={chartData.peakY - 10} text-anchor="middle" font-size="10" fill="var(--accent)" font-family="JetBrains Mono, monospace" font-weight="bold">peak · {chartData.peakVal}</text>

				{#each chartData.xLabels as xl}
					<text x={xl.x} y="184" text-anchor={xl.anchor} font-size="9" fill="var(--text-faint)" font-family="JetBrains Mono, monospace">{xl.label}</text>
				{/each}
			</svg>

			{#if tooltip && hoverIdx !== null}
				{@const svgWidth = svgEl?.getBoundingClientRect().width ?? 900}
				{@const tipX = (tooltip.svgX / 900) * svgWidth}
				{@const flip = tipX > svgWidth * 0.65}
				<div style="position: absolute; top: 0; left: {tipX}px; transform: translate({flip ? 'calc(-100% - 10px)' : '10px'}, 4px); pointer-events: none; z-index: 20; background: var(--bg-base); border: 1px solid var(--border); border-radius: 8px; padding: 9px 12px; min-width: 150px; box-shadow: 0 4px 16px rgba(0,0,0,0.18);">
					<div class="flex items-baseline justify-between gap-4" style="margin-bottom: 7px;">
						<span style="font-size: 11px; font-weight: 700; color: var(--text-primary); font-family: 'JetBrains Mono', monospace;">{tooltip.date}</span>
						<span style="font-size: 11px; font-weight: 700; color: var(--accent); font-family: 'JetBrains Mono', monospace;">{tooltip.total}</span>
					</div>
					{#if tooltip.rows.length > 0}
						<div style="border-top: 1px solid var(--border-subtle); padding-top: 6px; display: flex; flex-direction: column; gap: 4px;">
							{#each tooltip.rows as row}
								<div class="flex items-center justify-between gap-3">
									<div class="flex items-center gap-1.5 min-w-0">
										<div style="width: 7px; height: 7px; border-radius: 2px; background: {row.color}; flex-shrink: 0;"></div>
										<span class="truncate" style="font-size: 10px; color: var(--text-secondary); font-family: 'JetBrains Mono', monospace;" title={row.label}>{row.label.length > 16 ? row.label.slice(0, 15) + '…' : row.label}</span>
									</div>
									<span style="font-size: 10px; font-weight: 600; color: var(--text-primary); font-family: 'JetBrains Mono', monospace; flex-shrink: 0;">{row.count}</span>
								</div>
							{/each}
						</div>
					{/if}
				</div>
			{/if}
		</div>
	{/if}
</div>
