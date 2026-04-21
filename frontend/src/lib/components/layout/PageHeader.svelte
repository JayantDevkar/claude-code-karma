<script lang="ts">
	import type { ComponentType, Snippet } from 'svelte';

	interface Breadcrumb {
		label: string;
		href?: string;
	}

	interface MetadataItem {
		icon?: ComponentType;
		text: string;
		class?: string;
		href?: string;
	}

	interface Props {
		title: string;
		icon?: ComponentType;
		iconColor?: string; // CSS color variable name, e.g., '--subagent-plan'
		iconColorRaw?: { color: string; subtle: string }; // Raw color values (e.g., OKLCH)
		breadcrumbs?: Breadcrumb[];
		subtitle?: string;
		metadata?: MetadataItem[];
		badges?: Snippet;
		headerRight?: Snippet;
		class?: string;
	}

	let {
		title,
		icon: Icon,
		iconColor,
		iconColorRaw,
		breadcrumbs = [],
		subtitle,
		metadata = [],
		badges,
		headerRight,
		class: className
	}: Props = $props();
</script>

<div class={className}>
	<!-- Breadcrumb — mono caps, matches compact header nav -->
	{#if breadcrumbs.length > 0}
		<nav class="ph-breadcrumbs" aria-label="Breadcrumb">
			{#each breadcrumbs as crumb, i}
				{#if i > 0}
					<span class="ph-breadcrumb-sep" aria-hidden="true">/</span>
				{/if}
				{#if crumb.href}
					<a href={crumb.href} class="ph-breadcrumb-link">{crumb.label}</a>
				{:else}
					<span class="ph-breadcrumb-current" aria-current="page">{crumb.label}</span>
				{/if}
			{/each}
		</nav>
	{/if}

	<!-- Masthead row -->
	<div class="ph-masthead">
		<div class="ph-main">
			{#if Icon}
				<div
					class="ph-icon"
					style={iconColorRaw
						? `background-color: ${iconColorRaw.subtle}; color: ${iconColorRaw.color};`
						: iconColor
							? `background-color: var(${iconColor}-subtle); color: var(${iconColor});`
							: 'background-color: var(--bg-subtle); color: var(--text-muted);'}
				>
					<Icon size={20} strokeWidth={1.75} />
				</div>
			{/if}

			<div class="ph-body">
				<div class="ph-title-row">
					<h1 class="ph-title">{title}</h1>
					{#if badges}
						{@render badges()}
					{/if}
				</div>

				{#if subtitle}
					<p class="ph-subtitle">{subtitle}</p>
				{/if}

				{#if metadata.length > 0}
					<div class="ph-metadata">
						{#each metadata as item, i}
							{#if i > 0}
								<span class="ph-metadata-sep" aria-hidden="true">·</span>
							{/if}
							{#if item.href}
								<a href={item.href} class="ph-metadata-item {item.class || ''}">
									{#if item.icon}
										{@const ItemIcon = item.icon}
										<ItemIcon size={12} strokeWidth={1.75} />
									{/if}
									<span>{item.text}</span>
								</a>
							{:else}
								<div class="ph-metadata-item ph-metadata-item--static {item.class || ''}">
									{#if item.icon}
										{@const ItemIcon = item.icon}
										<ItemIcon size={12} strokeWidth={1.75} />
									{/if}
									<span>{item.text}</span>
								</div>
							{/if}
						{/each}
					</div>
				{/if}
			</div>
		</div>

		{#if headerRight}
			<div class="ph-right">
				{@render headerRight()}
			</div>
		{/if}
	</div>

	<div class="ph-rule" aria-hidden="true"></div>
</div>

<style>
	.ph-breadcrumbs {
		display: flex;
		align-items: center;
		gap: 8px;
		margin-bottom: 14px;
		font-family: var(--font-mono);
		font-size: 10px;
		letter-spacing: 0.14em;
		text-transform: uppercase;
		color: var(--text-muted);
	}

	.ph-breadcrumb-sep {
		color: var(--text-faint);
	}

	.ph-breadcrumb-link {
		color: var(--text-muted);
		text-decoration: none;
		transition: color var(--duration-fast) var(--ease);
	}

	.ph-breadcrumb-link:hover {
		color: var(--text-primary);
	}

	.ph-breadcrumb-current {
		color: var(--text-primary);
	}

	.ph-masthead {
		display: flex;
		align-items: flex-end;
		justify-content: space-between;
		gap: 16px;
		margin-bottom: 18px;
	}

	.ph-main {
		display: flex;
		align-items: flex-start;
		gap: 14px;
		min-width: 0;
		flex: 1;
	}

	.ph-icon {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 36px;
		height: 36px;
		border-radius: var(--radius-sm);
		flex-shrink: 0;
		margin-top: 4px;
	}

	.ph-body {
		display: flex;
		flex-direction: column;
		min-width: 0;
		flex: 1;
	}

	.ph-title-row {
		display: flex;
		align-items: center;
		gap: 12px;
		flex-wrap: wrap;
	}

	.ph-title {
		margin: 0;
		font-family: var(--font-serif);
		font-style: italic;
		font-weight: 400;
		font-size: 40px;
		line-height: 1;
		letter-spacing: -0.025em;
		color: var(--text-primary);
	}

	.ph-subtitle {
		margin: 8px 0 0;
		font-family: var(--font-mono);
		font-size: 10px;
		letter-spacing: 0.16em;
		text-transform: uppercase;
		color: var(--text-muted);
	}

	.ph-metadata {
		display: flex;
		align-items: center;
		gap: 10px;
		margin-top: 12px;
		flex-wrap: wrap;
		font-size: 12px;
		color: var(--text-muted);
	}

	.ph-metadata-sep {
		color: var(--text-faint);
	}

	.ph-metadata-item {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		text-decoration: none;
		color: var(--text-muted);
		transition: color var(--duration-fast) var(--ease);
	}

	a.ph-metadata-item:hover {
		color: var(--accent);
	}

	.ph-right {
		flex-shrink: 0;
	}

	.ph-rule {
		height: 1px;
		background: var(--border);
		margin-bottom: 24px;
	}
</style>
