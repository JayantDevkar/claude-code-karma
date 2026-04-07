<script lang="ts">
	import { Dialog } from 'bits-ui';
	import { X, Loader2, AlertCircle } from 'lucide-svelte';
	import { marked } from 'marked';
	import DOMPurify from 'isomorphic-dompurify';
	import { formatDistanceToNow } from 'date-fns';
	import { markdownCopyButtons } from '$lib/actions/markdownCopyButtons';
	import { API_BASE } from '$lib/config';
	import type { ProjectMemoryFile, MemoryFileType } from '$lib/api-types';

	interface Props {
		filename: string | null;
		projectEncodedName: string;
		onClose: () => void;
	}

	let { filename, projectEncodedName, onClose }: Props = $props();

	let loading = $state(false);
	let error = $state<string | null>(null);
	let fileData = $state<ProjectMemoryFile | null>(null);
	let renderedContent = $state('');
	let bodyFading = $state(false);

	const open = $derived(filename !== null);

	async function fetchFile(name: string) {
		loading = true;
		error = null;
		bodyFading = true;
		try {
			const res = await fetch(
				`${API_BASE}/projects/${projectEncodedName}/memory/files/${encodeURIComponent(name)}`
			);
			if (res.status === 404) {
				error = 'This memory file no longer exists.';
				fileData = null;
				return;
			}
			if (res.status === 400) {
				error = 'Invalid memory file name.';
				fileData = null;
				return;
			}
			if (res.status === 403) {
				error = 'Access to this file is not allowed.';
				fileData = null;
				return;
			}
			if (!res.ok) {
				throw new Error(`HTTP ${res.status}`);
			}
			const data: ProjectMemoryFile = await res.json();
			fileData = data;
		} catch (e) {
			console.error('Failed to fetch memory file', e);
			error = 'Failed to load this memory file.';
			fileData = null;
		} finally {
			loading = false;
			// Brief fade-out → fade-in to signal content has swapped
			setTimeout(() => {
				bodyFading = false;
			}, 80);
		}
	}

	// Fetch when filename changes
	$effect(() => {
		if (filename) {
			fetchFile(filename);
		} else {
			// Clear state when panel closes
			fileData = null;
			error = null;
			renderedContent = '';
		}
	});

	// Render markdown when fileData changes
	$effect(() => {
		if (!fileData?.content) {
			renderedContent = '';
			return;
		}
		const parsed = marked.parse(fileData.content);
		if (parsed instanceof Promise) {
			parsed.then((html) => {
				renderedContent = DOMPurify.sanitize(html);
			});
		} else {
			renderedContent = DOMPurify.sanitize(parsed);
		}
	});

	function formatRelative(dateStr: string): string {
		try {
			return formatDistanceToNow(new Date(dateStr), { addSuffix: true });
		} catch {
			return dateStr;
		}
	}

	function handleOpenChange(isOpen: boolean) {
		if (!isOpen) onClose();
	}

	function handleRetry() {
		if (filename) fetchFile(filename);
	}

	const TYPE_BADGE_CLASSES: Record<MemoryFileType, string> = {
		user: 'bg-blue-500/15 text-blue-600 dark:text-blue-400 ring-blue-500/20',
		feedback: 'bg-amber-500/15 text-amber-600 dark:text-amber-400 ring-amber-500/20',
		project: 'bg-violet-500/15 text-violet-600 dark:text-violet-400 ring-violet-500/20',
		reference: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 ring-emerald-500/20'
	};

	const TYPE_LABELS: Record<MemoryFileType, string> = {
		user: 'User',
		feedback: 'Feedback',
		project: 'Project',
		reference: 'Reference'
	};

	function badgeClass(type: MemoryFileType | null): string {
		const base =
			'inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ring-1';
		if (type === null) {
			return `${base} bg-[var(--bg-muted)] text-[var(--text-muted)] ring-[var(--border)]`;
		}
		return `${base} ${TYPE_BADGE_CLASSES[type]}`;
	}

	function badgeLabel(type: MemoryFileType | null): string {
		return type === null ? '—' : TYPE_LABELS[type];
	}
</script>

<Dialog.Root {open} onOpenChange={handleOpenChange}>
	<Dialog.Portal>
		<Dialog.Overlay
			class="
				fixed inset-0 z-40
				bg-black/40
				data-[state=open]:animate-in
				data-[state=closed]:animate-out
				data-[state=closed]:fade-out-0
				data-[state=open]:fade-in-0
			"
		/>
		<Dialog.Content
			class="
				memory-file-panel
				fixed top-0 right-0 z-50
				h-full w-full sm:w-[560px]
				bg-[var(--bg-base)]
				border-l border-[var(--border)]
				flex flex-col
				focus:outline-none
				data-[state=open]:animate-in
				data-[state=closed]:animate-out
				data-[state=closed]:slide-out-to-right
				data-[state=open]:slide-in-from-right
			"
			data-testid="memory-file-panel"
		>
			<!-- Sticky header -->
			<div
				class="sticky top-0 z-10 flex items-start justify-between gap-3 px-5 py-4 border-b border-[var(--border)] bg-[var(--bg-base)]"
			>
				<div class="flex-1 min-w-0 space-y-2">
					{#if fileData}
						<div class="flex items-center gap-2">
							<span class={badgeClass(fileData.type)} data-testid="panel-badge">
								{badgeLabel(fileData.type)}
							</span>
							<span class="text-[11px] text-[var(--text-muted)]">
								{formatRelative(fileData.modified)}
							</span>
						</div>
						<Dialog.Title
							class="text-base font-semibold text-[var(--text-primary)] leading-snug truncate"
						>
							{fileData.name}
						</Dialog.Title>
						<Dialog.Description
							class="text-[11px] font-mono text-[var(--text-muted)] truncate"
						>
							{fileData.filename}
						</Dialog.Description>
					{:else if loading}
						<Dialog.Title class="text-base font-semibold text-[var(--text-primary)]">
							Loading…
						</Dialog.Title>
						<Dialog.Description class="sr-only">
							Loading memory file content
						</Dialog.Description>
					{:else if error}
						<Dialog.Title class="text-base font-semibold text-[var(--text-primary)]">
							Memory file
						</Dialog.Title>
						<Dialog.Description class="sr-only">
							{error}
						</Dialog.Description>
					{/if}
				</div>
				<Dialog.Close
					class="
						shrink-0
						text-[var(--text-muted)]
						hover:text-[var(--text-primary)]
						transition-colors
						focus:outline-none
						focus-visible:ring-2
						focus-visible:ring-[var(--accent)]
						rounded-md
						p-1
					"
					aria-label="Close memory file"
				>
					<X size={18} />
				</Dialog.Close>
			</div>

			<!-- Scrollable body -->
			<div class="flex-1 overflow-y-auto">
				{#if loading && !fileData}
					<div class="flex items-center justify-center h-full">
						<Loader2 size={24} class="animate-spin text-[var(--text-muted)]" />
					</div>
				{:else if error}
					<div class="flex flex-col items-center justify-center h-full px-8 text-center">
						<AlertCircle size={32} class="text-[var(--text-muted)] mb-3" />
						<p class="text-sm text-[var(--text-primary)] mb-1">{error}</p>
						<p class="text-xs text-[var(--text-muted)] mb-4">
							{filename ?? ''}
						</p>
						<button
							type="button"
							onclick={handleRetry}
							class="text-xs font-medium px-3 py-1.5 rounded-md border border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text-primary)] hover:bg-[var(--bg-muted)] transition-colors"
						>
							Retry
						</button>
					</div>
				{:else if fileData}
					<div
						class="px-6 py-6 markdown-preview max-w-none prose prose-slate dark:prose-invert transition-opacity duration-150"
						class:opacity-0={bodyFading}
						use:markdownCopyButtons={renderedContent}
						data-testid="memory-file-body"
					>
						{@html renderedContent}
					</div>
				{/if}
			</div>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>

<style>
	:global(.memory-file-panel[data-state='open']) {
		animation-duration: 300ms !important;
		animation-timing-function: cubic-bezier(0.16, 1, 0.3, 1) !important;
	}

	:global(.memory-file-panel[data-state='closed']) {
		animation-duration: 200ms !important;
		animation-timing-function: cubic-bezier(0.4, 0, 1, 1) !important;
	}

	:global(.slide-in-from-right) {
		animation-name: slideInFromRight;
	}

	:global(.slide-out-to-right) {
		animation-name: slideOutToRight;
	}

	@keyframes slideInFromRight {
		from {
			transform: translateX(100%);
		}
		to {
			transform: translateX(0);
		}
	}

	@keyframes slideOutToRight {
		from {
			transform: translateX(0);
		}
		to {
			transform: translateX(100%);
		}
	}
</style>
