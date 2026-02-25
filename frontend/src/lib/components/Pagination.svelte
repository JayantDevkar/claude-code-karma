<script lang="ts">
	import { ChevronLeft, ChevronRight } from 'lucide-svelte';

	interface Props {
		total: number;
		page: number;
		perPage: number;
		totalPages: number;
		onPageChange: (page: number) => void;
		itemLabel?: string;
	}

	let { total, page, perPage, totalPages, onPageChange, itemLabel = 'items' }: Props = $props();

	const showingStart = $derived((page - 1) * perPage + 1);
	const showingEnd = $derived(Math.min(page * perPage, total));
	const hasPrev = $derived(page > 1);
	const hasNext = $derived(page < totalPages);

	// Google-style page numbers with ellipsis
	const pageNumbers = $derived.by(() => {
		const pages: (number | 'ellipsis')[] = [];
		const maxVisiblePages = 7;

		if (totalPages <= maxVisiblePages) {
			for (let i = 1; i <= totalPages; i++) {
				pages.push(i);
			}
		} else {
			pages.push(1);
			if (page > 3) pages.push('ellipsis');

			const start = Math.max(2, page - 1);
			const end = Math.min(totalPages - 1, page + 1);
			for (let i = start; i <= end; i++) {
				pages.push(i);
			}

			if (page < totalPages - 2) pages.push('ellipsis');
			if (totalPages > 1) pages.push(totalPages);
		}

		return pages;
	});
</script>

{#if totalPages > 1}
	<div
		class="flex flex-col sm:flex-row items-center justify-between gap-4 pt-6 border-t border-[var(--border)] mt-8"
	>
		<!-- Showing info -->
		<div class="text-xs text-[var(--text-muted)] tabular-nums">
			Showing <span class="font-medium text-[var(--text-secondary)]">{showingStart}</span>
			-
			<span class="font-medium text-[var(--text-secondary)]">{showingEnd}</span>
			of
			<span class="font-medium text-[var(--text-secondary)]">{total.toLocaleString()}</span>
			{itemLabel}
		</div>

		<!-- Page Navigation -->
		<nav class="flex items-center gap-1" aria-label="Pagination">
			<!-- Previous Button -->
			<button
				onclick={() => onPageChange(page - 1)}
				disabled={!hasPrev}
				class="p-2 rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--bg-base)]
					hover:bg-[var(--bg-subtle)] hover:border-[var(--border-hover)]
					disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-[var(--bg-base)] disabled:hover:border-[var(--border)]
					transition-colors"
				aria-label="Go to previous page"
			>
				<ChevronLeft size={16} strokeWidth={2} class="text-[var(--text-secondary)]" />
			</button>

			<!-- Page Numbers -->
			{#each pageNumbers as pageNum, i (i)}
				{#if pageNum === 'ellipsis'}
					<span class="px-2 text-[var(--text-faint)] text-sm">...</span>
				{:else}
					<button
						onclick={() => onPageChange(pageNum)}
						class="min-w-[36px] h-9 px-3 text-sm font-medium rounded-[var(--radius-md)] border transition-colors tabular-nums
							{pageNum === page
							? 'bg-[var(--accent)] border-[var(--accent)] text-white'
							: 'bg-[var(--bg-base)] border-[var(--border)] text-[var(--text-secondary)] hover:bg-[var(--bg-subtle)] hover:border-[var(--border-hover)]'}"
						aria-label="Go to page {pageNum}"
						aria-current={pageNum === page ? 'page' : undefined}
					>
						{pageNum}
					</button>
				{/if}
			{/each}

			<!-- Next Button -->
			<button
				onclick={() => onPageChange(page + 1)}
				disabled={!hasNext}
				class="p-2 rounded-[var(--radius-md)] border border-[var(--border)] bg-[var(--bg-base)]
					hover:bg-[var(--bg-subtle)] hover:border-[var(--border-hover)]
					disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-[var(--bg-base)] disabled:hover:border-[var(--border)]
					transition-colors"
				aria-label="Go to next page"
			>
				<ChevronRight size={16} strokeWidth={2} class="text-[var(--text-secondary)]" />
			</button>
		</nav>
	</div>
{/if}
