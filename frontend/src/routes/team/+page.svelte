<script lang="ts">
	import PageHeader from '$lib/components/layout/PageHeader.svelte';
	import { Users, MessageSquare } from 'lucide-svelte';

	let { data } = $props();
</script>

<PageHeader
	title="Team"
	icon={Users}
	iconColor="--nav-purple"
	breadcrumbs={[{ label: 'Dashboard', href: '/' }, { label: 'Team' }]}
/>

<div class="space-y-6">
	{#if data.error}
		<div class="text-center py-8 text-red-500">
			<p>Failed to load team data: {data.error}</p>
		</div>
	{:else if data.users.length === 0}
		<div
			class="flex flex-col items-center justify-center py-16 text-center text-[var(--text-muted)]"
		>
			<Users size={48} strokeWidth={1} class="mb-4 opacity-40" />
			<h3 class="text-lg font-medium text-[var(--text-primary)] mb-2">No remote sessions yet</h3>
			<p class="mb-4">Team members can sync their sessions using the <code>karma</code> CLI.</p>
			<pre
				class="inline-block px-4 py-2 bg-[var(--bg-muted)] rounded-[var(--radius-md)] text-sm font-mono"
			>karma init && karma sync &lt;project&gt;</pre>
		</div>
	{:else}
		<div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
			{#each data.users as user}
				<a
					href="/team/{encodeURIComponent(user.user_id)}"
					class="block border border-[var(--border)] rounded-[var(--radius-lg)] p-5 hover:border-[var(--accent)] transition-colors bg-[var(--bg-base)]"
				>
					<div class="flex items-center justify-between mb-3">
						<span class="font-semibold text-[var(--text-primary)]">{user.user_id}</span>
						<span
							class="text-xs px-2 py-0.5 rounded-full bg-[var(--bg-muted)] text-[var(--text-secondary)]"
						>
							{user.project_count} {user.project_count === 1 ? 'project' : 'projects'}
						</span>
					</div>
					<div class="flex items-center gap-4 text-sm text-[var(--text-muted)]">
						<span class="flex items-center gap-1.5">
							<MessageSquare size={14} />
							{user.total_sessions} sessions
						</span>
					</div>
				</a>
			{/each}
		</div>
	{/if}
</div>
