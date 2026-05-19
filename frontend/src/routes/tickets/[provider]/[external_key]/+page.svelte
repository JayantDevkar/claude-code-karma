<script lang="ts">
	import {
		ArrowLeft,
		AlertTriangle,
		ExternalLink,
		GitBranch,
		ChevronRight
	} from 'lucide-svelte';
	import {
		PROVIDER_META,
		normalizeStatus,
		statusColorVar,
		projectDisplayName,
		formatRelative
	} from '$lib/ticket-helpers';
	import ProviderChip from '$lib/components/tickets/ProviderChip.svelte';

	let { data } = $props();

	type SessionRow = (typeof data.sessions)[number];

	const ORPHAN_KEY = '__orphan__';

	function sourceLabel(s: string): string {
		if (s === 'slash_command') return 'via /link';
		if (s === 'branch') return 'via branch';
		return 'via paste';
	}
	function sourceClass(s: string): string {
		if (s === 'slash_command') return 'text-[var(--accent)] bg-[var(--accent-subtle)]';
		if (s === 'branch') return 'text-[var(--success)] bg-[var(--success-subtle)]';
		return 'text-[var(--info)] bg-[var(--info-subtle)]';
	}

	/** Map a live SessionState to a small badge spec. Returns null for
	 * STOPPED/ENDED — those don't merit an "active" badge. */
	function liveBadge(status: string | undefined | null): {
		label: string;
		klass: string;
	} | null {
		if (!status) return null;
		const s = status.toUpperCase();
		if (s === 'LIVE')
			return { label: 'ACTIVE', klass: 'text-[var(--success)] bg-[var(--success-subtle)]' };
		if (s === 'WAITING')
			return { label: 'WAITING', klass: 'text-[var(--warning)] bg-[var(--warning-subtle)]' };
		if (s === 'STARTING')
			return { label: 'STARTING', klass: 'text-[var(--info)] bg-[var(--info-subtle)]' };
		if (s === 'STALE')
			return { label: 'STALE', klass: 'text-[var(--text-muted)] bg-[var(--bg-muted)]' };
		return null;
	}

	// Project tabs (Q9b A): "All" + one tab per project that owns ≥ 1 session.
	// Orphan (unindexed) sessions group last when present.
	type ProjectBucket = {
		key: string;
		encoded: string | null;
		label: string;
		sessions: SessionRow[];
	};

	let buckets = $derived.by<ProjectBucket[]>(() => {
		const map = new Map<string, SessionRow[]>();
		for (const s of data.sessions) {
			const key = s.project_encoded_name ?? ORPHAN_KEY;
			if (!map.has(key)) map.set(key, []);
			map.get(key)!.push(s);
		}
		return [...map.entries()]
			.map(([key, sessions]) => ({
				key,
				encoded: key === ORPHAN_KEY ? null : key,
				label: key === ORPHAN_KEY ? 'Unindexed' : projectDisplayName(key),
				sessions
			}))
			.sort((a, b) => {
				if (a.key === ORPHAN_KEY) return 1;
				if (b.key === ORPHAN_KEY) return -1;
				return b.sessions.length - a.sessions.length;
			});
	});

	let showTabs = $derived(buckets.length > 1);
	let activeKey = $state<string>('__all__');

	let visibleSessions = $derived(
		activeKey === '__all__'
			? data.sessions
			: (buckets.find((b) => b.key === activeKey)?.sessions ?? [])
	);

	// Rollup stats. Active = live-and-not-quiet OR indexed-with-no-end_time.
	// Matches the per-row `isLive` derivation below so the count never
	// disagrees with what the user sees in the list. STALE/STOPPED/ENDED
	// live states correctly count as ended, not active.
	let projectCount = $derived(buckets.filter((b) => b.encoded).length);
	let activeCount = $derived(
		data.sessions.filter((s: SessionRow) => {
			if (s.live) {
				return s.live.status === 'LIVE' || s.live.status === 'WAITING' || s.live.status === 'STARTING';
			}
			return !!s.start_time && !s.end_time;
		}).length
	);
	let endedCount = $derived(data.sessions.length - activeCount);

	let meta = $derived(data.ticket ? PROVIDER_META[data.ticket.provider] : null);
	let norm = $derived(data.ticket ? normalizeStatus(data.ticket.status) : null);

	/** Suppress the `synced X` chip when metadata was set within ~60s of
	 * first_seen. Freshly-linked tickets report identical values; showing
	 * `first seen just now · synced just now` reads as redundant. */
	function isSyncedNearFirstSeen(firstSeen: string | null, synced: string | null): boolean {
		if (!firstSeen || !synced) return false;
		const f = Date.parse(firstSeen);
		const s = Date.parse(synced);
		if (Number.isNaN(f) || Number.isNaN(s)) return false;
		return Math.abs(s - f) < 60_000;
	}
</script>

<svelte:head>
	<title>{data.ticket ? `${data.ticket.external_key} · Tickets` : 'Ticket not found'}</title>
</svelte:head>

<div class="max-w-4xl mx-auto p-6 flex flex-col gap-4">
	<!-- Breadcrumb -->
	<div class="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
		<a href="/tickets" class="inline-flex items-center gap-1.5 hover:text-[var(--accent)]">
			<ArrowLeft size={12} />
			Tickets
		</a>
		<ChevronRight size={11} />
		<span class="font-mono text-[var(--text-secondary)]">
			{data.provider}/{data.external_key}
		</span>
	</div>

	{#if data.error || !data.ticket || !meta || !norm}
		<div class="flex flex-col items-center gap-3 py-12 text-center text-[var(--text-secondary)]">
			<AlertTriangle size={32} class="text-[var(--error)]" />
			<h1 class="text-xl font-semibold text-[var(--text-primary)] m-0">Ticket not found</h1>
			<p class="text-sm m-0">
				No karma record for <code class="font-mono">{data.provider}/{data.external_key}</code>.
			</p>
		</div>
	{:else}
		<!-- Hero — title is the protagonist. Provider chip + monospace key as
			 the small identifier above; status as a visible inline state next
			 to the title; all rollup numbers collapsed into one subtitle line.
			 No 4-up stats grid — see decision log "F1 rebuild" for rationale. -->
		<header class="flex flex-col gap-3">
			<div class="flex items-center gap-2.5 text-[12px] text-[var(--text-muted)]">
				<ProviderChip ticket={data.ticket} />
				<a
					href={data.ticket.url}
					target="_blank"
					rel="noopener noreferrer"
					class="font-mono text-[var(--text-secondary)] hover:text-[var(--accent)] inline-flex items-center gap-1"
				>
					{data.ticket.external_key}
					<ExternalLink size={10} />
				</a>
				<a
					href={data.ticket.url}
					target="_blank"
					rel="noopener noreferrer"
					class="ml-auto inline-flex items-center gap-1.5 px-2.5 py-1 text-[11px] rounded-md border border-[var(--border)] text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:border-[var(--border-hover)] transition-colors"
				>
					Open in {meta.label}
					<ExternalLink size={10} />
				</a>
			</div>

			<div class="flex items-start gap-4">
				<div class="flex-1 min-w-0">
					{#if data.ticket.title}
						<h1 class="text-2xl sm:text-[28px] font-semibold tracking-tight text-[var(--text-primary)] leading-tight m-0">
							{data.ticket.title}
						</h1>
					{:else}
						<h1 class="text-2xl font-semibold tracking-tight text-[var(--text-muted)] italic leading-tight m-0">
							title not yet fetched
						</h1>
					{/if}
					<p class="mt-2 text-[12px] text-[var(--text-muted)] m-0 flex flex-wrap items-center gap-x-3 gap-y-1">
						{#if data.ticket.status}
							<span class="inline-flex items-center gap-1.5 text-[var(--text-secondary)] font-medium">
								<span
									class="inline-block w-2 h-2 rounded-full"
									style="background: var({statusColorVar(norm.key)})"
								></span>
								{data.ticket.status}
							</span>
							<span class="text-[var(--text-faint)]">·</span>
						{/if}
						<span>
							{data.sessions.length}
							{data.sessions.length === 1 ? 'session' : 'sessions'}
							{#if activeCount > 0}
								<span class="text-[var(--text-faint)]"> ({activeCount} active)</span>
							{/if}
						</span>
						<span class="text-[var(--text-faint)]">·</span>
						<span>
							{projectCount || (data.sessions.length ? 1 : 0)}
							{(projectCount || (data.sessions.length ? 1 : 0)) === 1 ? 'project' : 'projects'}
						</span>
						<span class="text-[var(--text-faint)]">·</span>
						<span>first seen {formatRelative(data.ticket.first_seen_at)}</span>
						{#if data.ticket.metadata_updated_at && !isSyncedNearFirstSeen(data.ticket.first_seen_at, data.ticket.metadata_updated_at)}
							<span class="text-[var(--text-faint)]">·</span>
							<span>synced {formatRelative(data.ticket.metadata_updated_at)}</span>
						{/if}
					</p>
				</div>
			</div>
		</header>

		<!-- Sessions heading + project tabs -->
		<div class="flex items-baseline gap-3 mt-2">
			<h2 class="text-sm font-semibold text-[var(--text-primary)] m-0">
				Sessions
			</h2>
			<span class="text-[11px] text-[var(--text-muted)]">· sorted by most recently linked</span>
		</div>

		{#if showTabs}
			<div class="flex items-center gap-0 border-b border-[var(--border)] overflow-x-auto">
				<button
					type="button"
					role="tab"
					aria-selected={activeKey === '__all__'}
					onclick={() => (activeKey = '__all__')}
					class="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs whitespace-nowrap transition-colors
						{activeKey === '__all__'
						? 'text-[var(--text-primary)] font-semibold border-b-2 border-[var(--accent)] -mb-px'
						: 'text-[var(--text-muted)] hover:text-[var(--text-primary)] border-b-2 border-transparent -mb-px'}"
				>
					All
					<span class="font-mono text-[10px] text-[var(--text-faint)]">[{data.sessions.length}]</span>
				</button>
				{#each buckets as b (b.key)}
					<button
						type="button"
						role="tab"
						aria-selected={activeKey === b.key}
						onclick={() => (activeKey = b.key)}
						class="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs whitespace-nowrap transition-colors
							{activeKey === b.key
							? 'text-[var(--text-primary)] font-semibold border-b-2 border-[var(--accent)] -mb-px'
							: 'text-[var(--text-muted)] hover:text-[var(--text-primary)] border-b-2 border-transparent -mb-px'}"
					>
						{#if b.encoded}
							<GitBranch size={11} />
						{/if}
						{b.label}
						<span class="font-mono text-[10px] text-[var(--text-faint)]">[{b.sessions.length}]</span>
					</button>
				{/each}
			</div>
		{/if}

		{#if data.sessions.length === 0}
			<p class="text-sm text-[var(--text-muted)] m-0 px-1 py-6 text-center">
				No sessions linked to this ticket. Open a session and paste
				<code class="font-mono">{data.ticket.external_key}</code> to link one.
			</p>
		{:else}
			<div class="rounded-lg border border-[var(--border)] bg-[var(--bg-base)] overflow-hidden">
				{#each visibleSessions as s, i (s.link_id)}
					{@const badge = liveBadge(s.live?.status)}
					{@const isLive = !!s.live && ['LIVE', 'WAITING', 'STARTING'].includes(s.live.status)}
					{@const isActive = isLive || (!!s.start_time && !s.end_time)}
					{@const isOrphan = !s.sessions_slug && !s.live}
					{@const slugLabel = s.sessions_slug ?? s.session_slug ?? null}
					{@const navIdentifier = slugLabel ?? s.session_uuid.slice(0, 8)}
					{@const href = s.project_encoded_name
						? `/projects/${s.project_encoded_name}/${navIdentifier}`
						: null}
					<svelte:element
						this={href ? 'a' : 'div'}
						href={href}
						class="grid gap-3 items-center px-4 py-3 transition-colors
							{i > 0 ? 'border-t border-[var(--border-subtle)]' : ''}
							{href ? 'hover:bg-[var(--accent-muted)]' : ''}"
						style="grid-template-columns: 14px minmax(0, 1fr) auto auto"
					>
						<span
							aria-hidden="true"
							class="inline-block w-2 h-2 rounded-full shrink-0
								{isLive ? 'animate-pulse' : ''}"
							style="background: var({isActive ? '--success' : '--text-faint'})"
						></span>

						<div class="min-w-0">
							<div class="flex items-center gap-2 flex-wrap">
								{#if isOrphan}
									<span class="font-mono text-xs text-[var(--text-faint)] italic">
										{s.session_slug ?? s.session_uuid.slice(0, 8)} · no data
									</span>
								{:else if slugLabel}
									<span class="font-mono text-xs text-[var(--accent)]">{slugLabel}</span>
								{:else}
									<span class="font-mono text-xs text-[var(--text-faint)]">
										{s.session_uuid.slice(0, 8)}
									</span>
								{/if}
								{#if badge}
									<span class="text-[9px] uppercase tracking-wider font-semibold px-1.5 py-0.5 rounded {badge.klass}">
										{badge.label}
									</span>
								{:else if isActive && !s.live}
									<span class="text-[9px] uppercase tracking-wider font-semibold text-[var(--success)]">ACTIVE</span>
								{/if}
								<span
									class="text-[9px] uppercase tracking-wider font-semibold px-1.5 py-0.5 rounded {sourceClass(s.link_source)}"
								>
									{sourceLabel(s.link_source)}
								</span>
								{#if activeKey === '__all__' && s.project_encoded_name}
									<span class="inline-flex items-center gap-1 text-[10.5px] text-[var(--text-muted)] px-1.5 py-0.5 rounded bg-[var(--bg-subtle)] border border-[var(--border-subtle)]">
										<GitBranch size={9} />
										{projectDisplayName(s.project_encoded_name)}
									</span>
								{/if}
							</div>
							{#if s.initial_prompt}
								<div class="text-[11.5px] text-[var(--text-muted)] mt-1 truncate" title={s.initial_prompt}>
									{s.initial_prompt}
								</div>
							{/if}
						</div>

						<span class="font-mono text-[11px] text-[var(--text-secondary)] whitespace-nowrap">
							{formatRelative(s.start_time)}
						</span>
						<span class="text-[11px] text-[var(--text-faint)] whitespace-nowrap">
							linked {formatRelative(s.linked_at)}
						</span>
					</svelte:element>
				{/each}
			</div>
		{/if}
	{/if}
</div>
