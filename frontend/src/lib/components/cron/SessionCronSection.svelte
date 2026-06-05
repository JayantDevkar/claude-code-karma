<script lang="ts">
	import { onMount } from 'svelte';
	import { Clock, Loader2, Info, ChevronRight } from 'lucide-svelte';
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

	// ── status helpers ────────────────────────────────────────────────────────
	type DerivedStatus = 'active' | 'expired' | 'deleted';

	function statusOf(j: CronJob): DerivedStatus {
		if (j.deleted_at) return 'deleted';
		if (new Date(j.ttl_expires_at).getTime() < NOW_MS) return 'expired';
		return 'active';
	}

	let hasLiveState = $derived(
		jobs.some((j) => j.latest_state !== null && j.latest_state !== undefined)
	);

	// ── helpers ───────────────────────────────────────────────────────────────
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
		if (day >= 1) {
			const rh = hr - day * 24;
			return rh > 0 ? `${day}d ${rh}h` : `${day}d`;
		}
		if (hr >= 1) {
			const rm = min - hr * 60;
			return rm > 0 ? `${hr}h ${rm}m` : `${hr}h`;
		}
		if (min >= 1) return `${min}m`;
		return `${sec}s`;
	}

	function formatTimeAgo(iso: string): string {
		const delta = NOW_MS - new Date(iso).getTime();
		if (delta < 0) return `in ${formatRelative(-delta)}`;
		return `${formatRelative(delta)} ago`;
	}

	function formatAbsolute(iso: string): string {
		return new Date(iso).toLocaleString(undefined, {
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	function formatShortTime(iso: string): string {
		return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
	}

	type DotVariant = 'truth' | 'likely' | 'expired' | 'deleted';

	interface StatusMeta {
		dot: DotVariant;
		label: string;
		isLikely: boolean;
		via: string | null;
		truth: boolean;
	}

	function getStatusMeta(j: CronJob): StatusMeta {
		const s = statusOf(j);
		if (s === 'active') {
			const truth = j.latest_state !== null && j.latest_state !== undefined;
			return truth
				? { dot: 'truth', label: 'ACTIVE', isLikely: false, via: null, truth: true }
				: { dot: 'likely', label: 'LIKELY ACTIVE', isLikely: true, via: null, truth: false };
		}
		if (s === 'expired') {
			return { dot: 'expired', label: 'TTL EXPIRED', isLikely: false, via: null, truth: false };
		}
		const viaMap: Record<string, string> = {
			CronDelete: 'via explicit delete',
			session_end: 'via session end',
			expiry: 'via expiry',
			unknown: 'deletion unobserved'
		};
		return {
			dot: 'deleted',
			label: 'DELETED',
			isLikely: false,
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

<div class="section">
	<!-- Section header -->
	<div class="sec-header">
		<div>
			<h2 class="sec-title">Scheduled jobs</h2>
			<p class="sec-sub">
				{#if hasLiveState}
					Live state captured via hook.
				{:else}
					Reconstructed from session JSONL — cron is in-memory and session-scoped.
				{/if}
			</p>
		</div>
		{#if !loading && jobs.length > 0 && projectEncodedName}
			<a href="/cron?project={projectEncodedName}" class="view-all">
				View all in project →
			</a>
		{/if}
	</div>

	<!-- No-hook notice -->
	{#if !hasLiveState && !loading && jobs.length > 0}
		<div class="notice">
			<Info size={13} class="shrink-0 mt-px" style="color: var(--info);" />
			<span>
				The optional <code>cron_state_capture.py</code> hook is not installed — "likely active"
				status is inferred from the 7-day TTL window.
			</span>
		</div>
	{/if}

	<!-- Loading -->
	{#if loading}
		<div class="center-state">
			<Loader2 size={18} class="animate-spin" style="color: var(--text-faint);" />
		</div>

	<!-- Error -->
	{:else if error}
		<div class="error-state">Failed to load cron jobs: {error}</div>

	<!-- Empty -->
	{:else if jobs.length === 0}
		<div class="empty-state">
			<Clock size={24} style="opacity: 0.35; color: var(--text-faint);" />
			<p class="m-0">No scheduled jobs recorded for this session.</p>
			<p class="empty-hint">They appear here when Claude runs <code>CronCreate</code>.</p>
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

				<div class="cron-card" class:expanded class:gone={s !== 'active'}>
					<!-- Collapsed row -->
					<button type="button" class="cron-row" onclick={() => toggle(key)}>
						<span class="caret" class:open={expanded}>
							<ChevronRight size={13} />
						</span>

						<span
							class="status-dot"
							class:dot-truth={meta.dot === 'truth'}
							style={dotStyle(meta.dot)}
						></span>

						<div class="row-content">
							<!-- Line 1 -->
							<div class="row-head">
								<span class="cron-id">{(job.cron_id ?? job.tool_use_id).slice(0, 8)}</span>
								<span class="pill pill-schedule">{human}</span>
								{#if job.recurring}
									<span class="pill pill-recur">RECURRING</span>
								{:else}
									<span class="pill pill-once">ONE-SHOT</span>
								{/if}
								<span
									class="status-tag"
									class:tag-active-likely={s === 'active'}
									class:tag-inactive={s !== 'active'}
								>
									{meta.label}
									{#if meta.isLikely}<span class="qm">·?</span>{/if}
									{#if meta.via}<span class="via"> · {meta.via}</span>{/if}
								</span>
								{#if meta.truth}
									<span class="pill pill-hook">HOOK</span>
								{/if}
							</div>

							<!-- Line 2: Prompt -->
							<div class="row-prompt">
								<span class="quote">"</span>{job.prompt}<span class="quote">"</span>
							</div>

							<!-- Line 3: TTL bar -->
							<div class="ttl-inline">
								<div class="ttl-track">
									<div
										class="ttl-fill"
										style="width: {ttl.pct}%; background: {ttl.expired
											? 'var(--text-faint)'
											: ttl.warn
												? 'var(--warning)'
												: 'var(--success)'}; {ttl.expired ? 'opacity: 0.4;' : ''}"
									></div>
								</div>
								<span class="ttl-label">
									{#if s === 'deleted'}
										deleted
									{:else if ttl.expired}
										TTL expired
									{:else}
										{formatRelative(ttl.remaining)} left
									{/if}
								</span>
								{#if job.fires && job.fires.length > 0}
									<span class="sep">·</span>
									<span class="ttl-label">{job.fires.length} {job.fires.length === 1 ? 'fire' : 'fires'}</span>
								{/if}
							</div>
						</div>
					</button>

					<!-- Expanded panel -->
					{#if expanded}
						<div class="panel">
							<!-- Left: kv details -->
							<div class="kv-col">
								<div class="kv-row">
									<span class="kv-label">Cron ID</span>
									<span class="kv-val" style="color: var(--accent);">{job.cron_id ?? job.tool_use_id}</span>
								</div>
								<div class="kv-row">
									<span class="kv-label">Schedule</span>
									<span class="kv-val">
										{job.cron_expression}<span class="kv-dim"> · {human}</span>
									</span>
								</div>
								<div class="kv-row">
									<span class="kv-label">Created</span>
									<span class="kv-val">
										{formatAbsolute(job.created_at)}<span class="kv-dim"> · {formatTimeAgo(job.created_at)}</span>
									</span>
								</div>
								<div class="kv-row">
									<span class="kv-label">TTL expires</span>
									<span class="kv-val">
										{formatAbsolute(job.ttl_expires_at)}<span class="kv-dim"> · {formatTimeAgo(job.ttl_expires_at)}</span>
									</span>
								</div>
								{#if job.deleted_at}
									<div class="kv-row">
										<span class="kv-label">Deleted</span>
										<span class="kv-val">
											{formatAbsolute(job.deleted_at)}<span class="kv-dim"> · {meta.via}</span>
										</span>
									</div>
								{/if}
								{#if job.latest_state}
									<div class="kv-row">
										<span class="kv-label">Ground-truth state</span>
										<span class="kv-val">
											<span style="color: var(--success);">● alive</span>
											<span class="kv-dim"> · observed {formatTimeAgo(job.latest_state.captured_at)}</span>
										</span>
									</div>
								{/if}
								<div class="kv-row">
									<span class="kv-label">Prompt</span>
									<div class="prompt-block">
										<span class="barb">{'>'}</span>
										{job.prompt}
									</div>
								</div>
							</div>

							<!-- Right: fires -->
							<div class="fires-col">
								<div class="fires-header">
									<span class="kv-label">
										{#if !job.fires || job.fires.length === 0}
											No fires recorded
										{:else}
											Fires · {job.fires.length}
											{job.fires.length === 1 ? 'event' : 'events'}
										{/if}
									</span>
									{#if job.fires && job.fires.length > 0}
										<span class="fires-source">
											{job.fires.some((f) => f.inference_source === 'hook')
												? 'hook · ground truth'
												: 'inferred from logs'}
										</span>
									{/if}
								</div>

								{#if !job.fires || job.fires.length === 0}
									<div class="fires-empty">
										{#if job.recurring}
											No fires yet. <b>Cron was created {formatTimeAgo(job.created_at)}</b> and no fires have been observed in the session log.
										{:else}
											One-shot cron hasn't fired yet — scheduled for <b>{formatAbsolute(job.ttl_expires_at)}</b>.
										{/if}
									</div>
								{:else}
									<div class="fires-scroll">
										{#each job.fires as fire}
											{@const truth = fire.inference_source === 'hook'}
											{@const low = !truth && fire.inference_confidence < 0.7}
											{@const pct = Math.round(fire.inference_confidence * 100)}
											<div class="fire-card">
												<div class="fire-head">
													<span class="fire-time">
														<b>{formatShortTime(fire.fired_at)}</b>
													</span>
													<span class="fire-ago">· {formatTimeAgo(fire.fired_at)}</span>
													<span class="fire-conf" class:low>
														{#if truth}
															<span style="color: var(--success);">ground truth</span>
														{:else}
															<span class="conf-bar">
																<span class="conf-fill" style="width: {pct}%;"></span>
															</span>
															<span class="conf-pct">~{pct}%</span>
														{/if}
													</span>
												</div>
												{#if fire.outcome_excerpt}
													<div class="fire-body">{fire.outcome_excerpt}</div>
												{/if}
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
	.section {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.sec-header {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 12px;
	}

	.sec-title {
		font-size: 16px;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0 0 4px;
	}

	.sec-sub {
		font-size: 13px;
		color: var(--text-muted);
		margin: 0;
	}

	.view-all {
		font-size: 12px;
		color: var(--text-secondary);
		text-decoration: none;
		white-space: nowrap;
		flex-shrink: 0;
	}

	.view-all:hover {
		color: var(--accent);
	}

	.notice {
		display: flex;
		align-items: flex-start;
		gap: 8px;
		background: var(--info-subtle);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 10px 12px;
		font-size: 12.5px;
		color: var(--text-muted);
		line-height: 1.5;
	}

	.center-state {
		display: flex;
		justify-content: center;
		padding: 48px 0;
	}

	.error-state {
		background: var(--warning-subtle);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 12px 16px;
		font-size: 13px;
		color: var(--warning);
	}

	.empty-state {
		border: 1px dashed var(--border);
		border-radius: 10px;
		padding: 32px 20px;
		text-align: center;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 8px;
		font-size: 13px;
		color: var(--text-muted);
	}

	.empty-hint {
		font-size: 12px;
		color: var(--text-faint);
		margin: 0;
	}

	/* ── Cron list ──────────────────────────────────────────────────────────── */
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
		transition:
			border-color 0.15s,
			box-shadow 0.15s;
	}

	.cron-card:hover {
		border-color: var(--border-hover);
	}

	.cron-card.expanded {
		border-color: var(--border-hover);
		box-shadow: 0 1px 0 var(--border-subtle), 0 4px 14px -6px var(--border-subtle);
	}

	.cron-card.gone {
		background: var(--bg-subtle);
	}

	.cron-row {
		display: grid;
		grid-template-columns: 16px 12px 1fr;
		align-items: center;
		gap: 12px;
		padding: 12px 14px;
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
	}

	.caret.open {
		transform: rotate(90deg);
		color: var(--text-primary);
	}

	.status-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		flex-shrink: 0;
	}

	.dot-truth {
		box-shadow: 0 0 0 3px rgba(var(--success-rgb), 0.18);
		animation: sessionCronPulse 1.6s infinite;
	}

	@keyframes sessionCronPulse {
		0% { box-shadow: 0 0 0 0 rgba(var(--success-rgb), 0.6); }
		70% { box-shadow: 0 0 0 6px rgba(var(--success-rgb), 0); }
		100% { box-shadow: 0 0 0 0 rgba(var(--success-rgb), 0); }
	}

	.row-content {
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 4px;
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

	.pill {
		display: inline-flex;
		align-items: center;
		font-size: 10px;
		font-weight: 600;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		padding: 1px 6px;
		border-radius: 4px;
		font-family: var(--font-mono);
	}

	.pill-schedule {
		background: var(--accent-muted);
		color: var(--accent);
	}

	.pill-recur {
		background: var(--info-subtle);
		color: var(--info);
	}

	.pill-once {
		background: var(--bg-muted);
		color: var(--text-secondary);
	}

	.pill-hook {
		background: var(--success-subtle);
		color: var(--success);
	}

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

	.tag-active-likely {
		color: var(--success);
	}

	.qm {
		font-family: var(--font-mono);
		font-size: 10px;
		opacity: 0.7;
		letter-spacing: 0;
		text-transform: none;
	}

	.via {
		color: var(--text-faint);
		font-weight: 500;
		text-transform: none;
		letter-spacing: 0;
		font-size: 10.5px;
	}

	.row-prompt {
		font-size: 12.5px;
		line-height: 1.45;
		color: var(--text-primary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.quote {
		font-family: var(--font-mono);
		color: var(--text-faint);
	}

	.ttl-inline {
		display: flex;
		align-items: center;
		gap: 8px;
	}

	.ttl-track {
		flex: 1;
		height: 2px;
		background: var(--bg-muted);
		border-radius: 99px;
		overflow: hidden;
		max-width: 100px;
	}

	.ttl-fill {
		height: 100%;
		border-radius: 99px;
		transition: width 0.3s;
	}

	.ttl-label {
		font-size: 11px;
		color: var(--text-faint);
		font-family: var(--font-mono);
		white-space: nowrap;
	}

	.sep {
		color: var(--text-faint);
	}

	/* ── Expanded panel ─────────────────────────────────────────────────────── */
	.panel {
		border-top: 1px dashed var(--border);
		padding: 14px 16px 16px;
		display: grid;
		grid-template-columns: 220px 1fr;
		align-items: stretch;
		gap: 18px;
	}

	.kv-col {
		display: flex;
		flex-direction: column;
		gap: 10px;
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
		font-size: 12px;
		line-height: 1.5;
		color: var(--text-primary);
	}

	.kv-dim {
		color: var(--text-faint);
	}

	.prompt-block {
		background: var(--bg-subtle);
		border: 1px solid var(--border);
		border-radius: 7px;
		padding: 8px 10px;
		font-family: var(--font-mono);
		font-size: 11.5px;
		line-height: 1.55;
		color: var(--text-primary);
		white-space: pre-wrap;
		word-break: break-word;
		margin-top: 2px;
	}

	.barb {
		color: var(--accent);
		font-weight: 600;
		margin-right: 5px;
	}

	/* ── Fires column ───────────────────────────────────────────────────────── */
	.fires-col {
		min-width: 0;
		display: flex;
		flex-direction: column;
	}

	.fires-scroll {
		max-height: 400px;
		overflow-y: auto;
		padding-right: 4px;
	}

	.fires-scroll::-webkit-scrollbar {
		width: 4px;
	}

	.fires-scroll::-webkit-scrollbar-track {
		background: transparent;
	}

	.fires-scroll::-webkit-scrollbar-thumb {
		background: var(--border-hover);
		border-radius: 99px;
	}

	.fires-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 8px;
	}

	.fires-source {
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--text-faint);
	}

	.fire-card {
		background: var(--bg-subtle);
		border: 1px solid var(--border);
		border-radius: 7px;
		padding: 8px 10px;
		margin-bottom: 5px;
	}

	.fire-head {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 6px;
		margin-bottom: 4px;
	}

	.fire-time {
		font-family: var(--font-mono);
		font-size: 11px;
		color: var(--text-muted);
	}

	.fire-time b {
		color: var(--text-primary);
		font-weight: 500;
	}

	.fire-ago {
		font-size: 11px;
		color: var(--text-faint);
	}

	.fire-conf {
		margin-left: auto;
		display: inline-flex;
		align-items: center;
		gap: 5px;
		font-family: var(--font-mono);
		font-size: 10.5px;
	}

	.conf-bar {
		width: 32px;
		height: 2px;
		background: var(--border);
		border-radius: 99px;
		overflow: hidden;
		display: inline-block;
	}

	.conf-fill {
		height: 100%;
		background: var(--text-muted);
		opacity: 0.5;
		border-radius: 99px;
		display: block;
	}

	.fire-conf.low .conf-fill {
		background: var(--warning);
		opacity: 0.7;
	}

	.conf-pct {
		color: var(--text-muted);
	}

	.fire-conf.low .conf-pct {
		color: var(--warning);
	}

	.fire-body {
		font-size: 12.5px;
		line-height: 1.55;
		color: var(--text-primary);
		white-space: pre-wrap;
		word-break: break-word;
	}

	.fires-empty {
		padding: 16px;
		text-align: center;
		color: var(--text-muted);
		background: var(--bg-subtle);
		border: 1px dashed var(--border);
		border-radius: 7px;
		font-size: 12px;
		line-height: 1.55;
	}

	.fires-empty b {
		color: var(--text-primary);
		font-weight: 500;
	}

	@media (max-width: 640px) {
		.panel {
			grid-template-columns: 1fr;
		}
	}
</style>
