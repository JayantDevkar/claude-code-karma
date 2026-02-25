<script lang="ts">
	import { goto } from '$app/navigation';
	import { FileText, ExternalLink } from 'lucide-svelte';
	import { formatDistanceToNow } from 'date-fns';
	import type { PlanWithContext } from '$lib/api-types';
	import Card from '$lib/components/ui/Card.svelte';

	interface Props {
		plan: PlanWithContext;
	}
	let { plan }: Props = $props();

	let updatedAgo = $derived(formatDistanceToNow(new Date(plan.modified), { addSuffix: true }));

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

<a href="/plans/{plan.slug}" class="block group">
	<Card
		variant="default"
		padding="md"
		class="h-full transition-all hover:border-[var(--accent)]/50"
	>
		<div class="flex items-start gap-3">
			<div class="p-2 rounded-lg bg-[var(--accent-subtle)] shrink-0">
				<FileText size={16} class="text-[var(--accent)]" />
			</div>
			<div class="flex-1 min-w-0">
				<h3
					class="font-medium text-[var(--text-primary)] truncate group-hover:text-[var(--accent)]"
				>
					{plan.title || plan.slug}
				</h3>
				{#if plan.session_context && sessionUrl}
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
