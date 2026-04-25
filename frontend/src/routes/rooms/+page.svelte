<script lang="ts">
	import { browser } from '$app/environment';
	import { goto } from '$app/navigation';
	import { MessagesSquare, Search, Users, FileText, Pin } from 'lucide-svelte';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import SegmentedControl from '$lib/components/ui/SegmentedControl.svelte';
	import { formatDistanceToNow } from 'date-fns';

	let { data } = $props();

	// svelte-ignore state_referenced_locally
	let search = $state(data.filters.search ?? '');
	// svelte-ignore state_referenced_locally
	let status = $state<'all' | 'active' | 'archived'>(
		(data.filters.status as 'active' | 'archived' | null) ?? 'all'
	);
	// svelte-ignore state_referenced_locally
	let sort = $state<'activity' | 'created'>(
		(data.filters.sort as 'activity' | 'created') ?? 'activity'
	);

	let debounceTimer: ReturnType<typeof setTimeout> | null = null;

	function syncUrl() {
		if (!browser) return;
		const params = new URLSearchParams();
		if (search) params.set('search', search);
		if (status !== 'all') params.set('status', status);
		if (sort !== 'activity') params.set('sort', sort);
		const qs = params.toString();
		goto(qs ? `?${qs}` : '/rooms', { replaceState: true, noScroll: true, keepFocus: true });
	}

	function onSearchInput(e: Event) {
		search = (e.target as HTMLInputElement).value;
		if (debounceTimer) clearTimeout(debounceTimer);
		debounceTimer = setTimeout(syncUrl, 200);
	}

	$effect(() => {
		// Re-sync on segmented-control changes
		void status;
		void sort;
		syncUrl();
	});

	function fmtActivity(iso: string): string {
		try {
			return formatDistanceToNow(new Date(iso), { addSuffix: true });
		} catch {
			return iso;
		}
	}
</script>

<svelte:head>
	<title>Rooms · Claude Code Karma</title>
</svelte:head>

<div class="max-w-[1200px] mx-auto px-4 md:px-6 py-6 space-y-6">
	<PageHeader
		title="Rooms"
		icon={MessagesSquare}
		subtitle="Cross-agent coordination on Linear / GitHub tickets"
	/>

	<!-- Filters -->
	<div class="flex flex-col sm:flex-row gap-3 items-stretch sm:items-center">
		<div
			class="relative flex-1 min-w-0"
		>
			<Search
				size={16}
				class="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)] pointer-events-none"
			/>
			<input
				type="search"
				placeholder="Search by ticket id or title…"
				value={search}
				oninput={onSearchInput}
				class="w-full pl-10 pr-3 py-2 bg-[var(--bg-subtle)] border border-[var(--border)] rounded-md text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)] transition-shadow"
			/>
		</div>

		<SegmentedControl
			options={[
				{ value: 'all', label: 'All' },
				{ value: 'active', label: 'Active' },
				{ value: 'archived', label: 'Archived' }
			]}
			bind:value={status}
		/>

		<SegmentedControl
			options={[
				{ value: 'activity', label: 'Activity' },
				{ value: 'created', label: 'Created' }
			]}
			bind:value={sort}
		/>
	</div>

	{#if data.error}
		<EmptyState
			icon={MessagesSquare}
			title="Couldn't load rooms"
			description={data.error}
		/>
	{:else if data.rooms.length === 0}
		<EmptyState
			icon={MessagesSquare}
			title="No rooms yet"
			description="Configure both Claude Code hooks (SessionStart and UserPromptSubmit) per claude-communicate's wiring guide, then start a Claude session on a branch matching LIN-####. Rooms appear here as agents join."
		>
			<a
				href="https://github.com/JayantDevkar/claude-communicate#wiring-up-the-hooks"
				target="_blank"
				rel="noreferrer"
				class="text-sm font-medium text-[var(--accent)] hover:underline"
			>
				claude-communicate wiring guide →
			</a>
		</EmptyState>
	{:else}
		<div class="grid gap-3">
			{#each data.rooms as room (room.id)}
				<a
					href={`/rooms/${encodeURIComponent(room.id)}`}
					class="block group"
				>
					<Card class="hover:border-[var(--accent)] transition-colors p-4">
						<div class="flex items-start justify-between gap-3">
							<div class="min-w-0 flex-1">
								<div class="flex items-center gap-2 flex-wrap">
									<span class="font-mono text-sm font-semibold text-[var(--text-primary)]">
										{room.id}
									</span>
									{#if room.status === 'archived'}
										<Badge variant="slate">archived</Badge>
									{:else}
										<Badge variant="success">active</Badge>
									{/if}
								</div>
								{#if room.title}
									<div class="text-sm text-[var(--text-secondary)] mt-1 truncate">
										{room.title}
									</div>
								{/if}
								<div class="flex items-center gap-4 mt-2 text-xs text-[var(--text-muted)]">
									<span class="inline-flex items-center gap-1">
										<Users size={12} />
										{room.agent_count} {room.agent_count === 1 ? 'agent' : 'agents'}
									</span>
									<span class="inline-flex items-center gap-1">
										<FileText size={12} />
										{room.message_count} {room.message_count === 1 ? 'message' : 'messages'}
									</span>
									<span class="inline-flex items-center gap-1">
										<Pin size={12} />
										{room.decision_count} {room.decision_count === 1 ? 'decision' : 'decisions'}
									</span>
								</div>
							</div>
							<div class="text-xs text-[var(--text-muted)] whitespace-nowrap shrink-0">
								{fmtActivity(room.last_activity)}
							</div>
						</div>
					</Card>
				</a>
			{/each}
		</div>

		<div class="text-xs text-[var(--text-muted)] text-center">
			{data.total} {data.total === 1 ? 'room' : 'rooms'}
		</div>
	{/if}
</div>
