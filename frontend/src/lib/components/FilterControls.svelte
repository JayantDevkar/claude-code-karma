<script lang="ts">
	import { Check, ChevronDown } from 'lucide-svelte';
	import { slide } from 'svelte/transition';
	import type {
		SearchScopeSelection,
		SessionStatusFilter,
		SearchDateRange,
		LiveSubStatus,
		LiveStatusCounts
	} from '$lib/api-types';
	import { ALL_LIVE_SUB_STATUSES } from '$lib/api-types';
	import { SCOPE_CHECKBOX_OPTIONS, DATE_RANGE_OPTIONS } from '$lib/search';
	import { statusConfig } from '$lib/live-session-config';

	interface Props {
		scopeSelection: SearchScopeSelection;
		onScopeSelectionChange: (selection: SearchScopeSelection) => void;
		status: SessionStatusFilter;
		onStatusChange: (status: SessionStatusFilter) => void;
		dateRange: SearchDateRange;
		onDateRangeChange: (range: SearchDateRange) => void;
		/** Currently selected live sub-statuses */
		liveSubStatuses?: LiveSubStatus[];
		/** Callback when live sub-statuses change */
		onLiveSubStatusChange?: (statuses: LiveSubStatus[]) => void;
		/** Counts for each live sub-status */
		liveStatusCounts?: LiveStatusCounts;
		/** Count of completed sessions */
		completedCount?: number;
		/** Variant for different visual styles */
		variant?: 'desktop' | 'mobile';
	}

	let {
		scopeSelection,
		onScopeSelectionChange,
		status,
		onStatusChange,
		dateRange,
		onDateRangeChange,
		liveSubStatuses = ALL_LIVE_SUB_STATUSES,
		onLiveSubStatusChange,
		liveStatusCounts,
		completedCount,
		variant = 'desktop'
	}: Props = $props();

	// Toggle a scope checkbox
	function toggleScope(key: keyof SearchScopeSelection) {
		const newSelection = { ...scopeSelection, [key]: !scopeSelection[key] };
		// Prevent unchecking both - keep at least one
		if (!newSelection.titles && !newSelection.prompts) {
			return;
		}
		onScopeSelectionChange(newSelection);
	}

	// Handle keyboard for scope checkbox
	function handleScopeKeydown(event: KeyboardEvent, key: keyof SearchScopeSelection) {
		if (event.key === 'Enter' || event.key === ' ') {
			event.preventDefault();
			toggleScope(key);
		}
	}

	// Calculate total count for "All" option
	let totalCount = $derived(() => {
		const liveTotal = liveStatusCounts?.total ?? 0;
		const completed = completedCount ?? 0;
		return liveTotal + completed;
	});

	// Whether to show live sub-status checkboxes
	let showLiveSubStatuses = $derived(status === 'live' || status === 'all');

	// Toggle a single live sub-status
	function toggleLiveSubStatus(subStatus: LiveSubStatus) {
		if (!onLiveSubStatusChange) return;

		const currentStatuses = [...liveSubStatuses];
		const index = currentStatuses.indexOf(subStatus);

		if (index === -1) {
			currentStatuses.push(subStatus);
		} else {
			if (currentStatuses.length > 1) {
				currentStatuses.splice(index, 1);
			}
		}

		onLiveSubStatusChange(currentStatuses);
	}

	// Handle keyboard for checkbox
	function handleCheckboxKeydown(event: KeyboardEvent, subStatus: LiveSubStatus) {
		if (event.key === 'Enter' || event.key === ' ') {
			event.preventDefault();
			toggleLiveSubStatus(subStatus);
		}
	}

	// Check if a sub-status is selected
	function isSubStatusSelected(subStatus: LiveSubStatus): boolean {
		return liveSubStatuses.includes(subStatus);
	}

	// Get count for a specific sub-status
	function getSubStatusCount(subStatus: LiveSubStatus): number {
		if (!liveStatusCounts) return 0;
		return liveStatusCounts[subStatus] ?? 0;
	}

	// Capitalize first letter
	function capitalize(str: string): string {
		return str.charAt(0).toUpperCase() + str.slice(1);
	}

	// Style classes based on variant
	const isMobile = $derived(variant === 'mobile');
</script>

<!-- Search Scope Section -->
<div class="filter-section">
	<div class="filter-label">Search in</div>
	<div class={isMobile ? 'flex flex-col gap-2' : 'flex gap-2'}>
		{#each SCOPE_CHECKBOX_OPTIONS as option}
			{@const isSelected = scopeSelection[option.key]}
			<button
				type="button"
				onclick={() => toggleScope(option.key)}
				onkeydown={(e) => handleScopeKeydown(e, option.key)}
				class="scope-button {isMobile ? 'mobile' : 'desktop'}"
				class:selected={isSelected}
				role="checkbox"
				aria-checked={isSelected}
			>
				<span class="checkbox" class:checked={isSelected}>
					{#if isSelected}
						<Check size={isMobile ? 12 : 10} class="text-white" strokeWidth={3} />
					{/if}
				</span>
				<span>{option.label}</span>
			</button>
		{/each}
	</div>
</div>

<!-- Status Filter Section -->
<div class="filter-section">
	<div class="filter-label">Status</div>
	<div class="flex flex-col gap-1">
		<!-- All option -->
		<button
			type="button"
			onclick={() => onStatusChange('all')}
			class="status-button {isMobile ? 'mobile' : 'desktop'}"
			class:selected={status === 'all'}
		>
			<span class="radio" class:checked={status === 'all'}>
				{#if status === 'all'}
					<span class="radio-dot"></span>
				{/if}
			</span>
			<span class="flex-1">All</span>
			<span class="count">{totalCount()}</span>
		</button>

		<!-- Live option with expandable sub-statuses -->
		<div class="flex flex-col">
			<button
				type="button"
				onclick={() => onStatusChange('live')}
				class="status-button {isMobile ? 'mobile' : 'desktop'}"
				class:selected={status === 'live'}
			>
				<span class="radio" class:checked={status === 'live'}>
					{#if status === 'live'}
						<span class="radio-dot"></span>
					{/if}
				</span>
				<span class="flex-1 flex items-center gap-2">
					{#if isMobile}
						<span
							class="w-2 h-2 rounded-full bg-[var(--success)]"
							class:animate-pulse={status === 'live'}
						></span>
					{/if}
					Live
					<ChevronDown
						size={14}
						class="transition-transform duration-200 text-[var(--text-muted)] {showLiveSubStatuses
							? 'rotate-180'
							: ''}"
					/>
				</span>
				<span class="count">{liveStatusCounts?.total ?? 0}</span>
			</button>

			<!-- Live sub-status checkboxes -->
			{#if showLiveSubStatuses}
				<div
					class="substatus-container {isMobile ? 'mobile' : 'desktop'}"
					transition:slide={{ duration: 200 }}
				>
					{#each ALL_LIVE_SUB_STATUSES as subStatus}
						{@const config = statusConfig[subStatus]}
						{@const isSelected = isSubStatusSelected(subStatus)}
						{@const count = getSubStatusCount(subStatus)}
						<button
							type="button"
							onclick={() => toggleLiveSubStatus(subStatus)}
							onkeydown={(e) => handleCheckboxKeydown(e, subStatus)}
							class="substatus-button {isMobile ? 'mobile' : 'desktop'}"
							class:selected={isSelected}
							role="checkbox"
							aria-checked={isSelected}
						>
							<span class="checkbox small" class:checked={isSelected}>
								{#if isSelected}
									<Check size={10} class="text-white" strokeWidth={3} />
								{/if}
							</span>
							<span
								class="w-2 h-2 rounded-full flex-shrink-0"
								style="background-color: {config.color}"
							></span>
							<span class="flex-1 capitalize">{config.label}</span>
							<span class="count small">{count}</span>
						</button>
					{/each}
				</div>
			{/if}
		</div>

		<!-- Completed option -->
		<button
			type="button"
			onclick={() => onStatusChange('completed')}
			class="status-button {isMobile ? 'mobile' : 'desktop'}"
			class:selected={status === 'completed'}
		>
			<span class="radio" class:checked={status === 'completed'}>
				{#if status === 'completed'}
					<span class="radio-dot"></span>
				{/if}
			</span>
			<span class="flex-1">Completed</span>
			<span class="count">{completedCount ?? 0}</span>
		</button>
	</div>
</div>

<!-- Date Range Section -->
<div class="filter-section no-border">
	<div class="filter-label">Date range</div>
	<div class="grid grid-cols-2 gap-2">
		{#each DATE_RANGE_OPTIONS.filter((o) => o.value !== 'custom') as option}
			<button
				type="button"
				onclick={() => onDateRangeChange(option.value)}
				class="date-button {isMobile ? 'mobile' : 'desktop'}"
				class:selected={dateRange === option.value}
			>
				{#if dateRange === option.value}
					<Check size={isMobile ? 16 : 12} class="text-[var(--accent)]" />
				{/if}
				<span>{option.label}</span>
			</button>
		{/each}
	</div>
</div>

<style>
	.filter-section {
		padding: 1rem;
		border-bottom: 1px solid var(--border);
	}

	.filter-section.no-border {
		border-bottom: none;
	}

	.filter-label {
		font-size: 10px;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
		margin-bottom: 0.75rem;
		font-weight: 500;
	}

	/* Scope buttons */
	.scope-button {
		display: flex;
		align-items: center;
		gap: 0.625rem;
		font-size: 0.75rem;
		font-weight: 500;
		border-radius: 0.5rem;
		transition: all 150ms;
		color: var(--text-muted);
	}

	.scope-button:focus {
		outline: none;
		ring: 2px solid var(--accent);
		ring-offset: 1px;
	}

	.scope-button.desktop {
		padding: 0.5rem 0.75rem;
	}

	.scope-button.desktop:hover {
		color: var(--text-secondary);
	}

	.scope-button.desktop.selected {
		color: var(--text-primary);
	}

	.scope-button.mobile {
		width: 100%;
		padding: 0.875rem 1rem;
		border: 1px solid var(--border);
		border-radius: 0.75rem;
		min-height: 48px;
	}

	.scope-button.mobile.selected {
		background: var(--bg-subtle);
		color: var(--text-primary);
	}

	/* Checkbox */
	.checkbox {
		width: 0.875rem;
		height: 0.875rem;
		border-radius: 0.25rem;
		border: 1px solid var(--border);
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
		transition: all 150ms;
		background: var(--bg-base);
	}

	.checkbox.checked {
		background: var(--accent);
		border-color: var(--accent);
	}

	.scope-button.mobile .checkbox {
		width: 1.25rem;
		height: 1.25rem;
		border-width: 2px;
	}

	.checkbox.small {
		width: 0.875rem;
		height: 0.875rem;
	}

	.substatus-button.mobile .checkbox {
		width: 1.25rem;
		height: 1.25rem;
		border-width: 2px;
	}

	/* Status buttons */
	.status-button {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		text-align: left;
		transition: all 150ms;
	}

	.status-button:focus {
		outline: none;
		ring: 2px solid var(--accent);
		ring-offset: 1px;
	}

	.status-button.desktop {
		padding: 0.5rem 0.75rem;
		font-size: 0.875rem;
		border-radius: 0.5rem;
		color: var(--text-secondary);
	}

	.status-button.desktop:hover {
		background: var(--bg-subtle);
		color: var(--text-primary);
	}

	.status-button.desktop.selected {
		background: var(--accent-subtle);
		color: var(--accent);
	}

	.status-button.mobile {
		width: 100%;
		padding: 0.875rem 1rem;
		font-size: 0.875rem;
		font-weight: 500;
		border: 1px solid var(--border);
		border-radius: 0.75rem;
		min-height: 48px;
		color: var(--text-secondary);
	}

	.status-button.mobile.selected {
		background: var(--accent-subtle);
		border-color: var(--accent);
		color: var(--accent);
	}

	/* Radio */
	.radio {
		width: 1rem;
		height: 1rem;
		border-radius: 50%;
		border: 2px solid var(--border);
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
	}

	.radio.checked {
		border-color: var(--accent);
	}

	.radio-dot {
		width: 0.5rem;
		height: 0.5rem;
		border-radius: 50%;
		background: var(--accent);
	}

	/* Sub-status container */
	.substatus-container {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
	}

	.substatus-container.desktop {
		margin-left: 1.75rem;
		margin-top: 0.25rem;
		margin-bottom: 0.25rem;
		padding-left: 0.75rem;
		border-left: 2px solid var(--border);
	}

	.substatus-container.mobile {
		margin-left: 1rem;
		margin-top: 0.5rem;
		padding-left: 1rem;
		border-left: 2px solid var(--border);
		gap: 0.25rem;
	}

	/* Sub-status buttons */
	.substatus-button {
		display: flex;
		align-items: center;
		gap: 0.625rem;
		text-align: left;
		transition: all 150ms;
		color: var(--text-muted);
	}

	.substatus-button:focus {
		outline: none;
		ring: 2px solid var(--accent);
		ring-offset: 1px;
	}

	.substatus-button.desktop {
		padding: 0.375rem 0.5rem;
		font-size: 0.75rem;
		border-radius: 0.375rem;
	}

	.substatus-button.desktop:hover {
		color: var(--text-secondary);
	}

	.substatus-button.desktop.selected {
		color: var(--text-primary);
	}

	.substatus-button.mobile {
		width: 100%;
		padding: 0.75rem;
		font-size: 0.875rem;
		border-radius: 0.5rem;
		min-height: 48px;
	}

	.substatus-button.mobile.selected {
		background: var(--bg-subtle);
		color: var(--text-primary);
	}

	/* Count badge */
	.count {
		font-size: 0.75rem;
		color: var(--text-muted);
		font-variant-numeric: tabular-nums;
	}

	.count.small {
		font-size: 0.625rem;
	}

	/* Date buttons */
	.date-button {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.375rem;
		font-weight: 500;
		border: 1px solid var(--border);
		transition: all 150ms;
		background: var(--bg-base);
		color: var(--text-secondary);
	}

	.date-button:focus {
		outline: none;
		ring: 2px solid var(--accent);
		ring-offset: 1px;
	}

	.date-button.desktop {
		padding: 0.5rem 0.75rem;
		font-size: 0.75rem;
		border-radius: 0.5rem;
	}

	.date-button.desktop:hover {
		border-color: var(--border-hover);
		color: var(--text-primary);
	}

	.date-button.desktop.selected {
		background: var(--accent-subtle);
		border-color: var(--accent);
		color: var(--accent);
	}

	.date-button.mobile {
		padding: 0.75rem 1rem;
		font-size: 0.875rem;
		border-radius: 0.75rem;
	}

	.date-button.mobile.selected {
		background: var(--accent-subtle);
		border-color: var(--accent);
		color: var(--accent);
	}
</style>
