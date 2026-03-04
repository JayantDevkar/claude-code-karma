<script lang="ts">
	import type { Snippet } from 'svelte';
	import { formatDistanceToNow } from 'date-fns';
	import { sortIndicator } from '$lib/utils';

	/**
	 * A column definition for the shared usage table.
	 *
	 * - `key`: unique string key used for sort state
	 * - `label`: display text in the header
	 * - `align`: text alignment (default 'left')
	 * - `hidden`: if true, column is hidden on small screens (md:table-cell)
	 * - `sortable`: if false, the header renders as plain text (default true)
	 */
	export interface UsageColumn {
		key: string;
		label: string;
		align?: 'left' | 'right';
		hidden?: boolean;
		sortable?: boolean;
	}

	/**
	 * A row item must provide at minimum `count`, `session_count`, and `last_used`
	 * for the shared stat columns (Uses, Sessions, Last Used).
	 * Everything else is rendered via the `customCells` snippet.
	 */
	export interface UsageRowBase {
		count?: number;
		session_count?: number | null;
		last_used?: string | null;
		[key: string]: any;
	}

	interface Props<T extends UsageRowBase> {
		/** Sorted array of items to render — caller is responsible for sorting */
		items: T[];
		/** Unique key extractor for {#each} */
		getKey: (item: T) => string;
		/** Column definitions for the leading columns (before Uses/Sessions/Last Used) */
		columns: UsageColumn[];
		/** Current sort key */
		sortKey: string;
		/** Current sort direction */
		sortDir: 'asc' | 'desc';
		/** Called when a sortable column header is clicked */
		onToggleSort: (key: string) => void;
		/**
		 * Snippet that renders the leading cells for each row.
		 * Receives the row item; must return one <td> per leading column.
		 */
		customCells: Snippet<[T]>;
	}

	let {
		items,
		getKey,
		columns,
		sortKey,
		sortDir,
		onToggleSort,
		customCells
	}: Props<UsageRowBase> = $props();
</script>

<div class="overflow-x-auto border border-[var(--border)] rounded-xl">
	<table class="w-full text-sm">
		<thead>
			<tr class="border-b border-[var(--border)] bg-[var(--bg-subtle)]">
				{#each columns as col}
					<th
						class="px-4 py-3 font-medium text-[var(--text-secondary)] {col.align === 'right'
							? 'text-right'
							: 'text-left'} {col.hidden ? 'hidden md:table-cell' : ''}"
					>
						{#if col.sortable !== false}
							<button
								onclick={() => onToggleSort(col.key)}
								class="hover:text-[var(--text-primary)] transition-colors"
							>
								{col.label}{sortIndicator(sortKey, col.key, sortDir)}
							</button>
						{:else}
							{col.label}
						{/if}
					</th>
				{/each}
				<!-- Shared stat columns -->
				<th class="text-right px-4 py-3 font-medium text-[var(--text-secondary)]">
					<button
						onclick={() => onToggleSort('uses')}
						class="hover:text-[var(--text-primary)] transition-colors"
					>
						Uses{sortIndicator(sortKey, 'uses', sortDir)}
					</button>
				</th>
				<th
					class="text-right px-4 py-3 font-medium text-[var(--text-secondary)] hidden md:table-cell"
				>
					<button
						onclick={() => onToggleSort('sessions')}
						class="hover:text-[var(--text-primary)] transition-colors"
					>
						Sessions{sortIndicator(sortKey, 'sessions', sortDir)}
					</button>
				</th>
				<th
					class="text-right px-4 py-3 font-medium text-[var(--text-secondary)] hidden md:table-cell"
				>
					<button
						onclick={() => onToggleSort('last')}
						class="hover:text-[var(--text-primary)] transition-colors"
					>
						Last Used{sortIndicator(sortKey, 'last', sortDir)}
					</button>
				</th>
			</tr>
		</thead>
		<tbody>
			{#each items as item (getKey(item))}
				<tr class="border-b border-[var(--border)] hover:bg-[var(--bg-subtle)] transition-colors">
					{@render customCells(item)}
					<td class="px-4 py-3 text-right tabular-nums font-medium text-[var(--text-primary)]">
						{item.count?.toLocaleString() ?? '0'}
					</td>
					<td
						class="px-4 py-3 text-right tabular-nums text-[var(--text-muted)] hidden md:table-cell"
					>
						{item.session_count?.toLocaleString() ?? '—'}
					</td>
					<td class="px-4 py-3 text-right text-[var(--text-muted)] hidden md:table-cell">
						{#if item.last_used}
							{formatDistanceToNow(new Date(item.last_used))} ago
						{:else}
							Never
						{/if}
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
