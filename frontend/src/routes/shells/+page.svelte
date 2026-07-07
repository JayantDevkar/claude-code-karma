<script lang="ts">
	import { invalidateAll } from '$app/navigation';
	import type { BackgroundShell } from '$lib/api-types';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import StatsGrid from '$lib/components/StatsGrid.svelte';
	import { Activity, Terminal, Box } from 'lucide-svelte';

	type Tool = 'bash' | 'monitor' | 'manual';
	type Status = 'running' | 'closed';
	type CloseReason = 'kill' | 'natural' | 'timeout' | 'session_end';

	type Poll = {
		ts: string;
		bytes: number;
		text: string;
	};

	type Shell = {
		id: string;
		toolUseId: string;
		tool: Tool;
		command: string;
		description?: string;
		status: Status;
		closeReason?: CloseReason;
		exitCode?: number;
		spawnedAt: string;
		durationMs: number;
		pollCount: number;
		totalBytes: number;
		project: string;
		session: string;
		sessionUrl?: string;
		polls: Poll[];
	};

	let { data } = $props();

	function toShell(s: BackgroundShell): Shell {
		const running = s.terminated_at === null;
		const spawnedMs = new Date(s.spawned_at).getTime();
		const endMs = running ? Date.now() : new Date(s.terminated_at!).getTime();
		return {
			id: s.shell_id ?? s.tool_use_id,
			toolUseId: s.tool_use_id,
			tool: s.tool_name.toLowerCase() as Tool,
			command: s.command,
			description: s.description ?? undefined,
			status: running ? 'running' : 'closed',
			closeReason: (s.terminated_by as CloseReason) ?? undefined,
			exitCode: s.exit_code ?? undefined,
			spawnedAt: s.spawned_at,
			durationMs: endMs - spawnedMs,
			pollCount: s.poll_count,
			totalBytes: s.total_output_bytes,
			project: (s as any).project_display_name ?? (s as any).project_encoded_name ?? '—',
			session: (s as any).session_slug ?? s.session_uuid?.slice(0, 8) ?? '—',
			sessionUrl:
				(s as any).project_encoded_name && (s.session_uuid || (s as any).session_slug)
					? `/projects/${(s as any).project_encoded_name}/${(s as any).session_slug ?? s.session_uuid}`
					: undefined,
			polls: (s.polls ?? []).map((p) => ({
				ts: p.polled_at,
				bytes: p.output_bytes,
				text: p.output_excerpt ?? ''
			}))
		};
	}

	const shells = $derived((data.shells as BackgroundShell[]).map(toShell));

	// ---- kill ----
	let killing = $state<Set<string>>(new Set());

	async function killShell(toolUseId: string) {
		killing = new Set([...killing, toolUseId]);
		try {
			await fetch(`/api/shells/${encodeURIComponent(toolUseId)}/kill`, { method: 'POST' });
			await invalidateAll();
		} finally {
			killing = new Set([...killing].filter((id) => id !== toolUseId));
		}
	}

	// ---- filters ----
	let statusFilter = $state<'all' | Status>('all');
	let toolFilter = $state<'all' | Tool>('all');
	let projectFilter = $state<string>('all');
	let query = $state('');
	let openIds = $state<Set<string>>(new Set());
	let copiedIds = $state<Set<string>>(new Set());

	function copyCommand(id: string, command: string) {
		navigator.clipboard.writeText(command);
		copiedIds = new Set([...copiedIds, id]);
		setTimeout(() => {
			copiedIds = new Set([...copiedIds].filter((x) => x !== id));
		}, 1500);
	}

	const projects = $derived(Array.from(new Set(shells.map((s) => s.project))));

	// Global totals — always shown in the stat cards regardless of filters
	const globalCounts = $derived.by(() => {
		const total = shells.length;
		const running = shells.filter((s) => s.status === 'running').length;
		return { total, running, closed: total - running };
	});

	// Cross-filtered set: all active filters except status — drives the seg button counts
	const crossFiltered = $derived.by(() => {
		const q = query.trim().toLowerCase();
		return shells.filter((s) => {
			if (toolFilter !== 'all' && s.tool !== toolFilter) return false;
			if (projectFilter !== 'all' && s.project !== projectFilter) return false;
			if (q) {
				const hay = `${s.id} ${s.command} ${s.description ?? ''} ${s.project}`.toLowerCase();
				if (!hay.includes(q)) return false;
			}
			return true;
		});
	});

	// Counts shown in the seg buttons — reflect tool/project/search context
	const counts = $derived.by(() => {
		const total = crossFiltered.length;
		const running = crossFiltered.filter((s) => s.status === 'running').length;
		return { total, running, closed: total - running };
	});

	const filtered = $derived.by(() => {
		return crossFiltered.filter((s) => {
			if (statusFilter !== 'all' && s.status !== statusFilter) return false;
			return true;
		});
	});

	// Triage order: running shells pinned to the top, otherwise preserve incoming order.
	const triaged = $derived.by(() => {
		const running = filtered.filter((s) => s.status === 'running');
		const closed = filtered.filter((s) => s.status !== 'running');
		return [...running, ...closed];
	});

	function toggle(id: string) {
		const next = new Set(openIds);
		next.has(id) ? next.delete(id) : next.add(id);
		openIds = next;
	}

	function formatBytes(n: number): string {
		if (n < 1024) return `${n} B`;
		if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
		return `${(n / 1024 / 1024).toFixed(2)} MB`;
	}

	function formatDuration(ms: number): string {
		const s = Math.floor(ms / 1000);
		if (s < 60) return `${s}.${Math.floor((ms % 1000) / 100)}s`;
		const m = Math.floor(s / 60),
			rs = s % 60;
		if (m < 60) return `${m}m ${rs}s`;
		const h = Math.floor(m / 60),
			rm = m % 60;
		return `${h}h ${rm}m`;
	}

	function formatSpawned(iso: string): string {
		const d = new Date(iso);
		const now = new Date();
		const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
		if (d.toDateString() === now.toDateString()) return `Today at ${time}`;
		const yesterday = new Date(now);
		yesterday.setDate(now.getDate() - 1);
		if (d.toDateString() === yesterday.toDateString()) return `Yesterday at ${time}`;
		const sameYear = d.getFullYear() === now.getFullYear();
		const dateStr = d.toLocaleDateString([], { month: 'short', day: 'numeric', ...(sameYear ? {} : { year: 'numeric' }) });
		return `${dateStr} at ${time}`;
	}

	function statusLabel(s: Shell): string {
		if (s.status === 'running') return 'RUNNING';
		return (
			{
				kill: 'KILLED',
				natural: 'EXITED',
				timeout: 'TIMEOUT',
				session_end: 'SESSION ENDED'
			}[s.closeReason ?? 'session_end'] ?? 'CLOSED'
		);
	}

	function statusTone(s: Shell): string {
		if (s.status === 'running') return 'color: var(--success);';
		return (
			{
				kill: 'color: var(--error);',
				natural: 'color: var(--info);',
				timeout: 'color: var(--warning);',
				session_end: 'color: var(--text-faint);'
			}[s.closeReason ?? 'session_end'] ?? 'color: var(--text-faint);'
		);
	}

	function dotClass(s: Shell): string {
		if (s.status === 'running') return 'status-dot-running animate-pulse';
		return (
			{
				kill: 'status-dot-kill',
				natural: 'status-dot-natural',
				timeout: 'status-dot-timeout',
				session_end: 'status-dot-ended'
			}[s.closeReason ?? 'session_end'] ?? 'status-dot-ended'
		);
	}

	// Inline output sparkline: 8 decorative bars whose heights encode per-poll
	// output bytes. Purely visual (aria-hidden) — real numbers stay as text in
	// the Output column. Falls back to a flat low baseline when there's no data.
	function sparkBars(s: Shell): number[] {
		const SLOTS = 8;
		const vals = (s.polls ?? []).map((p) => p.bytes ?? 0);
		if (vals.length === 0) return Array(SLOTS).fill(8);
		// Take the most recent SLOTS polls (newest activity to the right).
		const recent = vals.slice(-SLOTS);
		const max = Math.max(...recent, 1);
		const bars = recent.map((v) => Math.max(8, Math.round((v / max) * 100)));
		// Left-pad shorter histories so bars stay right-aligned within the cell.
		while (bars.length < SLOTS) bars.unshift(8);
		return bars;
	}

	// Auto-refresh every 5s; track last refresh time for footer display
	import { onMount } from 'svelte';
	let lastRefresh = $state(new Date());
	let secondsAgo = $state(0);

	onMount(() => {
		const tick = setInterval(() => {
			secondsAgo = Math.round((Date.now() - lastRefresh.getTime()) / 1000);
		}, 1000);

		const refresh = setInterval(async () => {
			await invalidateAll();
			lastRefresh = new Date();
			secondsAgo = 0;
		}, 5000);

		return () => {
			clearInterval(tick);
			clearInterval(refresh);
		};
	});
</script>

<div class="mx-auto max-w-[1120px] px-8 pb-20 pt-8 text-[var(--text-primary)]">
	<!-- Page header -->
	<PageHeader
		title="Background Shells"
		subtitle="Every terminal Claude Code has spawned — what ran, what's still alive, what came back."
		iconName="shells"
		iconColor="--nav-green"
		breadcrumbs={[{ label: 'Home', href: '/' }, { label: 'Shells' }]}
	>
		{#snippet headerRight()}
			<button class="btn" onclick={() => invalidateAll()}>↻ Refresh</button>
		{/snippet}
	</PageHeader>

	<!-- Stat strip -->
	<div class="relative overflow-hidden rounded-2xl p-6 border border-[var(--border)] mb-6" style="background: linear-gradient(135deg, rgba(var(--success-rgb),0.02) 0%, rgba(var(--success-rgb),0.06) 100%);">
		<StatsGrid columns={3} stats={[
			{ title: 'Total spawned', value: globalCounts.total, icon: Terminal, color: 'purple' },
			{ title: 'Currently running', value: globalCounts.running, icon: Activity, color: 'green' },
			{ title: 'Closed', value: globalCounts.closed, icon: Box, color: 'gray' }
		]} />
	</div>

	<!-- Toolbar -->
	<div class="mb-3.5 flex flex-wrap items-center gap-2">
		<div class="seg">
			{#each [['all', 'All', counts.total], ['running', 'Running', counts.running], ['closed', 'Closed', counts.closed]] as [key, label, n] (key)}
				<button class:active={statusFilter === key} onclick={() => (statusFilter = key as any)}>
					{label}
					<span class="seg-count">{n}</span>
				</button>
			{/each}
		</div>

		<select bind:value={toolFilter} class="select">
			<option value="all">All tools</option>
			<option value="bash">Bash</option>
			<option value="monitor">Monitor</option>
			<option value="manual">Manual</option>
		</select>

		<select bind:value={projectFilter} class="select">
			<option value="all">All projects</option>
			{#each projects as p (p)}
				<option value={p}>{p}</option>
			{/each}
		</select>

		<label class="relative ml-auto min-w-[220px] flex-1">
			<span class="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-faint)]">⌕</span>
			<input
				bind:value={query}
				placeholder="Search shell id, command, project…"
				class="search-input"
			/>
		</label>
	</div>

	<!-- Section bar -->
	<div class="section-bar">
		<span class="flex items-center gap-2">
			<span class="text-[var(--accent)]">$</span>
			<span>shells --status={statusFilter} --tool={toolFilter}{projectFilter !== 'all' ? ` --project=${projectFilter}` : ''}</span>
		</span>
		<span class="text-[12.5px] text-[var(--text-secondary)]">
			showing <b class="text-[var(--text-primary)]">{filtered.length}</b> of
			<b class="text-[var(--text-primary)]">{globalCounts.total}</b>
		</span>
	</div>

	<!-- Triage table -->
	{#if triaged.length === 0}
		<div
			class="rounded-xl border border-dashed border-[var(--border)] bg-[var(--bg-subtle)] px-5 py-16 text-center text-[var(--text-secondary)]"
		>
			No shells match these filters.
		</div>
	{:else}
		<!-- Column headers -->
		<div class="sA-thead" aria-hidden="true">
			<span></span>
			<span>Shell · command</span>
			<span>Status</span>
			<span class="r">Output</span>
			<span class="r">Duration</span>
			<span></span>
		</div>

		<ul class="sA-table">
			{#each triaged as s (s.id)}
				{@const open = openIds.has(s.id)}
				<li class="sA-li {s.status === 'running' ? 'is-running' : 'is-dim'} {open ? 'is-open' : ''}">
					<!-- Triage row (click toggles expand) -->
					<div class="sA-row">
						<span class="size-2 rounded-full {dotClass(s)}" aria-hidden="true"></span>

						<!-- Main: id line + command -->
						<button
							type="button"
							class="sA-c-main"
							aria-expanded={open}
							onclick={() => toggle(s.id)}
						>
							<div class="sA-idline">
								<span class="sA-id">{s.id}</span>
								<span
									class="tag-badge {s.tool === 'bash'
										? 'tool-badge-bash'
										: s.tool === 'monitor'
											? 'tool-badge-monitor'
											: 'tool-badge-manual'}"
								>
									{s.tool}
								</span>
								{#if s.exitCode !== undefined}
									<span
										class="sA-exit"
										style={s.exitCode === 0 ? 'color: var(--success);' : 'color: var(--error);'}
									>
										exit {s.exitCode}
									</span>
								{/if}
								{#if s.description}
									<span class="sA-desc">· {s.description}</span>
								{/if}
							</div>
							<div class="sA-cmd"><span class="p">$</span>{s.command}</div>
						</button>

						<!-- Status: label + project -->
						<div class="sA-status">
							<span class="sl" style={statusTone(s)}>{statusLabel(s)}</span>
							<span class="ss">{s.project}</span>
						</div>

						<!-- Output sparkline (decorative) -->
						<div
							class="sA-spark {s.status === 'running' ? 'g' : ''}"
							aria-hidden="true"
							title={`${s.pollCount} polls · ${formatBytes(s.totalBytes)}`}
						>
							{#each sparkBars(s) as h, i (i)}
								<i style={`height:${h}%`}></i>
							{/each}
						</div>

						<!-- Metric: duration + polls/bytes -->
						<div class="sA-metric">
							<div class="mv tnum">{formatDuration(s.durationMs)}</div>
							<div class="ml">
								{#if s.status === 'running'}
									{s.pollCount} polls
								{:else}
									{formatBytes(s.totalBytes)}
								{/if}
							</div>
						</div>

						<!-- Trailing: inline kill (running) or expand caret -->
						<div class="sA-caret">
							{#if s.status === 'running'}
								<button
									type="button"
									disabled={killing.has(s.toolUseId)}
									onclick={() => killShell(s.toolUseId)}
									class="sA-kill disabled:opacity-50"
								>
									{#if killing.has(s.toolUseId)}
										<svg class="kill-spinner mr-1" xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
											<path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
										</svg>
										Killing…
									{:else}
										Kill
									{/if}
								</button>
							{:else}
								<button
									type="button"
									class="caret-btn {open ? 'rotate-90 text-[var(--text-primary)]' : ''}"
									aria-label={open ? 'Collapse shell details' : 'Expand shell details'}
									aria-expanded={open}
									onclick={() => toggle(s.id)}
								>
									<svg class="ic" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
								</button>
							{/if}
						</div>
					</div>

					{#if open}
						<div class="sA-detail">

							<!-- Command block -->
							<div class="flex items-start gap-2 rounded-[10px] border border-[var(--border)] bg-[var(--bg-subtle)] px-3.5 py-2.5 font-mono text-[12.5px]">
								<span class="shrink-0 font-semibold text-[var(--accent)]">$</span>
								<span class="min-w-0 flex-1 whitespace-pre-wrap break-all text-[var(--text-primary)]">{s.command}</span>
								<button
									type="button"
									title="Copy command"
									onclick={() => copyCommand(s.id, s.command)}
									class="shrink-0 text-[var(--text-faint)] transition hover:text-[var(--text-primary)]"
								>
									{#if copiedIds.has(s.id)}
										<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="color: var(--success);"><polyline points="20 6 9 17 4 12"/></svg>
									{:else}
										<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>
									{/if}
								</button>
							</div>

							<!-- Session link -->
							<div class="flex items-baseline gap-1.5">
								<span class="kv-label">Session</span>
								{#if s.sessionUrl}
									<a href={s.sessionUrl} class="font-mono text-[12.5px] text-[var(--accent)] hover:underline">{s.session}</a>
								{:else}
									<span class="font-mono text-[12.5px] text-[var(--accent)]">{s.session}</span>
								{/if}
							</div>

							<!-- Output polls -->
							{#if s.polls.length > 0}
								<div>
									<div class="mb-2 flex items-center justify-between">
										<span class="kv-label">Output polls · {s.polls.length} shown</span>
										<span class="kv-label">via BashOutput</span>
									</div>
									{#each s.polls as poll, i (i)}
										{@const pollKey = s.id + ':' + i}
										<div class="mb-1.5 rounded-lg border border-[var(--border)] bg-[var(--bg-muted)] px-3 py-2.5">
											<div class="mb-1.5 flex items-center justify-between">
												<span class="font-mono text-[11px] text-[var(--text-faint)]">{formatSpawned(poll.ts)}</span>
												<div class="flex items-center gap-2">
													<span class="font-mono text-[10.5px] text-[var(--text-faint)]">{formatBytes(poll.bytes)}</span>
													<button
														type="button"
														title="Copy output"
														onclick={() => copyCommand(pollKey, poll.text)}
														class="text-[var(--text-faint)] transition hover:text-[var(--text-primary)]"
													>
														{#if copiedIds.has(pollKey)}
															<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="color: var(--success);"><polyline points="20 6 9 17 4 12"/></svg>
														{:else}
															<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>
														{/if}
													</button>
												</div>
											</div>
											<pre class="poll-pre m-0 max-h-48 overflow-auto whitespace-pre-wrap break-words font-mono text-[12px] leading-6 text-[var(--text-primary)]">{poll.text}</pre>
										</div>
									{/each}
								</div>
							{/if}

						</div>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}

	<p class="mt-4 flex items-center gap-2 text-xs text-[var(--text-faint)]">
		<kbd
			class="rounded border border-[var(--border)] border-b-2 bg-[var(--bg-muted)] px-1.5 py-px font-mono text-[11px] text-[var(--text-primary)]"
			>↵</kbd
		>
		<span>Click any row to expand poll history</span>
		<span class="ml-auto">Updated {secondsAgo === 0 ? 'just now' : `${secondsAgo}s ago`}</span>
	</p>
</div>

<style>
	/* ── Status dot variants ────────────────────────────────────────────────── */
	.status-dot-running { background: var(--success); box-shadow: 0 0 0 4px rgba(var(--success-rgb), 0.15); }
	.status-dot-kill    { background: var(--error); }
	.status-dot-natural { background: var(--info); }
	.status-dot-timeout { background: var(--warning); }
	.status-dot-ended   { background: var(--text-faint); }

	/* ── Tool badges ─────────────────────────────────────────────────────────── */
	.tag-badge {
		display: inline-flex;
		align-items: center;
		gap: 4px;
		font-size: 10px;
		font-weight: 700;
		letter-spacing: 0.06em;
		text-transform: uppercase;
		padding: 2px 7px;
		border-radius: 5px;
		font-family: var(--font-mono);
	}
	.tool-badge-bash    { background: var(--accent-muted); color: var(--accent); }
	.tool-badge-monitor { background: var(--info-subtle);  color: var(--info); }
	.tool-badge-manual  { background: var(--warning-subtle); color: var(--warning); }

	/* ── Triage table ────────────────────────────────────────────────────────── */
	.sA-thead {
		display: grid;
		grid-template-columns: 16px minmax(0, 1fr) 130px 96px 96px 78px;
		align-items: center;
		gap: 14px;
		padding: 0 16px 8px;
	}
	.sA-thead span {
		font-size: 10px;
		font-weight: 700;
		letter-spacing: 0.07em;
		text-transform: uppercase;
		color: var(--text-faint);
	}
	.sA-thead .r { text-align: right; }

	.sA-table {
		border: 1px solid var(--border);
		border-radius: 12px;
		overflow: hidden;
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.sA-li {
		border-bottom: 1px solid var(--border-subtle);
		transition: background 120ms ease;
	}
	.sA-li:last-child { border-bottom: none; }
	.sA-li.is-running { background: linear-gradient(90deg, rgba(var(--success-rgb), 0.045), transparent 60%); }
	.sA-li.is-dim { background: var(--bg-subtle); }
	.sA-li:hover { background: var(--bg-muted); }
	.sA-li.is-running:hover { background: linear-gradient(90deg, rgba(var(--success-rgb), 0.075), transparent 60%); }
	.sA-li.is-open { background: var(--bg-base); }

	.sA-row {
		display: grid;
		grid-template-columns: 16px minmax(0, 1fr) 130px 96px 96px 78px;
		align-items: center;
		gap: 14px;
		padding: 12px 16px;
	}

	.sA-c-main {
		min-width: 0;
		text-align: left;
		background: transparent;
		border: 0;
		padding: 0;
		cursor: pointer;
	}
	.sA-idline { display: flex; align-items: center; gap: 8px; margin-bottom: 3px; flex-wrap: wrap; }
	.sA-id { font-family: var(--font-mono); font-size: 12px; font-weight: 600; color: var(--accent); }
	.sA-exit { font-family: var(--font-mono); font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; }
	.sA-desc { font-size: 11px; color: var(--text-muted); }
	.sA-cmd {
		font-family: var(--font-mono);
		font-size: 12px;
		color: var(--text-secondary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.sA-cmd .p { color: var(--accent); font-weight: 700; margin-right: 6px; }

	.sA-status { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
	.sA-status .sl {
		font-size: 11px;
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.04em;
		display: inline-flex;
		align-items: center;
		gap: 6px;
	}
	.sA-status .ss {
		font-family: var(--font-mono);
		font-size: 10.5px;
		color: var(--text-faint);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	/* ── Output sparkline (decorative) ───────────────────────────────────────── */
	.sA-spark { display: flex; align-items: flex-end; justify-content: flex-end; gap: 2px; height: 22px; }
	.sA-spark > i {
		width: 3px;
		background: color-mix(in srgb, var(--accent) 55%, transparent);
		border-radius: 2px;
	}
	.sA-spark.g > i { background: color-mix(in srgb, var(--success) 60%, transparent); }

	.sA-metric { text-align: right; }
	.sA-metric .mv { font-family: var(--font-mono); font-size: 12.5px; font-weight: 600; color: var(--text-primary); }
	.sA-metric .ml { font-size: 10px; color: var(--text-faint); text-transform: uppercase; letter-spacing: 0.04em; margin-top: 2px; }
	.tnum { font-variant-numeric: tabular-nums; }

	.sA-caret { display: flex; justify-content: flex-end; align-items: center; }
	.caret-btn {
		color: var(--text-faint);
		background: transparent;
		border: 0;
		cursor: pointer;
		display: inline-flex;
		transition: transform 140ms ease, color 120ms ease;
	}
	.caret-btn:hover { color: var(--text-primary); }

	/* ── Inline kill ─────────────────────────────────────────────────────────── */
	.sA-kill {
		display: inline-flex;
		align-items: center;
		height: 24px;
		padding: 0 9px;
		border-radius: 6px;
		font-size: 11.5px;
		font-weight: 600;
		color: var(--error);
		background: var(--error-subtle);
		border: 1px solid rgba(var(--error-rgb), 0.3);
		cursor: pointer;
		white-space: nowrap;
		transition: background 120ms ease, border-color 120ms ease, transform 100ms ease;
	}
	.sA-kill:hover:not(:disabled) {
		background: rgba(var(--error-rgb), 0.18);
		border-color: rgba(var(--error-rgb), 0.5);
		transform: scale(1.03);
	}
	.sA-kill:active:not(:disabled) { transform: scale(0.97); }
	@keyframes spin {
		to { transform: rotate(360deg); }
	}
	.kill-spinner {
		animation: spin 0.8s linear infinite;
		color: var(--error);
	}

	/* ── Expanded detail ─────────────────────────────────────────────────────── */
	.sA-detail {
		border-top: 1px dashed var(--border);
		padding: 16px 16px 18px;
		display: flex;
		flex-direction: column;
		gap: 12px;
	}

	/* ── Search input ────────────────────────────────────────────────────────── */
	.search-input {
		height: 34px;
		width: 100%;
		border-radius: 0.5rem;
		border: 1px solid var(--border-hover);
		background: var(--bg-base);
		padding: 0 0.75rem 0 2rem;
		font-size: 13px;
		color: var(--text-primary);
		outline: none;
	}
	.search-input:focus {
		border-color: var(--accent);
		box-shadow: 0 0 0 2px var(--accent-muted);
	}
	.search-input::placeholder {
		color: var(--text-faint);
	}

	/* ── Section bar ─────────────────────────────────────────────────────────── */
	.section-bar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		border-radius: 10px;
		border: 1px solid var(--border);
		background: var(--bg-muted);
		padding: 10px 14px;
		font-family: var(--font-mono);
		font-size: 13px;
		color: var(--text-primary);
		margin-bottom: 12px;
	}

	/* ── Refresh button ──────────────────────────────────────────────────────── */
	.btn {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		height: 34px;
		padding: 0 0.75rem;
		border-radius: 0.5rem;
		border: 1px solid var(--border-hover);
		background: var(--bg-base);
		font-size: 13px;
		font-weight: 500;
		color: var(--text-primary);
		cursor: pointer;
	}
	.btn:hover {
		background: var(--bg-subtle);
	}

	/* ── Segmented control ───────────────────────────────────────────────────── */
	.seg {
		display: inline-flex;
		background: var(--bg-muted);
		border: 1px solid var(--border);
		border-radius: 0.5rem;
		padding: 3px;
	}
	.seg button {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		padding: 6px 12px;
		border-radius: 0.375rem;
		font-size: 12.5px;
		font-weight: 500;
		color: var(--text-secondary);
		background: transparent;
		border: 0;
		cursor: pointer;
	}
	.seg button.active {
		background: var(--bg-base);
		color: var(--text-primary);
		box-shadow: 0 1px 2px var(--border-subtle);
	}
	.seg-count {
		font-family: 'JetBrains Mono', ui-monospace, monospace;
		font-size: 11px;
		padding: 1px 6px;
		border-radius: 9999px;
		background: var(--border-subtle);
		color: var(--text-secondary);
	}
	.seg button.active .seg-count {
		background: var(--accent-subtle);
		color: var(--accent);
	}

	/* ── Select ──────────────────────────────────────────────────────────────── */
	.select {
		height: 32px;
		padding: 0 0.625rem 0 0.75rem;
		border: 1px solid var(--border-hover);
		background: var(--bg-base);
		border-radius: 0.5rem;
		font-size: 13px;
		color: var(--text-primary);
		cursor: pointer;
	}

	/* ── KV label ────────────────────────────────────────────────────────────── */
	.kv-label {
		font-size: 10.5px;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--text-faint);
		font-weight: 600;
	}

	/* ── Poll output scrollbar ───────────────────────────────────────────────── */
	.poll-pre {
		scrollbar-width: thin;
		scrollbar-color: var(--border) transparent;
	}
	.poll-pre::-webkit-scrollbar {
		width: 3px;
		height: 3px;
	}
	.poll-pre::-webkit-scrollbar-track {
		background: transparent;
	}
	.poll-pre::-webkit-scrollbar-thumb {
		background: var(--border);
		border-radius: 99px;
	}
	.poll-pre::-webkit-scrollbar-thumb:hover {
		background: var(--border-hover);
	}

	/* ── Reduced motion ──────────────────────────────────────────────────────── */
	@media (prefers-reduced-motion: reduce) {
		.kill-spinner { animation: none; }
		.caret-btn,
		.sA-kill,
		.sA-li { transition: none; }
	}
</style>
