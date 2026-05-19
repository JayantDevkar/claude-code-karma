<script lang="ts">
	import type { TicketListItem } from '$lib/api-types';
	import { API_BASE } from '$lib/config';
	import { Ticket as TicketIcon, ArrowRight } from 'lucide-svelte';
	import TicketBadge from './TicketBadge.svelte';

	interface Props {
		projectEncodedName: string;
	}

	let { projectEncodedName }: Props = $props();

	let tickets = $state<TicketListItem[] | null>(null);
	let error = $state<string | null>(null);

	$effect(() => {
		const encoded = projectEncodedName;
		if (!encoded) return;

		let cancelled = false;
		(async () => {
			try {
				const res = await fetch(
					`${API_BASE}/tickets?project=${encodeURIComponent(encoded)}`
				);
				if (cancelled) return;
				if (!res.ok) {
					error = `HTTP ${res.status}`;
					return;
				}
				const data = (await res.json()) as TicketListItem[];
				if (!cancelled) tickets = data;
			} catch (e) {
				if (!cancelled) error = e instanceof Error ? e.message : String(e);
			}
		})();
		return () => {
			cancelled = true;
		};
	});

	const PREVIEW_LIMIT = 8;
	let preview = $derived(tickets ? tickets.slice(0, PREVIEW_LIMIT) : []);
	let overflow = $derived(tickets ? Math.max(0, tickets.length - PREVIEW_LIMIT) : 0);
	let viewAllHref = $derived(`/tickets?project=${encodeURIComponent(projectEncodedName)}`);
</script>

<section
	class="flex flex-col gap-3 p-4 rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)]"
	aria-labelledby="project-tickets-heading"
>
	<header class="flex items-center justify-between gap-3">
		<div class="flex items-center gap-2">
			<TicketIcon size={14} class="text-[var(--text-muted)]" />
			<h2
				id="project-tickets-heading"
				class="text-sm font-semibold text-[var(--text-primary)] m-0"
			>
				Linked tickets
			</h2>
			{#if tickets}
				<span class="text-xs text-[var(--text-muted)] tabular-nums">
					{tickets.length}
				</span>
			{/if}
		</div>
		{#if tickets && tickets.length > 0}
			<a
				href={viewAllHref}
				class="inline-flex items-center gap-1 text-xs text-[var(--text-secondary)] hover:text-[var(--accent)]"
			>
				View all
				<ArrowRight size={12} />
			</a>
		{/if}
	</header>

	{#if error}
		<p class="text-xs text-[var(--error)] m-0">Couldn't load tickets: {error}</p>
	{:else if tickets === null}
		<p class="text-xs text-[var(--text-muted)] m-0">Loading…</p>
	{:else if tickets.length === 0}
		<p class="text-xs text-[var(--text-muted)] m-0">
			No tickets linked to sessions in this project yet. Open a session and paste a ticket URL
			to link one.
		</p>
	{:else}
		<ul class="flex flex-wrap gap-2 m-0 p-0 list-none">
			{#each preview as t (t.id)}
				<li>
					<a
						href="/tickets/{t.provider}/{encodeURIComponent(t.external_key)}"
						class="block"
					>
						<TicketBadge ticket={t} variant="pill" />
					</a>
				</li>
			{/each}
			{#if overflow > 0}
				<li>
					<a
						href={viewAllHref}
						class="inline-flex items-center px-2 py-0.5 rounded-full text-xs text-[var(--text-secondary)] hover:text-[var(--accent)] bg-[var(--bg-muted)] border border-[var(--border)]"
					>
						+{overflow} more
					</a>
				</li>
			{/if}
		</ul>
	{/if}
</section>
