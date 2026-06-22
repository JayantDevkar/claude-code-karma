<script lang="ts">
	import type { CreateLinkResponse, SessionTicketRow } from '$lib/api-types';
	import { API_BASE } from '$lib/config';
	import { ExternalLink, X, Undo2 } from 'lucide-svelte';
	import { normalizeStatus, statusColorVar, PROVIDER_META } from '$lib/ticket-helpers';
	import TicketLinkInput from './TicketLinkInput.svelte';
	import { onDestroy } from 'svelte';

	interface Props {
		sessionUuid: string;
		sessionSlug?: string | null;
		initial?: SessionTicketRow[];
	}

	let { sessionUuid, sessionSlug, initial = [] }: Props = $props();

	let tickets = $state<SessionTicketRow[]>($state.snapshot(initial));

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
			if (!pending || pending.expiresAt <= Date.now()) stopCountdown();
		}, 250);
	}
	function stopCountdown() {
		if (countdownInterval) clearInterval(countdownInterval);
		countdownInterval = null;
	}
	onDestroy(stopCountdown);

	let secondsLeft = $derived.by(() => {
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
		tickets = tickets.filter((t) => t.id !== ticket.id);
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
		tickets = [pending.ticket, ...tickets];
		pending = null;
		stopCountdown();
	}

	async function commitUnlink(ticket: SessionTicketRow) {
		try {
			const res = await fetch(`${API_BASE}/sessions/${sessionUuid}/tickets/${ticket.id}`, { method: 'DELETE' });
			if (!res.ok) tickets = [ticket, ...tickets];
		} catch {
			tickets = [ticket, ...tickets];
		}
	}
</script>

<div class="flex flex-col gap-2.5">
	<span class="text-[10px] uppercase tracking-wide font-medium text-[var(--text-muted)]">
		{tickets.length} ticket{tickets.length !== 1 ? 's' : ''} linked
	</span>

	<!-- Ticket list -->
	{#if tickets.length > 0}
		<div class="flex flex-col gap-2">
			{#each tickets as ticket (ticket.id)}
				{@const norm = normalizeStatus(ticket.status)}
				{@const meta = PROVIDER_META[ticket.provider]}
				<div class="rounded-lg border border-[var(--border)] bg-[var(--bg-base)] overflow-hidden">
					<!-- Card header: provider chip + key + unlink -->
					<div class="flex items-center gap-2 px-3 pt-3 pb-2">
						<!-- Provider badge -->
						<span
							class="shrink-0 inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide"
							style="background: var({meta?.subtleVar ?? '--bg-muted'}); color: var({meta?.colorVar ?? '--text-muted'});"
						>{meta?.short ?? '??'}</span>

						<!-- Key link -->
						<a
							href={ticket.url}
							target="_blank"
							rel="noopener noreferrer"
							class="flex-1 min-w-0 font-mono text-xs font-semibold text-[var(--accent)] hover:underline inline-flex items-center gap-1"
						>
							<span class="truncate">{ticket.external_key}</span>
							<ExternalLink size={10} class="shrink-0 opacity-60" />
						</a>

						<!-- Unlink -->
						<button
							type="button"
							onclick={() => requestUnlink(ticket)}
							class="shrink-0 p-1 rounded text-[var(--text-faint)] hover:text-[var(--error)] hover:bg-[var(--error-subtle)] transition-colors"
							title="Unlink"
						>
							<X size={13} />
						</button>
					</div>

					<!-- Title -->
					{#if ticket.title}
						<p class="px-3 pb-2 text-xs text-[var(--text-primary)] leading-relaxed line-clamp-2 m-0">{ticket.title}</p>
					{/if}

					<!-- Status footer -->
					{#if norm.verbatim}
						<div class="flex items-center gap-1.5 px-3 py-2 border-t border-[var(--border)]/60">
							<span class="w-2 h-2 rounded-full shrink-0" style="background: var({statusColorVar(norm.key)})"></span>
							<span class="text-[11px] font-medium text-[var(--text-secondary)] uppercase tracking-wide">{norm.verbatim}</span>
						</div>
					{/if}
				</div>
			{/each}
		</div>
	{/if}

	<!-- Undo toast -->
	{#if pending}
		<div class="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-[var(--bg-muted)] border border-dashed border-[var(--border)] text-[11px] text-[var(--text-muted)]">
			<Undo2 size={11} class="shrink-0" />
			<span class="flex-1 min-w-0 truncate">Unlinked <code class="font-mono">{pending.ticket.external_key}</code></span>
			<span class="shrink-0 text-[var(--text-faint)]">{secondsLeft}s</span>
			<button type="button" onclick={undoUnlink} class="shrink-0 text-[var(--accent)] hover:underline font-semibold">Undo</button>
		</div>
	{/if}

	<!-- Link input -->
	<TicketLinkInput {sessionUuid} {sessionSlug} onCreated={handleCreated} />
</div>
