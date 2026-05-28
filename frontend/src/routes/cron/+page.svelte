<script lang="ts">
	import { goto, invalidateAll } from '$app/navigation';
	import { page } from '$app/stores';
	import {
		Clock,
		Activity,
		Archive,
		RefreshCw,
		Search,
		Info,
		X,
		Calendar,
		ChevronRight
	} from 'lucide-svelte';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import type { CronJob, CronProjectRollupRow } from '$lib/api-types';

	let { data } = $props();

	// ── filter state ──────────────────────────────────────────────────────────
	let projectFilter = $state(data.filters.project || 'all');
	let activeOnly = $state(data.filters.active_only === 'true');
	let query = $state('');
	let openIds = $state<Set<string>>(new Set());
	let caveatOpen = $state(true);
	let rescanning = $state(false);

	const NOW_MS = Date.now();

	// ── derived: project dropdown options ─────────────────────────────────────
	// Each option carries the encoded name (used in URL + server filter) and a
	// human label (shown in the <select>). The URL param / projectFilter value
	// is always the encoded name so the server-side WHERE clause works.
	const projectOptions = $derived(
		(data.rollup as CronProjectRollupRow[])
			.filter((r) => r.project_encoded_name)
			.map((r) => ({
				encoded: r.project_encoded_name,
				label: r.project_display_name ?? r.project_encoded_name
			}))
			.sort((a, b) => a.label.localeCompare(b.label))
	);

	// ── status helpers ────────────────────────────────────────────────────────
	type DerivedStatus = 'active' | 'expired' | 'deleted';

	function statusOf(j: CronJob): DerivedStatus {
		if (j.deleted_at) return 'deleted';
		if (new Date(j.ttl_expires_at).getTime() < NOW_MS) return 'expired';
		return 'active';
	}

	// ── counts (always over full server-returned set) ─────────────────────────
	const counts = $derived.by(() => {
		const total = (data.jobs as CronJob[]).length;
		const active = (data.jobs as CronJob[]).filter((j) => statusOf(j) === 'active').length;
		return { total, active, inactive: total - active };
	});

	// ── client-side filtering + sorting ──────────────────────────────────────
	const filtered = $derived.by(() => {
		const q = query.trim().toLowerCase();
		return (data.jobs as CronJob[]).filter((j) => {
			if (activeOnly && statusOf(j) !== 'active') return false;
			if (projectFilter !== 'all' && j.project_encoded_name !== projectFilter) return false;
			if (q) {
				const id = j.cron_id ?? j.tool_use_id;
				const hay =
					`${id} ${j.cron_expression} ${cronHuman(j.cron_expression)} ${j.prompt} ${j.project_display_name ?? ''}`.toLowerCase();
				if (!hay.includes(q)) return false;
			}
			return true;
		});
	});

	const sorted = $derived.by(() => {
		const order: Record<DerivedStatus, number> = { active: 0, expired: 1, deleted: 2 };
		return [...filtered].sort((a, b) => {
			const d = order[statusOf(a)] - order[statusOf(b)];
			if (d !== 0) return d;
			return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
		});
	});

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

	function jobKey(j: CronJob): string {
		return String(j.id);
	}

	function dotStyle(dot: DotVariant): string {
		if (dot === 'truth') return 'background: var(--success);';
		if (dot === 'likely') return 'background: var(--success); opacity: 0.55;';
		if (dot === 'expired') return 'background: #9ca3af;';
		return 'background: var(--text-faint);';
	}

	async function rescan() {
		rescanning = true;
		await invalidateAll();
		rescanning = false;
	}

	function onProjectChange() {
		const params = new URLSearchParams($page.url.searchParams);
		if (projectFilter === 'all') params.delete('project');
		else params.set('project', projectFilter);
		const qs = params.toString();
		goto(`/cron${qs ? `?${qs}` : ''}`, { replaceState: true });
	}
</script>

<svelte:head>
	<title>Cron Jobs · Claude Karma</title>
</svelte:head>

<div class="page-wrap">
	<!-- Page header -->
	<PageHeader
		title="Cron Jobs"
		icon={Clock}
		iconColor="--nav-purple"
		breadcrumbs={[{ label: 'Home', href: '/' }, { label: 'Cron' }]}
	>
		{#snippet headerRight()}
			<button
				class="rescan-btn"
				onclick={rescan}
				disabled={rescanning}
				aria-label="Rescan session logs"
			>
				<RefreshCw size={14} class={rescanning ? 'spinning' : ''} />
				Rescan logs
			</button>
		{/snippet}
	</PageHeader>

	<!-- Purple tagline -->
	<p class="tagline">
		Every scheduled prompt Claude Code has set up — when it ran, what it answered, and how long
		it has left before the 7-day TTL burns it down.
	</p>

	<!-- Caveat banner -->
	{#if caveatOpen}
		<div class="caveat-banner">
			<Info size={14} class="shrink-0 mt-px" style="color: var(--text-faint);" />
			<span class="caveat-body">
				Cron jobs live <b>in memory inside the Claude Code session</b> that created them — they
				can't be queried directly. This page reconstructs them from session logs and infers fires
				from assistant turns, so <b>"likely active"</b> means "TTL not elapsed and we haven't seen
				a delete." Install the optional hook for ground-truth state.
			</span>
			<button
				class="caveat-close"
				onclick={() => (caveatOpen = false)}
				aria-label="Dismiss"
			>
				<X size={14} />
			</button>
		</div>
	{/if}

	<!-- Stat strip -->
	<div class="stat-grid">
		<!-- Total tracked -->
		<div class="stat-card">
			<div class="stat-ico" style="background: var(--accent-muted); color: var(--accent);">
				<Clock size={18} />
			</div>
			<div>
				<div class="stat-num">{counts.total}</div>
				<div class="stat-label">Total tracked</div>
			</div>
		</div>

		<!-- Likely active -->
		<div class="stat-card">
			<div class="stat-ico" style="background: var(--success-subtle); color: var(--success);">
				<Activity size={18} />
			</div>
			<div>
				<div class="stat-num">
					<span class="approx">~</span>{counts.active}
					{#if counts.active > 0}<span class="pulse-dot"></span>{/if}
				</div>
				<div class="stat-label">Likely active · inferred from TTL</div>
			</div>
		</div>

		<!-- Expired or deleted -->
		<div class="stat-card">
			<div class="stat-ico" style="background: var(--bg-muted); color: var(--text-muted);">
				<Archive size={18} />
			</div>
			<div>
				<div class="stat-num">{counts.inactive}</div>
				<div class="stat-label">Expired or deleted</div>
			</div>
		</div>
	</div>

	<!-- Toolbar -->
	<div class="toolbar">
		<select
			class="select-input"
			bind:value={projectFilter}
			onchange={onProjectChange}
		>
			<option value="all">All projects</option>
			{#each projectOptions as p}
				<option value={p.encoded}>{p.label}</option>
			{/each}
		</select>

		<button
			class="toggle-btn"
			class:on={activeOnly}
			onclick={() => (activeOnly = !activeOnly)}
			role="switch"
			aria-checked={activeOnly}
		>
			<span class="sw"></span>
			<span>Active only</span>
		</button>

		<div class="search-wrap">
			<span class="search-icon-wrap"><Search size={14} /></span>
			<input
				class="search-input"
				placeholder="Search cron id, prompt, schedule…"
				bind:value={query}
			/>
		</div>
	</div>

	<!-- Section bar -->
	<div class="section-bar">
		<span class="section-cmd">
			<span class="dollar">$</span>
			crons --project={projectFilter}{activeOnly ? ' --active-only' : ''}{query
				? ` --search="${query}"`
				: ''}
		</span>
		<span class="section-count">
			showing <b>{sorted.length}</b> of <b>{counts.total}</b>
		</span>
	</div>

	<!-- List / empty state -->
	{#if data.jobs.length === 0}
		<!-- Big empty state (no crons ever created) -->
		<div class="big-empty">
			<div class="empty-icon-frame">
				<Calendar size={28} />
			</div>
			<h3 class="empty-h3">No cron jobs yet</h3>
			<p class="empty-body">
				When Claude Code creates a scheduled job during a session — via
				<code>CronCreate</code> — it'll show up here. Jobs are in-memory and session-scoped, so
				this page reconstructs their history from your session logs after the fact.
			</p>
			<div class="code-hint">
				<span class="dollar">$</span> ask claude to "remind me every 5 minutes to check the build"
			</div>
			<p class="empty-fine">
				Already created one and not seeing it? Check that the session log was written to disk.
			</p>
		</div>
	{:else if sorted.length === 0}
		<div class="filter-empty">No cron jobs match these filters.</div>
	{:else}
		<div class="cron-list">
			{#each sorted as job (jobKey(job))}
				{@const key = jobKey(job)}
				{@const expanded = openIds.has(key)}
				{@const meta = getStatusMeta(job)}
				{@const ttl = getTtlInfo(job)}
				{@const s = statusOf(job)}
				{@const human = cronHuman(job.cron_expression)}

				<div class="cron-card" class:expanded class:gone={s !== 'active'}>
					<!-- ── Collapsed row ─────────────────────────────────────────── -->
					<button
						type="button"
						class="cron-row"
						onclick={() => toggle(key)}
					>
						<!-- Caret -->
						<span class="caret" class:open={expanded} aria-hidden="true">
							<ChevronRight size={14} />
						</span>

						<!-- Status dot -->
						<span
							class="status-dot"
							class:dot-truth={meta.dot === 'truth'}
							style={dotStyle(meta.dot)}
						></span>

						<!-- Content column -->
						<div class="row-content">
							<!-- Line 1: ID + pills + status tag -->
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
									class:tag-active={!meta.isLikely && s === 'active'}
									class:tag-likely={meta.isLikely}
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

							<!-- Line 2: Prompt preview -->
							<div class="row-prompt">
								<span class="quote">"</span>{job.prompt}<span class="quote">"</span>
							</div>

							<!-- Line 3: Meta -->
							<div class="row-meta-line">
								<span class="mono-dim">{job.cron_expression}</span>
								<span class="sep">·</span>
								<span class="mono-dim">{job.project_display_name ?? '—'}</span>
								{#if job.fires && job.fires.length > 0}
									<span class="sep">·</span>
									<span class="mono-dim"
										>{job.fires.length}
										{job.fires.length === 1 ? 'fire' : 'fires'}</span
									>
								{/if}
							</div>
						</div>

						<!-- TTL meta column -->
						<div class="ttl-col">
							{#if s === 'deleted'}
								<span class="ttl-done">deleted</span>
								<div class="ttl-sub">{formatTimeAgo(job.deleted_at!)}</div>
							{:else if ttl.expired}
								<span class="ttl-done">TTL elapsed</span>
								<div class="ttl-bar-wrap">
									<div class="ttl-bar-track">
										<div class="ttl-bar-fill" style="width: 100%; background: var(--text-faint); opacity: 0.4;"></div>
									</div>
								</div>
								<div class="ttl-sub">{formatTimeAgo(job.ttl_expires_at)}</div>
							{:else}
								<div class="ttl-remaining" class:warn={ttl.warn}>
									<span class="ttl-num">{formatRelative(ttl.remaining)}</span>
									<span class="ttl-lbl">left</span>
								</div>
								<div class="ttl-bar-wrap">
									<div class="ttl-bar-track">
										<div
											class="ttl-bar-fill"
											style="width: {ttl.pct}%; background: {ttl.warn
												? 'var(--warning)'
												: 'var(--success)'};"
										></div>
									</div>
								</div>
								<div class="ttl-sub">TTL {formatShortTime(job.ttl_expires_at)}</div>
							{/if}
						</div>
					</button>

					<!-- ── Expanded panel ────────────────────────────────────────── -->
					{#if expanded}
						<div class="panel">
							<!-- Top metadata rows spanning both columns -->
							<div class="meta-strip">
								<div class="kv-row">
									<span class="kv-label">Cron ID</span>
									<span class="kv-val" style="color: var(--accent);"
										>{job.cron_id ?? job.tool_use_id}</span
									>
								</div>
								<div class="kv-row">
									<span class="kv-label">Schedule</span>
									<span class="kv-val">
										{job.cron_expression}<span class="kv-sep"> · </span><span
											class="kv-dim">{human}</span
										>
									</span>
								</div>
								<div class="kv-row">
									<span class="kv-label">Created</span>
									<span class="kv-val">
										{formatAbsolute(job.created_at)}<span class="kv-sep kv-dim"> · {formatTimeAgo(job.created_at)}</span>
									</span>
								</div>
								<div class="kv-row">
									<span class="kv-label">TTL expires</span>
									<span class="kv-val">
										{formatAbsolute(job.ttl_expires_at)}<span class="kv-sep kv-dim"> · {formatTimeAgo(job.ttl_expires_at)}</span>
									</span>
								</div>
								{#if job.deleted_at}
									<div class="kv-row">
										<span class="kv-label">Deleted</span>
										<span class="kv-val">
											{formatAbsolute(job.deleted_at)}<span class="kv-sep kv-dim"> · {meta.via}</span>
										</span>
									</div>
								{/if}
								<div class="kv-row">
									<span class="kv-label">Project</span>
									<span class="kv-val">{job.project_display_name ?? '—'}</span>
								</div>
								<div class="kv-row">
									<span class="kv-label">Source session</span>
									<span class="kv-val">
										{#if job.project_encoded_name}
											<a
												class="session-link"
												href="/projects/{job.project_encoded_name}/{job.session_slug ?? job.session_uuid}"
												onclick={(e) => e.stopPropagation()}
											>{job.session_uuid.slice(0, 13)}…</a>
										{:else}
											<span>{job.session_uuid.slice(0, 13)}…</span>
										{/if}
									</span>
								</div>
								{#if job.latest_state}
									<div class="kv-row">
										<span class="kv-label">Ground-truth state</span>
										<span class="kv-val">
											<span style="color: var(--success);">● alive</span>
											<span class="kv-dim"> · observed {formatTimeAgo(job.latest_state.captured_at)}</span>
										</span>
									</div>
								{/if}
							</div>

							<!-- Bottom row: prompt block ← → fires scroll — same height naturally -->
							<div class="prompt-fires-row">
								<!-- Left: prompt -->
								<div class="prompt-col">
									<span class="kv-label">Prompt</span>
									<div class="prompt-block">
										<span class="barb">{'>'}</span>
										{job.prompt}
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
										<span class="fires-source">
											{job.fires?.some((f) => f.inference_source === 'hook')
												? 'hook · ground truth'
												: 'inferred from logs'}
										</span>
									</div>

									{#if !job.fires || job.fires.length === 0}
										<div class="fires-empty">
											{#if job.recurring}
												No fires observed in the session log yet.
											{:else}
												One-shot cron — no fires recorded.
											{/if}
										</div>
									{:else}
										<div class="fires-scroll">
											{#each job.fires as fire, i}
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
						</div>
					{/if}
				</div>
			{/each}
		</div>

		<!-- Footer hint -->
		<div class="footer-hint">
			<kbd class="kbd">↵</kbd>
			<span>Click any row to expand fire history</span>
			<span class="footer-right">Reconstructed from session logs · <span class="mono-dim">{formatTimeAgo(new Date().toISOString())}</span></span>
		</div>
	{/if}
</div>

<style>
	.page-wrap {
		max-width: 1120px;
		margin: 0 auto;
		padding: 32px 32px 80px;
		display: flex;
		flex-direction: column;
		gap: 0;
	}

	.tagline {
		font-size: 14px;
		color: var(--accent);
		margin: 0 0 24px;
		white-space: nowrap;
	}

	/* ── Caveat banner ─────────────────────────────────────────────────────── */
	.caveat-banner {
		display: flex;
		align-items: flex-start;
		gap: 10px;
		background: var(--bg-subtle);
		border: 1px solid var(--border);
		border-radius: 10px;
		padding: 10px 12px 10px 14px;
		font-size: 12.5px;
		line-height: 1.55;
		color: var(--text-muted);
		margin-bottom: 22px;
	}

	.caveat-body {
		flex: 1;
	}

	.caveat-body b {
		font-weight: 600;
		color: var(--text-primary);
	}

	.caveat-close {
		margin-left: auto;
		padding: 2px;
		color: var(--text-faint);
		background: none;
		border: none;
		cursor: pointer;
		line-height: 1;
		display: flex;
	}

	.caveat-close:hover {
		color: var(--text-primary);
	}

	/* ── Stat strip ────────────────────────────────────────────────────────── */
	.stat-grid {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: 12px;
		margin-bottom: 22px;
	}

	.stat-card {
		display: flex;
		align-items: center;
		gap: 14px;
		background: var(--bg-base);
		border: 1px solid var(--border);
		border-radius: 12px;
		padding: 16px 18px;
	}

	.stat-ico {
		width: 36px;
		height: 36px;
		border-radius: 9px;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
	}

	.stat-num {
		font-size: 26px;
		font-weight: 600;
		letter-spacing: -0.02em;
		line-height: 1;
		font-variant-numeric: tabular-nums;
		display: flex;
		align-items: baseline;
		gap: 4px;
	}

	.approx {
		font-size: 13px;
		font-weight: 500;
		color: var(--text-faint);
		letter-spacing: 0;
	}

	.stat-label {
		font-size: 12px;
		color: var(--text-muted);
		margin-top: 4px;
	}

	.pulse-dot {
		width: 7px;
		height: 7px;
		border-radius: 50%;
		background: var(--success);
		display: inline-block;
		margin-left: 4px;
		animation: cronPulse 1.6s infinite;
	}

	@keyframes cronPulse {
		0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.6); }
		70% { box-shadow: 0 0 0 8px rgba(16, 185, 129, 0); }
		100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
	}

	/* ── Toolbar ───────────────────────────────────────────────────────────── */
	.toolbar {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 8px;
		margin-bottom: 14px;
	}

	.select-input {
		height: 32px;
		padding: 0 10px 0 12px;
		border: 1px solid var(--border-hover);
		background: var(--bg-base);
		border-radius: 8px;
		font-size: 13px;
		color: var(--text-primary);
		cursor: pointer;
	}

	.toggle-btn {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		height: 34px;
		padding: 0 12px;
		border: 1px solid var(--border-hover);
		border-radius: 8px;
		background: var(--bg-base);
		font-size: 13px;
		color: var(--text-muted);
		cursor: pointer;
		user-select: none;
	}

	.toggle-btn:hover {
		background: var(--bg-subtle);
	}

	.toggle-btn.on {
		color: var(--text-primary);
	}

	.sw {
		width: 26px;
		height: 15px;
		background: #d8d8d4;
		border-radius: 99px;
		position: relative;
		transition: background 0.15s;
		flex-shrink: 0;
	}

	.sw::after {
		content: '';
		position: absolute;
		top: 2px;
		left: 2px;
		width: 11px;
		height: 11px;
		background: white;
		border-radius: 50%;
		transition: transform 0.15s;
		box-shadow: 0 1px 2px rgba(0, 0, 0, 0.2);
	}

	.toggle-btn.on .sw {
		background: var(--accent);
	}

	.toggle-btn.on .sw::after {
		transform: translateX(11px);
	}

	.search-wrap {
		position: relative;
		flex: 1;
		min-width: 200px;
		display: flex;
		align-items: center;
	}

	.search-icon-wrap {
		position: absolute;
		left: 11px;
		color: var(--text-faint);
		pointer-events: none;
		display: flex;
		align-items: center;
	}

	.search-input {
		width: 100%;
		height: 34px;
		border: 1px solid var(--border-hover);
		border-radius: 8px;
		background: var(--bg-base);
		padding: 0 12px 0 34px;
		font-size: 13px;
		color: var(--text-primary);
		outline: none;
	}

	.search-input:focus {
		border-color: var(--accent);
		box-shadow: 0 0 0 3px var(--accent-muted);
	}

	.search-input::placeholder {
		color: var(--text-faint);
	}

	/* ── Section bar ───────────────────────────────────────────────────────── */
	.section-bar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		background: var(--bg-subtle);
		border: 1px solid var(--border);
		border-radius: 10px;
		padding: 10px 14px;
		font-family: var(--font-mono);
		font-size: 13px;
		color: var(--text-primary);
		margin-bottom: 12px;
		overflow: hidden;
	}

	.section-cmd {
		display: flex;
		align-items: center;
		gap: 8px;
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.dollar {
		color: var(--accent);
		font-weight: 600;
		flex-shrink: 0;
	}

	.section-count {
		font-size: 12.5px;
		color: var(--text-muted);
		flex-shrink: 0;
		font-family: inherit;
	}

	.section-count b {
		font-weight: 600;
		color: var(--text-primary);
	}

	/* ── Cron list ─────────────────────────────────────────────────────────── */
	.cron-list {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.cron-card {
		border: 1px solid var(--border);
		background: var(--bg-base);
		border-radius: 12px;
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
		box-shadow: 0 1px 0 rgba(0, 0, 0, 0.03), 0 6px 20px -8px rgba(0, 0, 0, 0.08);
	}

	.cron-card.gone {
		background: var(--bg-subtle);
	}

	.cron-row {
		display: grid;
		grid-template-columns: 18px 14px 1fr auto;
		align-items: center;
		gap: 14px;
		padding: 14px 16px;
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
		box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.18);
		animation: cronPulse 1.6s infinite;
	}

	/* ── Row content ───────────────────────────────────────────────────────── */
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
		gap: 8px;
	}

	.cron-id {
		font-family: var(--font-mono);
		font-size: 12.5px;
		font-weight: 600;
		color: var(--accent);
	}

	.pill {
		display: inline-flex;
		align-items: center;
		font-size: 10.5px;
		font-weight: 600;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		padding: 2px 7px;
		border-radius: 5px;
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
		font-size: 10.5px;
		font-weight: 600;
		letter-spacing: 0.05em;
		text-transform: uppercase;
		color: var(--text-muted);
		display: inline-flex;
		align-items: center;
		gap: 3px;
	}

	.tag-active,
	.tag-likely {
		color: var(--success);
	}

	.qm {
		font-family: var(--font-mono);
		font-size: 11px;
		opacity: 0.7;
		letter-spacing: 0;
		text-transform: none;
	}

	.via {
		color: var(--text-faint);
		font-weight: 500;
		text-transform: none;
		letter-spacing: 0;
		font-size: 11.5px;
	}

	.row-prompt {
		font-size: 13px;
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

	.row-meta-line {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 6px;
		font-size: 12px;
		color: var(--text-muted);
	}

	.mono-dim {
		font-family: var(--font-mono);
		color: var(--text-muted);
	}

	.sep {
		color: var(--text-faint);
	}

	/* ── TTL column ────────────────────────────────────────────────────────── */
	.ttl-col {
		text-align: right;
		display: flex;
		flex-direction: column;
		align-items: flex-end;
		gap: 5px;
		min-width: 130px;
	}

	.ttl-done {
		font-size: 12.5px;
		color: var(--text-faint);
		font-variant-numeric: tabular-nums;
	}

	.ttl-remaining {
		display: flex;
		align-items: baseline;
		gap: 5px;
		font-size: 12.5px;
		font-weight: 500;
		color: var(--text-primary);
	}

	.ttl-remaining.warn .ttl-num {
		color: var(--warning);
	}

	.ttl-num {
		font-family: var(--font-mono);
		font-variant-numeric: tabular-nums;
	}

	.ttl-lbl {
		font-size: 11px;
		color: var(--text-faint);
	}

	.ttl-bar-wrap {
		width: 110px;
	}

	.ttl-bar-track {
		height: 3px;
		background: var(--bg-muted);
		border-radius: 99px;
		overflow: hidden;
	}

	.ttl-bar-fill {
		height: 100%;
		border-radius: 99px;
		transition: width 0.3s;
	}

	.ttl-sub {
		font-family: var(--font-mono);
		font-size: 11.5px;
		color: var(--text-faint);
	}

	/* ── Expanded panel ────────────────────────────────────────────────────── */
	.panel {
		border-top: 1px dashed var(--border);
		padding: 16px 18px 18px;
		display: flex;
		flex-direction: column;
		gap: 16px;
	}

	/* Metadata rows sit above, full width */
	.meta-strip {
		display: flex;
		flex-wrap: wrap;
		gap: 12px 24px;
	}

	.meta-strip .kv-row {
		min-width: 160px;
	}

	/* Prompt + fires side by side — height is driven by whichever is taller */
	.prompt-fires-row {
		display: grid;
		grid-template-columns: 260px 1fr;
		align-items: stretch;
		gap: 22px;
		border-top: 1px dashed var(--border);
		padding-top: 14px;
	}

	.prompt-col {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	.prompt-col .prompt-block {
		flex: 1;
	}

	/* ── Key-value column (kept for any remaining .kv-row usage) ───────────── */
	.kv-col {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.kv-row {
		display: flex;
		flex-direction: column;
		gap: 3px;
	}

	.kv-label {
		font-size: 10.5px;
		letter-spacing: 0.07em;
		text-transform: uppercase;
		color: var(--text-faint);
		font-weight: 600;
	}

	.kv-val {
		font-family: var(--font-mono);
		font-size: 12.5px;
		line-height: 1.5;
		color: var(--text-primary);
	}

	.kv-sep {
		color: var(--text-faint);
	}

	.kv-dim {
		color: var(--text-faint);
	}

	.session-link {
		color: var(--accent);
		border-bottom: 1px solid rgba(124, 58, 237, 0.3);
		text-decoration: none;
	}

	.session-link:hover {
		border-bottom-color: var(--accent);
	}

	.prompt-block {
		background: var(--bg-subtle);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 10px 12px;
		font-family: var(--font-mono);
		font-size: 12px;
		line-height: 1.55;
		color: var(--text-primary);
		white-space: pre-wrap;
		word-break: break-word;
		margin-top: 2px;
	}

	.barb {
		color: var(--accent);
		font-weight: 600;
		margin-right: 6px;
	}

	/* ── Fires column ──────────────────────────────────────────────────────── */
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
		margin-bottom: 10px;
	}

	.fires-source {
		font-size: 11px;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		color: var(--text-faint);
	}

	.fire-card {
		background: var(--bg-subtle);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 10px 12px;
		margin-bottom: 6px;
	}

	.fire-head {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 8px;
		margin-bottom: 6px;
	}

	.fire-time {
		font-family: var(--font-mono);
		font-size: 11.5px;
		color: var(--text-muted);
	}

	.fire-time b {
		color: var(--text-primary);
		font-weight: 500;
	}

	.fire-ago {
		font-size: 11.5px;
		color: var(--text-faint);
	}

	.fire-conf {
		margin-left: auto;
		display: inline-flex;
		align-items: center;
		gap: 6px;
		font-family: var(--font-mono);
		font-size: 11px;
	}

	.conf-bar {
		width: 38px;
		height: 3px;
		background: rgba(0, 0, 0, 0.06);
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
		font-size: 13px;
		line-height: 1.55;
		color: var(--text-primary);
		white-space: pre-wrap;
		word-break: break-word;
	}

	.fires-empty {
		padding: 20px;
		text-align: center;
		color: var(--text-muted);
		background: var(--bg-subtle);
		border: 1px dashed var(--border);
		border-radius: 8px;
		font-size: 12.5px;
		line-height: 1.55;
	}

	/* ── Big empty state ───────────────────────────────────────────────────── */
	.big-empty {
		border: 1px dashed var(--border);
		border-radius: 14px;
		background: var(--bg-subtle);
		padding: 64px 32px 72px;
		display: flex;
		flex-direction: column;
		align-items: center;
		text-align: center;
		gap: 14px;
	}

	.empty-icon-frame {
		width: 56px;
		height: 56px;
		border-radius: 14px;
		background: var(--accent-muted);
		color: var(--accent);
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.empty-h3 {
		font-size: 18px;
		font-weight: 600;
		letter-spacing: -0.01em;
		color: var(--text-primary);
		margin: 0;
	}

	.empty-body {
		max-width: 440px;
		font-size: 13px;
		color: var(--text-muted);
		line-height: 1.55;
		margin: 0;
	}

	.code-hint {
		background: var(--bg-base);
		border: 1px solid var(--border);
		border-radius: 8px;
		padding: 8px 14px;
		font-family: var(--font-mono);
		font-size: 12.5px;
		color: var(--text-primary);
	}

	.empty-fine {
		font-size: 11.5px;
		color: var(--text-faint);
		margin: 0;
	}

	.filter-empty {
		padding: 60px 20px;
		text-align: center;
		color: var(--text-muted);
		border: 1px dashed var(--border);
		border-radius: 12px;
		background: var(--bg-subtle);
	}

	/* ── Footer hint ───────────────────────────────────────────────────────── */
	.footer-hint {
		display: flex;
		align-items: center;
		gap: 8px;
		margin-top: 18px;
		font-size: 12px;
		color: var(--text-faint);
	}

	.footer-right {
		margin-left: auto;
	}

	.kbd {
		font-family: var(--font-mono);
		font-size: 11px;
		background: var(--bg-subtle);
		border: 1px solid var(--border);
		border-bottom-width: 2px;
		padding: 1px 5px;
		border-radius: 4px;
		color: var(--text-primary);
	}

	/* ── Rescan button ─────────────────────────────────────────────────────── */
	.rescan-btn {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		height: 34px;
		padding: 0 12px;
		border-radius: 8px;
		border: 1px solid var(--border-hover);
		background: var(--bg-base);
		font-size: 13px;
		font-weight: 500;
		color: var(--text-primary);
		cursor: pointer;
	}

	.rescan-btn:hover {
		background: var(--bg-subtle);
	}

	.rescan-btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	:global(.spinning) {
		animation: spin 1s linear infinite;
	}

	@keyframes spin {
		from { transform: rotate(0deg); }
		to { transform: rotate(360deg); }
	}

	/* ── Responsive ────────────────────────────────────────────────────────── */
	@media (max-width: 760px) {
		.stat-grid {
			grid-template-columns: 1fr;
		}

		.prompt-fires-row {
			grid-template-columns: 1fr;
		}

		.cron-row {
			grid-template-columns: 18px 14px 1fr;
		}

		.ttl-col {
			display: none;
		}
	}
</style>
