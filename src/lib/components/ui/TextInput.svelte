<script lang="ts">
	interface Props {
		value?: string;
		placeholder?: string;
		disabled?: boolean;
		class?: string;
		type?: 'text' | 'password' | 'email';
		onkeydown?: (e: KeyboardEvent) => void;
		oninput?: (e: Event) => void;
	}

	let {
		value = $bindable(''),
		placeholder = '',
		disabled = false,
		class: className = '',
		type = 'text',
		onkeydown,
		oninput
	}: Props = $props();
</script>

<input
	{type}
	bind:value
	{placeholder}
	{disabled}
	{onkeydown}
	{oninput}
	class="
		w-full px-3 py-2 text-sm
		bg-[var(--bg-base)] text-[var(--text-primary)]
		border border-[var(--border)] rounded-md
		placeholder:text-[var(--text-muted)]
		focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:ring-offset-1 focus:ring-offset-[var(--bg-base)]
		disabled:opacity-50 disabled:cursor-not-allowed
		transition-shadow duration-150
		{className}
	"
/>
