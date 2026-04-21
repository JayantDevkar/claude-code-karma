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

	// Ink palette per color key. Tokens already retuned in app.css.
	const inkColor: Record<StatColor, string> = {
		blue: 'var(--nav-blue)',
		green: 'var(--nav-green)',
		orange: 'var(--nav-orange)',
		purple: 'var(--nav-purple)',
		teal: 'var(--nav-teal)',
		gray: 'var(--text-muted)',
		accent: 'var(--accent)'
	};

	const inkTint: Record<StatColor, string> = {
		blue: 'var(--nav-blue-subtle)',
		green: 'var(--nav-green-subtle)',
		orange: 'var(--nav-orange-subtle)',
		purple: 'var(--nav-purple-subtle)',
		teal: 'var(--nav-teal-subtle)',
		gray: 'var(--bg-muted)',
		accent: 'var(--accent-subtle)'
	};

	const ink = $derived(color ? inkColor[color] : 'var(--text-muted)');
	const tint = $derived(color ? inkTint[color] : 'var(--bg-muted)');

	let hasTokenBreakdown = $derived(
		tokenIn !== undefined && tokenOut !== undefined && (tokenIn > 0 || tokenOut > 0)
	);
	let totalTokens = $derived((tokenIn || 0) + (tokenOut || 0));
	let inPercent = $derived(totalTokens > 0 ? ((tokenIn || 0) / totalTokens) * 100 : 0);
	let outPercent = $derived(totalTokens > 0 ? ((tokenOut || 0) / totalTokens) * 100 : 0);
</script>

<div class="stat {className}" style="--ink: {ink}; --tint: {tint};">
	<div class="stat__label">
		<span class="stat__dot"></span>
		<span class="stat__title">{title}</span>
		{#if description}
			<span class="stat__desc">({description})</span>
		{/if}
	</div>

	<div class="stat__row">
		{#if Icon}
			<div class="stat__icon">
				<Icon size={16} strokeWidth={1.75} />
			</div>
		{/if}
		<div class="stat__value">{value}</div>
	</div>

	{#if hasTokenBreakdown}
		<div class="stat__breakdown">
			<div class="stat__bar">
				<span class="stat__bar-in" style="width: {inPercent}%" title="Input"></span>
				<span class="stat__bar-out" style="width: {outPercent}%" title="Output"></span>
			</div>
			<div class="stat__legend">
				<span class="stat__leg">
					<span class="stat__leg-dot stat__leg-dot--in"></span>
					In · {formatTokens(tokenIn)}
				</span>
				<span class="stat__leg">
					<span class="stat__leg-dot stat__leg-dot--out"></span>
					Out · {formatTokens(tokenOut)}
				</span>
			</div>
		</div>
	{/if}
</div>

<style>
	.stat {
		position: relative;
		padding: 18px 18px 20px;
		background: var(--bg-base);
		border: 1px solid var(--border);
		border-radius: var(--radius-md);
		transition: border-color var(--duration-fast) var(--ease);
	}

	.stat:hover {
		border-color: var(--border-hover);
	}

	.stat__label {
		display: flex;
		align-items: center;
		gap: 8px;
		margin-bottom: 14px;
		font-family: var(--font-mono);
		font-size: 10px;
		letter-spacing: 0.16em;
		text-transform: uppercase;
		color: var(--text-muted);
		font-weight: 500;
	}

	.stat__dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: var(--ink);
		flex-shrink: 0;
	}

	.stat__title {
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.stat__desc {
		letter-spacing: 0;
		text-transform: none;
		font-weight: 400;
		color: var(--text-faint);
	}

	.stat__row {
		display: flex;
		align-items: center;
		gap: 12px;
	}

	.stat__icon {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 32px;
		height: 32px;
		border-radius: var(--radius-sm);
		color: var(--ink);
		background: var(--tint);
		flex-shrink: 0;
	}

	.stat__value {
		font-size: 28px;
		font-weight: 600;
		letter-spacing: -0.02em;
		line-height: 1.1;
		color: var(--text-primary);
		font-variant-numeric: tabular-nums;
		min-width: 0;
		flex: 1;
	}

	.stat__breakdown {
		margin-top: 14px;
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	.stat__bar {
		display: flex;
		height: 4px;
		border-radius: 2px;
		overflow: hidden;
		background: var(--bg-muted);
	}

	.stat__bar-in {
		background: var(--accent);
		transition: width var(--duration-base) var(--ease);
	}

	.stat__bar-out {
		background: var(--nav-teal);
		transition: width var(--duration-base) var(--ease);
	}

	.stat__legend {
		display: flex;
		justify-content: space-between;
		align-items: center;
		font-family: var(--font-mono);
		font-size: 10px;
		letter-spacing: 0.05em;
		color: var(--text-muted);
		font-variant-numeric: tabular-nums;
	}

	.stat__leg {
		display: inline-flex;
		align-items: center;
		gap: 5px;
	}

	.stat__leg-dot {
		width: 5px;
		height: 5px;
		border-radius: 50%;
	}

	.stat__leg-dot--in {
		background: var(--accent);
	}

	.stat__leg-dot--out {
		background: var(--nav-teal);
	}
</style>
