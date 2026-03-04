<script lang="ts">
	import favicon from '$lib/assets/favicon.svg';
	import '../app.css';
	import Header from '$lib/components/Header.svelte';
	import CommandFooter from '$lib/components/CommandFooter.svelte';
	import CommandPalette from '$lib/components/command-palette/CommandPalette.svelte';
	import KeyboardShortcutsHelp from '$lib/components/KeyboardShortcutsHelp.svelte';
	import { globalKeyboard } from '$lib/actions/globalKeyboard';
	import { globalShortcuts } from '$lib/actions/globalShortcuts';
	import { navigating } from '$app/stores';
	import { registerWebMCPTools } from '$lib/webmcp';
	import {
		ProjectsPageSkeleton,
		ProjectDetailSkeleton,
		SessionDetailSkeleton,
		AgentSessionSkeleton,
		AnalyticsSkeleton,
		HistorySkeleton,
		SettingsSkeleton,
		AgentsPageSkeleton,
		AgentDetailSkeleton,
		PlansPageSkeleton,
		PlanDetailSkeleton,
		SessionsPageSkeleton,
		SkillsPageSkeleton,
		HooksPageSkeleton
	} from '$lib/components/skeleton';

	let { children } = $props();

	// Determine which skeleton to show based on navigation target
	// Skeleton shows only while actively navigating - no minimum display time
	// to prevent blocking content rendering during rapid navigation
	let navigationSkeletonType = $derived.by(() => {
		const nav = $navigating;
		if (!nav?.to?.url) return null;

		const path = nav.to.url.pathname;

		// Match routes to their skeletons
		if (path === '/projects') return 'projects';
		if (path === '/sessions') return 'sessions';
		if (path === '/analytics') return 'analytics';
		if (path === '/archived') return 'archived';
		if (path === '/settings') return 'settings';
		if (path === '/agents') return 'agents';
		if (path === '/skills') return 'skills';
		if (path === '/plans') return 'plans';
		// /plans/[slug] - plan detail (2 segments)
		if (path.startsWith('/plans/') && path.split('/').filter(Boolean).length === 2) {
			return 'plan-detail';
		}
		// /agents/[name] - agent detail (2 segments under /agents/)
		if (path.startsWith('/agents/') && path.split('/').filter(Boolean).length === 2)
			return 'agent-detail';
		// /projects/[project_slug]/[session_slug]/agents/[agent_id] - agent session detail
		// Must have 4+ segments: projects/slug/session/agents/id
		if (
			path.startsWith('/projects/') &&
			path.includes('/agents/') &&
			path.split('/').filter(Boolean).length >= 4
		) {
			return 'agent-session';
		}
		// /projects/[project_slug]/[session_slug] - session detail (3+ segments)
		if (path.startsWith('/projects/') && path.split('/').filter(Boolean).length >= 3) {
			return 'session-detail';
		}
		// /projects/[project_slug] - project detail (2 segments)
		if (path.startsWith('/projects/') && path.split('/').filter(Boolean).length === 2) {
			return 'project-detail';
		}
		if (path === '/hooks') return 'hooks';

		return null;
	});

	// Register WebMCP tools for AI agent access (Chrome 146+, no-op otherwise)
	$effect(() => {
		registerWebMCPTools();
	});

	// Keyboard help modal state
	let showKeyboardHelp = $state(false);

	// Theme toggle function (mirrors ThemeToggle.svelte logic)
	function toggleTheme() {
		const current = document.documentElement.getAttribute('data-theme');
		const newTheme = current === 'dark' ? 'light' : 'dark';
		document.documentElement.setAttribute('data-theme', newTheme);
		localStorage.setItem('theme', newTheme);
	}

	// Toggle keyboard help modal
	function toggleKeyboardHelp() {
		showKeyboardHelp = !showKeyboardHelp;
	}
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

<!-- Global keyboard listeners -->
<div
	use:globalKeyboard={{ onToggleHelp: toggleKeyboardHelp }}
	use:globalShortcuts={{ onToggleTheme: toggleTheme, onToggleHelp: toggleKeyboardHelp }}
	class="contents"
>
	<!-- Skip to main content link for keyboard users -->
	<a
		href="#main-content"
		class="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-[100] focus:px-4 focus:py-2 focus:bg-[var(--accent)] focus:text-white focus:rounded-lg focus:font-medium focus:shadow-lg"
	>
		Skip to main content
	</a>

	<div class="min-h-screen flex flex-col">
		<Header />
		<main
			id="main-content"
			class="flex-1 w-full max-w-[1200px] mx-auto px-6 py-8"
			tabindex="-1"
		>
			{#if navigationSkeletonType}
				<div role="status" aria-busy="true" aria-label="Loading page...">
					{#if navigationSkeletonType === 'projects'}
						<ProjectsPageSkeleton />
					{:else if navigationSkeletonType === 'project-detail'}
						<ProjectDetailSkeleton />
					{:else if navigationSkeletonType === 'agent-session'}
						<AgentSessionSkeleton />
					{:else if navigationSkeletonType === 'session-detail'}
						<SessionDetailSkeleton />
					{:else if navigationSkeletonType === 'analytics'}
						<AnalyticsSkeleton />
					{:else if navigationSkeletonType === 'history'}
						<HistorySkeleton />
					{:else if navigationSkeletonType === 'settings'}
						<SettingsSkeleton />
					{:else if navigationSkeletonType === 'agents'}
						<AgentsPageSkeleton />
					{:else if navigationSkeletonType === 'agent-detail'}
						<AgentDetailSkeleton />
					{:else if navigationSkeletonType === 'skills'}
						<SkillsPageSkeleton />
					{:else if navigationSkeletonType === 'plans'}
						<PlansPageSkeleton />
					{:else if navigationSkeletonType === 'plan-detail'}
						<PlanDetailSkeleton />
					{:else if navigationSkeletonType === 'sessions'}
						<SessionsPageSkeleton />
					{:else if navigationSkeletonType === 'hooks'}
						<HooksPageSkeleton />
					{/if}
				</div>
			{:else}
				{@render children()}
			{/if}
		</main>
		<CommandFooter onToggleHelp={toggleKeyboardHelp} />
	</div>

	<!-- Command Palette (global) - pass callbacks directly as props -->
	<CommandPalette onToggleTheme={toggleTheme} onToggleHelp={toggleKeyboardHelp} />

	<!-- Keyboard Shortcuts Help Modal -->
	<KeyboardShortcutsHelp bind:open={showKeyboardHelp} />
</div>
