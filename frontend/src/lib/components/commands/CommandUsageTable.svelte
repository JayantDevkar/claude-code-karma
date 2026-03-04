<script lang="ts">
	import type { CommandUsage } from '$lib/api-types';
	import { getCommandCategoryColorVars, getCommandCategoryLabel } from '$lib/utils';
	import UsageTable from '$lib/components/shared/UsageTable.svelte';
	import type { UsageColumn } from '$lib/components/shared/UsageTable.svelte';

	interface Props {
		commands: CommandUsage[];
	}

	let { commands }: Props = $props();

	// Sort state
	let sortKey = $state<'name' | 'category' | 'uses' | 'sessions' | 'last'>('uses');
	let sortDir = $state<'asc' | 'desc'>('desc');

	const columns: UsageColumn[] = [
		{ key: 'name', label: 'Command' },
		{ key: 'category', label: 'Category' }
	];

	let sortedCommands = $derived.by(() => {
		const sorted = [...commands];
		sorted.sort((a, b) => {
			let cmp = 0;
			switch (sortKey) {
				case 'name':
					cmp = a.name.localeCompare(b.name);
					break;
				case 'category':
					cmp = (a.category ?? '').localeCompare(b.category ?? '');
					break;
				case 'uses':
					cmp = a.count - b.count;
					break;
				case 'sessions':
					cmp = (a.session_count ?? 0) - (b.session_count ?? 0);
					break;
				case 'last':
					cmp =
						(a.last_used ? new Date(a.last_used).getTime() : 0) -
						(b.last_used ? new Date(b.last_used).getTime() : 0);
					break;
			}
			return sortDir === 'desc' ? -cmp : cmp;
		});
		return sorted;
	});

	function toggleSort(key: string) {
		const k = key as typeof sortKey;
		if (sortKey === k) {
			sortDir = sortDir === 'desc' ? 'asc' : 'desc';
		} else {
			sortKey = k;
			sortDir = 'desc';
		}
	}
</script>

<UsageTable
	items={sortedCommands}
	getKey={(c) => c.name}
	{columns}
	{sortKey}
	{sortDir}
	onToggleSort={toggleSort}
>
	{#snippet customCells(command)}
		{@const catColors = getCommandCategoryColorVars(command.category ?? 'user_command')}
		<td class="px-4 py-3">
			<div class="flex items-center gap-2.5">
				<span
					class="w-2 h-2 rounded-full flex-shrink-0"
					style="background-color: {catColors.color};"
				></span>
				<a
					href="/commands/{encodeURIComponent(command.name)}"
					class="font-medium text-[var(--text-primary)] hover:text-[var(--accent)] transition-colors"
				>
					/{command.name}
				</a>
			</div>
		</td>
		<td class="px-4 py-3">
			<span
				class="inline-flex items-center px-2 py-0.5 text-[10px] font-medium rounded-full"
				style="color: {catColors.color}; background-color: {catColors.subtle};"
			>
				{getCommandCategoryLabel(command.category ?? 'user_command')}
			</span>
		</td>
	{/snippet}
</UsageTable>
