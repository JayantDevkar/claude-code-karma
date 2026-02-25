<script lang="ts">
	import { onMount, onDestroy } from 'svelte';
	import { browser } from '$app/environment';
	import { Clock, ChevronDown, Check } from 'lucide-svelte';
	import type { AnalyticsFilterPeriod } from '$lib/api-types';
	import { analyticsFilterOptions, getAnalyticsFilterLabel } from '$lib/utils';

	interface Props {
		selectedFilter: AnalyticsFilterPeriod;
		onFilterChange: (filter: AnalyticsFilterPeriod) => void;
		class?: string;
	}

	let { selectedFilter, onFilterChange, class: className = '' }: Props = $props();

	let dropdownOpen = $state(false);
	let dropdownRef: HTMLDivElement;

	const handleSelect = (filter: AnalyticsFilterPeriod) => {
		dropdownOpen = false;
		onFilterChange(filter);
	};

	const handleClickOutside = (event: MouseEvent) => {
		const target = event.target as HTMLElement;
		if (dropdownRef && !dropdownRef.contains(target)) {
			dropdownOpen = false;
		}
	};

	onMount(() => {
		document.addEventListener('click', handleClickOutside);
	});

	onDestroy(() => {
		if (browser) {
			document.removeEventListener('click', handleClickOutside);
		}
	});

	// Get grouped options
	const hoursOptions = analyticsFilterOptions.filter((opt) => opt.group === 'Hours');
	const weeksOptions = analyticsFilterOptions.filter((opt) => opt.group === 'Weeks');
	const monthsOptions = analyticsFilterOptions.filter((opt) => opt.group === 'Months');
</script>

<div class="relative time-filter-dropdown {className}" bind:this={dropdownRef}>
	<button
		type="button"
		class="flex items-center gap-2 px-3 py-2 bg-[var(--bg-muted)] hover:bg-[var(--bg-base)] rounded-lg border border-[var(--border)] text-sm font-medium text-[var(--text-primary)] transition-all"
		onclick={() => (dropdownOpen = !dropdownOpen)}
	>
		<Clock size={14} class="text-[var(--text-muted)]" />
		<span>{getAnalyticsFilterLabel(selectedFilter)}</span>
		<ChevronDown
			size={14}
			class="text-[var(--text-muted)] transition-transform {dropdownOpen ? 'rotate-180' : ''}"
		/>
	</button>

	{#if dropdownOpen}
		<div
			class="absolute right-0 top-full mt-1 w-48 bg-[var(--bg-base)] border border-[var(--border)] rounded-lg shadow-lg z-50 py-1 overflow-hidden"
		>
			<!-- All Time option -->
			<button
				type="button"
				class="w-full flex items-center justify-between px-3 py-2 text-sm text-left hover:bg-[var(--bg-muted)] transition-colors {selectedFilter ===
				'all'
					? 'text-[var(--text-primary)] font-medium'
					: 'text-[var(--text-secondary)]'}"
				onclick={() => handleSelect('all')}
			>
				<span>All Time</span>
				{#if selectedFilter === 'all'}
					<Check size={14} class="text-[var(--accent)]" />
				{/if}
			</button>

			<!-- Hours section -->
			<div class="border-t border-[var(--border)] my-1"></div>
			<div
				class="px-3 py-1.5 text-[10px] font-medium uppercase tracking-wider text-[var(--text-muted)]"
			>
				Hours
			</div>
			{#each hoursOptions as option (option.id)}
				<button
					type="button"
					class="w-full flex items-center justify-between px-3 py-2 text-sm text-left hover:bg-[var(--bg-muted)] transition-colors {selectedFilter ===
					option.id
						? 'text-[var(--text-primary)] font-medium'
						: 'text-[var(--text-secondary)]'}"
					onclick={() => handleSelect(option.id)}
				>
					<span>{option.label}</span>
					{#if selectedFilter === option.id}
						<Check size={14} class="text-[var(--accent)]" />
					{/if}
				</button>
			{/each}

			<!-- Weeks section -->
			<div class="border-t border-[var(--border)] my-1"></div>
			<div
				class="px-3 py-1.5 text-[10px] font-medium uppercase tracking-wider text-[var(--text-muted)]"
			>
				Weeks
			</div>
			{#each weeksOptions as option (option.id)}
				<button
					type="button"
					class="w-full flex items-center justify-between px-3 py-2 text-sm text-left hover:bg-[var(--bg-muted)] transition-colors {selectedFilter ===
					option.id
						? 'text-[var(--text-primary)] font-medium'
						: 'text-[var(--text-secondary)]'}"
					onclick={() => handleSelect(option.id)}
				>
					<span>{option.label}</span>
					{#if selectedFilter === option.id}
						<Check size={14} class="text-[var(--accent)]" />
					{/if}
				</button>
			{/each}

			<!-- Months section -->
			<div class="border-t border-[var(--border)] my-1"></div>
			<div
				class="px-3 py-1.5 text-[10px] font-medium uppercase tracking-wider text-[var(--text-muted)]"
			>
				Months
			</div>
			{#each monthsOptions as option (option.id)}
				<button
					type="button"
					class="w-full flex items-center justify-between px-3 py-2 text-sm text-left hover:bg-[var(--bg-muted)] transition-colors {selectedFilter ===
					option.id
						? 'text-[var(--text-primary)] font-medium'
						: 'text-[var(--text-secondary)]'}"
					onclick={() => handleSelect(option.id)}
				>
					<span>{option.label}</span>
					{#if selectedFilter === option.id}
						<Check size={14} class="text-[var(--accent)]" />
					{/if}
				</button>
			{/each}
		</div>
	{/if}
</div>
