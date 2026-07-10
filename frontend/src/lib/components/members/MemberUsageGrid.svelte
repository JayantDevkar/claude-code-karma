<script lang="ts">
	import {
		Users,
		ArrowRight,
		Link2,
		Loader2,
		WifiOff
	} from 'lucide-svelte';
	import { API_BASE } from '$lib/config';
	import type { UsageTrendResponse, UsageTrendItem } from '$lib/api-types';
	import {
		getUserChartColor,
		getTeamMemberColor,
		formatRelativeTime
	} from '$lib/utils';

	interface ItemWithUsers {
		name: string;
		count: number;
		remote_user_ids?: string[];
	}

	interface Props {
		/** Trend API endpoint, e.g. "/skills/usage/trend" */
		endpoint: string;
		/** Domain label: "Skills", "Agents", or "Tools" */
		domainLabel: string;
		/** Domain icon component */
		domainIcon: typeof Users;
		/** Items with remote_user_ids for per-user item breakdown (skills only) */
		items?: ItemWithUsers[];
		/** Display name formatter for items */
		itemDisplayFn?: (name: string) => string;
		/** Link generator for items */
		itemLinkFn?: (name: string) => string;
		/** Optional filter to exclude items */
		excludeItemFn?: (name: string) => boolean;
	}

	let {
		endpoint,
		domainLabel,
		domainIcon: DomainIcon,
		items,
		itemDisplayFn,
		itemLinkFn,
		excludeItemFn
	}: Props = $props();

	let data = $state<UsageTrendResponse | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);

	async function fetchData() {
		loading = true;
		error = null;
		try {
			const url = new URL(`${API_BASE}${endpoint}`, window.location.origin);
			url.searchParams.set('period', 'month');
			const res = await fetch(url);
			if (!res.ok) throw new Error('Failed to fetch usage data');
			data = await res.json();
		} catch (e: unknown) {
			error = e instanceof Error ? e.message : 'Unknown error';
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		fetchData();
	});

	// Invert items' remote_user_ids → per-user item lists
	let userItemMap = $derived.by(() => {
		const map = new Map<string, Array<{ name: string; displayName: string; count: number; href: string | null }>>();
		if (!items) return map;

		for (const item of items) {
			if (excludeItemFn?.(item.name)) continue;
			const display = itemDisplayFn ? itemDisplayFn(item.name) : item.name;
			const href = itemLinkFn ? itemLinkFn(item.name) : null;
			const entry = { name: item.name, displayName: display, count: item.count, href };

			for (const uid of item.remote_user_ids ?? []) {
				if (!map.has(uid)) map.set(uid, []);
				map.get(uid)!.push(entry);
			}
		}

		// Sort each user's items by count descending
		for (const [, userItems] of map) {
			userItems.sort((a, b) => b.count - a.count);
		}

		return map;
	});

	// Build member cards from trend_by_user
	interface MemberCard {
		userId: string;
		name: string;
		total: number;
		trend: UsageTrendItem[];
		lastActive: string | null;
		isLocal: boolean;
		borderColor: string;
		bgColor: string;
		hexColor: string;
		topItems: Array<{ name: string; displayName: string; count: number; href: string | null }>;
	}

	let members = $derived.by<MemberCard[]>(() => {
		if (!data?.trend_by_user) return [];

		// Filter out local user — other tabs already show your own data
		const entries = Object.entries(data.trend_by_user).filter(
			([userId]) => userId !== '_local'
		);

		return entries
			.map(([userId, trend]) => {
				const total = trend.reduce((s, p) => s + p.count, 0);
				const lastActivePoint = [...trend].reverse().find((p) => p.count > 0);
				const colors = getTeamMemberColor(userId);

				return {
					userId,
					name: data?.user_names?.[userId] ?? userId,
					total,
					trend,
					lastActive: lastActivePoint?.date ?? null,
					isLocal: false,
					borderColor: colors.border,
					bgColor: colors.bg,
					hexColor: getUserChartColor(userId),
					topItems: (userItemMap.get(userId) ?? []).slice(0, 4)
				};
			})
			.sort((a, b) => b.total - a.total);
	});

	let totalUsage = $derived(members.reduce((s, m) => s + m.total, 0));
	let topMember = $derived(members.length > 0 ? members[0] : null);

	// SVG sparkline path generator
	function sparklinePath(
		trend: UsageTrendItem[],
		width: number,
		height: number
	): string {
		const counts = trend.map((t) => t.count);
		if (counts.length < 2) return '';
		const max = Math.max(...counts, 1);
		const step = width / (counts.length - 1);
		const pad = 1;
		const h = height - pad * 2;
		return counts
			.map((c, i) => {
				const x = i * step;
				const y = pad + h - (c / max) * h;
				return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
			})
			.join(' ');
	}

	// Area fill path (closes to bottom)
	function sparklineArea(
		trend: UsageTrendItem[],
		width: number,
		height: number
	): string {
		const line = sparklinePath(trend, width, height);
		if (!line) return '';
		const step = width / (trend.length - 1);
		const lastX = (trend.length - 1) * step;
		return `${line} L${lastX.toFixed(1)},${height} L0,${height} Z`;
	}
</script>

{#if loading}
	<div class="flex items-center justify-center py-16">
		<Loader2 size={20} class="animate-spin text-[var(--text-muted)]" />
	</div>
{:else if error}
	<div
		class="flex items-center gap-3 p-4 rounded-xl border border-[var(--error)]/20 bg-[var(--error-subtle)]"
	>
		<WifiOff size={14} class="text-[var(--error)] shrink-0" />
		<span class="text-sm text-[var(--error)] flex-1">{error}</span>
		<button
			onclick={() => fetchData()}
			class="text-xs font-medium text-[var(--error)] underline hover:no-underline"
		>
			Retry
		</button>
	</div>
{:else if members.length === 0}
	<!-- No team members — show sync CTA -->
	<div
		class="text-center py-16 bg-[var(--bg-subtle)] rounded-2xl border border-dashed border-[var(--border)]"
	>
		<Link2 size={36} class="mx-auto text-[var(--text-muted)] mb-3" />
		<p class="text-sm font-medium text-[var(--text-secondary)]">No team members yet</p>
		<p class="text-xs text-[var(--text-muted)] mt-1.5 max-w-sm mx-auto">
			Set up Syncthing sync to share sessions with teammates and see how they use {domainLabel.toLowerCase()}.
		</p>
		<a
			href="/sync"
			class="inline-flex items-center gap-1.5 mt-4 px-4 py-2 text-xs font-medium rounded-lg
				bg-[var(--accent)] text-white hover:bg-[var(--accent)]/80 transition-colors"
		>
			Set up Sync
			<ArrowRight size={12} />
		</a>
	</div>
{:else}
	<div class="space-y-6">
		<!-- Summary banner -->
		<div
			class="flex items-center justify-between gap-4 p-4 rounded-xl bg-[var(--bg-subtle)] border border-[var(--border)]"
		>
			<div class="flex items-center gap-3">
				<div class="p-2 rounded-lg bg-[var(--accent-subtle)]">
					<DomainIcon size={16} class="text-[var(--accent)]" />
				</div>
				<div>
					<p class="text-sm font-medium text-[var(--text-primary)]">
						{members.length} member{members.length !== 1 ? 's' : ''}
						<span class="text-[var(--text-muted)] font-normal">
							&middot; {totalUsage.toLocaleString()} total {domainLabel.toLowerCase()} uses this month
						</span>
					</p>
					{#if topMember}
						<p class="text-xs text-[var(--text-muted)] mt-0.5">
							Most active: <span class="font-medium text-[var(--text-secondary)]">{topMember.name}</span>
							with {topMember.total.toLocaleString()} uses
						</p>
					{/if}
				</div>
			</div>
		</div>

		<!-- Member Cards Grid -->
		<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
			{#each members as member (member.userId)}
				{@const profileHref = member.isLocal ? null : `/members/${encodeURIComponent(member.userId)}`}
				<div
					class="rounded-xl border border-[var(--border)] bg-[var(--bg-base)] overflow-hidden transition-all duration-200 hover:shadow-md group"
					style="border-left: 3px solid {member.borderColor};"
				>
					<div class="p-5 space-y-4">
						<!-- Header: Avatar + Name + Sparkline -->
						<div class="flex items-start justify-between gap-3">
							<div class="flex items-center gap-3 min-w-0">
								<!-- Avatar -->
								<div
									class="w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold shrink-0 transition-transform duration-200 group-hover:scale-105"
									style="background-color: {member.bgColor}; color: {member.borderColor};"
								>
									{member.name.charAt(0).toUpperCase()}
								</div>
								<div class="min-w-0">
									<p class="text-sm font-semibold text-[var(--text-primary)] truncate">
									{member.name}
								</p>
									<p class="text-[11px] text-[var(--text-muted)] mt-0.5">
										{member.total.toLocaleString()} {domainLabel.toLowerCase()} use{member.total !== 1 ? 's' : ''}
										{#if member.lastActive}
											&middot; last {formatRelativeTime(member.lastActive)}
										{/if}
									</p>
								</div>
							</div>

							<!-- Sparkline -->
							{#if member.trend.length >= 2}
								<div class="shrink-0 w-20 h-8 opacity-60 group-hover:opacity-100 transition-opacity">
									<svg viewBox="0 0 80 32" class="w-full h-full" preserveAspectRatio="none">
										<path
											d={sparklineArea(member.trend, 80, 32)}
											fill={member.hexColor}
											fill-opacity="0.1"
										/>
										<path
											d={sparklinePath(member.trend, 80, 32)}
											fill="none"
											stroke={member.hexColor}
											stroke-width="1.5"
											stroke-linecap="round"
											stroke-linejoin="round"
										/>
									</svg>
								</div>
							{/if}
						</div>

						<!-- Top Items (when available — skills with remote_user_ids) -->
						{#if member.topItems.length > 0}
							<div class="space-y-1.5">
								<p class="text-[10px] uppercase tracking-wider font-medium text-[var(--text-muted)]">
									Top {domainLabel}
								</p>
								{#each member.topItems as item, i}
									{@const maxCount = member.topItems[0].count}
									{@const pct = maxCount > 0 ? (item.count / maxCount) * 100 : 0}
									<div class="flex items-center gap-2.5">
										<div class="flex-1 min-w-0">
											<div class="flex items-center justify-between gap-2 mb-0.5">
												{#if item.href}
													<a
														href={item.href}
														class="text-xs text-[var(--text-secondary)] hover:text-[var(--accent)] truncate transition-colors"
													>
														{item.displayName}
													</a>
												{:else}
													<span class="text-xs text-[var(--text-secondary)] truncate">
														{item.displayName}
													</span>
												{/if}
												<span class="text-[10px] text-[var(--text-muted)] tabular-nums shrink-0">
													{item.count}
												</span>
											</div>
											<div class="h-1 rounded-full bg-[var(--bg-muted)] overflow-hidden">
												<div
													class="h-full rounded-full transition-all duration-500"
													style="width: {pct}%; background-color: {member.hexColor};"
												></div>
											</div>
										</div>
									</div>
								{/each}
							</div>
						{/if}

						<!-- Card Footer: Navigation -->
						{#if profileHref}
							<a
								href={profileHref}
								class="flex items-center gap-1.5 text-xs font-medium text-[var(--accent)] hover:text-[var(--text-primary)] transition-colors pt-1"
							>
								View profile
								<ArrowRight size={12} />
							</a>
						{/if}
					</div>
				</div>
			{/each}
		</div>

	</div>
{/if}
