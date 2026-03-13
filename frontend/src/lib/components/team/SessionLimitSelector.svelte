<script lang="ts">
	import type { SyncSessionLimit } from '$lib/api-types';
	import { API_BASE } from '$lib/config';

	let {
		teamName = '',
		currentLimit = 'all' as SyncSessionLimit
	}: { teamName: string; currentLimit: SyncSessionLimit } = $props();

	let selected = $state<SyncSessionLimit>('all');
	$effect(() => { selected = currentLimit; });
	let saving = $state(false);

	const OPTIONS: { value: SyncSessionLimit; label: string }[] = [
		{ value: 'all', label: 'All' },
		{ value: 'recent_100', label: 'Recent 100' },
		{ value: 'recent_10', label: 'Recent 10' }
	];

	async function updateLimit(value: SyncSessionLimit) {
		if (value === selected) return;
		saving = true;
		try {
			const res = await fetch(
				`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/settings`,
				{
					method: 'PATCH',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ sync_session_limit: value })
				}
			);
			if (res.ok) {
				selected = value;
			}
		} finally {
			saving = false;
		}
	}
</script>

<div class="flex items-center gap-3">
	<span class="text-xs text-[var(--text-muted)]">Sessions to sync:</span>
	<div
		class="inline-flex rounded-md border border-[var(--border)] bg-[var(--bg-subtle)] p-0.5"
	>
		{#each OPTIONS as opt}
			<button
				class="rounded px-2.5 py-1 text-xs transition-colors {selected === opt.value
					? 'bg-[var(--accent)] text-white'
					: 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'}"
				onclick={() => updateLimit(opt.value)}
				disabled={saving}
			>
				{opt.label}
			</button>
		{/each}
	</div>
</div>
