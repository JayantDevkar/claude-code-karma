<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { RefreshCw } from 'lucide-svelte';
	import type { SyncDetect, SyncStatusResponse } from '$lib/api-types';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import SetupWizard from '$lib/components/sync/SetupWizard.svelte';
	import OverviewTab from '$lib/components/sync/OverviewTab.svelte';
	import { POLLING_INTERVALS, API_BASE } from '$lib/config';

	let { data } = $props();

	let syncDetect = $state<SyncDetect | null>(null);
	let syncStatus = $state<SyncStatusResponse | null>(null);

	// Sync from server data on load/invalidation
	$effect(() => { syncDetect = data.detect ?? null; });
	$effect(() => { syncStatus = data.status ?? null; });

	// Auto-select first team for the overview dashboard
	let activeTeamName = $derived.by(() => {
		if (!syncStatus?.teams) return '';
		const names = Object.keys(syncStatus.teams);
		return names.length > 0 ? names[0] : '';
	});

	let pollInterval: ReturnType<typeof setInterval> | null = null;
	let isFetching = $state(false);
	let abortController: AbortController | null = null;
	let lastUpdated = $state<Date | null>(null);
	let secondsSinceUpdate = $state(0);
	let clockInterval: ReturnType<typeof setInterval> | null = null;

	async function refreshData() {
		if (isFetching) return;
		isFetching = true;
		abortController?.abort();
		abortController = new AbortController();
		try {
			const [detectRes, statusRes] = await Promise.all([
				fetch(`${API_BASE}/sync/detect`, { signal: abortController.signal }),
				fetch(`${API_BASE}/sync/status`, { signal: abortController.signal })
			]);
			if (detectRes.ok) syncDetect = await detectRes.json();
			if (statusRes.ok) syncStatus = await statusRes.json();
			lastUpdated = new Date();
			secondsSinceUpdate = 0;
		} catch (e) {
			if (e instanceof DOMException && e.name === 'AbortError') return;
		} finally {
			isFetching = false;
		}
	}

	onMount(() => {
		lastUpdated = new Date();
		pollInterval = setInterval(refreshData, POLLING_INTERVALS.SYNC_STATUS);
		clockInterval = setInterval(() => {
			if (lastUpdated) {
				secondsSinceUpdate = Math.floor((Date.now() - lastUpdated.getTime()) / 1000);
			}
		}, 1000);
	});

	onDestroy(() => {
		if (pollInterval) clearInterval(pollInterval);
		if (clockInterval) clearInterval(clockInterval);
		abortController?.abort();
	});
</script>

<div class="max-w-4xl mx-auto pb-12">
	<PageHeader
		title="Sync"
		icon={RefreshCw}
		iconColor="--nav-green"
		breadcrumbs={[{ label: 'Dashboard', href: '/' }, { label: 'Sync' }]}
	>
		{#snippet headerRight()}
			{#if syncStatus?.configured}
				<div class="flex items-center gap-3">
					{#if lastUpdated}
						<span class="text-xs text-[var(--text-muted)]">
							Last updated: {secondsSinceUpdate}s ago
						</span>
					{/if}
					<button
						onclick={refreshData}
						disabled={isFetching}
						class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
					>
						<RefreshCw size={12} class={isFetching ? 'animate-spin' : ''} />
						Refresh
					</button>
				</div>
			{/if}
		{/snippet}
	</PageHeader>

	{#if !syncStatus?.configured}
		<SetupWizard bind:detect={syncDetect} bind:status={syncStatus} ondone={refreshData} />
	{:else}
		<OverviewTab
			detect={syncDetect}
			status={syncStatus}
			active={true}
			teamName={activeTeamName}
			onteamchange={refreshData}
			initialWatchStatus={data.watchStatus}
			initialPending={data.pending}
		/>
	{/if}
</div>
