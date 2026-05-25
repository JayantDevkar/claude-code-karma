<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import type {
		BackgroundShell,
		ShellStatusFilter,
		ShellToolName,
		ShellsProjectRollupRow
	} from '$lib/api-types';
	import { Terminal, CircleDot, X, Play, Square, ChevronDown } from 'lucide-svelte';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';

	let { data } = $props();

	// ── Filter state (mirrors URL) ────────────────────────────────────────
	let filterProject = $state(data.filters.project);
	let filterStatus = $state<ShellStatusFilter | ''>(
		(data.filters.status as ShellStatusFilter | '') ?? ''
	);
	let filterTool = $state<ShellToolName | ''>(
		(data.filters.tool as ShellToolName | '') ?? ''
	);

	// ── Selected row ─────────────────────────────────────────────────────
	let selectedShellId = $state<string | null>(null);

	function navigate(opts: { project?: string; status?: string; tool?: string }) {
		const params = new URLSearchParams($page.url.searchParams);
		for (const [k, v] of Object.entries(opts)) {
			if (v) params.set(k, v);
			else params.delete(k);
		}
		goto(`/shells?${params.toString()}`);
	}

	function clearProject() {
		filterProject = '';
		navigate({ project: '' });
	}

	// ── Derived counts ────────────────────────────────────────────────────
	let shells = $derived(data.shells as BackgroundShell[]);

	let stats = $derived({
		spawned: shells.length,
		running: shells.filter((s) => s.terminated_at === null).length,
		closed: shells.filter((s) => s.terminated_at !== null).length
	});

	// ── Timeline helpers ──────────────────────────────────────────────────
	/**
	 * Compute a wall-clock timeline anchor: the earliest spawned_at across
	 * all loaded shells. Each shell gets a left-offset % on a shared axis.
	 */
	let timelineRange = $derived(() => {
		if (shells.length === 0) return { minMs: 0, spanMs: 1 };
		const times = shells.map((s) => new Date(s.spawned_at).getTime());
		const ends = shells.map((s) =>
			s.terminated_at ? new Date(s.terminated_at).getTime() : Date.now()
		);
		const minMs = Math.min(...times);
		const maxMs = Math.max(...ends);
		return { minMs, spanMs: Math.max(maxMs - minMs, 60_000) }; // at least 1 min
	});

	function pct(ts: string): number {
		const { minMs, spanMs } = timelineRange();
		return ((new Date(ts).getTime() - minMs) / spanMs) * 100;
	}

	function pctNow(): number {
		const { minMs, spanMs } = timelineRange();
		return ((Date.now() - minMs) / spanMs) * 100;
	}

	function durationLabel(shell: BackgroundShell): string {
		const start = new Date(shell.spawned_at).getTime();
		const end = shell.terminated_at ? new Date(shell.terminated_at).getTime() : Date.now();
		const secs = Math.round((end - start) / 1000);
		if (secs < 60) return `${secs}s`;
		const mins = Math.round(secs / 60);
		if (mins < 60) return `${mins}m`;
		return `${Math.round(mins / 60)}h ${mins % 60}m`;
	}

	function formatBytes(bytes: number): string {
		if (bytes < 1024) return `${bytes}B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)}MB`;
	}

	function truncateCmd(cmd: string, maxLen = 64): string {
		return cmd.length > maxLen ? cmd.slice(0, maxLen) + '…' : cmd;
	}

	function shellKey(shell: BackgroundShell): string {
		return shell.shell_id ?? shell.tool_use_id.slice(-8);
	}

	function isSelected(shell: BackgroundShell): boolean {
		return selectedShellId === shellKey(shell);
	}

	function toggleSelect(shell: BackgroundShell) {
		const key = shellKey(shell);
		selectedShellId = selectedShellId === key ? null : key;
	}

	let selectedShell = $derived(
		shells.find((s) => shellKey(s) === selectedShellId) ?? null
	);

	// ── Project rollup ────────────────────────────────────────────────────
	let rollup = $derived(data.rollup as ShellsProjectRollupRow[]);

	const STATUS_OPTIONS: { id: ShellStatusFilter | ''; label: string }[] = [
		{ id: '', label: 'All' },
		{ id: 'running', label: 'Running' },
		{ id: 'closed', label: 'Closed' }
	];

	const TOOL_OPTIONS: { id: ShellToolName | ''; label: string }[] = [
		{ id: '', label: 'All tools' },
		{ id: 'Bash', label: 'Bash' },
		{ id: 'Monitor', label: 'Monitor' }
	];
</script>

<svelte:head>
	<title>Background Shells · Claude Karma</title>
</svelte:head>

<div class="max-w-6xl mx-auto p-6 flex flex-col gap-5">
	<PageHeader
		title="Background Shells"
		icon={Terminal}
		iconColor="--nav-red"
		breadcrumbs={[{ label: 'Dashboard', href: '/' }, { label: 'Background Shells' }]}
		subtitle="Bash[run_in_background] · Monitor tool calls"
	/>

	<!-- ── Stats strip ──────────────────────────────────────────────────── -->
	<div
		class="flex items-center gap-6 px-4 py-3 rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)] font-mono text-sm"
	>
		<span>
			<span class="text-[var(--text-primary)] font-semibold">{stats.spawned}</span>
			<span class="text-[var(--text-muted)] ml-1">spawned</span>
		</span>
		<span class="text-[var(--border)]">·</span>
		<span>
			<span
				class="font-semibold"
				style="color: var(--status-active)"
			>{stats.running}</span>
			<span class="text-[var(--text-muted)] ml-1">still running</span>
		</span>
		<span class="text-[var(--border)]">·</span>
		<span>
			<span class="text-[var(--text-secondary)] font-semibold">{stats.closed}</span>
			<span class="text-[var(--text-muted)] ml-1">closed</span>
		</span>
	</div>

	<!-- ── Filter bar ───────────────────────────────────────────────────── -->
	<div
		class="flex flex-wrap items-center gap-3 px-3 py-2 rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)]"
	>
		<!-- Status tabs -->
		<div class="flex gap-0.5 p-0.5" role="tablist" aria-label="Filter by status">
			{#each STATUS_OPTIONS as opt (opt.id)}
				{@const active = filterStatus === opt.id}
				<button
					type="button"
					role="tab"
					aria-selected={active}
					onclick={() => {
						filterStatus = opt.id;
						navigate({ status: opt.id });
					}}
					class="inline-flex items-center gap-1.5 px-3 py-1 text-xs rounded transition-colors
						{active
						? 'bg-[var(--bg-base)] text-[var(--text-primary)] font-semibold shadow-[var(--shadow-sm)]'
						: 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'}"
				>
					{opt.label}
					{#if opt.id === ''}
						<span class="font-mono text-[10px] text-[var(--text-faint)]">{stats.spawned}</span>
					{:else if opt.id === 'running'}
						<span class="font-mono text-[10px] text-[var(--text-faint)]">{stats.running}</span>
					{:else}
						<span class="font-mono text-[10px] text-[var(--text-faint)]">{stats.closed}</span>
					{/if}
				</button>
			{/each}
		</div>

		<span class="w-px h-4 bg-[var(--border)]"></span>

		<!-- Tool select -->
		<div class="relative">
			<select
				bind:value={filterTool}
				onchange={() => navigate({ tool: filterTool })}
				class="appearance-none text-xs px-2.5 pr-6 py-1 rounded border border-[var(--border)] bg-[var(--bg-base)] text-[var(--text-secondary)] hover:border-[var(--border-hover)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)] cursor-pointer"
			>
				{#each TOOL_OPTIONS as opt (opt.id)}
					<option value={opt.id}>{opt.label}</option>
				{/each}
			</select>
			<ChevronDown
				size={10}
				class="absolute right-1.5 top-1/2 -translate-y-1/2 text-[var(--text-faint)] pointer-events-none"
			/>
		</div>

		<!-- Project select (populated from rollup) -->
		{#if rollup.length > 0}
			<div class="relative ml-auto">
				<select
					bind:value={filterProject}
					onchange={() => navigate({ project: filterProject })}
					class="appearance-none text-xs px-2.5 pr-6 py-1 rounded border border-[var(--border)] bg-[var(--bg-base)] text-[var(--text-secondary)] hover:border-[var(--border-hover)] focus:outline-none focus:ring-1 focus:ring-[var(--accent)] cursor-pointer"
				>
					<option value="">All projects</option>
					{#each rollup as row (row.project_encoded_name)}
						<option value={row.project_encoded_name}
							>{row.project_display_name ?? row.project_encoded_name}
							({row.shell_count})</option
						>
					{/each}
				</select>
				<ChevronDown
					size={10}
					class="absolute right-1.5 top-1/2 -translate-y-1/2 text-[var(--text-faint)] pointer-events-none"
				/>
			</div>
		{/if}
	</div>

	<!-- ── Active project filter badge ──────────────────────────────────── -->
	{#if data.filters.project}
		<div
			class="flex items-center gap-2 text-sm px-3 py-2 rounded-md bg-[var(--accent-muted)] border border-[var(--accent-subtle)]"
		>
			<span class="text-[var(--text-secondary)]">Filtered to project:</span>
			<code class="font-mono text-[var(--text-primary)] text-xs">{data.filters.project}</code>
			<a
				href="/projects/{data.filters.project}"
				class="font-mono text-[10px] text-[var(--accent)] hover:underline ml-1"
				>view project →</a
			>
			<button
				type="button"
				onclick={clearProject}
				class="ml-auto text-[var(--accent)] hover:underline text-xs"
			>
				Clear
			</button>
		</div>
	{/if}

	<!-- ── Empty state ──────────────────────────────────────────────────── -->
	{#if shells.length === 0}
		<div
			class="flex flex-col items-center justify-center gap-3 py-20 rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)]"
		>
			<Terminal size={36} class="text-[var(--text-faint)]" />
			<p class="text-[var(--text-primary)] font-medium text-sm m-0">No background shells recorded yet</p>
			<p class="text-[var(--text-muted)] text-xs text-center max-w-xs m-0">
				Background shells are spawned when Claude Code runs
				<code class="font-mono bg-[var(--bg-muted)] px-1 rounded">Bash</code>
				with
				<code class="font-mono bg-[var(--bg-muted)] px-1 rounded">run_in_background: true</code>
				or uses the
				<code class="font-mono bg-[var(--bg-muted)] px-1 rounded">Monitor</code> tool.
			</p>
		</div>
	{:else}
		<!-- ── Shell ladder ────────────────────────────────────────────────── -->
		<div class="rounded-lg border border-[var(--border)] overflow-hidden bg-[var(--bg-base)]">

			<!-- Column header -->
			<div
				class="px-4 py-2 bg-[var(--bg-subtle)] border-b border-[var(--border)] flex items-center gap-3"
			>
				<span
					class="text-[9px] uppercase tracking-wider font-semibold text-[var(--text-muted)] w-[88px] shrink-0"
					>Shell</span
				>
				<span
					class="text-[9px] uppercase tracking-wider font-semibold text-[var(--text-muted)] flex-1"
					>Timeline · command</span
				>
				<span
					class="text-[9px] uppercase tracking-wider font-semibold text-[var(--text-muted)] w-[100px] text-right shrink-0"
					>Duration · polls</span
				>
			</div>

			{#each shells as shell (shell.id)}
				{@const key = shellKey(shell)}
				{@const isRunning = shell.terminated_at === null}
				{@const isMonitor = shell.tool_name === 'Monitor'}
				{@const startPct = pct(shell.spawned_at)}
				{@const endPct = isRunning ? pctNow() : pct(shell.terminated_at!)}
				{@const widthPct = Math.max(endPct - startPct, 0.5)}
				{@const isKilled = shell.terminated_by === 'kill'}
				{@const isNatural = shell.terminated_by === 'natural' || shell.terminated_by === 'timeout'}
				{@const selected = isSelected(shell)}

				<div
					class="border-t border-[var(--border-subtle)] transition-colors
						{isMonitor ? 'bg-[var(--info-subtle)]' : ''}
						{selected ? 'bg-[var(--accent-muted)]' : 'hover:bg-[var(--bg-subtle)]'}"
				>
					<!-- Row -->
					<button
						type="button"
						onclick={() => toggleSelect(shell)}
						class="w-full text-left px-4 py-2.5 flex items-start gap-3 cursor-pointer"
						aria-expanded={selected}
					>
						<!-- Shell ID -->
						<div class="w-[88px] shrink-0 flex flex-col gap-0.5 pt-0.5">
							<code
								class="font-mono text-xs font-semibold tracking-tight text-[var(--text-primary)]"
								>{key}</code
							>
							{#if isMonitor}
								<span
									class="text-[9px] font-mono uppercase tracking-wide"
									style="color: var(--info)"
									>Monitor</span
								>
							{:else}
								<span class="text-[9px] font-mono uppercase tracking-wide text-[var(--text-faint)]"
									>Bash</span
								>
							{/if}
						</div>

						<!-- Timeline bar + command label -->
						<div class="flex-1 min-w-0 flex flex-col gap-1.5">
							<!-- Timeline track -->
							<div
								class="relative h-[14px] flex items-center"
								aria-label="Timeline bar"
							>
								<!-- Full track bg -->
								<div
									class="absolute inset-y-[5px] left-0 right-0 rounded-full"
									style="background: var(--bg-muted)"
								></div>

								<!-- Active bar segment -->
								<div
									class="absolute inset-y-[4px] rounded-full transition-all"
									style="
										left: {startPct}%;
										width: {widthPct}%;
										background: {isRunning
										? 'var(--status-active)'
										: isKilled
											? 'var(--error)'
											: isNatural
												? 'var(--status-done)'
												: 'var(--text-muted)'};
										opacity: {isRunning ? 0.85 : 0.55};
									"
								></div>

								<!-- Poll dots -->
								{#if shell.polls}
									{#each shell.polls as poll}
										{@const pollPct = pct(poll.polled_at)}
										<span
											class="absolute w-[6px] h-[6px] rounded-full -translate-x-1/2 -translate-y-1/2 top-1/2 ring-1 ring-[var(--bg-base)]"
											style="
												left: {pollPct}%;
												background: {isKilled ? 'var(--error)' : 'var(--status-active)'};
											"
											title="Poll at {poll.polled_at}"
										></span>
									{/each}
								{/if}

								<!-- End cap glyph -->
								{#if isRunning}
									<span
										class="absolute font-mono text-[11px] leading-none -translate-y-1/2 top-1/2"
										style="left: {Math.min(endPct, 97)}%; color: var(--status-active)"
										title="Still running"
									>▶</span>
								{:else if isKilled}
									<span
										class="absolute font-mono text-[11px] leading-none -translate-y-1/2 top-1/2"
										style="left: {Math.min(endPct, 97)}%; color: var(--error)"
										title="Killed"
									>×</span>
								{:else}
									<span
										class="absolute font-mono text-[11px] leading-none -translate-y-1/2 top-1/2"
										style="left: {Math.min(endPct, 97)}%; color: var(--status-done)"
										title="Exited"
									>■</span>
								{/if}
							</div>

							<!-- Command + description -->
							<div class="flex flex-col gap-0">
								<code class="font-mono text-[11px] text-[var(--text-secondary)] truncate leading-snug"
									>{truncateCmd(shell.command)}</code
								>
								{#if shell.description}
									<span class="text-[10px] text-[var(--text-faint)] truncate leading-snug"
										>{shell.description}</span
									>
								{/if}
							</div>
						</div>

						<!-- Duration + poll count -->
						<div
							class="w-[100px] shrink-0 text-right flex flex-col items-end gap-0.5 pt-0.5"
						>
							<span
								class="font-mono text-[11px]"
								style="color: {isRunning ? 'var(--status-active)' : 'var(--text-muted)'}"
							>
								{durationLabel(shell)}
								{#if isRunning}
									<span class="text-[9px] ml-0.5">alive</span>
								{/if}
							</span>
							<span class="font-mono text-[10px] text-[var(--text-faint)]">
								{shell.poll_count} poll{shell.poll_count !== 1 ? 's' : ''}
							</span>
							{#if shell.total_output_bytes > 0}
								<span class="font-mono text-[9px] text-[var(--text-faint)]">
									{formatBytes(shell.total_output_bytes)}
								</span>
							{/if}
						</div>
					</button>

					<!-- ── Detail panel (expanded) ──────────────────────────── -->
					{#if selected && selectedShell}
						<div
							class="px-4 pb-4 border-t border-[var(--border-subtle)] bg-[var(--bg-subtle)]"
						>
							<div class="pt-3 flex flex-col gap-3">
								<!-- Full command -->
								<div>
									<div
										class="text-[9px] uppercase tracking-wider font-semibold text-[var(--text-muted)] mb-1"
									>
										Full command
									</div>
									<pre
										class="font-mono text-xs text-[var(--text-primary)] bg-[var(--bg-muted)] rounded p-3 overflow-x-auto whitespace-pre-wrap break-all leading-relaxed m-0"
									>{selectedShell.command}{#if selectedShell.command_truncated}
<span class="text-[var(--text-faint)] italic"> [truncated]</span>{/if}</pre>
								</div>

								<!-- Metadata row -->
								<div class="flex flex-wrap gap-4 text-xs text-[var(--text-muted)]">
									<div>
										<span class="text-[var(--text-faint)]">spawned</span>
										<code class="font-mono ml-1 text-[var(--text-secondary)]"
											>{new Date(selectedShell.spawned_at).toLocaleString()}</code
										>
									</div>
									{#if selectedShell.terminated_at}
										<div>
											<span class="text-[var(--text-faint)]">ended</span>
											<code class="font-mono ml-1 text-[var(--text-secondary)]"
												>{new Date(selectedShell.terminated_at).toLocaleString()}</code
											>
										</div>
									{/if}
									{#if selectedShell.terminated_by}
										<div>
											<span class="text-[var(--text-faint)]">terminated by</span>
											<code
												class="font-mono ml-1"
												style="color: {selectedShell.terminated_by === 'kill'
													? 'var(--error)'
													: 'var(--status-done)'}"
												>{selectedShell.terminated_by}</code
											>
										</div>
									{/if}
									{#if selectedShell.exit_code !== null}
										<div>
											<span class="text-[var(--text-faint)]">exit code</span>
											<code
												class="font-mono ml-1"
												style="color: {selectedShell.exit_code === 0
													? 'var(--status-done)'
													: 'var(--error)'}"
												>{selectedShell.exit_code}</code
											>
										</div>
									{/if}
									{#if selectedShell.timeout_ms !== null}
										<div>
											<span class="text-[var(--text-faint)]">timeout</span>
											<code class="font-mono ml-1 text-[var(--text-secondary)]"
												>{selectedShell.timeout_ms / 1000}s</code
											>
										</div>
									{/if}
									{#if selectedShell.session_slug}
										<div>
											<span class="text-[var(--text-faint)]">session</span>
											<a
												href="/sessions/{selectedShell.session_uuid}"
												class="font-mono ml-1 text-[var(--accent)] hover:underline"
												>{selectedShell.session_slug}</a
											>
										</div>
									{/if}
									{#if selectedShell.project_encoded_name}
										<div>
											<span class="text-[var(--text-faint)]">project</span>
											<a
												href="/projects/{selectedShell.project_encoded_name}"
												class="font-mono ml-1 text-[var(--accent)] hover:underline text-xs"
												>{selectedShell.project_display_name ??
													selectedShell.project_encoded_name}</a
											>
										</div>
									{/if}
								</div>

								<!-- Latest poll excerpt -->
								{#if selectedShell.polls && selectedShell.polls.length > 0}
									{@const latestPoll =
										selectedShell.polls[selectedShell.polls.length - 1]}
									<div>
										<div
											class="text-[9px] uppercase tracking-wider font-semibold text-[var(--text-muted)] mb-1"
										>
											Latest poll output
											<span class="font-normal text-[var(--text-faint)]"
												>({new Date(latestPoll.polled_at).toLocaleTimeString()})</span
											>
										</div>
										{#if latestPoll.output_excerpt}
											<pre
												class="font-mono text-[11px] text-[var(--text-secondary)] bg-[var(--bg-muted)] rounded p-3 overflow-x-auto whitespace-pre-wrap break-all leading-relaxed max-h-48 m-0"
											>{latestPoll.output_excerpt}{#if latestPoll.output_truncated}<span
													class="text-[var(--text-faint)] italic"
												> [truncated]</span
												>{/if}</pre>
										{:else}
											<p class="text-xs text-[var(--text-faint)] italic m-0">No output captured</p>
										{/if}
									</div>
								{/if}

								<!-- Lifecycle timeline (text-based) -->
								<div>
									<div
										class="text-[9px] uppercase tracking-wider font-semibold text-[var(--text-muted)] mb-1.5"
									>
										Lifecycle
									</div>
									<div class="flex items-center gap-1 flex-wrap font-mono text-[10px]">
										<span
											class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-[var(--bg-muted)]"
										>
											<span style="color: var(--status-active)">┃</span>
											<span class="text-[var(--text-muted)]">spawn</span>
										</span>
										{#if selectedShell.polls && selectedShell.polls.length > 0}
											<span class="text-[var(--text-faint)]">━</span>
											{#each selectedShell.polls as _, i}
												{#if i < 6}
													<span
														class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-[var(--bg-muted)]"
													>
														<span style="color: var(--status-active)">●</span>
														<span class="text-[var(--text-muted)]">poll</span>
													</span>
													{#if i < Math.min(selectedShell.polls!.length - 1, 5)}
														<span class="text-[var(--text-faint)]">━</span>
													{/if}
												{/if}
											{/each}
											{#if selectedShell.polls.length > 6}
												<span class="text-[var(--text-faint)]">…+{selectedShell.polls.length - 6}</span>
											{/if}
										{/if}
										<span class="text-[var(--text-faint)]">━</span>
										{#if isRunning}
											<span
												class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded"
												style="background: var(--status-waiting-bg)"
											>
												<Play size={10} style="color: var(--status-active)" />
												<span style="color: var(--status-active)">running</span>
											</span>
										{:else if isKilled}
											<span
												class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded"
												style="background: var(--error-subtle)"
											>
												<X size={10} style="color: var(--error)" />
												<span style="color: var(--error)">killed</span>
											</span>
										{:else}
											<span
												class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded"
												style="background: var(--success-subtle)"
											>
												<Square size={10} style="color: var(--status-done)" />
												<span style="color: var(--status-done)">exited</span>
											</span>
										{/if}
									</div>
								</div>
							</div>
						</div>
					{/if}
				</div>
			{/each}
		</div>

		<!-- ── Project rollup footer ─────────────────────────────────────── -->
		{#if rollup.length > 1}
			<div
				class="rounded-lg border border-[var(--border)] overflow-hidden bg-[var(--bg-base)]"
			>
				<div
					class="px-4 py-2 bg-[var(--bg-subtle)] border-b border-[var(--border)] text-[9px] uppercase tracking-wider font-semibold text-[var(--text-muted)]"
				>
					By project
				</div>
				<div class="divide-y divide-[var(--border-subtle)]">
					{#each rollup as row (row.project_encoded_name)}
						<a
							href="/shells?project={row.project_encoded_name}"
							class="flex items-center gap-3 px-4 py-2.5 hover:bg-[var(--bg-subtle)] transition-colors"
						>
							<span class="flex-1 text-xs text-[var(--text-primary)] truncate"
								>{row.project_display_name ?? row.project_encoded_name}</span
							>
							<span class="font-mono text-[11px] text-[var(--text-muted)]"
								>{row.shell_count} shell{row.shell_count !== 1 ? 's' : ''}</span
							>
							{#if row.running_count > 0}
								<span
									class="font-mono text-[10px] px-1.5 py-0.5 rounded-full"
									style="background: var(--status-waiting-bg); color: var(--status-active)"
								>
									{row.running_count} running
								</span>
							{/if}
							<span class="font-mono text-[10px] text-[var(--text-faint)]"
								>{formatBytes(row.total_output_bytes)}</span
							>
						</a>
					{/each}
				</div>
			</div>
		{/if}
	{/if}
</div>
