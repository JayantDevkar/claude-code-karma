<script lang="ts">
	import {
		FileIcon,
		FilePlusIcon,
		FilePenIcon,
		FileMinusIcon,
		SearchIcon,
		BotIcon,
		UserIcon,
		ChevronUp,
		ChevronDown,
		Copy,
		ExternalLink
	} from 'lucide-svelte';
	import type { FileActivity, FileOperation } from '$lib/api-types';
	import {
		formatDate,
		truncate,
		formatDisplayPath,
		copyToClipboard,
		getSubagentColorVars
	} from '$lib/utils';

	interface Props {
		activities: FileActivity[];
		projectPath?: string | null;
		/** Current agent ID - when set, activities from this agent won't show subagent badges */
		currentAgentId?: string | null;
		/** Map of agent_id to subagent_type for color lookup */
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

	// Sort state
	type SortField = 'timestamp' | 'path' | 'operation' | 'actor';
	type SortOrder = 'asc' | 'desc';

	let sortField = $state<SortField>('timestamp');
	let sortOrder = $state<SortOrder>('asc');
	let filterQuery = $state('');

	// Toast state for copy feedback
	let showToast = $state(false);
	let toastMessage = $state('');

	// Operation icons and colors
	const operationConfig: Record<
		FileOperation,
		{ icon: typeof FileIcon; color: string; bgColor: string }
	> = {
		read: { icon: FileIcon, color: 'text-blue-400', bgColor: 'bg-blue-500/20' },
		write: { icon: FilePlusIcon, color: 'text-green-400', bgColor: 'bg-green-500/20' },
		edit: { icon: FilePenIcon, color: 'text-yellow-400', bgColor: 'bg-yellow-500/20' },
		delete: { icon: FileMinusIcon, color: 'text-red-400', bgColor: 'bg-red-500/20' },
		search: { icon: SearchIcon, color: 'text-purple-400', bgColor: 'bg-purple-500/20' }
	};

	// Sorted and filtered activities
	let sortedActivities = $derived.by(() => {
		let filtered = activities;

		// Apply filter
		if (filterQuery) {
			const lowerFilter = filterQuery.toLowerCase();
			filtered = activities.filter(
				(a) =>
					a.path.toLowerCase().includes(lowerFilter) ||
					a.actor.toLowerCase().includes(lowerFilter) ||
					a.operation.toLowerCase().includes(lowerFilter) ||
					a.tool_name.toLowerCase().includes(lowerFilter)
			);
		}

		// Apply sort
		return [...filtered].sort((a, b) => {
			let cmp = 0;
			switch (sortField) {
				case 'timestamp':
					cmp = new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
					break;
				case 'path':
					cmp = a.path.localeCompare(b.path);
					break;
				case 'operation':
					cmp = a.operation.localeCompare(b.operation);
					break;
				case 'actor':
					cmp = a.actor.localeCompare(b.actor);
					break;
			}
			return sortOrder === 'asc' ? cmp : -cmp;
		});
	});

	function handleSort(field: SortField) {
		if (sortField === field) {
			sortOrder = sortOrder === 'asc' ? 'desc' : 'asc';
		} else {
			sortField = field;
			sortOrder = 'asc';
		}
	}

	async function handleCopyPath(path: string) {
		const success = await copyToClipboard(path);
		if (success) {
			toastMessage = 'Path copied to clipboard';
			showToast = true;
			setTimeout(() => {
				showToast = false;
			}, 2000);
		}
	}

	function handleOpenInEditor(path: string) {
		// Use VS Code protocol to open file
		window.open(`vscode://file/${path}`, '_blank');
	}
</script>

<div
	class="
		rounded-lg border border-[var(--border)]
		bg-[var(--bg-subtle)]
		{className}
	"
>
	<!-- Header with search -->
	<div class="border-b border-[var(--border)] p-4">
		<div class="flex items-center gap-4">
			<div class="relative flex-1">
				<SearchIcon
					class="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]"
				/>
				<input
					type="text"
					placeholder="Filter by path, actor, or operation..."
					bind:value={filterQuery}
					class="
						w-full rounded-md border border-[var(--border)]
						bg-[var(--bg-base)]
						py-2 pl-10 pr-4 text-sm
						focus:outline-none focus:ring-2 focus:ring-[var(--accent)]
						placeholder:text-[var(--text-faint)]
					"
				/>
			</div>
			<span class="text-sm text-[var(--text-muted)]">
				{sortedActivities.length} operations
			</span>
		</div>
	</div>

	<!-- Table -->
	<div class="overflow-x-auto">
		<table class="w-full">
			<thead>
				<tr class="border-b border-[var(--border)] bg-[var(--bg-muted)]/30">
					<th
						class="cursor-pointer px-4 py-3 text-left text-xs font-medium text-[var(--text-muted)]"
						onclick={() => handleSort('timestamp')}
					>
						<div class="flex items-center gap-1">
							Time
							{#if sortField === 'timestamp'}
								{#if sortOrder === 'asc'}
									<ChevronUp class="h-4 w-4" />
								{:else}
									<ChevronDown class="h-4 w-4" />
								{/if}
							{/if}
						</div>
					</th>
					<th
						class="cursor-pointer px-4 py-3 text-left text-xs font-medium text-[var(--text-muted)]"
						onclick={() => handleSort('operation')}
					>
						<div class="flex items-center gap-1">
							Operation
							{#if sortField === 'operation'}
								{#if sortOrder === 'asc'}
									<ChevronUp class="h-4 w-4" />
								{:else}
									<ChevronDown class="h-4 w-4" />
								{/if}
							{/if}
						</div>
					</th>
					<th
						class="cursor-pointer px-4 py-3 text-left text-xs font-medium text-[var(--text-muted)]"
						onclick={() => handleSort('path')}
					>
						<div class="flex items-center gap-1">
							Path
							{#if sortField === 'path'}
								{#if sortOrder === 'asc'}
									<ChevronUp class="h-4 w-4" />
								{:else}
									<ChevronDown class="h-4 w-4" />
								{/if}
							{/if}
						</div>
					</th>
					<th
						class="cursor-pointer px-4 py-3 text-left text-xs font-medium text-[var(--text-muted)]"
						onclick={() => handleSort('actor')}
					>
						<div class="flex items-center gap-1">
							Actor
							{#if sortField === 'actor'}
								{#if sortOrder === 'asc'}
									<ChevronUp class="h-4 w-4" />
								{:else}
									<ChevronDown class="h-4 w-4" />
								{/if}
							{/if}
						</div>
					</th>
					<th class="px-4 py-3 text-left text-xs font-medium text-[var(--text-muted)]">
						Tool
					</th>
					<th class="px-4 py-3 text-left text-xs font-medium text-[var(--text-muted)]">
						Actions
					</th>
				</tr>
			</thead>
			<tbody>
				{#each sortedActivities as activity, i}
					{@const config = operationConfig[activity.operation] || operationConfig.read}
					<tr
						class="border-b border-[var(--border)] last:border-0 hover:bg-[var(--bg-muted)]/20"
					>
						<td
							class="whitespace-nowrap px-4 py-3 text-xs text-[var(--text-muted)] font-mono"
						>
							{formatDate(activity.timestamp)}
						</td>
						<td class="px-4 py-3">
							<div class="flex items-center gap-2">
								<config.icon class="h-4 w-4 {config.color}" />
								<span
									class="
										rounded-full px-2 py-0.5 text-xs capitalize
										{config.bgColor}
										{config.color}
									"
								>
									{activity.operation}
								</span>
							</div>
						</td>
						<td class="px-4 py-3">
							<code
								class="
									inline-block
									px-2 py-1
									font-mono text-xs
									text-[var(--text-primary)]
									bg-[var(--bg-muted)]
									border border-[var(--border)]
									rounded-md
								"
								title={activity.path}
							>
								{truncate(formatDisplayPath(activity.path, projectPath), 60)}
							</code>
						</td>
						<td class="px-4 py-3">
							<div class="flex items-center gap-1.5">
								{#if activity.actor_type === 'subagent' && (!currentAgentId || activity.actor !== currentAgentId)}
									{@const colorVars = getSubagentColorVars(
										subagentTypes[activity.actor]
									)}
									<!-- Show subagent badge for nested subagents (not the current agent being viewed) -->
									<BotIcon class="h-3.5 w-3.5" style="color: {colorVars.color}" />
									<span class="text-xs" style="color: {colorVars.color}"
										>{activity.actor}</span
									>
								{:else}
									<!-- Show main/session style for current agent or main session activities -->
									<UserIcon class="h-3.5 w-3.5 text-[var(--text-muted)]" />
									<span class="text-xs text-[var(--text-muted)]"
										>{activity.actor}</span
									>
								{/if}
							</div>
						</td>
						<td class="px-4 py-3">
							<span
								class="rounded bg-[var(--bg-muted)] px-1.5 py-0.5 text-xs font-mono"
							>
								{activity.tool_name}
							</span>
						</td>
						<td class="px-4 py-3">
							<div class="flex items-center gap-1">
								<button
									onclick={() => handleCopyPath(activity.path)}
									class="
										p-1.5 rounded
										text-[var(--text-muted)]
										hover:text-[var(--text-primary)]
										hover:bg-[var(--bg-muted)]
										transition-colors
									"
									title="Copy path"
								>
									<Copy class="h-3.5 w-3.5" />
								</button>
								<button
									onclick={() => handleOpenInEditor(activity.path)}
									class="
										p-1.5 rounded
										text-[var(--text-muted)]
										hover:text-[var(--text-primary)]
										hover:bg-[var(--bg-muted)]
										transition-colors
									"
									title="Open in Editor"
								>
									<ExternalLink class="h-3.5 w-3.5" />
								</button>
							</div>
						</td>
					</tr>
				{:else}
					<tr>
						<td
							colspan="6"
							class="px-4 py-8 text-center text-sm text-[var(--text-muted)]"
						>
							No file activity found
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
</div>

<!-- Toast notification -->
{#if showToast}
	<div
		class="
			fixed bottom-4 left-1/2 -translate-x-1/2
			px-4 py-2
			bg-[var(--text-primary)]
			text-[var(--bg-base)]
			text-sm font-medium
			rounded-lg
			shadow-lg
			animate-slide-up
		"
	>
		{toastMessage}
	</div>
{/if}
