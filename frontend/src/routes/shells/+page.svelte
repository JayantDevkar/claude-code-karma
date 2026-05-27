<script lang="ts">
	import { invalidateAll } from '$app/navigation';
	import type { BackgroundShell } from '$lib/api-types';

	type Tool = 'bash' | 'monitor';
	type Status = 'running' | 'closed';
	type CloseReason = 'kill' | 'natural' | 'timeout' | 'session_end';

	type Poll = {
		ts: string;
		bytes: number;
		text: string;
	};

	type Shell = {
		id: string;
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
				(s as any).project_encoded_name && (s as any).session_slug
					? `/projects/${(s as any).project_encoded_name}/${(s as any).session_slug}`
					: undefined,
			polls: (s.polls ?? []).map((p) => ({
				ts: p.polled_at,
				bytes: p.output_bytes,
				text: p.output_excerpt ?? ''
			}))
		};
	}

	const shells = $derived((data.shells as BackgroundShell[]).map(toShell));

	// ---- filters ----
	let statusFilter = $state<'all' | Status>('all');
	let toolFilter = $state<'all' | Tool>('all');
	let projectFilter = $state<string>('all');
	let query = $state('');
	let openIds = $state<Set<string>>(new Set());

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
		const t = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
		const today = new Date();
		const same = d.toDateString() === today.toDateString();
		return same ? `Today, ${t}` : d.toLocaleString();
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
</script>

<div class="mx-auto max-w-[1120px] px-8 pb-20 pt-8 text-stone-900">
	<!-- Page header -->
	<header class="mb-7 flex items-start justify-between gap-6">
		<div>
			<div class="mb-3 flex items-center gap-1.5 font-mono text-xs text-stone-400">
				<a href="/" class="text-stone-500 hover:text-stone-900">Home</a>
				<span>/</span>
				<span>Shells</span>
			</div>
			<h1 class="mb-1.5 text-[32px] font-bold tracking-tight">Background Shells</h1>
			<p class="text-sm text-violet-500">
				Every terminal Claude Code has spawned — what ran, what's still alive, what came back.
			</p>
		</div>
		<button class="btn" onclick={() => invalidateAll()}>↻ Refresh</button>
	</header>

	<!-- Stat strip -->
	<section class="mb-6 grid grid-cols-3 gap-3">
		<div class="stat-card">
			<div class="stat-ico bg-violet-100 text-violet-700">Σ</div>
			<div>
				<div class="stat-num">{globalCounts.total}</div>
				<div class="stat-label">Total spawned</div>
			</div>
		</div>
		<div class="stat-card">
			<div class="stat-ico bg-emerald-100 text-emerald-700">⌁</div>
			<div>
				<div class="stat-num">
					{globalCounts.running}
					{#if globalCounts.running > 0}
						<span
							class="ml-2 inline-block size-1.5 -translate-y-1 rounded-full bg-emerald-500 ring-4 ring-emerald-500/30 animate-pulse"
						></span>
					{/if}
				</div>
				<div class="stat-label">Currently running</div>
			</div>
		</div>
		<div class="stat-card">
			<div class="stat-ico bg-stone-100 text-stone-600">▢</div>
			<div>
				<div class="stat-num">{globalCounts.closed}</div>
				<div class="stat-label">Closed</div>
			</div>
		</div>
	</section>

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
					class="rounded-xl border bg-white transition
                 {open
						? 'border-stone-300 shadow-[0_1px_0_rgba(0,0,0,.03),0_6px_20px_-8px_rgba(0,0,0,.08)]'
						: 'border-stone-200 hover:border-stone-300'}"
				>
					<button
						type="button"
						class="grid w-full grid-cols-[18px_14px_1fr_auto] items-center gap-3.5 px-4 py-3.5 text-left"
						onclick={() => toggle(s.id)}
					>
						<span class="text-stone-400 transition {open ? 'rotate-90 text-stone-900' : ''}"
							>›</span
						>
						<span class="size-2 rounded-full {dotClass(s)}"></span>

						<div class="min-w-0 space-y-1">
							<div class="flex flex-wrap items-center gap-2.5">
								<span class="font-mono text-[12.5px] font-semibold text-violet-700">{s.id}</span>
								<span
									class="rounded px-1.5 py-0.5 text-[10.5px] font-semibold uppercase tracking-wider
                             {s.tool === 'bash'
										? 'bg-violet-100 text-violet-700'
										: 'bg-blue-100 text-blue-600'}"
								>
									{s.tool}
								</span>
								<span class="text-[10.5px] font-semibold uppercase tracking-wider {statusTone(s)}">
									{statusLabel(s)}
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
							<div class="truncate font-mono text-[12.5px] text-stone-500">
								<span class="mr-1.5 text-violet-500">$</span>{s.command}
							</div>
						</div>

						<div class="flex flex-col items-end gap-0.5 text-right">
							<span class="font-mono text-[13px] font-medium">{formatDuration(s.durationMs)}</span>
							<span class="font-mono text-[11.5px] text-stone-400">
								{s.pollCount} polls · {formatBytes(s.totalBytes)}
							</span>
						</div>
					</button>

					{#if open}
						<div
							class="grid grid-cols-[240px_1fr] gap-6 border-t border-dashed border-stone-200 px-4.5 pb-4.5 pt-4"
						>
							<dl class="space-y-2.5">
								<div>
									<dt class="kv-label">Shell ID</dt>
									<dd class="font-mono text-[12.5px] text-violet-700">{s.id}</dd>
								</div>
								<div>
									<dt class="kv-label">Spawned</dt>
									<dd class="font-mono text-[12.5px]">{formatSpawned(s.spawnedAt)}</dd>
								</div>
								<div>
									<dt class="kv-label">Duration</dt>
									<dd class="font-mono text-[12.5px]">
										{formatDuration(s.durationMs)}{s.status === 'running' ? ' · ongoing' : ''}
									</dd>
								</div>
								<div>
									<dt class="kv-label">Project</dt>
									<dd class="font-mono text-[12.5px]">{s.project}</dd>
								</div>
								<div>
									<dt class="kv-label">Session</dt>
									<dd class="font-mono text-[12.5px] text-violet-700">
										{#if s.sessionUrl}
											<a href={s.sessionUrl} class="hover:underline">{s.session}</a>
										{:else}
											{s.session}
										{/if}
									</dd>
								</div>
								<div>
									<dt class="kv-label">Output</dt>
									<dd class="font-mono text-[12.5px]">
										{formatBytes(s.totalBytes)} across {s.pollCount} polls
									</dd>
								</div>
								{#if s.status === 'running'}
									<button class="btn mt-1.5 w-full justify-center">▢ Kill shell</button>
								{/if}
							</dl>

							<div class="min-w-0">
								<div class="mb-2 flex items-center justify-between">
									<h4 class="kv-label">Output polls · {s.polls.length} shown</h4>
									<span class="kv-label">via BashOutput</span>
								</div>
								{#each s.polls as poll, i (i)}
									<div class="mb-1.5 rounded-lg border border-stone-200 bg-stone-100 px-3 py-2.5">
										<div class="mb-1.5 flex items-center justify-between">
											<span class="font-mono text-[11.5px] text-stone-500">
												<b class="font-medium text-stone-900">{poll.ts}</b>
											</span>
											<span
												class="rounded border border-stone-200 bg-white px-1.5 py-0.5 font-mono text-[11px] text-stone-500"
											>
												{formatBytes(poll.bytes)}
											</span>
										</div>
										<pre
											class="m-0 max-h-28 overflow-auto whitespace-pre-wrap break-words font-mono text-[12px] leading-6 text-stone-800">{poll.text}</pre>
									</div>
								{/each}
							</div>
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
		<span class="ml-auto">Updated 2s ago</span>
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
	.stat-card {
		display: flex;
		align-items: center;
		gap: 0.875rem;
		padding: 1rem 1.125rem;
		border: 1px solid #e7e5e4;
		background: #fff;
		border-radius: 0.75rem;
	}
	.stat-ico {
		width: 36px;
		height: 36px;
		display: flex;
		align-items: center;
		justify-content: center;
		border-radius: 0.5rem;
		font-family: 'JetBrains Mono', ui-monospace, monospace;
		font-weight: 600;
	}
	.stat-num {
		font-size: 26px;
		font-weight: 600;
		letter-spacing: -0.02em;
		line-height: 1;
	}
	.stat-label {
		font-size: 12px;
		color: #57534e;
		margin-top: 4px;
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
</style>
