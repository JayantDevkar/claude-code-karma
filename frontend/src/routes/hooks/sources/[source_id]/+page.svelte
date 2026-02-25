<script lang="ts">
	import {
		FolderOpen,
		Puzzle,
		Code,
		FileCode,
		Link as LinkIcon,
		ExternalLink
	} from 'lucide-svelte';
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import Badge from '$lib/components/ui/Badge.svelte';
	import { getHookSourceColorVars } from '$lib/utils';

	let { data } = $props();

	// All 13 hook event types for coverage matrix
	const ALL_EVENT_TYPES = [
		'SessionStart',
		'UserPromptSubmit',
		'PreToolUse',
		'PostToolUse',
		'PostToolUseFailure',
		'SubagentStart',
		'SubagentStop',
		'Stop',
		'PreCompact',
		'PermissionRequest',
		'Notification',
		'SessionEnd',
		'Setup'
	];

	// Color vars based on source type
	let colorVars = $derived(
		getHookSourceColorVars(data.detail.source.source_type, data.detail.source.source_name)
	);

	// Icon based on source type
	let sourceIcon = $derived(
		data.detail.source.source_type === 'plugin'
			? Puzzle
			: data.detail.source.source_type === 'project'
				? Code
				: FolderOpen
	);

	// Get event type color (use hook source color for covered events, muted for uncovered)
	function getEventColor(eventType: string): string {
		return data.detail.coverage_matrix[eventType] ? colorVars.color : 'var(--text-faint)';
	}

	function getEventBg(eventType: string): string {
		return data.detail.coverage_matrix[eventType] ? colorVars.subtle : 'var(--bg-muted)';
	}
</script>

<div class="space-y-8">
	<!-- Plugin Banner (if applicable) -->
	{#if data.detail.source.source_type === 'plugin' && data.detail.source.plugin_id}
		<a
			href="/plugins/{encodeURIComponent(data.detail.source.plugin_id)}"
			class="flex items-center gap-3 px-5 py-4 bg-gradient-to-r from-[{colorVars.subtle}] to-transparent rounded-xl border border-[var(--border)] hover:border-[{colorVars.color}] transition-all group"
		>
			<Puzzle size={20} style="color: {colorVars.color};" />
			<div class="flex-1">
				<p class="text-sm font-semibold text-[var(--text-primary)]">
					This source is the <span style="color: {colorVars.color};"
						>{data.detail.source.plugin_id}</span
					> plugin
				</p>
				<p class="text-xs text-[var(--text-muted)]">
					View plugin details and full capabilities
				</p>
			</div>
			<ExternalLink
				size={16}
				class="text-[var(--text-muted)] group-hover:text-[var(--text-primary)] transition-colors"
			/>
		</a>
	{/if}

	<!-- Page Header -->
	<PageHeader
		title={data.detail.source.source_name}
		icon={sourceIcon}
		iconColorRaw={colorVars}
		breadcrumbs={[
			{ label: 'Dashboard', href: '/' },
			{ label: 'Hooks', href: '/hooks' },
			{ label: data.detail.source.source_name }
		]}
	>
		{#snippet badges()}
			<Badge variant="accent">
				{data.detail.source.total_registrations} registration{data.detail.source
					.total_registrations !== 1
					? 's'
					: ''}
			</Badge>
			<Badge variant="slate">
				{data.detail.scripts.length} script{data.detail.scripts.length !== 1 ? 's' : ''}
			</Badge>
		{/snippet}
	</PageHeader>

	<!-- Event Coverage Matrix -->
	<div class="bg-[var(--bg-base)] border border-[var(--border)] rounded-xl p-6 shadow-sm">
		<h2 class="text-lg font-bold text-[var(--text-primary)] mb-6">Event Coverage</h2>

		<div class="flex flex-wrap gap-4">
			{#each ALL_EVENT_TYPES as eventType}
				<a
					href="/hooks/{eventType}"
					class="flex flex-col items-center gap-2 group transition-transform hover:scale-105"
				>
					<!-- Dot/Circle -->
					<div
						class="w-12 h-12 rounded-full border-2 flex items-center justify-center transition-all {data
							.detail.coverage_matrix[eventType]
							? 'shadow-md hover:shadow-lg'
							: 'border-dashed'}"
						style="background-color: {getEventBg(
							eventType
						)}; border-color: {getEventColor(eventType)};"
					>
						{#if data.detail.coverage_matrix[eventType]}
							<div
								class="w-3 h-3 rounded-full"
								style="background-color: {colorVars.color};"
							></div>
						{/if}
					</div>
					<!-- Label -->
					<span
						class="text-xs font-medium text-center max-w-[80px] leading-tight group-hover:text-[var(--text-primary)] transition-colors"
						style="color: {getEventColor(eventType)};"
					>
						{eventType}
					</span>
				</a>
			{/each}
		</div>

		<!-- Coverage Summary -->
		<div class="mt-6 pt-6 border-t border-[var(--border)] flex items-center gap-6 text-sm">
			<div class="flex items-center gap-2">
				<div
					class="w-3 h-3 rounded-full"
					style="background-color: {colorVars.color};"
				></div>
				<span class="text-[var(--text-secondary)]">
					{data.detail.source.event_types_covered.length} of {ALL_EVENT_TYPES.length} events
					covered
				</span>
			</div>
			{#if data.detail.source.blocking_hooks_count > 0}
				<div class="flex items-center gap-2">
					<span class="text-[var(--text-muted)]">•</span>
					<span class="text-[var(--text-secondary)]">
						{data.detail.source.blocking_hooks_count} blocking hook{data.detail.source
							.blocking_hooks_count !== 1
							? 's'
							: ''}
					</span>
				</div>
			{/if}
		</div>
	</div>

	<!-- Scripts Section -->
	<div>
		<h2 class="text-lg font-bold text-[var(--text-primary)] mb-4">
			Scripts ({data.detail.scripts.length})
		</h2>

		{#if data.detail.scripts.length === 0}
			<div
				class="text-center py-12 bg-[var(--bg-subtle)] rounded-xl border border-dashed border-[var(--border)]"
			>
				<FileCode class="mx-auto text-[var(--text-muted)] mb-3" size={36} />
				<p class="text-sm text-[var(--text-muted)]">No scripts found</p>
			</div>
		{:else}
			<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
				{#each data.detail.scripts as script}
					<div
						class="bg-[var(--bg-base)] border border-[var(--border)] rounded-xl p-5 shadow-sm hover:shadow-md transition-all border-l-4"
						style="border-left-color: {colorVars.color};"
					>
						<!-- Filename -->
						<div class="flex items-start gap-3 mb-3">
							<FileCode
								size={18}
								style="color: {colorVars.color};"
								class="flex-shrink-0 mt-0.5"
							/>
							<div class="flex-1 min-w-0">
								<h3
									class="text-sm font-bold text-[var(--text-primary)] truncate"
									title={script.filename}
								>
									{script.filename}
								</h3>
								{#if script.full_path}
									<p
										class="text-xs text-[var(--text-muted)] truncate mt-0.5"
										title={script.full_path}
									>
										{script.full_path}
									</p>
								{/if}
							</div>
						</div>

						<!-- Language Badge -->
						<div class="mb-3">
							<Badge variant="slate" class="text-xs">
								{script.language}
							</Badge>
						</div>

						<!-- Event Types -->
						<div class="mb-3">
							<p class="text-xs text-[var(--text-muted)] mb-2">Event Types:</p>
							<div class="flex flex-wrap gap-1.5">
								{#each script.event_types as eventType}
									<a
										href="/hooks/{eventType}"
										class="px-2 py-1 text-xs rounded-md font-medium transition-colors hover:opacity-80"
										style="background-color: {colorVars.subtle}; color: {colorVars.color};"
									>
										{eventType}
									</a>
								{/each}
							</div>
						</div>

						<!-- Registration Count -->
						<div
							class="flex items-center justify-between pt-3 border-t border-[var(--border)]"
						>
							<span class="text-xs text-[var(--text-muted)]">Registrations</span>
							<span
								class="text-sm font-semibold text-[var(--text-primary)] tabular-nums"
							>
								{script.registrations}
							</span>
						</div>

						<!-- Symlink Info -->
						{#if script.is_symlink && script.symlink_target}
							<div
								class="mt-3 pt-3 border-t border-[var(--border)] flex items-start gap-2"
							>
								<LinkIcon
									size={12}
									class="text-[var(--text-muted)] flex-shrink-0 mt-0.5"
								/>
								<div class="flex-1 min-w-0">
									<p class="text-xs text-[var(--text-muted)]">Symlink to:</p>
									<p
										class="text-xs text-[var(--text-secondary)] truncate mt-0.5"
										title={script.symlink_target}
									>
										{script.symlink_target}
									</p>
								</div>
							</div>
						{/if}
					</div>
				{/each}
			</div>
		{/if}
	</div>
</div>
