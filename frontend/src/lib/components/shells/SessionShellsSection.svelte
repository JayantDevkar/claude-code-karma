<script lang="ts">
	import { onMount } from 'svelte';
	import { Activity, Loader2 } from 'lucide-svelte';
	import { API_BASE } from '$lib/config';
	import type {
		BackgroundShell,
		ShellsListResponse
	} from '$lib/api-types';

	interface Props {
		sessionUuid: string;
		onLoaded?: (count: number) => void;
	}
	let { sessionUuid, onLoaded }: Props = $props();

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
			onLoaded?.(shells.length);
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		} finally {
			loading = false;
		}
	});

	function statusColor(shell: BackgroundShell): string {
		if (shell.terminated_at === null) return 'var(--success)';
		const r = shell.terminated_by ?? 'session_end';
		if (r === 'kill') return 'var(--error)';
		if (r === 'natural') return 'var(--info)';
		if (r === 'timeout') return 'var(--warning)';
		return 'var(--text-faint)';
	}

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

<div class="flex flex-col gap-2">

	<!-- Header -->
	<div class="flex items-center justify-between">
		<p class="text-[10px] uppercase tracking-wide font-medium text-[var(--text-muted)]">Background shells</p>
		{#if !loading && shells.length > 0}
			<a href="/shells?project={shells[0].project_encoded_name ?? ''}" class="text-[10px] text-[var(--text-muted)] hover:text-[var(--accent)] transition-colors">
				View all →
			</a>
		{/if}
	</div>

	{#if loading}
		<div class="flex justify-center py-6 text-[var(--text-muted)]">
			<Loader2 size={14} class="animate-spin" />
		</div>
	{:else if error}
		<p class="text-xs text-[var(--error)]">Failed to load: {error}</p>
	{:else if shells.length === 0}
		<div class="rounded-lg border border-dashed border-[var(--border)] py-6 px-4 text-center">
			<Activity size={18} class="mx-auto mb-1.5 opacity-30" />
			<p class="text-xs text-[var(--text-muted)] m-0">No background shells in this session.</p>
		</div>
	{:else}
		<div class="flex flex-col gap-2">
			{#each shells as shell (shell.id)}
				{@const isRunning = shell.terminated_at === null}
				{@const color = statusColor(shell)}
				<div class="rounded-lg border border-[var(--border)]/60 overflow-hidden bg-[var(--bg-base)]">
					<button
						type="button"
						class="w-full text-left px-2.5 py-2 flex items-center gap-2 hover:bg-[var(--bg-subtle)] transition-colors"
						onclick={() => (expandedId = expandedId === shell.id ? null : shell.id)}
					>
						<span
							class="shrink-0 w-1.5 h-1.5 rounded-full {isRunning ? 'animate-pulse' : ''}"
							style:background={color}
						></span>
						<code class="font-mono text-[11px] text-[var(--text-primary)] shrink-0">{shell.shell_id ?? '—'}</code>
						<span class="font-mono text-[10px] text-[var(--text-muted)] truncate flex-1" title={shell.command}>{shell.command}</span>
						<span class="shrink-0 font-mono text-[10px] text-[var(--text-muted)]">{formatDuration(shell.spawned_at, shell.terminated_at)}</span>
					</button>

					{#if expandedId === shell.id}
						<div class="border-t border-[var(--border)]/40 px-2.5 py-2 space-y-1.5 bg-[var(--bg-subtle)]">
							<pre class="font-mono text-[10px] text-[var(--text-primary)] bg-[var(--bg-muted)] px-2 py-1.5 rounded overflow-x-auto m-0 whitespace-pre-wrap break-all">{shell.command}{shell.command_truncated ? '\n…(truncated)' : ''}</pre>
							<div class="grid grid-cols-2 gap-x-3 gap-y-1 text-[10px]">
								<div class="text-[var(--text-muted)]">Spawned <span class="font-mono text-[var(--text-secondary)]">{new Date(shell.spawned_at).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}</span></div>
								{#if shell.terminated_at}<div class="text-[var(--text-muted)]">Ended <span class="font-mono text-[var(--text-secondary)]">{new Date(shell.terminated_at).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}</span></div>{/if}
								<div class="text-[var(--text-muted)]">Output <span class="font-mono text-[var(--text-secondary)]">{formatBytes(shell.total_output_bytes)}</span></div>
								{#if shell.poll_count > 0}<div class="text-[var(--text-muted)]">Polls <span class="font-mono text-[var(--text-secondary)]">{shell.poll_count}</span></div>{/if}
							</div>
							{#if shell.polls && shell.polls.length > 0}
								<pre class="font-mono text-[10px] text-[var(--text-secondary)] bg-[var(--bg-muted)] px-2 py-1.5 rounded overflow-x-auto m-0 max-h-32 whitespace-pre-wrap break-all">{shell.polls[shell.polls.length - 1].output_excerpt ?? '(empty)'}</pre>
							{/if}
						</div>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</div>
