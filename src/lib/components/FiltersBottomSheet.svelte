<script lang="ts">
	import { X, RotateCcw } from 'lucide-svelte';
	import { fly, fade } from 'svelte/transition';
	import { onMount, onDestroy } from 'svelte';
	import { browser } from '$app/environment';
	import type {
		SearchScopeSelection,
		SessionStatusFilter,
		SearchDateRange,
		LiveSubStatus,
		LiveStatusCounts
	} from '$lib/api-types';
	import { ALL_LIVE_SUB_STATUSES } from '$lib/api-types';
	import FilterControls from './FilterControls.svelte';

	interface Props {
		open: boolean;
		onClose: () => void;
		scopeSelection: SearchScopeSelection;
		onScopeSelectionChange: (selection: SearchScopeSelection) => void;
		status: SessionStatusFilter;
		onStatusChange: (status: SessionStatusFilter) => void;
		dateRange: SearchDateRange;
		onDateRangeChange: (range: SearchDateRange) => void;
		onReset: () => void;
		/** Currently selected live sub-statuses */
		liveSubStatuses?: LiveSubStatus[];
		/** Callback when live sub-statuses change */
		onLiveSubStatusChange?: (statuses: LiveSubStatus[]) => void;
		/** Counts for each live sub-status */
		liveStatusCounts?: LiveStatusCounts;
		/** Count of completed sessions */
		completedCount?: number;
	}

	let {
		open,
		onClose,
		scopeSelection,
		onScopeSelectionChange,
		status,
		onStatusChange,
		dateRange,
		onDateRangeChange,
		onReset,
		liveSubStatuses = ALL_LIVE_SUB_STATUSES,
		onLiveSubStatusChange,
		liveStatusCounts,
		completedCount
	}: Props = $props();

	// Prevent body scroll when sheet is open
	$effect(() => {
		if (browser && open) {
			document.body.style.overflow = 'hidden';
			return () => {
				document.body.style.overflow = '';
			};
		}
	});

	// Handle escape key
	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			onClose();
		}
	}

	onMount(() => {
		document.addEventListener('keydown', handleKeydown);
	});

	onDestroy(() => {
		if (browser) {
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

{#if open}
	<!-- Backdrop -->
	<div
		class="fixed inset-0 bg-black/50 z-40"
		onclick={onClose}
		transition:fade={{ duration: 200 }}
		aria-hidden="true"
	></div>

	<!-- Bottom Sheet -->
	<div
		class="fixed bottom-0 left-0 right-0 z-50 bg-[var(--bg-base)] rounded-t-2xl max-h-[85vh] overflow-hidden flex flex-col"
		transition:fly={{ y: 300, duration: 300 }}
		role="dialog"
		aria-modal="true"
		aria-label="Filter options"
	>
		<!-- Drag Handle -->
		<div class="flex justify-center py-3 shrink-0">
			<div class="w-12 h-1.5 bg-[var(--border)] rounded-full"></div>
		</div>

		<!-- Header -->
		<div
			class="flex items-center justify-between px-5 pb-4 border-b border-[var(--border)] shrink-0"
		>
			<h2 class="text-lg font-semibold text-[var(--text-primary)]">Filters</h2>
			<button
				type="button"
				onclick={onClose}
				class="p-2 -mr-2 rounded-lg hover:bg-[var(--bg-muted)] text-[var(--text-muted)] transition-colors"
				aria-label="Close filters"
			>
				<X size={20} />
			</button>
		</div>

		<!-- Scrollable Content -->
		<div class="flex-1 overflow-y-auto overscroll-contain">
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
				variant="mobile"
			/>
		</div>

		<!-- Footer Actions -->
		<div
			class="p-5 border-t border-[var(--border)] bg-[var(--bg-subtle)] shrink-0 safe-area-bottom"
		>
			<div class="flex gap-3">
				<button
					type="button"
					onclick={onReset}
					disabled={!hasFilters}
					class="
						flex-1 flex items-center justify-center gap-2
						px-4 py-3 text-sm font-medium
						bg-[var(--bg-base)] border border-[var(--border)]
						text-[var(--text-secondary)]
						rounded-xl transition-all
						active:bg-[var(--bg-muted)]
						disabled:opacity-40 disabled:cursor-not-allowed
					"
				>
					<RotateCcw size={16} />
					<span>Reset</span>
				</button>
				<button
					type="button"
					onclick={onClose}
					class="
						flex-1 flex items-center justify-center
						px-4 py-3 text-sm font-medium
						bg-[var(--accent)] text-white
						rounded-xl transition-all
						active:bg-[var(--accent-hover)]
					"
				>
					Apply Filters
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	/* Safe area for iPhone notch/home indicator */
	.safe-area-bottom {
		padding-bottom: max(1.25rem, env(safe-area-inset-bottom));
	}
</style>
