<script lang="ts">
	import { Folder, FileText, ChevronRight, Loader2, ArrowLeft, Plus, X } from 'lucide-svelte';
	import { goto } from '$app/navigation';
	import { formatDistanceToNow } from 'date-fns';
	import { Dialog } from 'bits-ui';
	import { listNavigation } from '$lib/actions/listNavigation';
	import { API_BASE } from '$lib/config';
	import UsageAnalytics from '$lib/components/charts/UsageAnalytics.svelte';
	import { getSkillChartHex } from '$lib/utils';

	interface SkillItem {
		name: string;
		path: string;
		type: 'file' | 'directory';
		size_bytes?: number;
		modified_at?: string;
	}

	interface Props {
		projectEncodedName?: string;
		currentPath?: string;
	}

	let { projectEncodedName, currentPath = '' }: Props = $props();

	// When embedded in project tab, we manage path locally (no URL changes).
	// When on the global /skills page, currentPath is driven by the URL prop.
	let internalPath = $state(currentPath);

	// Keep in sync with prop for global-skills-page usage (currentPath changes via URL)
	$effect(() => {
		if (!projectEncodedName) internalPath = currentPath;
	});

	let items = $state<SkillItem[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);

	// Modal state
	let showModal = $state(false);
	let newSkillName = $state('');

	$effect(() => {
		fetchSkills(internalPath);
	});

	async function fetchSkills(path: string) {
		loading = true;
		error = null;
		try {
			const url = new URL(`${API_BASE}/skills`);
			if (path) url.searchParams.set('path', path);
			if (projectEncodedName) url.searchParams.set('project', projectEncodedName);

			const res = await fetch(url);

			// Handle 404 gracefully - skills directory doesn't exist for this project
			if (res.status === 404) {
				items = [];
				return;
			}

			if (!res.ok) throw new Error('Failed to fetch skills');
			items = await res.json();
		} catch (e: any) {
			error = e.message;
		} finally {
			loading = false;
		}
	}

	function createSkill() {
		if (!newSkillName.trim()) return;

		let fullPath = internalPath ? `${internalPath}/${newSkillName}` : newSkillName;

		if (!fullPath.endsWith('.md') && !fullPath.endsWith('.txt')) {
			fullPath += '.md';
		}

		if (projectEncodedName) {
			goto(`/skills/${fullPath}?project=${encodeURIComponent(projectEncodedName)}`);
		} else {
			goto(`/skills/${fullPath}`);
		}
	}

	function formatSize(bytes: number | undefined): string {
		if (bytes === undefined) return '';
		if (bytes === 0) return '0 B';
		const k = 1024;
		const sizes = ['B', 'KB', 'MB', 'GB'];
		const i = Math.floor(Math.log(bytes) / Math.log(k));
		return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
	}

	function getSkillHref(item: SkillItem): string {
		const projectParam = projectEncodedName
			? `project=${encodeURIComponent(projectEncodedName)}`
			: '';
		if (item.type === 'directory') {
			// In project context, directories are handled via local state (onclick).
			// For global /skills page, build a real URL.
			if (projectEncodedName) return '#';
			return `/skills?path=${item.path}`;
		}
		const base = `/skills/${item.path}`;
		return projectParam ? `${base}?${projectParam}` : base;
	}

	function getBackHref(): string {
		const parentPath = internalPath.includes('/')
			? internalPath.split('/').slice(0, -1).join('/')
			: '';
		const projectParam = projectEncodedName
			? `project=${encodeURIComponent(projectEncodedName)}`
			: '';
		if (parentPath) {
			const base = `/skills?path=${parentPath}`;
			return projectParam ? `${base}&${projectParam}` : base;
		}
		return projectParam ? `/skills?${projectParam}` : '/skills';
	}
</script>

<!-- New Skill Modal with bits-ui Dialog for accessibility -->
<Dialog.Root bind:open={showModal}>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 bg-black/50 z-50" />
		<Dialog.Content
			class="fixed left-[50%] top-[50%] z-50 translate-x-[-50%] translate-y-[-50%] bg-[var(--bg-base)] rounded-xl shadow-xl max-w-md w-full p-6 border border-[var(--border)] focus:outline-none"
			style="box-shadow: var(--shadow-elevated);"
			onOpenAutoFocus={(e) => {
				e.preventDefault();
				document.getElementById('skill-name')?.focus();
			}}
		>
			<div class="flex items-center justify-between mb-4">
				<Dialog.Title class="text-lg font-semibold text-[var(--text-primary)]">
					Create New Skill
				</Dialog.Title>
				<Dialog.Close
					class="text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] rounded-md p-1"
					aria-label="Close dialog"
				>
					<X size={20} />
				</Dialog.Close>
			</div>

			<div class="space-y-4">
				<div>
					<label
						for="skill-name"
						class="block text-sm font-medium text-[var(--text-secondary)] mb-1"
					>
						File Name
					</label>
					<input
						id="skill-name"
						type="text"
						bind:value={newSkillName}
						placeholder="e.g. text-processing"
						class="w-full px-3 py-2 border border-[var(--border)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/20 focus:border-[var(--accent)] transition-all font-mono text-sm bg-[var(--bg-base)] text-[var(--text-primary)]"
						onkeydown={(e) => e.key === 'Enter' && createSkill()}
						aria-describedby="skill-name-hint"
					/>
					<p id="skill-name-hint" class="text-xs text-[var(--text-muted)] mt-1">
						Will be created in <span class="font-mono text-[var(--text-secondary)]"
							>/{internalPath}</span
						>
					</p>
				</div>

				<div class="flex justify-end gap-3 pt-2">
					<Dialog.Close
						class="px-4 py-2 text-[var(--text-secondary)] font-medium hover:bg-[var(--bg-subtle)] rounded-lg transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)]"
					>
						Cancel
					</Dialog.Close>
					<button
						onclick={createSkill}
						disabled={!newSkillName.trim()}
						class="px-4 py-2 bg-[var(--accent)] text-white font-medium rounded-lg hover:bg-[var(--accent-hover)] disabled:opacity-50 disabled:cursor-not-allowed transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2"
					>
						Create File
					</button>
				</div>
			</div>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>

<div class="space-y-6" use:listNavigation>
	<div class="flex items-center justify-between gap-4">
		{#if internalPath}
			<a
				href={getBackHref()}
				onclick={(e) => {
					if (projectEncodedName) {
						e.preventDefault();
						internalPath = internalPath.includes('/')
							? internalPath.split('/').slice(0, -1).join('/')
							: '';
					}
				}}
				class="p-2 hover:bg-[var(--bg-subtle)] rounded-lg text-[var(--text-muted)] transition-colors"
				aria-label="Go back to parent folder"
			>
				<ArrowLeft size={20} />
			</a>
		{/if}

		<!-- Temporarily suspended: New Skill creation -->
		<!-- <button
			onclick={() => { newSkillName = ''; showModal = true; }}
			class="flex items-center gap-2 px-3 py-1.5 bg-[var(--accent)] text-white font-medium rounded-lg hover:bg-[var(--accent-hover)] transition-all active:scale-95 text-sm focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2"
		>
			<Plus size={16} />
			New Skill
		</button> -->
	</div>

	{#if loading}
		<div class="flex items-center justify-center py-20">
			<Loader2 class="animate-spin text-[var(--text-muted)]" size={32} />
		</div>
	{:else if error}
		<div class="p-4 bg-red-500/10 text-red-500 rounded-lg text-sm border border-red-500/20">
			{error}
		</div>
	{:else if items.length === 0}
		<div
			class="text-center py-20 bg-[var(--bg-subtle)] rounded-2xl border border-dashed border-[var(--border)]"
		>
			<Folder class="mx-auto text-[var(--text-muted)] mb-3" size={48} />
			<p class="text-[var(--text-secondary)] font-medium">Empty directory</p>
		</div>
	{:else}
		<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
			{#each items as item}
				{#if item.type === 'directory'}
					<a
						href={getSkillHref(item)}
						onclick={(e) => {
							if (projectEncodedName) {
								e.preventDefault();
								internalPath = item.path;
							}
						}}
						class="group flex items-center gap-4 p-4 bg-[var(--bg-base)] border border-[var(--border)] rounded-xl hover:border-[var(--accent)]/50 hover:shadow-sm transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2"
						data-list-item
					>
						<div
							class="p-2.5 bg-blue-500/10 text-blue-500 rounded-lg group-hover:bg-blue-500/20 transition-colors"
						>
							<Folder size={20} />
						</div>
						<div class="min-w-0">
							<div class="font-medium text-[var(--text-primary)] truncate">
								{item.name}
							</div>
							<div class="text-xs text-[var(--text-muted)]">Folder</div>
						</div>
						<ChevronRight
							size={16}
							class="ml-auto text-[var(--text-faint)] group-hover:text-blue-500 transition-colors"
						/>
					</a>
				{:else}
					<a
						href={getSkillHref(item)}
						class="group flex items-center gap-4 p-4 bg-[var(--bg-base)] border border-[var(--border)] rounded-xl hover:border-[var(--accent)]/50 hover:shadow-sm transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2"
						data-list-item
					>
						<div
							class="p-2.5 bg-[var(--bg-subtle)] text-[var(--text-muted)] rounded-lg group-hover:bg-[var(--bg-muted)] transition-colors"
						>
							<FileText size={20} />
						</div>
						<div class="min-w-0 flex-1">
							<div class="font-medium text-[var(--text-primary)] truncate">
								{item.name}
							</div>
							<div
								class="flex items-center gap-2 text-xs text-[var(--text-muted)] mt-0.5"
							>
								<span>File</span>
								{#if item.size_bytes !== undefined}
									<span>•</span>
									<span>{formatSize(item.size_bytes)}</span>
								{/if}
							</div>
						</div>
						{#if item.modified_at}
							<div class="text-xs text-[var(--text-faint)] whitespace-nowrap">
								{formatDistanceToNow(new Date(item.modified_at))} ago
							</div>
						{/if}
					</a>
				{/if}
			{/each}
		</div>
	{/if}

	<!-- Skill Usage Trend Chart (only at root level) -->
	{#if !internalPath}
		<div class="mt-8">
			<UsageAnalytics
				endpoint="/skills/usage/trend"
				{projectEncodedName}
				itemLabel="Skills"
				colorFn={getSkillChartHex}
				itemLinkFn={(name) =>
					projectEncodedName
						? `/skills/${name}?project=${encodeURIComponent(projectEncodedName)}`
						: `/skills/${name}`}
			/>
		</div>
	{/if}
</div>
