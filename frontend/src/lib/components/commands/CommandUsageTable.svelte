<script lang="ts">
	import type { CommandUsage } from '$lib/api-types';
	import { formatDistanceToNow } from 'date-fns';
	import { getCommandCategoryColorVars, getCommandCategoryLabel } from '$lib/utils';

	interface Props {
		commands: CommandUsage[];
	}

	let { commands }: Props = $props();

	// Sort state
	let sortKey = $state<'name' | 'category' | 'uses' | 'sessions' | 'last'>('uses');
	let sortDir = $state<'asc' | 'desc'>('desc');

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

	function toggleSort(key: typeof sortKey) {
		if (sortKey === key) {
			sortDir = sortDir === 'desc' ? 'asc' : 'desc';
		} else {
			sortKey = key;
			sortDir = 'desc';
		}
	}

	function sortIndicator(key: typeof sortKey): string {
		if (sortKey !== key) return '';
		return sortDir === 'desc' ? ' ↓' : ' ↑';
	}
</script>

<div class="overflow-x-auto border border-[var(--border)] rounded-xl">
	<table class="w-full text-sm">
		<thead>
			<tr class="border-b border-[var(--border)] bg-[var(--bg-subtle)]">
				<th class="text-left px-4 py-3 font-medium text-[var(--text-secondary)]">
					<button
						onclick={() => toggleSort('name')}
						class="hover:text-[var(--text-primary)] transition-colors"
					>
						Command{sortIndicator('name')}
					</button>
				</th>
				<th class="text-left px-4 py-3 font-medium text-[var(--text-secondary)]">
					<button
						onclick={() => toggleSort('category')}
						class="hover:text-[var(--text-primary)] transition-colors"
					>
						Category{sortIndicator('category')}
					</button>
				</th>
				<th class="text-right px-4 py-3 font-medium text-[var(--text-secondary)]">
					<button
						onclick={() => toggleSort('uses')}
						class="hover:text-[var(--text-primary)] transition-colors"
					>
						Uses{sortIndicator('uses')}
					</button>
				</th>
				<th
					class="text-right px-4 py-3 font-medium text-[var(--text-secondary)] hidden md:table-cell"
				>
					<button
						onclick={() => toggleSort('sessions')}
						class="hover:text-[var(--text-primary)] transition-colors"
					>
						Sessions{sortIndicator('sessions')}
					</button>
				</th>
				<th
					class="text-right px-4 py-3 font-medium text-[var(--text-secondary)] hidden md:table-cell"
				>
					<button
						onclick={() => toggleSort('last')}
						class="hover:text-[var(--text-primary)] transition-colors"
					>
						Last Used{sortIndicator('last')}
					</button>
				</th>
			</tr>
		</thead>
		<tbody>
			{#each sortedCommands as command (command.name)}
				{@const catColors = getCommandCategoryColorVars(command.category ?? 'user_command')}
				<tr class="border-b border-[var(--border)] hover:bg-[var(--bg-subtle)] transition-colors">
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
					<td class="px-4 py-3 text-right tabular-nums font-medium text-[var(--text-primary)]">
						{command.count?.toLocaleString() ?? '0'}
					</td>
					<td
						class="px-4 py-3 text-right tabular-nums text-[var(--text-muted)] hidden md:table-cell"
					>
						{command.session_count?.toLocaleString() ?? '—'}
					</td>
					<td class="px-4 py-3 text-right text-[var(--text-muted)] hidden md:table-cell">
						{#if command.last_used}
							{formatDistanceToNow(new Date(command.last_used))} ago
						{:else}
							Never
						{/if}
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
