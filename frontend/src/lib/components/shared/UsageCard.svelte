<script lang="ts">
	import { Play, Clock, MessageSquare } from 'lucide-svelte';
	import { formatDistanceToNow } from 'date-fns';
	import type { Snippet } from 'svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import TierBadge from '$lib/components/ui/TierBadge.svelte';
	import { getUsageTier } from '$lib/utils';

	type BadgeVariant = 'purple' | 'accent' | 'blue' | 'emerald' | 'info';

	interface ColorVars {
		color: string;
		subtle: string;
	}

	interface Props {
		name: string;
		displayName: string;
		href: string;
		count: number;
		maxUsage?: number;
		colorVars: ColorVars;
		categoryLabel: string;
		badgeVariant: BadgeVariant;
		description?: string | null;
		lastUsed?: string | null;
		sessionCount?: number | null;
		icon: Snippet;
		subheader?: Snippet;
		class?: string;
	}

	let {
		name,
		displayName,
		href,
		count,
		maxUsage = 100,
		colorVars,
		categoryLabel,
		badgeVariant,
		description = null,
		lastUsed = null,
		sessionCount = null,
		icon,
		subheader,
		class: className = ''
	}: Props = $props();

	let usagePercentage = $derived(Math.min((count / maxUsage) * 100, 100));
	let tier = $derived(getUsageTier(count, maxUsage));
	let lastUsedFormatted = $derived(
		lastUsed ? formatDistanceToNow(new Date(lastUsed)) + ' ago' : 'Never'
	);
</script>

<a
	{href}
	class="
		group block
		bg-[var(--bg-base)]
		border border-[var(--border)]
		rounded-xl
		p-6
		shadow-sm hover:shadow-xl hover:-translate-y-1
		transition-all duration-300
		relative overflow-hidden
		focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2
		{className}
	"
	style="border-left: 4px solid {colorVars.color};"
	data-list-item
>
	<!-- Header row: Icon + Badges -->
	<div class="flex items-start justify-between mb-5">
		<div
			class="p-3 rounded-xl transition-all duration-300 group-hover:scale-110"
			style="background-color: {colorVars.subtle}; color: {colorVars.color};"
		>
			{@render icon()}
		</div>
		<div class="flex items-center gap-2">
			<TierBadge {tier} />
			<Badge variant={badgeVariant} size="sm" rounded="full">
				{categoryLabel}
			</Badge>
		</div>
	</div>

	<!-- Name -->
	<h3
		class="text-lg font-bold text-[var(--text-primary)] mb-2 truncate pr-4 tracking-tight group-hover:text-[var(--accent)] transition-colors"
		title={name}
	>
		{displayName}
	</h3>

	<!-- Description -->
	{#if description}
		<p class="text-xs text-[var(--text-muted)] mb-2 line-clamp-2" title={description}>
			{description}
		</p>
	{/if}

	<!-- Optional subheader slot (e.g. plugin link) — provides its own mb-4 spacer -->
	{#if subheader}
		{@render subheader()}
	{:else}
		<div class="mb-4"></div>
	{/if}

	<!-- Stats with progress bar -->
	<div class="space-y-3 mb-4">
		<!-- Uses stat with progress bar -->
		<div>
			<div class="flex items-center justify-between mb-1.5">
				<div class="flex items-center gap-2 text-xs text-[var(--text-muted)]">
					<Play size={12} />
					<span class="font-medium">Uses</span>
				</div>
				<span class="text-sm font-semibold text-[var(--text-primary)] tabular-nums">
					{count.toLocaleString()}
				</span>
			</div>
			<div class="h-1.5 bg-[var(--bg-subtle)] rounded-full overflow-hidden">
				<div
					class="h-full rounded-full transition-all duration-300"
					style="width: {usagePercentage}%; background-color: {colorVars.color};"
				></div>
			</div>
		</div>

		<!-- Sessions stat -->
		{#if sessionCount != null}
			<div class="flex items-center justify-between text-xs">
				<div class="flex items-center gap-2 text-[var(--text-muted)]">
					<MessageSquare size={12} />
					<span class="font-medium">Sessions</span>
				</div>
				<span class="text-sm font-semibold text-[var(--text-primary)] tabular-nums">
					{sessionCount}
				</span>
			</div>
		{/if}
	</div>

	<!-- Footer row: Last used -->
	<div
		class="flex items-center justify-between text-xs text-[var(--text-muted)] pt-4 border-t border-[var(--border-subtle)]"
	>
		<span class="flex items-center gap-1.5">
			<Clock size={12} />
			<span>{lastUsedFormatted}</span>
		</span>
		{#if sessionCount != null}
			<span class="flex items-center gap-1.5">
				<MessageSquare size={12} />
				<span>{sessionCount} session{sessionCount !== 1 ? 's' : ''}</span>
			</span>
		{/if}
	</div>
</a>
