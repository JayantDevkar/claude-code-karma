<script lang="ts">
	import { onMount } from 'svelte';
	import { FolderGit2, FileText, Loader2, ChevronDown, ChevronRight } from 'lucide-svelte';
	import { API_BASE } from '$lib/config';
	import { formatRelativeTime, formatBytes, getProjectNameFromEncoded } from '$lib/utils';
	import type { MemberProfile } from '$lib/api-types';

	interface Props {
		profile: MemberProfile;
	}

	interface RemoteProject {
		encoded_name: string;
		session_count: number;
		synced_at: string | null;
		machine_id: string | null;
	}

	interface RemoteSessionItem {
		uuid: string;
		mtime: string;
		size_bytes: number;
		worktree_name: string | null;
	}

	let { profile }: Props = $props();

	// Build a lookup from profile's team projects (which have proper names from the API)
	let projectNames = $derived.by(() => {
		const map = new Map<string, string>();
		for (const team of profile.teams) {
			for (const p of team.projects) {
				if (!map.has(p.encoded_name)) {
					map.set(p.encoded_name, p.name);
				}
			}
		}
		return map;
	});

	function getDisplayName(encodedName: string): string {
		return projectNames.get(encodedName) || getProjectNameFromEncoded(encodedName);
	}

	let projects = $state<RemoteProject[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let expandedProjects = $state(new Set<string>());
	let sessionCache = $state<Record<string, RemoteSessionItem[]>>({});
	let loadingSessions = $state(new Set<string>());

	let totalSessions = $derived(projects.reduce((sum, p) => sum + p.session_count, 0));

	async function fetchProjects() {
		loading = true;
		error = null;
		try {
			const res = await fetch(
				`${API_BASE}/remote/users/${encodeURIComponent(profile.user_id)}/projects`
			);
			if (!res.ok) {
				error = `Failed to load projects (${res.status})`;
				return;
			}
			projects = await res.json();
		} catch {
			error = 'Network error loading projects';
		} finally {
			loading = false;
		}
	}

	async function fetchSessions(encodedName: string) {
		if (sessionCache[encodedName]) return;

		const next = new Set(loadingSessions);
		next.add(encodedName);
		loadingSessions = next;

		try {
			const res = await fetch(
				`${API_BASE}/remote/users/${encodeURIComponent(profile.user_id)}/projects/${encodeURIComponent(encodedName)}/sessions`
			);
			if (res.ok) {
				const data: RemoteSessionItem[] = await res.json();
				sessionCache = { ...sessionCache, [encodedName]: data };
			}
		} catch {
			// silently fail — user can collapse and re-expand
		} finally {
			const updated = new Set(loadingSessions);
			updated.delete(encodedName);
			loadingSessions = updated;
		}
	}

	function toggleProject(encodedName: string) {
		const next = new Set(expandedProjects);
		if (next.has(encodedName)) {
			next.delete(encodedName);
		} else {
			next.add(encodedName);
			fetchSessions(encodedName);
		}
		expandedProjects = next;
	}

	onMount(() => {
		fetchProjects();
	});
</script>

<div class="space-y-4">
	{#if loading}
		<div class="flex items-center justify-center py-12">
			<Loader2 size={20} class="animate-spin text-[var(--text-muted)]" />
		</div>
	{:else if error}
		<p class="text-sm text-[var(--error)] py-8 text-center">{error}</p>
	{:else if projects.length === 0}
		<p class="text-sm text-[var(--text-muted)] py-8 text-center">
			No synced sessions from this member yet.
		</p>
	{:else}
		<!-- Summary -->
		<p class="text-sm text-[var(--text-secondary)]">
			{totalSessions} session{totalSessions === 1 ? '' : 's'} across {projects.length} project{projects.length === 1 ? '' : 's'}
		</p>

		<!-- Project cards -->
		<div class="space-y-2">
			{#each projects as project (project.encoded_name)}
				{@const isExpanded = expandedProjects.has(project.encoded_name)}
				{@const isLoadingSessions = loadingSessions.has(project.encoded_name)}
				{@const sessions = sessionCache[project.encoded_name]}

				<div class="rounded-lg border border-[var(--border)] bg-[var(--bg-base)] overflow-hidden">
					<!-- Project header (clickable) -->
					<button
						onclick={() => toggleProject(project.encoded_name)}
						class="w-full flex items-center justify-between p-4 text-left hover:bg-[var(--bg-muted)]/50 transition-colors"
					>
						<div class="flex items-center gap-3 min-w-0">
							<FolderGit2 size={16} class="text-[var(--text-muted)] shrink-0" />
							<div class="min-w-0">
								<span class="text-sm font-medium text-[var(--text-primary)] truncate block">
									{getDisplayName(project.encoded_name)}
								</span>
								{#if project.synced_at}
									<span class="text-[11px] text-[var(--text-muted)]">
										Synced {formatRelativeTime(project.synced_at)}
									</span>
								{/if}
							</div>
						</div>
						<div class="flex items-center gap-2 shrink-0">
							<span class="text-xs text-[var(--text-muted)]">
								{project.session_count} session{project.session_count === 1 ? '' : 's'}
							</span>
							{#if isExpanded}
								<ChevronDown size={14} class="text-[var(--text-muted)]" />
							{:else}
								<ChevronRight size={14} class="text-[var(--text-muted)]" />
							{/if}
						</div>
					</button>

					<!-- Expanded session list -->
					{#if isExpanded}
						<div class="border-t border-[var(--border)]">
							{#if isLoadingSessions}
								<div class="flex items-center justify-center py-6">
									<Loader2 size={16} class="animate-spin text-[var(--text-muted)]" />
								</div>
							{:else if sessions && sessions.length > 0}
								<div class="divide-y divide-[var(--border)]">
									{#each sessions as session (session.uuid)}
										<a
											href="/sessions/{session.uuid}?project={project.encoded_name}&source=remote&user={profile.user_id}"
											class="flex items-center justify-between px-4 py-3 hover:bg-[var(--bg-muted)]/50 transition-colors"
										>
											<div class="flex items-center gap-3 min-w-0">
												<FileText size={14} class="text-[var(--text-muted)] shrink-0" />
												<div class="flex items-center gap-2 min-w-0">
													<span class="text-sm font-mono text-[var(--text-primary)]">
														{session.uuid.slice(0, 8)}
													</span>
													{#if session.worktree_name}
														<span class="px-1.5 py-0.5 text-[10px] font-medium rounded bg-[var(--accent)]/10 text-[var(--accent)] border border-[var(--accent)]/20">
															{session.worktree_name}
														</span>
													{/if}
												</div>
											</div>
											<div class="flex items-center gap-3 text-xs text-[var(--text-muted)] shrink-0">
												<span>{formatBytes(session.size_bytes)}</span>
												<span>{formatRelativeTime(session.mtime)}</span>
											</div>
										</a>
									{/each}
								</div>
							{:else if sessions}
								<p class="text-xs text-[var(--text-muted)] py-4 text-center">
									No sessions found
								</p>
							{/if}
						</div>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</div>
