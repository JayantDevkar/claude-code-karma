<script lang="ts">
	import { GitBranch, Clock } from 'lucide-svelte';
	import { formatRelativeTime } from '$lib/utils';
	import type { BranchSummary } from '$lib/api-types';

	interface Props {
		branches: BranchSummary[];
		activeBranches: string[];
		selectedBranches: Set<string>;
		onBranchToggle: (branch: string) => void;
		onClearAll?: () => void;
		isLoading?: boolean;
		class?: string;
	}

	let {
		branches,
		activeBranches,
		selectedBranches,
		onBranchToggle,
		onClearAll,
		isLoading = false,
		class: className = ''
	}: Props = $props();

	// Sort branches: active first, then by session count
	const sortedBranches = $derived(
		[...branches].sort((a, b) => {
			const aActive = activeBranches.includes(a.name);
			const bActive = activeBranches.includes(b.name);
			if (aActive && !bActive) return -1;
			if (!aActive && bActive) return 1;
			return b.session_count - a.session_count;
		})
	);
</script>

<div
	class="
		p-4 pl-5
		bg-[var(--bg-subtle)]
		border border-[var(--border)]
		border-l-[3px] border-l-[var(--nav-purple)]
		rounded-lg
		{className}
	"
>
	<div class="flex items-center gap-2 mb-3">
		<div class="p-1.5 rounded-md bg-[var(--nav-purple-subtle)]">
			<GitBranch size={14} strokeWidth={2} class="text-[var(--nav-purple)]" />
		</div>
		<h3 class="text-sm font-medium text-[var(--text-primary)]">
			Active Branches
			<span class="ml-1.5 text-xs font-normal text-[var(--text-muted)]">
				({activeBranches.length})
			</span>
		</h3>
		{#if isLoading}
			<div
				class="flex items-center gap-2 ml-auto text-xs font-medium text-[var(--nav-purple)] animate-pulse"
			>
				<div
					class="w-3.5 h-3.5 border-2 border-current border-t-transparent rounded-full animate-spin"
				></div>
				<span>Updating...</span>
			</div>
		{/if}
	</div>

	<div class="flex flex-wrap gap-2">
		{#each sortedBranches.slice(0, 8) as branch}
			{@const isActive = activeBranches.includes(branch.name)}
			{@const isSelected = selectedBranches.has(branch.name)}
			<button
				type="button"
				onclick={() => onBranchToggle(branch.name)}
				aria-pressed={isSelected}
				aria-label="Filter sessions by branch {branch.name}"
				class="
					inline-flex items-center gap-2
					px-3 py-1.5
					rounded-md
					border
					transition-all duration-200
					focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--nav-purple)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-subtle)]
					{isSelected
					? 'bg-[var(--nav-purple)] border-[var(--nav-purple)] text-white shadow-sm'
					: 'bg-[var(--bg-muted)] border-[var(--border)] text-[var(--text-secondary)] hover:border-[var(--nav-purple)]/40 hover:bg-[var(--nav-purple-subtle)] hover:text-[var(--text-primary)] cursor-pointer'}
				"
			>
				{#if isActive && !isSelected}
					<div class="w-1.5 h-1.5 rounded-full bg-[var(--success)] pulse-live"></div>
				{:else if isActive && isSelected}
					<div class="w-1.5 h-1.5 rounded-full bg-white pulse-live"></div>
				{/if}
				<span class="text-xs font-medium">{branch.name}</span>
				<span
					class="text-[10px] font-mono {isSelected
						? 'opacity-80'
						: 'text-[var(--nav-purple)]'}">({branch.session_count})</span
				>
			</button>
		{/each}

		{#if sortedBranches.length > 8}
			<div
				class="
					inline-flex items-center
					px-3 py-1.5
					text-xs text-[var(--text-muted)]
				"
			>
				+{sortedBranches.length - 8} more
			</div>
		{/if}
	</div>

	{#if sortedBranches[0]?.last_active}
		<div
			class="
				flex items-center gap-1.5 mt-3 pt-3
				border-t border-[var(--border)]
				text-xs text-[var(--text-muted)]
			"
		>
			<Clock size={12} strokeWidth={2} class="text-[var(--nav-purple)]/60" />
			<span>Last active: {formatRelativeTime(sortedBranches[0].last_active)}</span>
		</div>
	{/if}
</div>
