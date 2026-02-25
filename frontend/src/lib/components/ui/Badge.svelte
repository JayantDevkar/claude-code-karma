<script lang="ts">
	import type { ComponentType, Snippet } from 'svelte';

	interface Props {
		variant?:
			| 'default'
			| 'accent'
			| 'success'
			| 'warning'
			| 'error'
			| 'info'
			| 'purple'
			| 'blue'
			| 'emerald'
			| 'slate';
		size?: 'sm' | 'md';
		rounded?: 'md' | 'full';
		icon?: ComponentType;
		children: Snippet;
		class?: string;
	}

	let {
		variant = 'default',
		size = 'md',
		rounded = 'md',
		icon: Icon,
		children,
		class: className = ''
	}: Props = $props();

	const variantClasses = {
		default: 'bg-[var(--bg-muted)] text-[var(--text-primary)] border-[var(--border)]',
		accent: 'bg-[var(--accent-subtle)] text-[var(--accent)] border-[var(--accent)]',
		success: 'bg-[var(--success-subtle)] text-[var(--success)] border-[var(--success)]',
		warning: 'bg-[var(--warning-subtle)] text-[var(--warning)] border-[var(--warning)]',
		error: 'bg-[var(--error-subtle)] text-[var(--error)] border-[var(--error)]',
		info: 'bg-[var(--info-subtle)] text-[var(--info)] border-[var(--info)]',
		purple: 'bg-[var(--model-opus-subtle)] text-[var(--model-opus)] border-[var(--model-opus)]/40',
		blue: 'bg-[var(--model-sonnet-subtle)] text-[var(--model-sonnet)] border-[var(--model-sonnet)]/40',
		emerald:
			'bg-[var(--model-haiku-subtle)] text-[var(--model-haiku)] border-[var(--model-haiku)]/40',
		slate: 'bg-[var(--bg-muted)] text-[var(--text-secondary)] border-[var(--border)]'
	};

	const sizeClasses = {
		sm: 'px-1.5 py-0.5 text-[10px]',
		md: 'px-2.5 py-1 text-xs'
	};

	const roundedClasses = {
		md: 'rounded-md',
		full: 'rounded-full'
	};

	const iconSizes = {
		sm: 10,
		md: 12
	};

	const gapClasses = {
		sm: 'gap-1',
		md: 'gap-1.5'
	};
</script>

<span
	class="
		inline-flex items-center
		font-medium
		border
		{variantClasses[variant]}
		{sizeClasses[size]}
		{roundedClasses[rounded]}
		{Icon ? gapClasses[size] : ''}
		{className}
	"
>
	{#if Icon}
		<Icon size={iconSizes[size]} strokeWidth={2} />
	{/if}
	{@render children()}
</span>
