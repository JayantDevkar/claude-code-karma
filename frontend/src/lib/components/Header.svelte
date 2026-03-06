<script lang="ts">
	import { page } from '$app/stores';
	import { Menu, X, Settings } from 'lucide-svelte';
	import LogoIcon from '$lib/assets/LogoIcon.svelte';

	let mobileMenuOpen = $state(false);

	let isHome = $derived($page.url.pathname === '/');

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

			<!-- Center: Desktop Navigation -->
			<nav
				class="hidden md:flex items-center justify-center gap-4 overflow-visible"
				aria-label="Main navigation"
			>
				<a
					href="/projects"
					class="text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/projects')}
					aria-current={$page.url.pathname.startsWith('/projects') ? 'page' : undefined}
				>
					Projects
				</a>
				<a
					href="/sessions"
					class="text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/sessions')}
					aria-current={$page.url.pathname.startsWith('/sessions') ? 'page' : undefined}
				>
					Sessions
				</a>
				<a
					href="/plans"
					class="text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/plans')}
					aria-current={$page.url.pathname.startsWith('/plans') ? 'page' : undefined}
				>
					Plans
				</a>
				<a
					href="/agents"
					class="text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/agents')}
					aria-current={$page.url.pathname.startsWith('/agents') ? 'page' : undefined}
				>
					Agents
				</a>
				<a
					href="/skills"
					class="text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/skills')}
					aria-current={$page.url.pathname.startsWith('/skills') ? 'page' : undefined}
				>
					Skills
				</a>
				<a
					href="/commands"
					class="text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/commands')}
					aria-current={$page.url.pathname.startsWith('/commands') ? 'page' : undefined}
				>
					Commands
				</a>
				<a
					href="/tools"
					class="text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/tools')}
					aria-current={$page.url.pathname.startsWith('/tools') ? 'page' : undefined}
				>
					Tools
				</a>
				<a
					href="/hooks"
					class="text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/hooks')}
					aria-current={$page.url.pathname.startsWith('/hooks') ? 'page' : undefined}
				>
					Hooks
				</a>
				<a
					href="/plugins"
					class="text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/plugins')}
					aria-current={$page.url.pathname.startsWith('/plugins') ? 'page' : undefined}
				>
					Plugins
				</a>
				<a
					href="/analytics"
					class="text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/analytics')}
					aria-current={$page.url.pathname.startsWith('/analytics') ? 'page' : undefined}
				>
					Analytics
				</a>
				<a
					href="/archived"
					class="text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/archived')}
					aria-current={$page.url.pathname.startsWith('/archived') ? 'page' : undefined}
				>
					Archived
				</a>
				<a
					href="/sync"
					class="text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/sync')}
					aria-current={$page.url.pathname.startsWith('/sync') ? 'page' : undefined}
				>
					Sync
				</a>
				<a
					href="/team"
					class="text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/team')}
					aria-current={$page.url.pathname.startsWith('/team') ? 'page' : undefined}
				>
					Team
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
			<nav class="flex flex-col p-6 gap-1" aria-label="Mobile navigation">
				<a
					href="/projects"
					onclick={closeMobileMenu}
					class="text-base font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] py-3 px-4 rounded-lg transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/projects')}
					class:bg-[var(--bg-subtle)]={$page.url.pathname.startsWith('/projects')}
					aria-current={$page.url.pathname.startsWith('/projects') ? 'page' : undefined}
				>
					Projects
				</a>
				<a
					href="/sessions"
					onclick={closeMobileMenu}
					class="text-base font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] py-3 px-4 rounded-lg transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/sessions')}
					class:bg-[var(--bg-subtle)]={$page.url.pathname.startsWith('/sessions')}
					aria-current={$page.url.pathname.startsWith('/sessions') ? 'page' : undefined}
				>
					Sessions
				</a>
				<a
					href="/plans"
					onclick={closeMobileMenu}
					class="text-base font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] py-3 px-4 rounded-lg transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/plans')}
					class:bg-[var(--bg-subtle)]={$page.url.pathname.startsWith('/plans')}
					aria-current={$page.url.pathname.startsWith('/plans') ? 'page' : undefined}
				>
					Plans
				</a>
				<a
					href="/agents"
					onclick={closeMobileMenu}
					class="text-base font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] py-3 px-4 rounded-lg transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/agents')}
					class:bg-[var(--bg-subtle)]={$page.url.pathname.startsWith('/agents')}
					aria-current={$page.url.pathname.startsWith('/agents') ? 'page' : undefined}
				>
					Agents
				</a>
				<a
					href="/skills"
					onclick={closeMobileMenu}
					class="text-base font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] py-3 px-4 rounded-lg transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/skills')}
					class:bg-[var(--bg-subtle)]={$page.url.pathname.startsWith('/skills')}
					aria-current={$page.url.pathname.startsWith('/skills') ? 'page' : undefined}
				>
					Skills
				</a>
				<a
					href="/commands"
					onclick={closeMobileMenu}
					class="text-base font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] py-3 px-4 rounded-lg transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/commands')}
					class:bg-[var(--bg-subtle)]={$page.url.pathname.startsWith('/commands')}
					aria-current={$page.url.pathname.startsWith('/commands') ? 'page' : undefined}
				>
					Commands
				</a>
				<a
					href="/tools"
					onclick={closeMobileMenu}
					class="text-base font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] py-3 px-4 rounded-lg transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/tools')}
					class:bg-[var(--bg-subtle)]={$page.url.pathname.startsWith('/tools')}
					aria-current={$page.url.pathname.startsWith('/tools') ? 'page' : undefined}
				>
					Tools
				</a>
				<a
					href="/hooks"
					onclick={closeMobileMenu}
					class="text-base font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] py-3 px-4 rounded-lg transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/hooks')}
					class:bg-[var(--bg-subtle)]={$page.url.pathname.startsWith('/hooks')}
					aria-current={$page.url.pathname.startsWith('/hooks') ? 'page' : undefined}
				>
					Hooks
				</a>
				<a
					href="/plugins"
					onclick={closeMobileMenu}
					class="text-base font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] py-3 px-4 rounded-lg transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/plugins')}
					class:bg-[var(--bg-subtle)]={$page.url.pathname.startsWith('/plugins')}
					aria-current={$page.url.pathname.startsWith('/plugins') ? 'page' : undefined}
				>
					Plugins
				</a>
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
					href="/archived"
					onclick={closeMobileMenu}
					class="text-base font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] py-3 px-4 rounded-lg transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/archived')}
					class:bg-[var(--bg-subtle)]={$page.url.pathname.startsWith('/archived')}
					aria-current={$page.url.pathname.startsWith('/archived') ? 'page' : undefined}
				>
					Archived
				</a>
				<a
					href="/sync"
					onclick={closeMobileMenu}
					class="text-base font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] py-3 px-4 rounded-lg transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/sync')}
					class:bg-[var(--bg-subtle)]={$page.url.pathname.startsWith('/sync')}
					aria-current={$page.url.pathname.startsWith('/sync') ? 'page' : undefined}
				>
					Sync
				</a>
				<a
					href="/team"
					onclick={closeMobileMenu}
					class="text-base font-medium text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] py-3 px-4 rounded-lg transition-colors"
					class:text-[var(--text-primary)]={$page.url.pathname.startsWith('/team')}
					class:bg-[var(--bg-subtle)]={$page.url.pathname.startsWith('/team')}
					aria-current={$page.url.pathname.startsWith('/team') ? 'page' : undefined}
				>
					Team
				</a>
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
