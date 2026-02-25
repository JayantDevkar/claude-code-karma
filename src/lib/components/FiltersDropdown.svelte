<script lang="ts">
	import { RotateCcw } from 'lucide-svelte';
	import { onMount, onDestroy } from 'svelte';
	import { browser } from '$app/environment';
	import type {
		SessionStatusFilter,
		SearchDateRange,
		LiveSubStatus,
		LiveStatusCounts,
		SearchScopeSelection
	} from '$lib/api-types';
	import { ALL_LIVE_SUB_STATUSES } from '$lib/api-types';
	import FilterControls from './FilterControls.svelte';

	interface Props {
		scopeSelection: SearchScopeSelection;
		onScopeSelectionChange: (selection: SearchScopeSelection) => void;
		status: SessionStatusFilter;
		onStatusChange: (status: SessionStatusFilter) => void;
		dateRange: SearchDateRange;
		onDateRangeChange: (range: SearchDateRange) => void;
		onReset: () => void;
		onClose: () => void;
		/** Currently selected live sub-statuses */
		liveSubStatuses?: LiveSubStatus[];
		/** Callback when live sub-statuses change */
		onLiveSubStatusChange?: (statuses: LiveSubStatus[]) => void;
		/** Counts for each live sub-status */
		liveStatusCounts?: LiveStatusCounts;
		/** Count of completed sessions */
		completedCount?: number;
		/** Whether data is currently loading/updating */
		isLoading?: boolean;
		class?: string;
	}

	let {
		scopeSelection,
		onScopeSelectionChange,
		status,
		onStatusChange,
		dateRange,
		onDateRangeChange,
		onReset,
		onClose,
		liveSubStatuses = ALL_LIVE_SUB_STATUSES,
		onLiveSubStatusChange,
		liveStatusCounts,
		completedCount,
		isLoading = false,
		class: className = ''
	}: Props = $props();

	let dropdownRef: HTMLDivElement;

	function handleClickOutside(event: MouseEvent) {
		const target = event.target as HTMLElement;
		// Don't close if clicking the filter button (parent handles toggle)
		if (target.closest('[aria-haspopup="true"]')) {
			return;
		}
		if (dropdownRef && !dropdownRef.contains(target)) {
			onClose();
		}
	}

	function handleKeydown(event: KeyboardEvent) {
		if (event.key === 'Escape') {
			onClose();
		}
	}

	onMount(() => {
		// Use capture phase to handle before other handlers
		document.addEventListener('click', handleClickOutside, true);
		document.addEventListener('keydown', handleKeydown);
	});

	onDestroy(() => {
		if (browser) {
			document.removeEventListener('click', handleClickOutside, true);
			document.removeEventListener('keydown', handleKeydown);
		}
	});

	// Check if any filters are non-default
	let hasFilters = $derived(
		!(scopeSelection.titles && scopeSelection.prompts) ||
			status !== 'all' ||
			dateRange !== 'all' ||
			liveSubStatuses.length !== ALL_LIVE_SUB_STATUSES.length
	);
</script>

<div
	bind:this={dropdownRef}
	class="
		absolute right-0 top-full mt-2 w-80
		bg-[var(--bg-base)] border border-[var(--border)]
		rounded-xl shadow-xl z-50
		overflow-hidden
		{className}
	"
	role="dialog"
	aria-label="Filter options"
>
	<FilterControls
		{scopeSelection}
		{onScopeSelectionChange}
		{status}
		{onStatusChange}
		{dateRange}
		{onDateRangeChange}
		{liveSubStatuses}
		{onLiveSubStatusChange}
		{liveStatusCounts}
		{completedCount}
		variant="desktop"
	/>

	<!-- Reset Button & Loading State -->
	<div class="p-3 bg-[var(--bg-subtle)] flex items-center justify-between gap-3">
		<button
			type="button"
			onclick={onReset}
			disabled={!hasFilters && !isLoading}
			class="
				flex-1 flex items-center justify-center gap-2
				px-4 py-2 text-sm font-medium
				text-[var(--text-muted)] hover:text-[var(--text-primary)]
				rounded-lg transition-all duration-150
				hover:bg-[var(--bg-muted)]
				focus:outline-none focus:ring-2 focus:ring-[var(--accent)]
				disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent
			"
		>
			<RotateCcw size={14} />
			<span>Reset all filters</span>
		</button>

		{#if isLoading}
			<div
				class="flex items-center gap-2 text-xs font-medium text-[var(--accent)] animate-pulse px-2"
			>
				<div
					class="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin"
				></div>
				<span>Updating...</span>
			</div>
		{/if}
	</div>
</div>
