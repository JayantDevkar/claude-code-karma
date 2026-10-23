<script lang="ts">
	interface Option {
		label: string;
		value: string;
	}

	interface Props {
		options: Option[];
		value?: string;
		disabled?: boolean;
		size?: 'sm' | 'md';
		class?: string;
		'aria-label'?: string;
		onchange?: (value: string) => void;
	}

	let {
		options,
		value = $bindable(options[0]?.value),
		disabled = false,
		size = 'md',
		class: className = '',
		'aria-label': ariaLabel,
		onchange
	}: Props = $props();

	// Roving tabindex: only the checked option (or the first, when none is) takes Tab focus.
	const tabStop = $derived(options.some((o) => o.value === value) ? value : options[0]?.value);

	function handleSelect(optionValue: string) {
		if (disabled) return;
		value = optionValue;
		onchange?.(optionValue);
	}

	function targetIndex(key: string, index: number, count: number): number | null {
		switch (key) {
			case 'ArrowRight':
			case 'ArrowDown':
				return (index + 1) % count;
			case 'ArrowLeft':
			case 'ArrowUp':
				return (index - 1 + count) % count;
			case 'Home':
				return 0;
			case 'End':
				return count - 1;
			default:
				return null;
		}
	}

	function handleKeydown(event: KeyboardEvent, index: number) {
		if (disabled || event.altKey || event.ctrlKey || event.metaKey) return;
		const next = targetIndex(event.key, index, options.length);
		if (next === null) return;
		event.preventDefault();
		if (options[next].value !== value) handleSelect(options[next].value);
		const radios = (event.currentTarget as HTMLElement).parentElement?.children;
		(radios?.[next] as HTMLElement | undefined)?.focus();
	}
</script>

<div
	class="seg-scroll inline-flex max-w-full overflow-x-auto {className}"
	class:seg-scroll--sm={size === 'sm'}
>
	<div
		class="
			seg-group inline-flex items-center gap-1 p-1 shrink-0
			bg-[var(--bg-subtle)] border border-[var(--border)] rounded-lg
			{disabled ? 'opacity-50 cursor-not-allowed' : ''}
		"
		role="radiogroup"
		aria-label={ariaLabel}
	>
		{#each options as option, i}
			<button
				type="button"
				role="radio"
				aria-checked={value === option.value}
				tabindex={option.value === tabStop ? 0 : -1}
				{disabled}
				onclick={() => handleSelect(option.value)}
				onkeydown={(e) => handleKeydown(e, i)}
				class="
					{size === 'sm'
					? 'seg-sm px-2 py-1 text-xs'
					: 'px-3 py-1.5 text-sm'} font-medium rounded-md shrink-0 whitespace-nowrap
					transition-all duration-150 ease-out
					focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-1
					{value === option.value
					? 'bg-[var(--accent)] text-[var(--bg-base)] shadow-sm'
					: 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'}
					{disabled ? 'cursor-not-allowed' : 'cursor-pointer'}
				"
			>
				{option.label}
			</button>
		{/each}
	</div>
</div>

<style>
	/* Invisible 44px touch area for sm options; the scroller gets 10px of room for it, cancelled by the negative margin. */
	@media (pointer: coarse) {
		.seg-scroll--sm {
			padding-block: 10px;
			margin-block: -10px;
			pointer-events: none;
		}
		.seg-scroll--sm .seg-group {
			pointer-events: auto;
		}
		.seg-sm {
			position: relative;
			min-width: 40px;
		}
		.seg-sm::before {
			content: '';
			position: absolute;
			inset: -10px -2px;
		}
	}
</style>
