<script lang="ts">
	import { API_BASE } from '$lib/config';
	import { invalidateAll } from '$app/navigation';
	import { onMount, onDestroy } from 'svelte';
	import {
		FolderSync,
		Plus,
		Trash2,
		Loader2,
		Play,
		Pause,
		X,
		ArrowUpDown,
		ArrowUp,
		ArrowDown
	} from 'lucide-svelte';
	import type { SyncTeamProject, SyncSubscription } from '$lib/api-types';
	import AddProjectDialog from './AddProjectDialog.svelte';

	interface Props {
		projects: SyncTeamProject[];
		teamName: string;
		subscriptions: SyncSubscription[];
		memberTag: string | undefined;
		allProjects: { encoded_name: string; name: string; path: string }[];
		onrefresh: () => void;
	}

	let {
		projects,
		teamName,
		subscriptions,
		memberTag,
		allProjects,
		onrefresh
	}: Props = $props();

	let showAddProject = $state(false);
	let removeProjectConfirm = $state<string | null>(null);
	let removeProjectError = $state<string | null>(null);
	let subscriptionActing = $state<string | null>(null);
	let directionActing = $state<string | null>(null);

	// Get the current user's subscription for a project
	function getMySubscription(gitIdentity: string): SyncSubscription | undefined {
		if (!memberTag) return undefined;
		return subscriptions.find(
			(s) => s.project_git_identity === gitIdentity && s.member_tag === memberTag
		);
	}

	function getProjectDisplayName(project: SyncTeamProject): string {
		if (project.encoded_name) return project.encoded_name;
		return project.git_identity;
	}

	function directionIcon(direction: string) {
		switch (direction) {
			case 'send': return ArrowUp;
			case 'receive': return ArrowDown;
			default: return ArrowUpDown;
		}
	}

	function directionLabel(direction: string): string {
		switch (direction) {
			case 'send': return 'Send';
			case 'receive': return 'Receive';
			default: return 'Both';
		}
	}

	let sharedProjectIdentities = $derived(projects.map((p) => p.git_identity));

	async function handleRemoveProject(gitIdentity: string) {
		removeProjectError = null;
		try {
			const res = await fetch(
				`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/projects/${encodeURIComponent(gitIdentity)}`,
				{ method: 'DELETE' }
			);
			if (res.ok) {
				removeProjectConfirm = null;
				removeProjectError = null;
				onrefresh();
			} else {
				removeProjectError = `Failed to remove project (${res.status})`;
			}
		} catch {
			removeProjectError = 'Network error — could not remove project';
		}
	}

	async function handleSubscriptionAction(gitIdentity: string, action: 'accept' | 'pause' | 'resume' | 'decline') {
		subscriptionActing = gitIdentity;
		try {
			const url = `${API_BASE}/sync/subscriptions/${encodeURIComponent(teamName)}/${encodeURIComponent(gitIdentity)}/${action}`;
			const body = action === 'accept' ? JSON.stringify({ direction: 'both' }) : undefined;
			const res = await fetch(url, {
				method: 'POST',
				headers: body ? { 'Content-Type': 'application/json' } : {},
				body
			});
			if (res.ok) {
				onrefresh();
			}
		} catch {
			// best-effort
		} finally {
			subscriptionActing = null;
		}
	}

	async function handleDirectionChange(gitIdentity: string, newDirection: string) {
		directionActing = gitIdentity;
		try {
			const res = await fetch(
				`${API_BASE}/sync/subscriptions/${encodeURIComponent(teamName)}/${encodeURIComponent(gitIdentity)}/direction`,
				{
					method: 'PATCH',
					headers: { 'Content-Type': 'application/json' },
					body: JSON.stringify({ direction: newDirection })
				}
			);
			if (res.ok) {
				onrefresh();
			}
		} catch {
			// best-effort
		} finally {
			directionActing = null;
		}
	}

	function cycleDirection(current: string): string {
		const order = ['both', 'send', 'receive'];
		const idx = order.indexOf(current);
		return order[(idx + 1) % order.length];
	}

	// --- Pending folders ---
	interface PendingFolder {
		folder_id: string;
		label: string;
		from_device: string;
		from_member: string | null;
		offered_at: string;
		folder_type: string;
		project_name: string;
	}

	let pendingFolders = $state<PendingFolder[]>([]);
	let pendingLoading = $state(true);
	let acceptingId = $state<string | null>(null);
	let rejectingId = $state<string | null>(null);
	let acceptingAll = $state(false);

	async function loadPendingFolders() {
		try {
			const res = await fetch(`${API_BASE}/sync/pending`);
			if (res.ok) {
				const data = await res.json();
				pendingFolders = (data.folders ?? [])
					.filter((f: any) => f.folder_type === 'out')
					.map((f: any) => {
						const parts = f.folder_id.split('--');
						const suffix = parts.length >= 3 ? parts.slice(2).join('--') : f.folder_id;
						return { ...f, project_name: suffix };
					});
			}
		} catch { /* non-critical */ }
		finally { pendingLoading = false; }
	}

	async function acceptFolder(folder: PendingFolder) {
		acceptingId = folder.folder_id;
		try {
			const res = await fetch(`${API_BASE}/sync/pending/accept/${encodeURIComponent(folder.folder_id)}`, {
				method: 'POST'
			});
			if (res.ok) {
				await loadPendingFolders();
				onrefresh();
			}
		} catch { /* */ }
		finally { acceptingId = null; }
	}

	async function rejectFolder(folder: PendingFolder) {
		rejectingId = folder.folder_id;
		try {
			const res = await fetch(`${API_BASE}/sync/pending/reject/${encodeURIComponent(folder.folder_id)}`, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ device_id: folder.from_device })
			});
			if (res.ok) {
				await loadPendingFolders();
			}
		} catch { /* */ }
		finally { rejectingId = null; }
	}

	async function acceptAll() {
		acceptingAll = true;
		try {
			for (const folder of pendingFolders) {
				await acceptFolder(folder);
			}
		} finally {
			acceptingAll = false;
		}
	}

	let pollInterval: ReturnType<typeof setInterval> | null = null;

	onMount(() => {
		loadPendingFolders();
		pollInterval = setInterval(loadPendingFolders, 15000);
	});

	onDestroy(() => {
		if (pollInterval) clearInterval(pollInterval);
	});
</script>

<div class="space-y-4">
	<!-- Pending folder invitations -->
	{#if pendingFolders.length > 0}
		<div class="space-y-3 mb-6">
			<div class="flex items-center gap-3">
				<span class="text-sm font-semibold text-[var(--warning)]">Pending Invitations</span>
				<div class="flex-1 h-px bg-[var(--warning)]/15"></div>
				<button
					onclick={acceptAll}
					disabled={acceptingAll}
					class="px-3 py-1.5 text-xs font-medium rounded-[var(--radius-md)] bg-[var(--success)]/10 text-[var(--success)] border border-[var(--success)]/20 hover:bg-[var(--success)]/15 transition-colors disabled:opacity-50"
				>
					{#if acceptingAll}
						<Loader2 size={12} class="animate-spin inline mr-1" />
					{/if}
					Accept All
				</button>
			</div>

			{#each pendingFolders as folder (folder.folder_id)}
				<div class="flex items-center gap-3 p-3.5 rounded-[var(--radius-lg)] border border-[var(--warning)]/15 bg-[var(--warning)]/[0.02]">
					<div class="w-8 h-8 rounded-lg bg-[var(--accent)]/10 flex items-center justify-center shrink-0">
						<FolderSync size={15} class="text-[var(--accent)]" />
					</div>
					<div class="flex-1 min-w-0">
						<div class="text-sm font-medium text-[var(--text-primary)] truncate">{folder.project_name}</div>
						{#if folder.from_member}
							<div class="text-[11px] text-[var(--text-muted)] mt-0.5">from {folder.from_member}</div>
						{/if}
					</div>
					<div class="flex gap-2 shrink-0">
						<button
							onclick={() => acceptFolder(folder)}
							disabled={acceptingId === folder.folder_id}
							class="px-3 py-1.5 text-xs font-medium rounded-[var(--radius-md)] bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors disabled:opacity-50"
						>
							{#if acceptingId === folder.folder_id}
								<Loader2 size={12} class="animate-spin" />
							{:else}
								Accept
							{/if}
						</button>
						<button
							onclick={() => rejectFolder(folder)}
							disabled={rejectingId === folder.folder_id}
							class="px-3 py-1.5 text-xs font-medium rounded-[var(--radius-md)] border border-[var(--border)] text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-muted)] transition-colors disabled:opacity-50"
						>
							Reject
						</button>
					</div>
				</div>
			{/each}
		</div>
	{/if}

	<!-- Header row -->
	<div class="flex items-center justify-between">
		<button
			onclick={() => (showAddProject = true)}
			class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-[var(--radius-md)]
				border border-[var(--border)] text-[var(--text-secondary)]
				hover:bg-[var(--bg-muted)] hover:text-[var(--text-primary)] transition-colors"
		>
			<Plus size={13} />
			Add Projects
		</button>
	</div>

	{#if removeProjectError}
		<p class="text-xs text-[var(--error)]" aria-live="polite">{removeProjectError}</p>
	{/if}

	<!-- Project cards -->
	<div class="space-y-2">
		{#each projects as project (project.git_identity)}
			{@const mySub = getMySubscription(project.git_identity)}
			{@const isActing = subscriptionActing === project.git_identity}
			{@const isDirActing = directionActing === project.git_identity}
			<div class="p-4 rounded-lg border border-[var(--border)] bg-[var(--bg-base)]">
				<!-- Project header info -->
				<div class="flex items-center justify-between">
					<div class="flex items-center gap-3 min-w-0">
						<FolderSync size={16} class="text-[var(--text-muted)] shrink-0" />
						<div class="min-w-0">
							{#if project.encoded_name}
								<a
									href="/projects/{project.encoded_name}"
									class="text-sm font-medium text-[var(--text-primary)] hover:text-[var(--accent)] transition-colors truncate block"
								>
									{getProjectDisplayName(project)}
								</a>
							{:else}
								<span class="text-sm font-medium text-[var(--text-primary)] truncate block">
									{getProjectDisplayName(project)}
								</span>
							{/if}
							<div class="flex items-center gap-2 mt-0.5">
								<span class="text-[11px] text-[var(--text-muted)] font-mono truncate">
									{project.git_identity}
								</span>
								<span class="text-[var(--border)]">&middot;</span>
								<span class="text-[11px] text-[var(--text-muted)] font-mono">
									{project.folder_suffix}
								</span>
							</div>
						</div>
					</div>
					<div class="flex items-center gap-2 shrink-0">
						<!-- Project status badge -->
						<span class="px-2 py-1 text-[11px] font-medium rounded-full border
							{project.status === 'shared'
								? 'bg-[var(--success)]/10 text-[var(--success)] border-[var(--success)]/20'
								: 'bg-[var(--error)]/10 text-[var(--error)] border-[var(--error)]/20'}">
							{project.status}
						</span>

						<!-- Remove button -->
						{#if removeProjectConfirm === project.git_identity}
							<div class="flex items-center gap-1.5">
								<button
									onclick={() => handleRemoveProject(project.git_identity)}
									class="px-2 py-1 text-xs font-medium rounded bg-[var(--error)] text-white hover:bg-[var(--error)]/80 transition-colors"
								>
									Remove
								</button>
								<button
									onclick={() => (removeProjectConfirm = null)}
									class="px-2 py-1 text-xs rounded text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition-colors"
								>
									Cancel
								</button>
							</div>
						{:else}
							<button
								onclick={() => (removeProjectConfirm = project.git_identity)}
								class="p-1.5 rounded text-[var(--text-muted)] hover:text-[var(--error)] hover:bg-[var(--error)]/10 transition-colors"
								title="Remove from team"
								aria-label="Remove project {getProjectDisplayName(project)}"
							>
								<Trash2 size={14} />
							</button>
						{/if}
					</div>
				</div>

				<!-- Subscription row -->
				{#if mySub}
					<div class="flex items-center justify-between mt-3 pt-3 border-t border-[var(--border)]/50">
						<div class="flex items-center gap-2">
							<span class="text-[11px] text-[var(--text-muted)]">My subscription:</span>
							<span class="px-2 py-0.5 text-[10px] font-medium rounded-full border
								{mySub.status === 'accepted' ? 'bg-[var(--success)]/10 text-[var(--success)] border-[var(--success)]/20'
								: mySub.status === 'paused' ? 'bg-[var(--warning)]/10 text-[var(--warning)] border-[var(--warning)]/20'
								: mySub.status === 'declined' ? 'bg-[var(--error)]/10 text-[var(--error)] border-[var(--error)]/20'
								: 'bg-[var(--bg-muted)] text-[var(--text-muted)] border-[var(--border)]'}">
								{mySub.status}
							</span>
							{#if mySub.status === 'accepted'}
								<!-- Direction toggle button -->
								{@const DirIcon = directionIcon(mySub.direction)}
								<button
									onclick={() => handleDirectionChange(project.git_identity, cycleDirection(mySub.direction))}
									disabled={isDirActing}
									class="flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium rounded-full border border-[var(--accent)]/20 bg-[var(--accent)]/10 text-[var(--accent)] hover:bg-[var(--accent)]/20 transition-colors disabled:opacity-50"
									title="Click to cycle direction"
								>
									{#if isDirActing}
										<Loader2 size={10} class="animate-spin" />
									{:else}
										<DirIcon size={10} />
									{/if}
									{directionLabel(mySub.direction)}
								</button>
							{/if}
						</div>

						<!-- Subscription actions -->
						<div class="flex items-center gap-1.5">
							{#if mySub.status === 'offered'}
								<button
									onclick={() => handleSubscriptionAction(project.git_identity, 'accept')}
									disabled={isActing}
									class="flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md bg-[var(--success)] text-white hover:bg-[var(--success)]/85 transition-colors disabled:opacity-50"
								>
									{#if isActing}<Loader2 size={11} class="animate-spin" />{:else}<Play size={11} />{/if}
									Accept
								</button>
								<button
									onclick={() => handleSubscriptionAction(project.git_identity, 'decline')}
									disabled={isActing}
									class="flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md text-[var(--text-muted)] hover:text-[var(--error)] hover:bg-[var(--error)]/5 transition-colors disabled:opacity-50"
								>
									<X size={11} />
									Decline
								</button>
							{:else if mySub.status === 'accepted'}
								<button
									onclick={() => handleSubscriptionAction(project.git_identity, 'pause')}
									disabled={isActing}
									class="flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md text-[var(--text-muted)] hover:text-[var(--warning)] hover:bg-[var(--warning)]/5 transition-colors disabled:opacity-50"
								>
									{#if isActing}<Loader2 size={11} class="animate-spin" />{:else}<Pause size={11} />{/if}
									Pause
								</button>
							{:else if mySub.status === 'paused'}
								<button
									onclick={() => handleSubscriptionAction(project.git_identity, 'resume')}
									disabled={isActing}
									class="flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md bg-[var(--success)] text-white hover:bg-[var(--success)]/85 transition-colors disabled:opacity-50"
								>
									{#if isActing}<Loader2 size={11} class="animate-spin" />{:else}<Play size={11} />{/if}
									Resume
								</button>
							{:else if mySub.status === 'declined'}
								<button
									onclick={() => handleSubscriptionAction(project.git_identity, 'accept')}
									disabled={isActing}
									class="flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-md bg-[var(--success)] text-white hover:bg-[var(--success)]/85 transition-colors disabled:opacity-50"
								>
									{#if isActing}<Loader2 size={11} class="animate-spin" />{:else}<Play size={11} />{/if}
									Accept
								</button>
							{/if}
						</div>
					</div>
				{/if}
			</div>
		{/each}

		{#if projects.length === 0}
			<p class="text-sm text-[var(--text-muted)] py-8 text-center">
				No projects shared yet. Add projects to start syncing sessions with your team.
			</p>
		{/if}
	</div>
</div>

<AddProjectDialog
	bind:open={showAddProject}
	{teamName}
	{allProjects}
	sharedProjectNames={sharedProjectIdentities}
	onadded={onrefresh}
/>
