<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import type { CronJob, CronFire } from '$lib/api-types';
	import { Clock, ExternalLink, Info, AlertTriangle, CheckCircle2, Trash2, X } from 'lucide-svelte';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';

	let { data } = $props();

	// ── URL-state filters ─────────────────────────────────────────────────────
	let projectFilter = $state(data.filters.project);
	let activeOnly = $state(data.filters.active_only === 'true');

	function navigate(opts: { project?: string; active_only?: string }) {
		const params = new URLSearchParams($page.url.searchParams);
		for (const [k, v] of Object.entries(opts)) {
			if (v) params.set(k, v);
			else params.delete(k);
		}
		goto(`/cron?${params.toString()}`);
	}

	function toggleActiveOnly() {
		activeOnly = !activeOnly;
		navigate({ active_only: activeOnly ? 'true' : '' });
	}

	function clearProject() {
		projectFilter = '';
		navigate({ project: '' });
	}

	// ── Selected job detail ───────────────────────────────────────────────────
	let selectedId = $state<number | null>(null);
	let selectedJob = $derived(data.jobs.find((j: CronJob) => j.id === selectedId) ?? null);

	// Auto-select first job when list changes
	$effect(() => {
		if (data.jobs.length > 0 && selectedId === null) {
			selectedId = data.jobs[0].id;
		}
	});

	// ── Summary stats ─────────────────────────────────────────────────────────
	const now = new Date();
	const TTL_MS = 7 * 24 * 60 * 60 * 1000;

	function isDeleted(job: CronJob): boolean {
		return job.deleted_at !== null;
	}
	function isExpired(job: CronJob): boolean {
		if (isDeleted(job)) return false;
		return new Date(job.ttl_expires_at) < now;
	}
	function isLikelyActive(job: CronJob): boolean {
		return !isDeleted(job) && !isExpired(job);
	}

	let stats = $derived({
		created: data.jobs.length,
		deleted: data.jobs.filter((j: CronJob) => isDeleted(j)).length,
		active: data.jobs.filter((j: CronJob) => isLikelyActive(j)).length
	});

	let hasAnyLiveState = $derived(
		data.jobs.some((j: CronJob) => j.latest_state != null)
	);

	// ── Helpers ───────────────────────────────────────────────────────────────
	function fmtDate(iso: string | null): string {
		if (!iso) return '—';
		const d = new Date(iso);
		return d.toLocaleString(undefined, {
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	function fmtRelative(iso: string | null): string {
		if (!iso) return '—';
		const ms = now.getTime() - new Date(iso).getTime();
		if (ms < 60_000) return 'just now';
		if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}m ago`;
		if (ms < 86_400_000) return `${Math.floor(ms / 3_600_000)}h ago`;
		return `${Math.floor(ms / 86_400_000)}d ago`;
	}

	function ttlProgress(job: CronJob): number {
		const created = new Date(job.created_at).getTime();
		const elapsed = now.getTime() - created;
		return Math.min(elapsed / TTL_MS, 1);
	}

	function ttlRemaining(job: CronJob): string {
		const expiresAt = new Date(job.ttl_expires_at).getTime();
		const remaining = expiresAt - now.getTime();
		if (remaining <= 0) return 'expired';
		const days = Math.floor(remaining / 86_400_000);
		const hours = Math.floor((remaining % 86_400_000) / 3_600_000);
		if (days > 0) return `${days}d ${hours}h left`;
		const mins = Math.floor((remaining % 3_600_000) / 60_000);
		if (hours > 0) return `${hours}h ${mins}m left`;
		return `${mins}m left`;
	}

	function jobStatusLabel(job: CronJob): string {
		if (isDeleted(job)) return `deleted via ${job.deleted_via ?? 'unknown'}`;
		if (isExpired(job)) return 'TTL expired';
		return 'likely active';
	}

	function cronShorthand(expr: string): string {
		const parts = expr.trim().split(/\s+/);
		if (parts.length < 5) return expr;
		const [min, hour, dom, month, dow] = parts;
		if (expr === '* * * * *') return 'every minute';
		if (min.startsWith('*/')) return `every ${min.slice(2)} min`;
		if (hour.startsWith('*/')) return `every ${hour.slice(2)}h`;
		if (min !== '*' && hour !== '*' && dom === '*' && month === '*' && dow === '*')
			return `daily at ${hour.padStart(2, '0')}:${min.padStart(2, '0')}`;
		return expr;
	}
</script>

<svelte:head>
	<title>Cron · Claude Karma</title>
</svelte:head>

<div class="max-w-[1400px] mx-auto p-6 flex flex-col gap-5 min-h-screen">
	<PageHeader
		title="Scheduled Jobs"
		icon={Clock}
		iconColor="--nav-teal"
		breadcrumbs={[{ label: 'Dashboard', href: '/' }, { label: 'Cron' }]}
		subtitle="reconstructed from session history"
	/>

	<!-- ── Honesty strip ──────────────────────────────────────────────────── -->
	<div
		class="flex items-start gap-3 px-4 py-3 rounded-lg border text-sm"
		style="background: var(--info-subtle); border-color: rgba(var(--info-rgb), 0.2);"
	>
		{#if hasAnyLiveState}
			<CheckCircle2
				size={15}
				class="shrink-0 mt-0.5"
				style="color: var(--success);"
			/>
			<div class="flex-1 min-w-0">
				<span style="color: var(--text-primary);">
					Live state captured via hook
				</span>
				<span class="ml-2" style="color: var(--text-secondary);">
					Some jobs have ground-truth state from the live-session hook.
				</span>
			</div>
		{:else}
			<Info size={15} class="shrink-0 mt-0.5" style="color: var(--info);" />
			<div class="flex-1 min-w-0 flex flex-wrap items-baseline gap-x-4 gap-y-1">
				<span style="color: var(--text-primary);">
					Cron in Claude Code is in-memory and session-scoped.
				</span>
				<span style="color: var(--text-secondary);">
					This view shows every CronCreate / CronDelete recorded in JSONL — not live state.
				</span>
				<a
					href="https://docs.anthropic.com/en/docs/claude-code"
					target="_blank"
					rel="noopener noreferrer"
					class="inline-flex items-center gap-1 text-xs font-medium"
					style="color: var(--info);"
				>
					docs <ExternalLink size={11} />
				</a>
			</div>
		{/if}
	</div>

	<!-- ── Stats bar ─────────────────────────────────────────────────────── -->
	{#if data.jobs.length > 0}
		<div
			class="flex items-center gap-4 text-sm px-1"
			style="color: var(--text-secondary);"
		>
			<span>
				<span class="font-semibold tabular-nums" style="color: var(--text-primary);">
					{stats.created}
				</span>
				<span class="ml-1">created</span>
			</span>
			<span style="color: var(--text-faint);">·</span>
			<span>
				<span class="font-semibold tabular-nums" style="color: var(--text-primary);">
					{stats.deleted}
				</span>
				<span class="ml-1">deleted</span>
			</span>
			<span style="color: var(--text-faint);">·</span>
			<span>
				<span class="font-semibold tabular-nums" style="color: var(--status-active);">
					{stats.active}
				</span>
				<span class="ml-1">likely active (within 7d TTL)</span>
			</span>

			<!-- Filters -->
			<div class="ml-auto flex items-center gap-2">
				{#if data.filters.project}
					<div
						class="flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs border"
						style="background: var(--accent-muted); border-color: var(--accent-subtle); color: var(--accent);"
					>
						<span class="font-mono">{data.filters.project}</span>
						<button
							type="button"
							onclick={clearProject}
							class="hover:opacity-70 transition-opacity"
							aria-label="Clear project filter"
						>
							<X size={11} />
						</button>
					</div>
				{/if}
				<button
					type="button"
					onclick={toggleActiveOnly}
					class="px-3 py-1 rounded-md text-xs border transition-colors"
					style={activeOnly
						? 'background: var(--status-active); border-color: var(--status-active); color: #fff;'
						: 'background: var(--bg-subtle); border-color: var(--border); color: var(--text-secondary);'}
				>
					Active only
				</button>
			</div>
		</div>
	{/if}

	<!-- ── Main content ──────────────────────────────────────────────────── -->
	{#if data.jobs.length === 0}
		<!-- Empty state -->
		<div
			class="flex flex-col items-center justify-center py-20 text-center gap-4"
		>
			<div
				class="w-14 h-14 rounded-full flex items-center justify-center border"
				style="background: var(--bg-subtle); border-color: var(--border); color: var(--text-faint);"
			>
				<Clock size={24} />
			</div>
			<div>
				<p class="text-lg font-semibold" style="color: var(--text-primary);">
					No scheduled jobs recorded yet
				</p>
				<p class="text-sm mt-1" style="color: var(--text-secondary);">
					Karma records cron jobs when Claude Code calls CronCreate in your sessions.<br />
					Cron is session-scoped — jobs are held in-memory and expire after 7 days.
				</p>
			</div>
		</div>
	{:else}
		<!-- Two-pane layout -->
		<div class="flex gap-0 rounded-lg border overflow-hidden" style="border-color: var(--border); min-height: 520px;">
			<!-- ── Left: job list ───────────────────────────────────────────── -->
			<div
				class="w-[340px] shrink-0 flex flex-col overflow-y-auto"
				style="border-right: 1px solid var(--border); background: var(--bg-subtle);"
			>
				{#each data.jobs as job (job.id)}
					{@const deleted = isDeleted(job)}
					{@const expired = isExpired(job)}
					{@const active = isLikelyActive(job)}
					{@const selected = selectedId === job.id}
					{@const progress = ttlProgress(job)}

					<button
						type="button"
						onclick={() => (selectedId = job.id)}
						class="w-full text-left px-4 py-3.5 transition-colors border-b"
						style="
							border-color: var(--border-subtle);
							background: {selected ? 'var(--bg-base)' : 'transparent'};
						"
					>
						<!-- Leading dot + cron_id -->
						<div class="flex items-center gap-2 mb-1">
							<span
								class="w-2 h-2 rounded-full shrink-0"
								style="background: {deleted
									? 'var(--text-faint)'
									: expired
										? 'var(--warning)'
										: 'var(--status-active)'};"
							></span>
							<span
								class="font-mono text-[11px] font-semibold tracking-wide"
								style="color: {selected ? 'var(--accent)' : 'var(--text-primary)'}; font-family: var(--font-mono);"
							>
								{(job.cron_id ?? job.tool_use_id).slice(0, 8)}
							</span>
							{#if job.latest_state}
								<span
									class="ml-auto w-1.5 h-1.5 rounded-full shrink-0"
									style="background: var(--success);"
									title="Live state captured"
								></span>
							{/if}
						</div>

						<!-- Cron expression -->
						<div
							class="font-mono text-xs mb-1 {deleted ? 'line-through opacity-50' : ''}"
							style="color: var(--text-secondary); font-family: var(--font-mono);"
						>
							{job.cron_expression}
							<span
								class="ml-1.5 not-italic font-sans text-[10px]"
								style="color: var(--text-faint);"
							>
								{cronShorthand(job.cron_expression)}
							</span>
						</div>

						<!-- Prompt excerpt -->
						<div
							class="text-[11px] line-clamp-2 mb-2"
							style="color: var(--text-muted);"
						>
							"{job.prompt.slice(0, 80)}{job.prompt.length > 80 ? '…' : ''}"
						</div>

						<!-- Bottom meta row -->
						<div class="flex items-center gap-2 text-[10px]" style="color: var(--text-faint);">
							<span>{job.recurring ? 'recurring' : 'one-shot'}</span>
							<span>·</span>
							<span>created {fmtRelative(job.created_at)}</span>
							{#if job.fires && job.fires.length > 0}
								<span>·</span>
								<span>{job.fires.length} fire{job.fires.length !== 1 ? 's' : ''}</span>
							{/if}
						</div>

						<!-- TTL bar -->
						{#if !deleted}
							<div
								class="mt-2 h-px rounded-full overflow-hidden"
								style="background: var(--border);"
							>
								<div
									class="h-full rounded-full transition-all"
									style="
										width: {Math.round(progress * 100)}%;
										background: {expired ? 'var(--warning)' : 'var(--status-active)'};
										opacity: 0.6;
									"
								></div>
							</div>
						{/if}
					</button>
				{/each}
			</div>

			<!-- ── Right: detail pane ────────────────────────────────────────── -->
			<div class="flex-1 min-w-0 overflow-y-auto p-6" style="background: var(--bg-base);">
				{#if selectedJob}
					{@const job = selectedJob}
					{@const deleted = isDeleted(job)}
					{@const expired = isExpired(job)}
					{@const active = isLikelyActive(job)}

					<!-- Detail header -->
					<div class="flex items-start justify-between gap-4 mb-5 pb-4 border-b" style="border-color: var(--border);">
						<div>
							<div class="flex items-center gap-2 mb-1">
								<span
									class="font-mono text-base font-bold tracking-wider"
									style="font-family: var(--font-mono); color: var(--text-primary);"
								>
									{(job.cron_id ?? job.tool_use_id).slice(0, 8)}
								</span>
								{#if job.latest_state}
									<span
										class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium"
										style="background: var(--success-subtle); color: var(--success);"
									>
										<span class="w-1.5 h-1.5 rounded-full" style="background: var(--success);"></span>
										live state
									</span>
								{/if}
							</div>
							{#if job.project_display_name}
								<div class="text-xs" style="color: var(--text-muted);">
									{job.project_display_name}
									{#if job.session_slug}
										<span class="ml-1 font-mono" style="color: var(--text-faint);">
											· {job.session_slug}
										</span>
									{/if}
								</div>
							{/if}
						</div>

						<!-- Status badge -->
						<span
							class="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium shrink-0"
							style="
								background: {deleted
									? 'var(--bg-muted)'
									: expired
										? 'var(--warning-subtle)'
										: 'var(--info-subtle)'};
								color: {deleted
									? 'var(--text-muted)'
									: expired
										? 'var(--warning)'
										: 'var(--status-active)'};
							"
						>
							{#if deleted}
								<Trash2 size={11} />
							{:else if expired}
								<AlertTriangle size={11} />
							{:else}
								<span class="w-1.5 h-1.5 rounded-full" style="background: var(--status-active);"></span>
							{/if}
							{jobStatusLabel(job)}
						</span>
					</div>

					<!-- Detail rows table -->
					<div
						class="rounded-lg border overflow-hidden mb-5"
						style="border-color: var(--border);"
					>
						{#each [
							{ label: 'schedule', value: null, isSchedule: true },
							{ label: 'status', value: null, isStatus: true },
							{ label: 'type', value: job.recurring ? 'recurring' : 'one-shot', isSchedule: false, isStatus: false },
							{ label: 'session', value: job.session_uuid.slice(0, 8) + '…', isSchedule: false, isStatus: false },
							{ label: 'created', value: fmtDate(job.created_at), isSchedule: false, isStatus: false },
							{ label: 'ttl expires', value: fmtDate(job.ttl_expires_at), isSchedule: false, isStatus: false },
							...(job.deleted_at ? [{ label: 'deleted', value: fmtDate(job.deleted_at), isSchedule: false, isStatus: false }] : [])
						] as row, i}
							<div
								class="flex items-start gap-4 px-4 py-2.5 {i > 0 ? 'border-t' : ''}"
								style="border-color: var(--border-subtle);"
							>
								<span
									class="text-[10px] uppercase tracking-wider font-semibold w-24 shrink-0 pt-0.5"
									style="color: var(--text-faint);"
								>
									{row.label}
								</span>
								<div class="flex-1 min-w-0">
									{#if row.isSchedule}
										<span
											class="font-mono text-sm {deleted ? 'line-through opacity-50' : ''}"
											style="font-family: var(--font-mono); color: var(--text-primary);"
										>
											{job.cron_expression}
										</span>
										<span
											class="ml-3 text-xs"
											style="color: var(--text-muted);"
										>
											{cronShorthand(job.cron_expression)}
											{#if job.recurring}· recur{/if}
										</span>
									{:else if row.isStatus}
										<div>
											<span
												class="text-sm font-medium"
												style="color: {deleted
													? 'var(--text-muted)'
													: expired
														? 'var(--warning)'
														: 'var(--status-active)'};"
											>
												{jobStatusLabel(job)}
											</span>
											{#if !deleted && !expired}
												<span class="ml-2 text-xs" style="color: var(--text-faint);">
													(7d TTL · {ttlRemaining(job)})
												</span>
											{:else if expired && !deleted}
												<span class="ml-2 text-xs" style="color: var(--text-faint);">
													expired {fmtRelative(job.ttl_expires_at)}
												</span>
											{/if}
										</div>
									{:else}
										<span
											class="text-sm font-mono"
											style="font-family: var(--font-mono); color: var(--text-primary);"
										>
											{row.value}
										</span>
									{/if}
								</div>
							</div>
						{/each}
					</div>

					<!-- Prompt -->
					<div class="mb-5">
						<div
							class="text-[10px] uppercase tracking-wider font-semibold mb-2"
							style="color: var(--text-faint);"
						>
							Prompt
						</div>
						<pre
							class="text-xs p-4 rounded-lg border whitespace-pre-wrap break-words leading-relaxed"
							style="
								font-family: var(--font-mono);
								background: var(--bg-subtle);
								border-color: var(--border);
								color: var(--text-secondary);
							"
						>{job.prompt}</pre>
					</div>

					<!-- Fires timeline -->
					<div>
						<div
							class="text-[10px] uppercase tracking-wider font-semibold mb-2"
							style="color: var(--text-faint);"
						>
							Inferred fires
						</div>
						{#if !job.fires || job.fires.length === 0}
							<p class="text-xs" style="color: var(--text-muted);">
								No fires inferred for this job.
							</p>
						{:else}
							<div
								class="rounded-lg border overflow-hidden"
								style="border-color: var(--border);"
							>
								{#each job.fires as fire, i (i)}
									<div
										class="flex items-start gap-3 px-4 py-2.5 {i > 0 ? 'border-t' : ''}"
										style="border-color: var(--border-subtle);"
									>
										<span
											class="font-mono text-[11px] shrink-0 mt-0.5"
											style="font-family: var(--font-mono); color: var(--text-muted);"
										>
											{fmtDate(fire.fired_at)}
										</span>
										<div class="flex-1 min-w-0">
											{#if fire.outcome_excerpt}
												<p
													class="text-[11px] truncate"
													style="color: var(--text-secondary);"
												>
													{fire.outcome_excerpt}
												</p>
											{/if}
											<div class="flex items-center gap-2 mt-0.5">
												<span
													class="text-[10px]"
													style="color: var(--text-faint);"
												>
													{fire.inference_source}
												</span>
												<span
													class="text-[10px] px-1 py-0.5 rounded"
													style="
														background: {fire.inference_confidence > 0.8
															? 'var(--success-subtle)'
															: 'var(--bg-muted)'};
														color: {fire.inference_confidence > 0.8
															? 'var(--success)'
															: 'var(--text-faint)'};
													"
												>
													{Math.round(fire.inference_confidence * 100)}% conf
												</span>
											</div>
										</div>
									</div>
								{/each}
							</div>
						{/if}
					</div>
				{:else}
					<div
						class="flex flex-col items-center justify-center h-full py-16 text-center"
						style="color: var(--text-faint);"
					>
						<Clock size={32} class="mb-3 opacity-30" />
						<p class="text-sm">Select a job to view details</p>
					</div>
				{/if}
			</div>
		</div>
	{/if}
</div>
