<script lang="ts">
	import { page } from '$app/stores';
	import { onMount, onDestroy } from 'svelte';
	import { browser } from '$app/environment';
	import { Menu, X, Settings } from 'lucide-svelte';
	import LogoIcon from '$lib/assets/LogoIcon.svelte';
	import NavDropdown from './NavDropdown.svelte';
	import { API_BASE } from '$lib/config';

	const navGroups = [
		{
			label: 'Projects',
			items: [
				{ label: 'Projects', href: '/projects' },
				{ label: 'Sessions', href: '/sessions' },
				{ label: 'Plans', href: '/plans' },
				{ label: 'Archived', href: '/archived' }
			]
		},
		{
			label: 'Agents',
			items: [
				{ label: 'Agents', href: '/agents' },
				{ label: 'Skills', href: '/skills' },
				{ label: 'Commands', href: '/commands' }
			]
		},
		{
			label: 'Explore',
			items: [
				{ label: 'Tools', href: '/tools' },
				{ label: 'Hooks', href: '/hooks' },
				{ label: 'Plugins', href: '/plugins' }
			]
		},
		{
			label: 'Teams',
			items: [
				{ label: 'Teams', href: '/team' },
				{ label: 'Members', href: '/members' },
				{ label: 'Sync', href: '/sync' }
			]
		}
	] as const;

	let pendingDeviceCount = $state(0);
	let pendingPollInterval: ReturnType<typeof setInterval> | null = null;

	async function checkPendingDevices() {
		try {
			const res = await fetch(`${API_BASE}/sync/pending-devices`);
			if (res.ok) {
				const data = await res.json();
				pendingDeviceCount = data.devices?.length ?? 0;
			}
		} catch { /* non-critical */ }
	}

	let mobileMenuOpen = $state(false);
	let openDropdown = $state<string | null>(null);
	let navRef = $state<HTMLElement>();

	let isHome = $derived($page.url.pathname === '/');

	function toggleMobileMenu() {
		mobileMenuOpen = !mobileMenuOpen;
	}

	function closeMobileMenu() {
		mobileMenuOpen = false;
	}

	function toggleDropdown(label: string) {
		openDropdown = openDropdown === label ? null : label;
	}

	function closeDropdowns() {
		openDropdown = null;
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			if (openDropdown) closeDropdowns();
			else if (mobileMenuOpen) closeMobileMenu();
		}
	}

	function handleClickOutside(event: MouseEvent) {
		if (navRef && !navRef.contains(event.target as HTMLElement)) {
			closeDropdowns();
		}
	}

	// Close dropdowns on route change
	$effect(() => {
		$page.url.pathname;
		closeDropdowns();
	});

	onMount(() => {
		document.addEventListener('click', handleClickOutside);
		checkPendingDevices();
		pendingPollInterval = setInterval(checkPendingDevices, 60000);
	});

	onDestroy(() => {
		if (browser) {
			document.removeEventListener('click', handleClickOutside);
		}
		if (pendingPollInterval) clearInterval(pendingPollInterval);
	});
</script>

<svelte:window onkeydown={handleKeydown} />

{#if isHome}
	<!-- Big Centered Header (Home) -->
	<header
		class="w-full mx-auto pt-6 sm:pt-8 md:pt-10 pb-2 flex items-center justify-center relative header-container"
	>
		<div class="flex flex-col items-center gap-3 md:gap-4">
			<div class="logo-wrapper logo-wrapper-lg">
				<img src="/logo.png" alt="Claude Code Karma" class="w-16 h-16 md:w-20 md:h-20 object-contain" />
			</div>
			<div class="text-center flex flex-col items-center gap-0.5">
				<h1
					class="text-2xl sm:text-3xl font-semibold tracking-tight text-[var(--text-primary)]"
				>
					Claude <span class="font-bold">Code Karma</span>
				</h1>
				<p
					class="text-sm tracking-wide"
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
			class="w-full mx-auto grid grid-cols-[auto_1fr_auto] items-center header-container"
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

			<!-- Center: Desktop Navigation -->
			<nav
				bind:this={navRef}
				class="hidden md:flex items-center justify-center gap-5 overflow-visible"
				aria-label="Main navigation"
			>
				{#each navGroups as group, i}
					<NavDropdown
						label={group.label}
						items={group.items}
						open={openDropdown === group.label}
						onToggle={() => toggleDropdown(group.label)}
						onClose={closeDropdowns}
						align={i === navGroups.length - 1 ? 'right' : 'left'}
						badge={group.label === 'Teams' && pendingDeviceCount > 0}
					/>
				{/each}

				<a
					href="/analytics"
					class="text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/analytics')}
					aria-current={$page.url.pathname.startsWith('/analytics') ? 'page' : undefined}
				>
					Analytics
				</a>

				<a
					href="/about"
					class="text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/about')}
					aria-current={$page.url.pathname.startsWith('/about') ? 'page' : undefined}
				>
					About
				</a>
			</nav>

			<div class="flex items-center justify-end gap-3">
				<a
					href="/settings"
					class="p-2 rounded-lg hover:bg-[var(--bg-muted)] transition-colors text-[var(--text-muted)] hover:text-[var(--text-primary)]"
					title="Settings"
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
			<nav class="flex flex-col p-6 gap-4" aria-label="Mobile navigation">
				{#each navGroups as group}
					<div>
						<div class="px-4 pb-1 text-[10px] font-medium uppercase tracking-wider text-[var(--text-muted)]">
							{group.label}
						</div>
						{#each group.items as item (item.href)}
							{@const active = $page.url.pathname.startsWith(item.href)}
							<a
								href={item.href}
								onclick={closeMobileMenu}
								class="text-base font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] py-3 px-4 rounded-lg transition-colors"
								class:text-[var(--text-primary)]={active}
								class:bg-[var(--bg-subtle)]={active}
								aria-current={active ? 'page' : undefined}
							>
								{item.label}
							</a>
						{/each}
					</div>
				{/each}

				<div>
					<div class="px-4 pb-1 text-[10px] font-medium uppercase tracking-wider text-[var(--text-muted)]">
						Insights
					</div>
					<a
						href="/analytics"
						onclick={closeMobileMenu}
						class="text-base font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] py-3 px-4 rounded-lg transition-colors"
						class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/analytics')}
						class:bg-[var(--bg-subtle)]={$page.url.pathname.startsWith('/analytics')}
						aria-current={$page.url.pathname.startsWith('/analytics') ? 'page' : undefined}
					>
						Analytics
					</a>
					<a
						href="/about"
						onclick={closeMobileMenu}
						class="text-base font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] py-3 px-4 rounded-lg transition-colors"
						class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/about')}
						class:bg-[var(--bg-subtle)]={$page.url.pathname.startsWith('/about')}
						aria-current={$page.url.pathname.startsWith('/about') ? 'page' : undefined}
					>
						About
					</a>
				</div>
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

	.header-container {
		max-width: clamp(75rem, 90vw, 100rem);
		padding-inline: clamp(1rem, 3vw, 2.5rem);
	}
</style>
