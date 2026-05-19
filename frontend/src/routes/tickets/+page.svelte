<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import type { TicketListItem, TicketProvider } from '$lib/api-types';
	import {
		PROVIDER_META,
		normalizeStatus,
		statusColorVar,
		formatRelative
	} from '$lib/ticket-helpers';
	import {
		Search,
		ExternalLink,
		Sparkles,
		GitBranch,
		Slash,
		Link as LinkIcon,
		ArrowRight
	} from 'lucide-svelte';

	let { data } = $props();

	let q = $state(data.filters.q);
	let provider = $state<TicketProvider | ''>((data.filters.provider as TicketProvider | '') ?? '');

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

	// Counts per provider — used in the segmented filter
	let counts = $derived({
		all: data.tickets.length,
		linear: data.tickets.filter((t: TicketListItem) => t.provider === 'linear').length,
		jira: data.tickets.filter((t: TicketListItem) => t.provider === 'jira').length,
		github: data.tickets.filter((t: TicketListItem) => t.provider === 'github').length
	});

	const PROVIDERS: { id: '' | TicketProvider; label: string }[] = [
		{ id: '', label: 'All' },
		{ id: 'linear', label: 'Linear' },
		{ id: 'jira', label: 'Jira' },
		{ id: 'github', label: 'GitHub' }
	];

	const LINK_PATHS = [
		{
			n: '01',
			title: 'In a session — type a slash command',
			cmd: '/link-ticket-to-session ABC-123',
			sub: 'Fastest. Works in any active session — the skill is installed by default.',
			Icon: Slash
		},
		{
			n: '02',
			title: 'Push a branch that names the ticket',
			cmd: 'git checkout -b feat/ABC-123-…',
			sub: 'Karma auto-detects keys like ABC-123, PROJ-42, or owner/repo#42.',
			Icon: GitBranch
		},
		{
			n: '03',
			title: 'Paste a URL from any session page',
			cmd: 'https://linear.app/team/issue/ABC-123',
			sub: 'Open the session, scroll to the Tickets section, paste the URL.',
			Icon: LinkIcon
		}
	] as const;

	const hasFilters = $derived(!!(data.filters.q || data.filters.provider || data.filters.project));
</script>

<svelte:head>
	<title>Tickets · Claude Karma</title>
</svelte:head>

<div class="max-w-6xl mx-auto p-6 flex flex-col gap-5">
	<!-- Page header -->
	<header class="flex items-baseline justify-between gap-4">
		<div class="flex items-baseline gap-2.5">
			<h1 class="text-2xl font-semibold tracking-tight text-[var(--text-primary)] m-0">Tickets</h1>
			<span class="font-mono text-xs text-[var(--text-muted)]">[{data.tickets.length}]</span>
		</div>
		<p class="text-xs text-[var(--text-muted)] m-0">
			Tickets linked to any session. Click through for the cross-project rollup.
		</p>
	</header>

	{#if data.tickets.length === 0 && !hasFilters}
		<!-- Terminal-flavored empty state (Q2 A) -->
		<div class="w-full max-w-[760px] mx-auto p-8 rounded-lg border border-dashed border-[var(--border)] bg-[var(--bg-subtle)] flex flex-col gap-6">
			<div class="flex items-center gap-2.5">
				<span class="font-mono text-sm text-[var(--accent)]">$ tickets</span>
				<span class="font-mono text-sm text-[var(--text-faint)]">[0 linked]</span>
			</div>
			<div>
				<h2 class="text-xl font-semibold text-[var(--text-primary)] m-0 leading-tight">
					No tickets yet. Three ways to start.
				</h2>
				<p class="text-sm text-[var(--text-muted)] mt-1.5 mb-0 max-w-[60ch]">
					Karma watches your Claude Code sessions. Link one to a ticket and the time
					spent, tool calls, and prompts roll up here.
				</p>
			</div>

			<div class="flex flex-col rounded-md border border-[var(--border)] bg-[var(--bg-base)] overflow-hidden">
				{#each LINK_PATHS as row, i (row.n)}
					<div
						class="grid items-center gap-4 px-4 py-3.5"
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
				Karma stores key, title, and status — the ticket lives in its source of truth.
			</div>
		</div>
	{:else}
		<!-- Filter bar -->
		<div class="flex flex-wrap items-center gap-3 p-1 rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)]">
			<div class="flex gap-0.5 p-0.5" role="tablist" aria-label="Filter by provider">
				{#each PROVIDERS as opt (opt.id)}
					{@const active = provider === opt.id}
					{@const meta = opt.id ? PROVIDER_META[opt.id] : null}
					<button
						type="button"
						role="tab"
						aria-selected={active}
						onclick={() => {
							provider = opt.id;
							navigate({ provider: opt.id });
						}}
						class="inline-flex items-center gap-1.5 px-3 py-1 text-xs rounded transition-colors
							{active
							? 'bg-[var(--bg-base)] text-[var(--text-primary)] font-semibold shadow-[var(--shadow-sm)]'
							: 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'}"
					>
						{#if meta}
							<span
								class="inline-block w-2 h-2 rounded-sm"
								style="background: var({meta.colorVar})"
							></span>
						{/if}
						{opt.label}
						<span class="font-mono text-[10px] text-[var(--text-faint)]">
							{opt.id === '' ? counts.all : counts[opt.id]}
						</span>
					</button>
				{/each}
			</div>
			<form onsubmit={submitSearch} class="flex items-center gap-2 flex-1 min-w-[240px] ml-auto max-w-[360px]">
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
		</div>

		{#if data.filters.project}
			<div
				class="flex items-center gap-2 text-sm px-3 py-2 rounded-md bg-[var(--accent-muted)] border border-[var(--accent-subtle)]"
			>
				<span class="text-[var(--text-secondary)]">Filtered to project:</span>
				<code class="font-mono text-[var(--text-primary)]">{data.filters.project}</code>
				<button
					type="button"
					onclick={clearProject}
					class="ml-auto text-[var(--accent)] hover:underline text-xs"
				>
					Clear
				</button>
			</div>
		{/if}

		{#if data.tickets.length === 0}
			<div class="text-center py-12 text-[var(--text-muted)]">
				<p class="text-sm m-0">No tickets match your filters.</p>
			</div>
		{:else}
			<!-- Populated table -->
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

				{#each data.tickets as t (t.id)}
					{@const meta = PROVIDER_META[t.provider]}
					{@const norm = normalizeStatus(t.status)}
					<a
						href="/tickets/{t.provider}/{encodeURIComponent(t.external_key)}"
						class="grid gap-3.5 px-4 py-3 items-center border-t border-[var(--border-subtle)] hover:bg-[var(--accent-muted)] transition-colors"
						style="grid-template-columns: 80px minmax(0, 1fr) 130px 90px 110px"
					>
						<span
							class="inline-flex items-center justify-self-start font-mono font-bold px-1 py-[1px] rounded-sm text-[10px] tracking-wider leading-snug"
							style="background: var({meta.colorVar}); color: var({meta.fgVar})"
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
			</div>
		{/if}
	{/if}
</div>
