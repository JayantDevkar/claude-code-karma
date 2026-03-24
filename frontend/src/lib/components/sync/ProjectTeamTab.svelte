<script lang="ts">
	import { Users, Loader2, WifiOff, Clock, DollarSign, FileText, Wrench, ChevronDown, ChevronUp } from 'lucide-svelte';
	import { API_BASE } from '$lib/config';
	import type { RemoteSessionUser, StatItem } from '$lib/api-types';
	import StatsGrid from '$lib/components/StatsGrid.svelte';
	import SessionCard from '$lib/components/SessionCard.svelte';
	import { formatRelativeTime, formatDuration, formatCost, getTeamMemberColor, cleanPromptText, truncate } from '$lib/utils';

	let {
		projectEncodedName,
		active = false
	}: {
		projectEncodedName: string;
		active?: boolean;
	} = $props();

	let users = $state<RemoteSessionUser[]>([]);
	let loading = $state(false);
	let loaded = $state(false);
	let error = $state<string | null>(null);
	let expandedUsers = $state<Set<string>>(new Set());

	async function loadRemoteSessions() {
		if (loaded || loading) return;
		loading = true;
		error = null;
		try {
			const res = await fetch(
				`${API_BASE}/projects/${encodeURIComponent(projectEncodedName)}/remote-sessions`
			);
			if (res.ok) {
				const data = await res.json();
				users = data.users ?? [];
			} else {
				error = 'Failed to load remote sessions';
			}
		} catch {
			error = 'Cannot reach backend';
		} finally {
			loading = false;
			if (!error) loaded = true;
		}
	}

	$effect(() => {
		if (active && !loaded) {
			loadRemoteSessions();
		}
	});

	function toggleExpanded(userId: string) {
		const next = new Set(expandedUsers);
		if (next.has(userId)) {
			next.delete(userId);
		} else {
			next.add(userId);
		}
		expandedUsers = next;
	}

	// --- Aggregated stats ---

	let totalSessions = $derived(users.reduce((sum, u) => sum + u.session_count, 0));

	let totalDuration = $derived(
		users.reduce((sum, u) => {
			return sum + u.sessions.reduce((s, sess) => s + (sess.duration_seconds ?? 0), 0);
		}, 0)
	);

	let totalCost = $derived(
		users.reduce((sum, u) => {
			return sum + u.sessions.reduce((s, sess) => s + (sess.total_cost ?? 0), 0);
		}, 0)
	);

	let summaryStats = $derived<StatItem[]>([
		{ title: 'Sessions', value: totalSessions, icon: FileText, color: 'blue' },
		{ title: 'Members', value: users.length, icon: Users, color: 'purple' },
		{ title: 'Total Time', value: formatDuration(totalDuration), icon: Clock, color: 'orange' },
		{ title: 'Total Cost', value: formatCost(totalCost), icon: DollarSign, color: 'green' }
	]);

	// --- Per-member aggregations ---

	interface MemberAgg {
		user: RemoteSessionUser;
		sessionCount: number;
		duration: number;
		cost: number;
		contributionPct: number;
		modelsUsed: Map<string, number>;
		topTools: [string, number][];
		lastTitle: string | null;
		lastPrompt: string | null;
	}

	let memberAggs = $derived.by<MemberAgg[]>(() => {
		const aggs: MemberAgg[] = users.map((user) => {
			const sessionCount = user.session_count;
			let duration = 0;
			let cost = 0;
			const models = new Map<string, number>();
			const tools = new Map<string, number>();
			let lastTitle: string | null = null;
			let lastPrompt: string | null = null;

			for (const sess of user.sessions) {
				duration += sess.duration_seconds ?? 0;
				cost += sess.total_cost ?? 0;

				for (const m of sess.models_used ?? []) {
					models.set(m, (models.get(m) ?? 0) + 1);
				}

				if (sess.tools_used) {
					for (const [tool, count] of Object.entries(sess.tools_used)) {
						tools.set(tool, (tools.get(tool) ?? 0) + count);
					}
				}
			}

			// Most recent session info (already sorted desc by API)
			if (user.sessions.length > 0) {
				const latest = user.sessions[0];
				lastTitle = latest.session_titles?.[0] ?? null;
				lastPrompt = latest.initial_prompt ? cleanPromptText(latest.initial_prompt) : null;
			}

			const topTools = [...tools.entries()]
				.sort((a, b) => b[1] - a[1])
				.slice(0, 3);

			return {
				user,
				sessionCount,
				duration,
				cost,
				contributionPct: totalSessions > 0 ? (sessionCount / totalSessions) * 100 : 0,
				modelsUsed: models,
				topTools,
				lastTitle,
				lastPrompt
			};
		});

		return aggs.sort((a, b) => b.sessionCount - a.sessionCount);
	});

	function shortModelName(model: string): string {
		if (model.includes('opus')) return 'Opus';
		if (model.includes('sonnet')) return 'Sonnet';
		if (model.includes('haiku')) return 'Haiku';
		return model.replace(/^claude-/, '').split('-').slice(0, 2).join(' ');
	}

</script>

<div class="space-y-6">
	<div>
		<h2 class="text-lg font-semibold text-[var(--text-primary)]">Team Activity</h2>
		<p class="text-sm text-[var(--text-muted)]">
			What teammates are working on in this project.
		</p>
	</div>

	{#if loading}
		<div class="flex items-center justify-center py-12 text-[var(--text-muted)]">
			<Loader2 size={20} class="animate-spin" />
		</div>
	{:else if error}
		<div
			class="flex items-center gap-3 p-4 rounded-[var(--radius-lg)] border border-[var(--error)]/20 bg-[var(--error-subtle)]"
		>
			<WifiOff size={14} class="text-[var(--error)] shrink-0" />
			<span class="text-sm text-[var(--error)] flex-1">{error}</span>
			<button
				onclick={() => { loaded = false; loadRemoteSessions(); }}
				class="text-xs font-medium text-[var(--error)] underline hover:no-underline"
			>
				Retry
			</button>
		</div>
	{:else if users.length === 0}
		<div class="text-center py-12">
			<Users size={28} class="mx-auto mb-3 text-[var(--text-muted)]" />
			<p class="text-sm font-medium text-[var(--text-primary)]">No team sessions yet</p>
			<p class="text-xs text-[var(--text-muted)] mt-1">
				When teammates sync sessions for this project, they'll appear here.
			</p>
		</div>
	{:else}
		<!-- Summary Stats -->
		<StatsGrid stats={summaryStats} columns={4} />

		<!-- Member Contributions -->
		<div class="space-y-3">
			{#each memberAggs as member (member.user.user_id)}
				{@const color = getTeamMemberColor(member.user.user_id)}
				{@const isExpanded = expandedUsers.has(member.user.user_id)}
				<div
					class="rounded-xl border border-[var(--border)] bg-[var(--bg-base)] overflow-hidden transition-shadow duration-200 hover:shadow-md"
					style="border-left: 3px solid {color.border}"
				>
					<!-- Member summary — always visible -->
					<button
						onclick={() => toggleExpanded(member.user.user_id)}
						class="w-full text-left px-5 py-4 cursor-pointer hover:bg-[var(--bg-subtle)] transition-colors"
					>
						<div class="space-y-2.5">
							<!-- Row 1: Avatar + name + stats + chevron -->
							<div class="flex items-center justify-between">
								<div class="flex items-center gap-3">
									<div
										class="w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold shrink-0"
										style="background-color: {color.bg}; color: {color.border}"
									>
										{member.user.user_id.charAt(0).toUpperCase()}
									</div>
									<div>
										<a
											href="/members/{encodeURIComponent(member.user.user_id)}"
											class="text-sm font-medium text-[var(--text-primary)] hover:text-[var(--accent)] transition-colors"
											onclick={(e) => e.stopPropagation()}
										>
											{member.user.user_id}
										</a>
										<p class="text-[11px] text-[var(--text-muted)]">
											{member.sessionCount} session{member.sessionCount !== 1 ? 's' : ''}
											&middot; {formatDuration(member.duration)}
											&middot; {formatCost(member.cost)}
											{#if member.user.synced_at}
												&middot; synced {formatRelativeTime(member.user.synced_at)}
											{/if}
										</p>
									</div>
								</div>
								<div class="text-[var(--text-muted)] shrink-0">
									{#if isExpanded}
										<ChevronUp size={16} />
									{:else}
										<ChevronDown size={16} />
									{/if}
								</div>
							</div>

							<!-- Row 2: Contribution bar -->
							<div class="flex items-center gap-3">
								<div class="flex-1 h-1.5 rounded-full bg-[var(--bg-muted)] overflow-hidden">
									<div
										class="h-full rounded-full transition-all duration-500"
										style="width: {member.contributionPct}%; background-color: {color.border}"
									></div>
								</div>
								<span class="text-[11px] font-medium text-[var(--text-muted)] tabular-nums w-8 text-right">
									{Math.round(member.contributionPct)}%
								</span>
							</div>

							<!-- Row 3: Models + Tools + Last activity -->
							<div class="flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-[var(--text-secondary)]">
								{#if member.modelsUsed.size > 0}
									<span class="flex items-center gap-1">
										{#each [...member.modelsUsed.entries()].sort((a, b) => b[1] - a[1]) as [model, count], i}
											{#if i > 0}<span class="text-[var(--text-faint)]">&middot;</span>{/if}
											<span>{shortModelName(model)} ({count})</span>
										{/each}
									</span>
								{/if}

								{#if member.topTools.length > 0}
									<span class="flex items-center gap-1">
										<Wrench size={10} class="text-[var(--text-muted)] shrink-0" />
										{#each member.topTools as [tool, count], i}
											{#if i > 0}<span class="text-[var(--text-faint)]">&middot;</span>{/if}
											<span>{tool} ({count})</span>
										{/each}
									</span>
								{/if}

								{#if member.lastTitle || member.lastPrompt}
									<span class="text-[var(--text-muted)] italic">
										Latest: {truncate(member.lastTitle || member.lastPrompt || '', 80)}
									</span>
								{/if}
							</div>
						</div>
					</button>

					<!-- Expanded: session list -->
					{#if isExpanded}
						<div class="border-t border-[var(--border-subtle)] p-3 space-y-2 bg-[var(--bg-subtle)]">
							{#each member.user.sessions.slice(0, 15) as session (session.uuid)}
								<SessionCard {session} {projectEncodedName} compact showBranch={false} />
							{/each}
							{#if member.user.sessions.length > 15}
								<p class="text-center text-[11px] text-[var(--text-muted)] py-1">
									+{member.user.sessions.length - 15} older sessions
								</p>
							{/if}
						</div>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</div>
