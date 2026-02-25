<script lang="ts">
	import { Search, X, SlidersHorizontal, ChevronDown } from 'lucide-svelte';
	import { onMount, onDestroy } from 'svelte';
	import { browser } from '$app/environment';

	interface Props {
		searchQuery?: string;
		onSearchChange: (query: string) => void;
		showFiltersDropdown: boolean;
		onToggleFilters: () => void;
		hasActiveFilters: boolean;
		activeFilterCount?: number;
		placeholder?: string;
		class?: string;
	}

	let {
		searchQuery = $bindable(''),
		onSearchChange,
		showFiltersDropdown,
		onToggleFilters,
		hasActiveFilters,
		activeFilterCount = 0,
		placeholder = 'Search by title or prompt...',
		class: className = ''
	}: Props = $props();

	let inputRef: HTMLInputElement | undefined;
	let debounceTimeout: ReturnType<typeof setTimeout>;

	function handleInput(e: Event) {
		const value = (e.target as HTMLInputElement).value;
		searchQuery = value;

		// Debounce the callback
		clearTimeout(debounceTimeout);
		debounceTimeout = setTimeout(() => {
			onSearchChange(value);
		}, 300);
	}

	function handleClear() {
		searchQuery = '';
		clearTimeout(debounceTimeout);
		onSearchChange('');
		inputRef?.focus();
	}

	function handleKeydown(e: KeyboardEvent) {
		// Escape to clear and blur
		if (e.key === 'Escape' && document.activeElement === inputRef) {
			if (searchQuery) {
				handleClear();
			} else {
				inputRef?.blur();
			}
		}
	}

	function handleGlobalKeydown(e: KeyboardEvent) {
		// Cmd/Ctrl + K to focus search
		if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
			e.preventDefault();
			inputRef?.focus();
			inputRef?.select();
		}
	}

	onMount(() => {
		document.addEventListener('keydown', handleGlobalKeydown);
	});

	onDestroy(() => {
		if (browser) {
			document.removeEventListener('keydown', handleGlobalKeydown);
			clearTimeout(debounceTimeout);
		}
	});
</script>

<div class="flex items-center gap-2 {className}">
	<!-- Search Input -->
	<div class="relative flex-1 group">
		<!-- Search Icon -->
		<div
			class="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)] group-focus-within:text-[var(--accent)] transition-colors"
		>
			<Search size={14} />
		</div>

		<input
			bind:this={inputRef}
			type="text"
			value={searchQuery}
			oninput={handleInput}
			onkeydown={handleKeydown}
			{placeholder}
			class="
				w-full pl-9 pr-16 py-2 text-sm
				bg-[var(--bg-base)] text-[var(--text-primary)]
				border border-[var(--border)] rounded-lg
				placeholder:text-[var(--text-faint)]
				hover:border-[var(--border-hover)]
				focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:ring-offset-1 focus:ring-offset-[var(--bg-base)]
				focus:border-[var(--accent)]
				transition-all duration-150
			"
		/>

		<!-- Keyboard Hint (shown when empty and not focused) -->
		{#if !searchQuery}
			<div
				class="hidden sm:flex absolute right-3 top-1/2 -translate-y-1/2 items-center gap-0.5 text-[var(--text-faint)] pointer-events-none opacity-60 group-focus-within:opacity-0 transition-opacity"
			>
				<kbd
					class="px-1.5 py-0.5 bg-[var(--bg-muted)] rounded text-[10px] font-medium border border-[var(--border)]"
					>⌘</kbd
				>
				<kbd
					class="px-1.5 py-0.5 bg-[var(--bg-muted)] rounded text-[10px] font-medium border border-[var(--border)]"
					>K</kbd
				>
			</div>
		{/if}

		<!-- Clear Button -->
		{#if searchQuery}
			<button
				type="button"
				onclick={handleClear}
				class="
					absolute right-3 top-1/2 -translate-y-1/2
					p-1 rounded-md
					text-[var(--text-muted)] hover:text-[var(--text-primary)]
					hover:bg-[var(--bg-muted)]
					focus:outline-none focus:ring-2 focus:ring-[var(--accent)]
					transition-colors
				"
				aria-label="Clear search"
			>
				<X size={14} />
			</button>
		{/if}
	</div>

	<!-- Filters Button -->
	<button
		type="button"
		onclick={onToggleFilters}
		class="
			inline-flex items-center gap-2 px-3 h-9
			bg-[var(--bg-base)] border rounded-[6px]
			text-xs font-medium
			focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:ring-offset-1
			transition-all duration-150
			{hasActiveFilters
			? 'border-[var(--accent)] text-[var(--accent)]'
			: 'border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--border-hover)] hover:text-[var(--text-primary)]'}
			{showFiltersDropdown ? 'bg-[var(--bg-subtle)]' : 'hover:bg-[var(--bg-subtle)]'}
		"
		aria-expanded={showFiltersDropdown}
		aria-haspopup="true"
	>
		<SlidersHorizontal size={12} strokeWidth={2} />
		<span class="hidden sm:inline">Filters</span>

		<!-- Active Filter Count Badge -->
		{#if activeFilterCount > 0}
			<span
				class="
					inline-flex items-center justify-center
					min-w-[18px] h-[18px] px-1
					bg-[var(--accent)] text-white
					rounded-full text-[10px] font-semibold
				"
			>
				{activeFilterCount}
			</span>
		{:else if hasActiveFilters}
			<!-- Dot indicator when filters active but no count -->
			<span class="w-1.5 h-1.5 rounded-full bg-[var(--accent)]"></span>
		{/if}

		<ChevronDown
			size={12}
			strokeWidth={2}
			class="transition-transform duration-200 {showFiltersDropdown ? 'rotate-180' : ''}"
		/>
	</button>
</div>
