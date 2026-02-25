<script lang="ts">
	import { Cable, Loader2, Wrench, Play, FolderOpen } from 'lucide-svelte';
	import { formatDistanceToNow } from 'date-fns';
	import { API_BASE } from '$lib/config';
	import UsageAnalytics from '$lib/components/charts/UsageAnalytics.svelte';
	import { getServerColorVars } from '$lib/utils/mcp';
	import type { McpToolsOverview, McpServer } from '$lib/api-types';

	interface Props {
		projectEncodedName?: string;
	}

	let { projectEncodedName }: Props = $props();

	let overview = $state<McpToolsOverview | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	$effect(() => {
		fetchTools();
	});

	async function fetchTools() {
		loading = true;
		error = null;
		try {
			const url = new URL(`${API_BASE}/tools`);
			if (projectEncodedName) {
				url.searchParams.set('project', projectEncodedName);
			}
			const res = await fetch(url);
			if (!res.ok) throw new Error('Failed to fetch tools');
			overview = await res.json();
		} catch (e: any) {
			error = e.message;
		} finally {
			loading = false;
		}
	}
</script>

<div class="space-y-6">
	{#if loading}
		<div class="flex items-center justify-center py-20">
			<Loader2 class="animate-spin text-[var(--text-muted)]" size={32} />
		</div>
	{:else if error}
		<div class="p-4 bg-red-500/10 text-red-500 rounded-lg text-sm border border-red-500/20">
			{error}
		</div>
	{:else if !overview?.servers?.length}
		<div
			class="text-center py-20 bg-[var(--bg-subtle)] rounded-2xl border border-dashed border-[var(--border)]"
		>
			<Cable class="mx-auto text-[var(--text-muted)] mb-3" size={48} />
			<p class="text-[var(--text-secondary)] font-medium">No MCP servers found</p>
			<p class="text-sm text-[var(--text-muted)] mt-1">
				MCP tool usage will appear once tools are used in sessions
			</p>
		</div>
	{:else}
		<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
			{#each overview.servers as server (server.name)}
				{@const colorVars = getServerColorVars(server.name, server.plugin_name)}
				<a
					href="/tools/{encodeURIComponent(server.name)}{projectEncodedName
						? `?project=${encodeURIComponent(projectEncodedName)}`
						: ''}"
					class="group block bg-[var(--bg-base)] border border-[var(--border)] rounded-xl p-5 hover:border-[var(--accent)]/50 hover:shadow-lg transition-all duration-300 relative overflow-hidden focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2"
				>
					<div class="flex items-start justify-between mb-4">
						<div
							class="p-2.5 bg-[var(--bg-subtle)] text-[var(--text-secondary)] rounded-lg transition-colors"
							style="--server-color: {colorVars.color}; --server-subtle: {colorVars.subtle};"
							style:background-color="var(--server-subtle)"
							style:color={colorVars.color}
						>
							<Cable size={20} strokeWidth={2} />
						</div>
						{#if server.plugin_name}
							<div
								class="px-2 py-0.5 rounded-full text-[10px] font-medium uppercase tracking-wider"
								style="background: {colorVars.subtle}; color: {colorVars.color};"
							>
								{server.source}
							</div>
						{:else}
							<div
								class="px-2 py-0.5 rounded-full bg-[var(--bg-subtle)] text-[10px] font-medium text-[var(--text-muted)] uppercase tracking-wider"
							>
								{server.source}
							</div>
						{/if}
					</div>

					<h3 class="font-semibold text-[var(--text-primary)] mb-2 truncate pr-4">
						{server.display_name}
					</h3>

					<div class="flex items-center gap-4 text-xs text-[var(--text-muted)]">
						<span class="flex items-center gap-1">
							<Wrench size={12} />
							{server.tool_count}
							{server.tool_count === 1 ? 'tool' : 'tools'}
						</span>
						<span class="flex items-center gap-1">
							<Play size={12} />
							{server.total_calls.toLocaleString()} calls
						</span>
						<span class="flex items-center gap-1">
							<FolderOpen size={12} />
							{server.session_count} sessions
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

	<!-- Tools Usage Trend Chart -->
	<div class="mt-8">
		<UsageAnalytics
			endpoint="/tools/usage/trend"
			{projectEncodedName}
			itemLabel="Tools"
			colorIndex={4}
			itemLinkFn={(name) => {
				const stripped = name.startsWith('mcp__') ? name.slice(5) : name;
				const lastSep = stripped.lastIndexOf('__');
				if (lastSep > 0) {
					const server = stripped.slice(0, lastSep);
					const tool = stripped.slice(lastSep + 2);
					return `/tools/${encodeURIComponent(server)}/${encodeURIComponent(tool)}`;
				}
				return `/tools/${encodeURIComponent(stripped)}`;
			}}
			itemDisplayFn={(name) => {
				const stripped = name.startsWith('mcp__') ? name.slice(5) : name;
				return stripped.replaceAll('__', ' / ').replaceAll('_', ' ');
			}}
		/>
	</div>
</div>
