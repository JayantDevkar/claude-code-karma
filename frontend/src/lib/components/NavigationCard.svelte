<script lang="ts">
	import type { Component } from 'svelte';

	interface Props {
		title: string;
		description?: string;
		href: string;
		icon: any;
		color?:
			| 'blue'
			| 'green'
			| 'orange'
			| 'purple'
			| 'gray'
			| 'red'
			| 'yellow'
			| 'teal'
			| 'violet'
			| 'indigo'
			| 'amber';
		disabled?: boolean;
	}

	let {
		title,
		description = '',
		href,
		icon: IconComponent,
		color = 'blue',
		disabled = false
	}: Props = $props();

	// Color config with gradients and glow effects
	const colorConfig = {
		blue: {
			text: 'var(--nav-blue)',
			bg: 'var(--nav-blue-subtle)',
			border: 'var(--nav-blue)',
			gradient:
				'linear-gradient(135deg, var(--nav-blue-subtle) 0%, rgba(59, 130, 246, 0.15) 100%)',
			glow: '0 4px 20px -2px rgba(59, 130, 246, 0.25)'
		},
		green: {
			text: 'var(--nav-green)',
			bg: 'var(--nav-green-subtle)',
			border: 'var(--nav-green)',
			gradient:
				'linear-gradient(135deg, var(--nav-green-subtle) 0%, rgba(16, 185, 129, 0.15) 100%)',
			glow: '0 4px 20px -2px rgba(16, 185, 129, 0.25)'
		},
		orange: {
			text: 'var(--nav-orange)',
			bg: 'var(--nav-orange-subtle)',
			border: 'var(--nav-orange)',
			gradient:
				'linear-gradient(135deg, var(--nav-orange-subtle) 0%, rgba(249, 115, 22, 0.15) 100%)',
			glow: '0 4px 20px -2px rgba(249, 115, 22, 0.25)'
		},
		purple: {
			text: 'var(--nav-purple)',
			bg: 'var(--nav-purple-subtle)',
			border: 'var(--nav-purple)',
			gradient:
				'linear-gradient(135deg, var(--nav-purple-subtle) 0%, rgba(139, 92, 246, 0.15) 100%)',
			glow: '0 4px 20px -2px rgba(139, 92, 246, 0.25)'
		},
		gray: {
			text: 'var(--nav-gray)',
			bg: 'var(--nav-gray-subtle)',
			border: 'var(--nav-gray)',
			gradient:
				'linear-gradient(135deg, var(--nav-gray-subtle) 0%, rgba(100, 116, 139, 0.12) 100%)',
			glow: '0 4px 20px -2px rgba(100, 116, 139, 0.2)'
		},
		red: {
			text: 'var(--nav-red)',
			bg: 'var(--nav-red-subtle)',
			border: 'var(--nav-red)',
			gradient:
				'linear-gradient(135deg, var(--nav-red-subtle) 0%, rgba(244, 63, 94, 0.15) 100%)',
			glow: '0 4px 20px -2px rgba(244, 63, 94, 0.25)'
		},
		yellow: {
			text: 'var(--nav-yellow)',
			bg: 'var(--nav-yellow-subtle)',
			border: 'var(--nav-yellow)',
			gradient:
				'linear-gradient(135deg, var(--nav-yellow-subtle) 0%, rgba(202, 138, 4, 0.15) 100%)',
			glow: '0 4px 20px -2px rgba(202, 138, 4, 0.25)'
		},
		teal: {
			text: 'var(--nav-teal)',
			bg: 'var(--nav-teal-subtle)',
			border: 'var(--nav-teal)',
			gradient:
				'linear-gradient(135deg, var(--nav-teal-subtle) 0%, rgba(8, 145, 178, 0.15) 100%)',
			glow: '0 4px 20px -2px rgba(8, 145, 178, 0.25)'
		},
		violet: {
			text: 'var(--nav-violet)',
			bg: 'var(--nav-violet-subtle)',
			border: 'var(--nav-violet)',
			gradient:
				'linear-gradient(135deg, var(--nav-violet-subtle) 0%, rgba(219, 39, 119, 0.15) 100%)',
			glow: '0 4px 20px -2px rgba(219, 39, 119, 0.25)'
		},
		indigo: {
			text: 'var(--nav-indigo)',
			bg: 'var(--nav-indigo-subtle)',
			border: 'var(--nav-indigo)',
			gradient:
				'linear-gradient(135deg, var(--nav-indigo-subtle) 0%, rgba(99, 102, 241, 0.15) 100%)',
			glow: '0 4px 20px -2px rgba(99, 102, 241, 0.25)'
		},
		amber: {
			text: 'var(--nav-amber)',
			bg: 'var(--nav-amber-subtle)',
			border: 'var(--nav-amber)',
			gradient:
				'linear-gradient(135deg, var(--nav-amber-subtle) 0%, rgba(217, 119, 6, 0.15) 100%)',
			glow: '0 4px 20px -2px rgba(217, 119, 6, 0.25)'
		}
	};

	const config = $derived(colorConfig[color]);
</script>

{#if description}
	<!-- Full card layout with description -->
	<a
		{href}
		class="group flex flex-col p-4 bg-[var(--bg-base)] border border-[var(--border)] rounded-[6px] transition-all duration-200 hover:scale-[1.01] active:scale-[0.99] active:bg-[var(--bg-subtle)] no-underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]"
		style="--hover-glow: {config.glow};"
		onmouseenter={(e) => {
			e.currentTarget.style.boxShadow = config.glow;
			e.currentTarget.style.borderColor = config.border;
		}}
		onmouseleave={(e) => {
			e.currentTarget.style.boxShadow = 'none';
			e.currentTarget.style.borderColor = '';
		}}
	>
		<div class="flex items-start justify-between mb-3">
			<div
				class="flex items-center justify-center w-8 h-8 rounded-md"
				style="color: {config.text}; background: {config.gradient};"
			>
				<IconComponent size={20} strokeWidth={2} />
			</div>
		</div>

		<div class="flex flex-col gap-1.5">
			<h3
				class="text-base font-medium tracking-tight text-[var(--text-primary)] group-hover:text-[var(--text-primary)] transition-colors"
			>
				{title}
			</h3>
			<p
				class="text-sm text-[var(--text-muted)] leading-relaxed group-hover:text-[var(--text-secondary)] transition-colors"
			>
				{description}
			</p>
		</div>
	</a>
{:else if disabled}
	<!-- Disabled/placeholder compact card -->
	<div
		class="group relative flex items-center justify-center px-4 py-3 bg-[var(--bg-subtle)] border border-[var(--border)] border-dashed rounded-[6px] opacity-50 cursor-not-allowed"
	>
		<div
			class="absolute left-4 flex items-center justify-center w-7 h-7 rounded-md"
			style="color: {config.text}; background: {config.gradient};"
		>
			<IconComponent size={18} strokeWidth={2} />
		</div>
		<h3 class="text-sm font-medium tracking-tight text-[var(--text-muted)]">
			{title}
		</h3>
		<span
			class="absolute right-4 text-[10px] font-medium text-[var(--text-faint)] uppercase tracking-wider"
			>Soon</span
		>
	</div>
{:else}
	<!-- Compact layout without description -->
	<a
		{href}
		class="group relative flex items-center justify-center px-4 py-3 bg-[var(--bg-base)] border border-[var(--border)] rounded-[6px] transition-all duration-200 hover:scale-[1.02] active:scale-[0.98] active:bg-[var(--bg-subtle)] no-underline focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]"
		onmouseenter={(e) => {
			e.currentTarget.style.boxShadow = config.glow;
			e.currentTarget.style.borderColor = config.border;
		}}
		onmouseleave={(e) => {
			e.currentTarget.style.boxShadow = 'none';
			e.currentTarget.style.borderColor = '';
		}}
	>
		<div
			class="absolute left-4 flex items-center justify-center w-7 h-7 rounded-md transition-all duration-200"
			style="color: {config.text}; background: {config.gradient};"
		>
			<IconComponent size={18} strokeWidth={2} />
		</div>
		<h3
			class="text-sm font-medium tracking-tight text-[var(--text-primary)] group-hover:text-[var(--text-primary)] transition-colors"
		>
			{title}
		</h3>
	</a>
{/if}
