<script lang="ts">
	import {
		Search,
		FileText,
		Terminal,
		Bot,
		Zap,
		Check,
		AlertCircle,
		Minimize2,
		MessageCircle
	} from 'lucide-svelte';
	import { getSubagentColorVars, getSubagentTypeDisplayName } from '$lib/utils';
	import type { SubagentStatus } from '$lib/api-types';

	interface Props {
		type: string | null | undefined;
		size?: 'sm' | 'md';
		class?: string;
		/** Optional status to show indicator (running/completed/error) */
		status?: SubagentStatus;
	}

	let { type, size = 'sm', class: className = '', status }: Props = $props();

	let sizeClasses = $derived(size === 'sm' ? 'px-2 py-0.5 text-[10px]' : 'px-2.5 py-1 text-xs');
	let iconSize = $derived(size === 'sm' ? 10 : 12);
	let statusDotSize = $derived(size === 'sm' ? 6 : 8);

	// Get color styles using the centralized utility
	let colorVars = $derived(getSubagentColorVars(type));
	// Get user-friendly display name
	let displayName = $derived(getSubagentTypeDisplayName(type));
</script>

{#if type}
	<span
		class="inline-flex items-center gap-1 rounded-full font-medium {sizeClasses} {className}"
		style="color: {colorVars.color}; background-color: {colorVars.subtle};"
	>
		{#if type === 'Explore'}
			<Search size={iconSize} strokeWidth={2} />
		{:else if type === 'Plan'}
			<FileText size={iconSize} strokeWidth={2} />
		{:else if type === 'Bash'}
			<Terminal size={iconSize} strokeWidth={2} />
		{:else if type === 'Claude Tax'}
			<Zap size={iconSize} strokeWidth={2} />
		{:else if type === 'acompact'}
			<Minimize2 size={iconSize} strokeWidth={2} />
		{:else if type === 'aprompt_suggestion'}
			<MessageCircle size={iconSize} strokeWidth={2} />
		{:else}
			<Bot size={iconSize} strokeWidth={2} />
		{/if}
		{displayName}
		{#if status}
			<span
				class="status-indicator"
				class:running={status === 'running'}
				class:completed={status === 'completed'}
				class:error={status === 'error'}
			>
				{#if status === 'running'}
					<span
						class="status-dot running"
						style="width: {statusDotSize}px; height: {statusDotSize}px;"
					></span>
				{:else if status === 'completed'}
					<Check size={statusDotSize + 2} strokeWidth={3} class="text-[var(--success)]" />
				{:else if status === 'error'}
					<AlertCircle
						size={statusDotSize + 2}
						strokeWidth={3}
						class="text-[var(--error)]"
					/>
				{/if}
			</span>
		{/if}
	</span>
{/if}

<style>
	.status-indicator {
		display: inline-flex;
		align-items: center;
		margin-left: 2px;
	}

	.status-dot {
		border-radius: 50%;
		flex-shrink: 0;
	}

	.status-dot.running {
		background-color: var(--success);
		animation: status-pulse 1.5s ease-in-out infinite;
	}

	@keyframes status-pulse {
		0%,
		100% {
			opacity: 1;
			transform: scale(1);
		}
		50% {
			opacity: 0.5;
			transform: scale(0.85);
		}
	}
</style>
