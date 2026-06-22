<script lang="ts">
	import {
		Search,
		Zap,
		ExternalLink,
		TrendingUp,
		ArrowDownNarrowWide,
		ChevronDown,
		ChevronRight,
		LayoutGrid,
		LayoutList,
		Sparkles,
		Info
	} from 'lucide-svelte';
	import { tick, onMount, onDestroy } from 'svelte';
	import { navigating } from '$app/stores';
	import { browser } from '$app/environment';
	import { replaceState, beforeNavigate } from '$app/navigation';
	import SkillUsageTable from '$lib/components/skills/SkillUsageTable.svelte';
	import KarmaIcon from '$lib/components/icons/Icon.svelte';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import {
		getPluginColorVars,
		getSkillGroupColorVars,
		getSkillCategoryColorVars,
		getSkillChartHex,
		getSkillCategoryLabel,
		cleanSkillName
	} from '$lib/utils';
	import type { SkillUsage, UsageTrendResponse } from '$lib/api-types';
	import { API_BASE } from '$lib/config';

	let { data } = $props();

	function initParam(key: string, fallback: string): string {
		if (browser) return new URLSearchParams(window.location.search).get(key) ?? fallback;
		return fallback;
	}

	let activeView = $state<'overview' | 'analytics'>(
		(initParam('view', 'overview') as 'overview' | 'analytics')
	);
	let searchQuery = $state(initParam('search', ''));
	let selectedFilter = $state<'all' | 'bundled' | 'plugin' | 'custom'>(
		(initParam('filter', 'all') as 'all' | 'bundled' | 'plugin' | 'custom')
	);
	let selectedPlugin = $state<string | null>(null); // null = all plugins
	let sortBy = $state<'count' | 'session_count' | 'last_used'>('count');
	let showSortMenu = $state(false);

	$effect(() => {
		if (!browser) return;
		const v = activeView;
		const f = selectedFilter;
		const s = searchQuery;
		tick().then(() => {
			const url = new URL(window.location.href);
			if (v !== 'overview') url.searchParams.set('view', v);
			else url.searchParams.delete('view');
			if (f !== 'all') url.searchParams.set('filter', f);
			else url.searchParams.delete('filter');
			if (s.trim()) url.searchParams.set('search', s.trim());
			else url.searchParams.delete('search');
			replaceState(url.toString(), {});
		});
	});

	// ── Base data ──────────────────────────────────────────────────────────────
	let allSkills = $derived<SkillUsage[]>(data.usage || []);

	// ── Grouping (mirrors the original logic) ─────────────────────────────────
	interface SkillGroup {
		key: string;
		label: string;
		skills: SkillUsage[];
		pluginName: string | null;
		category: string;
	}

	let groupedSkills = $derived.by<SkillGroup[]>(() => {
		const groups = new Map<string, SkillGroup>();
		for (const skill of allSkills) {
			let key: string, label: string, pluginName: string | null = null, category: string;
			if (skill.category === 'bundled_skill') {
				key = 'bundled_skill'; label = 'Bundled Skills'; category = 'bundled_skill';
			} else if (skill.category === 'plugin_skill' && skill.plugin) {
				key = `plugin:${skill.plugin}`; label = skill.plugin; pluginName = skill.plugin; category = 'plugin_skill';
			} else if (skill.category === 'custom_skill') {
				key = 'custom_skill'; label = 'Custom Skills'; category = 'custom_skill';
			} else if (skill.is_plugin && skill.plugin) {
				key = `plugin:${skill.plugin}`; label = skill.plugin; pluginName = skill.plugin; category = 'plugin_skill';
			} else {
				key = 'custom_skill'; label = 'Custom Skills'; category = 'custom_skill';
			}
			if (!groups.has(key)) groups.set(key, { key, label, skills: [], pluginName, category });
			groups.get(key)!.skills.push(skill);
		}
		return Array.from(groups.values());
	});

	// ── Left panel: sorted by utilization% desc, then total invocations desc ──
	let leftPanelGroups = $derived.by(() => {
		return [...groupedSkills]
			.filter(g => {
				if (selectedFilter === 'bundled') return g.category === 'bundled_skill';
				if (selectedFilter === 'plugin') return g.category === 'plugin_skill';
				if (selectedFilter === 'custom') return g.category === 'custom_skill';
				return true;
			})
			.sort((a, b) => {
				const aUsed = a.skills.filter(s => s.count > 0).length;
				const bUsed = b.skills.filter(s => s.count > 0).length;
				const aPct = a.skills.length > 0 ? aUsed / a.skills.length : 0;
				const bPct = b.skills.length > 0 ? bUsed / b.skills.length : 0;
				if (Math.abs(bPct - aPct) > 0.001) return bPct - aPct;
				const aTotal = a.skills.reduce((sum, s) => sum + s.count, 0);
				const bTotal = b.skills.reduce((sum, s) => sum + s.count, 0);
				return bTotal - aTotal;
			});
	});

	// ── Stats ──────────────────────────────────────────────────────────────────
	let totalUses = $derived(allSkills.reduce((sum, s) => sum + s.count, 0));
	let activeSkillsCount = $derived(allSkills.filter(s => s.count > 0).length);
	let totalSkillsCount = $derived(allSkills.length);
	let neverUsedCount = $derived(allSkills.filter(s => s.count === 0).length);
	let topPlugin = $derived.by(() => {
		let best: SkillGroup | null = null;
		let bestTotal = 0;
		for (const g of groupedSkills) {
			const total = g.skills.reduce((sum, s) => sum + s.count, 0);
			if (total > bestTotal) { bestTotal = total; best = g; }
		}
		return best ? best.label : '—';
	});
	let globalMax = $derived(
		allSkills.length > 0 ? Math.max(...allSkills.map(s => s.count), 1) : 1
	);

	// ── Right panel: active skills, filtered + sorted ─────────────────────────
	let rightPanelSkills = $derived.by(() => {
		let skills = allSkills.filter(s => s.count > 0);

		if (selectedPlugin !== null) {
			if (selectedPlugin === 'bundled_skill') {
				skills = skills.filter(s => s.category === 'bundled_skill');
			} else if (selectedPlugin === 'custom_skill') {
				skills = skills.filter(s => s.category === 'custom_skill');
			} else {
				skills = skills.filter(s => s.plugin === selectedPlugin);
			}
		}

		if (selectedFilter === 'bundled') skills = skills.filter(s => s.category === 'bundled_skill');
		else if (selectedFilter === 'plugin') skills = skills.filter(s => s.category === 'plugin_skill');
		else if (selectedFilter === 'custom') skills = skills.filter(s => s.category === 'custom_skill');

		if (searchQuery.trim()) {
			const q = searchQuery.toLowerCase();
			skills = skills.filter(s =>
				s.name.toLowerCase().includes(q) ||
				(s.plugin && s.plugin.toLowerCase().includes(q))
			);
		}

		return skills.slice().sort((a, b) => {
			if (sortBy === 'session_count') return (b.session_count ?? 0) - (a.session_count ?? 0);
			if (sortBy === 'last_used') {
				return (b.last_used ? new Date(b.last_used).getTime() : 0) -
				       (a.last_used ? new Date(a.last_used).getTime() : 0);
			}
			return b.count - a.count;
		});
	});

	// ── All Skills tab: also applies type + search filters ────────────────────
	let filteredSkills = $derived.by(() => {
		let skills = allSkills;
		if (selectedFilter === 'bundled') skills = skills.filter(s => s.category === 'bundled_skill');
		else if (selectedFilter === 'plugin') skills = skills.filter(s => s.category === 'plugin_skill');
		else if (selectedFilter === 'custom') skills = skills.filter(s => s.category === 'custom_skill');
		if (searchQuery.trim()) {
			const q = searchQuery.toLowerCase();
			skills = skills.filter(s =>
				s.name.toLowerCase().includes(q) || (s.plugin && s.plugin.toLowerCase().includes(q))
			);
		}
		return skills;
	});

	// ── Analytics derived ─────────────────────────────────────────────────────
	let analyticsTotalInvocations = $derived(rightPanelSkills.reduce((sum, s) => sum + s.count, 0));
	let analyticsAvgPerSkill = $derived(
		rightPanelSkills.length > 0 ? Math.round(analyticsTotalInvocations / rightPanelSkills.length) : 0
	);
	let analyticsTop15 = $derived(rightPanelSkills.slice(0, 15));
	let analyticsBarMax = $derived(analyticsTop15.length > 0 ? analyticsTop15[0].count : 1);
	let analyticsPluginBreakdown = $derived.by(() => {
		const map = new Map<string, { label: string; count: number; color: string; subtle: string }>();
		for (const skill of rightPanelSkills) {
			const key = skill.plugin ?? skill.category ?? 'custom';
			const label = skill.plugin ?? (skill.category === 'bundled_skill' ? 'built-in' : 'custom');
			const colors = getSkillColors(skill);
			if (!map.has(key)) map.set(key, { label, count: 0, color: colors.color, subtle: colors.subtle });
			map.get(key)!.count += skill.count;
		}
		return [...map.values()].sort((a, b) => b.count - a.count);
	});
	let analyticsPluginTotal = $derived(analyticsPluginBreakdown.reduce((s, p) => s + p.count, 0));
	let trendOpen = $state(true);
	let trendRange = $state<'7d' | '30d' | '90d'>('90d');
	let trendData = $state<UsageTrendResponse | null>(null);
	let trendLoading = $state(false);
	let trendRangeUserOverride = $state(false);

	const periodMap: Record<'7d' | '30d' | '90d', string> = { '7d': 'week', '30d': 'month', '90d': 'quarter' };

	$effect(() => {
		if (!browser || activeView !== 'analytics') return;
		trendLoading = true;
		const url = new URL(`${API_BASE}/skills/usage/trend`);
		url.searchParams.set('period', periodMap[trendRange]);
		fetch(url)
			.then(r => r.json())
			.then(d => {
				trendData = d;
				// Auto-downgrade to highest range that has data (unless user manually chose)
				if (!trendRangeUserOverride) {
					const total = (d as UsageTrendResponse)?.total ?? 0;
					if (total === 0 && trendRange === '90d') trendRange = '30d';
					else if (total === 0 && trendRange === '30d') trendRange = '7d';
				}
			})
			.catch(() => {})
			.finally(() => { trendLoading = false; });
	});

	// Rebuild daily totals filtered by excludeFn
	let trendPoints = $derived.by(() => {
		if (!trendData) return [];
		const sorted = [...trendData.trend].sort((a, b) => new Date(a.date).getTime() - new Date(b.date).getTime());
		if (!excludeFn || !trendData.trend_by_item) return sorted;
		const dailyTotals = new Map<string, number>();
		for (const [name, points] of Object.entries(trendData.trend_by_item)) {
			if (excludeFn(name)) continue;
			for (const p of points) dailyTotals.set(p.date, (dailyTotals.get(p.date) ?? 0) + p.count);
		}
		return sorted.map(d => ({ date: d.date, count: dailyTotals.get(d.date) ?? 0 }));
	});

	// Just a sentinel so the template knows data is ready
	let sparklinePath = $derived(trendPoints.length >= 2 ? { W: 600, H: 180 } : null);

	// ── Chart helpers ─────────────────────────────────────────────────────────
	function catmullRomPath(pts: {x: number, y: number}[]): string {
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

	function stackedAreaPath(topPts: {x:number,y:number}[], botPts: {x:number,y:number}[] | null, baseY: number): { line: string; area: string } {
		const line = catmullRomPath(topPts);
		if (!botPts) {
			const last = topPts[topPts.length - 1];
			const first = topPts[0];
			return { line, area: `${line} L ${last.x.toFixed(1)},${baseY} L ${first.x.toFixed(1)},${baseY} Z` };
		}
		const revBot = [...botPts].reverse();
		const revLine = catmullRomPath(revBot);
		// Connect: end of top → start of reversed bottom via straight line, then smooth back
		const last = topPts[topPts.length - 1];
		const revFirst = revBot[0];
		return { line, area: `${line} L ${revFirst.x.toFixed(1)},${revFirst.y.toFixed(1)} ${revLine.replace(/^M [^C]*C/, 'C')} Z` };
	}

	// ── Stacked chart data ─────────────────────────────────────────────────────
	let stackedChartData = $derived.by(() => {
		if (!trendData?.trend_by_item || trendPoints.length === 0) return null;
		const dates = trendPoints.map(p => p.date);
		const cX1 = 48, cX2 = 892, cY1 = 8, cY2 = 156;
		const cW = cX2 - cX1, cH = cY2 - cY1;

		// Group trend_by_item by plugin
		const groupMap = new Map<string, { label: string; color: string; counts: number[] }>();
		for (const [skillName, skillPts] of Object.entries(trendData.trend_by_item)) {
			if (excludeFn && excludeFn(skillName)) continue;
			const skill = allSkills.find(s => s.name === skillName);
			if (!skill) continue;
			const key = skill.plugin ?? (skill.category === 'bundled_skill' ? 'built-in' : 'custom');
			const colors = getSkillColors(skill);
			if (!groupMap.has(key)) groupMap.set(key, { label: key, color: colors.color, counts: new Array(dates.length).fill(0) });
			const ptMap = new Map(skillPts.map(p => [p.date, p.count]));
			const g = groupMap.get(key)!;
			dates.forEach((d, i) => { g.counts[i] += ptMap.get(d) ?? 0; });
		}

		const groups = [...groupMap.values()].sort((a, b) =>
			b.counts.reduce((s, v) => s + v, 0) - a.counts.reduce((s, v) => s + v, 0)
		);
		if (groups.length === 0) return null;

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
			const { line, area } = stackedAreaPath(topPts, botPts, cY2);
			return { ...g, topPts, line, area, gradId: `sg${idx}` };
		});

		const peakIdx = dailyTotals.reduce((mi, v, i) => v > dailyTotals[mi] ? i : mi, 0);
		const totalInv = dailyTotals.reduce((s, v) => s + v, 0);

		const xIdxs = dates.length <= 7 ? dates.map((_, i) => i)
			: [0, Math.floor(dates.length * 0.25), Math.floor(dates.length * 0.5), Math.floor(dates.length * 0.75), dates.length - 1];

		return {
			layers,
			groups,
			dates,
			dailyTotals,
			peakX: xi(peakIdx),
			peakY: yv(dailyTotals[peakIdx]),
			peakVal: dailyTotals[peakIdx],
			peakDate: new Date(dates[peakIdx] + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
			totalInv,
			avgPerDay: (totalInv / dates.length).toFixed(1),
			yMax,
			yTicks: [1, 0.67, 0.33, 0].map(f => ({ y: cY2 - f * cH, val: Math.round(yMax * f) })),
			xLabels: xIdxs.map(i => ({
				x: xi(i),
				label: new Date(dates[i] + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
				anchor: (i === 0 ? 'start' : i === dates.length - 1 ? 'end' : 'middle') as 'start' | 'end' | 'middle'
			})),
			xi,
			cX1, cX2, cY1, cY2
		};
	});

	// ── Chart tooltip state ───────────────────────────────────────────────────
	let chartHoverIdx = $state<number | null>(null);
	let chartSvgEl = $state<SVGSVGElement | null>(null);

	function handleChartMouseMove(e: MouseEvent) {
		if (!stackedChartData || !chartSvgEl) return;
		const rect = chartSvgEl.getBoundingClientRect();
		const scaleX = 900 / rect.width;
		const mx = (e.clientX - rect.left) * scaleX;
		const { dates, xi, cX1, cX2 } = stackedChartData;
		if (mx < cX1 - 10 || mx > cX2 + 10) { chartHoverIdx = null; return; }
		// Find nearest date index
		let best = 0, bestDist = Infinity;
		dates.forEach((_, i) => { const d = Math.abs(xi(i) - mx); if (d < bestDist) { bestDist = d; best = i; } });
		chartHoverIdx = best;
	}

	let tooltipData = $derived.by(() => {
		if (chartHoverIdx === null || !stackedChartData) return null;
		const i = chartHoverIdx;
		const date = new Date(stackedChartData.dates[i] + 'T00:00:00').toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
		const total = stackedChartData.dailyTotals[i];
		const rows = stackedChartData.layers
			.filter(l => l.counts[i] > 0)
			.map(l => ({ label: l.label, count: l.counts[i], color: l.color }))
			.sort((a, b) => b.count - a.count);
		return { date, total, rows, x: stackedChartData.xi(i) };
	});

	// ── Session reach (left analytics panel) ──────────────────────────────────
	let sessionReachSkills = $derived(
		rightPanelSkills.slice().sort((a, b) => (b.session_count ?? 0) - (a.session_count ?? 0)).slice(0, 8)
	);
	let sessionReachMax = $derived(sessionReachSkills.length > 0 ? (sessionReachSkills[0].session_count ?? 1) : 1);

	// ── Insight banner ────────────────────────────────────────────────────────
	let insightText = $derived.by(() => {
		if (rightPanelSkills.length === 0) return null;
		const top = rightPanelSkills[0];
		const topName = cleanSkillName(top.name, top.is_plugin);
		const topSession = sessionReachSkills[0];
		const topSessionName = topSession ? cleanSkillName(topSession.name, topSession.is_plugin) : null;
		const diverse = sessionReachSkills.length > 1 ? sessionReachSkills.find(s => s.name !== top.name) : null;
		const diverseName = diverse ? cleanSkillName(diverse.name, diverse.is_plugin) : null;
		if (topSessionName && diverseName && topSessionName !== topName) {
			return { bold: `${topName} leads all invocations`, rest: ` · ${topSessionName} spans ${topSession?.session_count} sessions · ${diverseName} is your second most-reached habit` };
		}
		return { bold: `${rightPanelSkills.length} active skills`, rest: ` · ${topName} leads with ${top.count} invocations across ${top.session_count ?? 0} sessions` };
	});

	let excludeFn = $derived.by(() => {
		if (selectedFilter === 'all') return undefined;
		if (selectedFilter === 'bundled') return (name: string) => {
			const s = allSkills.find(x => x.name === name);
			return s?.category !== 'bundled_skill';
		};
		if (selectedFilter === 'plugin') return (name: string) => {
			const s = allSkills.find(x => x.name === name);
			return s?.category !== 'plugin_skill';
		};
		return (name: string) => {
			const s = allSkills.find(x => x.name === name);
			return s?.category !== 'custom_skill';
		};
	});

	// ── Helpers ────────────────────────────────────────────────────────────────
	// Compact relative date — no time component
	function shortDate(ts: string | null): string {
		if (!ts) return '—';
		const date = new Date(ts);
		const diffMs = Date.now() - date.getTime();
		const diffMins = Math.floor(diffMs / 60000);
		const diffHours = Math.floor(diffMins / 60);
		const diffDays = Math.floor(diffHours / 24);
		if (diffMins < 1) return 'now';
		if (diffMins < 60) return `${diffMins}m`;
		if (diffHours < 24) return `${diffHours}h`;
		if (diffDays < 7) return `${diffDays}d`;
		return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
	}

	function getGroupColors(group: SkillGroup) {
		if (group.key === 'bundled_skill') return getSkillCategoryColorVars('bundled_skill');
		if (group.key === 'custom_skill') return getSkillCategoryColorVars('custom_skill');
		return getSkillGroupColorVars(group.key);
	}

	function getSourceBadgeLabel(skill: SkillUsage): string {
		if (skill.category === 'bundled_skill') return 'built-in';
		if (skill.plugin) return skill.plugin;
		return 'custom';
	}

	function getSkillColors(skill: SkillUsage) {
		if (skill.category === 'bundled_skill') return getSkillCategoryColorVars('bundled_skill');
		if (skill.plugin) return getPluginColorVars(skill.plugin);
		return getSkillCategoryColorVars('custom_skill');
	}

	let coverageOpen = $state(false);
	let skillsView = $state<'list' | 'grid'>('list');

	function togglePlugin(group: SkillGroup) {
		const key = group.pluginName ?? group.key;
		if (selectedPlugin === key) selectedPlugin = null;
		else selectedPlugin = key;
	}

	const sortLabels: Record<string, string> = {
		count: 'Invocations ↓',
		session_count: 'Sessions ↓',
		last_used: 'Last Used'
	};

	// ── Scroll save/restore when navigating to skill detail ───────────────────
	const SCROLL_KEY = 'skills_scroll';

	beforeNavigate(({ to }) => {
		if (!browser) return;
		if (to?.route.id?.startsWith('/skills/')) {
			sessionStorage.setItem(SCROLL_KEY, String(window.scrollY));
		} else {
			sessionStorage.removeItem(SCROLL_KEY);
		}
	});

	onMount(() => {
		const saved = sessionStorage.getItem(SCROLL_KEY);
		if (saved !== null) {
			sessionStorage.removeItem(SCROLL_KEY);
			requestAnimationFrame(() => window.scrollTo({ top: Number(saved), behavior: 'instant' }));
		}
	});

	let isPageLoading = $derived(!!$navigating && $navigating.to?.route.id === '/skills');
</script>

{#if isPageLoading}
	<!-- Loading state: keep height so layout doesn't jump -->
	<div class="-mx-6 -my-8 flex items-center justify-center" style="height: calc(100vh - 56px);">
		<div class="flex flex-col items-center gap-3">
			<Zap size={32} class="text-[var(--accent)] animate-pulse" />
			<span class="text-sm text-[var(--text-muted)]">Loading skills…</span>
		</div>
	</div>
{:else}

<!-- ── Full-bleed split-view container ────────────────────────────────────── -->
<div
	class="-mx-6 -my-8 flex flex-col"
	style="{activeView === 'overview' ? 'height: calc(100vh - 56px); overflow: hidden;' : ''}"
>

	<!-- ── Page Header ──────────────────────────────────────────────────────── -->
	<div class="flex-shrink-0" style="padding: 0 24px; background: var(--bg-base);">
		<PageHeader
			title="Skills"
			iconName="skills"
			iconColor="--nav-orange"
			breadcrumbs={[{ label: 'Dashboard', href: '/' }, { label: 'Skills' }]}
			subtitle="Did I get value from this skill?"
		/>
	</div>

	<!-- ── Body ─────────────────────────────────────────────────────────────── -->

	<!-- Filter bar — always visible -->
	<div
		class="flex flex-shrink-0 items-center"
		style="padding: 8px 12px; gap: 10px; {activeView === 'analytics' ? 'position: sticky; top: 56px; z-index: 10; background: var(--bg-base); border-bottom: 1px solid var(--border-subtle);' : ''}"
	>
		<!-- Left group: view tabs — fixed width matching left panel -->
		<div
			class="flex rounded-lg p-0.5 flex-shrink-0"
			style="width: 280px; background: var(--bg-muted);"
			role="tablist"
			aria-label="View"
		>
			{#each ([['overview', 'Overview'], ['analytics', 'Analytics']] as const) as [val, lbl]}
				<button
					role="tab"
					aria-selected={activeView === val}
					onclick={() => activeView = val}
					class="flex-1 rounded-md transition-all"
					style="
						padding: 4px 8px;
						font-size: 11px;
						font-weight: {activeView === val ? '600' : '500'};
						color: {activeView === val ? 'var(--bg-base)' : 'var(--text-secondary)'};
						background: {activeView === val ? 'var(--text-primary)' : 'transparent'};
					"
				>{lbl}</button>
			{/each}
		</div>

		<!-- Right group: type chips + search — above right panel -->
		<div class="flex items-center gap-2 flex-1">
			<div class="flex items-center gap-1.5">
				{#each ([['all', 'All'], ['bundled', 'Bundled'], ['plugin', 'Plugin'], ['custom', 'Custom']] as const) as [val, lbl]}
					<button
						onclick={() => selectedFilter = val}
						class="rounded-full transition-all"
						style="
							padding: 4px 12px;
							font-size: 11px;
							font-weight: {selectedFilter === val ? '600' : '500'};
							color: {selectedFilter === val ? 'var(--accent)' : 'var(--text-secondary)'};
							background: {selectedFilter === val ? 'var(--accent-muted)' : 'transparent'};
							border: {selectedFilter === val ? '1.5px solid var(--accent-subtle)' : '1px solid var(--border)'};
						"
					>{lbl}</button>
				{/each}
			</div>
			<div class="relative ml-auto">
				<Search class="absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" size={12} style="color: var(--text-faint);" />
				<input
					type="text"
					bind:value={searchQuery}
					aria-label="Search skills"
					placeholder="Search skills…"
					style="width: 180px; padding: 4px 10px 4px 26px; font-size: 12px; background: var(--bg-subtle); border: 1px solid var(--border); border-radius: 8px; color: var(--text-primary); outline: none;"
					data-search-input
				/>
			</div>
		</div>
	</div>

	{#if activeView === 'overview'}
	<!-- Split view -->
	<div class="flex flex-1 min-h-0 overflow-hidden" style="padding: 0 12px 12px; gap: 10px;">

		<!-- ── Left Panel: Plugin Coverage ─────────────────────────────────── -->
		<div
			class="flex-shrink-0 flex flex-col"
			style="width: 280px; background: var(--bg-base); border: 1px solid var(--border); border-radius: 12px; overflow: hidden; align-self: flex-start;"
		>
			<!-- Panel header — accordion trigger -->
			<button
				class="w-full text-left flex-shrink-0 transition-colors hover:bg-[var(--bg-subtle)]"
				style="border-bottom: 1px solid {coverageOpen ? 'var(--border-subtle)' : 'transparent'}; padding: 14px 16px 12px;"
				onclick={() => coverageOpen = !coverageOpen}
			>
				<div class="flex items-center justify-between mb-2">
					<span style="font-size: 10px; font-weight: 700; color: var(--accent); text-transform: uppercase; letter-spacing: 0.12em; font-family: 'JetBrains Mono', monospace;">
						Plugin Coverage
					</span>
					<div style="color: var(--text-faint); transition: transform 0.2s; transform: rotate({coverageOpen ? 90 : 0}deg);">
						<ChevronRight size={13} />
					</div>
				</div>
				<!-- Stats: fill full width -->
				<div class="flex items-center w-full">
					<div class="flex flex-col flex-1 items-center">
						<span style="font-size: 22px; font-weight: 700; font-family: 'JetBrains Mono', monospace; color: var(--text-primary); letter-spacing: -1px;">{totalUses.toLocaleString()}</span>
						<span style="font-size: 9px; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.06em;">uses</span>
					</div>
					<div style="width: 1px; height: 32px; background: var(--border);"></div>
					<div class="flex flex-col flex-1 items-center">
						<span style="font-size: 22px; font-weight: 700; font-family: 'JetBrains Mono', monospace; color: var(--text-primary); letter-spacing: -1px;">{activeSkillsCount}<span style="font-size: 13px; font-weight: 500; color: var(--text-faint);">/{totalSkillsCount}</span></span>
						<span style="font-size: 9px; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.06em;">active</span>
					</div>
					{#if neverUsedCount > 0}
						<div style="width: 1px; height: 32px; background: var(--border);"></div>
						<div class="flex flex-col flex-1 items-center">
							<span style="font-size: 22px; font-weight: 700; font-family: 'JetBrains Mono', monospace; color: var(--nav-orange); letter-spacing: -1px;">{neverUsedCount}</span>
							<span style="font-size: 9px; color: var(--nav-orange); text-transform: uppercase; letter-spacing: 0.06em; opacity: 0.8;">unused</span>
						</div>
					{/if}
				</div>
			</button>

			<!-- Plugin rows — only when accordion is open -->
			{#if coverageOpen}
			<div class="flex-1 overflow-y-auto">
				{#each leftPanelGroups as group}
					{@const colors = getGroupColors(group)}
					{@const usedCount = group.skills.filter(s => s.count > 0).length}
					{@const totalCount = group.skills.length}
					{@const utilPct = totalCount > 0 ? Math.round((usedCount / totalCount) * 100) : 0}
					{@const isNeverUsed = usedCount === 0}
					{@const pluginKey = group.pluginName ?? group.key}
					{@const isSelected = selectedPlugin === pluginKey}
					{@const isTopPlugin = group.label === topPlugin}
					{@const pctColor = isNeverUsed ? 'var(--text-faint)' : utilPct === 100 ? 'var(--nav-green)' : utilPct >= 50 ? 'var(--text-secondary)' : 'var(--text-faint)'}
					<div
						role="button"
						tabindex="0"
						onclick={() => togglePlugin(group)}
						onkeydown={(e) => e.key === 'Enter' && togglePlugin(group)}
						class="border-b cursor-pointer group/row transition-colors"
						style="
							padding: 10px 20px;
							border-color: var(--border-subtle);
							background: {isSelected ? 'var(--accent-muted)' : 'transparent'};
							border-left: {isSelected ? '2px solid var(--accent)' : '2px solid transparent'};
							opacity: {isNeverUsed ? 0.45 : 1};
						"
					>
						<!-- Name row -->
						<div class="flex items-center justify-between gap-2" style="margin-bottom: 6px;">
							<span class="flex-1 min-w-0 truncate" style="font-size: 12px; font-weight: 600; color: var(--text-primary); font-family: 'JetBrains Mono', monospace;">
								{group.label}
							</span>
							<div class="flex items-center gap-1.5 flex-shrink-0">
								{#if isTopPlugin}
									<TrendingUp size={10} style="color: var(--nav-orange);" />
								{/if}
								{#if group.pluginName}
									<a
										href="/plugins/{encodeURIComponent(group.pluginName)}"
										onclick={(e) => e.stopPropagation()}
										class="opacity-0 group-hover/row:opacity-100 transition-opacity"
										title="View plugin"
										style="color: var(--text-faint);"
									>
										<ExternalLink size={10} />
									</a>
								{/if}
								<span style="font-size: 12px; font-weight: 700; font-family: 'JetBrains Mono', monospace; color: {pctColor};">
									{utilPct}%
								</span>
							</div>
						</div>

						<!-- Bar + count -->
						<div class="flex items-center gap-2">
							<div class="flex-1" style="height: 3px; border-radius: 2px; background: var(--bg-muted); overflow: hidden;">
								{#if !isNeverUsed}
									<div style="height: 100%; border-radius: 2px; width: {utilPct}%; background: var(--accent); opacity: 0.5;"></div>
								{/if}
							</div>
							<span style="font-size: 10px; color: var(--text-faint); font-family: 'JetBrains Mono', monospace; flex-shrink: 0;">
								{usedCount}/{totalCount}
							</span>
						</div>
					</div>
				{/each}
			</div>

			<!-- Sort footer -->
			<div class="flex-shrink-0 border-t flex items-center justify-between" style="padding: 10px 16px; border-color: var(--border-subtle);">
				<span style="font-size: 10px; color: var(--text-faint);">Sorted by utilization</span>
				{#if selectedPlugin !== null}
					<button onclick={() => selectedPlugin = null} style="font-size: 10px; color: var(--accent); font-weight: 600;">
						Clear ×
					</button>
				{/if}
			</div>
			{/if}
		</div>

		<!-- ── Right Panel: Top Skills Leaderboard ──────────────────────────── -->
		<div class="flex-1 flex flex-col overflow-hidden min-w-0" style="background: var(--bg-base); border: 1px solid var(--border); border-radius: 12px;">

			<!-- Panel header -->
			<div
				class="flex-shrink-0 flex items-center justify-between border-b"
				style="padding: 14px 16px 12px; background: var(--bg-base); border-color: var(--border);"
			>
				<div>
					<div style="font-size: 10px; font-weight: 700; color: var(--accent); text-transform: uppercase; letter-spacing: 0.12em; font-family: 'JetBrains Mono', monospace; margin-bottom: 3px;">Top Skills</div>
					<div style="font-size: 11px; color: var(--text-faint);">
						{#if selectedPlugin !== null}
							{@const pg = leftPanelGroups.find(g => (g.pluginName ?? g.key) === selectedPlugin)}
							{rightPanelSkills.length} skills · {pg?.label ?? selectedPlugin}
						{:else}
							{rightPanelSkills.length} active skills ranked by usage
						{/if}
					</div>
				</div>

				<!-- View toggle + Sort dropdown -->
				<div class="flex items-center gap-2">
				<!-- List/Grid toggle -->
				<div class="flex rounded-md overflow-hidden" style="border: 1px solid var(--border);">
					<button
						onclick={() => skillsView = 'list'}
						style="padding: 5px 8px; background: {skillsView === 'list' ? 'var(--bg-muted)' : 'transparent'}; color: {skillsView === 'list' ? 'var(--text-primary)' : 'var(--text-faint)'}; display: flex; align-items: center;"
						title="List view"
					><LayoutList size={13} /></button>
					<button
						onclick={() => skillsView = 'grid'}
						style="padding: 5px 8px; background: {skillsView === 'grid' ? 'var(--bg-muted)' : 'transparent'}; color: {skillsView === 'grid' ? 'var(--text-primary)' : 'var(--text-faint)'}; display: flex; align-items: center; border-left: 1px solid var(--border);"
						title="Grid view"
					><LayoutGrid size={13} /></button>
				</div>

				<!-- Sort dropdown -->
				<div class="relative">
					<button
						onclick={() => showSortMenu = !showSortMenu}
						class="flex items-center gap-1.5 rounded-lg transition-colors"
						style="padding: 5px 10px; background: var(--bg-base); border: 1px solid var(--border); font-size: 11px; font-weight: 500; color: var(--text-secondary);"
					>
						<ArrowDownNarrowWide size={12} style="color: var(--text-faint);" />
						{sortLabels[sortBy]}
						<ChevronDown size={11} style="color: var(--text-faint);" />
					</button>
					{#if showSortMenu}
						<!-- svelte-ignore a11y_no_static_element_interactions -->
						<div
							class="absolute right-0 top-full mt-1 rounded-lg border shadow-lg z-10 overflow-hidden"
							style="background: var(--bg-base); border-color: var(--border); min-width: 160px;"
							onmouseleave={() => showSortMenu = false}
						>
							{#each (['count', 'session_count', 'last_used'] as const) as key}
								<button
									class="w-full text-left px-3 py-2 transition-colors hover:bg-[var(--bg-subtle)]"
									style="font-size: 12px; color: {sortBy === key ? 'var(--accent)' : 'var(--text-secondary)'}; font-weight: {sortBy === key ? '600' : '400'};"
									onclick={() => { sortBy = key; showSortMenu = false; }}
								>
									{sortLabels[key]}
								</button>
							{/each}
						</div>
					{/if}
				</div>
				</div>
			</div>

			<!-- Table container -->
			<div class="flex-1 overflow-y-auto">
				{#if rightPanelSkills.length === 0}
					<div class="flex flex-col items-center justify-center h-full gap-3">
						<Search size={36} style="color: var(--text-faint);" />
						<p style="font-size: 13px; color: var(--text-secondary); font-weight: 500;">No matching skills</p>
						<p style="font-size: 11px; color: var(--text-faint);">Try adjusting filters or search</p>
					</div>
				{:else if skillsView === 'list'}
					<!-- Column headers -->
					<div
						class="grid sticky top-0 border-b"
						style="background: var(--bg-base); border-color: var(--border); grid-template-columns: 32px 1fr 160px 100px 56px 64px 72px; padding: 10px 12px 8px;"
					>
						<div style="font-size: 10px; color: var(--text-faint); letter-spacing: 0.06em; text-transform: uppercase; text-align: center;">#</div>
						<div style="font-size: 10px; color: var(--text-faint); letter-spacing: 0.06em; text-transform: uppercase;">Skill</div>
						<div style="font-size: 10px; color: var(--text-faint); letter-spacing: 0.06em; text-transform: uppercase;">Source</div>
						<div style="font-size: 10px; color: var(--text-faint); letter-spacing: 0.06em; text-transform: uppercase; padding: 0 8px;">Invocations</div>
						<div style="font-size: 10px; color: var(--text-faint); letter-spacing: 0.06em; text-transform: uppercase; text-align: right;">Uses</div>
						<div style="font-size: 10px; color: var(--text-faint); letter-spacing: 0.06em; text-transform: uppercase; text-align: right;">Sessions</div>
						<div style="font-size: 10px; color: var(--text-faint); letter-spacing: 0.06em; text-transform: uppercase; text-align: right;">Last used</div>
					</div>

					<!-- Skill rows -->
					{#each rightPanelSkills as skill, i (skill.name)}
						{@const displayName = cleanSkillName(skill.name, skill.is_plugin)}
						{@const barWidth = Math.round((skill.count / globalMax) * 100)}
						{@const sourceBadge = getSourceBadgeLabel(skill)}
						{@const colors = getSkillColors(skill)}
						{@const useColor = selectedFilter === 'plugin' && skill.is_plugin}
						<a
							href="/skills/{encodeURIComponent(skill.name)}"
							class="grid border-b transition-colors hover:bg-[var(--bg-subtle)] no-underline"
							style="grid-template-columns: 32px 1fr 160px 100px 56px 64px 72px; padding: 8px 12px; border-color: var(--border-subtle); align-items: center;"
						>
							<div style="font-size: 11px; color: var(--text-faint); font-family: 'JetBrains Mono', monospace; text-align: center;">{i + 1}</div>
							<div class="min-w-0 pr-3">
								<span class="truncate block" style="font-size: 13px; font-weight: 600; color: var(--text-primary); font-family: 'JetBrains Mono', monospace;" title={displayName}>{displayName}</span>
							</div>
							<div class="min-w-0">
								{#if useColor && skill.plugin}
									<span class="truncate block rounded" style="font-size: 10px; font-weight: 700; font-family: 'JetBrains Mono', monospace; padding: 2px 7px; color: var(--bg-base); background: {colors.color}; display: inline-block; max-width: 100%;" title={skill.plugin}>{skill.plugin}</span>
								{:else}
									<span class="truncate block" style="font-size: 11px; color: var(--text-secondary); font-family: 'JetBrains Mono', monospace;" title={sourceBadge}>{sourceBadge}</span>
								{/if}
							</div>
							<div style="padding: 0 8px;">
								<div style="background: var(--bg-muted); height: 4px; border-radius: 2px; overflow: hidden;">
									<div style="height: 100%; border-radius: 2px; width: {barWidth}%; background: {useColor ? colors.color : 'var(--accent)'}; opacity: 0.7;"></div>
								</div>
							</div>
							<div style="font-size: 13px; font-weight: 700; font-family: 'JetBrains Mono', monospace; text-align: right; color: {useColor ? colors.color : 'var(--text-primary)'};">{skill.count}</div>
							<div style="font-size: 12px; color: var(--text-secondary); font-family: 'JetBrains Mono', monospace; text-align: right;">{skill.session_count ?? 0}</div>
							<div style="font-size: 11px; font-weight: 500; color: var(--text-secondary); font-family: 'JetBrains Mono', monospace; text-align: right;">{shortDate(skill.last_used)}</div>
						</a>
					{/each}
				{:else}
					<!-- Grid view -->
					<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 8px; padding: 12px;">
						{#each rightPanelSkills as skill, i (skill.name)}
							{@const displayName = cleanSkillName(skill.name, skill.is_plugin)}
							{@const barWidth = Math.round((skill.count / globalMax) * 100)}
							{@const sourceBadge = getSourceBadgeLabel(skill)}
							{@const colors = getSkillColors(skill)}
							{@const useColor = selectedFilter === 'plugin' && skill.is_plugin}
							<a
								href="/skills/{encodeURIComponent(skill.name)}"
								class="flex flex-col no-underline rounded-lg transition-all"
								style="padding: 14px 14px 12px; gap: 6px;
									border: 1px solid {useColor ? colors.subtle : 'var(--border-subtle)'};
									background: {useColor ? colors.subtle : 'var(--bg-subtle)'};"
								onmouseenter={(e) => { (e.currentTarget as HTMLElement).style.borderColor = useColor ? colors.color : 'var(--border)'; (e.currentTarget as HTMLElement).style.background = useColor ? colors.subtle : 'var(--bg-base)'; }}
								onmouseleave={(e) => { (e.currentTarget as HTMLElement).style.borderColor = useColor ? colors.subtle : 'var(--border-subtle)'; (e.currentTarget as HTMLElement).style.background = useColor ? colors.subtle : 'var(--bg-subtle)'; }}
							>
								<!-- Count — hero -->
								<div style="font-size: 28px; font-weight: 800; font-family: 'JetBrains Mono', monospace; letter-spacing: -1px; line-height: 1;
									color: {useColor ? colors.color : 'var(--accent)'};">
									{skill.count}
								</div>

								<!-- Skill name -->
								<div class="min-w-0" style="margin-top: 2px;">
									<span class="block truncate" style="font-size: 12px; font-weight: 600; color: var(--text-primary); font-family: 'JetBrains Mono', monospace;" title={displayName}>{displayName}</span>
								</div>

								<!-- Bar -->
								<div style="background: var(--bg-muted); height: 3px; border-radius: 2px; overflow: hidden; margin-top: 4px;">
									<div style="height: 100%; border-radius: 2px; width: {barWidth}%; background: {useColor ? colors.color : 'var(--accent)'}; opacity: 0.7;"></div>
								</div>

								<!-- Footer: source · last used -->
								<div class="flex items-center justify-between" style="margin-top: 2px; gap: 4px;">
									{#if useColor && skill.plugin}
										<span
											class="truncate rounded"
											style="font-size: 10px; font-weight: 700; font-family: 'JetBrains Mono', monospace; padding: 2px 7px; color: var(--bg-base); background: {colors.color}; flex-shrink: 1; min-width: 0;"
											title={skill.plugin}
										>{skill.plugin}</span>
									{:else}
										<span style="font-size: 10px; color: var(--text-secondary); font-family: 'JetBrains Mono', monospace;" class="truncate">{sourceBadge}</span>
									{/if}
									<span class="flex items-center gap-1 flex-shrink-0" style="color: var(--text-faint);">
									<svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
									<span style="font-size: 10px; font-weight: 500; font-family: 'JetBrains Mono', monospace;">{shortDate(skill.last_used)}</span>
								</span>
								</div>
							</a>
						{/each}
					</div>
				{/if}
			</div>
		</div>

	</div>

	{:else}

	<!-- Analytics view -->
	<div style="padding: 18px 24px 64px; display: flex; flex-direction: column; gap: 14px;">

		<!-- Insight banner -->
		{#if insightText}
			<div class="flex items-center gap-3 rounded-lg" style="padding: 10px 16px; background: linear-gradient(135deg, var(--accent-muted), color-mix(in oklch, var(--accent-muted), var(--bg-subtle) 50%)); border: 1px solid var(--accent-subtle);">
				<Sparkles size={14} style="color: var(--accent); flex-shrink: 0;" />
				<span style="font-size: 12px; color: var(--text-primary); line-height: 1.5;">
					<strong>{insightText.bold}</strong>{insightText.rest}
				</span>
			</div>
		{/if}

		<!-- Stacked area chart -->
		<div class="rounded-lg" style="padding: 16px 18px; background: var(--bg-base); border: 1px solid var(--border);">
			<!-- Header -->
			<div class="flex items-start justify-between" style="margin-bottom: 12px;">
				<div>
					<div style="font-size: 10px; font-weight: 700; color: var(--accent); text-transform: uppercase; letter-spacing: 0.12em; font-family: 'JetBrains Mono', monospace; margin-bottom: 5px;">Skill Invocations Over Time</div>
					{#if stackedChartData}
						<div class="flex items-center gap-4">
							<span style="font-size: 11px; color: var(--text-faint); font-family: 'JetBrains Mono', monospace;"><span style="font-weight: 700; color: var(--text-primary);">{stackedChartData.totalInv}</span> total</span>
							<span style="font-size: 11px; color: var(--text-faint); font-family: 'JetBrains Mono', monospace;"><span style="font-weight: 700; color: var(--text-primary);">{stackedChartData.avgPerDay}</span>/day avg</span>
							<span style="font-size: 11px; color: var(--text-faint); font-family: 'JetBrains Mono', monospace;">peak <span style="font-weight: 700; color: var(--text-primary);">{stackedChartData.peakVal}</span> on {stackedChartData.peakDate}</span>
						</div>
					{/if}
				</div>
				<div class="flex items-center gap-3">
					<!-- Legend -->
					{#if stackedChartData}
						<div class="flex items-center gap-2">
							{#each stackedChartData.groups.slice(0, 4) as g}
								<div class="flex items-center gap-1.5">
									<div style="width: 8px; height: 8px; border-radius: 2px; background: {g.color}; flex-shrink: 0;"></div>
									<span style="font-size: 10px; color: var(--text-faint);" class="truncate" title={g.label}>{g.label.length > 12 ? g.label.slice(0, 11) + '…' : g.label}</span>
								</div>
							{/each}
							{#if stackedChartData.groups.length > 4}
								<span style="font-size: 10px; color: var(--text-faint);">+{stackedChartData.groups.length - 4} more</span>
							{/if}
						</div>
					{/if}
					<!-- Range tabs -->
					<div class="flex overflow-hidden rounded" style="border: 1px solid var(--border);">
						{#each (['7d', '30d', '90d'] as const) as r}
							<button
								onclick={() => { trendRangeUserOverride = true; trendRange = r; }}
								style="padding: 4px 10px; font-size: 11px; font-weight: {trendRange === r ? '700' : '500'}; font-family: 'JetBrains Mono', monospace; background: {trendRange === r ? 'var(--accent-muted)' : 'var(--bg-subtle)'}; color: {trendRange === r ? 'var(--accent)' : 'var(--text-faint)'}; {r !== '90d' ? 'border-right: 1px solid var(--border);' : ''}"
							>{r}</button>
						{/each}
					</div>
				</div>
			</div>

			<!-- SVG stacked area chart -->
			{#if trendLoading && !trendData}
				<div style="height: 188px; display: flex; align-items: center; justify-content: center;">
					<div style="width: 18px; height: 18px; border: 2px solid var(--accent); border-top-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite;"></div>
				</div>
			{:else if !stackedChartData}
				<div style="height: 188px; display: flex; align-items: center; justify-content: center; color: var(--text-faint); font-size: 13px;">No data for this period</div>
			{:else}
				<!-- Chart container: relative for tooltip positioning -->
				<div style="position: relative;">
					<svg
						bind:this={chartSvgEl}
						viewBox="0 0 900 188"
						style="width: 100%; height: 188px; display: block; overflow: visible; cursor: crosshair;"
						onmousemove={handleChartMouseMove}
						onmouseleave={() => chartHoverIdx = null}
					>
						<defs>
							{#each stackedChartData.layers as layer}
								<linearGradient id={layer.gradId} x1="0" y1="0" x2="0" y2="1">
									<stop offset="0%" stop-color={layer.color} stop-opacity="0.22" />
									<stop offset="100%" stop-color={layer.color} stop-opacity="0.03" />
								</linearGradient>
							{/each}
						</defs>

						<!-- Gridlines -->
						{#each stackedChartData.yTicks as tick}
							<line x1={stackedChartData.cX1} y1={tick.y} x2={stackedChartData.cX2} y2={tick.y} stroke="var(--border)" stroke-width="0.5" />
							<text x={stackedChartData.cX1 - 5} y={tick.y + 3} text-anchor="end" font-size="9" fill="var(--text-faint)" font-family="JetBrains Mono, monospace">{tick.val}</text>
						{/each}
						<line x1={stackedChartData.cX1} y1={stackedChartData.cY2} x2={stackedChartData.cX2} y2={stackedChartData.cY2} stroke="var(--border)" stroke-width="1" />

						<!-- Area fills (bottom layer first) -->
						{#each stackedChartData.layers as layer}
							<path d={layer.area} fill="url(#{layer.gradId})" />
						{/each}

						<!-- Top lines per layer -->
						{#each stackedChartData.layers as layer, i}
							<path d={layer.line} fill="none" stroke={layer.color}
								stroke-width={i === stackedChartData.layers.length - 1 ? 2 : 1.5}
								stroke-opacity={i === 0 ? 0.5 : 0.8}
								stroke-dasharray={i === 0 ? '3 3' : 'none'}
							/>
						{/each}

						<!-- Hover crosshair -->
						{#if chartHoverIdx !== null}
							{@const hx = stackedChartData.xi(chartHoverIdx)}
							<line x1={hx} y1={stackedChartData.cY1} x2={hx} y2={stackedChartData.cY2} stroke="var(--text-faint)" stroke-width="1" stroke-dasharray="3 2" opacity="0.6" />
							<!-- Dots at each layer's top for hover index -->
							{#each stackedChartData.layers as layer}
								{@const cumY = layer.topPts?.[chartHoverIdx]?.y}
								{#if cumY !== undefined && layer.counts[chartHoverIdx] > 0}
									<circle cx={hx} cy={cumY} r="3.5" fill={layer.color} stroke="var(--bg-base)" stroke-width="1.5" />
								{/if}
							{/each}
						{/if}

						<!-- Peak annotation -->
						{#if chartHoverIdx !== stackedChartData.peakX}
							<circle cx={stackedChartData.peakX} cy={stackedChartData.peakY} r="4" fill="var(--accent)" stroke="var(--bg-base)" stroke-width="2" />
							<text x={stackedChartData.peakX} y={stackedChartData.peakY - 10} text-anchor="middle" font-size="10" fill="var(--accent)" font-family="JetBrains Mono, monospace" font-weight="bold">peak · {stackedChartData.peakVal}</text>
						{/if}

						<!-- X-axis labels -->
						{#each stackedChartData.xLabels as xl}
							<text x={xl.x} y="184" text-anchor={xl.anchor} font-size="9" fill="var(--text-faint)" font-family="JetBrains Mono, monospace">{xl.label}</text>
						{/each}
					</svg>

					<!-- Tooltip -->
					{#if tooltipData && chartHoverIdx !== null}
						{@const svgWidth = chartSvgEl?.getBoundingClientRect().width ?? 900}
						{@const tipX = (tooltipData.x / 900) * svgWidth}
						{@const flipLeft = tipX > svgWidth * 0.65}
						<div
							style="
								position: absolute;
								top: 0;
								left: {tipX}px;
								transform: translate({flipLeft ? 'calc(-100% - 10px)' : '10px'}, 4px);
								pointer-events: none;
								z-index: 20;
								background: var(--bg-base);
								border: 1px solid var(--border);
								border-radius: 8px;
								padding: 9px 12px;
								min-width: 150px;
								box-shadow: 0 4px 16px rgba(0,0,0,0.18);
							"
						>
							<!-- Date + total -->
							<div class="flex items-baseline justify-between gap-4" style="margin-bottom: 7px;">
								<span style="font-size: 11px; font-weight: 700; color: var(--text-primary); font-family: 'JetBrains Mono', monospace;">{tooltipData.date}</span>
								<span style="font-size: 11px; font-weight: 700; color: var(--accent); font-family: 'JetBrains Mono', monospace;">{tooltipData.total}</span>
							</div>
							{#if tooltipData.rows.length > 0}
								<div style="border-top: 1px solid var(--border-subtle); padding-top: 6px; display: flex; flex-direction: column; gap: 4px;">
									{#each tooltipData.rows as row}
										<div class="flex items-center justify-between gap-3">
											<div class="flex items-center gap-1.5 min-w-0">
												<div style="width: 7px; height: 7px; border-radius: 2px; background: {row.color}; flex-shrink: 0;"></div>
												<span class="truncate" style="font-size: 10px; color: var(--text-secondary); font-family: 'JetBrains Mono', monospace;" title={row.label}>{row.label.length > 16 ? row.label.slice(0, 15) + '…' : row.label}</span>
											</div>
											<span style="font-size: 10px; font-weight: 600; color: var(--text-primary); font-family: 'JetBrains Mono', monospace; flex-shrink: 0;">{row.count}</span>
										</div>
									{/each}
								</div>
							{:else}
								<div style="font-size: 10px; color: var(--text-faint); padding-top: 4px;">No activity</div>
							{/if}
						</div>
					{/if}
				</div>
			{/if}
		</div>

		<!-- Bottom row: Session Reach + Cost -->
		<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 14px; align-items: start;">

			<!-- Session Reach panel -->
			<div class="rounded-lg" style="padding: 16px 18px; background: var(--bg-base); border: 1px solid var(--border);">
				<div style="font-size: 10px; font-weight: 700; color: var(--accent); text-transform: uppercase; letter-spacing: 0.12em; font-family: 'JetBrains Mono', monospace; margin-bottom: 2px;">Session Reach</div>
				<div style="font-size: 11px; color: var(--text-faint); margin-bottom: 14px;">which skills are embedded in your workflow</div>

				{#if sessionReachSkills.length === 0}
					<div style="color: var(--text-faint); font-size: 12px; padding: 12px 0;">No data</div>
				{:else}
					<!-- Column headers -->
					<div style="display: grid; grid-template-columns: 1fr 80px 44px; gap: 8px; padding: 0 4px; margin-bottom: 6px;">
						<div style="font-size: 9px; color: var(--text-faint); letter-spacing: 0.1em; text-transform: uppercase;">Skill</div>
						<div style="font-size: 9px; color: var(--text-faint); letter-spacing: 0.1em; text-transform: uppercase; text-align: center;">sessions</div>
						<div style="font-size: 9px; color: var(--text-faint); letter-spacing: 0.1em; text-transform: uppercase; text-align: right;">reach</div>
					</div>
					<div style="border-top: 1px solid var(--border-subtle); padding-top: 4px;">
						{#each sessionReachSkills as skill}
							{@const colors = getSkillColors(skill)}
							{@const sessions = skill.session_count ?? 0}
							{@const barPct = Math.round((sessions / sessionReachMax) * 100)}
							{@const reachPct = analyticsTotalInvocations > 0 ? Math.round((sessions / analyticsTotalInvocations) * 100) : 0}
							{@const displayName = cleanSkillName(skill.name, skill.is_plugin)}
							<a
								href="/skills/{encodeURIComponent(skill.name)}"
								class="no-underline"
								style="display: grid; grid-template-columns: 1fr 80px 44px; gap: 8px; align-items: center; padding: 5px 4px; border-radius: 4px; cursor: pointer;"
								onmouseenter={(e) => (e.currentTarget as HTMLElement).style.background = 'var(--bg-subtle)'}
								onmouseleave={(e) => (e.currentTarget as HTMLElement).style.background = 'transparent'}
							>
								<div class="flex items-center gap-1.5 min-w-0">
									<div style="width: 5px; height: 5px; border-radius: 50%; background: {colors.color}; flex-shrink: 0;"></div>
									<span class="truncate" style="font-size: 12px; font-weight: 600; color: var(--text-primary); font-family: 'JetBrains Mono', monospace;" title={displayName}>{displayName}</span>
								</div>
								<div style="background: var(--bg-muted); height: 5px; border-radius: 3px; overflow: hidden;">
									<div style="height: 100%; border-radius: 3px; width: {barPct}%; background: var(--accent);"></div>
								</div>
								<div style="font-size: 10px; font-weight: 700; color: {reachPct >= 30 ? 'var(--accent)' : 'var(--text-faint)'}; text-align: right; font-family: 'JetBrains Mono', monospace;">{sessions}</div>
							</a>
						{/each}
					</div>
					<div style="margin-top: 10px; border-top: 1px solid var(--border-subtle); padding-top: 8px; font-size: 10px; color: var(--text-faint); line-height: 1.5;">
						Sessions count how many unique conversations triggered each skill — a high count means it's woven into your day-to-day
					</div>
				{/if}
			</div>

			<!-- Cost panel -->
			{#if true}
				{@const avgTokens = 500}
				{@const pricePerMTok = 3.00}
				{@const top5 = rightPanelSkills.slice(0, 5)}
				{@const top5Total = top5.reduce((s, sk) => s + sk.count, 0)}
				{@const allTotal = analyticsTotalInvocations}
				{@const costMax = top5.length > 0 ? top5[0].count : 1}
				{@const otherCount = allTotal - top5Total}
				{@const estTotalCost = (allTotal * avgTokens * pricePerMTok) / 1_000_000}
				{@const perInv = allTotal > 0 ? (estTotalCost / allTotal) : 0}
			<div class="rounded-lg" style="padding: 16px 18px; background: var(--bg-base); border: 1px solid var(--border);">
				<div style="font-size: 10px; font-weight: 700; color: var(--accent); text-transform: uppercase; letter-spacing: 0.12em; font-family: 'JetBrains Mono', monospace; margin-bottom: 2px;">Estimated Cost</div>
				<div style="font-size: 11px; color: var(--text-faint); margin-bottom: 12px;">across {allTotal} invocations this period</div>

				<!-- Hero total -->
				<div class="flex items-baseline gap-2" style="margin-bottom: 4px;">
					<span style="font-size: 32px; font-weight: 700; color: var(--text-primary); font-family: 'JetBrains Mono', monospace; letter-spacing: -1.5px;">~${estTotalCost < 0.01 ? estTotalCost.toFixed(4) : estTotalCost.toFixed(2)}</span>
					<span style="font-size: 12px; color: var(--text-faint);">total</span>
				</div>
				<div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 14px; font-family: 'JetBrains Mono', monospace;">~${perInv.toFixed(4)} per invocation avg</div>

				<!-- Callout -->
				<div class="flex gap-2 rounded" style="padding: 7px 10px; margin-bottom: 14px; background: var(--nav-orange-subtle); border: 1px solid color-mix(in oklch, var(--nav-orange) 30%, transparent);">
					<Info size={12} style="color: var(--nav-orange); flex-shrink: 0; margin-top: 1px;" />
					<span style="font-size: 10px; color: var(--nav-orange); line-height: 1.5;">Using ~500 tokens/invocation avg · actual cost varies by model and skill file size</span>
				</div>

				<!-- Column headers -->
				<div style="display: grid; grid-template-columns: 1fr 1fr 40px 68px; gap: 10px; padding: 0 4px; margin-bottom: 6px;">
					<div style="font-size: 9px; color: var(--text-faint); letter-spacing: 0.1em; text-transform: uppercase;">Skill</div>
					<div style="font-size: 9px; color: var(--text-faint); letter-spacing: 0.1em; text-transform: uppercase;">Cost share</div>
					<div style="font-size: 9px; color: var(--text-faint); letter-spacing: 0.1em; text-transform: uppercase; text-align: right;">%</div>
					<div style="font-size: 9px; color: var(--text-faint); letter-spacing: 0.1em; text-transform: uppercase; text-align: right;">Est. cost</div>
				</div>

				{#each top5 as skill}
					{@const skillCost = (skill.count * avgTokens * pricePerMTok) / 1_000_000}
					{@const pct = allTotal > 0 ? Math.round((skill.count / allTotal) * 100) : 0}
					{@const barPct = Math.round((skill.count / costMax) * 100)}
					{@const displayName = cleanSkillName(skill.name, skill.is_plugin)}
					<a
						href="/skills/{encodeURIComponent(skill.name)}"
						class="no-underline cost-row"
						style="display: grid; grid-template-columns: 1fr 1fr 40px 68px; gap: 10px; align-items: center; padding: 7px 4px; border-radius: 5px; cursor: pointer;"
						onmouseenter={(e) => (e.currentTarget as HTMLElement).style.background = 'color-mix(in oklch, var(--nav-orange) 6%, transparent)'}
						onmouseleave={(e) => (e.currentTarget as HTMLElement).style.background = 'transparent'}
					>
						<div class="truncate" style="font-size: 12px; font-weight: 600; color: var(--text-primary); font-family: 'JetBrains Mono', monospace;" title={displayName}>{displayName}</div>
						<div style="background: color-mix(in oklch, var(--nav-orange) 15%, transparent); height: 7px; border-radius: 4px; overflow: hidden;">
							<div style="background: var(--nav-orange); width: {barPct}%; height: 7px;"></div>
						</div>
						<div style="font-size: 11px; color: var(--text-faint); text-align: right; font-family: 'JetBrains Mono', monospace;">{pct}%</div>
						<div style="font-size: 12px; font-weight: 700; color: var(--text-primary); text-align: right; font-family: 'JetBrains Mono', monospace;">~${skillCost.toFixed(3)}</div>
					</a>
				{/each}

				{#if otherCount > 0}
					{@const otherCost = (otherCount * avgTokens * pricePerMTok) / 1_000_000}
					{@const otherPct = Math.round((otherCount / allTotal) * 100)}
					{@const otherBarPct = Math.round((otherCount / costMax) * 100)}
					<div style="display: grid; grid-template-columns: 1fr 1fr 40px 68px; gap: 10px; align-items: center; padding: 7px 4px; border-top: 1px dashed var(--border-subtle); margin-top: 2px;">
						<div style="font-size: 11px; color: var(--text-faint); font-style: italic;">{rightPanelSkills.length - 5} other skills</div>
						<div style="background: var(--bg-muted); height: 7px; border-radius: 4px; overflow: hidden;">
							<div style="background: var(--text-faint); width: {Math.min(otherBarPct, 100)}%; height: 7px; opacity: 0.5;"></div>
						</div>
						<div style="font-size: 11px; color: var(--text-faint); text-align: right; font-family: 'JetBrains Mono', monospace;">{otherPct}%</div>
						<div style="font-size: 12px; font-weight: 600; color: var(--text-faint); text-align: right; font-family: 'JetBrains Mono', monospace;">~${otherCost.toFixed(3)}</div>
					</div>
				{/if}

				<div style="margin-top: 12px; border-top: 1px solid var(--border-subtle); padding-top: 8px; font-size: 10px; color: var(--text-faint); line-height: 1.6;">
					~{avgTokens} tokens/invocation · Sonnet ${pricePerMTok}/MTok · actual cost varies by model &amp; skill file size
				</div>
			</div>
			{/if}

		</div>

	</div>

	{/if}

</div>

{/if}
