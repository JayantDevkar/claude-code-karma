<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import { TicketBadge } from '$lib/components/tickets';
	import type { TicketProvider } from '$lib/api-types';
	import { Search, Filter, Ticket as TicketIcon } from 'lucide-svelte';

	let { data } = $props();

	let q = $state(data.filters.q);
	let provider = $state<TicketProvider | ''>(
		(data.filters.provider as TicketProvider | '') ?? ''
	);

	function navigate(opts: { q?: string; provider?: string; project?: string }) {
		const params = new URLSearchParams($page.url.searchParams);
		for (const [k, v] of Object.entries(opts)) {
			if (v) params.set(k, v);
			else params.delete(k);
		}
		goto(`/tickets?${params.toString()}`);
	}

	function submitSearch(e: Event) {
		e.preventDefault();
		navigate({ q });
	}

	function clearProject() {
		navigate({ project: '' });
	}

	function formatRelative(iso: string | null): string {
		if (!iso) return '—';
		const d = new Date(iso);
		const diff = Date.now() - d.getTime();
		const mins = Math.floor(diff / 60000);
		if (mins < 1) return 'just now';
		if (mins < 60) return `${mins}m ago`;
		const hrs = Math.floor(mins / 60);
		if (hrs < 24) return `${hrs}h ago`;
		const days = Math.floor(hrs / 24);
		if (days < 30) return `${days}d ago`;
		return d.toLocaleDateString();
	}
</script>

<svelte:head>
	<title>Tickets · Claude Karma</title>
</svelte:head>

<div class="max-w-6xl mx-auto p-6 flex flex-col gap-6">
	<header class="flex items-center gap-3">
		<TicketIcon size={24} class="text-[var(--accent)]" />
		<h1 class="text-2xl font-bold text-[var(--text-primary)] m-0">Tickets</h1>
		<span class="text-sm text-[var(--text-muted)]">({data.tickets.length})</span>
	</header>

	<div class="flex flex-wrap items-center gap-3">
		<form onsubmit={submitSearch} class="flex items-center gap-2 flex-1 min-w-[280px]">
			<div class="relative flex-1">
				<Search
					size={16}
					class="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
				/>
				<input
					type="search"
					placeholder="Search by key or title…"
					bind:value={q}
					class="w-full pl-9 pr-3 py-1.5 text-sm rounded-md border border-[var(--border)] bg-[var(--bg-base)]"
				/>
			</div>
		</form>

		<div class="flex items-center gap-2">
			<Filter size={14} class="text-[var(--text-muted)]" />
			<select
				bind:value={provider}
				onchange={() => navigate({ provider })}
				class="px-2 py-1.5 text-sm rounded-md border border-[var(--border)] bg-[var(--bg-base)]"
			>
				<option value="">All providers</option>
				<option value="linear">Linear</option>
				<option value="jira">Jira</option>
				<option value="github">GitHub</option>
			</select>
		</div>
	</div>

	{#if data.filters.project}
		<div
			class="flex items-center gap-2 text-sm px-3 py-2 rounded-md bg-[var(--accent-subtle,#eef2ff)] border border-[var(--border)]"
		>
			<span class="text-[var(--text-secondary)]">Filtered to project:</span>
			<code class="font-mono">{data.filters.project}</code>
			<button
				type="button"
				onclick={clearProject}
				class="ml-auto text-[var(--accent)] hover:underline"
			>
				Clear
			</button>
		</div>
	{/if}

	{#if data.tickets.length === 0}
		<div class="text-center py-12 text-[var(--text-muted)]">
			<TicketIcon size={40} class="mx-auto mb-3 opacity-50" />
			<p class="text-sm">
				No tickets {data.filters.q || data.filters.provider || data.filters.project
					? 'match your filters'
					: 'linked yet'}.
			</p>
			{#if !data.filters.q && !data.filters.provider && !data.filters.project}
				<p class="text-xs mt-1">
					Open a session and paste a ticket URL to link your first one.
				</p>
			{/if}
		</div>
	{:else}
		<div class="overflow-x-auto rounded-lg border border-[var(--border)]">
			<table class="w-full text-sm">
				<thead class="bg-[var(--bg-subtle)] text-left">
					<tr>
						<th class="px-4 py-2 font-semibold text-[var(--text-secondary)]">Ticket</th>
						<th class="px-4 py-2 font-semibold text-[var(--text-secondary)]">Title</th>
						<th class="px-4 py-2 font-semibold text-[var(--text-secondary)]">Status</th>
						<th class="px-4 py-2 font-semibold text-[var(--text-secondary)] text-right">
							Sessions
						</th>
						<th class="px-4 py-2 font-semibold text-[var(--text-secondary)]">Last linked</th>
					</tr>
				</thead>
				<tbody>
					{#each data.tickets as t (t.id)}
						<tr class="border-t border-[var(--border)] hover:bg-[var(--bg-subtle)]">
							<td class="px-4 py-2">
								<a href="/tickets/{t.provider}/{encodeURIComponent(t.external_key)}">
									<TicketBadge ticket={t} variant="inline" />
								</a>
							</td>
							<td class="px-4 py-2 text-[var(--text-primary)] max-w-[40ch] truncate">
								{t.title ?? '—'}
							</td>
							<td class="px-4 py-2 text-[var(--text-secondary)]">{t.status ?? '—'}</td>
							<td class="px-4 py-2 text-right tabular-nums">{t.session_count}</td>
							<td class="px-4 py-2 text-[var(--text-muted)]">
								{formatRelative(t.last_linked_at)}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</div>
