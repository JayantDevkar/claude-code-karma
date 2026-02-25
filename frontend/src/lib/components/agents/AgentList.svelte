<script lang="ts">
	import { Bot, Loader2, Plus, X, Clock, HardDrive } from 'lucide-svelte';
	import { goto } from '$app/navigation';
	import { formatDistanceToNow } from 'date-fns';
	import { Dialog } from 'bits-ui';
	import { listNavigation } from '$lib/actions/listNavigation';
	import { API_BASE } from '$lib/config';
	import UsageAnalytics from '$lib/components/charts/UsageAnalytics.svelte';

	interface AgentSummary {
		name: string;
		size_bytes: number;
		modified_at: string;
	}

	interface Props {
		projectEncodedName?: string;
	}

	let { projectEncodedName }: Props = $props();

	let agents = $state<AgentSummary[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	// Modal state
	let showModal = $state(false);
	let newAgentName = $state('');

	$effect(() => {
		fetchAgents();
	});

	async function fetchAgents() {
		loading = true;
		error = null;
		try {
			const url = new URL(`${API_BASE}/agents`);
			if (projectEncodedName) {
				url.searchParams.set('project', projectEncodedName);
			}
			const res = await fetch(url);

			// Handle 404 gracefully - agents directory doesn't exist for this project
			if (res.status === 404) {
				agents = [];
				return;
			}

			if (!res.ok) throw new Error('Failed to fetch agents');
			agents = await res.json();
		} catch (e: any) {
			error = e.message;
		} finally {
			loading = false;
		}
	}

	function createAgent() {
		if (!newAgentName.trim()) return;
		const formattedName = newAgentName.trim().toLowerCase().replace(/\s+/g, '-');
		if (projectEncodedName) {
			goto(`/agents/${formattedName}?project=${encodeURIComponent(projectEncodedName)}`);
		} else {
			goto(`/agents/${formattedName}`);
		}
	}

	function formatSize(bytes: number): string {
		if (bytes === 0) return '0 B';
		const k = 1024;
		const sizes = ['B', 'KB', 'MB', 'GB'];
		const i = Math.floor(Math.log(bytes) / Math.log(k));
		return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
	}

	function getAgentHref(name: string): string {
		if (projectEncodedName) {
			return `/agents/${name}?project=${encodeURIComponent(projectEncodedName)}`;
		}
		return `/agents/${name}`;
	}
</script>

<!-- New Agent Modal with bits-ui Dialog for accessibility -->
<Dialog.Root bind:open={showModal}>
	<Dialog.Portal>
		<Dialog.Overlay class="fixed inset-0 bg-black/50 z-50" />
		<Dialog.Content
			class="fixed left-[50%] top-[50%] z-50 translate-x-[-50%] translate-y-[-50%] bg-[var(--bg-base)] rounded-xl shadow-xl max-w-md w-full p-6 border border-[var(--border)] focus:outline-none"
			style="box-shadow: var(--shadow-elevated);"
			onOpenAutoFocus={(e) => {
				e.preventDefault();
				document.getElementById('agent-name')?.focus();
			}}
		>
			<div class="flex items-center justify-between mb-4">
				<Dialog.Title class="text-lg font-semibold text-[var(--text-primary)]">
					Create New Agent
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
						for="agent-name"
						class="block text-sm font-medium text-[var(--text-secondary)] mb-1"
					>
						Agent Name
					</label>
					<input
						id="agent-name"
						type="text"
						bind:value={newAgentName}
						placeholder="e.g. documentation-helper"
						class="w-full px-3 py-2 border border-[var(--border)] rounded-lg focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/20 focus:border-[var(--accent)] transition-all font-mono text-sm bg-[var(--bg-base)] text-[var(--text-primary)]"
						onkeydown={(e) => e.key === 'Enter' && createAgent()}
						aria-describedby="agent-name-hint"
					/>
					<p id="agent-name-hint" class="text-xs text-[var(--text-muted)] mt-1">
						Will be created as <span class="font-mono text-[var(--text-secondary)]"
							>{newAgentName.trim().toLowerCase().replace(/\s+/g, '-') || '...'}</span
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
						onclick={createAgent}
						disabled={!newAgentName.trim()}
						class="px-4 py-2 bg-[var(--accent)] text-white font-medium rounded-lg hover:bg-[var(--accent-hover)] disabled:opacity-50 disabled:cursor-not-allowed transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2"
					>
						Create Agent
					</button>
				</div>
			</div>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>

<div class="space-y-6" use:listNavigation>
	{#if loading}
		<div class="flex items-center justify-center py-20">
			<Loader2 class="animate-spin text-[var(--text-muted)]" size={32} />
		</div>
	{:else if error}
		<div class="p-4 bg-red-500/10 text-red-500 rounded-lg text-sm border border-red-500/20">
			{error}
		</div>
	{:else if agents.length === 0}
		<div
			class="text-center py-20 bg-[var(--bg-subtle)] rounded-2xl border border-dashed border-[var(--border)]"
		>
			<Bot class="mx-auto text-[var(--text-muted)] mb-3" size={48} />
			<p class="text-[var(--text-secondary)] font-medium">No agents found</p>
			<p class="text-sm text-[var(--text-muted)] mt-1">
				{projectEncodedName
					? 'Add agents to this project'
					: 'Add some agents to your .claude directory'}
			</p>
		</div>
	{:else}
		<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
			{#each agents as agent}
				<a
					href={getAgentHref(agent.name)}
					class="group block bg-[var(--bg-base)] border border-[var(--border)] rounded-xl p-5 hover:border-[var(--accent)]/50 hover:shadow-lg transition-all duration-300 relative overflow-hidden focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2"
					data-list-item
				>
					<div class="flex items-start justify-between mb-4">
						<div
							class="p-2.5 bg-[var(--bg-subtle)] text-[var(--text-secondary)] rounded-lg group-hover:bg-[var(--accent)]/10 group-hover:text-[var(--accent)] transition-colors"
						>
							<Bot size={20} strokeWidth={2} />
						</div>
						<div
							class="px-2 py-0.5 rounded-full bg-[var(--bg-subtle)] text-[10px] font-medium text-[var(--text-muted)] uppercase tracking-wider"
						>
							Markdown
						</div>
					</div>

					<h3 class="font-semibold text-[var(--text-primary)] mb-4 truncate pr-4">
						{agent.name}
					</h3>

					<div class="flex items-center gap-4 text-xs text-[var(--text-muted)]">
						<span class="flex items-center gap-1">
							<HardDrive size={12} />
							{formatSize(agent.size_bytes)}
						</span>
						<span class="flex items-center gap-1">
							<Clock size={12} />
							{formatDistanceToNow(new Date(agent.modified_at))} ago
						</span>
					</div>

					<div
						class="absolute bottom-5 right-5 opacity-0 -translate-x-2 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-300"
					>
						<svg
							width="20"
							height="20"
							viewBox="0 0 24 24"
							fill="none"
							stroke="currentColor"
							stroke-width="2"
							stroke-linecap="round"
							stroke-linejoin="round"
							class="text-[var(--accent)]"
						>
							<path d="M5 12h14" />
							<path d="m12 5 7 7-7 7" />
						</svg>
					</div>
				</a>
			{/each}
		</div>
	{/if}

	<!-- Agent Usage Trend Chart -->
	<div class="mt-8">
		<UsageAnalytics
			endpoint="/agents/usage/trend"
			{projectEncodedName}
			itemLabel="Agents"
			colorIndex={0}
			itemLinkPrefix="/agents/"
		/>
	</div>
</div>
