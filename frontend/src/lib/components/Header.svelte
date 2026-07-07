<script lang="ts">
	import { page } from '$app/stores';
	import { Menu, X, ChevronDown, Settings, Info } from 'lucide-svelte';
	import Icon from '$lib/components/icons/Icon.svelte';

	let mobileMenuOpen = $state(false);
	let openGroup = $state<string | null>(null);

	let isHome = $derived($page.url.pathname === '/');
	let currentPath = $derived($page.url.pathname);

	interface NavItem {
		href: string;
		label: string;
		icon: string;
		color: string;
	}

	interface NavGroup {
		id: string;
		label: string;
		items: NavItem[];
	}

	const NAV_GROUPS: NavGroup[] = [
		{
			id: 'monitor',
			label: 'Monitor',
			items: [
				{ href: '/projects',  label: 'Projects',  icon: 'projects',  color: 'blue'  },
				{ href: '/sessions',  label: 'Sessions',  icon: 'sessions',  color: 'teal'  },
				{ href: '/analytics', label: 'Analytics', icon: 'analytics', color: 'green' },
				{ href: '/archived',  label: 'Archived',  icon: 'archived',  color: 'gray'  },
			]
		},
		{
			id: 'automate',
			label: 'Automate',
			items: [
				{ href: '/agents',   label: 'Agents',   icon: 'agents',   color: 'purple' },
				{ href: '/skills',   label: 'Skills',   icon: 'skills',   color: 'orange' },
				{ href: '/mcp',    label: 'MCP',      icon: 'tools',    color: 'indigo' },
				{ href: '/commands', label: 'Commands', icon: 'commands', color: 'red'    },
				{ href: '/hooks',    label: 'Hooks',    icon: 'hooks',    color: 'cyan'   },
				{ href: '/cron',     label: 'Cron',     icon: 'cron',     color: 'yellow' },
			]
		},
		{
			id: 'manage',
			label: 'Manage',
			items: [
				{ href: '/plans',   label: 'Plans',   icon: 'plans',   color: 'amber'  },
				{ href: '/tickets', label: 'Tickets', icon: 'tickets', color: 'amber'  },
				{ href: '/plugins', label: 'Plugins', icon: 'plugins', color: 'violet' },
				{ href: '/shells',  label: 'Shells',  icon: 'shells',  color: 'green'  },
				{ href: '/memory',  label: 'Memory',  icon: 'memory',  color: 'blue'   },
			]
		},
	];

	function activeGroup(pathname: string): NavGroup | null {
		return NAV_GROUPS.find(g => g.items.some(i => pathname.startsWith(i.href))) ?? null;
	}

	function activeItem(pathname: string): NavItem | null {
		for (const g of NAV_GROUPS) {
			const found = g.items.find(i => pathname.startsWith(i.href));
			if (found) return found;
		}
		return null;
	}

	function toggleGroup(id: string) {
		openGroup = openGroup === id ? null : id;
	}

	function closeDropdowns() {
		openGroup = null;
	}

	function toggleMobileMenu() {
		mobileMenuOpen = !mobileMenuOpen;
	}

	function closeMobileMenu() {
		mobileMenuOpen = false;
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			openGroup = null;
			mobileMenuOpen = false;
		}
	}

	// Close dropdown when route changes
	$effect(() => {
		currentPath;
		openGroup = null;
		mobileMenuOpen = false;
	});
</script>

<svelte:window onkeydown={handleKeydown} />

<!-- Click-outside overlay (invisible) -->
{#if openGroup}
	<div
		class="fixed inset-0 z-40"
		onclick={closeDropdowns}
		role="presentation"
	></div>
{/if}

{#if !isHome}
	<header class="sticky top-0 z-50 bg-[var(--bg-base)]/95 backdrop-blur-md border-b border-[var(--border)] h-14 flex items-center">
		<div class="w-full max-w-[1200px] mx-auto px-4 md:px-6 grid grid-cols-[1fr_auto_1fr] items-center">

			<!-- Left: Brand -->
			<a href="/" class="flex items-center gap-2 hover:opacity-80 transition-opacity">
				<div class="logo-wrap">
					<img src="/logo.png" alt="Claude Code Karma" class="w-7 h-7 object-contain" />
				</div>
				<span class="hidden sm:block text-sm font-semibold tracking-tight text-[var(--text-primary)]">
					Claude <span class="font-bold">Code Karma</span>
				</span>
			</a>

			<!-- Centre: Desktop grouped nav -->
			<nav class="hidden md:flex items-center gap-1" aria-label="Main navigation">
				{#each NAV_GROUPS as group (group.id)}
					{@const grpActive = activeGroup(currentPath)?.id === group.id}
					{@const isOpen = openGroup === group.id}
					{@const activeItm = grpActive ? activeItem(currentPath) : null}

					<div class="relative">
						<!-- Group trigger -->
						<button
							onclick={() => toggleGroup(group.id)}
							aria-expanded={isOpen}
							aria-haspopup="true"
							class="group-btn {grpActive ? 'group-btn--active' : ''} {isOpen ? 'group-btn--open' : ''}"
							style={grpActive && activeItm
								? `background-color: var(--nav-${activeItm.color}-subtle); color: var(--nav-${activeItm.color});`
								: ''}
						>
							{#if grpActive && activeItm}
								<span class="group-btn-icon">
									<Icon name={activeItm.icon} size={14} strokeWidth={1.5} />
								</span>
								<span class="group-btn-label">{activeItm.label}</span>
							{:else}
								<span class="group-btn-label">{group.label}</span>
							{/if}
							<ChevronDown size={12} class="chevron {isOpen ? 'chevron--open' : ''}" />
						</button>

						<!-- Dropdown panel -->
						{#if isOpen}
							<div class="dropdown" role="menu">
								<div class="dropdown-header">{group.label}</div>
								{#each group.items as item (item.href)}
									{@const itemActive = currentPath.startsWith(item.href)}
									<a
										href={item.href}
										role="menuitem"
										onclick={closeDropdowns}
										class="dropdown-item {itemActive ? 'dropdown-item--active' : ''}"
										style={itemActive
											? `background-color: var(--nav-${item.color}-subtle); color: var(--nav-${item.color});`
											: ''}
									>
										<span
											class="dropdown-item-icon"
											style="background-color: var(--nav-{item.color}-subtle); color: var(--nav-{item.color});"
										>
											<Icon name={item.icon} size={15} strokeWidth={1.5} />
										</span>
										<span class="dropdown-item-label">{item.label}</span>
										{#if itemActive}
											<span class="dropdown-item-dot"></span>
										{/if}
									</a>
								{/each}
							</div>
						{/if}
					</div>
				{/each}
			</nav>

			<!-- Right: settings + mobile toggle -->
			<div class="flex items-center gap-1 justify-end">
				<a
					href="/about"
					class="hidden md:flex p-2 rounded-lg hover:bg-[var(--bg-muted)] transition-colors text-[var(--text-muted)] hover:text-[var(--text-primary)]"
					title="About"
					aria-label="About"
				>
					<Info size={17} strokeWidth={1.75} />
				</a>
				<a
					href="/settings"
					class="p-2 rounded-lg hover:bg-[var(--bg-muted)] transition-colors text-[var(--text-muted)] hover:text-[var(--text-primary)]"
					title="Settings"
					aria-label="Settings"
				>
					<Settings size={17} strokeWidth={1.75} />
				</a>
				<button
					onclick={toggleMobileMenu}
					class="md:hidden p-2 rounded-lg hover:bg-[var(--bg-muted)] transition-colors text-[var(--text-muted)]"
					aria-label="Toggle menu"
				>
					{#if mobileMenuOpen}<X size={20} strokeWidth={2} />{:else}<Menu size={20} strokeWidth={2} />{/if}
				</button>
			</div>
		</div>
	</header>

	<!-- Mobile full-screen menu -->
	{#if mobileMenuOpen}
		<div class="fixed inset-0 top-14 z-40 bg-[var(--bg-base)]/98 backdrop-blur-md md:hidden overflow-y-auto">
			<nav class="flex flex-col p-5 gap-6" aria-label="Mobile navigation">
				{#each NAV_GROUPS as group (group.id)}
					<div>
						<div class="mobile-group-label">{group.label}</div>
						<div class="mobile-group-items">
							{#each group.items as item (item.href)}
								{@const itemActive = currentPath.startsWith(item.href)}
								<a
									href={item.href}
									onclick={closeMobileMenu}
									class="mobile-item {itemActive ? 'mobile-item--active' : ''}"
									style={itemActive ? `background-color: var(--nav-${item.color}-subtle);` : ''}
								>
									<span
										class="mobile-item-icon"
										style="background-color: var(--nav-{item.color}-subtle); color: var(--nav-{item.color});"
									>
										<Icon name={item.icon} size={18} strokeWidth={1.5} />
									</span>
									<span
										class="mobile-item-text"
										style={itemActive ? `color: var(--nav-${item.color});` : ''}
									>{item.label}</span>
								</a>
							{/each}
						</div>
					</div>
				{/each}

				<div>
					<div class="mobile-group-label">System</div>
					<div class="mobile-group-items">
						<a href="/settings" onclick={closeMobileMenu} class="mobile-item">
							<span class="mobile-item-icon" style="background-color: var(--nav-indigo-subtle); color: var(--nav-indigo);">
								<Settings size={18} strokeWidth={1.75} />
							</span>
							<span class="mobile-item-text">Settings</span>
						</a>
						<a href="/about" onclick={closeMobileMenu} class="mobile-item">
							<span class="mobile-item-icon" style="background-color: var(--bg-muted); color: var(--text-muted);">
								<Info size={18} strokeWidth={1.75} />
							</span>
							<span class="mobile-item-text">About</span>
						</a>
					</div>
				</div>
			</nav>
		</div>
	{/if}
{/if}

<style>
	/* ── Logo ───────────────────────────────────────────────────────────────── */
	.logo-wrap {
		width: 2.25rem;
		height: 2.25rem;
		border-radius: 50%;
		background: radial-gradient(circle, #2d2240 55%, transparent 100%);
		display: flex;
		align-items: center;
		justify-content: center;
	}

	/* ── Group trigger button ───────────────────────────────────────────────── */
	.group-btn {
		display: inline-flex;
		align-items: center;
		gap: 5px;
		height: 32px;
		padding: 0 10px;
		border: none;
		border-radius: 8px;
		background: transparent;
		color: var(--text-muted);
		font-size: 13px;
		font-weight: 500;
		cursor: pointer;
		transition: background 100ms, color 100ms;
		white-space: nowrap;
	}

	.group-btn:hover {
		background: var(--bg-subtle);
		color: var(--text-primary);
	}

	.group-btn--active {
		font-weight: 600;
		padding: 0 10px;
	}

	.group-btn--open {
		background: var(--bg-subtle);
		color: var(--text-primary);
	}

	.group-btn-icon {
		display: flex;
		align-items: center;
	}

	.group-btn-label {
		line-height: 1;
	}

	:global(.chevron) {
		color: var(--text-faint);
		transition: transform 150ms;
		flex-shrink: 0;
	}

	:global(.chevron--open) {
		transform: rotate(180deg);
	}

	/* ── Dropdown panel ─────────────────────────────────────────────────────── */
	.dropdown {
		position: absolute;
		top: calc(100% + 6px);
		left: 50%;
		transform: translateX(-50%);
		min-width: 180px;
		background: var(--bg-base);
		border: 1px solid var(--border);
		border-radius: 10px;
		box-shadow: 0 8px 24px -4px rgba(0, 0, 0, 0.12), 0 2px 8px -2px rgba(0, 0, 0, 0.08);
		padding: 5px;
		z-index: 50;
	}

	.dropdown-header {
		font-size: 10px;
		font-weight: 700;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		color: var(--text-faint);
		padding: 4px 10px 6px;
	}

	.dropdown-item {
		display: flex;
		align-items: center;
		gap: 9px;
		padding: 7px 9px;
		border-radius: 7px;
		text-decoration: none;
		color: var(--text-primary);
		font-size: 13px;
		font-weight: 500;
		transition: background 80ms;
	}

	.dropdown-item:hover {
		background: var(--bg-subtle);
	}

	.dropdown-item--active {
		font-weight: 600;
	}

	.dropdown-item-icon {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 26px;
		height: 26px;
		border-radius: 6px;
		flex-shrink: 0;
	}

	.dropdown-item-label {
		flex: 1;
	}

	.dropdown-item-dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: currentColor;
		opacity: 0.6;
		flex-shrink: 0;
	}

	/* ── Mobile menu ────────────────────────────────────────────────────────── */
	.mobile-group-label {
		font-size: 10px;
		font-weight: 700;
		letter-spacing: 0.12em;
		text-transform: uppercase;
		color: var(--text-faint);
		padding: 0 4px;
		margin-bottom: 6px;
	}

	.mobile-group-items {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.mobile-item {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 9px 10px;
		border-radius: 8px;
		text-decoration: none;
		transition: background 80ms;
	}

	.mobile-item:hover {
		background: var(--bg-subtle);
	}

	.mobile-item--active {
		background: var(--bg-subtle);
	}

	.mobile-item-icon {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 30px;
		height: 30px;
		border-radius: 7px;
		flex-shrink: 0;
	}

	.mobile-item-text {
		font-size: 14px;
		font-weight: 500;
		color: var(--text-primary);
	}
</style>
