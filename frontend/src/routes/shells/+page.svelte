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
		if (s.status === 'running') return 'text-emerald-600';
		return (
			{
				kill: 'text-red-600',
				natural: 'text-blue-600',
				timeout: 'text-amber-600',
				session_end: 'text-stone-400'
			}[s.closeReason ?? 'session_end'] ?? 'text-stone-400'
		);
	}

	function dotClass(s: Shell): string {
		if (s.status === 'running') return 'bg-emerald-500 ring-4 ring-emerald-500/15 animate-pulse';
		return (
			{
				kill: 'bg-red-500',
				natural: 'bg-blue-500',
				timeout: 'bg-amber-500',
				session_end: 'bg-stone-400'
			}[s.closeReason ?? 'session_end'] ?? 'bg-stone-400'
		);
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

<div class="mx-auto max-w-[1120px] px-8 pb-20 pt-8 text-stone-900">
	<!-- Page header -->
	<PageHeader
		title="Background Shells"
		subtitle="Every terminal Claude Code has spawned — what ran, what's still alive, what came back."
		icon={Terminal}
		iconColor="--nav-green"
		breadcrumbs={[{ label: 'Home', href: '/' }, { label: 'Shells' }]}
	>
		{#snippet headerRight()}
			<button class="btn" onclick={() => invalidateAll()}>↻ Refresh</button>
		{/snippet}
	</PageHeader>

	<!-- Stat strip -->
	<div class="relative overflow-hidden rounded-2xl p-6 border border-[var(--border)] mb-6" style="background: linear-gradient(135deg, rgba(16,185,129,0.02) 0%, rgba(16,185,129,0.06) 100%);">
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
			<span class="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400">⌕</span>
			<input
				bind:value={query}
				placeholder="Search shell id, command, project…"
				class="h-[34px] w-full rounded-lg border border-stone-300 bg-white px-3 pl-8 text-[13px] outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100"
			/>
		</label>
	</div>

	<!-- Section bar -->
	<div
		class="mb-3 flex items-center justify-between rounded-[10px] border border-stone-200 bg-stone-100 px-3.5 py-2.5 font-mono text-[13px]"
	>
		<span class="flex items-center gap-2">
			<span class="text-violet-500">$</span>
			<span>shells --status={statusFilter} --tool={toolFilter}{projectFilter !== 'all' ? ` --project=${projectFilter}` : ''}</span>
		</span>
		<span class="text-[12.5px] text-stone-500">
			showing <b class="text-stone-900">{filtered.length}</b> of
			<b class="text-stone-900">{globalCounts.total}</b>
		</span>
	</div>

	<!-- Shell list -->
	{#if filtered.length === 0}
		<div
			class="rounded-xl border border-dashed border-stone-200 bg-stone-50 px-5 py-16 text-center text-stone-500"
		>
			No shells match these filters.
		</div>
	{:else}
		<ul class="flex flex-col gap-2">
			{#each filtered as s (s.id)}
				{@const open = openIds.has(s.id)}
				<li
					class="group rounded-xl border bg-white transition
                 {open
						? 'border-stone-300 shadow-[0_1px_0_rgba(0,0,0,.03),0_6px_20px_-8px_rgba(0,0,0,.08)]'
						: 'border-stone-200 hover:border-stone-300'}"
				>
					<div class="grid w-full grid-cols-[14px_1fr_auto_18px] items-center gap-3.5 px-4 py-3.5">
						<span class="size-2 rounded-full {dotClass(s)}"></span>

						<button
							type="button"
							class="min-w-0 space-y-0.5 text-left"
							onclick={() => toggle(s.id)}
						>
							<div class="flex flex-wrap items-center gap-2.5">
								<span class="font-mono text-[12.5px] font-semibold text-violet-700">{s.id}</span>
								<span
									class="rounded px-1.5 py-0.5 text-[10.5px] font-semibold uppercase tracking-wider
                             {s.tool === 'bash'
										? 'bg-violet-100 text-violet-700'
										: s.tool === 'monitor'
											? 'bg-blue-100 text-blue-600'
											: 'bg-amber-100 text-amber-700'}"
								>
									{s.tool}
								</span>
								{#if s.exitCode !== undefined}
									<span
										class="font-mono text-[10.5px] font-semibold uppercase tracking-wider
                               {s.exitCode === 0 ? 'text-emerald-600' : 'text-red-600'}"
									>
										exit {s.exitCode}
									</span>
								{/if}
								{#if s.description}
									<span class="text-[13px] font-medium text-stone-900">· {s.description}</span>
								{/if}
							</div>
							<div class="font-mono text-[11.5px] text-stone-400">{s.project} · {formatSpawned(s.spawnedAt)}</div>
						</button>

						<div class="flex items-center gap-2.5">
							{#if s.status === 'running'}
								<div class="kill-wrap w-0 overflow-hidden group-hover:w-[90px]">
									<div class="flex justify-end pr-2">
										<button
											type="button"
											disabled={killing.has(s.toolUseId)}
											onclick={() => killShell(s.toolUseId)}
											class="kill-pill whitespace-nowrap disabled:opacity-50"
										>
											{#if killing.has(s.toolUseId)}
												<svg class="kill-spinner mr-1" xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
													<path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
												</svg>
												Killing…
											{:else}
												Kill shell
											{/if}
										</button>
									</div>
								</div>
							{/if}
							<div class="flex flex-col items-end gap-0.5 text-right">
								<span class="font-mono text-[13px] font-medium">{formatDuration(s.durationMs)}</span>
								<span class="font-mono text-[11.5px] text-stone-400">{s.pollCount} polls</span>
							</div>
						</div>

						<button
							type="button"
							class="text-stone-400 transition {open ? 'rotate-90 text-stone-900' : ''}"
							onclick={() => toggle(s.id)}
						>›</button>
					</div>

					{#if open}
						<div class="border-t border-dashed border-stone-200 px-4.5 pb-4.5 pt-4 space-y-3">

							<!-- Command block -->
							<div class="flex items-start gap-2 rounded-[10px] border border-[var(--border)] bg-[var(--bg-subtle)] px-3.5 py-2.5 font-mono text-[12.5px]">
								<span class="shrink-0 font-semibold text-[var(--accent)]">$</span>
								<span class="min-w-0 flex-1 whitespace-pre-wrap break-all text-[var(--text-primary)]">{s.command}</span>
								<button
									type="button"
									title="Copy command"
									onclick={() => copyCommand(s.id, s.command)}
									class="shrink-0 text-stone-400 transition hover:text-stone-700"
								>
									{#if copiedIds.has(s.id)}
										<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="text-emerald-500"><polyline points="20 6 9 17 4 12"/></svg>
									{:else}
										<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>
									{/if}
								</button>
							</div>

							<!-- Session link -->
							<div class="flex items-baseline gap-1.5">
								<span class="kv-label">Session</span>
								{#if s.sessionUrl}
									<a href={s.sessionUrl} class="font-mono text-[12.5px] text-violet-700 hover:underline">{s.session}</a>
								{:else}
									<span class="font-mono text-[12.5px] text-violet-700">{s.session}</span>
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
										<div class="mb-1.5 rounded-lg border border-stone-200 bg-stone-100 px-3 py-2.5">
											<div class="mb-1.5 flex items-center justify-between">
												<span class="font-mono text-[11px] text-stone-400">{formatSpawned(poll.ts)}</span>
												<div class="flex items-center gap-2">
													<span class="font-mono text-[10.5px] text-stone-400">{formatBytes(poll.bytes)}</span>
													<button
														type="button"
														title="Copy output"
														onclick={() => copyCommand(pollKey, poll.text)}
														class="text-stone-400 transition hover:text-stone-700"
													>
														{#if copiedIds.has(pollKey)}
															<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="text-emerald-500"><polyline points="20 6 9 17 4 12"/></svg>
														{:else}
															<svg xmlns="http://www.w3.org/2000/svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/></svg>
														{/if}
													</button>
												</div>
											</div>
											<pre class="poll-pre m-0 max-h-48 overflow-auto whitespace-pre-wrap break-words font-mono text-[12px] leading-6 text-stone-800">{poll.text}</pre>
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

	<p class="mt-4 flex items-center gap-2 text-xs text-stone-400">
		<kbd
			class="rounded border border-stone-200 border-b-2 bg-stone-100 px-1.5 py-px font-mono text-[11px] text-stone-900"
			>↵</kbd
		>
		<span>Click any row to expand poll history</span>
		<span class="ml-auto">Updated {secondsAgo === 0 ? 'just now' : `${secondsAgo}s ago`}</span>
	</p>
</div>

<style>
	.btn {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		height: 34px;
		padding: 0 0.75rem;
		border-radius: 0.5rem;
		border: 1px solid #d6d3d1;
		background: #fff;
		font-size: 13px;
		font-weight: 500;
		color: #0c0a09;
		cursor: pointer;
	}
	.btn:hover {
		background: #fafaf9;
	}
	.seg {
		display: inline-flex;
		background: #f5f5f4;
		border: 1px solid #e7e5e4;
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
		color: #57534e;
		background: transparent;
		border: 0;
		cursor: pointer;
	}
	.seg button.active {
		background: #fff;
		color: #0c0a09;
		box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
	}
	.seg-count {
		font-family: 'JetBrains Mono', ui-monospace, monospace;
		font-size: 11px;
		padding: 1px 6px;
		border-radius: 9999px;
		background: rgba(0, 0, 0, 0.05);
		color: #57534e;
	}
	.seg button.active .seg-count {
		background: #f3eefe;
		color: #6d28d9;
	}
	.select {
		height: 32px;
		padding: 0 0.625rem 0 0.75rem;
		border: 1px solid #d6d3d1;
		background: #fff;
		border-radius: 0.5rem;
		font-size: 13px;
		color: #0c0a09;
		cursor: pointer;
	}
	.kv-label {
		font-size: 10.5px;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: #a8a29e;
		font-weight: 600;
	}

	.kill-wrap {
		transition: width 180ms cubic-bezier(0.4, 0, 0.2, 1);
		flex-shrink: 0;
	}
	.kill-pill {
		display: inline-flex;
		align-items: center;
		height: 24px;
		padding: 0 10px;
		border-radius: 6px;
		font-size: 12.5px;
		font-weight: 500;
		color: #dc2626;
		background: #fef2f2;
		border: 1px solid #fecaca;
		transition: background 120ms ease, border-color 120ms ease, color 120ms ease, transform 100ms ease;
		cursor: pointer;
	}
	.kill-pill:hover {
		background: #fee2e2;
		border-color: #f87171;
		color: #b91c1c;
		transform: scale(1.03);
	}
	.kill-pill:active {
		transform: scale(0.97);
	}
	@keyframes spin {
		to { transform: rotate(360deg); }
	}
	.kill-spinner {
		animation: spin 0.8s linear infinite;
		color: #ef4444;
	}

	.poll-pre {
		scrollbar-width: thin;
		scrollbar-color: rgba(0, 0, 0, 0.12) transparent;
	}
	.poll-pre::-webkit-scrollbar {
		width: 3px;
		height: 3px;
	}
	.poll-pre::-webkit-scrollbar-track {
		background: transparent;
	}
	.poll-pre::-webkit-scrollbar-thumb {
		background: rgba(0, 0, 0, 0.12);
		border-radius: 99px;
	}
	.poll-pre::-webkit-scrollbar-thumb:hover {
		background: rgba(0, 0, 0, 0.28);
	}
</style>
