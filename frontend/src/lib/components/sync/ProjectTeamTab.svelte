<script lang="ts">
	import { Users, Loader2, WifiOff, FileText } from 'lucide-svelte';
	import { API_BASE } from '$lib/config';
	import type { RemoteSessionUser } from '$lib/api-types';
	import SessionCard from '$lib/components/SessionCard.svelte';
	import { formatRelativeTime, getTeamMemberColor } from '$lib/utils';

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
	let expandedUsers = $state<Set<string>>(new Set());

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

	function toggleExpanded(userId: string) {
		const next = new Set(expandedUsers);
		if (next.has(userId)) {
			next.delete(userId);
		} else {
			next.add(userId);
		}
		expandedUsers = next;
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
				{@const color = getTeamMemberColor(user.user_id)}
				{@const isExpanded = expandedUsers.has(user.user_id)}
				{@const visibleSessions = isExpanded ? user.sessions : user.sessions.slice(0, 10)}
				{@const hiddenCount = Math.max(0, user.sessions.length - 10)}
				<div class="rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-subtle)]">
					<!-- User header -->
					<div class="flex items-center justify-between px-5 py-3.5 border-b border-[var(--border-subtle)]">
						<div class="flex items-center gap-3">
							<div
								class="w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold"
								style="background-color: {color.bg}; color: {color.border}"
							>
								{user.user_id.charAt(0).toUpperCase()}
							</div>
							<div>
								<p class="text-sm font-medium text-[var(--text-primary)]">{user.user_id}</p>
								<p class="text-[11px] text-[var(--text-muted)]">
									{user.session_count} session{user.session_count !== 1 ? 's' : ''}
									{#if user.synced_at}
										&middot; synced {formatRelativeTime(user.synced_at)}
									{/if}
								</p>
							</div>
						</div>
					</div>

					<!-- Session list using SessionCard -->
					<div class="p-3 space-y-2">
						{#each visibleSessions as session (session.uuid)}
							<SessionCard {session} {projectEncodedName} compact showBranch={false} />
						{/each}
						{#if hiddenCount > 0}
							<button
								onclick={() => toggleExpanded(user.user_id)}
								class="w-full py-2 text-xs font-medium text-[var(--accent)] hover:text-[var(--accent-hover)] transition-colors"
							>
								{isExpanded ? 'Show less' : `+${hiddenCount} more sessions`}
							</button>
						{/if}
					</div>
				</div>
			{/each}
		</div>
	{/if}
</div>
