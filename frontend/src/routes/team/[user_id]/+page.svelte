<script lang="ts">
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import { User, FolderGit2, Clock, Monitor, FileText, HardDrive } from 'lucide-svelte';

	let { data } = $props();

	function formatBytes(bytes: number): string {
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}

	function formatDate(iso: string): string {
		return new Date(iso).toLocaleString();
	}
</script>

<PageHeader
	title={data.user_id}
	icon={User}
	iconColor="--nav-purple"
	breadcrumbs={[{ label: 'Team', href: '/team' }]}
/>

<div class="space-y-4">
	{#if data.error}
		<div class="text-center py-8 text-red-500">
			<p>Failed to load projects: {data.error}</p>
		</div>
	{:else if data.projects.length === 0}
		<p class="text-[var(--text-muted)] py-8 text-center">No synced projects for this user.</p>
	{:else}
		{#each data.projects as project}
			<div
				class="border border-[var(--border)] rounded-[var(--radius-lg)] p-4 bg-[var(--bg-base)]"
			>
				<div class="flex items-center gap-2">
					<FolderGit2 size={16} class="text-[var(--text-muted)]" />
					<span class="font-medium text-[var(--text-primary)] flex-1">
						{project.encoded_name}
					</span>
					<span
						class="text-xs px-2 py-0.5 rounded-full bg-[var(--bg-muted)] text-[var(--text-secondary)]"
					>
						{project.session_count} sessions
					</span>
				</div>
				{#if project.synced_at}
					<div class="flex items-center gap-3 mt-2 text-xs text-[var(--text-muted)]">
						<span class="flex items-center gap-1">
							<Clock size={12} />
							Synced: {formatDate(project.synced_at)}
						</span>
						{#if project.machine_id}
							<span class="flex items-center gap-1 opacity-70">
								<Monitor size={12} />
								{project.machine_id}
							</span>
						{/if}
					</div>
				{/if}

				{#if project.sessions && project.sessions.length > 0}
					<div class="mt-3 border-t border-[var(--border)] pt-3 space-y-1.5">
						{#each project.sessions as session}
							<a
								href="/projects/{project.encoded_name}/{session.uuid}"
								class="flex items-center gap-3 px-3 py-2 rounded-[var(--radius)] hover:bg-[var(--bg-subtle)] transition-colors group"
							>
								<FileText
									size={14}
									class="text-[var(--text-muted)] group-hover:text-[var(--accent)]"
								/>
								<span
									class="font-mono text-xs text-[var(--text-secondary)] group-hover:text-[var(--text-primary)]"
								>
									{session.uuid.slice(0, 8)}...
								</span>
								<span class="flex-1"></span>
								<span class="flex items-center gap-1 text-xs text-[var(--text-muted)]">
									<HardDrive size={10} />
									{formatBytes(session.size_bytes)}
								</span>
								<span class="text-xs text-[var(--text-muted)]">
									{formatDate(session.mtime)}
								</span>
							</a>
						{/each}
					</div>
				{/if}
			</div>
		{/each}
	{/if}
</div>
