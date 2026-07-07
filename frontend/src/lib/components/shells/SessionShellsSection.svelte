<script lang="ts">
	import { onMount } from 'svelte';
	import { Activity, Play, X, Square, Loader2 } from 'lucide-svelte';
	import { API_BASE } from '$lib/config';
	import type {
		BackgroundShell,
		ShellsListResponse
	} from '$lib/api-types';

	interface Props {
		sessionUuid: string;
	}
	let { sessionUuid }: Props = $props();

	let loading = $state(true);
	let error = $state<string | null>(null);
	let shells = $state<BackgroundShell[]>([]);
	let expandedId = $state<number | null>(null);

	onMount(async () => {
		try {
			const res = await fetch(`${API_BASE}/sessions/${sessionUuid}/shells?include_polls=true`);
			if (!res.ok) throw new Error(`API ${res.status}`);
			const data = (await res.json()) as ShellsListResponse;
			shells = data.shells ?? [];
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			loading = false;
		}
	});

	function formatDuration(start: string, end: string | null): string {
		const s = new Date(start).getTime();
		const e = end ? new Date(end).getTime() : Date.now();
		const seconds = Math.max(0, Math.round((e - s) / 1000));
		if (seconds < 60) return `${seconds}s`;
		if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
		return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`;
	}

	function formatBytes(n: number): string {
		if (n < 1024) return `${n} B`;
		if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
		return `${(n / (1024 * 1024)).toFixed(1)} MB`;
	}
</script>

<div class="space-y-4">
	<div class="flex items-baseline justify-between gap-4">
		<div>
			<h2 class="text-lg font-semibold text-[var(--text-primary)] m-0">Background shells</h2>
			<p class="text-sm text-[var(--text-muted)] m-0">
				Long-running <code class="font-mono text-xs">Bash</code> and
				<code class="font-mono text-xs">Monitor</code> processes spawned in this session.
			</p>
		</div>
		{#if !loading && shells.length > 0}
			<a
				href="/shells?project={shells[0].project_encoded_name ?? ''}"
				class="text-xs text-[var(--text-secondary)] hover:text-[var(--accent)] transition-colors"
			>
				View all in project →
			</a>
		{/if}
	</div>

	{#if loading}
		<div class="flex items-center justify-center py-12 text-[var(--text-muted)]">
			<Loader2 size={20} class="animate-spin" />
		</div>
	{:else if error}
		<div
			class="rounded-lg border border-[var(--error)] bg-[var(--error-subtle)] p-4 text-sm text-[var(--error)]"
		>
			Failed to load shells: {error}
		</div>
	{:else if shells.length === 0}
		<div
			class="rounded-lg border border-dashed border-[var(--border)] p-8 text-center text-sm text-[var(--text-muted)]"
		>
			<Activity size={28} class="mx-auto mb-3 opacity-40" />
			<p class="m-0">No background shells recorded for this session.</p>
			<p class="m-0 mt-1 text-xs">
				They appear here when Claude runs <code class="font-mono">Bash{'{run_in_background:true}'}</code>
				or <code class="font-mono">Monitor</code>.
			</p>
		</div>
	{:else}
		<ul class="space-y-2">
			{#each shells as shell (shell.id)}
				{@const isRunning = shell.terminated_at === null}
				{@const isMonitor = shell.tool_name === 'Monitor'}
				{@const isKilled = shell.terminated_by === 'kill'}
				{@const statusColor = isRunning
					? 'var(--status-active)'
					: isKilled
						? 'var(--error)'
						: shell.terminated_by === 'natural'
							? 'var(--status-done)'
							: 'var(--text-muted)'}
				<li
					class="rounded-lg border border-[var(--border)] hover:border-[var(--border-hover)] transition-colors overflow-hidden"
					style:background={isMonitor ? 'var(--info-subtle)' : 'var(--bg-subtle)'}
				>
					<button
						type="button"
						class="w-full text-left p-3 flex items-center gap-3 hover:bg-[var(--bg-muted)] transition-colors"
						onclick={() => (expandedId = expandedId === shell.id ? null : shell.id)}
					>
						<span
							class="inline-block w-2 h-2 rounded-full shrink-0"
							style:background={statusColor}
							aria-hidden="true"
						></span>
						<code
							class="font-mono text-sm text-[var(--text-primary)] shrink-0 min-w-[8ch]"
						>
							{shell.shell_id ?? '—'}
						</code>
						<span
							class="text-xs uppercase tracking-wide font-medium shrink-0"
							style:color={statusColor}
						>
							{#if isRunning}
								<Play size={11} class="inline" /> running
							{:else if isKilled}
								<X size={11} class="inline" /> killed
							{:else}
								<Square size={11} class="inline" /> {shell.terminated_by}
							{/if}
						</span>
						<span
							class="text-xs text-[var(--text-muted)] font-mono truncate flex-1"
							title={shell.command}
						>
							{shell.command}
						</span>
						<span class="text-xs text-[var(--text-muted)] shrink-0 font-mono">
							{formatDuration(shell.spawned_at, shell.terminated_at)}
							{#if shell.poll_count > 0}
								· {shell.poll_count} polls
							{/if}
						</span>
					</button>

					{#if expandedId === shell.id}
						<div
							class="border-t border-[var(--border)] p-4 space-y-3 bg-[var(--bg-base)]"
						>
							<div>
								<div class="text-xs uppercase tracking-wide text-[var(--text-muted)] mb-1">
									Command
								</div>
								<pre
									class="font-mono text-xs text-[var(--text-primary)] bg-[var(--bg-subtle)] p-3 rounded overflow-x-auto m-0 whitespace-pre-wrap break-all"
								>{shell.command}{shell.command_truncated ? '\n…(truncated)' : ''}</pre>
							</div>
							<div class="grid grid-cols-2 gap-3 text-xs">
								<div>
									<span class="text-[var(--text-muted)]">Spawned:</span>
									<span class="font-mono text-[var(--text-primary)]">
										{shell.spawned_at}
									</span>
								</div>
								{#if shell.terminated_at}
									<div>
										<span class="text-[var(--text-muted)]">Ended:</span>
										<span class="font-mono text-[var(--text-primary)]">
											{shell.terminated_at}
										</span>
									</div>
								{/if}
								<div>
									<span class="text-[var(--text-muted)]">Total output:</span>
									<span class="font-mono text-[var(--text-primary)]">
										{formatBytes(shell.total_output_bytes)}
									</span>
								</div>
								<div>
									<span class="text-[var(--text-muted)]">Tool:</span>
									<span class="font-mono text-[var(--text-primary)]">{shell.tool_name}</span>
								</div>
							</div>
							{#if shell.polls && shell.polls.length > 0}
								<div>
									<div class="text-xs uppercase tracking-wide text-[var(--text-muted)] mb-1">
										Latest poll output
									</div>
									<pre
										class="font-mono text-xs text-[var(--text-secondary)] bg-[var(--bg-subtle)] p-3 rounded overflow-x-auto m-0 max-h-40 whitespace-pre-wrap break-all"
									>{shell.polls[shell.polls.length - 1].output_excerpt ?? '(empty)'}</pre>
								</div>
							{/if}
						</div>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}
</div>
