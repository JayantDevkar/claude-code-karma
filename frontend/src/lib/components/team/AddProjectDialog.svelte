<script lang="ts">
	import Modal from '$lib/components/ui/Modal.svelte';
	import { API_BASE } from '$lib/config';
	import { Loader2, FolderSync } from 'lucide-svelte';

	interface ProjectOption {
		encoded_name: string;
		name: string;
		path?: string;
	}

	let {
		open = $bindable(false),
		teamName,
		allProjects = [],
		sharedProjectNames = [],
		onadded
	}: {
		open?: boolean;
		teamName: string;
		allProjects?: ProjectOption[];
		sharedProjectNames?: string[];
		onadded?: () => void;
	} = $props();

	let selected = $state<Set<string>>(new Set());
	let loading = $state(false);
	let error = $state<string | null>(null);

	let availableProjects = $derived(
		allProjects.filter((p) => !sharedProjectNames.includes(p.encoded_name))
	);

	function toggleProject(encodedName: string) {
		const next = new Set(selected);
		if (next.has(encodedName)) {
			next.delete(encodedName);
		} else {
			next.add(encodedName);
		}
		selected = next;
	}

	async function handleShare() {
		if (selected.size === 0 || loading) return;
		loading = true;
		error = null;

		try {
			const results = await Promise.all(
				[...selected].map(async (encodedName) => {
					const project = allProjects.find((p) => p.encoded_name === encodedName);
					const res = await fetch(
						`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/projects`,
						{
							method: 'POST',
							headers: { 'Content-Type': 'application/json' },
							body: JSON.stringify({
								name: encodedName,
								path: project?.path ?? ''
							})
						}
					);
					return res.ok;
				})
			);

			if (results.every((r) => r)) {
				open = false;
				selected = new Set();
				onadded?.();
			} else {
				error = 'Some projects failed to add';
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Network error';
		} finally {
			loading = false;
		}
	}
</script>

<Modal bind:open title="Share Projects with &quot;{teamName}&quot;">
	{#snippet children()}
		<div class="space-y-4">
			{#if availableProjects.length === 0}
				<p class="text-sm text-[var(--text-muted)] py-4 text-center">
					All projects are already shared with this team.
				</p>
			{:else}
				<p class="text-sm text-[var(--text-secondary)]">Select projects to sync:</p>
				<div class="max-h-64 overflow-y-auto space-y-1 -mx-1 px-1">
					{#each availableProjects as project (project.encoded_name)}
						<button
							onclick={() => toggleProject(project.encoded_name)}
							role="checkbox"
							aria-checked={selected.has(project.encoded_name)}
							class="w-full flex items-center gap-3 p-2.5 rounded-lg text-left hover:bg-[var(--bg-subtle)] transition-colors"
						>
							<div
								class="w-5 h-5 rounded border flex items-center justify-center shrink-0 transition-colors
									{selected.has(project.encoded_name)
									? 'bg-[var(--accent)] border-[var(--accent)] text-white'
									: 'border-[var(--border)]'}"
							>
								{#if selected.has(project.encoded_name)}
									<svg width="12" height="12" viewBox="0 0 12 12" fill="none">
										<path d="M2 6L5 9L10 3" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" />
									</svg>
								{/if}
							</div>
							<div class="flex items-center gap-2 min-w-0">
								<FolderSync size={14} class="text-[var(--text-muted)] shrink-0" />
								<span class="text-sm text-[var(--text-primary)] truncate">{project.name || project.encoded_name}</span>
							</div>
						</button>
					{/each}
				</div>
			{/if}

			{#if sharedProjectNames.length > 0}
				<p class="text-xs text-[var(--text-muted)]">
					Already shared: {sharedProjectNames.join(', ')}
				</p>
			{/if}

			{#if error}
				<p class="text-xs text-[var(--error)]">{error}</p>
			{/if}
		</div>
	{/snippet}

	{#snippet footer()}
		<button
			onclick={() => (open = false)}
			class="px-4 py-2 text-sm font-medium rounded-[var(--radius-md)] text-[var(--text-secondary)]
				hover:bg-[var(--bg-muted)] transition-colors"
		>
			Cancel
		</button>
		<button
			onclick={handleShare}
			disabled={selected.size === 0 || loading}
			class="px-4 py-2 text-sm font-medium rounded-[var(--radius-md)] bg-[var(--accent)] text-white
				hover:bg-[var(--accent-hover)] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
		>
			{#if loading}
				<span class="flex items-center gap-2">
					<Loader2 size={14} class="animate-spin" />
					Sharing...
				</span>
			{:else}
				Share {selected.size > 0 ? `${selected.size} Selected` : 'Selected'}
			{/if}
		</button>
	{/snippet}
</Modal>
