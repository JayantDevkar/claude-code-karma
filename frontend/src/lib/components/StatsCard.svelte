<script lang="ts">
	import type { StatColor } from '$lib/api-types';
	import { formatTokens } from '$lib/utils';

	interface Props {
		title: string;
		value: string | number;
		description?: string;
		// eslint-disable-next-line @typescript-eslint/no-explicit-any
		icon?: any;
		class?: string;
		color?: StatColor;
		// Token breakdown visualization
		tokenIn?: number;
		tokenOut?: number;
	}

	let {
		title,
		value,
		description,
		icon: Icon,
		class: className = '',
		color,
		tokenIn,
		tokenOut
	}: Props = $props();

	// Color map matching NavigationCard pattern for icon backgrounds
	const colorClasses: Record<StatColor, { bg: string; text: string }> = {
		blue: {
			bg: 'bg-[var(--nav-blue-subtle)] border-[var(--nav-blue)]/20',
			text: 'text-[var(--nav-blue)]'
		},
		green: {
			bg: 'bg-[var(--nav-green-subtle)] border-[var(--nav-green)]/20',
			text: 'text-[var(--nav-green)]'
		},
		orange: {
			bg: 'bg-[var(--nav-orange-subtle)] border-[var(--nav-orange)]/20',
			text: 'text-[var(--nav-orange)]'
		},
		purple: {
			bg: 'bg-[var(--nav-purple-subtle)] border-[var(--nav-purple)]/20',
			text: 'text-[var(--nav-purple)]'
		},
		teal: {
			bg: 'bg-[var(--nav-teal-subtle)] border-[var(--nav-teal)]/20',
			text: 'text-[var(--nav-teal)]'
		},
		gray: {
			bg: 'bg-[var(--bg-base)] border-[var(--border)]',
			text: 'text-[var(--text-muted)]'
		},
		accent: {
			bg: 'bg-[var(--accent-subtle)] border-[var(--accent)]/20',
			text: 'text-[var(--accent)]'
		}
	};

	// Derive icon container and text classes based on color prop
	let iconBgClass = $derived(color ? colorClasses[color].bg : colorClasses.gray.bg);
	let iconTextClass = $derived(color ? colorClasses[color].text : colorClasses.gray.text);

	// Calculate token percentages for visualization
	// Only show breakdown if at least one token value is greater than 0
	let hasTokenBreakdown = $derived(
		tokenIn !== undefined && tokenOut !== undefined && (tokenIn > 0 || tokenOut > 0)
	);
	let totalTokens = $derived((tokenIn || 0) + (tokenOut || 0));
	let inPercent = $derived(totalTokens > 0 ? ((tokenIn || 0) / totalTokens) * 100 : 0);
	let outPercent = $derived(totalTokens > 0 ? ((tokenOut || 0) / totalTokens) * 100 : 0);
</script>

<div
	class="
		p-5
		bg-[var(--bg-base)]
		border border-[var(--border)]
		rounded-xl
		shadow-sm hover:shadow-md
		transition-all duration-300
		{className}
	"
>
	<!-- Label at top with optional description in brackets -->
	<div class="text-xs uppercase tracking-wider font-semibold text-[var(--text-muted)] mb-3">
		{title}{#if description}<span class="normal-case tracking-normal font-normal">
				({description})</span
			>{/if}
	</div>

	<!-- Icon + Value aligned -->
	<div class="flex items-center gap-3">
		{#if Icon}
			<div
				class="
					flex items-center justify-center
					w-11 h-11
					border
					rounded-xl
					shrink-0
					transition-transform duration-300 hover:scale-105
					{iconBgClass}
				"
			>
				<Icon size={20} strokeWidth={2.5} class={iconTextClass} />
			</div>
		{/if}
		<div class="flex-1 min-w-0">
			<div class="text-2xl font-bold metric-value text-[var(--text-primary)] tracking-tight">
				{value}
			</div>
		</div>
	</div>

	<!-- Token breakdown visualization -->
	{#if hasTokenBreakdown}
		<div class="mt-3 space-y-1.5">
			<!-- Visual bar -->
			<div class="flex h-2 rounded-full overflow-hidden bg-[var(--bg-muted)]">
				<div
					class="bg-[var(--accent)] transition-all duration-300"
					style="width: {inPercent}%"
					title="Input: {formatTokens(tokenIn)}"
				></div>
				<div
					class="bg-[var(--nav-teal)] transition-all duration-300"
					style="width: {outPercent}%"
					title="Output: {formatTokens(tokenOut)}"
				></div>
			</div>
			<!-- Labels -->
			<div class="flex justify-between text-[10px] text-[var(--text-muted)]">
				<span class="flex items-center gap-1">
					<span class="w-2 h-2 rounded-full bg-[var(--accent)]"></span>
					In: {formatTokens(tokenIn)}
				</span>
				<span class="flex items-center gap-1">
					<span class="w-2 h-2 rounded-full bg-[var(--nav-teal)]"></span>
					Out: {formatTokens(tokenOut)}
				</span>
			</div>
		</div>
	{/if}
</div>
