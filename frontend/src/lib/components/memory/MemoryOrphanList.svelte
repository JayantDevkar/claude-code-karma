<script lang="ts">
	import { ChevronRight, FileText } from 'lucide-svelte';
	import { formatDistanceToNow } from 'date-fns';
	import type { MemoryFileMeta, MemoryFileType } from '$lib/api-types';

	interface Props {
		files: MemoryFileMeta[];
		onLinkHover: (filename: string, rect: DOMRect) => void;
		onLinkLeave: () => void;
		onLinkSelect: (filename: string) => void;
	}

	let { files, onLinkHover, onLinkLeave, onLinkSelect }: Props = $props();

	let expanded = $state(false);

	function formatRelative(dateStr: string): string {
		try {
			return formatDistanceToNow(new Date(dateStr), { addSuffix: true });
		} catch {
			return dateStr;
		}
	}

	function handleRowEnter(e: Event, filename: string) {
		const target = e.currentTarget as HTMLElement;
		onLinkHover(filename, target.getBoundingClientRect());
	}

	function handleRowLeave() {
		onLinkLeave();
	}

	function handleRowClick(filename: string) {
		onLinkSelect(filename);
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
			'inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ring-1 shrink-0';
		if (type === null) {
			return `${base} bg-[var(--bg-muted)] text-[var(--text-muted)] ring-[var(--border)]`;
		}
		return `${base} ${TYPE_BADGE_CLASSES[type]}`;
	}

	function badgeLabel(type: MemoryFileType | null): string {
		return type === null ? '—' : TYPE_LABELS[type];
	}
</script>

{#if files.length > 0}
	<div
		class="rounded-lg border border-[var(--border)] bg-[var(--bg-base)]"
		data-testid="memory-orphan-list"
	>
		<button
			type="button"
			class="w-full flex items-center gap-2.5 px-5 py-3 text-left hover:bg-[var(--bg-subtle)] rounded-lg transition-colors"
			onclick={() => (expanded = !expanded)}
			aria-expanded={expanded}
			data-testid="memory-orphan-toggle"
		>
			<ChevronRight
				size={16}
				class="text-[var(--text-muted)] transition-transform duration-150 {expanded
					? 'rotate-90'
					: ''}"
			/>
			<FileText size={14} class="text-[var(--text-muted)]" />
			<span class="text-sm font-medium text-[var(--text-primary)]">
				Other memory files
			</span>
			<span class="text-xs text-[var(--text-muted)]">({files.length})</span>
		</button>

		{#if expanded}
			<ul class="border-t border-[var(--border)] divide-y divide-[var(--border)]">
				{#each files as file (file.filename)}
					<li>
						<button
							type="button"
							class="w-full flex items-start gap-3 px-5 py-3 text-left hover:bg-[var(--bg-subtle)] transition-colors"
							onmouseenter={(e) => handleRowEnter(e, file.filename)}
							onmouseleave={handleRowLeave}
							onfocus={(e) => handleRowEnter(e, file.filename)}
							onblur={handleRowLeave}
							onclick={() => handleRowClick(file.filename)}
							data-testid="memory-orphan-row"
							data-memory-file={file.filename}
						>
							<span class={badgeClass(file.type)}>{badgeLabel(file.type)}</span>
							<div class="flex-1 min-w-0">
								<div class="flex items-baseline justify-between gap-2">
									<span
										class="text-sm font-medium text-[var(--text-primary)] truncate"
									>
										{file.name}
									</span>
									<span class="text-[10px] text-[var(--text-muted)] shrink-0">
										{formatRelative(file.modified)}
									</span>
								</div>
								{#if file.description}
									<p
										class="text-xs text-[var(--text-secondary)] mt-0.5 truncate"
									>
										{file.description}
									</p>
								{/if}
								<div class="flex items-center gap-2 mt-1">
									<span class="text-[10px] text-[var(--text-muted)] font-mono">
										{file.filename}
									</span>
									<span class="text-[10px] text-[var(--text-muted)]">·</span>
									<span class="text-[10px] text-[var(--text-muted)]">
										{file.word_count.toLocaleString()} words
									</span>
								</div>
							</div>
						</button>
					</li>
				{/each}
			</ul>
		{/if}
	</div>
{/if}
