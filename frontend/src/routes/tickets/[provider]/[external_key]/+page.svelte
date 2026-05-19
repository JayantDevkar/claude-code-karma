<script lang="ts">
	import { TicketBadge } from '$lib/components/tickets';
	import { ArrowLeft, AlertTriangle, ExternalLink, FolderGit2 } from 'lucide-svelte';

	let { data } = $props();

	function formatDate(iso: string | null): string {
		if (!iso) return '—';
		return new Date(iso).toLocaleString();
	}

	function sourceLabel(s: string): string {
		return s === 'slash_command' ? 'slash command' : s;
	}

	/** project_encoded_name → human display (last path segment after the leading dashes). */
	function projectDisplayName(encoded: string | null): string {
		if (!encoded) return 'Not yet indexed';
		const parts = encoded.split('-').filter(Boolean);
		return parts.length > 0 ? parts[parts.length - 1] : encoded;
	}

	type SessionRow = (typeof data.sessions)[number];
	type ProjectGroup = {
		key: string;
		project_encoded_name: string | null;
		sessions: SessionRow[];
	};

	const ORPHAN_KEY = '__orphan__';

	let groups = $derived.by<ProjectGroup[]>(() => {
		const buckets = new Map<string, SessionRow[]>();
		for (const s of data.sessions) {
			const key = s.project_encoded_name ?? ORPHAN_KEY;
			if (!buckets.has(key)) buckets.set(key, []);
			buckets.get(key)!.push(s);
		}
		return [...buckets.entries()]
			.map(([key, sessions]) => ({
				key,
				project_encoded_name: key === ORPHAN_KEY ? null : key,
				sessions
			}))
			.sort((a, b) => {
				// Orphan group always last
				if (a.key === ORPHAN_KEY) return 1;
				if (b.key === ORPHAN_KEY) return -1;
				return b.sessions.length - a.sessions.length;
			});
	});

	let realProjectGroups = $derived(groups.filter((g) => g.project_encoded_name));
	let showProjectBreakdown = $derived(realProjectGroups.length > 1);
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
			<div class="flex items-baseline justify-between gap-3">
				<h2
					id="sessions-heading"
					class="text-sm font-semibold uppercase tracking-wide text-[var(--text-secondary)] m-0"
				>
					Linked sessions ({data.sessions.length})
				</h2>
				{#if showProjectBreakdown}
					<p class="text-xs text-[var(--text-muted)] m-0 inline-flex items-center gap-1.5">
						<FolderGit2 size={12} />
						<span>
							Touched
							{#each realProjectGroups as g, i (g.key)}
								<a
									href="/projects/{g.project_encoded_name}"
									class="hover:text-[var(--accent)] hover:underline"
								>
									{projectDisplayName(g.project_encoded_name)}
								</a>
								<span class="text-[var(--text-faint)]">({g.sessions.length})</span>{#if i < realProjectGroups.length - 1}
									<span class="text-[var(--text-faint)]"> · </span>
								{/if}
							{/each}
						</span>
					</p>
				{/if}
			</div>

			{#if data.sessions.length === 0}
				<p class="text-sm text-[var(--text-muted)] m-0">
					No sessions linked to this ticket. Open a session and paste
					<code class="font-mono">{data.ticket.external_key}</code> to link one.
				</p>
			{:else}
				<div class="flex flex-col gap-4">
					{#each groups as group (group.key)}
						<div class="flex flex-col gap-2">
							<div
								class="flex items-baseline justify-between gap-3 pb-1 border-b border-[var(--border-subtle)]"
							>
								<div class="flex items-center gap-2 text-xs">
									<FolderGit2 size={12} class="text-[var(--text-muted)]" />
									{#if group.project_encoded_name}
										<a
											href="/projects/{group.project_encoded_name}"
											class="font-mono text-[var(--text-primary)] hover:text-[var(--accent)] hover:underline"
										>
											{projectDisplayName(group.project_encoded_name)}
										</a>
									{:else}
										<span class="italic text-[var(--text-muted)]">
											Not yet indexed
										</span>
									{/if}
									<span class="text-[var(--text-faint)]">
										· {group.sessions.length}
										{group.sessions.length === 1 ? 'session' : 'sessions'}
									</span>
								</div>
							</div>

							<ul class="flex flex-col gap-2 m-0 p-0 list-none">
								{#each group.sessions as s (s.link_id)}
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
						</div>
					{/each}
				</div>
			{/if}
		</section>
	{/if}
</div>
