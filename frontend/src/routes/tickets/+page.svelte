<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import type { TicketListItem, TicketProvider } from '$lib/api-types';
	import {
		PROVIDER_META,
		normalizeStatus,
		statusColorVar,
		formatRelative,
		githubKindFromUrl,
		type GithubKind
	} from '$lib/ticket-helpers';
	import {
		Search,
		ArrowRight,
		ExternalLink,
		Ticket as TicketIcon,
		CornerDownRight
	} from 'lucide-svelte';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import ProviderChip from '$lib/components/tickets/ProviderChip.svelte';
	import TicketEmptyState from '$lib/components/tickets/TicketEmptyState.svelte';

	let { data } = $props();

	let q = $state(data.filters.q);
	let provider = $state<TicketProvider | ''>((data.filters.provider as TicketProvider | '') ?? '');
	// GitHub kind sub-filter. Only meaningful when provider === 'github'.
	// URL param `kind` ∈ '' | 'issue' | 'pull_request'. Cleared automatically
	// when provider changes away from github (see setProvider below).
	let kind = $state<'' | GithubKind>((data.filters.kind as '' | GithubKind) ?? '');

	function navigate(opts: { q?: string; provider?: string; project?: string; kind?: string }) {
		const params = new URLSearchParams($page.url.searchParams);
		for (const [k, v] of Object.entries(opts)) {
			if (v) params.set(k, v);
			else params.delete(k);
		}
		goto(`/tickets?${params.toString()}`);
	}

	function setProvider(next: '' | TicketProvider) {
		provider = next;
		// kind only applies under GitHub; drop it when switching away.
		const nextKind = next === 'github' ? kind : '';
		if (next !== 'github') kind = '';
		navigate({ provider: next, kind: nextKind });
	}

	function setKind(next: '' | GithubKind) {
		kind = next;
		navigate({ kind: next });
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

	// Counts for the GH kind sub-filter, computed from the loaded list.
	// Only used when provider === 'github'.
	let githubKindCounts = $derived({
		all: data.tickets.filter((t: TicketListItem) => t.provider === 'github').length,
		issue: data.tickets.filter(
			(t: TicketListItem) => t.provider === 'github' && githubKindFromUrl(t.url) === 'issue'
		).length,
		pull_request: data.tickets.filter(
			(t: TicketListItem) =>
				t.provider === 'github' && githubKindFromUrl(t.url) === 'pull_request'
		).length
	});

	// data.tickets is already server-filtered by provider/q/project. The
	// kind sub-filter is client-side because kind is derivable from URL —
	// no need to ask the backend.
	let visibleTickets = $derived(
		kind && provider === 'github'
			? data.tickets.filter(
					(t: TicketListItem) =>
						t.provider === 'github' && githubKindFromUrl(t.url) === kind
				)
			: data.tickets
	);

	const PROVIDERS: { id: '' | TicketProvider; label: string }[] = [
		{ id: '', label: 'All' },
		{ id: 'linear', label: 'Linear' },
		{ id: 'jira', label: 'Jira' },
		{ id: 'github', label: 'GitHub' }
	];

	const GH_KINDS: { id: '' | GithubKind; label: string }[] = [
		{ id: '', label: 'All' },
		{ id: 'issue', label: 'Issues' },
		{ id: 'pull_request', label: 'PRs' }
	];

	const hasFilters = $derived(
		!!(data.filters.q || data.filters.provider || data.filters.project || data.filters.kind)
	);
</script>

<svelte:head>
	<title>Tickets · Claude Karma</title>
</svelte:head>

<div class="max-w-6xl mx-auto p-6 flex flex-col gap-5">
	<PageHeader
		title="Tickets"
		icon={TicketIcon}
		iconColor="--nav-amber"
		breadcrumbs={[{ label: 'Dashboard', href: '/' }, { label: 'Tickets' }]}
		subtitle="Linked across sessions · click through for the cross-project rollup"
	/>

	{#if data.tickets.length === 0 && !hasFilters}
		<div class="w-full max-w-[760px] mx-auto">
			<TicketEmptyState scope="global" />
		</div>
	{:else}
		<!-- Filter bar -->
		<div class="flex flex-col gap-2 p-1 rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)]">
			<div class="flex flex-wrap items-center gap-3">
				<div class="flex gap-0.5 p-0.5" role="tablist" aria-label="Filter by provider">
					{#each PROVIDERS as opt (opt.id)}
						{@const active = provider === opt.id}
						{@const meta = opt.id ? PROVIDER_META[opt.id] : null}
						<button
							type="button"
							role="tab"
							aria-selected={active}
							onclick={() => setProvider(opt.id)}
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
				<form
					onsubmit={submitSearch}
					class="flex items-center gap-2 flex-1 min-w-[240px] ml-auto max-w-[360px]"
				>
					<div class="relative flex-1">
						<Search
							size={12}
							class="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
						/>
						<input
							type="search"
							placeholder="Search title or key…"
							bind:value={q}
							class="w-full pl-7 pr-3 py-1.5 text-xs rounded-md border border-[var(--border)] bg-[var(--bg-base)] focus-ring"
						/>
					</div>
				</form>
			</div>

			<!-- GitHub kind sub-filter — only shown when GitHub is the active
				 provider. Kind (issue / pull_request) is a GitHub-specific
				 concept; surfacing it here keeps the hierarchy honest and
				 doesn't clutter the default view. -->
			{#if provider === 'github'}
				<div
					class="flex items-center gap-2 pl-2 pb-0.5"
					role="tablist"
					aria-label="Filter GitHub tickets by kind"
				>
					<CornerDownRight
						size={12}
						class="text-[var(--text-faint)] shrink-0"
						aria-hidden="true"
					/>
					<div class="flex gap-0.5 p-0.5">
						{#each GH_KINDS as opt (opt.id)}
							{@const kActive = kind === opt.id}
							{@const kCount =
								opt.id === ''
									? githubKindCounts.all
									: opt.id === 'issue'
										? githubKindCounts.issue
										: githubKindCounts.pull_request}
							<button
								type="button"
								role="tab"
								aria-selected={kActive}
								onclick={() => setKind(opt.id)}
								class="inline-flex items-center gap-1.5 px-2.5 py-0.5 text-[11px] rounded transition-colors
									{kActive
									? 'bg-[var(--bg-base)] text-[var(--text-primary)] font-semibold shadow-[var(--shadow-sm)]'
									: 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'}"
							>
								{opt.label}
								<span class="font-mono text-[10px] text-[var(--text-faint)]">{kCount}</span>
							</button>
						{/each}
					</div>
				</div>
			{/if}
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

		{#if visibleTickets.length === 0}
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

				{#each visibleTickets as t (t.id)}
					{@const norm = normalizeStatus(t.status)}
					<a
						href="/tickets/{t.provider}/{encodeURIComponent(t.external_key)}"
						class="grid gap-3.5 px-4 py-3 items-center border-t border-[var(--border-subtle)] hover:bg-[var(--accent-muted)] transition-colors"
						style="grid-template-columns: 80px minmax(0, 1fr) 130px 90px 110px"
					>
						<span class="justify-self-start">
							<ProviderChip ticket={t} />
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
