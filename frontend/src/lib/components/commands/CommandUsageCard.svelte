<script lang="ts">
	import { Zap, Terminal, Sparkles, Puzzle, FileText } from 'lucide-svelte';
	import UsageCard from '$lib/components/shared/UsageCard.svelte';
	import { getCommandCategoryColorVars, getCommandCategoryLabel, getUsageTier } from '$lib/utils';
	import type { CommandCategory } from '$lib/api-types';

	interface Command {
		name: string;
		count: number;
		category?: CommandCategory;
		is_plugin?: boolean;
		plugin?: string | null;
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

	let colorVars = $derived(getCommandCategoryColorVars(command.category ?? 'user_command'));
	let categoryLabel = $derived(getCommandCategoryLabel(command.category ?? 'user_command'));

	type BadgeVariant = 'purple' | 'accent' | 'blue' | 'emerald' | 'info';
	let badgeVariant = $derived<BadgeVariant>(
		command.category === 'builtin_command'
			? 'blue'
			: command.category === 'bundled_skill'
				? 'purple'
				: command.category === 'plugin_skill' || command.category === 'plugin_command'
					? 'emerald'
					: command.category === 'custom_skill'
						? 'info'
						: 'accent'
	);

	let CategoryIcon = $derived(
		command.category === 'builtin_command'
			? Terminal
			: command.category === 'bundled_skill'
				? Sparkles
				: command.category === 'plugin_skill' || command.category === 'plugin_command'
					? Puzzle
					: command.category === 'custom_skill'
						? Zap
						: FileText
	);

	let detailHref = $derived(`/commands/${encodeURIComponent(command.name)}`);
</script>

<UsageCard
	name={command.name}
	displayName="/{command.name}"
	href={detailHref}
	count={command.count}
	{maxUsage}
	{colorVars}
	{categoryLabel}
	{badgeVariant}
	description={command.description}
	lastUsed={command.last_used}
	sessionCount={command.session_count ?? null}
	class={className}
>
	{#snippet icon()}
		<CategoryIcon size={22} strokeWidth={2.5} />
	{/snippet}
</UsageCard>
