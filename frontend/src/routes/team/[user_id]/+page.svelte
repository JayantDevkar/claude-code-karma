<script lang="ts">
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import { User, FolderGit2, Clock, Monitor } from 'lucide-svelte';

	let { data } = $props();
</script>

<PageHeader
	title={data.user_id}
	icon={User}
	iconColor="--nav-purple"
	breadcrumbs={[{ label: 'Team', href: '/team' }]}
/>

<div class="space-y-3">
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
							Synced: {new Date(project.synced_at).toLocaleString()}
						</span>
						{#if project.machine_id}
							<span class="flex items-center gap-1 opacity-70">
								<Monitor size={12} />
								{project.machine_id}
							</span>
						{/if}
					</div>
				{/if}
			</div>
		{/each}
	{/if}
</div>
