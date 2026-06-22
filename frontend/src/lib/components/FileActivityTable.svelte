<script lang="ts">
	import {
		FileIcon,
		FilePlusIcon,
		FilePenIcon,
		FileMinusIcon,
		SearchIcon,
		BotIcon,
		Copy,
		ExternalLink,
		X
	} from 'lucide-svelte';
	import type { FileActivity, FileOperation } from '$lib/api-types';
	import {
		formatDate,
		formatDisplayPath,
		copyToClipboard,
		getSubagentColorVars
	} from '$lib/utils';

	interface Props {
		activities: FileActivity[];
		projectPath?: string | null;
		currentAgentId?: string | null;
		subagentTypes?: Record<string, string | null>;
		class?: string;
	}

	let {
		activities,
		projectPath = null,
		currentAgentId = null,
		subagentTypes = {},
		class: className = ''
	}: Props = $props();

	let filterQuery = $state('');
	let activeOps = $state<Set<FileOperation>>(new Set());

	let showToast = $state(false);

	const operationConfig: Record<FileOperation, { icon: typeof FileIcon; label: string; color: string; bgColor: string; borderColor: string }> = {
		read:   { icon: FileIcon,      label: 'Read',   color: 'text-blue-500',   bgColor: 'bg-blue-500/10',   borderColor: 'border-blue-500/30' },
		write:  { icon: FilePlusIcon,  label: 'Write',  color: 'text-green-500',  bgColor: 'bg-green-500/10',  borderColor: 'border-green-500/30' },
		edit:   { icon: FilePenIcon,   label: 'Edit',   color: 'text-amber-500',  bgColor: 'bg-amber-500/10',  borderColor: 'border-amber-500/30' },
		delete: { icon: FileMinusIcon, label: 'Delete', color: 'text-red-500',    bgColor: 'bg-red-500/10',    borderColor: 'border-red-500/30' },
		search: { icon: SearchIcon,    label: 'Search', color: 'text-purple-500', bgColor: 'bg-purple-500/10', borderColor: 'border-purple-500/30' }
	};

	// Which op types actually exist in the data
	const presentOps = $derived(
		[...new Set(activities.map(a => a.operation))] as FileOperation[]
	);

	function toggleOp(op: FileOperation) {
		const next = new Set(activeOps);
		if (next.has(op)) next.delete(op);
		else next.add(op);
		activeOps = next;
	}

	const filteredActivities = $derived.by(() => {
		return activities.filter(a => {
			const matchesOp = activeOps.size === 0 || activeOps.has(a.operation);
			const q = filterQuery.toLowerCase();
			const matchesQuery = !q ||
				a.path.toLowerCase().includes(q) ||
				a.operation.toLowerCase().includes(q) ||
				a.actor.toLowerCase().includes(q);
			return matchesOp && matchesQuery;
		});
	});

	async function handleCopyPath(path: string) {
		const success = await copyToClipboard(path);
		if (success) {
			showToast = true;
			setTimeout(() => { showToast = false; }, 2000);
		}
	}

	function handleOpenInEditor(path: string) {
		window.open(`vscode://file/${path}`, '_blank');
	}

	// Format just the time portion (HH:MM AM/PM)
	function formatTime(ts: string): string {
		return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
	}
</script>

<div class="flex flex-col gap-3 {className}">

	<!-- Search -->
	<div class="relative">
		<SearchIcon class="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[var(--text-muted)]" />
		<input
			type="text"
			placeholder="Search files…"
			bind:value={filterQuery}
			class="w-full rounded-lg border border-[var(--border)] bg-[var(--bg-base)] py-1.5 pl-8 pr-8 text-xs focus:outline-none focus:ring-1 focus:ring-[var(--accent)] placeholder:text-[var(--text-faint)]"
		/>
		{#if filterQuery}
			<button onclick={() => (filterQuery = '')} class="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--text-muted)] hover:text-[var(--text-primary)]">
				<X class="h-3 w-3" />
			</button>
		{/if}
	</div>

	<!-- Operation filter chips -->
	{#if presentOps.length > 1}
		<div class="flex flex-wrap gap-1.5">
			{#each presentOps as op}
				{@const cfg = operationConfig[op]}
				{@const count = activities.filter(a => a.operation === op).length}
				{@const active = activeOps.has(op)}
				<button
					onclick={() => toggleOp(op)}
					class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium transition-all
						{active
							? `${cfg.bgColor} ${cfg.borderColor} ${cfg.color}`
							: 'border-[var(--border)] bg-[var(--bg-base)] text-[var(--text-muted)] hover:border-[var(--border-hover)] hover:text-[var(--text-secondary)]'
						}"
				>
					<cfg.icon class="h-3 w-3" />
					{cfg.label}
					<span class="font-mono opacity-60">{count}</span>
				</button>
			{/each}
			{#if activeOps.size > 0}
				<button
					onclick={() => (activeOps = new Set())}
					class="inline-flex items-center gap-1 rounded-full border border-[var(--border)] px-2 py-1 text-[11px] text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
				>
					<X class="h-3 w-3" /> Clear
				</button>
			{/if}
		</div>
	{/if}

	<!-- Count -->
	<div class="flex items-center justify-between px-0.5">
		<span class="text-[10px] uppercase tracking-wide text-[var(--text-muted)] font-medium">
			{filteredActivities.length} {filteredActivities.length === 1 ? 'operation' : 'operations'}
			{#if activeOps.size > 0 || filterQuery} <span class="opacity-50">filtered</span>{/if}
		</span>
	</div>

	<!-- File list -->
	<div class="flex flex-col rounded-lg border border-[var(--border)]/60 overflow-hidden bg-[var(--bg-base)]">
		{#each filteredActivities as activity, i}
			{@const cfg = operationConfig[activity.operation] || operationConfig.read}
			{@const displayPath = formatDisplayPath(activity.path, projectPath)}
			{@const filename = displayPath.split('/').pop() ?? displayPath}
			{@const dirPath = displayPath.includes('/') ? displayPath.slice(0, displayPath.lastIndexOf('/')) : ''}
			{@const isSubagent = activity.actor_type === 'subagent' && (!currentAgentId || activity.actor !== currentAgentId)}
			{@const colorVars = isSubagent ? getSubagentColorVars(subagentTypes[activity.actor]) : null}

			<div class="group flex items-stretch gap-2.5 px-3 py-2.5 {i > 0 ? 'border-t border-[var(--border)]/40' : ''} hover:bg-[var(--bg-subtle)]">
				<!-- Op icon -->
				<div class="mt-0.5 shrink-0 rounded-md p-1.5 self-start {cfg.bgColor}">
					<cfg.icon class="h-3.5 w-3.5 {cfg.color}" />
				</div>

				<!-- Info (fills remaining width) -->
				<div class="flex-1 min-w-0">
					<span class="text-xs font-medium text-[var(--text-primary)] truncate block">{filename}</span>
					<div class="mt-0.5 flex items-center gap-1.5 min-w-0">
						{#if dirPath}
							<span class="text-[10px] text-[var(--text-muted)] font-mono truncate" title={activity.path}>{dirPath}</span>
						{/if}
						<span class="shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium capitalize {cfg.bgColor} {cfg.color}">{activity.operation}</span>
						{#if isSubagent && colorVars}
							<BotIcon class="shrink-0 h-3 w-3" style="color: {colorVars.color}" />
						{/if}
					</div>
				</div>

				<!-- Right column: time top, actions bottom on hover -->
				<div class="shrink-0 flex flex-col items-end justify-between">
					<span class="font-mono text-[10px] text-[var(--text-muted)]">{formatTime(activity.timestamp)}</span>
					<div class="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
						<button onclick={() => handleCopyPath(activity.path)} class="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-muted)]" title="Copy path"><Copy class="h-3 w-3" /></button>
						<button onclick={() => handleOpenInEditor(activity.path)} class="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-muted)]" title="Open in editor"><ExternalLink class="h-3 w-3" /></button>
					</div>
				</div>
			</div>
		{:else}
			<div class="px-3 py-10 text-center text-xs text-[var(--text-muted)]">
				{#if activeOps.size > 0 || filterQuery}
					No operations match your filter
				{:else}
					No file activity
				{/if}
			</div>
		{/each}
	</div>
</div>

{#if showToast}
	<div class="fixed bottom-4 left-1/2 -translate-x-1/2 px-4 py-2 bg-[var(--text-primary)] text-[var(--bg-base)] text-xs font-medium rounded-lg shadow-lg">
		Path copied
	</div>
{/if}
