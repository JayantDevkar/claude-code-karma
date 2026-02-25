<script lang="ts">
	import { FolderOpen, GitBranch, Activity, MessageSquare } from 'lucide-svelte';
	import type { Project } from '$lib/api-types';

	interface Props {
		project: Project;
		variant?: 'default' | 'compact';
		showRootBadge?: boolean;
		showNestedGitBadge?: boolean;
		relativePath?: string;
		hideGitBadge?: boolean;
		class?: string;
	}

	let {
		project,
		variant = 'default',
		showRootBadge = false,
		showNestedGitBadge = false,
		relativePath,
		hideGitBadge = false,
		class: className = ''
	}: Props = $props();

	function formatTime(timestamp?: string) {
		if (!timestamp) return 'No activity';
		const date = new Date(timestamp);
		const now = new Date();
		const diff = now.getTime() - date.getTime();
		const hours = Math.floor(diff / (1000 * 60 * 60));
		const days = Math.floor(hours / 24);

		if (hours < 1) return 'Just now';
		if (hours < 24) return `${hours}h ago`;
		if (days < 7) return `${days}d ago`;
		if (days < 30) return `${Math.floor(days / 7)}w ago`;
		return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
	}

	function getProjectName(path: string) {
		return path.split('/').pop() || path;
	}

	// Get the latest activity time - prefer latest_session_time (from list API),
	// fallback to first session's start_time (from detail API)
	const latestActivityTime = $derived(
		project.latest_session_time ?? project.sessions?.[0]?.start_time
	);

	// Check if project has recent activity (within last 6 hours)
	const hasRecentActivity = $derived.by(() => {
		if (!latestActivityTime) return false;
		const diff = Date.now() - new Date(latestActivityTime).getTime();
		return diff < 6 * 60 * 60 * 1000; // 6 hours
	});

	// Color scheme based on git status and activity
	const colorConfig = $derived.by(() => {
		if (project.is_git_repository) {
			return {
				border: hasRecentActivity ? 'var(--success)' : 'var(--nav-green)',
				iconBg: hasRecentActivity ? 'var(--success-subtle)' : 'var(--nav-green-subtle)',
				iconColor: hasRecentActivity ? 'var(--success)' : 'var(--nav-green)'
			};
		}
		return {
			border: hasRecentActivity ? 'var(--accent)' : 'var(--text-faint)',
			iconBg: hasRecentActivity ? 'var(--accent-subtle)' : 'var(--bg-muted)',
			iconColor: hasRecentActivity ? 'var(--accent)' : 'var(--text-muted)'
		};
	});
</script>

{#if variant === 'compact'}
	<!-- Compact variant for nested projects -->
	<a
		href="/projects/{project.slug}"
		class="
			block px-4 py-3 pl-5
			bg-[var(--bg-subtle)]
			border border-l-[3px] border-[var(--border)]
			rounded-[var(--radius-md)]
			hover:shadow-md
			transition-all
			group
			focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]
			{className}
		"
		style="
			border-left-color: {colorConfig.border};
			transition-duration: var(--duration-fast);
		"
		data-list-item
	>
		<div class="flex items-start gap-3">
			<!-- Icon with colored background -->
			<div
				class="flex h-8 w-8 items-center justify-center rounded-lg shrink-0 transition-colors"
				style="background-color: {colorConfig.iconBg};"
			>
				{#if project.is_git_repository}
					<GitBranch size={16} strokeWidth={2} style="color: {colorConfig.iconColor};" />
				{:else}
					<FolderOpen size={16} strokeWidth={2} style="color: {colorConfig.iconColor};" />
				{/if}
			</div>

			<!-- Content -->
			<div class="min-w-0 flex-1">
				<div class="flex items-start justify-between gap-2 mb-1">
					<h4
						class="text-sm font-mono font-medium text-[var(--accent)] leading-tight truncate"
					>
						{relativePath || getProjectName(project.path)}
					</h4>

					<!-- Badges -->
					<div class="flex items-center gap-1.5 shrink-0">
						{#if showRootBadge}
							<span
								class="
									px-1.5 py-0.5
									text-[10px] font-semibold uppercase tracking-wider
									bg-[var(--nav-purple-subtle)] text-[var(--nav-purple)]
									rounded-[var(--radius-xs)]
								"
							>
								Root
							</span>
						{/if}
						{#if showNestedGitBadge}
							<span
								class="
									px-1.5 py-0.5
									text-[10px] font-semibold uppercase tracking-wider
									bg-[var(--success-subtle)] text-[var(--success)]
									rounded-[var(--radius-xs)]
								"
							>
								Git
							</span>
						{/if}
					</div>
				</div>

				<!-- Stats row -->
				<div class="flex items-center justify-between text-xs text-[var(--text-muted)]">
					<div class="flex items-center gap-4">
						<div class="flex items-center gap-1.5">
							<MessageSquare size={12} strokeWidth={2} />
							<span class="tabular-nums">{project.session_count} sessions</span>
						</div>
						<div
							class="flex items-center gap-1.5"
							style={hasRecentActivity ? `color: ${colorConfig.border};` : ''}
						>
							<Activity size={12} strokeWidth={2} />
							<span class="tabular-nums">{formatTime(latestActivityTime)}</span>
						</div>
					</div>
					{#if hasRecentActivity}
						<span
							class="
								px-1.5 py-0.5
								text-[10px] font-semibold uppercase tracking-wider
								bg-[var(--accent-subtle)] text-[var(--accent)]
								rounded-[var(--radius-xs)]
							"
						>
							Recent
						</span>
					{/if}
				</div>
			</div>
		</div>
	</a>
{:else}
	<!-- Default variant for standalone projects -->
	<a
		href="/projects/{project.slug}"
		class="
			block p-4 pl-5
			bg-[var(--bg-subtle)]
			border border-l-[3px] border-[var(--border)]
			rounded-[var(--radius-lg)]
			hover:shadow-md
			transition-all
			group
			focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)]
			{className}
		"
		style="
			border-left-color: {colorConfig.border};
			transition-duration: var(--duration-fast);
		"
		data-list-item
	>
		<!-- Header -->
		<div class="flex items-start gap-3">
			<!-- Icon with colored background -->
			<div
				class="flex h-10 w-10 items-center justify-center rounded-lg shrink-0 transition-colors"
				style="background-color: {colorConfig.iconBg};"
			>
				{#if project.is_git_repository}
					<GitBranch size={20} strokeWidth={2} style="color: {colorConfig.iconColor};" />
				{:else}
					<FolderOpen size={20} strokeWidth={2} style="color: {colorConfig.iconColor};" />
				{/if}
			</div>

			<div class="min-w-0 flex-1">
				<h3
					class="text-sm font-mono font-medium text-[var(--accent)] leading-tight truncate mb-0.5"
				>
					{getProjectName(project.path)}
				</h3>

				<p class="text-xs font-mono text-[var(--text-muted)] truncate mb-3">
					{project.path}
				</p>

				<!-- Stats row (inline like SubagentCard) -->
				<div class="flex items-center gap-4 text-xs text-[var(--text-muted)]">
					<div class="flex items-center gap-1.5">
						<MessageSquare size={14} strokeWidth={2} />
						<span class="tabular-nums">{project.session_count} sessions</span>
					</div>
					{#if project.agent_count > 0}
						<div class="flex items-center gap-1.5">
							<Activity size={14} strokeWidth={2} />
							<span class="tabular-nums">{project.agent_count} agents</span>
						</div>
					{/if}
				</div>
			</div>
		</div>

		<!-- Footer: Last Activity -->
		<div
			class="mt-4 pt-3 border-t border-[var(--border)] flex items-center justify-between text-xs text-[var(--text-muted)]"
		>
			<div
				class="flex items-center gap-2"
				style={hasRecentActivity ? `color: ${colorConfig.border};` : ''}
			>
				<Activity size={13} strokeWidth={2} />
				<span class="tabular-nums">{formatTime(latestActivityTime)}</span>
			</div>
			{#if hasRecentActivity}
				<span
					class="
						px-1.5 py-0.5
						text-[10px] font-semibold uppercase tracking-wider
						bg-[var(--accent-subtle)] text-[var(--accent)]
						rounded-[var(--radius-xs)]
					"
				>
					Recent
				</span>
			{/if}
		</div>
	</a>
{/if}
