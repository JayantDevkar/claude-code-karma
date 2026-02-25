<script lang="ts">
	import { X } from 'lucide-svelte';
	import type { FilterChip, SearchFilters } from '$lib/api-types';

	interface Props {
		chips: FilterChip[];
		onRemove: (key: keyof SearchFilters) => void;
		onClearAll: () => void;
		totalCount: number;
		filteredCount: number;
		class?: string;
	}

	let {
		chips,
		onRemove,
		onClearAll,
		totalCount,
		filteredCount,
		class: className = ''
	}: Props = $props();

	let hasActiveFilters = $derived(chips.length > 0);
	let isFiltered = $derived(filteredCount !== totalCount);
</script>

{#if hasActiveFilters}
	<div class="flex flex-wrap items-center gap-2 {className}">
		<!-- Filter Chips -->
		<div class="flex flex-wrap items-center gap-2">
			{#each chips as chip (chip.key)}
				<button
					type="button"
					onclick={() => onRemove(chip.key)}
					class="
						group inline-flex items-center gap-1.5 pl-3 pr-2 py-1.5
						bg-[var(--accent-subtle)] text-[var(--accent)]
						rounded-full text-xs font-medium
						hover:bg-[var(--accent)]/15
						focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:ring-offset-1
						transition-all duration-150
					"
					aria-label="Remove {chip.label} filter"
				>
					<span class="text-[var(--text-muted)] font-normal">{chip.label}:</span>
					<span>{chip.value}</span>
					<span
						class="
							inline-flex items-center justify-center
							w-4 h-4 ml-0.5 rounded-full
							bg-[var(--accent)]/10 group-hover:bg-[var(--accent)]/20
							transition-colors
						"
					>
						<X size={10} class="opacity-70 group-hover:opacity-100" />
					</span>
				</button>
			{/each}
		</div>

		<!-- Spacer + Count & Clear -->
		<div class="flex items-center gap-3 ml-auto">
			<!-- Count -->
			{#if isFiltered}
				<span class="text-xs text-[var(--text-muted)] tabular-nums">
					<span class="font-medium text-[var(--text-secondary)]">{filteredCount}</span>
					<span>of</span>
					<span>{totalCount}</span>
					<span>sessions</span>
				</span>
			{/if}

			<!-- Clear All -->
			<button
				type="button"
				onclick={onClearAll}
				class="
					text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)]
					underline-offset-2 hover:underline
					focus:outline-none focus:ring-2 focus:ring-[var(--accent)] rounded
					transition-colors
				"
			>
				Clear all
			</button>
		</div>
	</div>
{/if}
