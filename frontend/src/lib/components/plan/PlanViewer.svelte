<script lang="ts">
	import { marked } from 'marked';
	import DOMPurify from 'isomorphic-dompurify';
	import { formatDistanceToNow } from 'date-fns';
	import { FileText } from 'lucide-svelte';
	import type { PlanDetail } from '$lib/api-types';
	import Card from '$lib/components/ui/Card.svelte';

	interface Props {
		plan: PlanDetail;
		embedded?: boolean;
		stripFirstH1?: boolean; // Remove first H1 when title is shown elsewhere
	}

	let { plan, embedded = false, stripFirstH1 = false }: Props = $props();

	// Strip the first H1 element from HTML (used when PageHeader shows the title)
	function removeFirstH1(html: string): string {
		// Match the first <h1>...</h1> including any attributes
		return html.replace(/<h1[^>]*>[\s\S]*?<\/h1>/, '');
	}

	// Render markdown content
	let renderedContent = $state('');

	$effect(() => {
		const parsed = marked.parse(plan.content || '');
		if (parsed instanceof Promise) {
			parsed.then((html) => {
				let sanitized = DOMPurify.sanitize(html);
				if (stripFirstH1) {
					sanitized = removeFirstH1(sanitized);
				}
				renderedContent = sanitized;
			});
		} else {
			let sanitized = DOMPurify.sanitize(parsed);
			if (stripFirstH1) {
				sanitized = removeFirstH1(sanitized);
			}
			renderedContent = sanitized;
		}
	});

	// Format date for subtitle
	function formatDate(dateStr: string): string {
		try {
			return formatDistanceToNow(new Date(dateStr), { addSuffix: true });
		} catch {
			return dateStr;
		}
	}

	// Build subtitle: "Updated X ago · Y words"
	let subtitle = $derived(() => {
		const updated = formatDate(plan.modified);
		const words = plan.word_count.toLocaleString();
		return `Updated ${updated} · ${words} words`;
	});
</script>

{#if embedded}
	<!-- Embedded mode: just the markdown content, no wrapper -->
	<div class="markdown-preview max-w-none prose prose-slate dark:prose-invert">
		{@html renderedContent}
	</div>
{:else}
	<!-- Standalone mode: single unified card -->
	<Card variant="default" padding="none" class="overflow-hidden">
		<!-- Header with title and subtitle -->
		<div class="px-6 py-4 border-b border-[var(--border)]">
			<div class="flex items-center gap-3">
				<div class="p-2 rounded-lg bg-[var(--accent-subtle)]">
					<FileText size={20} class="text-[var(--accent)]" />
				</div>
				<div>
					<h3 class="text-base font-semibold text-[var(--text-primary)]">
						{plan.title || plan.slug}
					</h3>
					<p class="text-sm text-[var(--text-muted)]">
						{subtitle()}
					</p>
				</div>
			</div>
		</div>

		<!-- Markdown Content -->
		<div class="p-6 md:p-8 markdown-preview max-w-none prose prose-slate dark:prose-invert">
			{@html renderedContent}
		</div>
	</Card>
{/if}
