<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		variant?: 'default' | 'subtle' | 'interactive';
		padding?: 'none' | 'sm' | 'md' | 'lg';
		children: Snippet;
		class?: string;
	}

	let { variant = 'default', padding = 'md', children, class: className = '' }: Props = $props();

	const variantClasses = {
		default: 'border border-[var(--border)] bg-[var(--bg-base)]',
		subtle: 'border border-[var(--border)] bg-[var(--bg-subtle)]',
		interactive:
			'border border-[var(--border)] bg-[var(--bg-base)] hover:shadow-sm transition-shadow duration-[var(--duration-base)] cursor-pointer'
	};

	const paddingClasses = {
		none: '',
		sm: 'p-3',
		md: 'p-4',
		lg: 'p-6'
	};
</script>

<div class="rounded-lg {variantClasses[variant]} {paddingClasses[padding]} {className}">
	{@render children()}
</div>
