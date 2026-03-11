<script lang="ts">
	import { goto } from '$app/navigation';
	import { FileText, ExternalLink, Globe } from 'lucide-svelte';
	import { formatDistanceToNow } from 'date-fns';
	import type { PlanWithContext } from '$lib/api-types';
	import { getTeamMemberColor } from '$lib/utils';
	import Card from '$lib/components/ui/Card.svelte';

	interface Props {
		plan: PlanWithContext;
	}
	let { plan }: Props = $props();

	let updatedAgo = $derived(formatDistanceToNow(new Date(plan.modified), { addSuffix: true }));

	const isRemote = $derived(!!plan.remote_user_id);
	const teamMemberColor = $derived(
		plan.remote_user_id ? getTeamMemberColor(plan.remote_user_id) : null
	);

	// Build plan detail URL (with remote_user param for remote plans)
	let planHref = $derived(
		isRemote
			? `/plans/${plan.slug}?remote_user=${plan.remote_user_id}`
			: `/plans/${plan.slug}`
	);

	// Build session URL if context exists
	let sessionUrl = $derived(
		plan.session_context
			? `/projects/${plan.session_context.project_encoded_name}/${plan.session_context.session_slug}`
			: null
	);

	function navigateToSession(e: MouseEvent) {
		e.preventDefault();
		e.stopPropagation();
		if (sessionUrl) {
			goto(sessionUrl);
		}
	}
</script>

<a href={planHref} class="block group">
	<Card
		variant="default"
		padding="md"
		class="h-full transition-all hover:border-[var(--accent)]/50"
	>
		<div class="flex items-start gap-3">
			<div
				class="p-2 rounded-lg shrink-0 {isRemote && teamMemberColor ? '' : 'bg-[var(--accent-subtle)]'}"
				style={isRemote && teamMemberColor ? `background-color: ${teamMemberColor.bg}` : ''}
			>
				<FileText size={16} class={isRemote && teamMemberColor ? teamMemberColor.text : 'text-[var(--accent)]'} />
			</div>
			<div class="flex-1 min-w-0">
				<h3
					class="font-medium text-[var(--text-primary)] truncate group-hover:text-[var(--accent)]"
				>
					{plan.title || plan.slug}
				</h3>
				{#if isRemote && plan.remote_user_id}
					<a
						href="/members/{encodeURIComponent(plan.remote_user_id)}"
						class="flex items-center gap-1 px-2 py-0.5 mt-1 rounded-full border w-fit {teamMemberColor?.badge ?? ''} hover:opacity-80 transition-opacity"
						title="Remote plan from {plan.remote_user_id}"
						onclick={(e) => e.stopPropagation()}
					>
						<Globe size={10} strokeWidth={2} class={teamMemberColor?.text ?? ''} />
						<span class="font-medium text-[11px]">{plan.remote_user_id}</span>
					</a>
				{:else if plan.session_context && sessionUrl}
					<button
						type="button"
						onclick={navigateToSession}
						class="inline-flex items-center gap-1 text-xs text-[var(--text-muted)] truncate hover:text-[var(--accent)] transition-colors cursor-pointer"
					>
						<span class="truncate">{plan.session_context.session_slug}</span>
						<ExternalLink size={10} class="shrink-0" />
					</button>
				{/if}
				<p class="text-xs text-[var(--text-muted)] mt-1">
					{updatedAgo} · {plan.word_count.toLocaleString()} words
				</p>
			</div>
		</div>
	</Card>
</a>
