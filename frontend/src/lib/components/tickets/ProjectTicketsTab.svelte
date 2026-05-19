<script lang="ts">
	import type { TicketListItem } from '$lib/api-types';
	import { API_BASE } from '$lib/config';
	import {
		PROVIDER_META,
		normalizeStatus,
		statusColorVar,
		formatRelative
	} from '$lib/ticket-helpers';
	import { ExternalLink, Search, Ticket as TicketIcon, Slash, GitBranch, Link as LinkIcon, Sparkles } from 'lucide-svelte';

	interface Props {
		projectEncodedName: string;
	}

	let { projectEncodedName }: Props = $props();

	let tickets = $state<TicketListItem[] | null>(null);
	let error = $state<string | null>(null);
	let q = $state('');

	$effect(() => {
		const encoded = projectEncodedName;
		if (!encoded) return;

		let cancelled = false;
		tickets = null;
		error = null;
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

	let filtered = $derived.by<TicketListItem[]>(() => {
		const all = tickets ?? [];
		const needle = q.trim().toLowerCase();
		if (!needle) return all;
		return all.filter((t) => {
			if (t.external_key.toLowerCase().includes(needle)) return true;
			if (t.title && t.title.toLowerCase().includes(needle)) return true;
			return false;
		});
	});

	const LINK_PATHS = [
		{
			n: '01',
			title: 'In a session — type a slash command',
			cmd: '/link OCC-1284',
			sub: 'The link-ticket-to-session skill is installed by default.',
			Icon: Slash
		},
		{
			n: '02',
			title: 'Push a branch that names the ticket',
			cmd: 'git checkout -b feat/OCC-1284-auth',
			sub: 'Karma auto-detects keys like OCC-1284 or owner/repo#42.',
			Icon: GitBranch
		},
		{
			n: '03',
			title: 'Paste a URL on a session page',
			cmd: 'https://linear.app/.../OCC-1284',
			sub: 'Open any session in this project and use the Tickets section.',
			Icon: LinkIcon
		}
	] as const;
</script>

<div class="flex flex-col gap-4">
	<header class="flex items-baseline justify-between gap-3">
		<div class="flex items-baseline gap-2.5">
			<h2 class="text-sm font-semibold text-[var(--text-primary)] m-0 inline-flex items-center gap-2">
				<TicketIcon size={14} class="text-[var(--text-muted)]" />
				Tickets touched by this project
			</h2>
			{#if tickets}
				<span class="font-mono text-xs text-[var(--text-muted)]">
					[{filtered.length}{q && tickets.length !== filtered.length ? ` of ${tickets.length}` : ''}]
				</span>
			{/if}
		</div>
		<a
			href="/tickets?project={encodeURIComponent(projectEncodedName)}"
			class="text-xs text-[var(--text-secondary)] hover:text-[var(--accent)] inline-flex items-center gap-1"
		>
			Open in /tickets
			<ExternalLink size={11} />
		</a>
	</header>

	{#if error}
		<p class="text-xs text-[var(--error)] m-0">Couldn't load tickets: {error}</p>
	{:else if tickets === null}
		<p class="text-xs text-[var(--text-muted)] m-0">Loading…</p>
	{:else if tickets.length === 0}
		<!-- Reuse the terminal-flavored empty state from /tickets (Q2 A) -->
		<div class="w-full p-6 rounded-lg border border-dashed border-[var(--border)] bg-[var(--bg-subtle)] flex flex-col gap-5">
			<div class="flex items-center gap-2.5">
				<span class="font-mono text-sm text-[var(--accent)]">$ tickets</span>
				<span class="font-mono text-sm text-[var(--text-faint)]">[0 linked in this project]</span>
			</div>
			<div>
				<h3 class="text-lg font-semibold text-[var(--text-primary)] m-0 leading-tight">
					Nothing linked here yet. Three ways to start.
				</h3>
				<p class="text-sm text-[var(--text-muted)] mt-1 mb-0 max-w-[60ch]">
					When a session in this project gets linked to a ticket, it shows up here.
				</p>
			</div>
			<div class="flex flex-col rounded-md border border-[var(--border)] bg-[var(--bg-base)] overflow-hidden">
				{#each LINK_PATHS as row, i (row.n)}
					<div
						class="grid items-center gap-4 px-4 py-3"
						class:border-t={i > 0}
						class:border-[var(--border-subtle)]={i > 0}
						style="grid-template-columns: 28px 1fr auto"
					>
						<span class="font-mono text-xs text-[var(--text-faint)]">{row.n}</span>
						<div>
							<div class="text-sm font-medium text-[var(--text-primary)] flex items-center gap-2">
								<row.Icon size={12} class="text-[var(--text-muted)]" />
								{row.title}
							</div>
							<p class="text-xs text-[var(--text-muted)] mt-0.5 mb-0">{row.sub}</p>
						</div>
						<code class="font-mono text-[11.5px] px-2.5 py-1.5 rounded bg-[var(--bg-muted)] text-[var(--text-primary)] border border-[var(--border-subtle)] whitespace-nowrap">
							{row.cmd}
						</code>
					</div>
				{/each}
			</div>
			<div class="flex items-center gap-2 text-[11px] text-[var(--text-faint)]">
				<Sparkles size={11} />
				Karma is read-only — the ticket lives in its source of truth.
			</div>
		</div>
	{:else}
		<!-- Search + populated table -->
		<form onsubmit={(e) => e.preventDefault()} class="flex items-center gap-2 max-w-[360px]">
			<div class="relative flex-1">
				<Search size={12} class="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" />
				<input
					type="search"
					placeholder="Search title or key…"
					bind:value={q}
					class="w-full pl-7 pr-3 py-1.5 text-xs rounded-md border border-[var(--border)] bg-[var(--bg-base)] focus-ring"
				/>
			</div>
		</form>

		<div class="rounded-lg border border-[var(--border)] overflow-hidden bg-[var(--bg-base)]">
			<div
				class="grid gap-3.5 px-4 py-2.5 bg-[var(--bg-subtle)] border-b border-[var(--border)]"
				style="grid-template-columns: 80px minmax(0, 1fr) 130px 90px 110px"
			>
				<div class="text-[9px] uppercase tracking-wider font-semibold text-[var(--text-muted)]">Provider</div>
				<div class="text-[9px] uppercase tracking-wider font-semibold text-[var(--text-muted)]">Ticket</div>
				<div class="text-[9px] uppercase tracking-wider font-semibold text-[var(--text-muted)]">Status</div>
				<div class="text-[9px] uppercase tracking-wider font-semibold text-[var(--text-muted)] text-right">Sessions</div>
				<div class="text-[9px] uppercase tracking-wider font-semibold text-[var(--text-muted)]">Last linked</div>
			</div>

			{#each filtered as t (t.id)}
				{@const meta = PROVIDER_META[t.provider]}
				{@const norm = normalizeStatus(t.status)}
				<a
					href="/tickets/{t.provider}/{encodeURIComponent(t.external_key)}"
					class="grid gap-3.5 px-4 py-3 items-center border-t border-[var(--border-subtle)] hover:bg-[var(--accent-muted)] transition-colors"
					style="grid-template-columns: 80px minmax(0, 1fr) 130px 90px 110px"
				>
					<span
						class="inline-flex items-center justify-self-start font-mono font-bold text-white px-1 py-[1px] rounded-sm text-[10px] tracking-wider leading-snug"
						style="background: var({meta.colorVar})"
						title={meta.label}
					>
						{meta.short}
					</span>

					<div class="min-w-0">
						<div class="flex items-center gap-1.5 text-[var(--text-primary)]">
							<span class="font-mono text-xs whitespace-nowrap overflow-hidden text-ellipsis">{t.external_key}</span>
							<ExternalLink size={10} class="text-[var(--text-faint)] shrink-0" />
						</div>
						{#if t.title}
							<div class="text-xs text-[var(--text-secondary)] mt-0.5 truncate">{t.title}</div>
						{:else}
							<div class="text-[11px] text-[var(--text-faint)] mt-0.5 italic">title not yet fetched</div>
						{/if}
					</div>

					<div class="inline-flex items-center gap-1.5 text-[11.5px] text-[var(--text-secondary)]">
						{#if t.status}
							<span
								class="inline-block w-[7px] h-[7px] rounded-full shrink-0"
								style="background: var({statusColorVar(norm.key)})"
							></span>
							{t.status}
						{:else}
							<span class="text-[var(--text-faint)]">—</span>
						{/if}
					</div>

					<div class="text-right">
						<span
							class="inline-flex font-mono text-[11px] px-2 py-0.5 rounded-full
							{t.session_count > 1
								? 'bg-[var(--accent-subtle)] text-[var(--accent)]'
								: 'bg-[var(--bg-muted)] text-[var(--text-secondary)]'}"
						>
							{t.session_count}
						</span>
					</div>

					<div class="text-[11px] text-[var(--text-muted)]">{formatRelative(t.last_linked_at)}</div>
				</a>
			{/each}

			{#if filtered.length === 0}
				<div class="px-4 py-6 text-center text-xs text-[var(--text-muted)]">
					No tickets match your search.
				</div>
			{/if}
		</div>
	{/if}
</div>
