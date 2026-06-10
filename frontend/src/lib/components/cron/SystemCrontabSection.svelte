<!--
  SystemCrontabSection — ADDITIVE feature (not upstream).

  Renders the host's real Linux cron table (the OS cron daemon), distinct
  from Claude Code's session-scoped CronCreate jobs shown above on /cron.
  Entries are grouped by origin (Claude skill / Claude / user / system) so
  the signal (your skill crons) is separated from OS noise (run-parts, etc).
  Self-fetches GET /cron/system so the page's +page.server.ts stays untouched.
-->
<script lang="ts">
	import { onMount } from 'svelte';
	import { Terminal, RefreshCw, AlertTriangle, ChevronRight } from 'lucide-svelte';
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
	let open = $state(true);
	// Origins collapsed by default — OS noise starts folded.
	let collapsed = $state<Set<string>>(new Set(['system']));

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
			hint: 'cron déclaré par un skill Claude'
		},
		claude: { label: 'Claude', cls: 'o-claude', hint: 'script sous ~/.claude' },
		user: { label: 'User', cls: 'o-user', hint: 'crontab utilisateur, hors Claude' },
		system: { label: 'Système · OS', cls: 'o-system', hint: 'paquets système, run-parts, /etc' }
	};

	function nextMs(e: SystemCronEntry): number {
		return e.next_run ? new Date(e.next_run).getTime() : Number.POSITIVE_INFINITY;
	}

	const groups = $derived(
		ORIGIN_ORDER.map((origin) => ({
			origin,
			...ORIGIN_META[origin],
			items: entries.filter((e) => e.origin === origin).sort((a, b) => nextMs(a) - nextMs(b))
		})).filter((g) => g.items.length > 0)
	);

	function toggleGroup(origin: string) {
		const next = new Set(collapsed);
		next.has(origin) ? next.delete(origin) : next.add(origin);
		collapsed = next;
	}

	function nextRunLabel(iso: string | null): string {
		if (!iso) return '—';
		const d = new Date(iso);
		const delta = d.getTime() - Date.now();
		const mins = Math.round(delta / 60000);
		if (mins < 0) return d.toLocaleString();
		if (mins < 60) return `in ${mins}m`;
		const hrs = Math.round(mins / 60);
		if (hrs < 24) return `in ${hrs}h`;
		return `in ${Math.round(hrs / 24)}d`;
	}
</script>

<section class="sys-wrap">
	<div class="sys-head">
		<button class="sys-toggle" onclick={() => (open = !open)} aria-expanded={open}>
			<span class="sys-icon"><Terminal size={16} /></span>
			<div class="sys-title-col">
				<span class="sys-title">Linux crontab · système</span>
				<span class="sys-sub">
					Vraie table cron de l'OS, groupée par origine — distincte des crons Claude
					(CronCreate) ci-dessus.
				</span>
			</div>
			<span class="sys-count">{entries.length}</span>
			<span class="sys-caret" class:open aria-hidden="true"><ChevronRight size={15} /></span>
		</button>
		<button class="sys-refresh" onclick={load} disabled={loading} aria-label="Reload crontab">
			<RefreshCw size={13} class={loading ? 'spinning' : ''} />
		</button>
	</div>

	{#if open}
		<div class="sys-body">
			{#if loading && entries.length === 0}
				<div class="sys-state">Lecture de la crontab…</div>
			{:else if loadError}
				<div class="sys-state sys-err">
					<AlertTriangle size={14} /> Impossible de lire <code>/cron/system</code> : {loadError}
				</div>
			{:else if !supported}
				<div class="sys-state">
					{unsupportedNote ?? 'Pas de daemon cron sur cette plateforme.'}
				</div>
			{:else if entries.length === 0}
				<div class="sys-state">Aucune entrée crontab sur cette machine.</div>
			{:else}
				{#if errors.length}
					<div class="sys-warn"><AlertTriangle size={13} />{errors.join(' · ')}</div>
				{/if}

				{#each groups as g (g.origin)}
					{@const isOpen = !collapsed.has(g.origin)}
					<div class="grp">
						<button
							class="grp-head"
							onclick={() => toggleGroup(g.origin)}
							aria-expanded={isOpen}
						>
							<span class="grp-caret" class:open={isOpen} aria-hidden="true">
								<ChevronRight size={13} />
							</span>
							<span class="badge {g.cls}">{g.label}</span>
							<span class="grp-hint">{g.hint}</span>
							<span class="grp-count">{g.items.length}</span>
						</button>

						{#if isOpen}
							<div class="sys-table" role="table">
								<div class="sys-tr sys-th" role="row">
									<span role="columnheader">Schedule</span>
									<span role="columnheader">Command</span>
									<span role="columnheader">User</span>
									<span role="columnheader">Source</span>
									<span role="columnheader">Next</span>
								</div>
								{#each g.items as e (e.raw)}
									<div class="sys-tr" role="row">
										<span class="sys-sched" title={e.schedule} role="cell"
											>{e.schedule_human}</span
										>
										<span class="sys-cmd" role="cell">
											{#if e.skill}<span
													class="skill-tag"
													title="skill Claude">{e.skill}</span
												>{/if}
											<span class="cmd-txt" title={e.command}
												>{e.command}</span
											>
										</span>
										<span class="sys-user" role="cell">{e.user ?? '—'}</span>
										<span class="sys-source" title={e.source} role="cell"
											>{e.source}</span
										>
										<span class="sys-next" role="cell"
											>{nextRunLabel(e.next_run)}</span
										>
									</div>
								{/each}
							</div>
						{/if}
					</div>
				{/each}
			{/if}
		</div>
	{/if}
</section>

<style>
	.sys-wrap {
		margin-top: 28px;
		border: 1px solid var(--border);
		border-radius: 14px;
		background: var(--bg-base);
		overflow: hidden;
	}

	.sys-head {
		display: flex;
		align-items: center;
		width: 100%;
		background: var(--bg-subtle);
		border-bottom: 1px solid var(--border);
		padding-right: 12px;
	}

	.sys-toggle {
		display: flex;
		align-items: center;
		gap: 12px;
		flex: 1;
		min-width: 0;
		padding: 14px 12px 14px 16px;
		background: none;
		border: none;
		cursor: pointer;
		text-align: left;
	}

	.sys-icon {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 30px;
		height: 30px;
		border-radius: 8px;
		background: var(--accent-muted);
		color: var(--accent);
		flex-shrink: 0;
	}

	.sys-title-col {
		display: flex;
		flex-direction: column;
		gap: 2px;
		min-width: 0;
		flex: 1;
	}

	.sys-title {
		font-size: 14px;
		font-weight: 600;
		color: var(--text-primary);
	}

	.sys-sub {
		font-size: 12px;
		color: var(--text-muted);
		line-height: 1.4;
	}

	.sys-err code {
		font-family: var(--font-mono);
		font-size: 11.5px;
		background: var(--bg-muted);
		padding: 0 4px;
		border-radius: 4px;
	}

	.sys-count {
		font-family: var(--font-mono);
		font-size: 12.5px;
		font-weight: 600;
		color: var(--accent);
		background: var(--accent-muted);
		padding: 2px 9px;
		border-radius: 99px;
		flex-shrink: 0;
	}

	.sys-refresh {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 28px;
		height: 28px;
		border: 1px solid var(--border-hover);
		border-radius: 7px;
		background: var(--bg-base);
		color: var(--text-muted);
		cursor: pointer;
		flex-shrink: 0;
	}

	.sys-refresh:hover {
		background: var(--bg-subtle);
	}

	.sys-refresh:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.sys-caret {
		color: var(--text-faint);
		display: flex;
		align-items: center;
		transition: transform 0.15s;
		flex-shrink: 0;
	}

	.sys-caret.open {
		transform: rotate(90deg);
	}

	.sys-body {
		padding: 10px 14px 16px;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}

	.sys-state {
		padding: 28px 16px;
		text-align: center;
		color: var(--text-muted);
		font-size: 13px;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 8px;
	}

	.sys-err {
		color: var(--warning);
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

	/* ── group ─────────────────────────────────────────────────────────────── */
	.grp {
		border: 1px solid var(--border);
		border-radius: 10px;
		overflow: hidden;
	}

	.grp-head {
		display: flex;
		align-items: center;
		gap: 10px;
		width: 100%;
		padding: 9px 12px;
		background: var(--bg-subtle);
		border: none;
		cursor: pointer;
		text-align: left;
	}

	.grp-caret {
		color: var(--text-faint);
		display: flex;
		align-items: center;
		transition: transform 0.15s;
		flex-shrink: 0;
	}

	.grp-caret.open {
		transform: rotate(90deg);
	}

	.grp-hint {
		font-size: 12px;
		color: var(--text-muted);
		flex: 1;
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.grp-count {
		font-family: var(--font-mono);
		font-size: 11.5px;
		font-weight: 600;
		color: var(--text-muted);
		background: var(--bg-muted);
		padding: 1px 8px;
		border-radius: 99px;
		flex-shrink: 0;
	}

	/* ── origin badges ─────────────────────────────────────────────────────── */
	.badge {
		font-size: 10.5px;
		font-weight: 600;
		letter-spacing: 0.03em;
		text-transform: uppercase;
		padding: 2px 8px;
		border-radius: 6px;
		font-family: var(--font-mono);
		flex-shrink: 0;
	}

	.o-skill {
		background: var(--accent-muted);
		color: var(--accent);
	}

	.o-claude {
		background: var(--info-subtle, rgba(59, 130, 246, 0.12));
		color: var(--info, #3b82f6);
	}

	.o-user {
		background: var(--success-subtle, rgba(34, 197, 94, 0.12));
		color: var(--success, #22c55e);
	}

	.o-system {
		background: var(--bg-muted);
		color: var(--text-faint);
	}

	/* ── table ─────────────────────────────────────────────────────────────── */
	.sys-table {
		display: flex;
		flex-direction: column;
		font-size: 12.5px;
	}

	.sys-tr {
		display: grid;
		grid-template-columns: 130px 1fr 90px 160px 80px;
		gap: 12px;
		align-items: center;
		padding: 9px 12px;
		border-bottom: 1px solid var(--border-subtle);
	}

	.sys-tr:last-child {
		border-bottom: none;
	}

	.sys-th {
		font-size: 10.5px;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		color: var(--text-faint);
		font-weight: 600;
		border-bottom: 1px solid var(--border);
		background: var(--bg-base);
	}

	.sys-sched {
		font-family: var(--font-mono);
		color: var(--text-primary);
		font-weight: 500;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.sys-cmd {
		display: flex;
		align-items: center;
		gap: 7px;
		min-width: 0;
	}

	.skill-tag {
		font-family: var(--font-mono);
		font-size: 10.5px;
		font-weight: 600;
		color: var(--accent);
		background: var(--accent-muted);
		padding: 1px 6px;
		border-radius: 5px;
		flex-shrink: 0;
	}

	.cmd-txt {
		font-family: var(--font-mono);
		color: var(--text-muted);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		min-width: 0;
	}

	.sys-user {
		color: var(--text-muted);
		font-family: var(--font-mono);
	}

	.sys-source {
		color: var(--text-faint);
		font-family: var(--font-mono);
		font-size: 11.5px;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.sys-next {
		color: var(--text-muted);
		font-variant-numeric: tabular-nums;
		text-align: right;
		white-space: nowrap;
	}

	@media (max-width: 760px) {
		.sys-tr {
			grid-template-columns: 100px 1fr 70px;
		}
		.sys-source,
		.sys-next {
			display: none;
		}
	}
</style>
