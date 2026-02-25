<script lang="ts">
	import { ChevronDown } from 'lucide-svelte';

	interface Option {
		label: string;
		value: string | number;
	}

	interface Props {
		options: Option[];
		value?: string | number;
		disabled?: boolean;
		class?: string;
		onchange?: (value: string | number) => void;
	}

	let {
		options,
		value = $bindable(options[0]?.value),
		disabled = false,
		class: className = '',
		onchange
	}: Props = $props();

	function handleChange(e: Event) {
		const target = e.target as HTMLSelectElement;
		const selectedOption = options.find((o) => String(o.value) === target.value);
		if (selectedOption) {
			value = selectedOption.value;
			onchange?.(selectedOption.value);
		}
	}
</script>

<div class="relative inline-block {className}">
	<select
		{disabled}
		onchange={handleChange}
		class="
			appearance-none w-full px-3 py-2 pr-8 text-sm font-medium
			bg-[var(--bg-base)] text-[var(--text-primary)]
			border border-[var(--border)] rounded-md
			focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:ring-offset-1 focus:ring-offset-[var(--bg-base)]
			disabled:opacity-50 disabled:cursor-not-allowed
			cursor-pointer transition-shadow duration-150
		"
	>
		{#each options as option}
			<option value={option.value} selected={option.value === value}>
				{option.label}
			</option>
		{/each}
	</select>
	<div
		class="absolute inset-y-0 right-0 flex items-center pr-2 pointer-events-none text-[var(--text-muted)]"
	>
		<ChevronDown size={14} />
	</div>
</div>
