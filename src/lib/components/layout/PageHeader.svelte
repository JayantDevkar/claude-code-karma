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
	<!-- Breadcrumb Navigation -->
	{#if breadcrumbs.length > 0}
		<div class="flex items-center gap-2 text-xs text-[var(--text-secondary)] mb-4">
			{#each breadcrumbs as crumb, i}
				{#if i > 0}
					<span class="text-[var(--text-faint)]">/</span>
				{/if}
				{#if crumb.href}
					<a
						href={crumb.href}
						class="hover:text-[var(--text-primary)] transition-colors"
						style="transition-duration: var(--duration-fast); transition-timing-function: var(--ease);"
					>
						{crumb.label}
					</a>
				{:else}
					<span class="text-[var(--text-primary)] font-medium">{crumb.label}</span>
				{/if}
			{/each}
		</div>
	{/if}

	<!-- Page Header -->
	<div class="mb-6 pb-6 border-b border-[var(--border)]">
		<div class="flex items-start gap-4">
			<!-- Icon -->
			{#if Icon}
				<div
					class="
						inline-flex items-center justify-center
						w-12 h-12
						border
						rounded-[var(--radius-md)]
						shrink-0
					"
					style={iconColorRaw
						? `background-color: ${iconColorRaw.subtle}; border-color: ${iconColorRaw.color}; color: ${iconColorRaw.color};`
						: iconColor
							? `background-color: var(${iconColor}-subtle); border-color: var(${iconColor}); color: var(${iconColor});`
							: 'background-color: var(--bg-subtle); border-color: var(--border); color: var(--text-muted);'}
				>
					<Icon size={24} strokeWidth={2} />
				</div>
			{/if}

			<!-- Title and Content -->
			<div class="flex-1 min-w-0">
				<div class="flex items-center gap-3 mb-2">
					<h1 class="text-2xl font-semibold tracking-tight text-[var(--text-primary)]">
						{title}
					</h1>
					{#if badges}
						{@render badges()}
					{/if}
				</div>
				{#if subtitle}
					<span
						class="
							inline-flex
							px-2 py-0.5
							text-xs font-mono
							text-[var(--text-muted)]
							bg-[var(--bg-muted)]
							rounded-[var(--radius-sm)]
						">{subtitle}</span
					>
				{/if}

				{#if metadata.length > 0}
					<div
						class="flex items-center gap-3 text-xs text-[var(--text-muted)] mt-3 flex-wrap"
					>
						{#each metadata as item, i}
							{#if i > 0}
								<span class="text-[var(--text-faint)]">•</span>
							{/if}
							{#if item.href}
								<a
									href={item.href}
									class="flex items-center gap-1.5 hover:text-[var(--accent)] transition-colors {item.class ||
										''}"
								>
									{#if item.icon}
										<svelte:component
											this={item.icon}
											size={12}
											strokeWidth={2}
										/>
									{/if}
									<span>{item.text}</span>
								</a>
							{:else}
								<div class="flex items-center gap-1.5 {item.class || ''}">
									{#if item.icon}
										<svelte:component
											this={item.icon}
											size={12}
											strokeWidth={2}
										/>
									{/if}
									<span>{item.text}</span>
								</div>
							{/if}
						{/each}
					</div>
				{/if}
			</div>

			<!-- Right Side Content (e.g., Model Badge) -->
			{#if headerRight}
				<div class="shrink-0">
					{@render headerRight()}
				</div>
			{/if}
		</div>
	</div>
</div>
