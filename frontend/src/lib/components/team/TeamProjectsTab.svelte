<script lang="ts">
	import { onMount } from 'svelte';
	import { API_BASE } from '$lib/config';
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
		ArrowDown,
		Check,
		Inbox,
		RefreshCw,
		CheckCircle2
	} from 'lucide-svelte';
	import type { SyncTeamProject, SyncSubscription, SyncProjectStatus } from '$lib/api-types';
	import AddProjectDialog from './AddProjectDialog.svelte';

	interface Props {
		projects: SyncTeamProject[];
		teamName: string;
		subscriptions: SyncSubscription[];
		memberTag: string | undefined;
		isLeader?: boolean;
		allProjects: { encoded_name: string; name: string; path: string; git_remote_url?: string | null }[];
		onrefresh: () => void;
	}

	let {
		projects,
		teamName,
		subscriptions,
		memberTag,
		isLeader = false,
		allProjects,
		onrefresh
	}: Props = $props();

	let showAddProject = $state(false);
	let removeProjectConfirm = $state<string | null>(null);
	let removeProjectError = $state<string | null>(null);
	let subscriptionActing = $state<string | null>(null);
	let directionActing = $state<string | null>(null);

	// Track selected direction per invitation (before accepting)
	let selectedDirections = $state<Record<string, string>>({});

	// Direction options with human-readable descriptions
	const DIRECTION_OPTIONS = [
		{ value: 'both', label: 'Both ways', desc: 'Send your sessions & receive theirs', icon: ArrowUpDown },
		{ value: 'send', label: 'Send only', desc: 'Share your sessions with the team', icon: ArrowUp },
		{ value: 'receive', label: 'Receive only', desc: 'Get team sessions without sharing', icon: ArrowDown }
	] as const;

	// Get the current user's subscription for a project
	function getMySubscription(gitIdentity: string): SyncSubscription | undefined {
		if (!memberTag) return undefined;
		return subscriptions.find(
			(s) => s.project_git_identity === gitIdentity && s.member_tag === memberTag
		);
	}

	// Look up human-readable project info from allProjects.
	// Matches by git_identity (remote URL) first for cross-machine matching,
	// then falls back to encoded_name for same-machine or non-git projects.
	function getProjectInfo(project: SyncTeamProject): { displayName: string; path: string; localEncodedName?: string } {
		const gitId = project.git_identity;
		// Try matching by git remote URL (works across machines)
		const remoteMatch = allProjects.find(p => p.git_remote_url && p.git_remote_url === gitId);
		if (remoteMatch) {
			return { displayName: remoteMatch.name, path: remoteMatch.path, localEncodedName: remoteMatch.encoded_name };
		}
		// Try matching by encoded_name (same machine)
		const key = project.encoded_name || gitId;
		const nameMatch = allProjects.find(p => p.encoded_name === key);
		if (nameMatch) {
			return { displayName: nameMatch.name, path: nameMatch.path, localEncodedName: nameMatch.encoded_name };
		}
		// Fallback: extract last meaningful segment
		const segments = key.replace(/^-/, '').split('-');
		const name = segments.length >= 2
			? segments.slice(-2).join('-')
			: segments[segments.length - 1] || key;
		return { displayName: name, path: key };
	}

	function getSelectedDir(gitIdentity: string): string {
		return selectedDirections[gitIdentity] ?? 'both';
	}

	function selectDir(gitIdentity: string, dir: string) {
		selectedDirections = { ...selectedDirections, [gitIdentity]: dir };
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
			case 'send': return 'Send only';
			case 'receive': return 'Receive only';
			default: return 'Both ways';
		}
	}

	let sharedProjectIdentities = $derived(projects.map((p) => p.git_identity));

	// Split projects: offered invitations vs everything else
	let offeredProjects = $derived(
		projects.filter(p => {
			const sub = getMySubscription(p.git_identity);
			return sub?.status === 'offered';
		})
	);

	let activeProjects = $derived(
		projects.filter(p => {
			const sub = getMySubscription(p.git_identity);
			return sub?.status !== 'offered';
		})
	);

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

	async function handleSubscriptionAction(gitIdentity: string, action: 'accept' | 'pause' | 'resume' | 'decline', direction: string = 'both') {
		subscriptionActing = gitIdentity;
		try {
			const url = `${API_BASE}/sync/subscriptions/${encodeURIComponent(teamName)}/${encodeURIComponent(gitIdentity)}/${action}`;
			const body = action === 'accept' ? JSON.stringify({ direction }) : undefined;
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

	// ── Sync status state ──
	let projectStatuses = $state<SyncProjectStatus[]>([]);
	let syncingProject = $state<string | null>(null);
	let syncingAll = $state(false);

	async function loadProjectStatus() {
		try {
			const res = await fetch(
				`${API_BASE}/sync/teams/${encodeURIComponent(teamName)}/project-status`
			).catch(() => null);
			if (res?.ok) {
				const data = await res.json();
				projectStatuses = data.projects ?? [];
			}
		} catch {
			// non-critical
		}
	}

	let statusByGit = $derived.by(() => {
		const map = new Map<string, SyncProjectStatus>();
		for (const ps of projectStatuses) {
			map.set(ps.git_identity, ps);
		}
		return map;
	});

	let totalTeamGap = $derived(
		projectStatuses.reduce((sum, p) => sum + (p.gap ?? 0), 0)
	);

	async function syncProject(gitIdentity: string) {
		syncingProject = gitIdentity;
		try {
			await fetch(
				`${API_BASE}/sync/package?team_name=${encodeURIComponent(teamName)}&git_identity=${encodeURIComponent(gitIdentity)}`,
				{ method: 'POST' }
			);
			await loadProjectStatus();
		} finally {
			syncingProject = null;
		}
	}

	async function syncAllTeam() {
		syncingAll = true;
		try {
			await fetch(
				`${API_BASE}/sync/package?team_name=${encodeURIComponent(teamName)}`,
				{ method: 'POST' }
			);
			await loadProjectStatus();
		} finally {
			syncingAll = false;
		}
	}

	onMount(() => {
		loadProjectStatus();
	});
</script>

<div class="space-y-6">
	<!-- ═══════════════════════════════════════════════════════
	     Pending Invitations — prominent cards for offered subs
	     ═══════════════════════════════════════════════════════ -->
	{#if offeredProjects.length > 0}
		<section class="space-y-3">
			<div class="flex items-center gap-2.5">
				<div class="w-6 h-6 rounded-md bg-[var(--warning)]/12 flex items-center justify-center">
					<Inbox size={13} class="text-[var(--warning)]" />
				</div>
				<h3 class="text-sm font-semibold text-[var(--text-primary)]">
					Pending Invitation{offeredProjects.length !== 1 ? 's' : ''}
				</h3>
				<span class="px-1.5 py-0.5 text-[10px] font-bold rounded-full bg-[var(--warning)] text-white">
					{offeredProjects.length}
				</span>
			</div>

			{#each offeredProjects as project (project.git_identity)}
				{@const info = getProjectInfo(project)}
				{@const isActing = subscriptionActing === project.git_identity}
				{@const dir = getSelectedDir(project.git_identity)}

				<div class="rounded-[var(--radius-lg)] border border-[var(--warning)]/20 bg-gradient-to-b from-[var(--warning)]/[0.03] to-transparent overflow-hidden">
					<!-- Project header -->
					<div class="px-5 pt-5 pb-3">
						<div class="flex items-start gap-3.5">
							<div class="w-10 h-10 rounded-lg bg-[var(--warning)]/10 border border-[var(--warning)]/15 flex items-center justify-center shrink-0">
								<FolderSync size={18} class="text-[var(--warning)]" />
							</div>
							<div class="flex-1 min-w-0">
								<div class="flex items-center gap-2.5">
									<h4 class="text-[15px] font-semibold text-[var(--text-primary)] truncate">
										{info.displayName}
									</h4>
									<span class="px-2 py-0.5 text-[10px] font-semibold tracking-wide uppercase rounded-full bg-[var(--warning)]/10 text-[var(--warning)] border border-[var(--warning)]/15 shrink-0">
										invitation
									</span>
								</div>
								<p class="text-xs font-mono text-[var(--text-faint)] mt-1 truncate">{info.path}</p>
							</div>
						</div>

						<p class="text-[13px] text-[var(--text-secondary)] mt-4">
							Choose how you want to sync sessions for this project:
						</p>
					</div>

					<!-- Direction selector — 3 option cards -->
					<div class="px-5 pb-4">
						<div class="grid grid-cols-3 gap-2">
							{#each DIRECTION_OPTIONS as opt}
								{@const isSelected = dir === opt.value}
								{@const Icon = opt.icon}
								<button
									onclick={() => selectDir(project.git_identity, opt.value)}
									class="relative flex flex-col items-center gap-1.5 p-3.5 rounded-[var(--radius-md)] border-2 transition-all text-center
										{isSelected
											? 'border-[var(--accent)] bg-[var(--accent)]/[0.05] shadow-[0_0_0_1px_rgba(var(--accent-rgb),0.1)]'
											: 'border-[var(--border)] hover:border-[var(--text-faint)]/40 hover:bg-[var(--bg-subtle)]'}"
								>
									{#if isSelected}
										<span class="absolute top-2 right-2 w-4 h-4 rounded-full bg-[var(--accent)] flex items-center justify-center">
											<Check size={10} class="text-white" />
										</span>
									{/if}
									<Icon size={18} class={isSelected ? 'text-[var(--accent)]' : 'text-[var(--text-muted)]'} />
									<span class="text-xs font-semibold {isSelected ? 'text-[var(--accent)]' : 'text-[var(--text-primary)]'}">
										{opt.label}
									</span>
									<span class="text-[10px] leading-snug {isSelected ? 'text-[var(--accent)]/70' : 'text-[var(--text-muted)]'}">
										{opt.desc}
									</span>
								</button>
							{/each}
						</div>
					</div>

					<!-- Actions footer -->
					<div class="flex items-center gap-3 px-5 py-3.5 border-t border-[var(--border)]/60 bg-[var(--bg-subtle)]/40">
						<button
							onclick={() => handleSubscriptionAction(project.git_identity, 'accept', dir)}
							disabled={isActing}
							class="flex items-center gap-2 px-5 py-2 text-sm font-medium rounded-[var(--radius-md)] bg-[var(--success)] text-white hover:bg-[var(--success)]/85 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
						>
							{#if isActing}
								<Loader2 size={14} class="animate-spin" />
								Accepting...
							{:else}
								<Check size={14} />
								Accept
							{/if}
						</button>
						<button
							onclick={() => handleSubscriptionAction(project.git_identity, 'decline')}
							disabled={isActing}
							class="flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-[var(--radius-md)] text-[var(--text-muted)] hover:text-[var(--error)] hover:bg-[var(--error)]/5 transition-colors disabled:opacity-50"
						>
							<X size={14} />
							Decline
						</button>
					</div>
				</div>
			{/each}
		</section>
	{/if}

	<!-- ═══════════════════════════════════════════════════════
	     Active Projects — accepted / paused / declined / no-sub
	     ═══════════════════════════════════════════════════════ -->

	<!-- Leader: Add Projects button -->
	{#if isLeader}
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
	{/if}

	{#if removeProjectError}
		<p class="text-xs text-[var(--error)]" aria-live="polite">{removeProjectError}</p>
	{/if}

	<!-- Active Projects header -->
	<div class="flex items-center justify-between px-5 py-3.5 border-b border-[var(--border-subtle)]">
		<div class="flex items-center gap-2">
			<h3 class="text-sm font-semibold text-[var(--text-primary)]">Active Projects</h3>
		</div>
		{#if totalTeamGap > 0}
			<button
				onclick={syncAllTeam}
				disabled={syncingAll}
				class="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-[var(--radius)] bg-[var(--accent)] text-white hover:bg-[var(--accent-hover)] transition-colors disabled:opacity-50"
			>
				{#if syncingAll}
					<Loader2 size={12} class="animate-spin" />
					Syncing...
				{:else}
					<RefreshCw size={12} />
					Sync All ({totalTeamGap})
				{/if}
			</button>
		{/if}
	</div>

	<div class="space-y-2">
		{#each activeProjects as project (project.git_identity)}
			{@const info = getProjectInfo(project)}
			{@const mySub = getMySubscription(project.git_identity)}
			{@const isActing = subscriptionActing === project.git_identity}
			{@const isDirActing = directionActing === project.git_identity}
			{@const ps = statusByGit.get(project.git_identity)}
			{@const hasSendSub = mySub?.status === 'accepted' && (mySub?.direction === 'send' || mySub?.direction === 'both')}

			<div class="p-4 rounded-[var(--radius-lg)] border border-[var(--border)] bg-[var(--bg-base)]">
				<!-- Project header -->
				<div class="flex items-center justify-between">
					<div class="flex items-center gap-3 min-w-0">
						<div class="w-8 h-8 rounded-lg bg-[var(--accent)]/8 flex items-center justify-center shrink-0">
							<FolderSync size={15} class="text-[var(--accent)]" />
						</div>
						<div class="min-w-0">
							{#if info.localEncodedName}
								<a
									href="/projects/{info.localEncodedName}"
									class="text-sm font-semibold text-[var(--text-primary)] hover:text-[var(--accent)] transition-colors truncate block"
								>
									{info.displayName}
								</a>
							{:else}
								<span class="text-sm font-semibold text-[var(--text-primary)] truncate block">
									{info.displayName}
								</span>
							{/if}
							<p class="text-[11px] font-mono text-[var(--text-faint)] mt-0.5 truncate">{info.path}</p>
						</div>
					</div>

					<div class="flex items-center gap-2 shrink-0">
						<!-- Project status badge -->
						<span class="px-2 py-0.5 text-[10px] font-medium rounded-full border
							{project.status === 'shared'
								? 'bg-[var(--success)]/8 text-[var(--success)] border-[var(--success)]/15'
								: 'bg-[var(--error)]/8 text-[var(--error)] border-[var(--error)]/15'}">
							{project.status}
						</span>

						<!-- Sync badge + button -->
						{#if ps && hasSendSub}
							{#if (ps.gap ?? 0) === 0}
								<span class="shrink-0 flex items-center gap-1 px-2 py-1 text-[11px] font-medium rounded-full bg-[var(--success)]/10 text-[var(--success)] border border-[var(--success)]/20">
									<CheckCircle2 size={11} />
									In Sync
								</span>
							{:else}
								<span class="shrink-0 flex items-center gap-1 px-2 py-1 text-[11px] font-medium rounded-full bg-[var(--warning)]/10 text-[var(--warning)] border border-[var(--warning)]/20">
									{ps.gap} ready to sync
								</span>
								<button
									onclick={() => syncProject(project.git_identity)}
									disabled={syncingProject === project.git_identity}
									class="shrink-0 p-1.5 rounded-[var(--radius)] text-[var(--text-muted)] hover:text-[var(--accent)] hover:bg-[var(--accent)]/10 transition-colors disabled:opacity-50"
									aria-label="Sync project"
								>
									{#if syncingProject === project.git_identity}
										<Loader2 size={14} class="animate-spin" />
									{:else}
										<RefreshCw size={14} />
									{/if}
								</button>
							{/if}
						{/if}

						<!-- Remove button (leader only) -->
						{#if isLeader && removeProjectConfirm === project.git_identity}
							<div class="flex items-center gap-1.5">
								<button
									onclick={() => handleRemoveProject(project.git_identity)}
									class="px-2 py-1 text-xs font-medium rounded-[var(--radius-sm)] bg-[var(--error)] text-white hover:bg-[var(--error)]/80 transition-colors"
								>
									Remove
								</button>
								<button
									onclick={() => (removeProjectConfirm = null)}
									class="px-2 py-1 text-xs rounded-[var(--radius-sm)] text-[var(--text-muted)] hover:bg-[var(--bg-muted)] transition-colors"
								>
									Cancel
								</button>
							</div>
						{:else if isLeader}
							<button
								onclick={() => (removeProjectConfirm = project.git_identity)}
								class="p-1.5 rounded-[var(--radius-sm)] text-[var(--text-muted)] hover:text-[var(--error)] hover:bg-[var(--error)]/8 transition-colors"
								title="Remove from team"
								aria-label="Remove project {info.displayName}"
							>
								<Trash2 size={14} />
							</button>
						{/if}
					</div>
				</div>

				<!-- Subscription row (for non-offered states) -->
				{#if mySub}
					<div class="flex items-center justify-between mt-3 pt-3 border-t border-[var(--border)]/40">
						<div class="flex items-center gap-2">
							<span class="text-[11px] text-[var(--text-muted)]">Sync:</span>
							<span class="px-2 py-0.5 text-[10px] font-medium rounded-full border
								{mySub.status === 'accepted' ? 'bg-[var(--success)]/8 text-[var(--success)] border-[var(--success)]/15'
								: mySub.status === 'paused' ? 'bg-[var(--warning)]/8 text-[var(--warning)] border-[var(--warning)]/15'
								: mySub.status === 'declined' ? 'bg-[var(--error)]/8 text-[var(--error)] border-[var(--error)]/15'
								: 'bg-[var(--bg-muted)] text-[var(--text-muted)] border-[var(--border)]'}">
								{mySub.status}
							</span>
							{#if mySub.status === 'accepted'}
								{@const DirIcon = directionIcon(mySub.direction)}
								<button
									onclick={() => handleDirectionChange(project.git_identity, cycleDirection(mySub.direction))}
									disabled={isDirActing}
									class="flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium rounded-full border border-[var(--accent)]/15 bg-[var(--accent)]/6 text-[var(--accent)] hover:bg-[var(--accent)]/12 transition-colors disabled:opacity-50"
									title="Click to change sync direction"
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

						<div class="flex items-center gap-1.5">
							{#if mySub.status === 'accepted'}
								<button
									onclick={() => handleSubscriptionAction(project.git_identity, 'pause')}
									disabled={isActing}
									class="flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-[var(--radius-md)] text-[var(--text-muted)] hover:text-[var(--warning)] hover:bg-[var(--warning)]/5 transition-colors disabled:opacity-50"
								>
									{#if isActing}<Loader2 size={11} class="animate-spin" />{:else}<Pause size={11} />{/if}
									Pause
								</button>
							{:else if mySub.status === 'paused'}
								<button
									onclick={() => handleSubscriptionAction(project.git_identity, 'resume')}
									disabled={isActing}
									class="flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-[var(--radius-md)] bg-[var(--success)] text-white hover:bg-[var(--success)]/85 transition-colors disabled:opacity-50"
								>
									{#if isActing}<Loader2 size={11} class="animate-spin" />{:else}<Play size={11} />{/if}
									Resume
								</button>
							{:else if mySub.status === 'declined'}
								<button
									onclick={() => handleSubscriptionAction(project.git_identity, 'accept', 'both')}
									disabled={isActing}
									class="flex items-center gap-1 px-2.5 py-1 text-xs font-medium rounded-[var(--radius-md)] bg-[var(--success)] text-white hover:bg-[var(--success)]/85 transition-colors disabled:opacity-50"
								>
									{#if isActing}<Loader2 size={11} class="animate-spin" />{:else}<Play size={11} />{/if}
									Re-accept
								</button>
							{/if}
						</div>
					</div>
				{/if}
			</div>
		{/each}

		{#if projects.length === 0}
			<div class="text-center py-12">
				<div class="w-12 h-12 mx-auto mb-3 rounded-xl bg-[var(--bg-muted)] flex items-center justify-center">
					<FolderSync size={20} class="text-[var(--text-muted)]" />
				</div>
				<p class="text-sm font-medium text-[var(--text-secondary)]">No projects shared yet</p>
				<p class="text-xs text-[var(--text-muted)] mt-1">
					{#if isLeader}
						Add projects to start syncing sessions with your team.
					{:else}
						The team leader hasn't shared any projects yet.
					{/if}
				</p>
			</div>
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
