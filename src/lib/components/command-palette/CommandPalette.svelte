<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { Command, Dialog } from 'bits-ui';
	import {
		Search,
		Home,
		FolderOpen,
		Bot,
		Zap,
		BarChart3,
		Settings,
		Folder,
		Clock,
		X,
		MessageSquare,
		Cable,
		Webhook,
		Calendar,
		Puzzle,
		Archive
	} from 'lucide-svelte';
	import { commandPalette } from '$lib/stores/commandPalette';
	import KeyIndicator from '$lib/components/ui/KeyIndicator.svelte';
	import type { Project } from '$lib/api-types';
	import { API_BASE } from '$lib/config';

	interface Props {
		onToggleTheme?: () => void;
		onToggleHelp?: () => void;
	}

	let { onToggleTheme, onToggleHelp }: Props = $props();

	// Subscribe to store
	let isOpen = $derived($commandPalette.isOpen);

	// Projects state
	let projects = $state<Project[]>([]);
	let projectsLoaded = $state(false);

	// Sessions state
	interface SessionItem {
		uuid: string;
		slug: string;
		title: string;
		initial_prompt?: string;
		project_name: string;
		project_slug?: string;
		start_time: string;
	}
	let sessions = $state<SessionItem[]>([]);
	let sessionsLoaded = $state(false);

	// Recent searches state
	interface RecentItem {
		id: string;
		label: string;
		path: string;
		icon:
			| 'home'
			| 'folder'
			| 'bot'
			| 'zap'
			| 'chart'
			| 'settings'
			| 'project'
			| 'session'
			| 'calendar'
			| 'archive'
			| 'puzzle';
	}

	const RECENT_STORAGE_KEY = 'claude-karma-recent-searches';
	const MAX_RECENT = 4;

	let recentItems = $state<RecentItem[]>([]);

	// Load recent items on mount
	onMount(() => {
		loadRecentItems();
	});

	function loadRecentItems() {
		try {
			const stored = localStorage.getItem(RECENT_STORAGE_KEY);
			if (stored) {
				recentItems = JSON.parse(stored);
			}
		} catch (e) {
			console.error('Failed to load recent searches:', e);
		}
	}

	function saveRecentItem(item: RecentItem) {
		// Remove if already exists
		const filtered = recentItems.filter((r) => r.id !== item.id);
		// Add to front
		const updated = [item, ...filtered].slice(0, MAX_RECENT);
		recentItems = updated;
		localStorage.setItem(RECENT_STORAGE_KEY, JSON.stringify(updated));
	}

	function removeRecentItem(id: string, e: Event) {
		e.stopPropagation();
		const updated = recentItems.filter((r) => r.id !== id);
		recentItems = updated;
		localStorage.setItem(RECENT_STORAGE_KEY, JSON.stringify(updated));
	}

	// Fetch projects when palette opens
	$effect(() => {
		if (isOpen && !projectsLoaded) {
			fetchProjects();
		}
	});

	async function fetchProjects() {
		try {
			const response = await fetch(`${API_BASE}/projects`);
			if (response.ok) {
				projects = await response.json();
				projectsLoaded = true;
			}
		} catch (error) {
			console.error('Failed to fetch projects for command palette:', error);
		}
	}

	$effect(() => {
		if (isOpen && !sessionsLoaded) {
			fetchSessions();
		}
	});

	async function fetchSessions() {
		try {
			const response = await fetch(`${API_BASE}/sessions/all?per_page=50`);
			if (response.ok) {
				const data = await response.json();
				sessions = (data.sessions ?? []).map((s: any) => ({
					uuid: s.uuid,
					slug: s.slug,
					title: s.session_titles?.[0] || s.chain_title || '',
					initial_prompt: s.initial_prompt,
					project_name: s.project_name || s.project_display_name || '',
					project_slug: s.project_slug || s.project_encoded_name || '',
					start_time: s.start_time
				}));
				sessionsLoaded = true;
			}
		} catch (error) {
			console.error('Failed to fetch sessions for command palette:', error);
		}
	}

	// Handle open state changes
	function handleOpenChange(open: boolean) {
		if (open) {
			commandPalette.open();
		} else {
			commandPalette.close();
		}
	}

	// Handle command selection - close palette, save to recent, and execute
	function handleSelect(callback: () => void, recentItem?: RecentItem) {
		commandPalette.close();
		if (recentItem) {
			saveRecentItem(recentItem);
		}
		callback();
	}

	// Get display name for project (last part of path)
	function getProjectDisplayName(project: Project): string {
		return project.path.split('/').pop() || project.path;
	}

	function getRelativeTime(dateStr: string): string {
		const diff = Date.now() - new Date(dateStr).getTime();
		const mins = Math.floor(diff / 60000);
		if (mins < 60) return `${mins}m ago`;
		const hours = Math.floor(mins / 60);
		if (hours < 24) return `${hours}h ago`;
		const days = Math.floor(hours / 24);
		return `${days}d ago`;
	}

	function getSessionLabel(s: SessionItem): string {
		return (
			s.title ||
			(s.initial_prompt ? s.initial_prompt.slice(0, 60) : (s.slug || '').slice(0, 8))
		);
	}
	// Handle keydown to ensure Escape always closes
	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			e.preventDefault();
			e.stopPropagation();
			commandPalette.close();
		}
	}
</script>

<Dialog.Root open={isOpen} onOpenChange={handleOpenChange}>
	<Dialog.Portal>
		<!-- Backdrop -->
		<Dialog.Overlay class="cmd-overlay" />

		<!-- Dialog Content -->
		<Dialog.Content class="cmd-dialog">
			<Dialog.Title class="sr-only">Command Menu</Dialog.Title>
			<Dialog.Description class="sr-only">Search and navigate</Dialog.Description>

			<div onkeydown={handleKeydown} role="presentation">
				<Command.Root class="cmd-root" shouldFilter={true}>
					<!-- Search Input -->
					<div class="cmd-search">
						<Search size={20} class="cmd-search-icon" />
						<Command.Input placeholder="Search..." class="cmd-input" />
						<KeyIndicator keys={['esc']} class="cmd-esc" />
					</div>

					<!-- Command List -->
					<Command.List class="cmd-list">
						<Command.Empty class="cmd-empty">No results found</Command.Empty>

						<!-- Recent -->
						{#if recentItems.length > 0}
							<Command.Group>
								<Command.GroupHeading class="cmd-heading"
									>Recent</Command.GroupHeading
								>
								<Command.GroupItems>
									{#each recentItems as item}
										<Command.Item
											value={`recent ${item.label} ${item.path}`}
											onSelect={() => handleSelect(() => goto(item.path))}
											class="cmd-item"
										>
											{#if item.icon === 'home'}<Home
													size={18}
													class="cmd-icon"
												/>
											{:else if item.icon === 'folder'}<FolderOpen
													size={18}
													class="cmd-icon"
												/>
											{:else if item.icon === 'bot'}<Bot
													size={18}
													class="cmd-icon"
												/>
											{:else if item.icon === 'zap'}<Zap
													size={18}
													class="cmd-icon"
												/>
											{:else if item.icon === 'chart'}<BarChart3
													size={18}
													class="cmd-icon"
												/>
											{:else if item.icon === 'settings'}<Settings
													size={18}
													class="cmd-icon"
												/>
											{:else if item.icon === 'project'}<Folder
													size={18}
													class="cmd-icon"
												/>
											{:else if item.icon === 'session'}<MessageSquare
													size={18}
													class="cmd-icon"
												/>
											{:else if item.icon === 'calendar'}<Calendar
													size={18}
													class="cmd-icon"
												/>
											{:else if item.icon === 'puzzle'}<Puzzle
													size={18}
													class="cmd-icon"
												/>
											{:else if item.icon === 'archive'}<Archive
													size={18}
													class="cmd-icon"
												/>
											{:else}<Clock size={18} class="cmd-icon" />
											{/if}
											<span class="cmd-label">{item.label}</span>
											<button
												class="cmd-remove"
												onclick={(e) => removeRecentItem(item.id, e)}
												title="Remove from recent"
											>
												<X size={14} />
											</button>
										</Command.Item>
									{/each}
								</Command.GroupItems>
							</Command.Group>
						{/if}

						<!-- Navigation -->
						<Command.Group>
							<Command.GroupHeading class="cmd-heading"
								>Navigation</Command.GroupHeading
							>
							<Command.GroupItems>
								<Command.Item
									value="Home dashboard"
									onSelect={() =>
										handleSelect(() => goto('/'), {
											id: 'nav-home',
											label: 'Home',
											path: '/',
											icon: 'home'
										})}
									class="cmd-item"
								>
									<Home size={18} class="cmd-icon" />
									<span class="cmd-label">Home</span>
									<KeyIndicator keys={['G', 'H']} class="cmd-shortcut" />
								</Command.Item>

								<Command.Item
									value="Projects folders"
									onSelect={() =>
										handleSelect(() => goto('/projects'), {
											id: 'nav-projects',
											label: 'Projects',
											path: '/projects',
											icon: 'folder'
										})}
									class="cmd-item"
								>
									<FolderOpen size={18} class="cmd-icon" />
									<span class="cmd-label">Projects</span>
									<KeyIndicator keys={['G', 'P']} class="cmd-shortcut" />
								</Command.Item>

								<Command.Item
									value="Plans tasks roadmap"
									onSelect={() =>
										handleSelect(() => goto('/plans'), {
											id: 'nav-plans',
											label: 'Plans',
											path: '/plans',
											icon: 'calendar'
										})}
									class="cmd-item"
								>
									<Calendar size={18} class="cmd-icon" />
									<span class="cmd-label">Plans</span>
								</Command.Item>

								<Command.Item
									value="Agents bots"
									onSelect={() =>
										handleSelect(() => goto('/agents'), {
											id: 'nav-agents',
											label: 'Agents',
											path: '/agents',
											icon: 'bot'
										})}
									class="cmd-item"
								>
									<Bot size={18} class="cmd-icon" />
									<span class="cmd-label">Agents</span>
									<KeyIndicator keys={['G', 'A']} class="cmd-shortcut" />
								</Command.Item>

								<Command.Item
									value="Skills abilities"
									onSelect={() =>
										handleSelect(() => goto('/skills'), {
											id: 'nav-skills',
											label: 'Skills',
											path: '/skills',
											icon: 'zap'
										})}
									class="cmd-item"
								>
									<Zap size={18} class="cmd-icon" />
									<span class="cmd-label">Skills</span>
									<KeyIndicator keys={['G', 'S']} class="cmd-shortcut" />
								</Command.Item>

								<Command.Item
									value="Tools MCP servers integrations"
									onSelect={() =>
										handleSelect(() => goto('/tools'), {
											id: 'nav-tools',
											label: 'Tools',
											path: '/tools',
											icon: 'zap'
										})}
									class="cmd-item"
								>
									<Cable size={18} class="cmd-icon" />
									<span class="cmd-label">Tools</span>
								</Command.Item>

								<Command.Item
									value="Hooks scripts interceptors"
									onSelect={() =>
										handleSelect(() => goto('/hooks'), {
											id: 'nav-hooks',
											label: 'Hooks',
											path: '/hooks',
											icon: 'zap'
										})}
									class="cmd-item"
								>
									<Webhook size={18} class="cmd-icon" />
									<span class="cmd-label">Hooks</span>
								</Command.Item>

								<Command.Item
									value="Plugins extensions"
									onSelect={() =>
										handleSelect(() => goto('/plugins'), {
											id: 'nav-plugins',
											label: 'Plugins',
											path: '/plugins',
											icon: 'zap'
										})}
									class="cmd-item"
								>
									<Puzzle size={18} class="cmd-icon" />
									<span class="cmd-label">Plugins</span>
								</Command.Item>

								<Command.Item
									value="Analytics stats"
									onSelect={() =>
										handleSelect(() => goto('/analytics'), {
											id: 'nav-analytics',
											label: 'Analytics',
											path: '/analytics',
											icon: 'chart'
										})}
									class="cmd-item"
								>
									<BarChart3 size={18} class="cmd-icon" />
									<span class="cmd-label">Analytics</span>
								</Command.Item>

								<Command.Item
									value="Archived history"
									onSelect={() =>
										handleSelect(() => goto('/archived'), {
											id: 'nav-archived',
											label: 'Archived',
											path: '/archived',
											icon: 'archive'
										})}
									class="cmd-item"
								>
									<Archive size={18} class="cmd-icon" />
									<span class="cmd-label">Archived</span>
								</Command.Item>

								<Command.Item
									value="Settings preferences"
									onSelect={() =>
										handleSelect(() => goto('/settings'), {
											id: 'nav-settings',
											label: 'Settings',
											path: '/settings',
											icon: 'settings'
										})}
									class="cmd-item"
								>
									<Settings size={18} class="cmd-icon" />
									<span class="cmd-label">Settings</span>
								</Command.Item>
							</Command.GroupItems>
						</Command.Group>

						<!-- Projects (dynamic) -->
						{#if projects.length > 0}
							<Command.Group>
								<Command.GroupHeading class="cmd-heading"
									>Projects</Command.GroupHeading
								>
								<Command.GroupItems>
									{#each projects as project}
										<Command.Item
											value={`${getProjectDisplayName(project)} ${project.path}`}
											onSelect={() =>
												handleSelect(
													() => goto(`/projects/${project.slug}`),
													{
														id: `project-${project.slug}`,
														label: getProjectDisplayName(project),
														path: `/projects/${project.slug}`,
														icon: 'project'
													}
												)}
											class="cmd-item"
										>
											<Folder size={18} class="cmd-icon" />
											<span class="cmd-label"
												>{getProjectDisplayName(project)}</span
											>
											<span class="cmd-meta"
												>{project.session_count} sessions</span
											>
										</Command.Item>
									{/each}
								</Command.GroupItems>
							</Command.Group>
						{/if}

						<!-- Sessions (dynamic) -->
						{#if sessions.length > 0}
							<Command.Group>
								<Command.GroupHeading class="cmd-heading"
									>Sessions</Command.GroupHeading
								>
								<Command.GroupItems>
									{#each sessions as session}
										<Command.Item
											value={`${getSessionLabel(session)} ${session.initial_prompt || ''} ${session.project_name}`}
											onSelect={() =>
												handleSelect(
													() =>
														goto(
															`/projects/${session.project_slug}/${session.slug}`
														),
													{
														id: `session-${session.slug}`,
														label: getSessionLabel(session),
														path: `/projects/${session.project_slug}/${session.slug}`,
														icon: 'session'
													}
												)}
											class="cmd-item"
										>
											<MessageSquare size={18} class="cmd-icon" />
											<div class="flex flex-col flex-1 min-w-0">
												<span class="cmd-label truncate"
													>{getSessionLabel(session)}</span
												>
												<span
													class="text-[10px] text-[var(--text-faint)] truncate"
													>{session.project_name}</span
												>
											</div>
											<span class="cmd-meta"
												>{getRelativeTime(session.start_time)}</span
											>
										</Command.Item>
									{/each}
								</Command.GroupItems>
							</Command.Group>
						{/if}
					</Command.List>
				</Command.Root>
			</div>
		</Dialog.Content>
	</Dialog.Portal>
</Dialog.Root>

<style>
	:global(.cmd-overlay) {
		position: fixed;
		inset: 0;
		z-index: 9998;
		background: rgba(0, 0, 0, 0.6);
		backdrop-filter: blur(8px);
		animation: fadeIn 150ms ease-out;
	}

	:global(.cmd-dialog) {
		position: fixed;
		left: 50%;
		top: 12vh;
		z-index: 9999;
		width: calc(100% - 2rem);
		max-width: 640px;
		transform: translateX(-50%);
		background: var(--bg-base);
		border: 1px solid var(--border);
		border-radius: 1rem;
		overflow: hidden;
		box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.4);
		animation: scaleIn 150ms cubic-bezier(0.16, 1, 0.3, 1);
	}

	:global(.cmd-dialog:focus) {
		outline: none;
	}

	:global(.cmd-root) {
		display: flex;
		flex-direction: column;
	}

	/* Search */
	.cmd-search {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 1rem 1.25rem;
		border-bottom: 1px solid var(--border);
	}

	:global(.cmd-search-icon) {
		color: var(--accent);
		flex-shrink: 0;
	}

	:global(.cmd-input) {
		flex: 1;
		font-size: 1.125rem;
		font-weight: 500;
		background: transparent;
		color: var(--text-primary);
		border: none;
		outline: none;
		box-shadow: none;
	}

	:global(.cmd-input::placeholder) {
		color: var(--text-faint);
	}

	:global(.cmd-input:focus) {
		outline: none;
		box-shadow: none;
		border: none;
	}

	:global(.cmd-input:focus-visible) {
		outline: none;
		box-shadow: none;
	}

	/* Extra aggressive - target any input in the search area */
	.cmd-search :global(input),
	.cmd-search :global(input:focus),
	.cmd-search :global(input:focus-visible),
	.cmd-search :global([cmdk-input]),
	.cmd-search :global([cmdk-input]:focus) {
		outline: none !important;
		box-shadow: none !important;
		border: none !important;
	}

	:global(.cmd-esc) {
		flex-shrink: 0;
		opacity: 0.5;
	}

	/* List */
	:global(.cmd-list) {
		max-height: 400px;
		overflow-y: auto;
		padding: 0.75rem;
	}

	:global(.cmd-empty) {
		padding: 3rem 1rem;
		text-align: center;
		font-size: 0.9375rem;
		color: var(--text-muted);
	}

	/* Heading */
	:global(.cmd-heading) {
		padding: 0.75rem 0.75rem 0.5rem;
		font-size: 0.6875rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--accent);
	}

	/* Item */
	:global(.cmd-item) {
		display: flex;
		align-items: center;
		gap: 0.875rem;
		padding: 0.875rem 0.75rem;
		border-radius: 0.5rem;
		cursor: pointer;
		transition: background-color 100ms ease;
	}

	:global(.cmd-item:hover),
	:global(.cmd-item[data-selected='true']) {
		background: var(--bg-subtle);
	}

	:global(.cmd-item[data-selected='true']) {
		background: var(--accent-subtle);
	}

	:global(.cmd-icon) {
		color: var(--text-muted);
		flex-shrink: 0;
	}

	:global(.cmd-item[data-selected='true'] .cmd-icon) {
		color: var(--accent);
	}

	:global(.cmd-label) {
		flex: 1;
		font-size: 0.9375rem;
		font-weight: 500;
		color: var(--text-primary);
	}

	:global(.cmd-shortcut) {
		opacity: 0.5;
		flex-shrink: 0;
	}

	:global(.cmd-item[data-selected='true'] .cmd-shortcut) {
		opacity: 0.8;
	}

	:global(.cmd-meta) {
		font-size: 0.75rem;
		color: var(--text-faint);
		flex-shrink: 0;
	}

	@keyframes fadeIn {
		from {
			opacity: 0;
		}
		to {
			opacity: 1;
		}
	}

	@keyframes scaleIn {
		from {
			opacity: 0;
			transform: translateX(-50%) scale(0.96) translateY(-8px);
		}
		to {
			opacity: 1;
			transform: translateX(-50%) scale(1) translateY(0);
		}
	}
</style>
