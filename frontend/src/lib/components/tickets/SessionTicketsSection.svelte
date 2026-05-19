<script lang="ts">
	import type { CreateLinkResponse, SessionTicketRow } from '$lib/api-types';
	import { API_BASE } from '$lib/config';
	import { Ticket as TicketIcon, Undo2, Plus } from 'lucide-svelte';
	import TicketBadge from './TicketBadge.svelte';
	import TicketLinkInput from './TicketLinkInput.svelte';
	import { onDestroy } from 'svelte';

	interface Props {
		sessionUuid: string;
		sessionSlug?: string | null;
		/** Initial tickets fetched server-side. Component holds local state from here. */
		initial?: SessionTicketRow[];
	}

	let { sessionUuid, sessionSlug, initial = [] }: Props = $props();

	// Seed once at construction. Route changes unmount the component so we don't
	// need to react to `initial` changing.
	let tickets = $state<SessionTicketRow[]>($state.snapshot(initial));

	// Undo toast state — keyed by linkId so we never overlap.
	type PendingUndo = {
		ticket: SessionTicketRow;
		expiresAt: number;
		timeoutId: ReturnType<typeof setTimeout>;
	};
	let pending = $state<PendingUndo | null>(null);
	const UNDO_MS = 5000;
	let tick = $state(0);
	let countdownInterval: ReturnType<typeof setInterval> | null = null;

	function startCountdown() {
		if (countdownInterval) return;
		countdownInterval = setInterval(() => {
			tick++;
			if (!pending || pending.expiresAt <= Date.now()) {
				stopCountdown();
			}
		}, 250);
	}
	function stopCountdown() {
		if (countdownInterval) clearInterval(countdownInterval);
		countdownInterval = null;
	}
	onDestroy(stopCountdown);

	let secondsLeft = $derived.by(() => {
		// reference tick so this recomputes
		void tick;
		if (!pending) return 0;
		return Math.max(0, Math.ceil((pending.expiresAt - Date.now()) / 1000));
	});

	function handleCreated(resp: CreateLinkResponse) {
		const next: SessionTicketRow = {
			...resp.ticket,
			link_id: resp.link.id,
			link_source: resp.link.link_source,
			linked_at: resp.link.linked_at,
			session_slug: resp.link.session_slug
		};
		const idx = tickets.findIndex((t) => t.id === resp.ticket.id);
		if (idx >= 0) tickets[idx] = next;
		else tickets = [next, ...tickets];
	}

	function requestUnlink(ticket: SessionTicketRow) {
		// Optimistic remove
		tickets = tickets.filter((t) => t.id !== ticket.id);

		// If there's already a pending undo, commit it immediately (we only show one toast)
		if (pending) {
			clearTimeout(pending.timeoutId);
			void commitUnlink(pending.ticket);
		}

		const timeoutId = setTimeout(() => {
			void commitUnlink(ticket);
			pending = null;
			stopCountdown();
		}, UNDO_MS);

		pending = { ticket, expiresAt: Date.now() + UNDO_MS, timeoutId };
		startCountdown();
	}

	function undoUnlink() {
		if (!pending) return;
		clearTimeout(pending.timeoutId);
		// Restore the ticket at the top (most recent linked-at)
		tickets = [pending.ticket, ...tickets];
		pending = null;
		stopCountdown();
	}

	async function commitUnlink(ticket: SessionTicketRow) {
		try {
			const res = await fetch(`${API_BASE}/sessions/${sessionUuid}/tickets/${ticket.id}`, {
				method: 'DELETE'
			});
			if (!res.ok) {
				// Restore on failure
				tickets = [ticket, ...tickets];
			}
		} catch {
			tickets = [ticket, ...tickets];
		}
	}
</script>

<section
	class="flex flex-col gap-2.5 px-4 py-3 rounded-lg border border-[var(--border)] bg-[var(--bg-base)]"
	aria-labelledby="tickets-heading"
>
	<header class="flex items-center justify-between gap-2">
		<div class="flex items-center gap-2">
			<TicketIcon size={13} class="text-[var(--text-muted)]" />
			<span
				id="tickets-heading"
				class="font-mono text-[12px] text-[var(--accent)]"
			>
				$ tickets
			</span>
			<span class="font-mono text-[11px] text-[var(--text-faint)]">
				[{tickets.length} linked]
			</span>
		</div>
	</header>

	{#if tickets.length > 0}
		<ul class="flex flex-wrap gap-1.5 m-0 p-0 list-none">
			{#each tickets as ticket (ticket.id)}
				<li>
					<TicketBadge
						{ticket}
						variant="pill"
						showStatus={false}
						onRemove={() => requestUnlink(ticket)}
					/>
				</li>
			{/each}
		</ul>
	{/if}

	{#if pending}
		<div
			class="inline-flex items-center gap-2 px-2.5 py-1 rounded-full bg-[var(--bg-muted)] border border-dashed border-[var(--border)] text-[11px] text-[var(--text-muted)] self-start"
			role="status"
			aria-live="polite"
		>
			<Undo2 size={11} />
			<span>
				Unlinked
				<code class="font-mono">{pending.ticket.external_key}</code>
			</span>
			<span class="text-[var(--text-faint)]">· undo in {secondsLeft}s</span>
			<button
				type="button"
				onclick={undoUnlink}
				class="text-[var(--accent)] hover:underline font-semibold focus-ring"
			>
				Undo
			</button>
		</div>
	{/if}

	{#if tickets.length === 0 && !pending}
		<p class="text-[11px] text-[var(--text-muted)] m-0 inline-flex items-center gap-1.5">
			<Plus size={10} />
			Paste a URL, key, or
			<code class="font-mono px-1 py-px rounded bg-[var(--bg-muted)] text-[var(--text-secondary)]">owner/repo#N</code>
			below to link this session.
		</p>
	{/if}

	<TicketLinkInput {sessionUuid} {sessionSlug} onCreated={handleCreated} />
</section>
