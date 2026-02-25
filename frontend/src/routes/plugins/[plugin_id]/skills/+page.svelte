<script lang="ts">
	import { Wrench, FileText, Clock, Package, AlertCircle, Folder } from 'lucide-svelte';
	import { formatDistanceToNow } from 'date-fns';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import Card from '$lib/components/ui/Card.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import type { Breadcrumb } from '$lib/api-types';

	let { data } = $props();

	// Format plugin name for display (remove @marketplace suffix)
	function formatPluginName(name: string): string {
		return name.replace(/@marketplace$/, '');
	}

	// Build breadcrumbs
	let breadcrumbs = $derived.by((): Breadcrumb[] => {
		const crumbs: Breadcrumb[] = [
			{ label: 'Dashboard', href: '/' },
			{ label: 'Plugins', href: '/plugins' }
		];

		if (data.plugin) {
			const pluginName = formatPluginName(data.plugin.name);
			crumbs.push(
				{ label: pluginName, href: `/plugins/${encodeURIComponent(data.plugin.name)}` },
				{ label: 'Skills' }
			);
		}

		return crumbs;
	});

	// Format file size
	function formatSize(bytes: number | undefined): string {
		if (bytes === undefined) return '';
		if (bytes === 0) return '0 B';
		const k = 1024;
		const sizes = ['B', 'KB', 'MB', 'GB'];
		const i = Math.floor(Math.log(bytes) / Math.log(k));
		return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
	}

	// Determine page title
	let pageTitle = $derived(
		data.plugin ? `${formatPluginName(data.plugin.name)} Skills` : 'Plugin Skills'
	);
</script>

<div class="space-y-6">
	<!-- Page Header with Breadcrumb -->
	<PageHeader
		title={pageTitle}
		icon={Wrench}
		{breadcrumbs}
		subtitle={data.plugin
			? `Browse skills provided by ${formatPluginName(data.plugin.name)}`
			: ''}
	/>

	<!-- Error State -->
	{#if data.error}
		<div
			class="text-center py-20 bg-[var(--bg-subtle)] rounded-2xl border border-dashed border-red-500/20"
		>
			<AlertCircle class="mx-auto text-red-500 mb-3" size={48} />
			<p class="text-[var(--text-secondary)] font-medium">{data.error}</p>
			<p class="text-sm text-[var(--text-muted)] mt-1">
				The plugin may not exist or could not be loaded
			</p>
		</div>
	{:else if data.skills.length === 0}
		<!-- Empty State: No skills -->
		<div
			class="text-center py-20 bg-[var(--bg-subtle)] rounded-2xl border border-dashed border-[var(--border)]"
		>
			<Folder class="mx-auto text-[var(--text-muted)] mb-3" size={48} />
			<p class="text-[var(--text-secondary)] font-medium">No skills found</p>
			<p class="text-sm text-[var(--text-muted)] mt-1">
				This plugin does not have any skills available
			</p>
		</div>
	{:else}
		<!-- Skills Grid -->
		<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5 stagger-children">
			{#each data.skills as skill}
				<a
					href="/plugins/{encodeURIComponent(data.plugin_id)}/skills/{skill.path}"
					class="block group"
				>
					<Card
						variant="default"
						padding="md"
						class="h-full transition-all hover:border-[var(--accent)]/50 hover:shadow-md"
					>
						<div class="flex flex-col h-full gap-3">
							<!-- Header -->
							<div class="flex items-start gap-3">
								<div
									class="p-2 rounded-lg bg-[var(--bg-subtle)] text-[var(--text-muted)] group-hover:bg-[var(--accent)]/10 group-hover:text-[var(--accent)] transition-colors"
								>
									<FileText size={18} />
								</div>
								<div class="flex-1 min-w-0">
									<h3
										class="font-semibold text-[var(--text-primary)] truncate group-hover:text-[var(--accent)] transition-colors"
									>
										{skill.name}
									</h3>
									<p class="text-xs text-[var(--text-muted)] font-mono truncate">
										{skill.path}
									</p>
								</div>
							</div>

							<!-- Metadata -->
							<div
								class="flex flex-wrap items-center gap-2 pt-2 border-t border-[var(--border)] text-xs text-[var(--text-muted)]"
							>
								{#if skill.size_bytes !== undefined}
									<div class="flex items-center gap-1">
										<FileText size={12} />
										<span>{formatSize(skill.size_bytes)}</span>
									</div>
								{/if}
								{#if skill.modified_at}
									<div class="flex items-center gap-1">
										<Clock size={12} />
										<span
											>{formatDistanceToNow(new Date(skill.modified_at))} ago</span
										>
									</div>
								{/if}
							</div>
						</div>
					</Card>
				</a>
			{/each}
		</div>
	{/if}
</div>
