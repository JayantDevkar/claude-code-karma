<script lang="ts">
	import { marked } from 'marked';
	import DOMPurify from 'isomorphic-dompurify';
	import { goto } from '$app/navigation';
	import { Globe, Download, User, FolderOpen, Check } from 'lucide-svelte';
	import Modal from '$lib/components/ui/Modal.svelte';
	import { API_BASE } from '$lib/config';
	import type { InheritResult } from '$lib/api-types';

	interface Props {
		open: boolean;
		itemName: string;
		itemType: 'skill' | 'command' | 'agent';
		content?: string | null;
		sourceUserId?: string | null;
		onClose: () => void;
		onInherited?: (result: InheritResult) => void;
	}

	let {
		open,
		itemName,
		itemType,
		content = null,
		sourceUserId = null,
		onClose,
		onInherited
	}: Props = $props();

	let selectedScope = $state<'user' | 'project'>('user');
	let loading = $state(false);
	let errorMsg = $state<string | null>(null);
	let successMsg = $state<string | null>(null);

	let renderedContent = $state('');

	$effect(() => {
		if (!content) {
			renderedContent = '';
			return;
		}
		const parsed = marked.parse(content);
		if (parsed instanceof Promise) {
			parsed.then((html) => (renderedContent = DOMPurify.sanitize(html)));
		} else {
			renderedContent = DOMPurify.sanitize(parsed);
		}
	});

	const itemDir = $derived(itemType === 'command' ? 'commands' : itemType === 'agent' ? 'agents' : 'skills');
	const scopeLabels = $derived<Record<'user' | 'project', string>>({
		user: `~/.claude/${itemDir}/`,
		project: `.claude/${itemDir}/`
	});

	async function handleInherit() {
		loading = true;
		errorMsg = null;
		successMsg = null;

		try {
			const params = new URLSearchParams({ scope: selectedScope });
			const res = await fetch(
				`${API_BASE}/${itemType}s/${encodeURIComponent(itemName)}/inherit?${params}`,
				{ method: 'POST' }
			);

			if (!res.ok) {
				const body = await res.json().catch(() => ({}));
				errorMsg = body?.detail ?? `Failed to inherit ${itemType}`;
				return;
			}

			const result: InheritResult = await res.json();
			successMsg = `Inherited as "${result.inherited_name}" to ${result.path}`;
			onInherited?.(result);

			// Navigate to the inherited skill's page (only on fresh create, not re-inherit)
			if (itemType === 'skill' && result.inherited_name && result.status === 'created') {
				await goto(`/skills/${encodeURIComponent(result.inherited_name)}`);
			}
		} catch (e: unknown) {
			errorMsg = e instanceof Error ? e.message : 'Network error';
		} finally {
			loading = false;
		}
	}

	function handleOpenChange(isOpen: boolean) {
		if (!isOpen) {
			errorMsg = null;
			successMsg = null;
			onClose();
		}
	}
</script>

<Modal
	{open}
	onOpenChange={handleOpenChange}
	title="Inherit {itemType}: {itemName}"
	maxWidth="xl"
>
	{#snippet children()}
		<div class="space-y-5">
			<!-- Source attribution -->
			{#if sourceUserId}
				<div class="flex items-center gap-2 text-sm text-[var(--text-secondary)]">
					<Globe size={15} class="text-[var(--info)] shrink-0" />
					<span>From <span class="font-semibold text-[var(--text-primary)]">{sourceUserId}</span>'s machine</span>
				</div>
			{/if}

			<!-- Content preview -->
			{#if content}
				<div>
					<p class="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-2">
						Content Preview
					</p>
					<div
						class="
							max-h-[60vh] overflow-y-auto rounded-lg border border-[var(--border)]
							bg-[var(--bg-subtle)] p-4
							text-sm text-[var(--text-primary)]
							markdown-preview prose prose-slate
						"
					>
						{@html renderedContent}
					</div>
				</div>
			{/if}

			<!-- Scope selector -->
			<div>
				<p class="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider mb-2">
					Install Scope
				</p>
				<div class="grid grid-cols-2 gap-2">
					<button
						onclick={() => (selectedScope = 'user')}
						class="
							flex flex-col items-start gap-1 px-4 py-3 rounded-lg border text-left
							transition-all
							{selectedScope === 'user'
								? 'border-[var(--accent)] bg-[var(--accent-subtle)] text-[var(--accent)]'
								: 'border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text-secondary)] hover:border-[var(--border-hover)] hover:bg-[var(--bg-muted)]'}
						"
					>
						<div class="flex items-center gap-2 text-sm font-medium">
							<User size={14} />
							User Scope
						</div>
						<span class="text-[10px] font-mono opacity-70">{scopeLabels.user}</span>
					</button>

					<button
						onclick={() => (selectedScope = 'project')}
						class="
							flex flex-col items-start gap-1 px-4 py-3 rounded-lg border text-left
							transition-all
							{selectedScope === 'project'
								? 'border-[var(--accent)] bg-[var(--accent-subtle)] text-[var(--accent)]'
								: 'border-[var(--border)] bg-[var(--bg-subtle)] text-[var(--text-secondary)] hover:border-[var(--border-hover)] hover:bg-[var(--bg-muted)]'}
						"
					>
						<div class="flex items-center gap-2 text-sm font-medium">
							<FolderOpen size={14} />
							Project Scope
						</div>
						<span class="text-[10px] font-mono opacity-70">{scopeLabels.project}</span>
					</button>
				</div>
				{#if selectedScope === 'project'}
					<p class="mt-2 text-xs text-[var(--text-muted)]">
						Will be saved to <code class="font-mono">.claude/{itemDir}/{itemName}/</code> in the current project directory.
					</p>
				{/if}
			</div>

			<!-- Error / success feedback -->
			{#if errorMsg}
				<div class="px-4 py-3 rounded-lg border border-[var(--error)]/30 bg-[var(--error-subtle)] text-[var(--error)] text-sm">
					{errorMsg}
				</div>
			{/if}

			{#if successMsg}
				<div class="flex items-center gap-2 px-4 py-3 rounded-lg border border-[var(--success)]/30 bg-[var(--success-subtle)] text-[var(--success)] text-sm">
					<Check size={15} />
					{successMsg}
				</div>
			{/if}
		</div>
	{/snippet}

	{#snippet footer()}
		<button
			onclick={onClose}
			class="px-4 py-2 text-sm font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] bg-[var(--bg-subtle)] hover:bg-[var(--bg-muted)] border border-[var(--border)] rounded-lg transition-all"
		>
			Cancel
		</button>
		<button
			onclick={handleInherit}
			disabled={loading || !!successMsg}
			class="
				inline-flex items-center gap-2 px-4 py-2
				text-sm font-medium
				text-[var(--bg-base)] bg-[var(--accent)] hover:opacity-90
				rounded-lg transition-all active:scale-95
				disabled:opacity-50 disabled:cursor-not-allowed disabled:active:scale-100
			"
		>
			{#if loading}
				<span class="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white"></span>
				Inheriting…
			{:else if successMsg}
				<Check size={15} />
				Inherited
			{:else}
				<Download size={15} />
				Inherit
			{/if}
		</button>
	{/snippet}
</Modal>
