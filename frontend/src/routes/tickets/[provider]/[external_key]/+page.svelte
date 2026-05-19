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

	// Rollup stats
	let projectCount = $derived(buckets.filter((b) => b.encoded).length);
	let activeCount = $derived(
		data.sessions.filter((s: SessionRow) => s.start_time && !s.end_time).length
	);
	let endedCount = $derived(data.sessions.length - activeCount);

	let meta = $derived(data.ticket ? PROVIDER_META[data.ticket.provider] : null);
	let norm = $derived(data.ticket ? normalizeStatus(data.ticket.status) : null);
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
		<!-- Compact summary card (stats-first hierarchy) -->
		<div class="flex items-center gap-3.5 px-4 py-3 rounded-lg border border-[var(--border)] bg-[var(--bg-subtle)]">
			<span
				class="inline-flex items-center font-mono font-bold text-white px-2 py-1 rounded text-[13px] tracking-wider leading-none"
				style="background: var({meta.colorVar})"
				title={meta.label}
			>
				{meta.short}
			</span>
			<div class="flex-1 min-w-0">
				<div class="flex items-center gap-2.5 mb-0.5">
					<a
						href={data.ticket.url}
						target="_blank"
						rel="noopener noreferrer"
						class="font-mono text-[13px] text-[var(--text-primary)] hover:text-[var(--accent)] inline-flex items-center gap-1"
					>
						{data.ticket.external_key}
					</a>
					<span class="inline-flex items-center gap-1.5 text-[11px] text-[var(--text-muted)]">
						<span
							class="inline-block w-1.5 h-1.5 rounded-full"
							style="background: var({statusColorVar(norm.key)})"
						></span>
						{data.ticket.status ?? '—'}
					</span>
				</div>
				{#if data.ticket.title}
					<div class="text-sm text-[var(--text-primary)] truncate">{data.ticket.title}</div>
				{:else}
					<div class="text-xs text-[var(--text-faint)] italic">title not yet fetched</div>
				{/if}
			</div>
			<a
				href={data.ticket.url}
				target="_blank"
				rel="noopener noreferrer"
				class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md border border-[var(--border)] bg-[var(--bg-base)] text-[var(--text-primary)] hover:border-[var(--border-hover)] transition-colors"
			>
				Open in {meta.label}
				<ExternalLink size={11} />
			</a>
		</div>

		<!-- Rollup stats — projects / sessions / first seen / last touched -->
		<div class="flex rounded-lg border border-[var(--border)] bg-[var(--bg-base)] overflow-hidden">
			<div class="flex-1 p-3.5 border-r border-[var(--border-subtle)]">
				<div class="text-[9px] uppercase tracking-wider font-semibold text-[var(--text-faint)] mb-1">
					Projects
				</div>
				<div class="font-mono text-xl font-medium text-[var(--text-primary)] leading-none">
					{projectCount || (data.sessions.length ? 1 : 0)}
				</div>
				<div class="text-[10.5px] text-[var(--text-muted)] mt-1">
					{#if projectCount > 1}
						across {projectCount} repos
					{:else}
						single project
					{/if}
				</div>
			</div>
			<div class="flex-1 p-3.5 border-r border-[var(--border-subtle)]">
				<div class="text-[9px] uppercase tracking-wider font-semibold text-[var(--text-faint)] mb-1">
					Sessions
				</div>
				<div class="font-mono text-xl font-medium text-[var(--text-primary)] leading-none">
					{data.sessions.length}
				</div>
				<div class="text-[10.5px] text-[var(--text-muted)] mt-1">
					{activeCount} active · {endedCount} ended
				</div>
			</div>
			<div class="flex-1 p-3.5 border-r border-[var(--border-subtle)]">
				<div class="text-[9px] uppercase tracking-wider font-semibold text-[var(--text-faint)] mb-1">
					First seen
				</div>
				<div class="font-mono text-xl font-medium text-[var(--text-primary)] leading-none">
					{formatRelative(data.ticket.first_seen_at)}
				</div>
				<div class="text-[10.5px] text-[var(--text-muted)] mt-1">when karma noticed it</div>
			</div>
			<div class="flex-1 p-3.5">
				<div class="text-[9px] uppercase tracking-wider font-semibold text-[var(--text-faint)] mb-1">
					Metadata
				</div>
				<div class="font-mono text-xl font-medium text-[var(--text-primary)] leading-none">
					{formatRelative(data.ticket.metadata_updated_at)}
				</div>
				<div class="text-[10.5px] text-[var(--text-muted)] mt-1">last refresh from MCP</div>
			</div>
		</div>

		<!-- Sessions heading + project tabs -->
		<div class="flex items-baseline justify-between gap-3 mt-2">
			<h2 class="text-sm font-semibold text-[var(--text-primary)] m-0">
				Sessions
				<span class="font-mono text-xs text-[var(--text-faint)] font-normal">[{data.sessions.length}]</span>
			</h2>
			<span class="text-[11px] text-[var(--text-muted)]">Sorted by most recently linked</span>
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
					{@const isActive = !!s.start_time && !s.end_time}
					{@const href =
						s.project_encoded_name && s.sessions_slug
							? `/projects/${s.project_encoded_name}/${s.sessions_slug}`
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
								{isActive ? 'animate-pulse' : ''}"
							style="background: var({isActive ? '--success' : '--text-faint'})"
						></span>

						<div class="min-w-0">
							<div class="flex items-center gap-2 flex-wrap">
								{#if s.project_encoded_name && s.sessions_slug}
									<span class="font-mono text-xs text-[var(--accent)]">{s.sessions_slug}</span>
								{:else if s.session_slug}
									<span class="font-mono text-xs text-[var(--text-faint)] italic">{s.session_slug} (orphan)</span>
								{:else}
									<span class="font-mono text-xs text-[var(--text-faint)] italic">unindexed session</span>
								{/if}
								{#if isActive}
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
