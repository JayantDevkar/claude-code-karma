<script lang="ts">
	import { TicketBadge } from '$lib/components/tickets';
	import { ArrowLeft, AlertTriangle, ExternalLink } from 'lucide-svelte';

	let { data } = $props();

	function formatDate(iso: string | null): string {
		if (!iso) return '—';
		return new Date(iso).toLocaleString();
	}

	function sourceLabel(s: string): string {
		return s === 'slash_command' ? 'slash command' : s;
	}
</script>

<svelte:head>
	<title>
		{data.ticket ? `${data.ticket.external_key} · Tickets` : 'Ticket not found'}
	</title>
</svelte:head>

<div class="max-w-4xl mx-auto p-6 flex flex-col gap-6">
	<a
		href="/tickets"
		class="inline-flex items-center gap-1.5 text-sm text-[var(--text-secondary)] hover:text-[var(--accent)] self-start"
	>
		<ArrowLeft size={14} />
		Back to tickets
	</a>

	{#if data.error || !data.ticket}
		<div
			class="flex flex-col items-center gap-3 py-12 text-center text-[var(--text-secondary)]"
		>
			<AlertTriangle size={32} class="text-[var(--error)]" />
			<h1 class="text-xl font-semibold text-[var(--text-primary)] m-0">Ticket not found</h1>
			<p class="text-sm m-0">
				No karma record for <code class="font-mono">{data.provider}/{data.external_key}</code>.
			</p>
		</div>
	{:else}
		<header class="flex flex-col gap-3">
			<TicketBadge ticket={data.ticket} variant="card" />
			<div class="flex items-center gap-3 text-xs text-[var(--text-muted)]">
				<span>First seen {formatDate(data.ticket.first_seen_at)}</span>
				{#if data.ticket.metadata_updated_at}
					<span>· Metadata refreshed {formatDate(data.ticket.metadata_updated_at)}</span>
				{/if}
			</div>
		</header>

		<section class="flex flex-col gap-3" aria-labelledby="sessions-heading">
			<h2
				id="sessions-heading"
				class="text-sm font-semibold uppercase tracking-wide text-[var(--text-secondary)] m-0"
			>
				Linked sessions ({data.sessions.length})
			</h2>

			{#if data.sessions.length === 0}
				<p class="text-sm text-[var(--text-muted)] m-0">
					No sessions linked to this ticket. Open a session and paste
					<code class="font-mono">{data.ticket.external_key}</code> to link one.
				</p>
			{:else}
				<ul class="flex flex-col gap-2 m-0 p-0 list-none">
					{#each data.sessions as s (s.link_id)}
						<li
							class="flex flex-col gap-1.5 p-3 rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)]"
						>
							<div class="flex items-baseline justify-between gap-3">
								<div class="flex items-baseline gap-2 min-w-0">
									{#if s.project_encoded_name && s.sessions_slug}
										<a
											href="/projects/{s.project_encoded_name}/{s.sessions_slug}"
											class="font-mono text-sm text-[var(--accent)] hover:underline truncate"
										>
											{s.sessions_slug}
										</a>
									{:else if s.session_slug}
										<span class="font-mono text-sm text-[var(--text-muted)] italic">
											{s.session_slug} (orphan — not yet indexed)
										</span>
									{:else}
										<span class="font-mono text-sm text-[var(--text-muted)] truncate">
											{s.session_uuid}
										</span>
									{/if}
								</div>
								<span
									class="text-[10px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-[var(--bg-muted)] text-[var(--text-secondary)]"
									title="how this link was created"
								>
									{sourceLabel(s.link_source)}
								</span>
							</div>
							{#if s.initial_prompt}
								<p
									class="text-xs text-[var(--text-secondary)] m-0 line-clamp-2"
									title={s.initial_prompt}
								>
									{s.initial_prompt}
								</p>
							{/if}
							<div class="flex items-center gap-3 text-xs text-[var(--text-muted)]">
								<span>Linked {formatDate(s.linked_at)}</span>
								{#if s.start_time}
									<span>· Started {formatDate(s.start_time)}</span>
								{/if}
								{#if s.project_encoded_name && !s.sessions_slug}
									<a
										href="/projects/{s.project_encoded_name}"
										class="ml-auto inline-flex items-center gap-1 hover:text-[var(--accent)]"
									>
										project <ExternalLink size={10} />
									</a>
								{/if}
							</div>
						</li>
					{/each}
				</ul>
			{/if}
		</section>
	{/if}
</div>
