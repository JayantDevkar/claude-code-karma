<script lang="ts">
	import { ArrowLeft, MessagesSquare, Reply, Pin, AlertCircle, Bot, User, Copy, Check } from 'lucide-svelte';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import type { RoomMessage, RoomMessagesResponse } from '$lib/api-types';
	import { API_BASE } from '$lib/config';
	import { onMount } from 'svelte';

	let { data } = $props();

	let detail = $derived(data.detail);
	let room = $derived(detail.room);
	let presence = $derived(detail.presence);
	let decisions = $derived(detail.decisions);

	// Start with inlined messages, page in more if room has more.
	// svelte-ignore state_referenced_locally
	let messages = $state<RoomMessage[]>(detail.messages);
	// svelte-ignore state_referenced_locally
	let total = $state<number>(detail.messages_total);
	let inlined = $derived<number>(detail.messages_inlined);
	let isLoadingMore = $state(false);

	// Highlight target for "scroll-to-pinned-answer" on hover/focus.
	let highlightId = $state<string | null>(null);

	let copiedUrn = $state<string | null>(null);

	async function loadAll() {
		if (messages.length >= total || isLoadingMore) return;
		isLoadingMore = true;
		try {
			// Fetch the rest in one shot (per_page caps at 500 server-side)
			const params = new URLSearchParams({
				page: '1',
				per_page: String(Math.min(total, 500)),
				order: 'asc'
			});
			const res = await fetch(
				`${API_BASE}/rooms/${encodeURIComponent(room.id)}/messages?${params}`
			);
			if (res.ok) {
				const data: RoomMessagesResponse = await res.json();
				messages = data.messages;
			}
		} finally {
			isLoadingMore = false;
		}
	}

	onMount(() => {
		if (total > inlined) loadAll();
	});

	// Decision lookup by answer_id → which decision pins this answer?
	let decisionByAnswer = $derived(
		new Map(decisions.map((d) => [d.answer_id, d]))
	);

	// Quick lookup of message by id for jump-to behavior.
	let messageById = $derived(new Map(messages.map((m) => [m.id, m])));

	function shortId(id: string): string {
		return id.length > 12 ? id.slice(0, 8) + '…' : id;
	}

	function jumpTo(id: string) {
		const el = document.getElementById(`msg-${id}`);
		if (!el) return;
		el.scrollIntoView({ behavior: 'smooth', block: 'center' });
		highlightId = id;
		setTimeout(() => {
			if (highlightId === id) highlightId = null;
		}, 1600);
	}

	async function copyUrn(urn: string) {
		try {
			await navigator.clipboard.writeText(urn);
			copiedUrn = urn;
			setTimeout(() => {
				if (copiedUrn === urn) copiedUrn = null;
			}, 1200);
		} catch {
			// no-op (clipboard may be blocked in some contexts)
		}
	}

	function isIndexerMessage(m: RoomMessage): boolean {
		return m.from_agent_id === '_indexer';
	}

	function bodyAsText(m: RoomMessage): string {
		// type=decision/status are JSON; show summary if present, else raw.
		if (m.type === 'decision' || m.type === 'status') {
			try {
				const parsed = JSON.parse(m.body);
				if (parsed.summary) return parsed.summary;
				if (parsed.reason) return parsed.reason;
				return m.body;
			} catch {
				return m.body;
			}
		}
		return m.body;
	}

	function decisionPinsThis(m: RoomMessage) {
		// For decision messages, what answer does it pin?
		if (m.type !== 'decision') return null;
		try {
			const parsed = JSON.parse(m.body);
			return parsed.pins ?? null;
		} catch {
			return null;
		}
	}

	function statusKind(m: RoomMessage): string | null {
		if (m.type !== 'status') return null;
		try {
			return JSON.parse(m.body).kind ?? null;
		} catch {
			return null;
		}
	}

	function confidenceBadge(c: string | null) {
		if (!c) return null;
		const variant =
			c === 'high' ? 'success' : c === 'medium' ? 'info' : c === 'low' ? 'warning' : 'slate';
		return { label: c, variant: variant as 'success' | 'info' | 'warning' | 'slate' };
	}
</script>

<svelte:head>
	<title>{room.id} · Rooms · Claude Code Karma</title>
</svelte:head>

<div class="max-w-[1200px] mx-auto px-4 md:px-6 py-6 space-y-6">
	<a
		href="/rooms"
		class="inline-flex items-center gap-1 text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
	>
		<ArrowLeft size={12} />
		All rooms
	</a>

	<PageHeader
		title={room.title || room.id}
		icon={MessagesSquare}
		breadcrumbs={[
			{ label: 'Rooms', href: '/rooms' },
			{ label: room.id }
		]}
		metadata={[
			{ text: `${room.message_count} ${room.message_count === 1 ? 'message' : 'messages'}` },
			{ text: `${room.decision_count} ${room.decision_count === 1 ? 'decision' : 'decisions'}` },
			{ text: `${presence.filter((p) => p.left_at === null).length} present` }
		]}
	/>

	<!-- Roster -->
	<Card class="p-4">
		<div class="text-xs font-semibold text-[var(--text-secondary)] uppercase tracking-wider mb-2">
			Participants
		</div>
		<div class="flex flex-wrap gap-2">
			{#each presence as p}
				<div
					class="inline-flex items-center gap-1.5 px-2 py-1 rounded-md text-xs border border-[var(--border)] bg-[var(--bg-subtle)]"
					class:opacity-60={p.left_at !== null}
				>
					{#if p.is_human}
						<User size={12} class="text-[var(--accent)]" />
					{:else}
						<Bot size={12} class="text-[var(--text-secondary)]" />
					{/if}
					<span class="font-mono">{p.agent_id}</span>
					{#if p.left_at !== null}
						<span class="text-[var(--text-muted)]">(left)</span>
					{/if}
				</div>
			{/each}
		</div>
	</Card>

	<!-- Timeline -->
	<div class="space-y-3">
		{#if isLoadingMore && messages.length === inlined}
			<div class="text-center text-xs text-[var(--text-muted)]">Loading messages…</div>
		{/if}

		{#each messages as m (m.id)}
			{@const indexer = isIndexerMessage(m)}
			{@const pinnedAnswerId = decisionPinsThis(m)}
			{@const sk = statusKind(m)}
			{@const conf = confidenceBadge(m.confidence)}
			{@const pinned = decisionByAnswer.get(m.id)}
			<div
				id={`msg-${m.id}`}
				class="rounded-lg border transition-colors"
				class:border-[var(--border)]={highlightId !== m.id}
				class:border-[var(--accent)]={highlightId === m.id}
				class:bg-[var(--bg-subtle)]={!indexer}
				class:bg-transparent={indexer}
				class:opacity-80={indexer}
			>
				<div class="p-4">
					<!-- Header row: from / type / confidence / time -->
					<div class="flex items-center gap-2 flex-wrap text-xs">
						{#if indexer}
							<span
								class="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono uppercase bg-[var(--bg-muted)] text-[var(--text-muted)]"
							>
								indexer
							</span>
						{:else}
							<span
								class="font-mono font-semibold text-[var(--text-primary)]"
								class:italic={indexer}
							>
								{m.from_agent_id}
							</span>
						{/if}

						<Badge
							variant={m.type === 'decision'
								? 'info'
								: m.type === 'answer'
									? 'success'
									: m.type === 'question'
										? 'warning'
										: 'slate'}
						>
							{m.type}
						</Badge>

						{#if conf}
							<Badge variant={conf.variant}>conf: {conf.label}</Badge>
						{/if}

						{#if sk}
							<Badge variant="slate">{sk}</Badge>
						{/if}

						<span class="text-[var(--text-muted)] ml-auto font-mono">
							{new Date(m.created_at).toISOString().slice(11, 19)}Z
						</span>
					</div>

					<!-- Body -->
					<div
						class="mt-2 text-sm whitespace-pre-wrap break-words"
						class:text-[var(--text-secondary)]={indexer}
						class:italic={indexer}
						class:text-[var(--text-primary)]={!indexer}
					>
						{bodyAsText(m)}
					</div>

					<!-- Cross-link badges row -->
					<div class="mt-3 flex flex-wrap gap-2 text-xs">
						{#if m.in_reply_to}
							<button
								type="button"
								onclick={() => jumpTo(m.in_reply_to!)}
								class="inline-flex items-center gap-1 px-2 py-1 rounded-md border border-[var(--border)] hover:border-[var(--accent)] hover:bg-[var(--bg-muted)] transition-colors text-[var(--text-secondary)] font-mono"
								title="Jump to the message this replies to"
							>
								<Reply size={11} />
								in reply to {shortId(m.in_reply_to)}
							</button>
						{/if}

						{#if pinnedAnswerId}
							<button
								type="button"
								onclick={() => jumpTo(pinnedAnswerId)}
								onmouseenter={() => (highlightId = pinnedAnswerId)}
								onmouseleave={() => {
									if (highlightId === pinnedAnswerId) highlightId = null;
								}}
								onfocus={() => (highlightId = pinnedAnswerId)}
								onblur={() => {
									if (highlightId === pinnedAnswerId) highlightId = null;
								}}
								class="inline-flex items-center gap-1 px-2 py-1 rounded-md border border-[var(--accent)]/30 bg-[var(--accent)]/5 hover:bg-[var(--accent)]/10 transition-colors text-[var(--accent)] font-mono"
								title="This decision pins an answer above — hover to highlight, click to scroll"
							>
								<Pin size={11} />
								pins {shortId(pinnedAnswerId)}
							</button>
						{/if}

						{#if pinned}
							<span
								class="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-[var(--accent)]/10 text-[var(--accent)] font-mono"
							>
								<Pin size={11} />
								pinned by decision {shortId(pinned.id)}
							</span>
						{/if}

						{#if m.to_agents.length > 0}
							<span
								class="inline-flex items-center gap-1 px-2 py-1 rounded-md text-[var(--text-muted)] font-mono"
							>
								→ {m.to_agents.join(', ')}
							</span>
						{/if}
					</div>

					<!-- Citations -->
					{#if m.citations.length > 0}
						<div class="mt-3 flex flex-wrap gap-1.5">
							{#each m.citations as c}
								<button
									type="button"
									onclick={() => copyUrn(c.urn)}
									class="inline-flex items-center gap-1 px-2 py-1 rounded text-xs font-mono border border-[var(--border)] bg-[var(--bg-base)] hover:bg-[var(--bg-muted)] transition-colors"
									title={`Click to copy URN${c.node_kind ? ` (${c.node_kind})` : ''}`}
								>
									{#if copiedUrn === c.urn}
										<Check size={10} class="text-[var(--accent)]" />
									{:else}
										<Copy size={10} class="text-[var(--text-muted)]" />
									{/if}
									<span class="truncate max-w-[280px]">{c.urn}</span>
									{#if c.node_kind}
										<Badge variant="slate">{c.node_kind}</Badge>
									{/if}
								</button>
							{/each}
						</div>
					{/if}

					{#if sk === 'rejection'}
						<div class="mt-2 inline-flex items-center gap-1 text-xs text-[var(--text-muted)]">
							<AlertCircle size={12} />
							The author can re-answer with a stable-URN citation to clear this.
						</div>
					{/if}
				</div>
			</div>
		{/each}

		{#if messages.length < total}
			<div class="text-center text-xs text-[var(--text-muted)]">
				Showing {messages.length} of {total} messages
			</div>
		{/if}
	</div>
</div>
