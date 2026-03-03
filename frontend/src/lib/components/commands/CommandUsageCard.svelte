<script lang="ts">
	import { Zap, Play, Clock, MessageSquare, Terminal, Sparkles, Puzzle, FileText } from 'lucide-svelte';
	import { formatDistanceToNow } from 'date-fns';
	import Badge from '$lib/components/ui/Badge.svelte';
	import TierBadge from '$lib/components/ui/TierBadge.svelte';
	import { getCommandCategoryColorVars, getCommandCategoryLabel, getUsageTier } from '$lib/utils';
	import type { CommandCategory } from '$lib/api-types';

	interface Command {
		name: string;
		count: number;
		category?: CommandCategory;
		description?: string | null;
		last_used?: string | null;
		session_count?: number;
	}

	interface Props {
		command: Command;
		maxUsage?: number;
		class?: string;
	}

	let { command, maxUsage = 100, class: className = '' }: Props = $props();

	// Color based on category
	let colorVars = $derived(getCommandCategoryColorVars(command.category ?? 'user_command'));
	let categoryLabel = $derived(getCommandCategoryLabel(command.category ?? 'user_command'));

	// Badge variant based on category
	type BadgeVariant = 'purple' | 'accent' | 'blue' | 'emerald' | 'info';
	let badgeVariant = $derived<BadgeVariant>(
		command.category === 'builtin_command'
			? 'blue'
			: command.category === 'bundled_skill'
				? 'purple'
				: command.category === 'plugin_skill'
					? 'emerald'
					: command.category === 'custom_skill'
						? 'info'
						: 'accent'
	);

	// Category icon
	let CategoryIcon = $derived(
		command.category === 'builtin_command'
			? Terminal
			: command.category === 'bundled_skill'
				? Sparkles
				: command.category === 'plugin_skill'
					? Puzzle
					: command.category === 'custom_skill'
						? Zap
						: FileText
	);

	// Calculate usage percentage for progress bar
	let usagePercentage = $derived(Math.min((command.count / maxUsage) * 100, 100));

	// Tier badge
	let tier = $derived(getUsageTier(command.count, maxUsage));

	// Format last used as relative time
	let lastUsedFormatted = $derived(
		command.last_used ? formatDistanceToNow(new Date(command.last_used)) + ' ago' : 'Never'
	);

	// Build link for command detail page
	let detailHref = $derived(`/commands/${encodeURIComponent(command.name)}`);
</script>

<a
	href={detailHref}
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
			<CategoryIcon size={22} strokeWidth={2.5} />
		</div>
		<div class="flex items-center gap-2">
			<TierBadge {tier} />
			<Badge variant={badgeVariant} size="sm" rounded="full">
				{categoryLabel}
			</Badge>
		</div>
	</div>

	<!-- Command name -->
	<h3
		class="text-lg font-bold text-[var(--text-primary)] mb-2 truncate pr-4 tracking-tight group-hover:text-[var(--accent)] transition-colors"
		title={command.name}
	>
		/{command.name}
	</h3>

	<!-- Description if available -->
	{#if command.description}
		<p class="text-xs text-[var(--text-muted)] mb-4 line-clamp-2" title={command.description}>
			{command.description}
		</p>
	{:else}
		<div class="mb-4"></div>
	{/if}

	<!-- Stats with progress bar -->
	<div class="space-y-3 mb-4">
		<!-- Runs stat with progress bar -->
		<div>
			<div class="flex items-center justify-between mb-1.5">
				<div class="flex items-center gap-2 text-xs text-[var(--text-muted)]">
					<Play size={12} />
					<span class="font-medium">Uses</span>
				</div>
				<span class="text-sm font-semibold text-[var(--text-primary)] tabular-nums">
					{command.count.toLocaleString()}
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
		{#if command.session_count != null}
			<div class="flex items-center justify-between text-xs">
				<div class="flex items-center gap-2 text-[var(--text-muted)]">
					<MessageSquare size={12} />
					<span class="font-medium">Sessions</span>
				</div>
				<span class="text-sm font-semibold text-[var(--text-primary)] tabular-nums">
					{command.session_count}
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
	</div>
</a>
