<script lang="ts">
	import { Users, Loader2, WifiOff, FileText } from 'lucide-svelte';
	import { API_BASE } from '$lib/config';
	import type { RemoteSessionUser } from '$lib/api-types';

	let {
		projectEncodedName,
		active = false
	}: {
		projectEncodedName: string;
		active?: boolean;
	} = $props();

	let users = $state<RemoteSessionUser[]>([]);
	let loading = $state(false);
	let loaded = $state(false);
	let error = $state<string | null>(null);

	async function loadRemoteSessions() {
		if (loaded || loading) return;
		loading = true;
		error = null;
		try {
			const res = await fetch(
				`${API_BASE}/projects/${encodeURIComponent(projectEncodedName)}/remote-sessions`
			);
			if (res.ok) {
				const data = await res.json();
				users = data.users ?? [];
			} else {
				error = 'Failed to load remote sessions';
			}
		} catch {
			error = 'Cannot reach backend';
		} finally {
			loading = false;
			if (!error) loaded = true;
		}
	}

	$effect(() => {
		if (active && !loaded) {
			loadRemoteSessions();
		}
	});

	function formatBytes(bytes: number): string {
		if (bytes < 1024) return `${bytes} B`;
		if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
		return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
	}

	function formatRelative(mtime: number): string {
		const diff = Date.now() - mtime * 1000;
		const mins = Math.floor(diff / 60000);
		if (mins < 1) return 'just now';
		if (mins < 60) return `${mins}m ago`;
		const hours = Math.floor(mins / 60);
		if (hours < 24) return `${hours}h ago`;
		const days = Math.floor(hours / 24);
		return `${days}d ago`;
	}

	let totalSessions = $derived(users.reduce((sum, u) => sum + u.session_count, 0));
</script>

<div class="space-y-6">
	<div>
		<h2 class="text-lg font-semibold text-[var(--text-primary)]">Team Sessions</h2>
		<p class="text-sm text-[var(--text-muted)]">
			Sessions synced from teammates for this project.
		</p>
	</div>

	{#if loading}
		<div class="flex items-center justify-center py-12 text-[var(--text-muted)]">
			<Loader2 size={20} class="animate-spin" />
		</div>
	{:else if error}
		<div
			class="flex items-center gap-3 p-4 rounded-[var(--radius-lg)] border border-[var(--error)]/20 bg-[var(--error-subtle)]"
		>
			<WifiOff size={14} class="text-[var(--error)] shrink-0" />
			<span class="text-sm text-[var(--error)] flex-1">{error}</span>
			<button
				onclick={() => { loaded = false; loadRemoteSessions(); }}
				class="text-xs font-medium text-[var(--error)] underline hover:no-underline"
			>
				Retry
			</button>
		</div>
	{:else if users.length === 0}
		<div class="text-center py-12">
			<Users size={28} class="mx-auto mb-3 text-[var(--text-muted)]" />
			<p class="text-sm font-medium text-[var(--text-primary)]">No team sessions yet</p>
			<p class="text-xs text-[var(--text-muted)] mt-1">
				When teammates sync sessions for this project, they'll appear here.
			</p>
		</div>
	{:else}
		<!-- Summary -->
		<div class="flex items-center gap-4 text-sm text-[var(--text-secondary)]">
			<span class="flex items-center gap-1.5">
				<Users size={14} class="text-[var(--text-muted)]" />
				{users.length} teammate{users.length !== 1 ? 's' : ''}
			</span>
			<span class="flex items-center gap-1.5">
				<FileText size={14} class="text-[var(--text-muted)]" />
				{totalSessions} session{totalSessions !== 1 ? 's' : ''}
			</span>
		</div>

		<!-- User cards -->
		<div class="space-y-4">
			{#each users as user (user.user_id)}
				<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)]">
					<!-- User header -->
					<div class="flex items-center justify-between px-5 py-3.5 border-b border-[var(--border-subtle)]">
						<div class="flex items-center gap-3">
							<div
								class="w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold bg-[var(--accent)]/10 text-[var(--accent)]"
							>
								{user.user_id.charAt(0).toUpperCase()}
							</div>
							<div>
								<p class="text-sm font-medium text-[var(--text-primary)]">{user.user_id}</p>
								<p class="text-[11px] text-[var(--text-muted)]">
									{user.session_count} session{user.session_count !== 1 ? 's' : ''}
									{#if user.synced_at}
										&middot; synced {formatRelative(new Date(user.synced_at).getTime() / 1000)}
									{/if}
								</p>
							</div>
						</div>
					</div>

					<!-- Session list -->
					<div class="px-5 divide-y divide-[var(--border-subtle)]">
						{#each user.sessions.slice(0, 10) as session (session.uuid)}
							<div class="flex items-center justify-between py-2.5">
								<div class="min-w-0">
									<p class="text-xs font-mono text-[var(--text-secondary)] truncate">
										{session.uuid.slice(0, 12)}...
									</p>
								</div>
								<div class="flex items-center gap-3 text-[11px] text-[var(--text-muted)] shrink-0">
									<span>{formatBytes(session.size_bytes)}</span>
									<span>{formatRelative(session.mtime)}</span>
								</div>
							</div>
						{/each}
						{#if user.sessions.length > 10}
							<p class="py-2.5 text-xs text-[var(--text-muted)]">
								+{user.sessions.length - 10} more sessions
							</p>
						{/if}
					</div>
				</div>
			{/each}
		</div>
	{/if}
</div>
