<script lang="ts">
	import { onMount } from 'svelte';
	import { Clock, Loader2, CircleCheck, CircleX, AlertCircle } from 'lucide-svelte';
	import { API_BASE } from '$lib/config';
	import type { CronJob, CronListResponse } from '$lib/api-types';

	interface Props {
		sessionUuid: string;
	}
	let { sessionUuid }: Props = $props();

	let loading = $state(true);
	let error = $state<string | null>(null);
	let jobs = $state<CronJob[]>([]);
	let expandedId = $state<number | null>(null);

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

	let hasLiveState = $derived(jobs.some((j) => j.latest_state !== null && j.latest_state !== undefined));

	function ttlRemaining(ttl: string): string {
		const ms = new Date(ttl).getTime() - Date.now();
		if (ms <= 0) return 'expired';
		const hours = Math.floor(ms / 3_600_000);
		const days = Math.floor(hours / 24);
		if (days > 0) return `${days}d ${hours % 24}h left`;
		return `${hours}h left`;
	}

	function ttlProgress(created: string, ttl: string): number {
		const total = new Date(ttl).getTime() - new Date(created).getTime();
		const elapsed = Date.now() - new Date(created).getTime();
		return Math.max(0, Math.min(100, (elapsed / total) * 100));
	}

	function jobStatus(j: CronJob): { label: string; color: string } {
		if (j.deleted_at) {
			return { label: `deleted via ${j.deleted_via}`, color: 'var(--text-muted)' };
		}
		if (new Date(j.ttl_expires_at).getTime() < Date.now()) {
			return { label: 'TTL expired', color: 'var(--warning)' };
		}
		return { label: 'likely active', color: 'var(--status-active)' };
	}
</script>

<div class="space-y-4">
	<div class="flex items-baseline justify-between gap-4">
		<div>
			<h2 class="text-lg font-semibold text-[var(--text-primary)] m-0">Scheduled jobs (cron)</h2>
			<p class="text-sm text-[var(--text-muted)] m-0">
				{#if hasLiveState}
					Live state captured via hook.
				{:else}
					Reconstructed from session JSONL — cron in Claude Code is in-memory and session-scoped.
				{/if}
			</p>
		</div>
		{#if !loading && jobs.length > 0}
			<a
				href="/cron?project={jobs[0].project_encoded_name ?? ''}"
				class="text-xs text-[var(--text-secondary)] hover:text-[var(--accent)] transition-colors"
			>
				View all in project →
			</a>
		{/if}
	</div>

	{#if !hasLiveState && !loading && jobs.length > 0}
		<div
			class="rounded-lg border border-[var(--info)] bg-[var(--info-subtle)] p-3 text-xs text-[var(--text-secondary)] flex items-start gap-2"
		>
			<AlertCircle size={14} class="shrink-0 mt-0.5 text-[var(--info)]" />
			<div>
				The optional <code class="font-mono">cron_state_capture.py</code> hook is not installed
				for this session, so &quot;active&quot; status is inferred from the 7-day TTL window.
			</div>
		</div>
	{/if}

	{#if loading}
		<div class="flex items-center justify-center py-12 text-[var(--text-muted)]">
			<Loader2 size={20} class="animate-spin" />
		</div>
	{:else if error}
		<div
			class="rounded-lg border border-[var(--error)] bg-[var(--error-subtle)] p-4 text-sm text-[var(--error)]"
		>
			Failed to load cron jobs: {error}
		</div>
	{:else if jobs.length === 0}
		<div
			class="rounded-lg border border-dashed border-[var(--border)] p-8 text-center text-sm text-[var(--text-muted)]"
		>
			<Clock size={28} class="mx-auto mb-3 opacity-40" />
			<p class="m-0">No scheduled jobs recorded for this session.</p>
			<p class="m-0 mt-1 text-xs">
				They appear here when Claude runs <code class="font-mono">CronCreate</code>.
			</p>
		</div>
	{:else}
		<ul class="space-y-2">
			{#each jobs as job (job.id)}
				{@const status = jobStatus(job)}
				{@const expired = !job.deleted_at && new Date(job.ttl_expires_at).getTime() < Date.now()}
				<li
					class="rounded-lg border border-[var(--border)] hover:border-[var(--border-hover)] transition-colors overflow-hidden bg-[var(--bg-subtle)]"
				>
					<button
						type="button"
						class="w-full text-left p-3 flex flex-col gap-2 hover:bg-[var(--bg-muted)] transition-colors"
						onclick={() => (expandedId = expandedId === job.id ? null : job.id)}
					>
						<div class="flex items-center gap-3">
							<span
								class="inline-block w-2 h-2 rounded-full shrink-0"
								style:background={status.color}
								aria-hidden="true"
							></span>
							<code class="font-mono text-base text-[var(--text-primary)] shrink-0">
								{job.cron_id ?? '—'}
							</code>
							<code
								class="font-mono text-sm text-[var(--text-secondary)] shrink-0"
								class:line-through={job.deleted_at !== null}
							>
								{job.cron_expression}
							</code>
							<span
								class="text-xs uppercase tracking-wide font-medium shrink-0"
								style:color={status.color}
							>
								{#if !job.deleted_at && !expired}
									<CircleCheck size={11} class="inline" />
								{:else if job.deleted_at}
									<CircleX size={11} class="inline" />
								{:else}
									<AlertCircle size={11} class="inline" />
								{/if}
								{status.label}
							</span>
							{#if job.fires && job.fires.length > 0}
								<span class="ml-auto text-xs text-[var(--text-muted)] font-mono">
									{job.fires.length} fires
								</span>
							{/if}
						</div>
						<div
							class="text-xs text-[var(--text-secondary)] truncate"
							title={job.prompt}
						>
							{job.prompt}
						</div>
						<div class="flex items-center gap-2">
							<div
								class="h-1 flex-1 rounded-full bg-[var(--bg-muted)] overflow-hidden"
							>
								<div
									class="h-full rounded-full transition-all"
									style:width="{ttlProgress(job.created_at, job.ttl_expires_at)}%"
									style:background={expired ? 'var(--warning)' : 'var(--status-active)'}
								></div>
							</div>
							<span class="text-xs text-[var(--text-muted)] font-mono shrink-0">
								7d TTL · {ttlRemaining(job.ttl_expires_at)}
							</span>
						</div>
					</button>

					{#if expandedId === job.id}
						<div
							class="border-t border-[var(--border)] p-4 space-y-3 bg-[var(--bg-base)]"
						>
							<div>
								<div class="text-xs uppercase tracking-wide text-[var(--text-muted)] mb-1">
									Prompt
								</div>
								<pre
									class="font-mono text-xs text-[var(--text-primary)] bg-[var(--bg-subtle)] p-3 rounded overflow-x-auto m-0 whitespace-pre-wrap break-words"
								>{job.prompt}</pre>
							</div>
							<div class="grid grid-cols-2 gap-3 text-xs">
								<div>
									<span class="text-[var(--text-muted)]">Created:</span>
									<span class="font-mono text-[var(--text-primary)]">{job.created_at}</span>
								</div>
								<div>
									<span class="text-[var(--text-muted)]">TTL expires:</span>
									<span class="font-mono text-[var(--text-primary)]">{job.ttl_expires_at}</span>
								</div>
								<div>
									<span class="text-[var(--text-muted)]">Recurring:</span>
									<span class="font-mono text-[var(--text-primary)]">
										{job.recurring ? 'yes' : 'no'}
									</span>
								</div>
								<div>
									<span class="text-[var(--text-muted)]">tool_use_id:</span>
									<span class="font-mono text-[var(--text-primary)] truncate">
										{job.tool_use_id}
									</span>
								</div>
							</div>
							{#if job.fires && job.fires.length > 0}
								<div>
									<div class="text-xs uppercase tracking-wide text-[var(--text-muted)] mb-1">
										Inferred fires ({job.fires.length})
									</div>
									<ul class="space-y-1">
										{#each job.fires as fire}
											<li
												class="flex items-center gap-3 text-xs font-mono text-[var(--text-secondary)] py-1"
											>
												<span class="text-[var(--text-muted)]">{fire.fired_at}</span>
												<span class="text-[var(--text-muted)]">
													conf {fire.inference_confidence.toFixed(2)}
												</span>
												{#if fire.outcome_excerpt}
													<span class="truncate text-[var(--text-primary)]">
														{fire.outcome_excerpt}
													</span>
												{/if}
											</li>
										{/each}
									</ul>
								</div>
							{/if}
						</div>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}
</div>
