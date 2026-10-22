<script lang="ts">
	import { page } from '$app/stores';
	import { AlertTriangle, ArrowLeft } from 'lucide-svelte';

	const notFound = $derived($page.status === 404);
</script>

<div class="flex flex-col items-center justify-center min-h-[60vh] p-8">
	<div class="flex flex-col items-center gap-4 max-w-md text-center">
		<div
			class="flex h-16 w-16 items-center justify-center rounded-full bg-[var(--error-subtle)]"
		>
			<AlertTriangle size={32} class="text-[var(--error)]" />
		</div>
		<p
			class="font-mono text-xs font-semibold uppercase tracking-wider text-[var(--text-secondary)]"
		>
			Error {$page.status}
		</p>
		<h1 class="text-xl font-semibold text-[var(--text-primary)]">
			{notFound ? 'Page not found' : 'Something went wrong'}
		</h1>
		<p class="text-[var(--text-secondary)] break-words">
			{#if notFound}
				There is no page at <code class="font-mono text-[var(--text-primary)]"
					>{$page.url.pathname}</code
				>.
			{:else}
				{$page.error?.message ?? 'An unexpected error occurred.'}
			{/if}
		</p>
		<a
			href="/"
			class="inline-flex items-center gap-2 mt-4 px-4 py-2 rounded-lg bg-[var(--accent)] text-[var(--bg-base)] font-medium hover:opacity-90 transition-opacity"
		>
			<ArrowLeft size={16} />
			Back to Home
		</a>
	</div>
</div>
