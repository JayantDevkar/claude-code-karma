<script lang="ts">
	import { onMount } from 'svelte';
	import { Clock, Loader2, ChevronRight, Repeat, Zap, ExternalLink } from 'lucide-svelte';
	import { API_BASE } from '$lib/config';
	import type { CronJob, CronListResponse } from '$lib/api-types';

	interface Props {
		sessionUuid: string;
		projectEncodedName?: string;
	}
	let { sessionUuid, projectEncodedName }: Props = $props();

	let loading = $state(true);
	let error = $state<string | null>(null);
	let jobs = $state<CronJob[]>([]);
	let openIds = $state<Set<string>>(new Set());

	const NOW_MS = Date.now();

	onMount(async () => {
		try {
			const res = await fetch(`${API_BASE}/sessions/${sessionUuid}/cron?include_fires=true`);
			if (!res.ok) throw new Error(`API ${res.status}`);
			const data = (await res.json()) as CronListResponse;
			jobs = data.jobs ?? [];
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			loading = false;
		}
	});

	type DerivedStatus = 'active' | 'expired' | 'deleted';

	function statusOf(j: CronJob): DerivedStatus {
		if (j.deleted_at) return 'deleted';
		if (new Date(j.ttl_expires_at).getTime() < NOW_MS) return 'expired';
		return 'active';
	}

	let hasLiveState = $derived(jobs.some((j) => j.latest_state !== null && j.latest_state !== undefined));

	function toggle(key: string) {
		const next = new Set(openIds);
		next.has(key) ? next.delete(key) : next.add(key);
		openIds = next;
	}

	function cronHuman(expr: string): string {
		const parts = expr.trim().split(/\s+/);
		if (parts.length < 5) return expr;
		const [min, hour, dom, month, dow] = parts;
		if (expr === '* * * * *') return 'every min';
		if (min.startsWith('*/') && hour === '*') return `every ${min.slice(2)} min`;
		if (hour.startsWith('*/') && min === '0') return `every ${hour.slice(2)}h`;
		if (min !== '*' && hour !== '*' && dom === '*' && month === '*' && dow === '*') {
			return `daily ${hour.padStart(2, '0')}:${min.padStart(2, '0')}`;
		}
		return expr;
	}

	function formatRelative(ms: number): string {
		const abs = Math.abs(ms);
		const sec = Math.floor(abs / 1000);
		const min = Math.floor(sec / 60);
		const hr = Math.floor(min / 60);
		const day = Math.floor(hr / 24);
		if (day >= 1) { const rh = hr - day * 24; return rh > 0 ? `${day}d ${rh}h` : `${day}d`; }
		if (hr >= 1) { const rm = min - hr * 60; return rm > 0 ? `${hr}h ${rm}m` : `${hr}h`; }
		if (min >= 1) return `${min}m`;
		return `${sec}s`;
	}

	function formatTimeAgo(iso: string): string {
		const delta = NOW_MS - new Date(iso).getTime();
		if (delta < 0) return `in ${formatRelative(-delta)}`;
		return `${formatRelative(delta)} ago`;
	}

	function formatAbsolute(iso: string): string {
		return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
	}

	function formatDate(iso: string): string {
		return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric' });
	}

	function formatShortTime(iso: string): string {
		return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
	}

	type DotVariant = 'truth' | 'likely' | 'expired' | 'deleted';
	interface StatusMeta { dot: DotVariant; label: string; isLikely: boolean; via: string | null; truth: boolean; }

	function getStatusMeta(j: CronJob): StatusMeta {
		const s = statusOf(j);
		if (s === 'active') {
			const truth = j.latest_state !== null && j.latest_state !== undefined;
			return truth
				? { dot: 'truth', label: 'ACTIVE', isLikely: false, via: null, truth: true }
				: { dot: 'likely', label: 'ACTIVE', isLikely: true, via: null, truth: false };
		}
		if (s === 'expired') return { dot: 'expired', label: 'TTL EXPIRED', isLikely: false, via: null, truth: false };
		const viaMap: Record<string, string> = {
			CronDelete: 'via explicit delete', session_end: 'via session end', expiry: 'via expiry', unknown: 'deletion unobserved'
		};
		return {
			dot: 'deleted', label: 'DELETED', isLikely: false,
			via: j.deleted_via ? (viaMap[j.deleted_via] ?? j.deleted_via) : 'deletion unobserved',
			truth: false
		};
	}

	function getTtlInfo(j: CronJob) {
		const ttl = new Date(j.ttl_expires_at).getTime();
		const created = new Date(j.created_at).getTime();
		const total = ttl - created;
		const remaining = ttl - NOW_MS;
		const expired = remaining <= 0;
		const pct = expired ? 0 : Math.max(0, Math.min(100, (remaining / total) * 100));
		const warn = !expired && remaining < 24 * 3600 * 1000;
		return { remaining, expired, pct, warn };
	}

	function dotStyle(dot: DotVariant): string {
		if (dot === 'truth') return 'background: var(--success);';
		if (dot === 'likely') return 'background: var(--success); opacity: 0.55;';
		if (dot === 'expired') return 'background: var(--text-faint); opacity: 0.7;';
		return 'background: var(--text-faint);';
	}
</script>

<div class="cron-wrap">
	<!-- Header -->
	<div class="sec-header">
		<span class="sec-label">
			{#if loading}Cron jobs{:else}{jobs.length} cron job{jobs.length !== 1 ? 's' : ''}{/if}
		</span>
		{#if !loading && jobs.length > 0 && projectEncodedName}
			<a href="/cron?project={projectEncodedName}" class="view-all">
				View all <ExternalLink size={9} />
			</a>
		{/if}
	</div>

	<!-- Inferred-state note -->
	{#if !hasLiveState && !loading && jobs.length > 0}
		<p class="inferred-note">
			Status inferred from 7-day TTL — install <code>cron_state_capture.py</code> for live state.
		</p>
	{/if}

	<!-- Loading -->
	{#if loading}
		<div class="center-state">
			<Loader2 size={14} class="animate-spin" style="color: var(--text-faint);" />
		</div>

	<!-- Error -->
	{:else if error}
		<p class="error-note">Failed to load: {error}</p>

	<!-- Empty -->
	{:else if jobs.length === 0}
		<div class="empty-state">
			<Clock size={18} style="opacity: 0.3; color: var(--text-faint);" />
			<p class="m-0">No scheduled jobs in this session.</p>
		</div>

	<!-- Job list -->
	{:else}
		<div class="cron-list">
			{#each jobs as job (job.id)}
				{@const key = String(job.id)}
				{@const expanded = openIds.has(key)}
				{@const meta = getStatusMeta(job)}
				{@const ttl = getTtlInfo(job)}
				{@const s = statusOf(job)}
				{@const human = cronHuman(job.cron_expression)}
				{@const visibleFires = (job.fires ?? []).filter((f) => f.outcome_excerpt || f.inference_source === 'hook')}

				<div class="cron-card" class:expanded class:gone={s !== 'active'}>
					<!-- Collapsed row -->
					<button type="button" class="cron-row" onclick={() => toggle(key)}>
						<!-- Status dot -->
						<span
							class="status-dot"
							class:dot-truth={meta.dot === 'truth'}
							style={dotStyle(meta.dot)}
						></span>

						<!-- Content column -->
						<div class="row-content">
							<!-- Line 1: ID + recur type + status -->
							<div class="row-head">
								<span class="cron-id">{(job.cron_id ?? job.tool_use_id).slice(0, 8)}</span>
								<span class="recur-icon" class:recur-on={job.recurring} title={job.recurring ? 'Recurring' : 'One-shot'}>
									{#if job.recurring}<Repeat size={10} />{:else}<Zap size={10} />{/if}
								</span>
								<span
									class="status-tag"
									class:tag-active={s === 'active' && !meta.isLikely}
									class:tag-likely={meta.isLikely}
									class:tag-inactive={s !== 'active'}
								>
									{meta.label}{#if meta.isLikely}<sup class="qm">?</sup>{/if}
									{#if meta.via}<span class="via"> · {meta.via}</span>{/if}
								</span>
								{#if meta.truth}<span class="pill-hook">HOOK</span>{/if}
							</div>

							<!-- Line 2: Prompt -->
							<div class="row-prompt" class:expanded>{job.prompt}</div>

							<!-- Line 3: schedule · fires · TTL -->
							<div class="row-meta">
								<span class="mono-dim">{human}</span>
								{#if visibleFires.length > 0}
									<span class="sep">·</span>
									<span class="mono-dim">{visibleFires.length} {visibleFires.length === 1 ? 'fire' : 'fires'}</span>
								{/if}
								<span class="sep">·</span>
								{#if s === 'deleted'}
									<span class="mono-dim">deleted</span>
								{:else if ttl.expired}
									<span class="mono-dim">TTL elapsed</span>
								{:else}
									<span class="mono-dim" class:warn-text={ttl.warn}>{formatRelative(ttl.remaining)} left</span>
								{/if}
							</div>
						</div>

						<!-- Caret -->
						<span class="caret" class:open={expanded}>
							<ChevronRight size={13} />
						</span>
					</button>

					<!-- Expanded panel -->
					{#if expanded}
						<div class="panel">
							<!-- Meta strip -->
							<div class="meta-row">
								<div class="kv-row">
									<span class="kv-label">Lifetime</span>
									<span class="kv-val">
										{formatDate(job.created_at)} → {formatDate(job.ttl_expires_at)}
										<span class="kv-dim"> · 7 days</span>
									</span>
								</div>
								{#if job.deleted_at}
									<div class="kv-row">
										<span class="kv-label">Deleted</span>
										<span class="kv-val">{formatAbsolute(job.deleted_at)}<span class="kv-dim"> · {meta.via}</span></span>
									</div>
								{/if}
								{#if job.latest_state}
									<div class="kv-row">
										<span class="kv-label">Live state</span>
										<span class="kv-val"><span style="color: var(--success);">● alive</span><span class="kv-dim"> · {formatTimeAgo(job.latest_state.captured_at)}</span></span>
									</div>
								{/if}
								<div class="kv-row">
									<span class="kv-label">Schedule</span>
									<span class="kv-val mono">{job.cron_expression}<span class="kv-dim"> · {human}</span></span>
								</div>
							</div>

							<!-- Fires section -->
							<div class="fires-section">
								<span class="kv-label">
									{#if visibleFires.length === 0}No fires recorded{:else}Fires · {visibleFires.length} {visibleFires.length === 1 ? 'event' : 'events'}{/if}
								</span>

								{#if visibleFires.length === 0}
									<div class="fires-empty">
										{#if job.recurring}No fires observed in session log.{:else}One-shot — no fires recorded.{/if}
									</div>
								{:else}
									<div class="fire-timeline">
										{#each visibleFires as fire, i}
											{@const truth = fire.inference_source === 'hook'}
											{@const last = i === visibleFires.length - 1}
											<div class="fire-tl-row" class:last>
												<div class="fire-tl-track">
													<span class="fire-tl-dot" class:truth></span>
													{#if !last}<span class="fire-tl-line"></span>{/if}
												</div>
												<div class="fire-tl-content">
													<span class="fire-tl-time">{formatShortTime(fire.fired_at)}</span>
													<span class="fire-tl-ago">{formatTimeAgo(fire.fired_at)}</span>
													{#if truth}<span class="fire-confirmed">confirmed</span>{/if}
													{#if fire.outcome_excerpt}
														<p class="fire-tl-body">{fire.outcome_excerpt}</p>
													{/if}
												</div>
											</div>
										{/each}
									</div>
								{/if}
							</div>
						</div>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.cron-wrap {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}

	.sec-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
	}

	.sec-label {
		font-size: 10px;
		letter-spacing: 0.07em;
		text-transform: uppercase;
		font-weight: 600;
		color: var(--text-muted);
	}

	.view-all {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		font-size: 10px;
		color: var(--text-muted);
		text-decoration: none;
	}
	.view-all:hover { color: var(--accent); }

	.inferred-note {
		font-size: 10px;
		color: var(--text-faint);
		margin: 0;
		line-height: 1.5;
	}

	.inferred-note code {
		font-family: var(--font-mono);
		color: var(--text-muted);
	}

	.error-note {
		font-size: 12px;
		color: var(--error);
		margin: 0;
	}

	.center-state {
		display: flex;
		justify-content: center;
		padding: 32px 0;
	}

	.empty-state {
		border: 1px dashed var(--border);
		border-radius: 10px;
		padding: 28px 16px;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 8px;
		text-align: center;
		font-size: 12px;
		color: var(--text-muted);
	}

	/* ── List ─── */
	.cron-list {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	.cron-card {
		border: 1px solid var(--border);
		background: var(--bg-base);
		border-radius: 10px;
		overflow: hidden;
		transition: border-color 0.15s, box-shadow 0.15s;
	}
	.cron-card:hover { border-color: var(--border-hover); }
	.cron-card.expanded {
		border-color: var(--border-hover);
		box-shadow: 0 1px 0 var(--border-subtle), 0 4px 14px -6px var(--border-subtle);
	}
	.cron-card.gone { background: var(--bg-subtle); }
	.cron-card.gone.expanded { background: var(--bg-base); }

	/* ── Row ─── */
	.cron-row {
		display: grid;
		grid-template-columns: 10px 1fr 16px;
		align-items: center;
		gap: 10px;
		padding: 11px 13px;
		width: 100%;
		cursor: pointer;
		user-select: none;
		text-align: left;
		background: none;
		border: none;
	}

	.caret {
		color: var(--text-faint);
		display: flex;
		align-items: center;
		transition: transform 0.15s;
		flex-shrink: 0;
	}
	.caret.open { transform: rotate(90deg); color: var(--text-primary); }

	.status-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		flex-shrink: 0;
	}

	.dot-truth {
		box-shadow: 0 0 0 3px rgba(var(--success-rgb), 0.18);
		animation: cronPulse 1.6s infinite;
	}

	@keyframes cronPulse {
		0%   { box-shadow: 0 0 0 0   rgba(var(--success-rgb), 0.6); }
		70%  { box-shadow: 0 0 0 5px rgba(var(--success-rgb), 0);   }
		100% { box-shadow: 0 0 0 0   rgba(var(--success-rgb), 0);   }
	}

	/* ── Row content ─── */
	.row-content {
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 3px;
	}

	.row-head {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 6px;
	}

	.cron-id {
		font-family: var(--font-mono);
		font-size: 12px;
		font-weight: 600;
		color: var(--accent);
	}

	.recur-icon {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 18px;
		height: 18px;
		border-radius: 4px;
		background: var(--bg-muted);
		color: var(--text-faint);
		flex-shrink: 0;
	}
	.recur-icon.recur-on { background: var(--info-subtle); color: var(--info); }

	.status-tag {
		font-size: 10px;
		font-weight: 600;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		color: var(--text-muted);
		display: inline-flex;
		align-items: center;
		gap: 3px;
	}
	.tag-active, .tag-likely { color: var(--success); }
	.tag-inactive { color: var(--text-faint); }

	.qm {
		font-size: 8px;
		opacity: 0.6;
		letter-spacing: 0;
		text-transform: none;
		font-weight: 500;
	}

	.via {
		color: var(--text-faint);
		font-weight: 500;
		text-transform: none;
		letter-spacing: 0;
		font-size: 10.5px;
	}

	.pill-hook {
		font-family: var(--font-mono);
		font-size: 9px;
		font-weight: 600;
		letter-spacing: 0.04em;
		padding: 1px 5px;
		border-radius: 4px;
		background: var(--success-subtle);
		color: var(--success);
	}

	.row-prompt {
		font-size: 12px;
		line-height: 1.45;
		color: var(--text-primary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.row-prompt.expanded {
		white-space: normal;
		overflow: visible;
		text-overflow: unset;
	}

	.row-meta {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 5px;
		font-size: 11px;
	}

	.mono-dim {
		font-family: var(--font-mono);
		color: var(--text-muted);
	}
	.warn-text { color: var(--warning) !important; }
	.sep { color: var(--text-faint); }

	/* ── Expanded panel ─── */
	.panel {
		border-top: 1px dashed var(--border);
		padding: 13px 14px 14px;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}

	.meta-row {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.kv-row {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.kv-label {
		font-size: 10px;
		letter-spacing: 0.07em;
		text-transform: uppercase;
		color: var(--text-faint);
		font-weight: 600;
	}

	.kv-val {
		font-family: var(--font-mono);
		font-size: 11.5px;
		line-height: 1.5;
		color: var(--text-primary);
	}
	.kv-val.mono { font-family: var(--font-mono); }
	.kv-dim { color: var(--text-faint); }

	/* ── Fires ─── */
	.fires-section {
		display: flex;
		flex-direction: column;
		gap: 0;
		border-top: 1px dashed var(--border);
		padding-top: 12px;
	}

	.fires-empty {
		margin-top: 8px;
		padding: 12px;
		text-align: center;
		color: var(--text-muted);
		border: 1px dashed var(--border);
		border-radius: 7px;
		font-size: 11.5px;
	}

	.fire-timeline {
		display: flex;
		flex-direction: column;
		margin-top: 10px;
	}

	.fire-tl-row {
		display: grid;
		grid-template-columns: 18px 1fr;
		gap: 0 8px;
	}

	.fire-tl-track {
		display: flex;
		flex-direction: column;
		align-items: center;
		padding-top: 3px;
	}

	.fire-tl-dot {
		width: 7px;
		height: 7px;
		border-radius: 50%;
		background: var(--border-hover);
		flex-shrink: 0;
	}
	.fire-tl-dot.truth {
		background: var(--success);
		box-shadow: 0 0 0 2px rgba(var(--success-rgb), 0.2);
	}

	.fire-tl-line {
		flex: 1;
		width: 1px;
		background: var(--border);
		margin: 3px 0;
		min-height: 8px;
	}

	.fire-tl-content {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0 6px;
		padding-bottom: 11px;
	}
	.fire-tl-row.last .fire-tl-content { padding-bottom: 0; }

	.fire-tl-time {
		font-family: var(--font-mono);
		font-size: 11.5px;
		font-weight: 600;
		color: var(--text-primary);
	}

	.fire-tl-ago {
		font-size: 11px;
		color: var(--text-faint);
	}

	.fire-confirmed {
		font-size: 10px;
		font-weight: 600;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		color: var(--success);
	}

	.fire-tl-body {
		width: 100%;
		margin: 3px 0 0;
		font-size: 11.5px;
		line-height: 1.5;
		color: var(--text-muted);
		word-break: break-word;
	}
</style>
