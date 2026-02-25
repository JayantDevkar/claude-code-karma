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
		onchange?: (value: string) => void;
	}

	let {
		options,
		value = $bindable(options[0]?.value),
		disabled = false,
		size = 'md',
		class: className = '',
		onchange
	}: Props = $props();

	function handleSelect(optionValue: string) {
		if (disabled) return;
		value = optionValue;
		onchange?.(optionValue);
	}
</script>

<div
	class="
		inline-flex items-center gap-1 p-1
		bg-[var(--bg-subtle)] border border-[var(--border)] rounded-lg
		{disabled ? 'opacity-50 cursor-not-allowed' : ''}
		{className}
	"
	role="radiogroup"
>
	{#each options as option}
		<button
			type="button"
			role="radio"
			aria-checked={value === option.value}
			{disabled}
			onclick={() => handleSelect(option.value)}
			class="
				{size === 'sm' ? 'px-2 py-1 text-xs' : 'px-3 py-1.5 text-sm'} font-medium rounded-md
				transition-all duration-150 ease-out
				focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-1
				{value === option.value
				? 'bg-[var(--accent)] text-white shadow-sm'
				: 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]'}
				{disabled ? 'cursor-not-allowed' : 'cursor-pointer'}
			"
		>
			{option.label}
		</button>
	{/each}
</div>
