<script lang="ts">
	import type { ComponentType } from 'svelte';
	import { page } from '$app/stores';
	import {
		Menu,
		X,
		Settings,
		FolderOpen,
		MessageSquare,
		Ticket,
		FileText,
		Bot,
		Wrench,
		Terminal,
		Cable,
		Webhook,
		Puzzle,
		LineChart,
		History
	} from 'lucide-svelte';
	import LogoIcon from '$lib/assets/LogoIcon.svelte';

	let mobileMenuOpen = $state(false);

	let isHome = $derived($page.url.pathname === '/');

	/**
	 * Single source of truth for top navigation. Each item carries the
	 * lucide icon used on its homepage NavigationCard and the brand color
	 * token name so the active pill matches the user's mental map from the
	 * homepage. Items render icon-only (with `title` tooltip) when inactive
	 * and expand to icon+label in a brand-tinted pill when active.
	 */
	interface NavItem {
		href: string;
		label: string;
		icon: ComponentType;
		color: string; // matches --nav-{color} and --nav-{color}-subtle in app.css
	}

	const NAV_ITEMS: NavItem[] = [
		{ href: '/projects', label: 'Projects', icon: FolderOpen, color: 'blue' },
		{ href: '/sessions', label: 'Sessions', icon: MessageSquare, color: 'teal' },
		{ href: '/tickets', label: 'Tickets', icon: Ticket, color: 'amber' },
		{ href: '/plans', label: 'Plans', icon: FileText, color: 'yellow' },
		{ href: '/agents', label: 'Agents', icon: Bot, color: 'purple' },
		{ href: '/skills', label: 'Skills', icon: Wrench, color: 'orange' },
		{ href: '/commands', label: 'Commands', icon: Terminal, color: 'red' },
		{ href: '/tools', label: 'Tools', icon: Cable, color: 'teal' },
		{ href: '/hooks', label: 'Hooks', icon: Webhook, color: 'amber' },
		{ href: '/plugins', label: 'Plugins', icon: Puzzle, color: 'violet' },
		{ href: '/analytics', label: 'Analytics', icon: LineChart, color: 'green' },
		{ href: '/archived', label: 'Archived', icon: History, color: 'gray' }
	];

	let currentPath = $derived($page.url.pathname);

	function isActive(href: string, pathname: string): boolean {
		return pathname.startsWith(href);
	}

	function toggleMobileMenu() {
		mobileMenuOpen = !mobileMenuOpen;
	}

	function closeMobileMenu() {
		mobileMenuOpen = false;
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape' && mobileMenuOpen) {
			closeMobileMenu();
		}
	}
</script>

<svelte:window onkeydown={handleKeydown} />

{#if isHome}
	<!-- Big Centered Header (Home) -->
	<header
		class="w-full max-w-[1000px] mx-auto pt-8 sm:pt-12 md:pt-16 pb-6 md:pb-8 px-4 flex items-center justify-center relative"
	>
		<div class="flex flex-col items-center gap-4 md:gap-5">
			<div class="logo-wrapper logo-wrapper-lg">
				<img src="/logo.png" alt="Claude Code Karma" class="w-16 h-16 md:w-20 md:h-20 object-contain" />
			</div>
			<div class="text-center flex flex-col items-center gap-1">
				<h1
					class="text-2xl sm:text-3xl font-semibold tracking-tight text-[var(--text-primary)]"
				>
					Claude <span class="font-bold">Code Karma</span>
				</h1>
				<p
					class="mt-1 text-sm tracking-wide"
					style="background: linear-gradient(135deg, #a855f7, #7c3aed); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;"
				>
					Track work, not terminals
				</p>
			</div>
		</div>
	</header>
{:else}
	<!-- Compact Inline Header (Routes) -->
	<header
		class="sticky top-0 z-50 bg-[var(--bg-base)]/90 backdrop-blur-md border-b border-[var(--border)] h-14 flex items-center"
	>
		<div
			class="w-full max-w-[1200px] mx-auto px-4 md:px-6 grid grid-cols-[auto_1fr_auto] items-center"
		>
			<!-- Left: Brand -->
			<div class="flex items-center gap-3">
				<a
					href="/"
					class="flex items-center gap-2 md:gap-3 hover:opacity-80 transition-opacity group"
				>
					<div class="logo-wrapper logo-wrapper-sm">
						<img src="/logo.png" alt="Claude Code Karma" class="w-7 h-7 object-contain" />
					</div>
					<h1
						class="hidden sm:block text-sm font-semibold tracking-tight text-[var(--text-primary)]"
					>
						Claude <span class="font-bold">Code Karma</span>
					</h1>
				</a>
			</div>

			<!-- Center: Desktop Navigation (icon-first compact)
				 Direction C from design brief 2026-05-19. Icons only when
				 inactive; icon + label in a brand-tinted pill when active.
				 `title` provides the tooltip on hover. Each item's color
				 mirrors its homepage NavigationCard color for continuity. -->
			<nav
				class="hidden md:flex items-center justify-center gap-0.5"
				aria-label="Main navigation"
			>
				{#each NAV_ITEMS as item (item.href)}
					{@const active = isActive(item.href, currentPath)}
					{@const Icon = item.icon}
					<a
						href={item.href}
						title={item.label}
						aria-label={item.label}
						aria-current={active ? 'page' : undefined}
						class="relative inline-flex items-center gap-1.5 rounded-lg transition-colors focus-ring
							{active
								? 'px-2.5 py-1.5'
								: 'p-2 text-[var(--text-muted)] hover:text-[var(--text-primary)]'}"
						style={active
							? `background-color: var(--nav-${item.color}-subtle); color: var(--nav-${item.color});`
							: ''}
					>
						<Icon class="size-4" />
						{#if active}
							<span
								class="text-[12.5px] font-medium text-[var(--text-primary)] whitespace-nowrap"
							>
								{item.label}
							</span>
						{/if}
					</a>
				{/each}
			</nav>

			<div class="flex items-center justify-end gap-3">
				<a
					href="/settings"
					class="p-2 rounded-lg hover:bg-[var(--bg-muted)] transition-colors text-[var(--text-muted)] hover:text-[var(--text-primary)]"
					title="Settings"
					aria-label="Settings"
					aria-current={currentPath.startsWith('/settings') ? 'page' : undefined}
				>
					<Settings size={18} strokeWidth={2} />
				</a>

				<!-- Mobile Menu Button - visible only on mobile -->
				<button
					onclick={toggleMobileMenu}
					class="md:hidden p-2 rounded-lg hover:bg-[var(--bg-muted)] transition-colors text-[var(--text-muted)]"
					aria-label="Toggle menu"
				>
					{#if mobileMenuOpen}
						<X size={20} strokeWidth={2} />
					{:else}
						<Menu size={20} strokeWidth={2} />
					{/if}
				</button>
			</div>
		</div>
	</header>

	<!-- Mobile Menu Overlay -->
	{#if mobileMenuOpen}
		<div
			class="fixed inset-0 top-14 z-40 bg-[var(--bg-base)]/95 backdrop-blur-md md:hidden"
			onclick={closeMobileMenu}
			role="presentation"
		>
			<nav class="flex flex-col p-6 gap-1" aria-label="Mobile navigation">
				{#each NAV_ITEMS as item (item.href)}
					{@const active = isActive(item.href, currentPath)}
					{@const Icon = item.icon}
					<a
						href={item.href}
						onclick={closeMobileMenu}
						aria-current={active ? 'page' : undefined}
						class="flex items-center gap-3 text-base font-medium py-3 px-4 rounded-lg transition-colors
							{active
								? 'text-[var(--text-primary)]'
								: 'text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)]'}"
						style={active
							? `background-color: var(--nav-${item.color}-subtle);`
							: ''}
					>
						<Icon
							class="size-5 shrink-0"
							style={active ? `color: var(--nav-${item.color});` : ''}
						/>
						<span>{item.label}</span>
					</a>
				{/each}
			</nav>
		</div>
	{/if}
{/if}

<style>
	.logo-wrapper {
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: background-color 0.3s ease;
	}

	.logo-wrapper {
		background: radial-gradient(circle, #2d2240 55%, transparent 100%);
	}

	.logo-wrapper-lg {
		width: 5.5rem;
		height: 5.5rem;
	}

	.logo-wrapper-sm {
		width: 2.25rem;
		height: 2.25rem;
	}

	@media (min-width: 768px) {
		.logo-wrapper-lg {
			width: 6.5rem;
			height: 6.5rem;
		}
	}
</style>
