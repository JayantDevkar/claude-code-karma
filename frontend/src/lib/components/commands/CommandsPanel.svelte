<script lang="ts">
	import { TerminalSquare, Zap, Loader2, Copy, Check } from 'lucide-svelte';
	import { marked } from 'marked';
	import DOMPurify from 'isomorphic-dompurify';
	import type { CommandUsage } from '$lib/api-types';
	import EmptyState from '$lib/components/ui/EmptyState.svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import { cleanSkillName, getCommandColorVars, getCommandCategoryColorVars, getCommandCategoryLabel } from '$lib/utils';
	import { API_BASE } from '$lib/config';
	import { markdownCopyButtons } from '$lib/actions/markdownCopyButtons';

	interface Props {
		commands: CommandUsage[];
		projectEncodedName?: string;
	}

	let { commands, projectEncodedName }: Props = $props();

	// Deduplicate commands by name (same command can appear multiple times with different invocation_source)
	let sortedCommands = $derived.by(() => {
		const merged = new Map<string, CommandUsage>();
		for (const cmd of commands) {
			const existing = merged.get(cmd.name);
			if (existing) {
				merged.set(cmd.name, { ...existing, count: existing.count + cmd.count });
			} else {
				merged.set(cmd.name, { ...cmd });
			}
		}
		return [...merged.values()].sort((a, b) => b.count - a.count);
	});

	// Modal state
	let modalOpen = $state(false);
	let modalTitle = $state('');
	let modalContent = $state('');
	let modalLoading = $state(false);
	let modalError = $state<string | null>(null);
	let copied = $state(false);

	let renderedContent = $state('');

	// Strip YAML frontmatter and leading h1 that duplicates the modal title
	function stripFrontmatterAndTitle(raw: string, commandName: string): string {
		let text = raw;
		// Remove YAML frontmatter
		if (text.startsWith('---')) {
			const end = text.indexOf('---', 3);
			if (end !== -1) {
				text = text.slice(end + 3).trimStart();
			}
		}
		// Remove leading h1 if it matches the command name
		const h1Match = text.match(/^#\s+(.+)\n*/);
		if (h1Match) {
			const h1Text = h1Match[1].trim().replace(/^\//, '');
			if (h1Text === commandName || h1Text === `/${commandName}`) {
				text = text.slice(h1Match[0].length);
			}
		}
		return text;
	}

	$effect(() => {
		if (!modalContent) {
			renderedContent = '';
			return;
		}
		const cleaned = stripFrontmatterAndTitle(modalContent, modalTitle.replace(/^\//, ''));
		const parsed = marked.parse(cleaned);
		if (parsed instanceof Promise) {
			parsed.then((html) => (renderedContent = DOMPurify.sanitize(html)));
		} else {
			renderedContent = DOMPurify.sanitize(parsed);
		}
	});

	function isPluginCommand(command: CommandUsage): boolean {
		if (command.category) {
			return command.category === 'plugin_skill' || command.category === 'plugin_command';
		}
		return command.source === 'plugin';
	}

	function isBuiltinCommand(command: CommandUsage): boolean {
		if (command.category) {
			return command.category === 'builtin_command';
		}
		return command.source === 'builtin' || command.source === 'unknown';
	}

	async function openCommand(command: CommandUsage) {
		if (isBuiltinCommand(command)) return;
		const displayName = isPluginCommand(command) ? cleanSkillName(command.name, true) : command.name;
		modalTitle = `/${displayName}`;
		modalContent = '';
		modalError = null;
		modalLoading = true;
		modalOpen = true;

		try {
			let url: string;
			if (isPluginCommand(command)) {
				url = `${API_BASE}/skills/info/${encodeURIComponent(command.name)}`;
			} else {
				const base = `${API_BASE}/commands/info/${encodeURIComponent(command.name)}`;
				url = projectEncodedName
					? `${base}?project=${encodeURIComponent(projectEncodedName)}`
					: base;
			}

			const res = await fetch(url);
			if (!res.ok) {
				modalError =
					res.status === 404 ? 'Command file not found' : 'Failed to fetch command';
				return;
			}
			const data = await res.json();
			modalContent = data.content || '';
		} catch (e: any) {
			modalError = e.message;
		} finally {
			modalLoading = false;
		}
	}

	function copyContent() {
		if (modalContent) {
			navigator.clipboard.writeText(modalContent);
			copied = true;
			setTimeout(() => (copied = false), 2000);
		}
	}

	function getCommandColors(command: CommandUsage): { color: string; subtle: string } {
		if (command.category) {
			return getCommandCategoryColorVars(command.category);
		}
		return getCommandColorVars(command.source ?? 'unknown', command.plugin);
	}

	function getBadgeLabel(command: CommandUsage): string {
		if (command.category) {
			return getCommandCategoryLabel(command.category);
		}
		switch (command.source) {
			case 'builtin':
				return 'Built-in';
			case 'plugin':
				return 'Plugin';
			case 'project':
				return 'Project';
			case 'user':
				return 'User';
			default:
				return 'Unknown';
		}
	}
</script>

<div class="flex flex-col gap-2">
	<span class="text-[10px] uppercase tracking-wide font-medium text-[var(--text-muted)]">
		{sortedCommands.length} command{sortedCommands.length !== 1 ? 's' : ''}
	</span>

	{#if sortedCommands.length > 0}
		<div class="flex flex-col rounded-lg border border-[var(--border)]/60 overflow-hidden bg-[var(--bg-base)]">
			{#each sortedCommands as command, i (command.name)}
				{@const cmdColors = getCommandColors(command)}
				{@const Icon = isPluginCommand(command) ? Zap : TerminalSquare}
				{@const isClickable = !isBuiltinCommand(command)}
				{@const displayName = isPluginCommand(command) ? cleanSkillName(command.name, true) : command.name}

				<button
					onclick={() => openCommand(command)}
					disabled={!isClickable}
					class="group flex items-center gap-2.5 px-3 py-2.5 text-left hover:bg-[var(--bg-subtle)] transition-colors {i > 0 ? 'border-t border-[var(--border)]/40' : ''} {isClickable ? 'cursor-pointer' : 'cursor-default'}"
				>
					<span
						class="shrink-0 flex items-center justify-center w-6 h-6 rounded-md"
						style="background: {cmdColors.subtle}; color: {cmdColors.color};"
					>
						<Icon size={13} strokeWidth={2} />
					</span>

					<div class="flex-1 min-w-0">
						<span class="text-xs font-medium text-[var(--text-primary)] truncate block" title={command.name}>/{displayName}</span>
						<div class="flex items-center gap-1 mt-0.5">
							<span class="text-[10px] font-medium px-1 py-px rounded" style="background: {cmdColors.subtle}; color: {cmdColors.color};">{getBadgeLabel(command)}</span>
							{#if command.plugin}<span class="text-[10px] text-[var(--text-faint)] truncate">{command.plugin}</span>{/if}
						</div>
					</div>

					<span class="shrink-0 font-mono text-[11px] font-semibold" style="color: {cmdColors.color};">{command.count}×</span>
				</button>
			{/each}
		</div>
	{:else}
		<EmptyState
			icon={TerminalSquare}
			title="No commands used"
			description="Slash commands invoked during this session will appear here"
		/>
	{/if}
</div>

<!-- Command content modal -->
<Modal bind:open={modalOpen} title={modalTitle} maxWidth="xl">
	{#snippet children()}
		{#if modalLoading}
			<div class="flex items-center justify-center gap-2 py-12 text-[var(--text-muted)]">
				<Loader2 size={16} class="animate-spin" />
				<span class="text-sm">Loading command content...</span>
			</div>
		{:else if modalError}
			<div class="py-8 text-center text-sm text-[var(--text-muted)]">
				{modalError}
			</div>
		{:else}
			<div class="markdown-preview max-h-[70vh] overflow-y-auto pr-2 custom-scrollbar" use:markdownCopyButtons={renderedContent}>
				{@html renderedContent}
			</div>
		{/if}
	{/snippet}
	{#snippet footer()}
		<button
			onclick={copyContent}
			class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-muted)] transition-colors {copied
				? 'text-green-500'
				: ''}"
		>
			{#if copied}
				<Check size={14} />
				<span>Copied!</span>
			{:else}
				<Copy size={14} />
				<span>Copy</span>
			{/if}
		</button>
	{/snippet}
</Modal>

<style>
	.custom-scrollbar::-webkit-scrollbar {
		width: 6px;
	}
	.custom-scrollbar::-webkit-scrollbar-track {
		background: var(--bg-subtle);
		border-radius: 3px;
	}
	.custom-scrollbar::-webkit-scrollbar-thumb {
		background: var(--border);
		border-radius: 3px;
	}
	.custom-scrollbar::-webkit-scrollbar-thumb:hover {
		background: var(--text-muted);
	}
</style>
