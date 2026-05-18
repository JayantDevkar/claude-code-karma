<script lang="ts">
	import type { CreateLinkResponse, SessionTicketRow } from '$lib/api-types';
	import { API_BASE } from '$lib/config';
	import { Ticket as TicketIcon } from 'lucide-svelte';
	import TicketBadge from './TicketBadge.svelte';
	import TicketLinkInput from './TicketLinkInput.svelte';

	interface Props {
		sessionUuid: string;
		sessionSlug?: string | null;
		/** Initial tickets fetched server-side. Component holds local state from here. */
		initial?: SessionTicketRow[];
	}

	let { sessionUuid, sessionSlug, initial = [] }: Props = $props();

	// Snapshot the initial seed so the warning about reactive prop capture
	// is silenced. SvelteKit unmounts the component across route changes,
	// so seeding once at construction is exactly the desired behavior.
	let tickets = $state<SessionTicketRow[]>($state.snapshot(initial));
	let removingId = $state<number | null>(null);

	function handleCreated(resp: CreateLinkResponse) {
		// If we already have this ticket linked, the API returned the existing row.
		const idx = tickets.findIndex((t) => t.id === resp.ticket.id);
		if (idx >= 0) {
			tickets[idx] = {
				...resp.ticket,
				link_id: resp.link.id,
				link_source: resp.link.link_source,
				linked_at: resp.link.linked_at,
				session_slug: resp.link.session_slug
			};
		} else {
			tickets = [
				{
					...resp.ticket,
					link_id: resp.link.id,
					link_source: resp.link.link_source,
					linked_at: resp.link.linked_at,
					session_slug: resp.link.session_slug
				},
				...tickets
			];
		}
	}

	async function unlink(ticketId: number) {
		if (removingId !== null) return;
		removingId = ticketId;
		try {
			const res = await fetch(
				`${API_BASE}/sessions/${sessionUuid}/tickets/${ticketId}`,
				{ method: 'DELETE' }
			);
			if (res.ok) {
				tickets = tickets.filter((t) => t.id !== ticketId);
			}
		} finally {
			removingId = null;
		}
	}
</script>

<section
	class="flex flex-col gap-3 p-4 rounded-lg border border-[var(--border)] bg-[var(--bg-base)]"
	aria-labelledby="tickets-heading"
>
	<header class="flex items-center gap-2">
		<TicketIcon size={16} class="text-[var(--text-muted)]" />
		<h2
			id="tickets-heading"
			class="text-sm font-semibold text-[var(--text-primary)] tracking-wide uppercase"
		>
			Tickets
		</h2>
		<span class="text-xs text-[var(--text-muted)]">
			({tickets.length})
		</span>
	</header>

	{#if tickets.length > 0}
		<ul class="flex flex-wrap gap-2 m-0 p-0 list-none">
			{#each tickets as ticket (ticket.id)}
				<li>
					<TicketBadge
						{ticket}
						variant="pill"
						onRemove={() => unlink(ticket.id)}
					/>
				</li>
			{/each}
		</ul>
	{:else}
		<p class="text-xs text-[var(--text-muted)] m-0">
			No tickets linked yet. Paste a URL or ref below to link this session to a ticket.
		</p>
	{/if}

	<TicketLinkInput {sessionUuid} {sessionSlug} onCreated={handleCreated} />
</section>
