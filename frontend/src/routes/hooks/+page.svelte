<svelte:head>
	<link
		href="https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&display=swap"
		rel="stylesheet"
	/>
</svelte:head>

<script lang="ts">
	import type { HookEventSummary, HookEventDetail } from '$lib/api-types';
	import type { HookActivity } from './+page.server';
	import { API_BASE } from '$lib/config';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import { Search } from 'lucide-svelte';

	let { data } = $props();

	// ── State ────────────────────────────────────────────────────────────────
	let activeTab = $state<'timeline' | 'source'>('timeline');
	let searchQuery = $state('');
	let schemaExpanded = $state(false);
	let rightPanelEl = $state<HTMLElement | null>(null);

	// Selected event — init from URL param only; landing shown when nothing selected
	let selectedEventType = $state<string | null>(data.initialEvent ?? null);
	let drawerOpenInit = !!(data.initialEvent);

	// Lazy-loaded detail (schema_info + related_events)
	let detailData = $state<HookEventDetail | null>(null);
	let detailLoading = $state(false);

	// Drawer state
	let drawerOpen = $state(drawerOpenInit);

	function closeDrawer() {
		drawerOpen = false;
	}

	// Script source viewer
	let expandedScript = $state<string | null>(null);
	let scriptContent = $state<string | null>(null);
	let scriptLoading = $state(false);
	let scriptCopied = $state(false);

	async function copyScript() {
		if (!scriptContent) return;
		await navigator.clipboard.writeText(scriptContent);
		scriptCopied = true;
		setTimeout(() => (scriptCopied = false), 1800);
	}

	async function toggleScript(filename: string) {
		if (expandedScript === filename) { expandedScript = null; scriptContent = null; return; }
		expandedScript = filename;
		scriptContent = null;
		scriptLoading = true;
		try {
			const res = await fetch(`${API_BASE}/hooks/scripts/${encodeURIComponent(filename)}`);
			if (res.ok) {
				const d = await res.json();
				scriptContent = d.content ?? '# (no content)';
			}
		} catch { scriptContent = '# error loading file'; }
		finally { scriptLoading = false; }
	}

	$effect(() => {
		const et = selectedEventType;
		schemaExpanded = false;
		expandedScript = null;
		scriptContent = null;
		if (!et) return;
		loadDetail(et);
	});

	// Close drawer on Escape
	$effect(() => {
		function onKey(e: KeyboardEvent) {
			if (e.key === 'Escape' && drawerOpen) closeDrawer();
		}
		window.addEventListener('keydown', onKey);
		return () => window.removeEventListener('keydown', onKey);
	});

	async function loadDetail(eventType: string) {
		detailLoading = true;
		detailData = null;
		try {
			const res = await fetch(`${API_BASE}/hooks/${encodeURIComponent(eventType)}`);
			if (res.ok) detailData = (await res.json()) as HookEventDetail;
		} catch {
			// silent
		} finally {
			detailLoading = false;
		}
	}

	function selectEvent(eventType: string) {
		selectedEventType = eventType;
		drawerOpen = true;
		if (typeof window !== 'undefined') {
			const url = new URL(window.location.href);
			url.searchParams.set('event', eventType);
			window.history.replaceState({}, '', url);
		}
	}

	// ── Derived ──────────────────────────────────────────────────────────────
	let selectedEvent = $derived(
		selectedEventType
			? (data.hooks.event_summaries.find((e) => e.event_type === selectedEventType) ?? null)
			: null
	);

	let relatedPrev = $derived(
		detailData?.related_events.find((e) => e.position === 'previous') ?? null
	);
	let relatedNext = $derived(
		detailData?.related_events.find((e) => e.position === 'next') ?? null
	);

	const PHASE_ORDER = [
		'Session Lifecycle',
		'User Input',
		'Tool Lifecycle',
		'Agent Lifecycle',
		'Context & Permissions',
		'System',
		'Setup',
		'Unknown'
	];

	interface PhaseGroup {
		phase: string;
		events: HookEventSummary[];
	}

	let eventsByPhase = $derived.by<PhaseGroup[]>(() => {
		const q = searchQuery.toLowerCase();
		const filtered = q
			? data.hooks.event_summaries.filter((e) => e.event_type.toLowerCase().includes(q))
			: data.hooks.event_summaries;

		const grouped = new Map<string, HookEventSummary[]>();
		for (const ev of filtered) {
			const phase = ev.phase || 'Unknown';
			if (!grouped.has(phase)) grouped.set(phase, []);
			grouped.get(phase)!.push(ev);
		}

		const result: PhaseGroup[] = [];
		for (const phase of PHASE_ORDER) {
			if (grouped.has(phase)) {
				result.push({ phase, events: grouped.get(phase)! });
				grouped.delete(phase);
			}
		}
		for (const [phase, events] of grouped) result.push({ phase, events });
		return result;
	});

	interface SourceGroup {
		source: (typeof data.hooks.sources)[number];
		events: HookEventSummary[];
	}

	let eventsBySource = $derived.by<SourceGroup[]>(() => {
		const q = searchQuery.toLowerCase();
		return data.hooks.sources
			.map((source) => {
				const events = source.event_types_covered
					.map((et) => data.hooks.event_summaries.find((e) => e.event_type === et))
					.filter((e): e is HookEventSummary => !!e)
					.filter((e) => !q || e.event_type.toLowerCase().includes(q));
				return { source, events };
			})
			.filter((g) => g.events.length > 0);
	});

	// ── Helpers ───────────────────────────────────────────────────────────────
	function dotColor(ev: HookEventSummary): string {
		const has = ev.total_registrations > 0;
		if (has && ev.can_block) return 'var(--error)';
		if (has) return 'var(--accent)';
		if (ev.can_block) return 'rgba(209,78,43,0.25)';
		return 'var(--border)';
	}

	function sourceHexColor(sourceType: string, sourceName: string): string {
		if (sourceType === 'global') return '#E87C3A';
		const known: Record<string, string> = {
			plannotator: '#3A8A66',
			superpowers: '#4A7EBB'
		};
		if (known[sourceName]) return known[sourceName];
		const palette = ['#7C3AED', '#3A8A66', '#4A7EBB', '#E87C3A', '#6B5BF5', '#2A8A50'];
		let hash = 0;
		for (let i = 0; i < sourceName.length; i++) hash = (hash * 31 + sourceName.charCodeAt(i)) >>> 0;
		return palette[hash % palette.length];
	}

	function isSymlink(sourceName: string, filename: string | null | undefined): boolean {
		if (!filename) return false;
		for (const src of data.hooks.sources) {
			if (src.source_name === sourceName) {
				return src.scripts.find((s) => s.filename === filename)?.is_symlink ?? false;
			}
		}
		return false;
	}

	function langLabel(lang: string): string {
		const map: Record<string, string> = {
			python: 'Python',
			javascript: 'JavaScript',
			typescript: 'TypeScript',
			bash: 'Shell',
			shell: 'Shell'
		};
		return map[lang.toLowerCase()] ?? lang;
	}

	function timeAgo(isoTs: string | undefined): string | null {
		if (!isoTs) return null;
		const diff = Date.now() - new Date(isoTs).getTime();
		const m = Math.floor(diff / 60000);
		if (m < 1) return 'just now';
		if (m < 60) return `${m}m ago`;
		const h = Math.floor(m / 60);
		if (h < 24) return `${h}h ago`;
		return `${Math.floor(h / 24)}d ago`;
	}

	const activity = data.hookActivity as HookActivity;

	// B: SessionEnd reason display labels
	const END_REASON_LABELS: Record<string, string> = {
		prompt_input_exit: 'Exit command',
		clear: 'Clear',
		logout: 'Logout',
		other: 'Other',
		session_handoff: 'Session handoff',
		stuck_starting: 'Stuck starting'
	};
</script>

<style>
	@keyframes live-pulse {
		0%, 100% { opacity: 1; transform: scale(1); }
		50% { opacity: 0.4; transform: scale(0.7); }
	}
	.live-pulse {
		animation: live-pulse 1.6s ease-in-out infinite;
	}
	.script-btn {
		cursor: pointer;
		text-decoration: underline dotted;
		text-underline-offset: 2px;
		color: var(--text-secondary);
		background: none; border: none; padding: 0;
		font-family: 'DM Mono', 'JetBrains Mono', monospace;
		font-size: 11px;
	}
	.script-btn:hover { color: var(--accent); }
</style>

<!-- Full-bleed container -->
<div class="-mx-6 -my-8" style="background: var(--bg-base); min-height: 100vh;">
	<!-- Page Header -->
	<div style="padding: 32px 32px 0;">
		<PageHeader
			title="Hooks"
			iconName="hooks"
			iconColor="--nav-cyan"
			breadcrumbs={[{ label: 'Dashboard', href: '/' }, { label: 'Hooks' }]}
			subtitle="Hook scripts intercepting your Claude Code sessions"
		/>
	</div>

	<!-- Filter bar -->
	<div
		class="flex items-center"
		style="padding: 10px 32px; gap: 12px;"
	>
		<!-- Tab toggle -->
		<div
			class="flex rounded-lg p-0.5 flex-shrink-0"
			style="background: var(--bg-muted);"
			role="tablist"
			aria-label="View"
		>
			{#each ([['timeline', 'Event Timeline'], ['source', 'By Source']] as const) as [val, lbl]}
				<button
					role="tab"
					aria-selected={activeTab === val}
					onclick={() => (activeTab = val)}
					class="rounded-md transition-all"
					style="
						padding: 6px 16px;
						font-size: 12px;
						font-weight: {activeTab === val ? '600' : '500'};
						color: {activeTab === val ? 'var(--bg-base)' : 'var(--text-secondary)'};
						background: {activeTab === val ? 'var(--text-primary)' : 'transparent'};
					"
				>{lbl}</button>
			{/each}
		</div>

		<!-- Search -->
		<div class="relative ml-auto">
			<Search class="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" size={13} style="color: var(--text-faint);" />
			<input
				type="text"
				bind:value={searchQuery}
				aria-label="Search events"
				placeholder="Search events…"
				style="width: 200px; padding: 6px 12px 6px 30px; font-size: 12px; background: var(--bg-subtle); border: 1px solid var(--border); border-radius: 8px; color: var(--text-primary); outline: none;"
			/>
		</div>
	</div>

	<!-- Main landing content -->
	<div style="padding: 32px 32px 64px;">
		<!-- Stats + notifications row -->
		<div style="display: flex; align-items: flex-start; gap: 24px; margin-bottom: 36px;">
			<!-- Stat pills -->
			<div style="display: flex; flex-direction: column; gap: 8px; flex-shrink: 0;">
				{#each [
					{ label: 'Sources', value: data.hooks.stats.total_sources, accent: false },
					{ label: 'Registrations', value: data.hooks.stats.total_registrations, accent: false },
					{ label: 'Blocking', value: data.hooks.stats.blocking_hooks, accent: true },
				] as stat}
					<div style="
						background: var(--bg-subtle);
						border: 1px solid {stat.accent && stat.value > 0 ? 'rgba(209,78,43,0.3)' : 'var(--border)'};
						border-radius: 10px; padding: 14px 20px;
						display: flex; align-items: baseline; gap: 10px;
					">
						<span style="font-size: 32px; font-weight: 700; font-family: 'JetBrains Mono', monospace; color: {stat.accent && stat.value > 0 ? 'var(--error)' : 'var(--text-primary)'}; line-height: 1;">{stat.value}</span>
						<span style="font-size: 14px; color: var(--text-muted);">{stat.label}</span>
					</div>
				{/each}
			</div>

			<!-- Recent notifications (front row) -->
			{#if activity.recentNotifications.length > 0}
				<div style="flex: 1; min-width: 0;">
					<div style="font-size: 10px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 10px;">Recent notifications</div>
					<div style="display: flex; flex-direction: column; gap: 6px;">
						{#each activity.recentNotifications as notif}
							{@const href = notif.projectEncodedName && notif.slug ? `/projects/${notif.projectEncodedName}/${notif.slug}` : null}
							<div style="background: var(--bg-subtle); border: 1px solid var(--border); border-left: 3px solid var(--accent); border-radius: 7px; padding: 10px 14px;">
								<p style="font-size: 12px; color: var(--text-primary); margin: 0 0 5px; line-height: 1.5;">{notif.message}</p>
								<div style="display: flex; gap: 8px; align-items: center;">
									{#if href}
										<a {href} style="font-size: 10px; font-family: 'DM Mono', monospace; color: var(--accent); text-decoration: none;" onmouseenter={(e) => (e.currentTarget.style.textDecoration = 'underline')} onmouseleave={(e) => (e.currentTarget.style.textDecoration = 'none')}>
											{notif.slug ?? notif.sessionId.slice(0, 8)}
										</a>
									{:else}
										<span style="font-size: 10px; font-family: 'DM Mono', monospace; color: var(--text-muted);">{notif.sessionId.slice(0, 8)}</span>
									{/if}
									<span style="font-size: 10px; color: var(--text-muted);">{timeAgo(notif.updatedAt)}</span>
								</div>
							</div>
						{/each}
					</div>
				</div>
			{/if}
		</div>

		<!-- Event groups -->
		{#if activeTab === 'timeline'}
			{#each eventsByPhase as group}
				{#if group.events.length > 0}
					<div style="margin-bottom: 32px;">
						<div style="font-size: 10px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 10px; padding-left: 2px;">
							{group.phase}
						</div>
						<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 8px;">
							{#each group.events as ev (ev.event_type)}
								{@const isSelected = ev.event_type === selectedEventType && drawerOpen}
								{@const isPulsing = activity.activePulseEvent === ev.event_type}
								{@const lastSeen = timeAgo(activity.lastSeenByEvent[ev.event_type])}
								<button
									onclick={() => selectEvent(ev.event_type)}
									style="
										display: flex; flex-direction: column; gap: 6px;
										padding: 14px 16px;
										background: var(--bg-base);
										border: 1.5px solid {isSelected ? 'var(--accent)' : 'var(--border)'};
										border-radius: 9px; cursor: pointer; text-align: left;
										opacity: {ev.total_registrations === 0 ? 0.45 : 1};
										transition: border-color 0.12s, box-shadow 0.12s;
										box-shadow: {isSelected ? '0 0 0 3px rgba(107,91,245,0.1)' : 'none'};
									"
									onmouseenter={(e) => {
										if (!isSelected) (e.currentTarget as HTMLElement).style.borderColor = 'color-mix(in srgb, var(--accent) 50%, var(--border))';
									}}
									onmouseleave={(e) => {
										if (!isSelected) (e.currentTarget as HTMLElement).style.borderColor = 'var(--border)';
									}}
								>
									<!-- Top row: dot + name + count -->
									<div style="display: flex; align-items: center; gap: 7px;">
										<span
											class={isPulsing ? 'live-pulse' : ''}
											style="width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; background: {isPulsing ? '#22c55e' : dotColor(ev)};"
										></span>
										<span style="
											flex: 1; font-size: 12px; font-family: 'DM Mono', 'JetBrains Mono', monospace;
											font-weight: 500; color: {isSelected ? 'var(--accent)' : 'var(--text-primary)'};
											overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
										">{ev.event_type}</span>
										{#if ev.can_block}
											<svg width="9" height="9" viewBox="0 0 10 10" fill="none" style="flex-shrink:0;">
												<path d="M5 1.5L9 8H1L5 1.5Z" fill="var(--error)" />
											</svg>
										{/if}
										{#if ev.total_registrations > 0}
											<span style="font-size: 11px; font-family: 'DM Mono', monospace; color: {ev.can_block ? 'var(--error)' : 'var(--accent)'}; font-weight: 600; flex-shrink: 0;">{ev.total_registrations}</span>
										{/if}
									</div>
									<!-- Bottom row: description + last seen -->
									{#if ev.description || lastSeen}
										<div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
											{#if ev.description}
												<span style="font-size: 10.5px; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1;">{ev.description}</span>
											{/if}
											{#if lastSeen}
												<span style="font-size: 9.5px; color: var(--text-muted); flex-shrink: 0; white-space: nowrap;">{lastSeen}</span>
											{/if}
										</div>
									{/if}
								</button>
							{/each}
						</div>
					</div>
				{/if}
			{/each}
		{:else}
			<!-- By Source mode -->
			{#each eventsBySource as group (group.source.source_id)}
				{@const color = sourceHexColor(group.source.source_type, group.source.source_name)}
				<div style="margin-bottom: 32px;">
					<div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px;">
						<span style="font-size: 10px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: {color};">
							{group.source.source_name}
						</span>
						<span style="font-size: 10px; color: var(--text-muted); background: var(--bg-base); border: 1px solid var(--border); padding: 2px 8px; border-radius: 3px;">
							{group.source.total_registrations} hooks · {group.source.source_type}
						</span>
					</div>
					<div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 8px;">
						{#each group.events as ev (ev.event_type)}
							{@const isSelected = ev.event_type === selectedEventType && drawerOpen}
							{@const isPulsing = activity.activePulseEvent === ev.event_type}
							{@const lastSeen = timeAgo(activity.lastSeenByEvent[ev.event_type])}
							<button
								onclick={() => selectEvent(ev.event_type)}
								style="
									display: flex; flex-direction: column; gap: 6px;
									padding: 14px 16px;
									background: var(--bg-base);
									border: 1.5px solid {isSelected ? color : 'var(--border)'};
									border-left: 3px solid {color};
									border-radius: 9px; cursor: pointer; text-align: left;
									opacity: {ev.total_registrations === 0 ? 0.45 : 1};
									transition: border-color 0.12s;
								"
								onmouseenter={(e) => {
									if (!isSelected) (e.currentTarget as HTMLElement).style.borderColor = color;
								}}
								onmouseleave={(e) => {
									if (!isSelected) (e.currentTarget as HTMLElement).style.borderColor = 'var(--border)';
								}}
							>
								<div style="display: flex; align-items: center; gap: 7px;">
									<span
										class={isPulsing ? 'live-pulse' : ''}
										style="width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; background: {isPulsing ? '#22c55e' : dotColor(ev)};"
									></span>
									<span style="flex: 1; font-size: 12px; font-family: 'DM Mono', 'JetBrains Mono', monospace; font-weight: 500; color: var(--text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
										{ev.event_type}
									</span>
									{#if ev.can_block}
										<svg width="9" height="9" viewBox="0 0 10 10" fill="none" style="flex-shrink:0;">
											<path d="M5 1.5L9 8H1L5 1.5Z" fill="var(--error)" />
										</svg>
									{/if}
									{#if ev.total_registrations > 0}
										<span style="font-size: 11px; font-family: 'DM Mono', monospace; color: var(--accent); font-weight: 600; flex-shrink: 0;">{ev.total_registrations}</span>
									{/if}
								</div>
								{#if ev.description || lastSeen}
									<div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
										{#if ev.description}
											<span style="font-size: 10.5px; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1;">{ev.description}</span>
										{/if}
										{#if lastSeen}
											<span style="font-size: 9.5px; color: var(--text-muted); flex-shrink: 0; white-space: nowrap;">{lastSeen}</span>
										{/if}
									</div>
								{/if}
							</button>
						{/each}
					</div>
				</div>
			{/each}
		{/if}

	</div>

	<!-- Drawer backdrop -->
	{#if drawerOpen}
		<div
			role="button"
			tabindex="-1"
			aria-label="Close drawer"
			onclick={closeDrawer}
			onkeydown={(e) => e.key === 'Enter' && closeDrawer()}
			style="position: fixed; inset: 0; background: rgba(0,0,0,0.18); z-index: 40; backdrop-filter: blur(1px); cursor: default;"
		></div>
	{/if}

	<!-- Event detail drawer -->
	<div
		bind:this={rightPanelEl}
		aria-modal="true"
		role="dialog"
		style="
			position: fixed; right: 0; top: 56px;
			height: calc(100vh - 56px); width: 440px;
			background: var(--bg-base);
			border-left: 1px solid var(--border);
			box-shadow: -12px 0 40px rgba(0,0,0,0.12);
			z-index: 50; overflow-y: auto;
			transform: translateX({drawerOpen ? '0' : '100%'});
			transition: transform 0.24s cubic-bezier(0.4, 0, 0.2, 1);
		"
	>
		{#if selectedEvent}
			<div style="padding: 24px 28px 48px;">
				<!-- Drawer header -->
				<div style="display: flex; align-items: flex-start; justify-content: space-between; margin-bottom: 18px;">
					<div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap; flex: 1; min-width: 0;">
						<h2 style="font-size: 20px; font-weight: 700; letter-spacing: -0.02em; font-family: 'DM Mono', 'JetBrains Mono', monospace; color: var(--text-primary); margin: 0;">
							{selectedEvent.event_type}
						</h2>
						{#if selectedEvent.phase}
							<span style="font-size: 11px; font-weight: 500; color: var(--text-secondary); background: var(--bg-subtle); border: 1px solid var(--border); border-radius: 4px; padding: 3px 8px; flex-shrink: 0;">
								{selectedEvent.phase}
							</span>
						{/if}
						{#if selectedEvent.can_block}
							<span style="display: inline-flex; align-items: center; gap: 4px; font-size: 10px; font-weight: 700; color: var(--error); background: var(--error-subtle); border: 1px solid rgba(209,78,43,0.25); border-radius: 4px; padding: 3px 8px; flex-shrink: 0;">
								<svg width="8" height="8" viewBox="0 0 10 10" fill="none"><path d="M5 1L9 8.5H1L5 1Z" fill="var(--error)" /></svg>
								CAN BLOCK
							</span>
						{/if}
					</div>
					<button
						onclick={closeDrawer}
						aria-label="Close"
						style="flex-shrink: 0; margin-left: 12px; margin-top: 2px; background: none; border: none; cursor: pointer; color: var(--text-muted); padding: 4px; border-radius: 4px; line-height: 1; font-size: 18px;"
					>✕</button>
				</div>

				<!-- Description -->
					{#if selectedEvent.description}
						<div
							style="
								background: var(--bg-base);
								border: 1px solid var(--border);
								border-radius: 6px;
								padding: 11px 16px;
								margin-bottom: 28px;
							"
						>
							<p
								style="font-size: 13px; font-style: italic; color: var(--text-secondary); line-height: 1.6; margin: 0;"
							>
								{selectedEvent.description}
							</p>
						</div>
					{/if}

					<!-- Registrations section -->
					<div style="margin-bottom: 28px;">
						<div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
							<span
								style="
									font-size: 11px; font-weight: 700; letter-spacing: 0.08em;
									text-transform: uppercase; color: var(--text-primary);
								"
							>
								Registrations
							</span>
							<span
								style="
									font-size: 11px; font-weight: 700;
									padding: 2px 8px; border-radius: 4px;
									background: {selectedEvent.total_registrations > 0 ? 'var(--accent)' : 'var(--bg-muted)'};
									color: {selectedEvent.total_registrations > 0 ? '#fff' : 'var(--text-muted)'};
								"
							>
								{selectedEvent.total_registrations}
							</span>
						</div>

						{#if selectedEvent.total_registrations === 0}
							<div
								style="
									border: 1.5px dashed var(--border);
									border-radius: 8px; padding: 32px 24px;
									text-align: center;
								"
							>
								<p
									style="font-size: 13px; color: var(--text-secondary); font-weight: 500; margin: 0 0 4px;"
								>
									No active registrations
								</p>
								<p style="font-size: 11px; color: var(--text-muted); margin: 0;">
									This event has no registered handlers
								</p>
								{#if selectedEvent.can_block}
									<p
										style="font-size: 11px; color: var(--error); margin: 12px 0 0; font-weight: 500;"
									>
										This hook can block execution when registered
									</p>
								{/if}
							</div>
						{:else}
							<div style="display: flex; flex-direction: column; gap: 10px;">
								{#each selectedEvent.registrations as reg}
									{@const color = sourceHexColor(reg.source_type, reg.source_name)}
									{@const symlink = isSymlink(reg.source_name, reg.script_filename)}
									<div
										style="
											background: var(--bg-base);
											border: 1px solid var(--border);
											border-left: 3px solid {color};
											border-radius: 7px;
											padding: 14px 16px;
										"
									>
										<!-- Card header -->
										<div
											style="
												display: flex; align-items: center; gap: 8px;
												flex-wrap: wrap;
												margin-bottom: 12px;
											"
										>
											<span
												style="font-size: 13px; font-weight: 600; color: var(--text-primary);"
											>
												{reg.source_name}
											</span>
											<span
												style="
													font-size: 10px; font-weight: 500;
													padding: 2px 7px; border-radius: 3px;
													{reg.source_type === 'global'
														? 'background: rgba(232,124,58,0.1); color: #C07030; border: 1px solid rgba(232,124,58,0.3);'
														: 'background: rgba(74,126,187,0.1); color: #4A7EBB; border: 1px solid rgba(74,126,187,0.3);'}
												"
											>
												{reg.source_type}
											</span>
											{#if reg.script_filename}
												<span style="color: var(--text-muted); font-size: 11px;">·</span>
												<button
													class="script-btn"
													onclick={() => toggleScript(reg.script_filename!)}
													title="View source"
												>
													{reg.script_filename}
												</button>
												<span
													style="
														font-size: 10px; font-weight: 500;
														padding: 2px 7px; border-radius: 3px;
														{reg.script_language.toLowerCase() === 'python'
															? 'background: rgba(59,115,172,0.1); color: #3B73AC;'
															: 'background: var(--bg-muted); color: var(--text-muted);'}
													"
												>
													{langLabel(reg.script_language)}
												</span>
												{#if symlink}
													<span
														style="font-size: 10px; color: var(--text-muted); font-style: italic;"
													>
														symlink
													</span>
												{/if}
											{/if}
										</div>

										<!-- Command -->
										<div style="margin-bottom: 10px;">
											<span
												style="
													display: block;
													font-size: 9px; font-weight: 700;
													letter-spacing: 0.12em; text-transform: uppercase;
													color: var(--text-muted);
													margin-bottom: 5px;
												"
											>
												Command
											</span>
											<div style="position: relative;">
												<pre
													style="
														font-family: 'DM Mono', 'JetBrains Mono', monospace;
														font-size: 11px; color: var(--text-secondary);
														background: var(--bg-subtle);
														border: 1px solid var(--border);
														border-radius: 4px; padding: 9px 40px 9px 12px;
														margin: 0; word-break: break-all; white-space: pre-wrap;
													">{reg.command}</pre>
												<button
													onclick={async () => {
														await navigator.clipboard.writeText(reg.command);
														const btn = document.activeElement as HTMLElement;
														const orig = btn.textContent;
														btn.textContent = '✓';
														setTimeout(() => { if (btn) btn.textContent = orig; }, 1600);
													}}
													title="Copy command"
													style="
														position: absolute; top: 6px; right: 6px;
														background: var(--bg-base); border: 1px solid var(--border);
														border-radius: 4px; padding: 3px 6px;
														cursor: pointer; font-size: 10px; color: var(--text-muted);
														line-height: 1;
													"
												>⎘</button>
											</div>
										</div>

										<!-- Meta row -->
										<div
											style="display: flex; align-items: center; gap: 14px; flex-wrap: wrap;"
										>
											{#if reg.timeout_ms}
												<span
													style="display: flex; align-items: center; gap: 4px; font-size: 11px; color: var(--text-muted);"
												>
													<svg width="11" height="11" viewBox="0 0 11 11" fill="none">
														<circle
															cx="5.5"
															cy="5.5"
															r="4.5"
															stroke="currentColor"
															stroke-width="1.2"
														/>
														<path
															d="M5.5 3v2.5l1.5 1"
															stroke="currentColor"
															stroke-width="1.2"
															stroke-linecap="round"
														/>
													</svg>
													timeout:
													<span
														style="font-family: 'DM Mono', 'JetBrains Mono', monospace; color: var(--text-secondary);"
													>
														{reg.timeout_ms}ms
													</span>
												</span>
											{/if}
											{#if reg.matcher && reg.matcher !== '*'}
												<span style="font-size: 11px; color: var(--text-muted);">
													matcher:
													<span
														style="font-family: 'DM Mono', 'JetBrains Mono', monospace; color: var(--text-secondary);"
													>
														{reg.matcher}
													</span>
												</span>
											{/if}
											{#if reg.can_block}
												<span
													style="font-size: 11px; color: var(--error); font-weight: 500;"
												>
													can block execution
												</span>
											{/if}
										</div>

										<!-- Script source viewer -->
										{#if reg.script_filename && expandedScript === reg.script_filename}
											<div style="margin-top: 12px; border-top: 1px solid var(--border); padding-top: 12px;">
												<div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
													<span style="font-size: 9px; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; color: var(--text-muted);">
														Source
													</span>
													<button
														onclick={() => { expandedScript = null; scriptContent = null; }}
														style="font-size: 10px; color: var(--text-muted); background: none; border: none; cursor: pointer; padding: 0;"
													>
														collapse ↑
													</button>
												</div>
												{#if scriptLoading}
													<div style="font-size: 11px; color: var(--text-muted); padding: 8px 0;">Loading…</div>
												{:else if scriptContent}
													<div style="position: relative;">
														<pre style="
															font-family: 'DM Mono', 'JetBrains Mono', monospace;
															font-size: 10.5px; line-height: 1.6;
															color: var(--text-secondary);
															background: var(--bg-subtle);
															border: 1px solid var(--border);
															border-radius: 5px;
															padding: 12px 14px;
															margin: 0;
															overflow-x: auto;
															white-space: pre;
															max-height: 400px;
															overflow-y: auto;
														">{scriptContent}</pre>
														<button
															onclick={copyScript}
															title="Copy to clipboard"
															style="
																position: absolute; top: 7px; right: 7px;
																background: var(--bg-base); border: 1px solid var(--border);
																border-radius: 5px; padding: 4px 8px;
																cursor: pointer; display: flex; align-items: center; gap: 4px;
																font-size: 10px; color: {scriptCopied ? '#22c55e' : 'var(--text-muted)'};
																transition: color 0.15s, border-color 0.15s;
															"
														>
															{#if scriptCopied}
																<svg width="11" height="11" viewBox="0 0 12 12" fill="none">
																	<path d="M2 6l3 3 5-5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
																</svg>
																copied
															{:else}
																<svg width="11" height="11" viewBox="0 0 12 12" fill="none">
																	<rect x="4" y="1" width="7" height="7" rx="1.2" stroke="currentColor" stroke-width="1.2"/>
																	<path d="M8 8v1.8A1.2 1.2 0 016.8 11H1.2A1.2 1.2 0 010 9.8V4.2A1.2 1.2 0 011.2 3H3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
																</svg>
																copy
															{/if}
														</button>
													</div>
												{/if}
											</div>
										{/if}
									</div>
								{/each}
							</div>
						{/if}
					</div>

					<!-- ── Contextual Activity Panels ──────────────────────────────── -->

					<!-- B: SessionEnd — reason breakdown -->
					{#if selectedEvent.event_type === 'SessionEnd'}
						<div style="margin-bottom: 28px;">
							<div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
								<span style="font-size: 11px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-primary);">
									Session Activity
								</span>
							</div>
							<div style="background: var(--bg-base); border: 1px solid var(--border); border-radius: 8px; padding: 16px 18px;">
								<div style="display: flex; align-items: baseline; gap: 6px; margin-bottom: 12px;">
									<span style="font-size: 28px; font-weight: 700; color: var(--text-primary); font-family: 'JetBrains Mono', monospace; line-height: 1;">
										{activity.totalSessions.toLocaleString()}
									</span>
									<span style="font-size: 12px; color: var(--text-muted);">total sessions ended</span>
								</div>
								{#if Object.keys(activity.endReasons).length > 0}
									<div style="font-size: 10px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 8px;">
										End reasons (tracked sessions)
									</div>
									<div style="display: flex; flex-direction: column; gap: 6px;">
										{#each Object.entries(activity.endReasons).sort((a, b) => b[1] - a[1]) as [reason, count]}
											{@const label = END_REASON_LABELS[reason] ?? reason}
											{@const max = Math.max(...Object.values(activity.endReasons))}
											<div style="display: flex; align-items: center; gap: 8px;">
												<span style="font-size: 11px; color: var(--text-secondary); min-width: 120px;">{label}</span>
												<div style="flex: 1; height: 4px; background: var(--bg-muted); border-radius: 2px; overflow: hidden;">
													<div style="height: 100%; width: {(count / max) * 100}%; background: var(--accent); border-radius: 2px;"></div>
												</div>
												<span style="font-size: 11px; font-family: 'JetBrains Mono', monospace; color: var(--text-muted); min-width: 16px; text-align: right;">{count}</span>
											</div>
										{/each}
									</div>
								{:else}
									<p style="font-size: 12px; color: var(--text-muted); margin: 0;">No end reasons recorded in tracked sessions yet.</p>
								{/if}
							</div>
						</div>
					{/if}

					<!-- C: SubagentStart / SubagentStop — invocation stats -->
					{#if selectedEvent.event_type === 'SubagentStart' || selectedEvent.event_type === 'SubagentStop'}
						<div style="margin-bottom: 28px;">
							<div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
								<span style="font-size: 11px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-primary);">
									Subagent Activity
								</span>
							</div>
							<div style="background: var(--bg-base); border: 1px solid var(--border); border-radius: 8px; padding: 16px 18px;">
								<div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; margin-bottom: {Object.keys(activity.subagentStats.byType).length > 0 ? '16px' : '0'};">
									<div>
										<div style="font-size: 22px; font-weight: 700; color: var(--text-primary); font-family: 'JetBrains Mono', monospace; line-height: 1;">
											{activity.subagentStats.totalInvocations.toLocaleString()}
										</div>
										<div style="font-size: 11px; color: var(--text-muted); margin-top: 3px;">all-time spawns</div>
									</div>
									<div>
										<div style="font-size: 22px; font-weight: 700; color: var(--text-primary); font-family: 'JetBrains Mono', monospace; line-height: 1;">
											{activity.subagentStats.trackedTotal}
										</div>
										<div style="font-size: 11px; color: var(--text-muted); margin-top: 3px;">in tracked sessions</div>
									</div>
									<div>
										<div style="font-size: 22px; font-weight: 700; color: var(--text-primary); font-family: 'JetBrains Mono', monospace; line-height: 1;">
											{activity.subagentStats.sessionsWithAgents}
										</div>
										<div style="font-size: 11px; color: var(--text-muted); margin-top: 3px;">sessions with agents</div>
									</div>
								</div>
								{#if Object.keys(activity.subagentStats.byType).length > 0}
									<div style="border-top: 1px solid var(--border); padding-top: 12px;">
										<div style="font-size: 10px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-muted); margin-bottom: 8px;">
											By type
										</div>
										<div style="display: flex; flex-wrap: wrap; gap: 6px;">
											{#each Object.entries(activity.subagentStats.byType).sort((a, b) => b[1] - a[1]) as [type, count]}
												<span style="font-size: 11px; padding: 3px 10px; background: var(--bg-subtle); border: 1px solid var(--border); border-radius: 4px; color: var(--text-secondary);">
													{type} <span style="font-family: 'JetBrains Mono', monospace; color: var(--accent);">{count}</span>
												</span>
											{/each}
										</div>
									</div>
								{/if}
							</div>
						</div>
					{/if}

					<!-- D: Notification / PermissionRequest — recent messages -->
					{#if selectedEvent.event_type === 'Notification' || selectedEvent.event_type === 'PermissionRequest'}
						<div style="margin-bottom: 28px;">
							<div style="display: flex; align-items: center; gap: 8px; margin-bottom: 12px;">
								<span style="font-size: 11px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-primary);">
									Recent Messages
								</span>
							</div>
							{#if activity.recentNotifications.length > 0}
								<div style="display: flex; flex-direction: column; gap: 8px;">
									{#each activity.recentNotifications as notif}
										{@const href = notif.projectEncodedName && notif.slug ? `/projects/${notif.projectEncodedName}/${notif.slug}` : null}
										<div style="background: var(--bg-base); border: 1px solid var(--border); border-left: 3px solid var(--accent); border-radius: 7px; padding: 10px 14px;">
											<p style="font-size: 12px; color: var(--text-primary); margin: 0 0 6px; line-height: 1.5;">{notif.message}</p>
											<div style="display: flex; align-items: center; gap: 8px;">
												{#if href}
													<a {href} style="font-size: 10px; font-family: 'DM Mono', 'JetBrains Mono', monospace; color: var(--accent); text-decoration: none;" onmouseenter={(e) => (e.currentTarget.style.textDecoration = 'underline')} onmouseleave={(e) => (e.currentTarget.style.textDecoration = 'none')}>
														{notif.slug}
													</a>
												{:else}
													<span style="font-size: 10px; font-family: 'DM Mono', monospace; color: var(--text-muted);">{notif.sessionId.slice(0, 8)}</span>
												{/if}
												<span style="font-size: 10px; color: var(--text-muted);">{timeAgo(notif.updatedAt)}</span>
											</div>
										</div>
									{/each}
								</div>
							{:else}
								<div style="border: 1.5px dashed var(--border); border-radius: 8px; padding: 20px 24px; text-align: center;">
									<p style="font-size: 12px; color: var(--text-muted); margin: 0;">No notification messages in tracked sessions.</p>
								</div>
							{/if}
						</div>
					{/if}

					<!-- Event Schema (collapsible, lazy-loaded) -->
					{#if detailLoading}
						<div
							style="
								background: var(--bg-base); border: 1px solid var(--border);
								border-radius: 8px; padding: 13px 18px;
								font-size: 11px; color: var(--text-muted);
								margin-bottom: 28px;
							"
						>
							Loading schema…
						</div>
					{:else if detailData?.schema_info}
						{@const schema = detailData.schema_info}
						<div
							style="
								background: var(--bg-base);
								border: 1px solid var(--border);
								border-radius: 8px; overflow: hidden;
								margin-bottom: 28px;
							"
						>
							<!-- Toggle row -->
							<button
								onclick={() => (schemaExpanded = !schemaExpanded)}
								style="
									width: 100%; display: flex; align-items: center; justify-content: space-between;
									padding: 13px 18px; cursor: pointer;
									background: transparent; border: none; text-align: left;
								"
							>
								<span
									style="
										font-size: 11px; font-weight: 700; letter-spacing: 0.08em;
										text-transform: uppercase; color: var(--text-primary);
									"
								>
									Event Schema
								</span>
								<span
									style="
										font-size: 16px; color: var(--text-muted);
										display: inline-block;
										transform: {schemaExpanded ? 'rotate(90deg)' : 'rotate(0deg)'};
										transition: transform 0.18s ease;
									"
								>
									›
								</span>
							</button>

							{#if schemaExpanded}
								<div
									style="
										border-top: 1px solid var(--border);
										padding: 18px 18px 20px;
									"
								>
									<!-- Input Fields -->
									{#if schema.input_fields.length > 0}
										<div style="margin-bottom: 18px;">
											<div
												style="
													font-size: 10px; font-weight: 600; letter-spacing: 0.1em;
													text-transform: uppercase; color: var(--text-muted);
													margin-bottom: 8px;
												"
											>
												Input Fields
											</div>
											<div
												style="border: 1px solid var(--border); border-radius: 5px; overflow: hidden;"
											>
												<div
													style="
														display: grid; grid-template-columns: 100px 72px 58px 1fr;
														padding: 6px 12px;
														background: var(--bg-subtle);
														border-bottom: 1px solid var(--border);
													"
												>
													{#each ['Field', 'Type', 'Required', 'Description'] as h}
														<span
															style="font-size: 10px; font-weight: 600; color: var(--text-muted);"
															>{h}</span
														>
													{/each}
												</div>
												{#each schema.input_fields as field}
													<div
														style="
															display: grid; grid-template-columns: 100px 72px 58px 1fr;
															padding: 9px 12px;
															border-bottom: 1px solid var(--border);
															align-items: start;
														"
													>
														<span
															style="font-family: 'DM Mono', 'JetBrains Mono', monospace; font-size: 11px; font-weight: 500; color: var(--text-primary);"
															>{field.name}</span
														>
														<span
															style="font-family: 'DM Mono', 'JetBrains Mono', monospace; font-size: 11px; color: var(--accent);"
															>{field.type}</span
														>
														<span>
															{#if field.required}
																<span
																	style="font-size: 10px; font-weight: 600; background: rgba(42,138,80,0.1); color: #2A8A50; border-radius: 3px; padding: 2px 7px;"
																	>required</span
																>
															{:else}
																<span
																	style="font-size: 10px; font-weight: 600; background: var(--bg-subtle); color: var(--text-muted); border-radius: 3px; padding: 2px 7px;"
																	>optional</span
																>
															{/if}
														</span>
														<span
															style="font-size: 11px; color: var(--text-secondary); line-height: 1.5;"
															>{field.description || '—'}</span
														>
													</div>
												{/each}
											</div>
										</div>
									{/if}

									<!-- Output Fields -->
									{#if schema.output_fields.length > 0}
										<div style="margin-bottom: 18px;">
											<div
												style="
													font-size: 10px; font-weight: 600; letter-spacing: 0.1em;
													text-transform: uppercase; color: var(--text-muted);
													margin-bottom: 8px;
												"
											>
												Output Fields
											</div>
											<div
												style="border: 1px solid var(--border); border-radius: 5px; overflow: hidden;"
											>
												<div
													style="display: grid; grid-template-columns: 100px 72px 58px 1fr; padding: 6px 12px; background: var(--bg-subtle); border-bottom: 1px solid var(--border);"
												>
													{#each ['Field', 'Type', 'Required', 'Description'] as h}
														<span
															style="font-size: 10px; font-weight: 600; color: var(--text-muted);"
															>{h}</span
														>
													{/each}
												</div>
												{#each schema.output_fields as field}
													<div
														style="display: grid; grid-template-columns: 100px 72px 58px 1fr; padding: 9px 12px; border-bottom: 1px solid var(--border); align-items: start;"
													>
														<span
															style="font-family: 'DM Mono', 'JetBrains Mono', monospace; font-size: 11px; font-weight: 500; color: var(--text-primary);"
															>{field.name}</span
														>
														<span
															style="font-family: 'DM Mono', 'JetBrains Mono', monospace; font-size: 11px; color: var(--accent);"
															>{field.type}</span
														>
														<span>
															{#if field.required}
																<span
																	style="font-size: 10px; font-weight: 600; background: rgba(42,138,80,0.1); color: #2A8A50; border-radius: 3px; padding: 2px 7px;"
																	>required</span
																>
															{:else}
																<span
																	style="font-size: 10px; font-weight: 600; background: var(--bg-subtle); color: var(--text-muted); border-radius: 3px; padding: 2px 7px;"
																	>optional</span
																>
															{/if}
														</span>
														<span
															style="font-size: 11px; color: var(--text-secondary); line-height: 1.5;"
															>{field.description || '—'}</span
														>
													</div>
												{/each}
											</div>
										</div>
									{/if}

									<!-- Base Fields -->
									{#if schema.base_fields.length > 0}
										<div>
											<div
												style="
													font-size: 10px; font-weight: 600; letter-spacing: 0.1em;
													text-transform: uppercase; color: var(--text-muted);
													margin-bottom: 8px;
												"
											>
												Base Fields
												<span
													style="font-weight: 400; text-transform: none; letter-spacing: 0;"
												>
													— all hooks share these
												</span>
											</div>
											<div
												style="border: 1px solid var(--border); border-radius: 5px; overflow: hidden;"
											>
												<div
													style="display: grid; grid-template-columns: 100px 72px 58px 1fr; padding: 6px 12px; background: var(--bg-subtle); border-bottom: 1px solid var(--border);"
												>
													{#each ['Field', 'Type', 'Required', 'Description'] as h}
														<span
															style="font-size: 10px; font-weight: 600; color: var(--text-muted);"
															>{h}</span
														>
													{/each}
												</div>
												{#each schema.base_fields as field}
													<div
														style="display: grid; grid-template-columns: 100px 72px 58px 1fr; padding: 9px 12px; border-bottom: 1px solid var(--border); align-items: start;"
													>
														<span
															style="font-family: 'DM Mono', 'JetBrains Mono', monospace; font-size: 11px; font-weight: 500; color: var(--text-primary);"
															>{field.name}</span
														>
														<span
															style="font-family: 'DM Mono', 'JetBrains Mono', monospace; font-size: 11px; color: var(--text-secondary);"
															>{field.type}</span
														>
														<span>
															{#if field.required}
																<span
																	style="font-size: 10px; font-weight: 600; background: rgba(42,138,80,0.1); color: #2A8A50; border-radius: 3px; padding: 2px 7px;"
																	>required</span
																>
															{:else}
																<span
																	style="font-size: 10px; font-weight: 600; background: var(--bg-subtle); color: var(--text-muted); border-radius: 3px; padding: 2px 7px;"
																	>optional</span
																>
															{/if}
														</span>
														<span
															style="font-size: 11px; color: var(--text-secondary); line-height: 1.5;"
															>{field.description || '—'}</span
														>
													</div>
												{/each}
											</div>
										</div>
									{/if}
								</div>
							{/if}
						</div>
					{/if}

					<!-- Related Events -->
					{#if relatedPrev || relatedNext}
						<div>
							<div
								style="
									font-size: 11px; font-weight: 700; letter-spacing: 0.08em;
									text-transform: uppercase; color: var(--text-primary);
									margin-bottom: 10px;
								"
							>
								Related Events
							</div>
							<div style="display: flex; gap: 8px; flex-wrap: wrap;">
								{#if relatedPrev}
									<button
										onclick={() => selectEvent(relatedPrev!.event_type)}
										style="
											display: flex; align-items: center; gap: 6px;
											background: var(--bg-base);
											border: 1px solid var(--border);
											border-radius: 6px; padding: 9px 16px;
											cursor: pointer;
											transition: border-color 0.15s;
										"
										onmouseenter={(e) =>
											((e.currentTarget as HTMLElement).style.borderColor =
												'var(--accent)')}
										onmouseleave={(e) =>
											((e.currentTarget as HTMLElement).style.borderColor = 'var(--border)')}
									>
										<svg width="14" height="14" viewBox="0 0 14 14" fill="none">
											<path
												d="M8.5 3L5 7l3.5 4"
												stroke="var(--text-muted)"
												stroke-width="1.5"
												stroke-linecap="round"
												stroke-linejoin="round"
											/>
										</svg>
										<span
											style="font-family: 'DM Mono', 'JetBrains Mono', monospace; font-size: 11px; font-weight: 500; color: var(--accent);"
										>
											{relatedPrev.event_type}
										</span>
									</button>
								{/if}
								{#if relatedNext}
									<button
										onclick={() => selectEvent(relatedNext!.event_type)}
										style="
											display: flex; align-items: center; gap: 6px;
											background: var(--bg-base);
											border: 1px solid var(--border);
											border-radius: 6px; padding: 9px 16px;
											cursor: pointer;
											transition: border-color 0.15s;
										"
										onmouseenter={(e) =>
											((e.currentTarget as HTMLElement).style.borderColor =
												'var(--accent)')}
										onmouseleave={(e) =>
											((e.currentTarget as HTMLElement).style.borderColor = 'var(--border)')}
									>
										<span
											style="font-family: 'DM Mono', 'JetBrains Mono', monospace; font-size: 11px; font-weight: 500; color: var(--accent);"
										>
											{relatedNext.event_type}
										</span>
										<svg width="14" height="14" viewBox="0 0 14 14" fill="none">
											<path
												d="M5.5 3L9 7l-3.5 4"
												stroke="var(--text-muted)"
												stroke-width="1.5"
												stroke-linecap="round"
												stroke-linejoin="round"
											/>
										</svg>
									</button>
								{/if}
							</div>
						</div>
					{/if}
				</div>
		{/if}
	</div>
</div>
