<script lang="ts">
	import { goto } from '$app/navigation';
	import { Zap, Puzzle, Play, Clock, MessageSquare } from 'lucide-svelte';
	import { formatDistanceToNow } from 'date-fns';
	import Badge from '$lib/components/ui/Badge.svelte';
	import TierBadge from '$lib/components/ui/TierBadge.svelte';
	import { getSkillColorVars, cleanSkillName, getUsageTier } from '$lib/utils';

	interface Skill {
		name: string;
		count: number;
		is_plugin: boolean;
		plugin: string | null;
		last_used?: string | null;
		session_count?: number;
	}

	interface Props {
		skill: Skill;
		maxUsage?: number;
		class?: string;
	}

	let { skill, maxUsage = 100, class: className = '' }: Props = $props();

	// Consistent hash-based colors
	let colorVars = $derived(getSkillColorVars(skill.name, skill.is_plugin, skill.plugin));

	// Clean display name
	let displayName = $derived(cleanSkillName(skill.name, skill.is_plugin));

	// Badge variant based on type
	type BadgeVariant = 'purple' | 'accent';
	let badgeVariant = $derived<BadgeVariant>(skill.is_plugin ? 'purple' : 'accent');
	let badgeText = $derived(skill.is_plugin ? 'Plugin' : 'Custom');

	// Calculate usage percentage for progress bar
	let usagePercentage = $derived(Math.min((skill.count / maxUsage) * 100, 100));

	// Tier badge
	let tier = $derived(getUsageTier(skill.count, maxUsage));

	// Format last used as relative time
	let lastUsedFormatted = $derived(
		skill.last_used ? formatDistanceToNow(new Date(skill.last_used)) + ' ago' : 'Never'
	);

	// Build link for skill detail page
	let detailHref = $derived(`/skills/${encodeURIComponent(skill.name)}`);
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
			<Zap size={22} strokeWidth={2.5} />
		</div>
		<div class="flex items-center gap-2">
			<TierBadge {tier} />
			<Badge variant={badgeVariant} size="sm" rounded="full">
				{badgeText}
			</Badge>
		</div>
	</div>

	<!-- Skill name -->
	<h3
		class="text-lg font-bold text-[var(--text-primary)] mb-2 truncate pr-4 tracking-tight group-hover:text-[var(--accent)] transition-colors"
		title={skill.name}
	>
		{displayName}
	</h3>

	<!-- Plugin source if applicable -->
	{#if skill.plugin}
		<div class="mb-4">
			<span
				role="link"
				tabindex={0}
				class="
					inline-flex items-center gap-1.5 px-2 py-1
					text-[10px] font-medium cursor-pointer
					text-[var(--text-muted)] hover:text-[var(--accent)]
					bg-[var(--bg-subtle)] hover:bg-[var(--accent-subtle)]
					rounded-full
					transition-colors
				"
				onclick={(e) => {
					e.preventDefault();
					e.stopPropagation();
					goto(`/plugins/${encodeURIComponent(skill.plugin!)}`);
				}}
				onkeydown={(e) => {
					if (e.key === 'Enter') {
						e.stopPropagation();
						goto(`/plugins/${encodeURIComponent(skill.plugin!)}`);
					}
				}}
				title="View plugin: {skill.plugin}"
			>
				<Puzzle size={10} />
				<span class="truncate max-w-[140px]">{skill.plugin}</span>
			</span>
		</div>
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
					{skill.count.toLocaleString()}
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
		{#if skill.session_count != null}
			<div class="flex items-center justify-between text-xs">
				<div class="flex items-center gap-2 text-[var(--text-muted)]">
					<MessageSquare size={12} />
					<span class="font-medium">Sessions</span>
				</div>
				<span class="text-sm font-semibold text-[var(--text-primary)] tabular-nums">
					{skill.session_count}
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
		{#if skill.session_count != null}
			<span class="flex items-center gap-1.5">
				<MessageSquare size={12} />
				<span
					>{skill.session_count} session{skill.session_count !== 1 ? 's' : ''}</span
				>
			</span>
		{/if}
	</div>
</a>
