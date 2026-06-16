<!--
  SystemCrontabSection — renders the host's real OS cron table (the cron
  daemon), distinct from Claude Code's session-scoped CronCreate jobs on
  /cron. Each entry is an expandable card mirroring the Claude cron list:
  the expanded panel shows the raw crontab line, its source, and a schedule
  timeline (recent + upcoming fire times computed from the expression — the
  OS keeps no per-job run history to read back). Self-fetches
  GET /cron/system so the page's +page.server.ts stays untouched.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { RefreshCw, AlertTriangle, ChevronRight } from 'lucide-svelte';
	import { API_BASE } from '$lib/config';

	interface SystemCronEntry {
		schedule: string;
		schedule_human: string;
		command: string;
		user: string | null;
		source: string;
		origin: string;
		skill: string | null;
		next_run: string | null;
		recent_runs: string[];
		upcoming_runs: string[];
		description: string | null;
		raw: string;
	}
	interface SystemCronResponse {
		entries: SystemCronEntry[];
		count: number;
		by_source: Record<string, number>;
		by_origin: Record<string, number>;
		errors: string[];
		supported?: boolean;
		platform?: string;
		note?: string;
	}

	let entries = $state<SystemCronEntry[]>([]);
	let errors = $state<string[]>([]);
	let loading = $state(true);
	let loadError = $state<string | null>(null);
	let supported = $state(true);
	let unsupportedNote = $state<string | null>(null);
	let originFilter = $state<string>('all');
	let openKeys = $state<Set<string>>(new Set());

	async function load() {
		loading = true;
		loadError = null;
		try {
			const res = await fetch(`${API_BASE}/cron/system`);
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			const data: SystemCronResponse = await res.json();
			entries = data.entries ?? [];
			errors = data.errors ?? [];
			supported = data.supported !== false;
			unsupportedNote = data.note ?? null;
		} catch (e) {
			loadError = e instanceof Error ? e.message : 'fetch failed';
		} finally {
			loading = false;
		}
	}

	onMount(load);

	// ── origin taxonomy ───────────────────────────────────────────────────────
	const ORIGIN_ORDER = ['claude-skill', 'claude', 'user', 'system'] as const;
	const ORIGIN_META: Record<string, { label: string; cls: string; hint: string }> = {
		'claude-skill': {
			label: 'Claude · skill',
			cls: 'o-skill',
			hint: 'Scheduled by a Claude skill'
		},
		claude: { label: 'Claude', cls: 'o-claude', hint: 'Script under ~/.claude' },
		user: { label: 'User', cls: 'o-user', hint: 'User crontab, unrelated to Claude' },
		system: { label: 'System', cls: 'o-system', hint: 'OS packages, run-parts, /etc' }
	};

	function entryKey(e: SystemCronEntry): string {
		return `${e.source}\n${e.raw}`;
	}

	function nextMs(e: SystemCronEntry): number {
		return e.next_run ? new Date(e.next_run).getTime() : Number.POSITIVE_INFINITY;
	}

	// Origin chips: only origins that exist, in fixed order, with counts.
	const chips = $derived(
		ORIGIN_ORDER.map((o) => ({
			origin: o,
			...ORIGIN_META[o],
			count: entries.filter((e) => e.origin === o).length
		})).filter((c) => c.count > 0)
	);

	// Flat list: filter by chip, claude-first origin order, then soonest next.
	const visible = $derived(
		entries
			.filter((e) => originFilter === 'all' || e.origin === originFilter)
			.slice()
			.sort((a, b) => {
				const ao = ORIGIN_ORDER.indexOf(a.origin as (typeof ORIGIN_ORDER)[number]);
				const bo = ORIGIN_ORDER.indexOf(b.origin as (typeof ORIGIN_ORDER)[number]);
				if (ao !== bo) return ao - bo;
				return nextMs(a) - nextMs(b);
			})
	);

	function toggle(key: string) {
		const next = new Set(openKeys);
		if (next.has(key)) {
			next.delete(key);
		} else {
			next.add(key);
		}
		openKeys = next;
	}

	function relLabel(iso: string): string {
		const delta = new Date(iso).getTime() - Date.now();
		const mins = Math.round(Math.abs(delta) / 60000);
		const dir = delta < 0 ? 'ago' : '';
		const inPrefix = delta < 0 ? '' : 'in ';
		if (mins < 1) return delta < 0 ? 'just now' : 'now';
		if (mins < 60) return `${inPrefix}${mins}m ${dir}`.trim();
		const hrs = Math.round(mins / 60);
		if (hrs < 24) return `${inPrefix}${hrs}h ${dir}`.trim();
		return `${inPrefix}${Math.round(hrs / 24)}d ${dir}`.trim();
	}

	function shortTime(iso: string): string {
		return new Date(iso).toLocaleString(undefined, {
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}
</script>

<section class="sys-wrap">
	{#if loading && entries.length === 0}
		<div class="sys-state">Reading the crontab…</div>
	{:else if loadError}
		<div class="sys-state sys-err">
			<AlertTriangle size={14} /> Could not read <code>/cron/system</code>: {loadError}
		</div>
	{:else if !supported}
		<div class="sys-state">
			{unsupportedNote ?? 'No cron daemon on this platform.'}
		</div>
	{:else if entries.length === 0}
		<div class="sys-state">No crontab entries on this machine.</div>
	{:else}
		{#if errors.length}
			<div class="sys-warn"><AlertTriangle size={13} />{errors.join(' · ')}</div>
		{/if}

		<!-- Origin filter chips -->
		<div class="chips" role="tablist" aria-label="Filter by origin">
			<button
				class="chip"
				class:on={originFilter === 'all'}
				onclick={() => (originFilter = 'all')}
				role="tab"
				aria-selected={originFilter === 'all'}
			>
				All <span class="chip-n">{entries.length}</span>
			</button>
			{#each chips as c (c.origin)}
				<button
					class="chip {c.cls}"
					class:on={originFilter === c.origin}
					onclick={() => (originFilter = originFilter === c.origin ? 'all' : c.origin)}
					role="tab"
					aria-selected={originFilter === c.origin}
					title={c.hint}
				>
					{c.label} <span class="chip-n">{c.count}</span>
				</button>
			{/each}
			<button
				class="sys-refresh"
				onclick={load}
				disabled={loading}
				aria-label="Reload crontab"
			>
				<RefreshCw size={13} class={loading ? 'spinning' : ''} />
			</button>
		</div>

		<!-- Entry cards -->
		<div class="sc-list">
			{#each visible as e (entryKey(e))}
				{@const key = entryKey(e)}
				{@const expanded = openKeys.has(key)}
				{@const meta = ORIGIN_META[e.origin] ?? ORIGIN_META.user}
				<div class="sc-card" class:expanded>
					<button class="sc-row" onclick={() => toggle(key)} aria-expanded={expanded}>
						<span class="sc-dot {meta.cls}" title={meta.hint}></span>
						<div class="sc-main">
							<div class="sc-head">
								<span class="sc-sched" title={e.schedule}>{e.schedule_human}</span>
								<span class="sc-badge {meta.cls}">{meta.label}</span>
								{#if e.skill}<span class="sc-skill" title="Claude skill">{e.skill}</span>{/if}
							</div>
							{#if e.description}
								<div class="sc-desc">{e.description}</div>
							{/if}
							<div class="sc-cmd" title={e.command}>{e.command}</div>
						</div>
						<span class="sc-next">{e.next_run ? relLabel(e.next_run) : '—'}</span>
						<span class="sc-caret" class:open={expanded} aria-hidden="true">
							<ChevronRight size={14} />
						</span>
					</button>

					{#if expanded}
						<div class="sc-panel">
							{#if e.source !== 'user crontab' || e.user}
								<div class="sc-meta">
									{#if e.source !== 'user crontab'}
										<span class="sc-meta-item"
											><span class="sc-meta-k">source</span> {e.source}</span
										>
									{/if}
									{#if e.user}
										<span class="sc-meta-item"
											><span class="sc-meta-k">user</span> {e.user}</span
										>
									{/if}
								</div>
							{/if}

							{#if e.recent_runs.length || e.upcoming_runs.length}
								{@const rows = [
									...e.recent_runs.map((t) => ({ t, kind: 'past' })),
									{ t: '', kind: 'now' },
									...e.upcoming_runs.map((t) => ({ t, kind: 'next' }))
								]}
								<div class="fire-timeline">
									{#each rows as row, i (row.kind + row.t)}
										{@const last = i === rows.length - 1}
										<div class="fire-tl-row" class:last>
											<div class="fire-tl-track">
												<span
													class="fire-tl-dot"
													class:now={row.kind === 'now'}
													class:next={row.kind === 'next'}
												></span>
												{#if !last}<span class="fire-tl-line"></span>{/if}
											</div>
											<div class="fire-tl-content">
												{#if row.kind === 'now'}
													<span class="fire-tl-time now">now</span>
												{:else}
													<span class="fire-tl-time" class:dim={row.kind === 'past'}
														>{shortTime(row.t)}</span
													>
													<span class="fire-tl-ago">{relLabel(row.t)}</span>
												{/if}
											</div>
										</div>
									{/each}
								</div>
								<p class="sc-tl-note">
									Times computed from the schedule — the OS doesn't keep per-job run
									history.
								</p>
							{/if}
						</div>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</section>

<style>
	.sys-wrap {
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	.sys-refresh {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 26px;
		height: 26px;
		border: 1px solid var(--border-hover);
		border-radius: 7px;
		background: var(--bg-base);
		color: var(--text-muted);
		cursor: pointer;
	}

	.sys-refresh:hover {
		background: var(--bg-subtle);
	}

	.sys-refresh:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	/* ── states ────────────────────────────────────────────────────────────── */
	.sys-state {
		padding: 36px 16px;
		text-align: center;
		color: var(--text-muted);
		font-size: 13px;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 8px;
		border: 1px dashed var(--border);
		border-radius: 12px;
		background: var(--bg-subtle);
	}

	.sys-err {
		color: var(--warning);
	}

	.sys-err code {
		font-family: var(--font-mono);
		font-size: 11.5px;
		background: var(--bg-muted);
		padding: 0 4px;
		border-radius: 4px;
	}

	.sys-warn {
		display: flex;
		align-items: center;
		gap: 7px;
		font-size: 12px;
		color: var(--warning);
		padding: 7px 10px;
		background: var(--warning-subtle, rgba(234, 179, 8, 0.08));
		border-radius: 8px;
	}

	/* ── origin chips ──────────────────────────────────────────────────────── */
	.chips {
		display: flex;
		align-items: center;
		gap: 6px;
		flex-wrap: wrap;
	}

	.chip {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		height: 28px;
		padding: 0 11px;
		border: 1px solid var(--border-hover);
		border-radius: 99px;
		background: var(--bg-base);
		font-size: 12px;
		font-weight: 500;
		color: var(--text-muted);
		cursor: pointer;
	}

	.chip:hover {
		background: var(--bg-subtle);
	}

	.chip.on {
		border-color: var(--accent);
		background: var(--accent-muted);
		color: var(--accent);
		font-weight: 600;
	}

	.chip-n {
		font-family: var(--font-mono);
		font-size: 10.5px;
		background: var(--bg-muted);
		color: var(--text-muted);
		padding: 0 6px;
		border-radius: 99px;
	}

	.chip.on .chip-n {
		background: var(--bg-base);
		color: var(--accent);
	}

	/* ── entry cards (mirrors the Claude cron .cron-card pattern) ──────────── */
	.sc-list {
		display: flex;
		flex-direction: column;
		gap: 8px;
	}

	.sc-card {
		border: 1px solid var(--border);
		background: var(--bg-base);
		border-radius: 12px;
		overflow: hidden;
		transition:
			border-color 0.15s,
			box-shadow 0.15s;
	}

	.sc-card:hover {
		border-color: var(--border-hover);
	}

	.sc-card.expanded {
		border-color: var(--border-hover);
		box-shadow: 0 6px 20px -12px var(--border-subtle);
	}

	.sc-row {
		display: flex;
		align-items: center;
		gap: 12px;
		width: 100%;
		padding: 12px 14px;
		background: none;
		border: none;
		cursor: pointer;
		text-align: left;
		min-width: 0;
	}

	.sc-dot {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		flex-shrink: 0;
	}

	.sc-dot.o-skill {
		background: var(--accent);
	}
	.sc-dot.o-claude {
		background: var(--info, #3b82f6);
	}
	.sc-dot.o-user {
		background: var(--success, #22c55e);
	}
	.sc-dot.o-system {
		background: var(--text-faint);
	}

	.sc-main {
		display: flex;
		flex-direction: column;
		gap: 3px;
		flex: 1;
		min-width: 0;
	}

	.sc-head {
		display: flex;
		align-items: center;
		gap: 8px;
		min-width: 0;
	}

	.sc-sched {
		font-family: var(--font-mono);
		font-size: 13px;
		font-weight: 600;
		color: var(--text-primary);
		white-space: nowrap;
	}

	.sc-badge {
		font-size: 10px;
		font-weight: 600;
		letter-spacing: 0.03em;
		text-transform: uppercase;
		padding: 1px 7px;
		border-radius: 5px;
		font-family: var(--font-mono);
		flex-shrink: 0;
	}

	.sc-badge.o-skill {
		background: var(--accent-muted);
		color: var(--accent);
	}
	.sc-badge.o-claude {
		background: var(--info-subtle, rgba(59, 130, 246, 0.12));
		color: var(--info, #3b82f6);
	}
	.sc-badge.o-user {
		background: var(--success-subtle, rgba(34, 197, 94, 0.12));
		color: var(--success, #22c55e);
	}
	.sc-badge.o-system {
		background: var(--bg-muted);
		color: var(--text-faint);
	}

	.sc-skill {
		font-family: var(--font-mono);
		font-size: 10.5px;
		font-weight: 600;
		color: var(--accent);
		background: var(--accent-muted);
		padding: 1px 6px;
		border-radius: 5px;
		flex-shrink: 0;
	}

	.sc-desc {
		font-size: 13px;
		color: var(--text-primary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.sc-cmd {
		font-family: var(--font-mono);
		font-size: 12px;
		color: var(--text-muted);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.sc-next {
		font-size: 12px;
		color: var(--text-muted);
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
		flex-shrink: 0;
	}

	.sc-caret {
		color: var(--text-faint);
		display: flex;
		align-items: center;
		transition: transform 0.15s;
		flex-shrink: 0;
	}

	.sc-caret.open {
		transform: rotate(90deg);
	}

	/* ── expanded panel ────────────────────────────────────────────────────── */
	.sc-panel {
		padding: 12px 14px 14px 34px;
		border-top: 1px solid var(--border-subtle);
		background: var(--bg-subtle);
		display: flex;
		flex-direction: column;
		gap: 10px;
	}

	.sc-meta {
		display: flex;
		align-items: center;
		gap: 16px;
		flex-wrap: wrap;
	}

	.sc-meta-item {
		font-family: var(--font-mono);
		font-size: 11.5px;
		color: var(--text-muted);
	}

	.sc-meta-k {
		color: var(--text-faint);
		text-transform: uppercase;
		font-size: 10px;
		letter-spacing: 0.05em;
		margin-right: 4px;
	}

	/* ── schedule timeline (mirrors the Claude cron fire-history styles) ───── */
	.fire-timeline {
		display: flex;
		flex-direction: column;
		margin-top: 10px;
	}

	.fire-tl-row {
		display: grid;
		grid-template-columns: 20px 1fr;
		gap: 0 10px;
	}

	.fire-tl-track {
		display: flex;
		flex-direction: column;
		align-items: center;
		padding-top: 4px;
	}

	.fire-tl-dot {
		width: 7px;
		height: 7px;
		border-radius: 50%;
		background: var(--border-hover);
		flex-shrink: 0;
	}

	.fire-tl-dot.now {
		background: var(--accent);
		box-shadow: 0 0 0 2px var(--accent-muted);
	}

	.fire-tl-dot.next {
		background: var(--bg-base);
		border: 1.5px solid var(--accent);
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
		gap: 0 8px;
		padding-bottom: 12px;
	}

	.fire-tl-row.last .fire-tl-content {
		padding-bottom: 0;
	}

	.fire-tl-time {
		font-family: var(--font-mono);
		font-size: 12px;
		font-weight: 600;
		color: var(--text-primary);
	}

	.fire-tl-time.dim {
		color: var(--text-faint);
		font-weight: 500;
	}

	.fire-tl-time.now {
		color: var(--accent);
	}

	.fire-tl-ago {
		font-size: 11.5px;
		color: var(--text-faint);
	}

	.sc-tl-note {
		margin: 0;
		font-size: 11px;
		color: var(--text-faint);
	}

	@media (max-width: 760px) {
		.sc-next {
			display: none;
		}
	}
</style>
