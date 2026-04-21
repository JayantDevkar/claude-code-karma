<script lang="ts">
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
		index?: number;
	}

	let {
		title,
		description = '',
		href,
		icon: IconComponent,
		color = 'blue',
		disabled = false,
		index = 0
	}: Props = $props();

	const accentVar = $derived(`var(--nav-${color})`);
	const accentSubtleVar = $derived(`var(--nav-${color}-subtle)`);

	const indexLabel = $derived(String(index + 1).padStart(2, '0'));
</script>

{#if disabled}
	<div class="card card--disabled" style="--ink: {accentVar}; --ink-tint: {accentSubtleVar};">
		<span class="card__index">{indexLabel}</span>
		<span class="card__dot"></span>
		<span class="card__title">{title}</span>
		<IconComponent size={15} strokeWidth={1.75} class="card__icon" />
		<span class="card__soon">Soon</span>
	</div>
{:else if description}
	<a
		{href}
		class="card card--full"
		style="--ink: {accentVar}; --ink-tint: {accentSubtleVar};"
	>
		<div class="card__header">
			<span class="card__index">{indexLabel}</span>
			<span class="card__dot"></span>
			<IconComponent size={15} strokeWidth={1.75} class="card__icon" />
		</div>
		<div class="card__body">
			<h3 class="card__title">{title}</h3>
			<p class="card__desc">{description}</p>
		</div>
	</a>
{:else}
	<a
		{href}
		class="card"
		style="--ink: {accentVar}; --ink-tint: {accentSubtleVar};"
	>
		<span class="card__index">{indexLabel}</span>
		<span class="card__dot"></span>
		<span class="card__title">{title}</span>
		<IconComponent size={15} strokeWidth={1.75} class="card__icon" />
	</a>
{/if}

<style>
	.card {
		position: relative;
		display: grid;
		grid-template-columns: auto auto 1fr auto;
		align-items: center;
		gap: 10px;
		padding: 12px 14px;
		background: var(--bg-base);
		border: 1px solid var(--border);
		border-radius: var(--radius-sm);
		text-decoration: none;
		color: var(--text-primary);
		transition:
			background var(--duration-fast) var(--ease),
			border-color var(--duration-fast) var(--ease),
			transform var(--duration-fast) var(--ease);
		overflow: hidden;
	}

	/* Thin ink accent line on the left, only visible on hover */
	.card::before {
		content: '';
		position: absolute;
		left: 0;
		top: 0;
		bottom: 0;
		width: 2px;
		background: var(--ink);
		transform: scaleY(0);
		transform-origin: top center;
		transition: transform var(--duration-base) var(--ease);
	}

	.card:hover {
		background: var(--ink-tint);
		border-color: var(--ink);
	}

	.card:hover::before {
		transform: scaleY(1);
	}

	.card:active {
		transform: translateY(1px);
	}

	.card__index {
		font-family: var(--font-mono);
		font-size: 10px;
		letter-spacing: 0.08em;
		color: var(--text-faint);
		font-variant-numeric: tabular-nums;
		min-width: 20px;
	}

	.card__dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: var(--ink);
		flex-shrink: 0;
	}

	.card__title {
		font-family: var(--font-mono);
		font-size: 11px;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--text-primary);
		font-weight: 500;
		white-space: nowrap;
	}

	.card :global(.card__icon) {
		color: var(--text-faint);
		transition: color var(--duration-fast);
	}

	.card:hover :global(.card__icon) {
		color: var(--ink);
	}

	/* ===== Full card with description ===== */
	.card--full {
		display: flex;
		flex-direction: column;
		padding: 16px;
		gap: 14px;
		min-height: 120px;
	}

	.card--full .card__header {
		display: flex;
		align-items: center;
		gap: 10px;
	}

	.card--full .card__header .card__index {
		margin-left: auto;
		order: 3;
	}

	.card--full .card__body {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}

	.card--full .card__title {
		font-family: var(--font-serif);
		font-style: italic;
		font-size: 22px;
		line-height: 1;
		letter-spacing: -0.015em;
		text-transform: none;
		color: var(--text-primary);
	}

	.card__desc {
		font-size: 13px;
		line-height: 1.5;
		color: var(--text-muted);
	}

	/* ===== Disabled ===== */
	.card--disabled {
		background: var(--bg-subtle);
		border-style: dashed;
		opacity: 0.55;
		cursor: not-allowed;
	}

	.card--disabled:hover {
		background: var(--bg-subtle);
		border-color: var(--border);
	}

	.card__soon {
		font-family: var(--font-mono);
		font-size: 9px;
		letter-spacing: 0.2em;
		text-transform: uppercase;
		color: var(--text-faint);
	}
</style>
