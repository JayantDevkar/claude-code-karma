<script lang="ts">
	import { navigating } from '$app/stores';
	import { Puzzle, Clock, Package, FolderOpen } from 'lucide-svelte';
	import { formatDistanceToNow } from 'date-fns';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import PluginCapabilities from '$lib/components/plugins/PluginCapabilities.svelte';
	import PluginUsageStats from '$lib/components/plugins/PluginUsageStats.svelte';
	import SkeletonBox from '$lib/components/skeleton/SkeletonBox.svelte';
	import SkeletonText from '$lib/components/skeleton/SkeletonText.svelte';
	import { getPluginColorVars } from '$lib/utils';
	import { API_BASE } from '$lib/config';
	import type { PluginUsageStats as PluginUsageStatsType } from '$lib/api-types';

	let { data } = $props();

	// Check if navigating to a different plugin
	let isLoading = $derived(
		!!$navigating && $navigating.to?.route.id === '/plugins/[plugin_name]'
	);

	let plugin = $derived(data.plugin);

	// Progressively load usage data from separate endpoint
	let usageData = $state<PluginUsageStatsType | null>(null);
	let usageLoading = $state(true);

	$effect(() => {
		if (plugin && typeof window !== 'undefined') {
			usageLoading = true;
			usageData = null;
			fetch(`${API_BASE}/plugins/${encodeURIComponent(plugin.name)}/usage?period=all`)
				.then((r) => {
					if (r.ok) return r.json();
					return null;
				})
				.then((d: PluginUsageStatsType | null) => {
					usageData = d;
					usageLoading = false;
				})
				.catch(() => {
					usageLoading = false;
				});
		}
	});
	let colorVars = $derived(
		plugin
			? getPluginColorVars(plugin.name)
			: { color: 'var(--accent)', subtle: 'var(--accent-subtle)' }
	);

	// Format last update
	let lastUpdated = $derived.by(() => {
		if (!plugin || !plugin.installations.length) return 'Never';
		const latest = plugin.installations.reduce((a, b) =>
			new Date(a.last_updated) > new Date(b.last_updated) ? a : b
		);
		return formatDistanceToNow(new Date(latest.last_updated)) + ' ago';
	});

	// Get latest version
	let latestVersion = $derived.by(() => {
		if (!plugin || !plugin.installations.length) return 'Unknown';
		const latest = plugin.installations.reduce((a, b) =>
			new Date(a.last_updated) > new Date(b.last_updated) ? a : b
		);
		return latest.version.substring(0, 7);
	});

	// Get scopes
	let scopes = $derived.by(() => {
		if (!plugin) return [];
		return [...new Set(plugin.installations.map((i) => i.scope))];
	});
</script>

{#if isLoading}
	<!-- Loading Skeleton -->
	<div class="space-y-8">
		<!-- Page Header Skeleton -->
		<div>
			<!-- Breadcrumb -->
			<div class="flex items-center gap-2 text-xs text-[var(--text-secondary)] mb-4">
				<SkeletonText width="70px" size="xs" />
				<span class="text-[var(--text-faint)]">/</span>
				<SkeletonText width="50px" size="xs" />
				<span class="text-[var(--text-faint)]">/</span>
				<SkeletonText width="120px" size="xs" />
			</div>
			<!-- Title with icon and meta -->
			<div class="flex items-start gap-4 mb-6 pb-6 border-b border-[var(--border)]">
				<SkeletonBox width="48px" height="48px" rounded="lg" />
				<div class="flex-1">
					<SkeletonText width="200px" size="xl" class="mb-2" />
					<SkeletonText width="300px" size="sm" class="mb-3" />
					<div class="flex items-center gap-3">
						<SkeletonText width="60px" size="xs" />
						<SkeletonText width="80px" size="xs" />
						<SkeletonText width="50px" size="xs" />
					</div>
				</div>
			</div>
		</div>

		<!-- Capabilities Section Skeleton -->
		<div class="bg-[var(--bg-base)] border border-[var(--border)] rounded-2xl p-6">
			<SkeletonText width="120px" size="sm" class="mb-4" />
			<div class="space-y-3">
				{#each Array(3) as _}
					<SkeletonText lines={2} size="sm" />
				{/each}
			</div>
		</div>

		<!-- Usage Stats Section Skeleton -->
		<div class="bg-[var(--bg-base)] border border-[var(--border)] rounded-2xl p-6">
			<SkeletonText width="100px" size="sm" class="mb-4" />
			<div class="grid grid-cols-2 md:grid-cols-4 gap-4">
				{#each Array(4) as _}
					<SkeletonBox height="80px" rounded="lg" />
				{/each}
			</div>
		</div>
	</div>
{:else}
	<div class="space-y-8">
		<!-- Page Header with integrated meta -->
		<PageHeader
			title={plugin.name.split('@')[0]}
			icon={Puzzle}
			iconColorRaw={colorVars}
			breadcrumbs={[
				{ label: 'Dashboard', href: '/' },
				{ label: 'Plugins', href: '/plugins' },
				{ label: plugin.name.split('@')[0] }
			]}
			subtitle={plugin.description || 'Claude Code plugin'}
			metadata={[
				{ icon: Package, text: `v${latestVersion}` },
				{ icon: Clock, text: lastUpdated },
				...scopes.map((s) => ({ icon: FolderOpen, text: s }))
			]}
		/>

		<!-- Capabilities Section -->
		{#if plugin.capabilities}
			<div class="bg-[var(--bg-base)] border border-[var(--border)] rounded-2xl p-6">
				<PluginCapabilities
					capabilities={plugin.capabilities}
					pluginName={plugin.name}
					pluginColor={colorVars.color}
					pluginColorSubtle={colorVars.subtle}
				/>
			</div>
		{/if}

		<!-- Usage Stats Section -->
		<div class="bg-[var(--bg-base)] border border-[var(--border)] rounded-2xl p-6">
			{#if usageLoading}
				<h3 class="text-sm font-semibold text-[var(--text-primary)] mb-4">
					Usage Analytics
				</h3>
				<div class="grid grid-cols-2 md:grid-cols-4 gap-4">
					{#each Array(4) as _}
						<SkeletonBox height="80px" rounded="lg" />
					{/each}
				</div>
			{:else}
				<PluginUsageStats
					usage={usageData || {
						plugin_name: plugin.name,
						total_agent_runs: 0,
						total_skill_invocations: 0,
						total_mcp_tool_calls: 0,
						estimated_cost_usd: 0,
						by_agent: {},
						by_skill: {},
						by_mcp_tool: {},
						by_agent_daily: {},
						by_skill_daily: {},
						by_mcp_tool_daily: {},
						trend: [],
						first_used: null,
						last_used: null
					}}
					pluginName={plugin.name}
					mcpServers={plugin.capabilities?.mcp_tools ?? []}
				/>
			{/if}
		</div>

		<!-- Installations Section -->
		{#if plugin.installations.length > 0}
			<div class="bg-[var(--bg-base)] border border-[var(--border)] rounded-2xl p-6">
				<h3 class="text-sm font-semibold text-[var(--text-primary)] mb-4">Installations</h3>
				<div class="space-y-3">
					{#each plugin.installations as installation}
						<div
							class="flex items-center justify-between p-4 bg-[var(--bg-subtle)] rounded-xl"
						>
							<div class="flex items-center gap-4 min-w-0 flex-1">
								<span
									class="px-2 py-1 text-xs font-medium bg-[var(--bg-base)] rounded capitalize flex-shrink-0"
								>
									{installation.scope}
								</span>
								<span
									class="text-sm text-[var(--text-secondary)] font-mono break-all"
									title={installation.install_path}
								>
									{installation.install_path}
								</span>
							</div>
							<div class="text-xs text-[var(--text-muted)] flex-shrink-0 ml-4">
								v{installation.version.substring(0, 7)}
							</div>
						</div>
					{/each}
				</div>
			</div>
		{/if}
	</div>
{/if}
